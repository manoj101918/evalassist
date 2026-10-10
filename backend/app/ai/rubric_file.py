"""Load an exam's questions and rubric from a JSON file (used by the CLI runner and evals).

Format:
    {"questions": [
        {"label": "1", "type": "mcq", "correct_option": "B", "text": "... A. ...\\nB. ...",
         "max_marks": 1},
        {"label": "21", "type": "short", "text": "...", "max_marks": 2, "model_answer": "...",
         "rubric": [{"description": "...", "marks": 2}]}
    ]}
"""
import json
from pathlib import Path

from app.ai.schemas import QuestionSpec, RubricPointSpec


def load_rubric(path: Path) -> list[QuestionSpec]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    specs = []
    for q in data["questions"]:
        qtype = q.get("type", "short")
        max_marks = float(q["max_marks"])
        rubric = [RubricPointSpec(p["description"], float(p["marks"])) for p in q.get("rubric", [])]
        if qtype == "mcq" and not rubric:
            rubric = [RubricPointSpec(f"Chooses the correct option: {q['correct_option']}", max_marks)]
        specs.append(QuestionSpec(
            id=q["label"], label=q["label"], text=q["text"], max_marks=max_marks,
            model_answer=q.get("model_answer"), rubric=rubric,
            qtype=qtype, correct_option=q.get("correct_option"),
        ))
    return specs
