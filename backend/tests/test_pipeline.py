import asyncio
import re

import pymupdf

from app.ai.pipeline import clamp_grading, describe_page, grade_script, merge_segments, normalise_label
from app.ai.schemas import Grading, PointGrade, QuestionSpec, RubricPointSpec, Segmentation, SegmentedAnswer

Q1 = QuestionSpec(id="q1", label="1", text="Define photosynthesis.", max_marks=4,
                  rubric=[RubricPointSpec("Uses light energy", 2), RubricPointSpec("Makes glucose", 2)])
Q2 = QuestionSpec(id="q2", label="2a", text="Name the organelle.", max_marks=2,
                  rubric=[RubricPointSpec("Chloroplast", 2)])
Q3 = QuestionSpec(id="q3", label="3", text="Unattempted question.", max_marks=5,
                  rubric=[RubricPointSpec("Anything", 5)])


class FakeGrader:
    """Stands in for the Groq Grader: returns canned outputs per step."""

    vision_model, grading_model, check_model = "vision", "grading", "check"
    reader = None  # no OCR service: pages are read by the (fake) vision model

    def __init__(self, pages, segmentation, gradings):
        self.pages = pages  # transcription text per page
        self.segmentation = segmentation
        self.gradings = gradings  # {(question label, "grade"|"check"): Grading}
        self.calls = []

    async def parse(self, *, step, model, system, content, output, **_):
        self.calls.append(step)
        assert model == {"transcribe": "vision", "segment": "grading",
                         "grade": "grading", "check": "check"}[step]
        if step == "segment":
            return self.segmentation
        label = re.search(r"^Question (\S+) \(maximum", system, re.M).group(1)
        return self.gradings[(label, step)]


    async def text(self, *, step, model, system, content, **_):
        self.calls.append(step)
        assert (step, model) == ("transcribe", "vision")
        page_no = int(content[1]["text"].split()[3])
        return self.pages[page_no - 1]


def page_png(text: str | None) -> bytes:
    """A rendered page: handwriting-sized dark text, or blank when text is None."""
    doc = pymupdf.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 100), text, fontsize=28)
    return page.get_pixmap(dpi=100, colorspace=pymupdf.csGRAY).tobytes("png")


def grading(*points, summary="ok"):
    return Grading(points=[PointGrade(point_number=i, verdict=v, marks=m, evidence_quote=e, reason="r")
                           for i, (v, m, e) in enumerate(points, start=1)], summary_reason=summary)


def test_normalise_label():
    assert normalise_label("Q.2(a)") == "2a"
    assert normalise_label("Ans-3") == "3"
    assert normalise_label("Question 1") == "1"
    assert normalise_label("2a") == "2a"


def test_clamp_grading_bounds_marks_and_fills_missing_points():
    g = grading(("full", 5, "x"))  # over the 2-mark maximum; point 2 missing
    total, breakdown = clamp_grading(g, Q1)
    assert breakdown[0]["marks"] == 2
    assert breakdown[1]["verdict"] == "absent" and breakdown[1]["marks"] == 0
    assert total == 2


def test_clamp_grading_rounds_to_half_and_zeroes_absent():
    g = grading(("partial", 1.3, "x"), ("absent", 1, ""))
    total, breakdown = clamp_grading(g, Q1)
    assert breakdown[0]["marks"] == 1.5
    assert breakdown[1]["marks"] == 0
    assert total == 1.5


def test_merge_segments_joins_continued_answers_and_drops_unknown_labels():
    seg = Segmentation(answers=[
        SegmentedAnswer(question_label="Q1", pages=[1], text="part one", ambiguous=False, note=""),
        SegmentedAnswer(question_label="9", pages=[2], text="stray", ambiguous=False, note=""),
        SegmentedAnswer(question_label="1", pages=[3], text="part two", ambiguous=True, note="continued?"),
    ])
    merged = merge_segments(seg, [Q1, Q2])
    assert set(merged) == {"q1"}
    assert merged["q1"].pages == [1, 3]
    assert merged["q1"].text == "part one\npart two"
    assert merged["q1"].ambiguous


def test_grade_script_end_to_end():
    pages = [
        "Q1. Plants use light energy to make glucose.",
        "2(a) chloroplast in the [illegible] cell",
        "should never be requested",  # page 3 is blank
    ]
    segmentation = Segmentation(answers=[
        SegmentedAnswer(question_label="1", pages=[1], text="Plants use light energy to make glucose.",
                        ambiguous=False, note=""),
        SegmentedAnswer(question_label="2(a)", pages=[2], text="chloroplast", ambiguous=False, note=""),
    ])
    gradings = {
        ("1", "grade"): grading(("full", 2, "use light energy"), ("full", 2, "make glucose")),
        ("1", "check"): grading(("full", 2, "use light energy"), ("partial", 1.5, "make glucose")),
        ("2a", "grade"): grading(("full", 2, "chloroplast")),
        ("2a", "check"): grading(("full", 2, "chloroplast")),
    }
    fake = FakeGrader(pages, segmentation, gradings)
    images = [page_png("Q1 answer"), page_png("2(a) answer"), page_png(None)]
    result = asyncio.run(grade_script(fake, images, [Q1, Q2, Q3]))

    a1, a2, a3 = result.answers
    assert (a1.ai_marks, a1.check_marks, a1.confidence) == (4, 3.5, "green")
    assert a2.confidence == "yellow"  # partial legibility on page 2
    assert a2.page_numbers == [2]
    assert a3.ai_marks == 0 and a3.transcription == ""  # not attempted
    assert fake.calls.count("transcribe") == 2  # blank page 3 is skipped
    assert result.pages[2].text == "" and result.pages[2].legibility == "clear"
    assert fake.calls.count("segment") == 1
    assert fake.calls.count("grade") == 2 and fake.calls.count("check") == 2


def test_describe_page_legibility_markers_and_diagrams():
    clear = describe_page("21. Supervised learning uses labelled data.\nQ22) Overfitting.\n2(b) yes")
    assert clear.legibility == "clear"
    assert clear.question_markers == ["21", "22", "2(b)"]
    assert not clear.has_diagram_or_math

    partial = describe_page("25. Financial [illegible] and transport sector [diagram: bar chart]")
    assert partial.legibility == "partial"
    assert partial.has_diagram_or_math

    assert describe_page("[illegible] [illegible] [illegible] the").legibility == "unreadable"
    assert describe_page("").legibility == "clear"


def test_ungradeable_answer_is_red_not_fatal():
    from app.ai.client import AIError

    class FailingGrader(FakeGrader):
        async def parse(self, *, step, **kw):
            if step in ("grade", "check"):
                raise AIError(f"{step}: no valid reply after retrying")
            return await super().parse(step=step, **kw)

    segmentation = Segmentation(answers=[
        SegmentedAnswer(question_label="1", pages=[1], text="some answer", ambiguous=False, note=""),
    ])
    fake = FailingGrader(["Q1. some answer"], segmentation, {})
    result = asyncio.run(grade_script(fake, [page_png("Q1 answer")], [Q1]))
    (a1,) = result.answers
    assert a1.confidence == "red"
    assert a1.transcription == "some answer"
    assert "grade manually" in a1.confidence_reasons[0]
