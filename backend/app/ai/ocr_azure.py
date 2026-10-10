"""Page reading with Azure AI Document Intelligence (prebuilt "read" model).

Why: Azure reads a handwritten page in ~5 s (vs ~1 page/minute on Groq's free vision tier),
and returns a confidence score and position for every word. We use the confidences to
  - drop noise lines (margin marks, faint bleed-through from the back of the sheet), which
    always come back with very low confidence,
  - mark individual unreadable words as [illegible],
  - measure legibility from real numbers instead of guessing,
and keep the word positions so the review screen can highlight evidence on the page image.
"""
import io
from dataclasses import dataclass, field

from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential

MODEL_ID = "prebuilt-read"
MODEL_NAME = "azure/prebuilt-read"   # name used in cost tracking and caches
NOISE_LINE_CONFIDENCE = 0.5          # a line whose words average below this is noise
ILLEGIBLE_WORD_CONFIDENCE = 0.25     # a single word below this becomes [illegible]


@dataclass
class OcrWord:
    text: str
    confidence: float
    box: list[float]  # polygon x1,y1,x2,y2,… normalised to 0–1 of page width/height


@dataclass
class OcrLine:
    words: list[OcrWord]

    @property
    def mean_confidence(self) -> float:
        return sum(w.confidence for w in self.words) / len(self.words) if self.words else 0.0


@dataclass
class OcrPage:
    text: str
    words: list[OcrWord] = field(default_factory=list)  # kept words only
    dropped_lines: int = 0
    low_confidence_share: float = 0.0                   # kept words below 0.5


def clean_lines(lines: list[OcrLine]) -> OcrPage:
    """Turn raw OCR lines into a clean transcription (pure function, unit-tested)."""
    kept_text, kept_words, dropped = [], [], 0
    for line in lines:
        if not line.words:
            continue
        if line.mean_confidence < NOISE_LINE_CONFIDENCE:
            dropped += 1
            continue
        tokens = [w.text if w.confidence >= ILLEGIBLE_WORD_CONFIDENCE else "[illegible]" for w in line.words]
        kept_text.append(" ".join(tokens))
        kept_words.extend(line.words)
    low = sum(1 for w in kept_words if w.confidence < 0.5)
    return OcrPage(
        text="\n".join(kept_text),
        words=kept_words,
        dropped_lines=dropped,
        low_confidence_share=low / len(kept_words) if kept_words else 0.0,
    )


def _lines_from_result(result) -> list[OcrLine]:
    """Group Azure's words into its lines using character spans."""
    if not result.pages:
        return []
    page = result.pages[0]
    width, height = float(page.width or 1), float(page.height or 1)
    words = sorted(page.words or [], key=lambda w: w.span.offset)
    lines = []
    for line in page.lines or []:
        ranges = [(s.offset, s.offset + s.length) for s in line.spans]
        members = [w for w in words if any(a <= w.span.offset < b for a, b in ranges)]
        lines.append(OcrLine([
            OcrWord(
                text=w.content,
                confidence=float(w.confidence),
                box=[round(v / (width if i % 2 == 0 else height), 4) for i, v in enumerate(w.polygon or [])],
            )
            for w in members
        ]))
    return lines


class AzureReader:
    def __init__(self, endpoint: str, key: str):
        self.endpoint = endpoint
        self.key = key

    async def read_page(self, png: bytes) -> OcrPage:
        # azure-core retries 429/5xx/connection errors with backoff by default.
        async with DocumentIntelligenceClient(self.endpoint, AzureKeyCredential(self.key)) as client:
            poller = await client.begin_analyze_document(
                MODEL_ID, io.BytesIO(png), content_type="application/octet-stream")
            result = await poller.result()
        return clean_lines(_lines_from_result(result))
