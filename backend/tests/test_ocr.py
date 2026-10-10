import asyncio

import pymupdf

from app.ai.ocr_azure import MODEL_NAME, OcrLine, OcrPage, OcrWord, clean_lines
from app.ai.pipeline import legibility_from_confidence, transcribe_pages


def line(*words):
    return OcrLine([OcrWord(t, c, [0, 0, 1, 0, 1, 1, 0, 1]) for t, c in words])


def test_noise_lines_dropped_and_unsure_words_marked():
    page = clean_lines([
        line(("26.", 0.95), ("Distinguish", 0.99), ("structured", 0.97)),
        line(("C.P", 0.17)),                                   # margin mark
        line(("07", 0.39), ("biberg", 0.21), ("Jug", 0.26)),   # bleed-through
        line(("Z-score", 0.9), ("and", 0.98), ("IQR", 0.2)),   # one unreadable word
    ])
    assert page.text == "26. Distinguish structured\nZ-score and [illegible]"
    assert page.dropped_lines == 2
    assert len(page.words) == 6
    assert round(page.low_confidence_share, 3) == round(1 / 6, 3)


def test_empty_page():
    page = clean_lines([])
    assert page.text == "" and page.low_confidence_share == 0


def test_legibility_from_confidence():
    assert legibility_from_confidence(0.02) == "clear"
    assert legibility_from_confidence(0.2) == "partial"
    assert legibility_from_confidence(0.5) == "unreadable"


def _page_png() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "21. Supervised learning uses labelled data", fontsize=24)
    return doc[0].get_pixmap(dpi=100, colorspace=pymupdf.csGRAY).tobytes("png")


class FakeReader:
    def __init__(self, fail=False):
        self.fail = fail

    async def read_page(self, png):
        if self.fail:
            raise ConnectionError("Azure unreachable")
        return OcrPage(text="21. Supervised learning uses labelled data",
                       words=[OcrWord("21.", 0.99, [0.1, 0.1, 0.2, 0.1, 0.2, 0.15, 0.1, 0.15])],
                       low_confidence_share=0.0)


class FakeGrader:
    vision_model = "vision"

    def __init__(self, reader):
        self.reader = reader
        self.external, self.vision_calls = [], 0

    def record_external(self, step, model, cost_usd):
        self.external.append((step, model, cost_usd))

    async def text(self, **_):
        self.vision_calls += 1
        return "21. read by the vision model"


def test_azure_reader_used_and_costed():
    g = FakeGrader(FakeReader())
    (page,) = asyncio.run(transcribe_pages(g, [_page_png()]))
    assert page.text.startswith("21. Supervised")
    assert page.legibility == "clear" and page.question_markers == ["21"]
    assert page.words and g.vision_calls == 0
    assert g.external == [("read", MODEL_NAME, 0.0015)]


def test_falls_back_to_vision_model_when_azure_fails():
    g = FakeGrader(FakeReader(fail=True))
    (page,) = asyncio.run(transcribe_pages(g, [_page_png()]))
    assert page.text == "21. read by the vision model"
    assert g.vision_calls == 1
