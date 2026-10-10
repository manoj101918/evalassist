"""The evaluation dataset: 50 real handwritten Data Science exam booklets with teacher marks.

Source: Dinesh K P, "A Dataset of Digitized Student Examination Papers, Answer Keys, and
Manual Evaluations for Automated Grading Research", Mendeley Data V1,
doi:10.17632/sf3kvjwknt.1 (CC BY 4.0). Download with `python -m evals.download_dataset`.

Exam: Q1–Q20 MCQ (1 mark), Q21–Q35 short answers (2 marks), 50 marks total.
Ground truth used:
  - short answers: the teacher's per-question marks (blank / NC / NM = 0);
  - MCQs: the option the teacher recorded for each student (the dataset's MCQ *totals* don't
    match its own key, so we score whether the AI read the same option the teacher did).
"""
import csv
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path

from app.ai.schemas import QuestionSpec, RubricPointSpec

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("EVAL_DATA_DIR", REPO_ROOT / "samples" / "mendeley_ds_exam"))
PDF_DIR = DATA_DIR / "Student_Pdf"
MARKS_CSV = DATA_DIR / "Teacher_manual_marks_Anonymized.csv"
SPLIT_SEED = 42
SPLIT_SIZES = {"test": 10, "val": 10}  # the remaining students are "train"


@dataclass
class StudentTruth:
    short: dict[str, float]    # question label → teacher marks (Q21–Q35)
    mcq_choice: dict[str, str]  # question label → option recorded by the teacher (Q1–Q20)


def build_questions() -> list[QuestionSpec]:
    """Question paper + answer key → QuestionSpecs (MCQs graded by rule, short answers by AI)."""
    text = (DATA_DIR / "Question.txt").read_text(encoding="utf-8")
    key = {r["Question_Number"]: r for r in csv.DictReader(open(DATA_DIR / "answerkey.txt", encoding="utf-8"))}
    parsed: dict[str, dict] = {}
    current = None
    for line in text.splitlines():
        if m := re.match(r"^(\d+)\.\s+(.*)", line):
            current = m.group(1)
            parsed[current] = {"text": m.group(2).strip(), "options": []}
        elif (o := re.match(r"^([A-D])\.\s+(.*)", line)) and current:
            parsed[current]["options"].append(f"{o.group(1)}. {o.group(2).strip()}")
    specs = []
    for label in sorted(parsed, key=int):
        q, k = parsed[label], key[label]
        if k["Type"] == "MCQ":
            specs.append(QuestionSpec(
                id=label, label=label, text="\n".join([q["text"], *q["options"]]), max_marks=1,
                qtype="mcq", correct_option=k["Correct_Answer"].strip(),
                rubric=[RubricPointSpec(f"Chooses the correct option: {k['Correct_Answer']}", 1)],
            ))
        else:
            answer = k["Correct_Answer"].strip()
            specs.append(QuestionSpec(
                id=label, label=label, text=q["text"], max_marks=2, model_answer=answer,
                rubric=[RubricPointSpec(f"Correct answer covering: {answer}", 2)],
            ))
    return specs


def load_truth() -> dict[str, StudentTruth]:
    truth = {}
    for row in csv.DictReader(open(MARKS_CSV, encoding="utf-8")):
        short = {}
        for n in range(21, 36):
            v = (row[str(n)] or "").strip()
            short[str(n)] = float(v) if v not in ("", "NC", "NM") else 0.0
        choices = {str(n): (row[str(n)] or "").strip().upper() for n in range(1, 21)}
        truth[row["Student_ID"]] = StudentTruth(short=short, mcq_choice=choices)
    return truth


def students() -> list[str]:
    return sorted(load_truth(), key=lambda s: int(s.split("_")[1]))


def split(name: str) -> list[str]:
    """Deterministic split by student, so no student is in both training and test data."""
    ids = students()
    random.Random(SPLIT_SEED).shuffle(ids)
    test, val = ids[:SPLIT_SIZES["test"]], ids[SPLIT_SIZES["test"]:SPLIT_SIZES["test"] + SPLIT_SIZES["val"]]
    groups = {"test": test, "val": val, "train": ids[len(test) + len(val):], "all": students()}
    return sorted(groups[name], key=lambda s: int(s.split("_")[1]))


def pdf_path(student: str) -> Path:
    return PDF_DIR / f"{student}.pdf"
