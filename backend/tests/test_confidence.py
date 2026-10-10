from app.ai.confidence import ConfidenceInput, decide, worst_legibility


def ci(**kw):
    base = dict(max_marks=10, found=True, ambiguous=False, legibility="clear",
                has_diagram_or_math=False, marks_a=6, marks_b=6, missing_evidence=0)
    return ConfidenceInput(**{**base, **kw})


def test_green_when_everything_agrees():
    colour, reasons = decide(ci())
    assert colour == "green"
    assert reasons


def test_small_disagreement_within_tolerance_is_green():
    assert decide(ci(marks_a=6, marks_b=5.5))[0] == "green"


def test_slight_disagreement_is_yellow():
    assert decide(ci(marks_a=6, marks_b=5))[0] == "yellow"


def test_large_disagreement_is_red():
    colour, reasons = decide(ci(marks_a=8, marks_b=5))  # gap 3 > 25% of 10
    assert colour == "red"
    assert any("disagree" in r for r in reasons)


def test_partial_legibility_is_yellow_unreadable_is_red():
    assert decide(ci(legibility="partial"))[0] == "yellow"
    assert decide(ci(legibility="unreadable"))[0] == "red"


def test_diagram_or_math_is_red():
    assert decide(ci(has_diagram_or_math=True))[0] == "red"


def test_ambiguous_segmentation_is_red():
    assert decide(ci(ambiguous=True))[0] == "red"


def test_missing_evidence_is_yellow():
    assert decide(ci(missing_evidence=1))[0] == "yellow"


def test_not_found_depends_on_legibility():
    assert decide(ci(found=False, marks_a=0, marks_b=0))[0] == "yellow"
    assert decide(ci(found=False, marks_a=0, marks_b=0, legibility="partial"))[0] == "red"


def test_red_reasons_include_yellow_reasons():
    colour, reasons = decide(ci(has_diagram_or_math=True, legibility="partial"))
    assert colour == "red"
    assert len(reasons) == 2


def test_worst_legibility():
    assert worst_legibility(["clear", "partial", "clear"]) == "partial"
    assert worst_legibility(["clear", "unreadable"]) == "unreadable"
    assert worst_legibility([]) == "clear"
