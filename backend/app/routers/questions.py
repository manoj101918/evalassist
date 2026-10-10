import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.access import get_exam, get_question
from app.audit import write_audit
from app.auth import ANY_ROLE, CurrentUser, require_role
from app.db import get_db

router = APIRouter(tags=["questions"])


class RubricPointIn(BaseModel):
    description: str = Field(min_length=1)
    marks: float = Field(gt=0)


class QuestionIn(BaseModel):
    label: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1)
    max_marks: float = Field(gt=0)
    position: int = 0
    model_answer: str | None = None
    qtype: Literal["short", "long", "mcq"] = "short"
    correct_option: str | None = None
    rubric_points: list[RubricPointIn] = []

    @model_validator(mode="after")
    def check_rubric(self):
        if self.qtype == "mcq":
            option = (self.correct_option or "").strip().upper()
            if not re.fullmatch(r"[A-Z]", option):
                raise ValueError("Multiple-choice questions need the correct option, a single letter like B")
            self.correct_option = option
            # MCQs are graded by the correct option; keep one matching point for display.
            self.rubric_points = [RubricPointIn(description=f"Chooses the correct option: {option}",
                                                marks=self.max_marks)]
            return self
        self.correct_option = None
        total = sum(p.marks for p in self.rubric_points)
        if total > self.max_marks + 1e-6:
            raise ValueError(f"Rubric points add up to {total:g}, more than max marks {self.max_marks:g}")
        return self


def _save_points(question_id: str, points: list[RubricPointIn]) -> list[dict]:
    db = get_db()
    db.table("rubric_points").delete().eq("question_id", question_id).execute()
    if not points:
        return []
    return db.table("rubric_points").insert([
        {"question_id": question_id, "description": p.description, "marks": p.marks, "position": i}
        for i, p in enumerate(points)
    ]).execute().data


def _question_fields(body: QuestionIn) -> dict:
    return body.model_dump(exclude={"rubric_points"})


@router.post("/exams/{exam_id}/questions", status_code=201)
def create_question(exam_id: str, body: QuestionIn,
                    user: CurrentUser = Depends(require_role(*ANY_ROLE))):
    get_exam(exam_id, user)
    db = get_db()
    exists = db.table("questions").select("id").eq("exam_id", exam_id).eq("label", body.label).execute().data
    if exists:
        raise HTTPException(409, f"Question {body.label} already exists in this exam")
    row = db.table("questions").insert({**_question_fields(body), "exam_id": exam_id}).execute().data[0]
    row["rubric_points"] = _save_points(row["id"], body.rubric_points)
    write_audit(user, "question.create", "question", row["id"], after=row)
    return row


@router.put("/questions/{question_id}")
def update_question(question_id: str, body: QuestionIn,
                    user: CurrentUser = Depends(require_role(*ANY_ROLE))):
    before = get_question(question_id, user)
    before.pop("exams", None)
    row = get_db().table("questions").update(_question_fields(body)).eq("id", question_id).execute().data[0]
    row["rubric_points"] = _save_points(question_id, body.rubric_points)
    write_audit(user, "question.update", "question", question_id, before=before, after=row)
    return row


@router.delete("/questions/{question_id}", status_code=204)
def delete_question(question_id: str, user: CurrentUser = Depends(require_role(*ANY_ROLE))):
    before = get_question(question_id, user)
    before.pop("exams", None)
    get_db().table("questions").delete().eq("id", question_id).execute()
    write_audit(user, "question.delete", "question", question_id, before=before)
