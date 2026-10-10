from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.access import get_answer, get_exam, get_script
from app.audit import write_audit
from app.auth import ANY_ROLE, CurrentUser, require_role, require_script_access
from app.db import fetch_all, get_db, signed_url

router = APIRouter(tags=["review"])

CONFIDENCE_ORDER = {"red": 0, "yellow": 1, "green": 2}


def _one(value):
    """PostgREST returns one-to-one embeds as an object, but be tolerant of a list."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


@router.get("/exams/{exam_id}/answers")
def review_queue(exam_id: str,
                 confidence: Literal["green", "yellow", "red"] | None = None,
                 status: Literal["pending", "decided"] | None = None,
                 question_id: str | None = None,
                 script_id: str | None = None,
                 user: CurrentUser = Depends(require_role(*ANY_ROLE))):
    get_exam(exam_id, user)
    db = get_db()

    def query():
        q = (db.table("answers")
             .select("id, script_id, question_id, ai_marks, check_marks, confidence, status, "
                     "scripts!inner(roll_number, exam_id, assigned_to), "
                     "questions!inner(label, position, max_marks), final_marks(marks)")
             .eq("scripts.exam_id", exam_id))
        if not user.is_staff:
            q = q.eq("scripts.assigned_to", user.id)
        if script_id:
            q = q.eq("script_id", script_id)
        if confidence:
            q = q.eq("confidence", confidence)
        if status == "pending":
            q = q.eq("status", "pending")
        elif status == "decided":
            q = q.neq("status", "pending")
        if question_id:
            q = q.eq("question_id", question_id)
        return q.order("id")

    rows = fetch_all(query)
    items = []
    for r in rows:
        fm = _one(r.get("final_marks"))
        items.append({
            "id": r["id"], "script_id": r["script_id"], "question_id": r["question_id"],
            "roll_number": r["scripts"]["roll_number"], "question_label": r["questions"]["label"],
            "question_position": r["questions"]["position"], "max_marks": r["questions"]["max_marks"],
            "ai_marks": r["ai_marks"], "check_marks": r["check_marks"],
            "confidence": r["confidence"], "status": r["status"],
            "final_marks": fm["marks"] if fm else None,
        })
    items.sort(key=lambda a: (CONFIDENCE_ORDER[a["confidence"]], a["roll_number"],
                              a["question_position"], a["question_label"]))
    return items


@router.get("/answers/{answer_id}")
def answer_detail(answer_id: str, user: CurrentUser = Depends(require_role(*ANY_ROLE))):
    answer = get_answer(answer_id, user)
    require_script_access(user, answer["scripts"])
    db = get_db()
    question = (db.table("questions").select("*, rubric_points(*)")
                .eq("id", answer["question_id"]).execute().data[0])
    question["rubric_points"].sort(key=lambda p: p["position"])
    pages = (db.table("script_pages").select("page_no, image_path, legibility")
             .eq("script_id", answer["script_id"]).order("page_no").execute().data)
    shown = set(answer["page_numbers"]) or {p["page_no"] for p in pages}
    final = db.table("final_marks").select("*").eq("answer_id", answer_id).execute().data
    script = answer.pop("scripts")
    return {
        **answer,
        "roll_number": script["roll_number"],
        "exam_id": script["exam_id"],
        "question": question,
        "pages": [{"page_no": p["page_no"], "legibility": p["legibility"],
                   "url": signed_url(p["image_path"]), "is_answer_page": p["page_no"] in shown}
                  for p in pages],
        "final": final[0] if final else None,
    }


class DecisionIn(BaseModel):
    action: Literal["accept", "change"]
    marks: float | None = Field(default=None, ge=0)
    comment: str | None = None


def _decide(answer: dict, marks: float, action: str, comment: str | None, user: CurrentUser) -> dict:
    db = get_db()
    before_final = db.table("final_marks").select("*").eq("answer_id", answer["id"]).execute().data
    final = {
        "answer_id": answer["id"], "marks": marks, "decided_by": user.id,
        "decided_at": datetime.now(UTC).isoformat(), "comment": comment,
    }
    db.table("final_marks").upsert(final, on_conflict="answer_id").execute()
    status = "accepted" if action == "accept" else "changed"
    db.table("answers").update({"status": status}).eq("id", answer["id"]).execute()
    write_audit(user, f"answer.{status}", "answer", answer["id"],
                before={"status": answer["status"], "ai_marks": answer["ai_marks"],
                        "final_marks": before_final[0]["marks"] if before_final else None},
                after={"status": status, "final_marks": marks, "comment": comment})
    return final


def _refresh_script_status(script_id: str) -> None:
    db = get_db()
    pending = (db.table("answers").select("id").eq("script_id", script_id)
               .eq("status", "pending").limit(1).execute().data)
    db.table("scripts").update({"status": "ready" if pending else "reviewed"}).eq("id", script_id).execute()


@router.post("/answers/{answer_id}/decision")
def decide_answer(answer_id: str, body: DecisionIn, user: CurrentUser = Depends(require_role(*ANY_ROLE))):
    answer = get_answer(answer_id, user)
    require_script_access(user, answer["scripts"])
    if answer["scripts"]["status"] not in ("ready", "reviewed"):
        raise HTTPException(400, "This script is still being processed")
    max_marks = float(get_db().table("questions").select("max_marks")
                      .eq("id", answer["question_id"]).execute().data[0]["max_marks"])
    if body.action == "accept":
        marks = float(answer["ai_marks"] or 0)
    else:
        if body.marks is None:
            raise HTTPException(400, "Enter the marks to give")
        marks = body.marks
    if marks > max_marks:
        raise HTTPException(400, f"Marks can't be more than {max_marks:g}")
    final = _decide(answer, marks, body.action, body.comment, user)
    _refresh_script_status(answer["script_id"])
    return final


@router.post("/scripts/{script_id}/accept-green")
def accept_green(script_id: str, user: CurrentUser = Depends(require_role(*ANY_ROLE))):
    script = get_script(script_id, user)
    require_script_access(user, script)
    if script["status"] not in ("ready", "reviewed"):
        raise HTTPException(400, "This script is still being processed")
    greens = (get_db().table("answers").select("*").eq("script_id", script_id)
              .eq("confidence", "green").eq("status", "pending").execute().data)
    for a in greens:
        _decide(a, float(a["ai_marks"] or 0), "accept", "Bulk-accepted (green)", user)
    _refresh_script_status(script_id)
    return {"accepted": len(greens)}

