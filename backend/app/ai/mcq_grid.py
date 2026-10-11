"""Read MCQ answers written as a grid ("1, A" / "2, D" / …) from OCR word positions.

Students often write MCQ answers as a column of question numbers with the chosen letter beside
each. OCR reads such a grid column by column, so the plain text comes out as all the numbers
followed by all the letters, and the question-to-letter pairing is lost. Azure also returns
where every word is on the page, so we pair each number with the letter on the same row.

Only pages that look like an MCQ grid (several number–letter pairs) are trusted, so a list in a
written answer ("1. A random forest…") is not mistaken for MCQ answers. The letter may be
followed by the option's text ("D. All of the mentioned"). A number with no letter
beside it becomes a cell to re-read from the page image (see pipeline.reread_mcq_cells).
"""
import re
from dataclasses import dataclass

from app.ai.rules import OCR_LOOKALIKES
from app.ai.schemas import PageTranscript

NUMBER_RE = re.compile(r"^\(?(\d{1,3})\s*[.,):_/%\-]*$")  # "7)", "4/.", "5%." ("/" misread)
LETTER_RE = re.compile(r"^\(?([A-Za-z])\)?[.,)]*$")
# Number and letter read as one token: "1.A", "1)b", "15.0" (a curly D read as zero).
COMBINED_RE = re.compile(r"^\(?(\d{1,3})[.,):_/%\-]+\(?([A-Za-z08])\)?[.,)]*$")
MIN_PAIRS_FOR_GRID = 3      # fewer number–letter pairs on a page: not an MCQ grid
MAX_GAP = 0.25              # letter must start within this share of page width after the number
ROW_TOLERANCE = 0.6         # vertical offset allowed, as a share of the taller word's height
LOW_CONFIDENCE = 0.8        # OCR confidence below this: take the letter but flag it
COLUMN_TOLERANCE = 0.06     # letters within this share of page width form one answer column
ROW_SNAP = 0.3              # an inferred row must fall this close to a whole question number


@dataclass
class _Word:
    text: str
    confidence: float
    x0: float
    x1: float
    cy: float
    h: float


@dataclass
class GridCell:
    label: str                  # question label, e.g. "2"
    page_no: int                # 1-based
    letter: str | None          # chosen option, or None if nothing was read beside the number
    confidence: float           # OCR confidence of the letter (0 when missing)
    how: str                    # "grid" | "look-alike:0" | "inferred" | "missing" | "reread"
    region: tuple[float, float, float, float]  # x0, y0, x1, y1 (0–1) to crop for a re-read
    y: float = 0.0              # row centre
    letter_x: float | None = None  # left edge of the letter (its answer column)

    @property
    def needs_check(self) -> bool:
        return self.how != "grid" or self.confidence < LOW_CONFIDENCE


def _word(w: dict) -> _Word | None:
    box = w.get("box") or []
    if len(box) < 4:
        return None
    xs, ys = box[0::2], box[1::2]
    return _Word(w["text"].strip(), float(w.get("confidence", 1.0)), min(xs), max(xs),
                 sum(ys) / len(ys), max(ys) - min(ys))


def _same_row(a: _Word, b: _Word) -> bool:
    return abs(a.cy - b.cy) <= ROW_TOLERANCE * max(a.h, b.h, 0.005)


def _label(digits: str, labels: set[str]) -> str | None:
    """The question label a number token stands for. OCR often reads a closing bracket as "1",
    so "71" or "171" next to the grid is question 7 or 17 when 71/171 is not a question."""
    label = digits.lstrip("0") or "0"
    if label in labels:
        return label
    if len(label) > 1 and label.endswith("1") and label[:-1] in labels:
        return label[:-1]
    return None


def _letter(text: str, valid: set[str]) -> tuple[str, str] | None:
    """(letter, how) if the token is an option letter or a known OCR look-alike of one."""
    m = LETTER_RE.match(text)
    if m and m.group(1).upper() in valid:
        return m.group(1).upper(), "grid"
    lone = text.strip(" .,()").upper()
    if lone in OCR_LOOKALIKES and OCR_LOOKALIKES[lone] in valid:
        return OCR_LOOKALIKES[lone], f"look-alike:{lone}"
    return None


