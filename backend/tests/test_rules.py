import pytest

from app.ai.rules import chosen_option, grade_mcq, parse_options
from app.ai.schemas import QuestionSpec, RubricPointSpec

Q = QuestionSpec(
    id="q5", label="5", max_marks=1, qtype="mcq", correct_option="B",
    text="Which of the following is an ensemble learning method based on decision trees?\n"
         "A. Support Vector Machine\nB. Random Forest\nC. K-Nearest Neighbors\nD. Logistic Regression",
    rubric=[RubricPointSpec("Chooses option B", 1)],
)
OPTIONS = parse_options(Q.text)


def test_parse_options():
    assert OPTIONS == {"A": "Support Vector Machine", "B": "Random Forest",
                       "C": "K-Nearest Neighbors", "D": "Logistic Regression"}


@pytest.mark.parametrize("answer, expected", [
    ("B", "B"), ("B.", "B"), ("(b)", "B"), ("b)", "B"), ("Ans: C", "C"), ("Answer - d", "D"),
    ("option A.", "A"), ("5. B", "B"), ("  D  ", "D"),
    ("Random forest", "B"),                     # written out, no letter
    ("A random forest of trees", "B"),          # article "A" is not option A
])
def test_chosen_option(answer, expected):
    assert chosen_option(answer, OPTIONS)[0] == expected


def test_several_options_is_ambiguous():
    assert chosen_option("B. or C.", OPTIONS) == (None, "several options")


def test_unreadable():
    assert chosen_option("[illegible]", OPTIONS) == (None, "unreadable")


def test_grade_correct_is_green_full_marks():
    g = grade_mcq(Q, "B", "clear")
    assert (g.chosen, g.marks, g.confidence) == ("B", 1, "green")
    assert g.breakdown[0]["verdict"] == "full"


def test_grade_wrong_is_green_zero():
    g = grade_mcq(Q, "D", "clear")
    assert (g.chosen, g.marks, g.confidence) == ("D", 0, "green")


def test_grade_from_text_or_partial_legibility_is_yellow():
    assert grade_mcq(Q, "Random Forest", "clear").confidence == "yellow"
    assert grade_mcq(Q, "B", "partial").confidence == "yellow"


def test_ocr_lookalike_digit_is_taken_but_flagged():
    assert chosen_option("0", OPTIONS) == ("D", "look-alike:0")
    assert chosen_option("8.", OPTIONS) == ("B", "look-alike:8")
    g = grade_mcq(Q, "8", "clear")
    assert (g.chosen, g.marks, g.confidence) == ("B", 1, "yellow")
    assert any("please confirm" in r for r in g.confidence_reasons)


def test_grade_unidentified_is_not_green():
    g = grade_mcq(Q, "trees", "clear")
    assert g.chosen is None and g.marks == 0 and g.confidence == "yellow"
