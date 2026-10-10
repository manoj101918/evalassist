from app.ai.schemas import QuestionSpec, RubricPointSpec
from app.db import get_db


def load_questions(exam_id: str) -> list[QuestionSpec]:
    rows = (get_db().table("questions")
            .select("*, rubric_points(*)")
            .eq("exam_id", exam_id)
            .order("position").order("label")
            .execute().data)
    specs = []
    for r in rows:
        points = sorted(r.get("rubric_points") or [], key=lambda p: p["position"])
        specs.append(QuestionSpec(
            id=r["id"], label=r["label"], text=r["text"], max_marks=float(r["max_marks"]),
            model_answer=r.get("model_answer"),
            rubric=[RubricPointSpec(p["description"], float(p["marks"])) for p in points],
            qtype=r.get("qtype") or "short",
            correct_option=r.get("correct_option"),
        ))
    return specs


def rubric_problems(questions: list[QuestionSpec]) -> list[str]:
    """Questions that can't be graded yet: missing rubric, wrong totals, MCQ without an answer."""
    problems = []
    for q in questions:
        if q.qtype == "mcq":
            if not q.correct_option:
                problems.append(f"Question {q.label} is multiple choice but has no correct option.")
            continue  # MCQs are graded by the correct option, not rubric points
        total = sum(p.marks for p in q.rubric)
        if not q.rubric:
            problems.append(f"Question {q.label} has no rubric points.")
        elif abs(total - q.max_marks) > 1e-6:
            problems.append(f"Question {q.label}: rubric adds up to {total:g}, but max marks is {q.max_marks:g}.")
    return problems
