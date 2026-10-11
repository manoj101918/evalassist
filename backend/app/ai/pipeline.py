"""The grading agent: read → segment → grade → double-check → decide colour.

`grade_script` is pure (no database): it takes rendered page images and the exam's questions
and returns a ScriptResult. The worker persists it; scripts/run_pipeline.py prints it.
"""
import asyncio
import logging
import re
from dataclasses import asdict

from app.ai import prompts
from app.ai.client import AIError, Grader, QuotaExhausted, image_block, text_block
from app.ai.confidence import ConfidenceInput, decide, worst_legibility
from app.ai.evidence import missing_evidence
from app.ai.mcq_grid import GridCell, read_mcq_grid
from app.ai.ocr_azure import MODEL_NAME as AZURE_MODEL_NAME
from app.ai.rules import grade_mcq, parse_options
from app.ai.schemas import (
    AnswerResult,
    Grading,
    PageTranscript,
    QuestionSpec,
    ScriptResult,
    Segmentation,
    SegmentedAnswer,
)
from app.config import AZURE_READ_PRICE_PER_PAGE
from app.pdf import crop_png, is_blank

log = logging.getLogger(__name__)


def normalise_label(label: str) -> str:
    s = label.lower()
    s = re.sub(r"^\s*(question|ques|ans(wer)?|q)[\s.:\-)]*", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def round_half(x: float) -> float:
    return round(x * 2) / 2


def clamp_grading(grading: Grading, q: QuestionSpec) -> tuple[float, list[dict]]:
    """Force marks into the rubric's bounds and return (total, per-point breakdown)."""
    by_number = {p.point_number: p for p in grading.points}
    breakdown = []
    for i, rp in enumerate(q.rubric, start=1):
        g = by_number.get(i)
        if g is None:
            breakdown.append({"point_number": i, "description": rp.description, "max_marks": rp.marks,
                              "verdict": "absent", "marks": 0.0, "evidence_quote": "",
                              "reason": "Not assessed by the grader."})
            continue
        marks = 0.0 if g.verdict == "absent" else min(max(round_half(g.marks), 0.0), rp.marks)
        breakdown.append({"point_number": i, "description": rp.description, "max_marks": rp.marks,
                          "verdict": g.verdict, "marks": marks,
                          "evidence_quote": g.evidence_quote, "reason": g.reason})
    total = min(sum(b["marks"] for b in breakdown), q.max_marks)
    return total, breakdown


MARKER_RE = re.compile(r"^\s*(?:q(?:uestion)?|ans(?:wer)?)?[\s.\-]*(\d+(?:\s*\(?[a-z]\))?)\s*[.):\-\s]",
                       re.IGNORECASE | re.MULTILINE)
DIAGRAM_RE = re.compile(r"\[(?:diagram|figure|graph|chart|table|math|equation|formula|drawing)\b", re.IGNORECASE)
WORD_RE = re.compile(r"\[illegible\]|\S+")


def describe_page(text: str) -> PageTranscript:
    """Derive legibility, question markers and diagram flags from a plain transcription."""
    words = WORD_RE.findall(text)
    illegible = sum(1 for w in words if w.lower() == "[illegible]")
    share = illegible / len(words) if words else 0.0
    legibility = "clear" if illegible == 0 else "partial" if share <= 0.3 else "unreadable"
    return PageTranscript(
        text=text,
        legibility=legibility,
        question_markers=[m.group(1).replace(" ", "") for m in MARKER_RE.finditer(text)],
        has_diagram_or_math=bool(DIAGRAM_RE.search(text)),
    )


def legibility_from_confidence(low_confidence_share: float) -> str:
    """Azure gives a confidence per word; a few unsure words don't make a page hard to read."""
    if low_confidence_share < 0.10:
        return "clear"
    return "partial" if low_confidence_share < 0.35 else "unreadable"


async def read_with_azure(grader: Grader, png: bytes) -> PageTranscript:
    ocr = await grader.reader.read_page(png)
    grader.record_external("read", AZURE_MODEL_NAME, cost_usd=AZURE_READ_PRICE_PER_PAGE)
    page = describe_page(ocr.text)
    page.legibility = legibility_from_confidence(ocr.low_confidence_share)
    page.words = [asdict(w) for w in ocr.words]
    return page


async def transcribe_page(grader: Grader, png: bytes, page_no: int) -> PageTranscript:
    if is_blank(png):
        # Blank sheets (often just bleed-through from the reverse side) make the vision model
        # invent text, so they are never sent.
        return describe_page("")
    if grader.reader is not None:
        try:
            return await read_with_azure(grader, png)
        except QuotaExhausted:
            raise
        except Exception as exc:  # noqa: BLE001 - fall back to the vision model for this page
            log.warning("Azure read failed on page %d (%s); falling back to the vision model", page_no, exc)
    text = await grader.text(
        step="transcribe",
        model=grader.vision_model,
        system=prompts.TRANSCRIBE_SYSTEM,
        content=[image_block(png), text_block(f"This is page {page_no} of the booklet. Transcribe it.")],
        # No hidden reasoning, and a tight output budget: Groq's free tier allows the vision
        # model only ~1000 output tokens per minute. A handwritten page is well under that.
        effort="none",
        max_tokens=1000,
    )
    return describe_page(text)


async def segment(grader: Grader, pages: list[PageTranscript],
                  questions: list[QuestionSpec]) -> Segmentation:
    booklet = "\n\n".join(f"=== PAGE {i} ===\n{p.text}" for i, p in enumerate(pages, start=1))
    return await grader.parse(
        step="segment",
        model=grader.grading_model,
        system=prompts.SEGMENT_SYSTEM,
        content=(f"Questions in this exam:\n{prompts.render_question_list(questions)}\n\n"
                 f"Booklet transcription:\n{booklet}"),
        output=Segmentation,
        effort="medium",
        max_tokens=6000,
    )


async def grade_answer(grader: Grader, q: QuestionSpec, answer_text: str,
                       checker: bool) -> Grading:
    # Instructions + question/rubric are identical for every script answering this question,
    # so they form a stable prefix Groq's prompt caching can reuse; only the answer varies.
    instructions = prompts.CHECKER_SYSTEM if checker else prompts.GRADER_SYSTEM
    return await grader.parse(
        step="check" if checker else "grade",
        model=grader.check_model if checker else grader.grading_model,
        system=f"{instructions}\n\n{prompts.render_question(q)}",
        content=f"Student's answer:\n<answer>\n{answer_text}\n</answer>",
        output=Grading,
        # Medium keeps hidden reasoning within budget; high often ran past it on short answers.
        effort="medium",
        max_tokens=3000,
    )


def merge_segments(segmentation: Segmentation,
                   questions: list[QuestionSpec]) -> dict[str, SegmentedAnswer]:
    """Map segments onto question ids; merge duplicates (answer continued later)."""
    by_label = {normalise_label(q.label): q for q in questions}
    merged: dict[str, SegmentedAnswer] = {}
    for seg in segmentation.answers:
        q = by_label.get(normalise_label(seg.question_label))
        if q is None:
            continue
        if q.id in merged:
            prev = merged[q.id]
            merged[q.id] = SegmentedAnswer(
                question_label=prev.question_label,
                pages=sorted(set(prev.pages) | set(seg.pages)),
                text=f"{prev.text}\n{seg.text}",
                ambiguous=prev.ambiguous or seg.ambiguous,
                note="; ".join(n for n in (prev.note, seg.note) if n),
            )
        else:
            merged[q.id] = seg
    return merged


async def reread_mcq_cell(grader: Grader, png: bytes, cell: GridCell, valid: set[str]) -> None:
    """Read one MCQ cell OCR left empty by showing the vision model just that crop."""
    reply = await grader.text(
        step="reread",
        model=grader.vision_model,
        system=prompts.REREAD_OPTION_SYSTEM,
        content=[image_block(crop_png(png, cell.region)),
                 text_block(f"Question {cell.label}: which option letter is written here?")],
        effort="none",
        max_tokens=20,
    )
    m = re.search(r"\b([A-E])\b", reply.upper())
    if m and m.group(1) in valid:
        cell.letter, cell.how = m.group(1), "reread"


async def read_mcq_answers(grader: Grader, pages: list[PageTranscript], questions: list[QuestionSpec],
                           page_images: list[bytes] | None) -> dict[str, GridCell]:
    """MCQ answers from the word positions of grid-like pages; empty cells are re-read from the
    page image when images are available. Keyed by question label."""
    mcqs = [q for q in questions if q.is_mcq]
    if not mcqs:
        return {}
    valid = set().union(*(parse_options(q.text) for q in mcqs)) or set("ABCDE")
    cells = read_mcq_grid(pages, {normalise_label(q.label) for q in mcqs}, valid)
    missing = [c for c in cells.values() if c.letter is None]
    if page_images and missing:
        results = await asyncio.gather(
            *(reread_mcq_cell(grader, page_images[c.page_no - 1], c, valid) for c in missing),
            return_exceptions=True)
        for c, r in zip(missing, results, strict=True):
            # A re-read is a bonus: if it fails (even on a used-up quota) the cell stays empty
            # and the teacher sees it, rather than the whole booklet failing.
            if isinstance(r, Exception):
                log.warning("re-reading MCQ %s failed: %s", c.label, r)
    return cells


def grid_check_reason(cell: GridCell) -> str | None:
    if cell.how == "reread":
        return "The letter was re-read from the page image by the AI: please confirm it in the booklet."
    if cell.how == "inferred":
        return (f"The question number was not readable; its position on the page suggests "
                f"Q{cell.label}: please confirm in the booklet.")
    if cell.how.startswith("look-alike:"):
        return f"Read as '{cell.how.split(':', 1)[1]}', taken as {cell.letter}: please confirm in the booklet."
    if cell.needs_check:
        return f"The letter was read with low confidence ({cell.confidence:.2f}): please confirm."
    return None


async def evaluate_answer(grader: Grader, q: QuestionSpec, seg: SegmentedAnswer | None,
                          pages: list[PageTranscript], grid_cell: GridCell | None = None) -> AnswerResult:
    if seg is None or not seg.text.strip():
        legibility = worst_legibility([p.legibility for p in pages])
        colour, reasons = decide(ConfidenceInput(
            max_marks=q.max_marks, found=False, ambiguous=False, legibility=legibility,
            has_diagram_or_math=False, marks_a=0, marks_b=0, missing_evidence=0))
        return AnswerResult(question_id=q.id, page_numbers=[], transcription="", ai_marks=0,
                            ai_breakdown=[], ai_reason="No answer to this question was found.",
                            check_marks=0, check_breakdown=[], confidence=colour,
                            confidence_reasons=reasons)

    valid_pages = [p for p in seg.pages if 1 <= p <= len(pages)]
    answer_pages = [pages[p - 1] for p in valid_pages]

    if q.is_mcq:
        # Tier 1: exact rule, no AI call.
        rule = grade_mcq(q, seg.text, worst_legibility([p.legibility for p in answer_pages]))
        if grid_cell is not None and (reason := grid_check_reason(grid_cell)):
            rule.confidence_reasons.append(reason)
            if rule.confidence == "green":
                rule.confidence = "yellow"
        return AnswerResult(
            question_id=q.id, page_numbers=valid_pages, transcription=seg.text,
            ai_marks=rule.marks, ai_breakdown=rule.breakdown, ai_reason=rule.reason,
            check_marks=rule.marks, check_breakdown=rule.breakdown,
            confidence=rule.confidence, confidence_reasons=rule.confidence_reasons,
        )

    try:
        grading_a, grading_b = await asyncio.gather(
            grade_answer(grader, q, seg.text, checker=False),
            grade_answer(grader, q, seg.text, checker=True),
        )
    except QuotaExhausted:
        raise  # out of quota: stop the whole script so it can be retried later
    except AIError as exc:
        # One answer the AI can't grade shouldn't block the whole booklet: hand it to the teacher.
        return AnswerResult(question_id=q.id, page_numbers=valid_pages, transcription=seg.text,
                            ai_marks=0, ai_breakdown=[], ai_reason="The AI could not grade this answer.",
                            check_marks=0, check_breakdown=[], confidence="red",
                            confidence_reasons=[f"AI grading failed, please grade manually ({exc})."])
    marks_a, breakdown_a = clamp_grading(grading_a, q)
    marks_b, breakdown_b = clamp_grading(grading_b, q)

    colour, reasons = decide(ConfidenceInput(
        max_marks=q.max_marks,
        found=True,
        ambiguous=seg.ambiguous,
        legibility=worst_legibility([p.legibility for p in answer_pages]),
        has_diagram_or_math=any(p.has_diagram_or_math for p in answer_pages),
        marks_a=marks_a,
        marks_b=marks_b,
        missing_evidence=len(missing_evidence(breakdown_a, seg.text)),
    ))
    if seg.ambiguous and seg.note:
        reasons.append(f"Segmentation note: {seg.note}")

    return AnswerResult(
        question_id=q.id, page_numbers=valid_pages, transcription=seg.text,
        ai_marks=marks_a, ai_breakdown=breakdown_a, ai_reason=grading_a.summary_reason,
        check_marks=marks_b, check_breakdown=breakdown_b,
        confidence=colour, confidence_reasons=reasons,
    )


async def transcribe_pages(grader: Grader, page_images: list[bytes]) -> list[PageTranscript]:
    return list(await asyncio.gather(
        *(transcribe_page(grader, png, i) for i, png in enumerate(page_images, start=1))
    ))


async def grade_script(grader: Grader, page_images: list[bytes],
                       questions: list[QuestionSpec]) -> ScriptResult:
    pages = await transcribe_pages(grader, page_images)
    return await grade_pages(grader, pages, questions, page_images)


async def grade_pages(grader: Grader, pages: list[PageTranscript], questions: list[QuestionSpec],
                      page_images: list[bytes] | None = None) -> ScriptResult:
    """Everything after reading: split into answers, grade, decide colours. Evals call this
    directly with cached transcriptions, so re-running an evaluation costs no page reads.
    `page_images` (optional) lets empty MCQ cells be re-read from the page."""
    segmentation, grid = await asyncio.gather(
        segment(grader, pages, questions),
        read_mcq_answers(grader, pages, questions, page_images),
    )
    segments = merge_segments(segmentation, questions)
    cells: dict[str, GridCell] = {}
    for q in questions:
        cell = grid.get(normalise_label(q.label)) if q.is_mcq else None
        if cell is not None and cell.letter:
            # Position-based reading beats the text split for answers written as a grid.
            cells[q.id] = cell
            segments[q.id] = SegmentedAnswer(question_label=q.label, pages=[cell.page_no],
                                             text=cell.letter, ambiguous=False, note="")
    answers = await asyncio.gather(
        *(evaluate_answer(grader, q, segments.get(q.id), pages, cells.get(q.id)) for q in questions)
    )
    return ScriptResult(pages=pages, answers=list(answers))
