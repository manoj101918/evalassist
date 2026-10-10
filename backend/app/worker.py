"""Background worker: claims queued scripts one at a time and runs the grading agent.

Run with:  python -m app.worker
"""
import asyncio
import logging
import time
from dataclasses import asdict
from datetime import UTC, datetime

from app.ai.client import CallUsage, Grader, QuotaExhausted
from app.ai.pipeline import grade_script
from app.config import get_settings
from app.db import get_db, storage, with_retry
from app.pdf import render_pages
from app.questions_repo import load_questions

log = logging.getLogger("worker")


def claim_next_script() -> dict | None:
    rows = get_db().rpc("claim_next_script").execute().data
    return rows[0] if rows else None


def process_script(script: dict) -> None:
    db = get_db()
    settings = get_settings()
    script_id = script["id"]

    questions = with_retry(lambda: load_questions(script["exam_id"]))
    if not questions:
        raise RuntimeError("Exam has no questions.")

    pdf_bytes = with_retry(lambda: storage().download(script["pdf_path"]))
    images = render_pages(pdf_bytes, dpi=settings.render_dpi)
    base = script["pdf_path"].rsplit("/", 1)[0]
    image_paths = []
    for i, png in enumerate(images, start=1):
        path = f"{base}/page-{i}.png"
        with_retry(lambda path=path, png=png: storage().upload(path, png, {"content-type": "image/png", "upsert": "true"}))
        image_paths.append(path)

    # Usage is recorded in memory during the (long) AI run and saved at the end, so a network
    # blip on the cost log can't abort a booklet that has otherwise been graded.
    def progress(u: CallUsage) -> None:
        log.info("  %s: %s call %d (%s, %d in / %d out tokens)", script["roll_number"], u.step,
                 len(grader.tracker.calls), u.model, u.input_tokens + u.cache_read_tokens, u.output_tokens)

    grader = Grader(settings.groq_vision_model, settings.groq_grading_model, settings.groq_check_model,
                    settings.groq_api_key, settings.max_parallel_calls, progress,
                    reader=settings.make_reader())
    result = asyncio.run(grade_script(grader, images, questions))

    def save() -> None:
        # Replace any output of a previous (failed) attempt.
        db.table("answers").delete().eq("script_id", script_id).execute()
        db.table("script_pages").upsert([
            {"script_id": script_id, "page_no": i, "image_path": image_paths[i - 1],
             "transcription": p.text, "legibility": p.legibility,
             "has_diagram_or_math": p.has_diagram_or_math, "words": p.words,
             "reader": settings.page_reader_name()}
            for i, p in enumerate(result.pages, start=1)
        ], on_conflict="script_id,page_no").execute()
        db.table("answers").insert([
            {"script_id": script_id, "question_id": a.question_id, "page_numbers": a.page_numbers,
             "transcription": a.transcription, "ai_marks": a.ai_marks, "ai_breakdown": a.ai_breakdown,
             "ai_reason": a.ai_reason, "check_marks": a.check_marks,
             "check_breakdown": a.check_breakdown, "confidence": a.confidence,
             "confidence_reasons": a.confidence_reasons}
            for a in result.answers
        ]).execute()
        db.table("scripts").update({
            "status": "ready", "page_count": len(images), "error": None,
            "processed_at": datetime.now(UTC).isoformat(),
        }).eq("id", script_id).execute()

    with_retry(save)
    try:
        with_retry(lambda: db.table("ai_calls").insert(
            [{"script_id": script_id, **asdict(u)} for u in grader.tracker.calls]).execute())
    except Exception:  # noqa: BLE001 - cost tracking must never fail a graded script
        log.exception("could not save AI cost log for script %s", script_id)
    log.info("script %s ready: %d pages, %d answers, %d AI calls, $%.4f", script_id, len(images),
             len(result.answers), len(grader.tracker.calls), grader.tracker.total_cost)


def handle_failure(script: dict, exc: Exception) -> None:
    # Retrying straight away into a used-up Groq quota only burns attempts: stop and let the
    # coordinator press Retry once the limit resets.
    retry = script["attempts"] < get_settings().max_attempts and not isinstance(exc, QuotaExhausted)
    with_retry(lambda: get_db().table("scripts").update({
        "status": "queued" if retry else "failed",
        "error": str(exc)[:1000],
    }).eq("id", script["id"]).execute())
    log.exception("script %s failed (attempt %d, %s)", script["id"], script["attempts"],
                  "will retry" if retry else "giving up")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # One line per poll / per SDK retry drowns the log.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("groq").setLevel(logging.WARNING)
    s = get_settings()
    poll = s.worker_poll_seconds
    log.info("worker started; page reader=%s (fallback %s) grading=%s check=%s",
             s.page_reader_name(), s.groq_vision_model, s.groq_grading_model, s.groq_check_model)
    requeued = False
    while True:
        # Network blips (DNS failures, timeouts) must not kill the worker: log, wait, carry on.
        try:
            if not requeued:
                # A script left in 'processing' means a previous worker died mid-run; requeue it.
                get_db().table("scripts").update({"status": "queued"}).eq("status", "processing").execute()
                requeued = True
            script = claim_next_script()
        except Exception as exc:  # noqa: BLE001
            log.warning("could not reach the database (%s: %s); retrying in %ss",
                        type(exc).__name__, exc, poll * 5)
            time.sleep(poll * 5)
            continue
        if script is None:
            time.sleep(poll)
            continue
        log.info("processing script %s (roll %s)", script["id"], script["roll_number"])
        try:
            process_script(script)
        except Exception as exc:  # noqa: BLE001 - any failure marks the script for retry
            try:
                handle_failure(script, exc)
            except Exception:  # noqa: BLE001 - requeued on the next worker start
                log.exception("could not record failure for script %s", script["id"])


if __name__ == "__main__":
    main()
