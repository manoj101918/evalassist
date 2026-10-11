import asyncio

import pymupdf

from app.ai.mcq_grid import read_mcq_grid
from app.ai.pipeline import grade_pages
from app.ai.schemas import PageTranscript, QuestionSpec, RubricPointSpec, Segmentation

LABELS = {str(i) for i in range(1, 21)}


def word(text, x, y, conf=0.99, w=0.03, h=0.015):
    """An OCR word whose box starts at x and is centred on row y (page shares)."""
    return {"text": text, "confidence": conf,
            "box": [x, y - h / 2, x + w, y - h / 2, x + w, y + h / 2, x, y + h / 2]}


def page(words, text=""):
    return PageTranscript(text=text, legibility="clear", question_markers=[], has_diagram_or_math=False,
                          words=words)


def grid(rows, x_num=0.03, x_letter=0.08):
    """Numbers first, then letters: the column-by-column order OCR returns for a grid."""
    nums = [word(n, x_num, 0.1 + 0.04 * i) for i, (n, _) in enumerate(rows)]
    letters = [word(t, x_letter, 0.1 + 0.04 * i) for i, (_, t) in enumerate(rows) if t]
    return nums + letters


def test_grid_read_in_column_order_is_paired_by_row():
    cells = read_mcq_grid([page(grid([("1,", "A"), ("2,", "D"), ("3.", "C"), ("4)", "B")]))], LABELS)
    assert {k: c.letter for k, c in cells.items()} == {"1": "A", "2": "D", "3": "C", "4": "B"}
    assert not any(c.needs_check for c in cells.values())


def test_letter_followed_by_option_text_is_accepted():
    words = grid([("1.", "D."), ("2,", "B,"), ("3.", "A,")]) + [
        word("All", 0.12, 0.1), word("of", 0.16, 0.1), word("the", 0.19, 0.1)]
    cells = read_mcq_grid([page(words)], LABELS)
    assert [cells[k].letter for k in ("1", "2", "3")] == ["D", "B", "A"]


def test_ocr_misreads_are_handled_and_flagged():
    words = [
        word("1.A", 0.03, 0.10, w=0.05),     # number and letter in one token
        word("15.0", 0.03, 0.14, w=0.05),    # curly D read as zero, in one token
        word("71", 0.03, 0.18), word("C", 0.08, 0.18),   # "7)" with the bracket read as 1
        word("4/.", 0.03, 0.22), word("0", 0.08, 0.22),  # "/" separator; D read as 0
    ]
    cells = read_mcq_grid([page(words)], LABELS)
    assert {k: c.letter for k, c in cells.items()} == {"1": "A", "15": "D", "7": "C", "4": "D"}
    assert not cells["1"].needs_check and not cells["7"].needs_check
    assert cells["15"].how == "look-alike:0" and cells["15"].needs_check
    assert cells["4"].needs_check


def test_low_confidence_letter_needs_check():
    words = grid([("1.", "A"), ("2.", "B"), ("3.", "C")])
    words[-1]["confidence"] = 0.5
    cells = read_mcq_grid([page(words)], LABELS)
    assert cells["3"].letter == "C" and cells["3"].needs_check


def test_number_without_letter_becomes_a_cell_to_reread():
    cells = read_mcq_grid([page(grid([("1.", "A"), ("2,", None), ("3.", "C"), ("4.", "B")]))], LABELS)
    assert cells["2"].letter is None and cells["2"].how == "missing"
    x0, y0, x1, y1 = cells["2"].region
    assert x0 <= 0.03 and x1 > 0.08 and y0 < 0.14 < y1   # covers the number and the space after it


def test_unreadable_number_is_inferred_from_row_order_and_flagged():
    # Q2's number was mangled by OCR ("2.7"); its letter sits between the rows of Q1 and Q3.
    words = grid([("1.", "A"), ("2.7", "B"), ("3.", "C"), ("4.", "D")])
    cells = read_mcq_grid([page(words)], LABELS)
    assert cells["2"].letter == "B" and cells["2"].how == "inferred" and cells["2"].needs_check
    # A letter below the last row (e.g. part of the next answer) is not given a question.
    words = grid([("1.", "A"), ("2.", "B"), ("3.", "C")]) + [word("A", 0.08, 0.3)]
    assert set(read_mcq_grid([page(words)], LABELS)) == {"1", "2", "3"}


