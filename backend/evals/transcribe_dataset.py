"""Read every page of every dataset booklet once and cache the transcriptions.

Pages are read by the configured page reader: Azure Document Intelligence (~5 s/page, ~200
pages for the 50 booklets, within the free 500 pages/month) or, without Azure, Groq vision
(~1 page/minute on the free tier, so ≈3–4 hours). The cache is per reader, and every later
evaluation reuses it. Resumable: booklets already cached are skipped. Run from backend/:

    python -m evals.transcribe_dataset               # all students
    python -m evals.transcribe_dataset --split test  # only the test split
"""
import argparse
import asyncio
import json
import logging
import time
from dataclasses import asdict
from pathlib import Path

from app.ai.client import Grader, QuotaExhausted
from app.ai.pipeline import transcribe_pages
from app.config import get_settings
from app.pdf import render_pages
from evals.dataset import pdf_path, split

CACHE_DIR = Path(__file__).resolve().parent / "cache" / "transcripts"
log = logging.getLogger("transcribe")


def cache_path(student: str, model: str) -> Path:
    return CACHE_DIR / model.replace("/", "_") / f"{student}.json"


def load_cached(student: str, model: str) -> dict | None:
    p = cache_path(student, model)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


async def transcribe_student(student: str, settings) -> dict:
    grader = Grader(settings.groq_vision_model, settings.groq_grading_model, settings.groq_check_model,
                    settings.groq_api_key, settings.max_parallel_calls, reader=settings.make_reader())
    started = time.time()
    images = render_pages(pdf_path(student).read_bytes(), dpi=settings.render_dpi)
    pages = await grader.run(transcribe_pages(grader, images))
    return {
        "student": student,
        "model": settings.page_reader_name(),
        "pages": [p.model_dump() for p in pages],
        "calls": [asdict(c) for c in grader.tracker.calls],
        "seconds": round(time.time() - started, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="all", choices=["all", "train", "val", "test"])
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    for name in ("httpx", "groq", "azure"):
        logging.getLogger(name).setLevel(logging.WARNING)

    settings = get_settings()
    todo = [s for s in split(args.split)
            if pdf_path(s).exists() and not cache_path(s, settings.page_reader_name()).exists()]
    missing = [s for s in split(args.split) if not pdf_path(s).exists()]
    if missing:
        log.warning("%d PDFs not downloaded yet (run python -m evals.download_dataset)", len(missing))
    log.info("%d booklets to transcribe with %s", len(todo), settings.page_reader_name())

    for i, student in enumerate(todo, 1):
        try:
            result = asyncio.run(transcribe_student(student, settings))
        except QuotaExhausted as exc:
            log.error("stopping: %s", exc)
            break
        except Exception as exc:  # noqa: BLE001 - skip this one, it will be retried next run
            log.error("%s failed: %s", student, exc)
            continue
        out = cache_path(student, settings.page_reader_name())
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=1), encoding="utf-8")
        cost = sum(c["cost_usd"] for c in result["calls"])
        log.info("[%d/%d] %s: %d pages, %.0fs, $%.4f", i, len(todo), student,
                 len(result["pages"]), result["seconds"], cost)


if __name__ == "__main__":
    main()
