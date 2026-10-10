"""Load rows while enforcing that they belong to the current user's college.

The backend uses the service-role key (RLS bypassed), so these checks are the tenancy boundary.
"""
from fastapi import HTTPException, status

from app.auth import CurrentUser
from app.db import get_db


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def get_exam(exam_id: str, user: CurrentUser) -> dict:
    rows = (get_db().table("exams").select("*").eq("id", exam_id)
            .eq("college_id", user.college_id).limit(1).execute().data)
    if not rows:
        raise _not_found("Exam")
    return rows[0]


def get_question(question_id: str, user: CurrentUser) -> dict:
    rows = (get_db().table("questions").select("*, exams!inner(college_id), rubric_points(*)")
            .eq("id", question_id).eq("exams.college_id", user.college_id)
            .limit(1).execute().data)
    if not rows:
        raise _not_found("Question")
    return rows[0]


def get_script(script_id: str, user: CurrentUser) -> dict:
    rows = (get_db().table("scripts").select("*, exams!inner(college_id)")
            .eq("id", script_id).eq("exams.college_id", user.college_id)
            .limit(1).execute().data)
    if not rows:
        raise _not_found("Script")
    return rows[0]


def get_answer(answer_id: str, user: CurrentUser) -> dict:
    rows = (get_db().table("answers")
            .select("*, scripts!inner(id, exam_id, roll_number, status, assigned_to, exams!inner(college_id))")
            .eq("id", answer_id).eq("scripts.exams.college_id", user.college_id)
            .limit(1).execute().data)
    if not rows:
        raise _not_found("Answer")
    return rows[0]
