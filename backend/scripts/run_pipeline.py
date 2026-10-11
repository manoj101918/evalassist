"""Run the grading agent on one scanned PDF without the database or web app.

Use this to measure accuracy and cost per script before a pilot:

    python scripts/run_pipeline.py booklet.pdf rubric.json [--teacher-marks marks.json] [--out result.json]

rubric.json:
    {"questions": [{"label": "1", "text": "...", "max_marks": 5, "model_answer": "...",
                    "rubric": [{"description": "...", "marks": 2}, ...]}, ...]}
marks.json (optional, the teacher's marks for comparison):
    {"1": 4, "2": 3.5, ...}
"""
import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.client import Grader  # noqa: E402
from app.ai.pipeline import grade_script  # noqa: E402
from app.ai.rubric_file import load_rubric  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.pdf import render_pages  # noqa: E402

COLOUR = {"green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m"}
RESET = "\033[0m"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("rubric", type=Path)
    ap.add_argument("--teacher-marks", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--vision-model", help="override GROQ_VISION_MODEL")
    ap.add_argument("--grading-model", help="override GROQ_GRADING_MODEL")
    ap.add_argument("--check-model", help="override GROQ_CHECK_MODEL")
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args()

    s = get_settings()
    vision = args.vision_model or s.groq_vision_model
    grading = args.grading_model or s.groq_grading_model
    check = args.check_model or s.groq_check_model
    reader = None if args.vision_model else s.make_reader()  # --vision-model forces the vision reader
    questions = load_rubric(args.rubric)
    images = render_pages(args.pdf.read_bytes(), dpi=args.dpi)
    print(f"{args.pdf.name}: {len(images)} pages, {len(questions)} questions; "
          f"reader {'Azure Document Intelligence' if reader else vision}, grading {grading}, check {check}")

    done = []

    def progress(u):
        done.append(u)
        print(f"  [{len(done):>3}] {u.step:<10} {u.model:<22} {u.input_tokens + u.cache_read_tokens:>6} in "
              f"{u.output_tokens:>5} out  ${u.cost_usd:.5f}", flush=True)

    grader = Grader(vision, grading, check, s.groq_api_key, s.max_parallel_calls, progress, reader=reader)
    result = asyncio.run(grader.run(grade_script(grader, images, questions)))

    print("\nPages:")
    for i, p in enumerate(result.pages, start=1):
        flag = " [diagram/maths]" if p.has_diagram_or_math else ""
        print(f"  {i:>2}: {p.legibility:<10} markers={p.question_markers}{flag}")

    teacher = json.loads(args.teacher_marks.read_text()) if args.teacher_marks else {}
    diffs = []
    print("\nAnswers:")
    for q, a in zip(questions, result.answers, strict=True):
        c = COLOUR[a.confidence]
        line = (f"  Q{q.label:<5} AI {a.ai_marks:>4g}/{q.max_marks:g}  check {a.check_marks:>4g}  "
                f"{c}{a.confidence:<6}{RESET} pages={a.page_numbers}")
        if q.label in teacher:
            t = float(teacher[q.label])
            diffs.append(abs(t - a.ai_marks))
            line += f"  teacher {t:g}  diff {a.ai_marks - t:+g}"
        print(line)
        for r in a.confidence_reasons:
            print(f"         - {r}")

    total_ai = sum(a.ai_marks for a in result.answers)
    print(f"\nTotal AI marks: {total_ai:g}/{sum(q.max_marks for q in questions):g}")
    if diffs:
        print(f"Vs teacher: exact {sum(d == 0 for d in diffs)}/{len(diffs)}, "
              f"within 0.5: {sum(d <= 0.5 for d in diffs)}/{len(diffs)}, "
              f"mean abs diff {sum(diffs) / len(diffs):.2f}")

    by_step: dict[str, float] = {}
    for c in grader.tracker.calls:
        by_step[c.step] = by_step.get(c.step, 0) + c.cost_usd
    print(f"\nAI cost for this script: ${grader.tracker.total_cost:.4f} "
          f"({', '.join(f'{k} ${v:.4f}' for k, v in by_step.items())}); "
          f"{len(grader.tracker.calls)} calls")

    if args.out:
        args.out.write_text(json.dumps({
            "pages": [p.model_dump() for p in result.pages],
            "answers": [asdict(a) for a in result.answers],
            "calls": [asdict(c) for c in grader.tracker.calls],
        }, indent=2), encoding="utf-8")
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
