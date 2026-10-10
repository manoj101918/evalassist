from collections import Counter
from datetime import UTC, datetime
from pathlib import PurePath
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.access import get_exam, get_script
from app.audit import write_audit
from app.auth import ANY_ROLE, STAFF, CurrentUser, require_role
from app.db import fetch_all, get_db, storage
from app.pdf import page_count
from app.questions_repo import load_questions, rubric_problems

router = APIRouter(tags=["scripts"])

MAX_PDF_BYTES = 50 * 1024 * 1024


def roll_from_filename(filename: str) -> str:
    return PurePath(filename).stem.strip().upper()


@router.post("/exams/{exam_id}/scripts", status_code=201)
async def upload_scripts(exam_id: str, files: list[UploadFile] = File(...),
                         user: CurrentUser = Depends(require_role(*STAFF))):
    get_exam(exam_id, user)
    questions = load_questions(exam_id)
    if not questions:
        raise HTTPException(400, "Add the exam's questions and rubrics before uploading scripts.")
    problems = rubric_problems(questions)
    if problems:
        raise HTTPException(400, "Fix the rubric first: " + " ".join(problems))

    db = get_db()
    results = []
    for f in files:
        roll = roll_from_filename(f.filename or "")
        data = await f.read()
        try:
            if not data.startswith(b"%PDF"):
                raise ValueError("not a PDF file")
            if len(data) > MAX_PDF_BYTES:
                raise ValueError("file is larger than 50 MB")
            pages = page_count(data)
            if pages == 0:
                raise ValueError("PDF has no pages")
            if db.table("scripts").select("id").eq("exam_id", exam_id).eq("roll_number", roll).execute().data:
                raise ValueError(f"roll number {roll} already uploaded for this exam")
            script_id = str(uuid4())
            path = f"{user.college_id}/{exam_id}/{script_id}/original.pdf"
            storage().upload(path, data, {"content-type": "application/pdf"})
            row = db.table("scripts").insert({
                "id": script_id, "exam_id": exam_id, "roll_number": roll, "pdf_path": path,
                "page_count": pages, "status": "queued", "uploaded_by": user.id,
            }).execute().data[0]
            write_audit(user, "script.upload", "script", script_id,
                        after={"roll_number": roll, "pages": pages, "filename": f.filename})
            results.append({"filename": f.filename, "ok": True, "script": row})
        except Exception as exc:  # noqa: BLE001 - report per-file errors, keep going
            results.append({"filename": f.filename, "ok": False, "error": str(exc)})
    return results


SCRIPT_FIELDS = ("id, exam_id, roll_number, page_count, status, error, attempts, created_at, processed_at, "
                 "assigned_to, assigned_at, assignee:profiles!scripts_assigned_to_fkey(full_name, employee_id)")


def attach_progress(scripts: list[dict]) -> list[dict]:
    """Add answer counts per script: total, decided, and per confidence colour."""
    db = get_db()
    ids = [s["id"] for s in scripts]
    progress: dict[str, Counter] = {}
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        for a in fetch_all(lambda chunk=chunk: db.table("answers").select("id, script_id, status, confidence")
                           .in_("script_id", chunk).order("id")):
            c = progress.setdefault(a["script_id"], Counter())
            c["total"] += 1
            c[a["confidence"]] += 1
            if a["status"] != "pending":
                c["decided"] += 1
    for s in scripts:
        s["answers"] = dict(progress.get(s["id"], Counter()))
    return scripts


@router.get("/exams/{exam_id}/scripts")
def list_scripts(exam_id: str, user: CurrentUser = Depends(require_role(*ANY_ROLE))):
    get_exam(exam_id, user)
    db = get_db()

    def query():
        q = db.table("scripts").select(SCRIPT_FIELDS).eq("exam_id", exam_id)
        if not user.is_staff:
            q = q.eq("assigned_to", user.id)
        return q.order("roll_number")

    return attach_progress(fetch_all(query))


@router.get("/my/scripts")
def my_scripts(user: CurrentUser = Depends(require_role(*ANY_ROLE))):
    """Scripts assigned to the signed-in user, across all exams, for the teacher's home page."""
    db = get_db()
    scripts = fetch_all(lambda: db.table("scripts")
                        .select(f"{SCRIPT_FIELDS}, exams!inner(subject, exam_date, total_marks, college_id)")
                        .eq("assigned_to", user.id).eq("exams.college_id", user.college_id)
                        .order("assigned_at", desc=True).order("roll_number"))
    for s in scripts:
        exam = s.pop("exams")
        exam.pop("college_id", None)
        s["exam"] = exam
    return attach_progress(scripts)


class AssignIn(BaseModel):
    script_ids: list[str] = Field(min_length=1)
    teacher_id: str | None  # None unassigns


class DistributeIn(BaseModel):
    teacher_ids: list[str] = Field(min_length=1)
    only_unassigned: bool = True


