from collections import Counter
from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.access import get_exam
from app.audit import write_audit
from app.auth import ANY_ROLE, STAFF, CurrentUser, require_role
from app.db import get_db, signed_url, storage
from app.questions_repo import load_questions, rubric_problems

router = APIRouter(prefix="/exams", tags=["exams"])


class ExamIn(BaseModel):
    subject: str = Field(min_length=1)
    exam_date: date | None = None
    total_marks: float = Field(gt=0)


@router.get("")
def list_exams(user: CurrentUser = Depends(require_role(*ANY_ROLE))):
    db = get_db()
    q = db.table("exams").select("*").eq("college_id", user.college_id)
    if not user.is_staff:
        # Teachers only see exams in which scripts are assigned to them.
        mine = db.table("scripts").select("exam_id").eq("assigned_to", user.id).execute().data
        q = q.in_("id", sorted({s["exam_id"] for s in mine}) or ["00000000-0000-0000-0000-000000000000"])
    exams = q.order("created_at", desc=True).execute().data
    if exams:
        scripts = (db.table("scripts").select("exam_id, status")
                   .in_("exam_id", [e["id"] for e in exams]).execute().data)
        counts: dict[str, Counter] = {}
        for s in scripts:
            counts.setdefault(s["exam_id"], Counter())[s["status"]] += 1
        for e in exams:
            e["script_counts"] = dict(counts.get(e["id"], Counter()))
    return exams


@router.post("", status_code=201)
def create_exam(body: ExamIn, user: CurrentUser = Depends(require_role(*STAFF))):
    row = get_db().table("exams").insert({
        **body.model_dump(mode="json"), "college_id": user.college_id, "created_by": user.id,
    }).execute().data[0]
    write_audit(user, "exam.create", "exam", row["id"], after=row)
    return row


@router.get("/{exam_id}")
def exam_detail(exam_id: str, user: CurrentUser = Depends(require_role(*ANY_ROLE))):
    exam = get_exam(exam_id, user)
    questions = (get_db().table("questions").select("*, rubric_points(*)")
                 .eq("exam_id", exam_id).order("position").order("label").execute().data)
    for q in questions:
        q["rubric_points"].sort(key=lambda p: p["position"])
    exam["questions"] = questions
    exam["rubric_problems"] = rubric_problems(load_questions(exam_id))
    questions_total = sum(float(q["max_marks"]) for q in questions)
    if questions and abs(questions_total - float(exam["total_marks"])) > 1e-6:
        exam["rubric_problems"].append(
            f"Questions add up to {questions_total:g} marks, but the exam total is {float(exam['total_marks']):g}.")
    exam["question_paper_url"] = (signed_url(exam["question_paper_path"])
                                  if exam.get("question_paper_path") else None)
    return exam


@router.patch("/{exam_id}")
def update_exam(exam_id: str, body: ExamIn, user: CurrentUser = Depends(require_role(*STAFF))):
    before = get_exam(exam_id, user)
    row = get_db().table("exams").update(body.model_dump(mode="json")).eq("id", exam_id).execute().data[0]
    write_audit(user, "exam.update", "exam", exam_id, before=before, after=row)
    return row


@router.delete("/{exam_id}", status_code=204)
def delete_exam(exam_id: str, user: CurrentUser = Depends(require_role(*STAFF))):
    before = get_exam(exam_id, user)
    get_db().table("exams").delete().eq("id", exam_id).execute()
    write_audit(user, "exam.delete", "exam", exam_id, before=before)


@router.post("/{exam_id}/question-paper")
async def upload_question_paper(exam_id: str, file: UploadFile = File(...),
                                user: CurrentUser = Depends(require_role(*STAFF))):
    get_exam(exam_id, user)
    data = await file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Question paper must be a PDF")
    path = f"{user.college_id}/{exam_id}/question-paper-{uuid4().hex[:8]}.pdf"
    storage().upload(path, data, {"content-type": "application/pdf", "upsert": "true"})
    get_db().table("exams").update({"question_paper_path": path}).eq("id", exam_id).execute()
    write_audit(user, "exam.question_paper", "exam", exam_id, after={"path": path})
    return {"question_paper_url": signed_url(path)}
