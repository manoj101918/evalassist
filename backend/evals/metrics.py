"""Agreement metrics between AI marks and teacher marks."""
from collections import Counter


def quadratic_weighted_kappa(a: list[float], b: list[float], step: float = 0.5) -> float:
    """Cohen's kappa with quadratic weights, the standard metric for automated scoring.
    1 = perfect agreement, 0 = chance level. Marks are bucketed in `step` increments."""
    if not a:
        return float("nan")
    ra = [round(x / step) for x in a]
    rb = [round(x / step) for x in b]
    lo, hi = min(ra + rb), max(ra + rb)
    n = hi - lo + 1
    if n == 1:
        return 1.0
    observed = [[0] * n for _ in range(n)]
    for x, y in zip(ra, rb, strict=True):
        observed[x - lo][y - lo] += 1
    hist_a, hist_b = Counter(ra), Counter(rb)
    total = len(ra)
    num = den = 0.0
    for i in range(n):
        for j in range(n):
            w = (i - j) ** 2 / (n - 1) ** 2
            expected = hist_a[i + lo] * hist_b[j + lo] / total
            num += w * observed[i][j]
            den += w * expected
    return 1.0 - num / den if den else 1.0


def agreement(ai: list[float], teacher: list[float]) -> dict:
    diffs = [abs(x - y) for x, y in zip(ai, teacher, strict=True)]
    n = len(diffs)
    return {
        "n": n,
        "qwk": round(quadratic_weighted_kappa(ai, teacher), 3) if n else None,
        "mae": round(sum(diffs) / n, 3) if n else None,
        "exact_pct": round(100 * sum(d == 0 for d in diffs) / n, 1) if n else None,
        "within_half_pct": round(100 * sum(d <= 0.5 for d in diffs) / n, 1) if n else None,
        "ai_mean": round(sum(ai) / n, 3) if n else None,
        "teacher_mean": round(sum(teacher) / n, 3) if n else None,
    }


def colour_report(rows: list[dict]) -> dict:
    """rows: [{"confidence": ..., "ai": float, "teacher": float}] → share per colour and how
    often each colour's AI mark equals the teacher's (green should be very high)."""
    out = {}
    total = len(rows) or 1
    for colour in ("green", "yellow", "red"):
        sel = [r for r in rows if r["confidence"] == colour]
        out[colour] = {
            "share_pct": round(100 * len(sel) / total, 1),
            "exact_pct": round(100 * sum(r["ai"] == r["teacher"] for r in sel) / len(sel), 1) if sel else None,
        }
    return out
