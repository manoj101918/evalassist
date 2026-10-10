"""Tier 1 of the grading router: deterministic rules, no AI call.

Multiple-choice answers are graded by comparing the option the student chose with the correct
option. This is exact, instant and free, and it removes most AI calls on MCQ-heavy papers.
"""
import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.ai.schemas import QuestionSpec

OPTION_LINE_RE = re.compile(r"^\s*\(?([A-Z])[.)]\s+(.+?)\s*$", re.MULTILINE)
# A letter counts as a chosen option only when written like one: "B", "B.", "(b)", "Ans: C",
# "option d)" — i.e. followed by . ) : - or standing alone at the end of a line. So an answer
# starting with the article "A random forest…" is not read as option A.
OPTION_TOKEN_RE = re.compile(
    r"(?:^|(?<=[\s(:]))(?:(?i:ans(?:wer)?|option|opt)\s*[:\-.]?\s*)?\(?([A-Za-z])\)?(?=[.):\-]|[ \t]*$)",
    re.MULTILINE)
TEXT_MATCH_THRESHOLD = 85
OCR_LOOKALIKES = {"0": "D", "O": "D", "8": "B", "Ɗ": "D"}


@dataclass
class RuleGrade:
    chosen: str | None          # the option letter the student chose, if identifiable
    marks: float
    breakdown: list[dict]
    reason: str
    confidence: str             # green / yellow / red
    confidence_reasons: list[str]


def parse_options(question_text: str) -> dict[str, str]:
    """Options written in the question as lines like 'A. Random Forest'."""
    return {m.group(1): m.group(2) for m in OPTION_LINE_RE.finditer(question_text)}


def chosen_option(answer: str, options: dict[str, str]) -> tuple[str | None, str]:
    """Return (letter or None, how it was found). Tries the leading letter, then a single
    standalone capital letter, then the option text written out in words."""
    valid = set(options) or set("ABCDE")
    text = answer.strip()
    if not text or ("[illegible]" in text.lower() and len(text) < 20):
        return None, "unreadable"
    letters = {m.group(1).upper() for m in OPTION_TOKEN_RE.finditer(text)} & valid
    if len(letters) == 1:
        return letters.pop(), "letter"
    if len(letters) > 1:
        return None, "several options"
    if options:
        best = max(options, key=lambda k: fuzz.partial_ratio(options[k].lower(), text.lower()))
        if fuzz.partial_ratio(options[best].lower(), text.lower()) >= TEXT_MATCH_THRESHOLD:
            return best, "option text"
    # OCR sometimes reads a handwritten letter as a look-alike digit (a curly "D" as "0").
    # Options are letters, so a lone look-alike is almost certainly that letter; flagged for review.
    lone = text.strip(" .)(").upper()
    if lone in OCR_LOOKALIKES and OCR_LOOKALIKES[lone] in valid:
        return OCR_LOOKALIKES[lone], f"look-alike:{lone}"
    return None, "not identified"


def grade_mcq(q: QuestionSpec, answer: str, legibility: str) -> RuleGrade:
    options = parse_options(q.text)
    correct = (q.correct_option or "").upper()
    chosen, how = chosen_option(answer, options)
    correct_label = f"{correct}" + (f" ({options[correct]})" if correct in options else "")

    if chosen is None:
        reason = {
            "several options": "More than one option appears in the answer.",
            "unreadable": "The chosen option could not be read.",
        }.get(how, "Could not identify which option the student chose.")
        colour = "red" if legibility == "unreadable" or how == "unreadable" else "yellow"
        return RuleGrade(None, 0.0, [_point(q, correct_label, "absent", 0.0, answer, reason)],
                         reason, colour, [reason + " Please check the booklet."])

    right = chosen == correct
    marks = q.max_marks if right else 0.0
    reason = f"Student chose {chosen}; the correct answer is {correct_label}."
    reasons = [f"Graded by exact rule (no AI): {'correct' if right else 'incorrect'} option."]
    colour = "green"
    if how == "option text":
        colour = "yellow"
        reasons.append(f"Option inferred from the written text, not a letter: check it's really {chosen}.")
    elif how.startswith("look-alike:"):
        colour = "yellow"
        reasons.append(f"Read as '{how.split(':', 1)[1]}', taken as {chosen}: please confirm in the booklet.")
    if legibility != "clear":
        colour = "yellow"
        reasons.append("Some words on this page could not be read.")
    return RuleGrade(chosen, marks, [_point(q, correct_label, "full" if right else "absent",
                                            marks, answer.strip()[:80], reason)],
                     reason, colour, reasons)


def _point(q: QuestionSpec, correct_label: str, verdict: str, marks: float, quote: str, reason: str) -> dict:
    return {"point_number": 1, "description": f"Chooses the correct option: {correct_label}",
            "max_marks": q.max_marks, "verdict": verdict, "marks": marks,
            "evidence_quote": quote, "reason": reason}
