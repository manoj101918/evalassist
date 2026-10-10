from app.ai.evidence import missing_evidence, quote_found

ANSWER = """Photosynthesis is the process by which green plants make food using sunlight.
It happens in the chloroplast, which contains chlorophyl. CO2 + water -> glucose + oxygen."""


def test_exact_quote_found():
    assert quote_found("happens in the chloroplast", ANSWER)


def test_quote_found_ignoring_case_and_punctuation():
    assert quote_found("IT HAPPENS IN THE CHLOROPLAST,", ANSWER)


def test_quote_with_small_transcription_differences_found():
    assert quote_found("which contains chlorophyll", ANSWER)


def test_invented_quote_not_found():
    assert not quote_found("the Calvin cycle fixes carbon in the stroma", ANSWER)


def test_empty_quote_counts_as_found():
    assert quote_found("", ANSWER)


def test_missing_evidence_only_checks_awarded_points():
    points = [
        {"point_number": 1, "marks": 2, "evidence_quote": "make food using sunlight"},
        {"point_number": 2, "marks": 1, "evidence_quote": "light reactions in thylakoid membranes"},
        {"point_number": 3, "marks": 0, "evidence_quote": "something invented"},
    ]
    assert missing_evidence(points, ANSWER) == [2]
