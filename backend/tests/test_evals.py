import math

import pytest

from evals import dataset
from evals.metrics import agreement, colour_report, quadratic_weighted_kappa


def test_qwk_perfect_and_chance():
    assert quadratic_weighted_kappa([0, 1, 2, 2], [0, 1, 2, 2]) == 1.0
    assert quadratic_weighted_kappa([2, 2, 2], [2, 2, 2]) == 1.0
    # Systematic disagreement is worse than chance.
    assert quadratic_weighted_kappa([0, 2, 0, 2], [2, 0, 2, 0]) < 0
    assert math.isnan(quadratic_weighted_kappa([], []))


def test_qwk_penalises_big_gaps_more():
    small = quadratic_weighted_kappa([0, 1, 2, 1, 0, 2], [0, 1.5, 2, 1, 0.5, 2])
    large = quadratic_weighted_kappa([0, 1, 2, 1, 0, 2], [2, 1, 0, 1, 2, 0])
    assert small > large


def test_agreement_numbers():
    a = agreement([2, 1, 0, 1.5], [2, 2, 0, 1])
    assert a["n"] == 4 and a["mae"] == 0.375
    assert a["exact_pct"] == 50.0 and a["within_half_pct"] == 75.0


def test_colour_report():
    rows = [{"confidence": "green", "ai": 2, "teacher": 2},
            {"confidence": "green", "ai": 1, "teacher": 2},
            {"confidence": "red", "ai": 0, "teacher": 1}]
    r = colour_report(rows)
    assert r["green"] == {"share_pct": 66.7, "exact_pct": 50.0}
    assert r["yellow"]["exact_pct"] is None


needs_data = pytest.mark.skipif(not dataset.MARKS_CSV.exists(), reason="evaluation dataset not downloaded")


@needs_data
def test_dataset_questions_and_split():
    qs = dataset.build_questions()
    assert len(qs) == 35
    assert sum(q.max_marks for q in qs) == 50
    assert all(q.is_mcq for q in qs[:20]) and not any(q.is_mcq for q in qs[20:])
    parts = {name: set(dataset.split(name)) for name in ("train", "val", "test")}
    assert parts["test"].isdisjoint(parts["train"]) and parts["val"].isdisjoint(parts["train"])
    assert sum(len(p) for p in parts.values()) == len(dataset.students())
