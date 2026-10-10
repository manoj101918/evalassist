"""Grade dataset booklets (from cached transcriptions) and compare with the teacher's marks.

    python -m evals.run_eval --split test --name baseline
    python -m evals.run_eval --split val --name router-v1 --limit 3

Writes evals/reports/<name>.md and .json. Per-booklet results are cached under
evals/cache/runs/<name>/, so an interrupted run resumes where it stopped.

Metrics
  short answers (Q21–35, 2 marks, teacher per-question marks):
    QWK (quadratic weighted kappa), MAE, exact / within-0.5 agreement, mean marks,
    and per colour: share of answers and how often the AI mark equals the teacher's.
    "Green exact %" is the key trust number: green answers should almost always be right.
  MCQs (Q1–20): how often the option the AI read equals the option the teacher recorded.
  operations: AI calls, tokens, cost and seconds per booklet (reading + grading).
"""
import argparse
import asyncio
import json
import logging
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.ai.client import Grader, QuotaExhausted
from app.ai.pipeline import grade_pages
from app.ai.rules import chosen_option, parse_options
from app.ai.schemas import PageTranscript
from app.config import get_settings
from evals.dataset import build_questions, load_truth, split
from evals.metrics import agreement, colour_report
from evals.transcribe_dataset import load_cached

EVALS_DIR = Path(__file__).resolve().parent
RUNS_DIR = EVALS_DIR / "cache" / "runs"
REPORTS_DIR = EVALS_DIR / "reports"
log = logging.getLogger("eval")


async def grade_student(student: str, cached: dict, questions, settings) -> dict:
    grader = Grader(settings.groq_vision_model, settings.groq_grading_model, settings.groq_check_model,
                    settings.groq_api_key, settings.max_parallel_calls)
    pages = [PageTranscript(**p) for p in cached["pages"]]
    started = time.time()
    result = await grade_pages(grader, pages, questions)
    return {
        "student": student,
        "answers": [asdict(a) for a in result.answers],
        "grading_calls": [asdict(c) for c in grader.tracker.calls],
        "reading_calls": cached["calls"],
        "grading_seconds": round(time.time() - started, 1),
        "reading_seconds": cached["seconds"],
    }


def summarise(results: list[dict], questions, truth) -> dict:
    by_label = {q.label: q for q in questions}
    short_ai, short_teacher, colour_rows, mcq_hits, mcq_total = [], [], [], 0, 0
    for r in results:
        t = truth[r["student"]]
        for a in r["answers"]:
            q = by_label[a["question_id"]]
            if q.qtype == "mcq":
                recorded = t.mcq_choice.get(q.label, "")
                if recorded:
                    mcq_total += 1
                    read, _ = chosen_option(a["transcription"], parse_options(q.text))
                    mcq_hits += int(read == recorded)
            else:
                teacher = t.short[q.label]
                short_ai.append(float(a["ai_marks"]))
                short_teacher.append(teacher)
                colour_rows.append({"confidence": a["confidence"], "ai": float(a["ai_marks"]), "teacher": teacher})

    def per_booklet(key_calls: str, key_secs: str | None = None):
        calls = [len(r[key_calls]) for r in results]
        cost = [sum(c["cost_usd"] for c in r[key_calls]) for r in results]
        tokens = [sum(c["input_tokens"] + c["cache_read_tokens"] + c["output_tokens"] for c in r[key_calls])
                  for r in results]
        n = len(results) or 1
        out = {"calls": round(sum(calls) / n, 1), "tokens": round(sum(tokens) / n),
               "cost_usd": round(sum(cost) / n, 5)}
        if key_secs:
            out["seconds"] = round(sum(r[key_secs] for r in results) / n, 1)
        return out

    return {
        "booklets": len(results),
        "short_answers": agreement(short_ai, short_teacher),
        "colours": colour_report(colour_rows),
        "mcq_option_read_pct": round(100 * mcq_hits / mcq_total, 1) if mcq_total else None,
        "per_booklet": {"reading": per_booklet("reading_calls", "reading_seconds"),
                        "grading": per_booklet("grading_calls", "grading_seconds")},
    }


