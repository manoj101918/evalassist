"""Decide the green / yellow / red flag for one answer.

Green  - teacher can approve quickly.
Yellow - something is slightly off; check the AI's reasoning.
Red    - teacher should grade this answer carefully.
"""
from dataclasses import dataclass

AGREE_TOLERANCE = 0.5       # marks; two gradings this close count as agreeing
LARGE_GAP_FRACTION = 0.25   # of max marks; a bigger gap between gradings is red


@dataclass
class ConfidenceInput:
    max_marks: float
    found: bool                   # segmentation located an answer for this question
    ambiguous: bool               # segmentation unsure about the answer's boundaries
    legibility: str               # worst legibility across the answer's pages
    has_diagram_or_math: bool
    marks_a: float
    marks_b: float
    missing_evidence: int         # awarded points whose quote isn't in the answer


def decide(ci: ConfidenceInput) -> tuple[str, list[str]]:
    red: list[str] = []
    yellow: list[str] = []

    if not ci.found:
        msg = "No answer found for this question; AI suggests 0. Check the booklet."
        (red if ci.legibility != "clear" else yellow).append(msg)
    if ci.ambiguous:
        red.append("Unclear where this answer starts or ends in the booklet.")
    if ci.legibility == "unreadable":
        red.append("Handwriting on this answer's pages could not be read reliably.")
    elif ci.legibility == "partial":
        yellow.append("Some words could not be read.")
    if ci.has_diagram_or_math:
        red.append("Answer includes a diagram or maths working; AI cannot grade these reliably yet.")

    gap = abs(ci.marks_a - ci.marks_b)
    if gap > LARGE_GAP_FRACTION * ci.max_marks:
        red.append(f"The two AI gradings disagree a lot ({ci.marks_a:g} vs {ci.marks_b:g}).")
    elif gap > AGREE_TOLERANCE:
        yellow.append(f"The two AI gradings differ slightly ({ci.marks_a:g} vs {ci.marks_b:g}).")

    if ci.missing_evidence:
        yellow.append(f"{ci.missing_evidence} awarded point(s) cite text not found in the answer.")

    if red:
        return "red", red + yellow
    if yellow:
        return "yellow", yellow
    return "green", ["Clear handwriting, both gradings agree, evidence verified."]


def worst_legibility(values: list[str]) -> str:
    order = {"clear": 0, "partial": 1, "unreadable": 2}
    return max(values, key=lambda v: order.get(v, 2)) if values else "clear"