def test_list_in_a_written_answer_is_not_an_mcq_grid():
    words = [word("1.", 0.03, 0.1), word("A", 0.08, 0.1), word("random", 0.12, 0.1),
             word("forest", 0.2, 0.1), word("2.", 0.03, 0.14), word("Boosting", 0.08, 0.14)]
    assert read_mcq_grid([page(words)], LABELS) == {}


def mcq(label, correct):
    return QuestionSpec(id=f"q{label}", label=label, max_marks=1, qtype="mcq", correct_option=correct,
                        text="Pick one.\nA. one\nB. two\nC. three\nD. four",
                        rubric=[RubricPointSpec(f"Chooses the correct option: {correct}", 1)])


class FakeGrader:
    vision_model, grading_model, check_model = "vision", "grading", "check"
    reader = None

    def __init__(self):
        self.calls = []

    async def parse(self, *, step, output, **_):
        self.calls.append(step)
        assert step == "segment"
        return Segmentation(answers=[])  # the text split finds nothing on a grid page

    async def text(self, *, step, model, content, **_):
        self.calls.append(step)
        assert (step, model) == ("reread", "vision")
        assert content[0]["type"] == "image_url"
        return "D"


def blank_png():
    with pymupdf.open() as doc:
        return doc.new_page().get_pixmap(dpi=50, colorspace=pymupdf.csGRAY).tobytes("png")


def test_pipeline_grades_mcqs_from_the_grid_and_rereads_empty_cells():
    pages = [page(grid([("1.", "A"), ("2,", None), ("3.", "C"), ("4.", "0")]))]
    questions = [mcq("1", "A"), mcq("2", "D"), mcq("3", "B"), mcq("4", "D")]
    fake = FakeGrader()
    result = asyncio.run(grade_pages(fake, pages, questions, [blank_png()]))
    a1, a2, a3, a4 = result.answers
    assert (a1.transcription, a1.ai_marks, a1.confidence) == ("A", 1, "green")
    assert (a2.transcription, a2.ai_marks, a2.confidence) == ("D", 1, "yellow")   # re-read
    assert "re-read" in " ".join(a2.confidence_reasons)
    assert (a3.ai_marks, a3.confidence) == (0, "green")                            # wrong option
    assert (a4.transcription, a4.ai_marks, a4.confidence) == ("D", 1, "yellow")   # look-alike
    assert fake.calls.count("reread") == 1


def test_failed_reread_leaves_the_cell_for_the_teacher_instead_of_failing_the_booklet():
    from app.ai.client import QuotaExhausted

    class QuotaGrader(FakeGrader):
        async def text(self, **_):
            raise QuotaExhausted("Groq usage limit reached for vision")

    pages = [page(grid([("1.", "A"), ("2,", None), ("3.", "C"), ("4.", "B")]))]
    questions = [mcq("1", "A"), mcq("2", "D"), mcq("3", "C"), mcq("4", "B")]
    result = asyncio.run(grade_pages(QuotaGrader(), pages, questions, [blank_png()]))
    assert [a.ai_marks for a in result.answers] == [1, 0, 1, 1]
    assert result.answers[1].confidence == "yellow"


def test_without_page_images_empty_cells_are_left_to_the_text_split():
    pages = [page(grid([("1.", "A"), ("2,", None), ("3.", "C"), ("4.", "B")]))]
    questions = [mcq("1", "A"), mcq("2", "D"), mcq("3", "C"), mcq("4", "B")]
    result = asyncio.run(grade_pages(FakeGrader(), pages, questions))
    assert result.answers[0].ai_marks == 1
    assert result.answers[1].transcription == "" and result.answers[1].confidence == "yellow"