def write_report(name: str, split_name: str, settings, summary: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    meta = {"name": name, "split": split_name, "date": datetime.now(UTC).isoformat(timespec="seconds"),
            "models": {"vision": settings.page_reader_name(), "grading": settings.groq_grading_model,
                       "check": settings.groq_check_model}}
    (REPORTS_DIR / f"{name}.json").write_text(json.dumps({**meta, **summary}, indent=2), encoding="utf-8")
    s, c, pb = summary["short_answers"], summary["colours"], summary["per_booklet"]
    md = [
        f"# Evaluation: {name}",
        "",
        f"- Split: **{split_name}** ({summary['booklets']} booklets) · {meta['date']}",
        f"- Models: vision `{meta['models']['vision']}`, grading `{meta['models']['grading']}`, "
        f"check `{meta['models']['check']}`",
        "",
        "## Short answers vs teacher (Q21–35)",
        "| Answers | QWK | MAE | Exact | Within 0.5 | AI mean | Teacher mean |",
        "|---|---|---|---|---|---|---|",
        f"| {s['n']} | {s['qwk']} | {s['mae']} | {s['exact_pct']}% | {s['within_half_pct']}% | "
        f"{s['ai_mean']} | {s['teacher_mean']} |",
        "",
        "## Confidence colours (short answers)",
        "| Colour | Share | AI = teacher |",
        "|---|---|---|",
        *[f"| {k} | {v['share_pct']}% | {v['exact_pct'] if v['exact_pct'] is not None else '–'}% |"
          for k, v in c.items()],
        "",
        f"## MCQs (Q1–20)\nAI read the same option as the teacher recorded: **{summary['mcq_option_read_pct']}%**",
        "",
        "## Cost and speed per booklet",
        "| Stage | AI calls | Tokens | Cost (USD) | Seconds |",
        "|---|---|---|---|---|",
        *[f"| {k} | {v['calls']} | {v['tokens']} | {v['cost_usd']} | {v.get('seconds', '–')} |"
          for k, v in pb.items()],
        "",
    ]
    path = REPORTS_DIR / f"{name}.md"
    path.write_text("\n".join(md), encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["all", "train", "val", "test"])
    ap.add_argument("--name", required=True, help="run name, e.g. baseline")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    for name in ("httpx", "groq"):
        logging.getLogger(name).setLevel(logging.WARNING)

    settings = get_settings()
    questions, truth = build_questions(), load_truth()
    run_dir = RUNS_DIR / args.name
    run_dir.mkdir(parents=True, exist_ok=True)

    students = split(args.split)[: args.limit]
    results = []
    for i, student in enumerate(students, 1):
        out = run_dir / f"{student}.json"
        if out.exists():
            results.append(json.loads(out.read_text(encoding="utf-8")))
            continue
        cached = load_cached(student, settings.page_reader_name())
        if cached is None:
            log.warning("%s has no cached transcription; run python -m evals.transcribe_dataset", student)
            continue
        try:
            r = asyncio.run(grade_student(student, cached, questions, settings))
        except QuotaExhausted as exc:
            log.error("stopping: %s", exc)
            break
        except Exception as exc:  # noqa: BLE001 - skip; re-running the command retries it
            log.error("%s failed: %s", student, exc)
            continue
        out.write_text(json.dumps(r, indent=1), encoding="utf-8")
        results.append(r)
        log.info("[%d/%d] %s graded (%d calls, %.0fs)", i, len(students), student,
                 len(r["grading_calls"]), r["grading_seconds"])

    if not results:
        log.error("nothing graded")
        return
    summary = summarise(results, questions, truth)
    path = write_report(args.name, args.split, settings, summary)
    log.info("report: %s", path)
    print(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
