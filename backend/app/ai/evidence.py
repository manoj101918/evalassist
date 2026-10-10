"""Check that the evidence a grader quoted actually appears in the student's answer.

A quote that cannot be found is a sign the model invented or misremembered content, so it
lowers confidence (see confidence.decide).
"""
import re

from rapidfuzz import fuzz

MATCH_THRESHOLD = 85


def _normalise(text: str) -> str:
    text = text.lower().replace("[illegible]", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def quote_found(quote: str, answer_text: str) -> bool:
    q = _normalise(quote)
    if not q:
        return True
    a = _normalise(answer_text)
    if q in a:
        return True
    return fuzz.partial_ratio(q, a) >= MATCH_THRESHOLD


def missing_evidence(points: list[dict], answer_text: str) -> list[int]:
    """Point numbers that were awarded marks but whose quote isn't in the answer."""
    return [
        p["point_number"] for p in points
        if p["marks"] > 0 and not quote_found(p.get("evidence_quote", ""), answer_text)
    ]
