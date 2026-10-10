"""Structured-output models for each LLM call, plus plain specs the pipeline works with.

Output models avoid numeric/length constraints: structured outputs validate shape, and the
pipeline clamps values itself (see pipeline.clamp_grading).
"""
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

Legibility = Literal["clear", "partial", "unreadable"]
Verdict = Literal["full", "partial", "absent"]


# ---- LLM outputs ----------------------------------------------------------

class PageTranscript(BaseModel):
    text: str
    legibility: Legibility
    question_markers: list[str]
    has_diagram_or_math: bool
    # Word positions from OCR (Azure): {text, confidence, box: normalised polygon}. Empty for
    # the vision-model reader. Used to highlight evidence on the page image.
    words: list[dict] = []


class SegmentedAnswer(BaseModel):
    question_label: str
    pages: list[int]
    text: str
    ambiguous: bool
    note: str


class Segmentation(BaseModel):
    answers: list[SegmentedAnswer]


class PointGrade(BaseModel):
    point_number: int
    verdict: Verdict
    marks: float
    evidence_quote: str
    reason: str


class Grading(BaseModel):
    points: list[PointGrade]
    summary_reason: str


# ---- Pipeline inputs / outputs -------------------------------------------

@dataclass
class RubricPointSpec:
    description: str
    marks: float


@dataclass
class QuestionSpec:
    id: str
    label: str
    text: str
    max_marks: float
    rubric: list[RubricPointSpec]
    model_answer: str | None = None
    qtype: str = "short"               # "short" | "long" | "mcq"
    correct_option: str | None = None  # MCQ only, e.g. "B"

    @property
    def is_mcq(self) -> bool:
        return self.qtype == "mcq" and bool(self.correct_option)


@dataclass
class AnswerResult:
    question_id: str
    page_numbers: list[int]
    transcription: str
    ai_marks: float
    ai_breakdown: list[dict]
    ai_reason: str
    check_marks: float
    check_breakdown: list[dict]
    confidence: str
    confidence_reasons: list[str]


@dataclass
class ScriptResult:
    pages: list[PageTranscript]
    answers: list[AnswerResult] = field(default_factory=list)
