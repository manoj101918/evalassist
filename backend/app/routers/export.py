import re
from collections import defaultdict

from fastapi import APIRouter, Depends, Response

from app.access import get_exam
from app.audit import write_audit
from app.auth import STAFF, CurrentUser, require_role
from app.db import fetch_all, get_db
from app.export import build_workbook

router = APIRouter(tags=["export"])


@router.get("/exams/{exam_id}/export.xlsx")
def export_exam(exam_id: str, user: CurrentUser = Depends(require_role(*STAFF))):
    exam = get_exam(exam_id, user)
    db = get_db()
    questions = (db.table("questions").select("id, label, max_marks")
                 .eq("exam_id", exam_id).order("position").order("label").execute().data)
    scripts = fetch_all(lambda: db.table("scripts").select("id, roll_number")
                        .eq("exam_id", exam_id).order("id"))
    rows = fetch_all(lambda: db.table("answers")
                     .select("script_id, question_id, ai_marks, check_marks, confidence, status, "
                             "scripts!inner(exam_id), "
                             "final_marks(marks, decided_at, comment, profiles(full_name))")
                     .eq("scripts.exam_id", exam_id).order("id"))
    answers = []
    for r in rows:
        fm = r.get("final_marks")
        fm = (fm[0] if fm else None) if isinstance(fm, list) else fm
        answers.append({
            "script_id": r["script_id"], "question_id": r["question_id"],
            "ai_marks": r["ai_marks"], "check_marks": r["check_marks"],
            "confidence": r["confidence"], "status": r["status"],
            "final_marks": fm["marks"] if fm else None,
            "decided_by": ((fm.get("profiles") or {}).get("full_name") if fm else None),
            "decided_at": fm["decided_at"] if fm else None,
            "comment": fm["comment"] if fm else None,
        })

    cost_by_script: dict[str, float] = defaultdict(float)
    script_ids = [s["id"] for s in scripts]
    for i in range(0, len(script_ids), 200):
        chunk = script_ids[i:i + 200]
        for c in fetch_all(lambda chunk=chunk: db.table("ai_calls").select("script_id, cost_usd")
                           .in_("script_id", chunk).order("id")):
            cost_by_script[c["script_id"]] += float(c["cost_usd"])

    content = build_workbook(exam, questions, scripts, answers, cost_by_script)
    write_audit(user, "exam.export", "exam", exam_id)
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", exam["subject"]).strip("_") or "exam"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}_marks.xlsx"'},
    )
