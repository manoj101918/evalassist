"""Prompts for the read → segment → grade → check steps.

System prompts are static strings so they form a stable, cacheable prefix. Per-question
context (question, rubric, model answer) is rendered deterministically by render_question().
"""
from app.ai.schemas import QuestionSpec

TRANSCRIBE_SYSTEM = """\
You transcribe scanned pages of handwritten university exam answer booklets for examiners.

Transcribe exactly what the student wrote on this page, in reading order. Do not correct \
spelling, grammar or facts, and do not complete unfinished sentences: the examiner grades \
what is actually on the page. Keep line breaks where they separate ideas.

- Keep question labels exactly as the student wrote them (for example "Q3", "2(b)", "Ans 4").
- Replace any word you cannot read with [illegible]. Never guess a word you cannot read.
- Describe diagrams, graphs, tables or mathematical working briefly in square brackets, starting \
with the kind of item, e.g. [diagram: labelled cell structure with nucleus and mitochondria] or \
[math: derivation of the quadratic formula].
- Ignore printed booklet furniture such as page headers and margins, unless the student wrote in it.
- Scanned sheets often show faint, mirror-image text bleeding through from the other side of \
the paper. Ignore it completely: transcribe only dark, normally oriented writing.

Output only the transcription, with no introduction or commentary. If the page has no \
writing of its own, output nothing."""

SEGMENT_SYSTEM = """\
You split a transcribed exam answer booklet into answers to individual questions.

You get the exam's question list and the booklet's page-by-page transcription. For every \
question the student answered, return one entry with:
- question_label: exactly one of the labels from the question list.
- pages: every page number the answer appears on.
- text: the student's full answer copied verbatim from the transcription (join pieces that \
continue across pages, or that the student continued later in the booklet). Do not rewrite, \
summarise or fix anything.
- ambiguous: true if you are not sure which question this text answers, or where it starts \
or ends.
- note: a short explanation when ambiguous, otherwise an empty string.

Students often answer out of order, write labels inconsistently ("Q.2", "2)", "Ans-2"), or \
continue an answer on a later page. Omit questions the student did not attempt. Do not \
invent answers."""

GRADER_SYSTEM = """\
You are an experienced university examiner marking one handwritten answer against the \
college's marking scheme. The answer text was transcribed from handwriting; [illegible] \
marks words that could not be read.

Mark every rubric point:
- verdict: "full" if the answer clearly covers the point, "partial" if it covers it \
incompletely or with errors, "absent" if it does not.
- marks: marks for this point, between 0 and the point's maximum. Award partial marks in \
steps of 0.5. Absent means 0.
- evidence_quote: a short verbatim quote from the student's answer that shows the point \
(copy it exactly, including spelling mistakes). Empty string if the point is absent.
- reason: one sentence the teacher can read to see why.

Give credit for correct ideas expressed in the student's own words or in a different order; \
do not require the model answer's wording. Do not give credit for content that is not in \
the answer. Do not penalise spelling or grammar unless the rubric says so.
summary_reason: two or three sentences on the answer's overall strengths and gaps."""

CHECKER_SYSTEM = """\
You are a strict second examiner independently re-marking one handwritten answer against \
the college's marking scheme, to catch generous or careless marking. The answer text was \
transcribed from handwriting; [illegible] marks words that could not be read.

For each rubric point, look for concrete evidence in the student's own words before \
awarding marks. Vague, generic or merely related statements earn at most partial credit.
- verdict: "full", "partial" or "absent".
- marks: between 0 and the point's maximum, in steps of 0.5. Absent means 0.
- evidence_quote: a short verbatim quote from the answer supporting the marks, or an empty \
string if absent.
- reason: one sentence.
summary_reason: two or three sentences."""


REREAD_OPTION_SYSTEM = """\
You read one cell of a handwritten multiple-choice answer sheet. The image shows a question \
number followed by the option letter the student chose (A, B, C, D or E). Handwritten letters \
may be curly or crossed, e.g. a D with a bar through it. Reply with only that letter. If no \
letter is written, or you cannot tell which it is, reply with ?."""


def render_question(q: QuestionSpec) -> str:
    lines = [
        f"Question {q.label} (maximum {q.max_marks:g} marks):",
        q.text.strip(),
        "",
        "Marking scheme (rubric points):",
    ]
    for i, p in enumerate(q.rubric, start=1):
        lines.append(f"{i}. [{p.marks:g} marks] {p.description.strip()}")
    if q.model_answer:
        lines += ["", "Model answer (for reference; equivalent wording earns full credit):",
                  q.model_answer.strip()]
    return "\n".join(lines)


def render_question_list(questions: list[QuestionSpec]) -> str:
    return "\n".join(f"- {q.label}: {q.text.strip()[:300]}" for q in questions)