def _region(n: _Word) -> tuple[float, float, float, float]:
    """The number plus the space to its right, one row high: where the letter should be."""
    pad = max(n.h, 0.01) * 1.2
    return (max(n.x0 - 0.01, 0.0), max(n.cy - pad, 0.0), min(n.x1 + 0.15, 1.0), min(n.cy + pad, 1.0))


def read_page(words: list[dict], labels: set[str], valid: set[str], page_no: int) -> list[GridCell]:
    ws = [w for w in (_word(d) for d in words) if w and w.text]
    cells: list[GridCell] = []
    numbers: list[_Word] = []
    for w in ws:
        if (m := COMBINED_RE.match(w.text)) and (label := _label(m.group(1), labels)):
            hit = _letter(m.group(2), valid)
            if hit:
                cells.append(GridCell(label, page_no, hit[0], w.confidence, hit[1], _region(w),
                                      y=w.cy, letter_x=w.x0))
                continue
        if (m := NUMBER_RE.match(w.text)) and _label(m.group(1), labels):
            numbers.append(w)

    used: set[int] = set()
    for n in sorted(numbers, key=lambda w: (w.cy, w.x0)):
        label = _label(NUMBER_RE.match(n.text).group(1), labels)
        best = None
        for i, w in enumerate(ws):
            if i in used or w is n or not _same_row(n, w):
                continue
            gap = w.x0 - n.x1
            hit = _letter(w.text, valid)
            if hit and -0.01 <= gap <= MAX_GAP and (best is None or gap < best[0]):
                best = (gap, i, hit)
        if best is not None:
            _, i, (letter, how) = best
            used.add(i)
            cells.append(GridCell(label, page_no, letter, ws[i].confidence, how, _region(n),
                                  y=n.cy, letter_x=ws[i].x0))
            continue
        cells.append(GridCell(label, page_no, None, 0.0, "missing", _region(n), y=n.cy))
    return _infer_unnumbered_rows(ws, used, cells, labels, valid, page_no)


def _infer_unnumbered_rows(ws: list[_Word], used: set[int], cells: list[GridCell], labels: set[str],
                           valid: set[str], page_no: int) -> list[GridCell]:
    """A letter in the answer column whose question number OCR missed or mangled ("3.7", "20-")
    sits between two rows that were read. Questions run in order down a column, so its position
    tells which question it answers. Flagged for the teacher to confirm."""
    anchors = [c for c in cells if c.letter and c.letter_x is not None and c.label.isdigit()]
    taken = {c.label for c in cells if c.letter}
    for i, w in enumerate(ws):
        if i in used or not (hit := _letter(w.text, valid)):
            continue
        column = [c for c in anchors if abs(c.letter_x - w.x0) <= COLUMN_TOLERANCE]
        above = max((c for c in column if c.y < w.cy), key=lambda c: c.y, default=None)
        below = min((c for c in column if c.y > w.cy), key=lambda c: c.y, default=None)
        if above is None or below is None:
            continue
        first, last = int(above.label), int(below.label)
        if last - first < 2:
            continue
        estimate = first + (w.cy - above.y) / (below.y - above.y) * (last - first)
        label = str(round(estimate))
        if (abs(estimate - round(estimate)) > ROW_SNAP or not first < int(label) < last
                or label not in labels or label in taken):
            continue
        taken.add(label)
        pad = max(w.h, 0.01) * 1.2
        region = (max(w.x0 - 0.12, 0.0), max(w.cy - pad, 0.0), min(w.x1 + 0.03, 1.0), min(w.cy + pad, 1.0))
        cells = [c for c in cells if c.label != label]  # replaces a number read without a letter
        cells.append(GridCell(label, page_no, hit[0], w.confidence, "inferred", region,
                              y=w.cy, letter_x=w.x0))
    return cells


def read_mcq_grid(pages: list[PageTranscript], labels: set[str],
                  valid: set[str] | None = None) -> dict[str, GridCell]:
    """Question label → the cell read for it, from pages that look like an MCQ grid."""
    valid = valid or set("ABCDE")
    found: dict[str, GridCell] = {}
    for page_no, page in enumerate(pages, start=1):
        cells = read_page(page.words, labels, valid, page_no)
        if sum(1 for c in cells if c.letter) < MIN_PAIRS_FOR_GRID:
            continue
        for c in cells:
            prev = found.get(c.label)
            if prev is None or (prev.letter is None and c.letter is not None):
                found[c.label] = c
    return found