def _college_staff(user: CurrentUser, ids: list[str]) -> dict[str, dict]:
    rows = (get_db().table("profiles").select("id, full_name, employee_id, role")
            .eq("college_id", user.college_id).in_("id", ids).execute().data)
    found = {r["id"]: r for r in rows}
    missing = set(ids) - set(found)
    if missing:
        raise HTTPException(400, "Unknown teacher selected")
    return found


def balanced_assignment(script_ids: list[str], teacher_ids: list[str],
                        current_load: dict[str, int]) -> dict[str, str]:
    """Give each script to the teacher with the fewest scripts so far (ties by list order)."""
    load = {t: current_load.get(t, 0) for t in teacher_ids}
    result = {}
    for sid in script_ids:
        teacher = min(teacher_ids, key=lambda t: load[t])
        result[sid] = teacher
        load[teacher] += 1
    return result


def _assign(user: CurrentUser, exam_id: str, mapping: dict[str, str | None]) -> None:
    db = get_db()
    now = datetime.now(UTC).isoformat()
    by_teacher: dict[str | None, list[str]] = {}
    for sid, tid in mapping.items():
        by_teacher.setdefault(tid, []).append(sid)
    for tid, sids in by_teacher.items():
        db.table("scripts").update({"assigned_to": tid, "assigned_at": now if tid else None}) \
            .eq("exam_id", exam_id).in_("id", sids).execute()
        write_audit(user, "script.assign", "exam", exam_id, after={"teacher_id": tid, "script_ids": sids})


@router.post("/exams/{exam_id}/assign")
def assign_scripts(exam_id: str, body: AssignIn, user: CurrentUser = Depends(require_role(*STAFF))):
    get_exam(exam_id, user)
    if body.teacher_id:
        _college_staff(user, [body.teacher_id])
    valid = {r["id"] for r in get_db().table("scripts").select("id").eq("exam_id", exam_id)
             .in_("id", body.script_ids).execute().data}
    if valid != set(body.script_ids):
        raise HTTPException(400, "Some scripts are not in this exam")
    _assign(user, exam_id, {sid: body.teacher_id for sid in body.script_ids})
    return {"assigned": len(body.script_ids)}


@router.post("/exams/{exam_id}/assign/distribute")
def distribute_scripts(exam_id: str, body: DistributeIn, user: CurrentUser = Depends(require_role(*STAFF))):
    get_exam(exam_id, user)
    _college_staff(user, body.teacher_ids)
    scripts = fetch_all(lambda: get_db().table("scripts").select("id, assigned_to")
                        .eq("exam_id", exam_id).order("roll_number"))
    to_assign = [s["id"] for s in scripts if not (body.only_unassigned and s["assigned_to"])]
    load = Counter(s["assigned_to"] for s in scripts if s["assigned_to"] and s["id"] not in to_assign)
    mapping = balanced_assignment(to_assign, body.teacher_ids, load)
    _assign(user, exam_id, mapping)
    return {"assigned": len(mapping), "per_teacher": dict(Counter(mapping.values()))}


class ScriptPatch(BaseModel):
    roll_number: str = Field(min_length=1, max_length=50)


@router.patch("/scripts/{script_id}")
def rename_script(script_id: str, body: ScriptPatch, user: CurrentUser = Depends(require_role(*STAFF))):
    before = get_script(script_id, user)
    roll = body.roll_number.strip().upper()
    clash = (get_db().table("scripts").select("id").eq("exam_id", before["exam_id"])
             .eq("roll_number", roll).neq("id", script_id).execute().data)
    if clash:
        raise HTTPException(409, f"Roll number {roll} already exists in this exam")
    row = get_db().table("scripts").update({"roll_number": roll}).eq("id", script_id).execute().data[0]
    write_audit(user, "script.rename", "script", script_id,
                before={"roll_number": before["roll_number"]}, after={"roll_number": roll})
    return row


@router.post("/scripts/{script_id}/retry")
def retry_script(script_id: str, user: CurrentUser = Depends(require_role(*STAFF))):
    script = get_script(script_id, user)
    if script["status"] not in ("failed", "ready"):
        raise HTTPException(400, f"Script is {script['status']}; only failed or unreviewed scripts can be re-run")
    decided = (get_db().table("answers").select("id").eq("script_id", script_id)
               .neq("status", "pending").limit(1).execute().data)
    if decided:
        raise HTTPException(400, "A teacher has already reviewed answers in this script; it can't be re-run")
    get_db().table("scripts").update({"status": "queued", "attempts": 0, "error": None}).eq("id", script_id).execute()
    write_audit(user, "script.retry", "script", script_id)
    return {"ok": True}


@router.delete("/scripts/{script_id}", status_code=204)
def delete_script(script_id: str, user: CurrentUser = Depends(require_role(*STAFF))):
    script = get_script(script_id, user)
    folder = script["pdf_path"].rsplit("/", 1)[0]
    files = [f"{folder}/{f['name']}" for f in storage().list(folder)]
    if files:
        storage().remove(files)
    get_db().table("scripts").delete().eq("id", script_id).execute()
    write_audit(user, "script.delete", "script", script_id,
                before={"roll_number": script["roll_number"], "status": script["status"]})
