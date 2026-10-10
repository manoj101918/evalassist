import pymupdf

MAX_IMAGE_BYTES = 4_000_000  # keep base64 page images well within Groq request limits


def page_count(pdf_bytes: bytes) -> int:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        return doc.page_count


def _render(page: pymupdf.Page, dpi: int) -> bytes:
    # Grayscale keeps scans of ink handwriting legible at a fraction of the size.
    return page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY).tobytes("png")


def render_pages(pdf_bytes: bytes, dpi: int = 150) -> list[bytes]:
    """Render every page to PNG, lowering the DPI for any page that would be too large."""
    images = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            d = dpi
            png = _render(page, d)
            while len(png) > MAX_IMAGE_BYTES and d > 72:
                d = int(d * 0.8)
                png = _render(page, d)
            images.append(png)
    return images


# Share of near-black pixels below which a page counts as blank. Real handwriting pages measure
# ≥0.2%; blank sheets showing only faint bleed-through from the reverse side measure ≤0.02%.
BLANK_INK_RATIO = 0.0005


def ink_ratio(png: bytes) -> float:
    """Fraction of dark (ink) pixels in a rendered grayscale page."""
    pix = pymupdf.Pixmap(png)
    if pix.n != 1:
        pix = pymupdf.Pixmap(pymupdf.csGRAY, pix)
    samples = pix.samples
    dark = sum(samples.count(bytes([v])) for v in range(100))
    return dark / len(samples) if samples else 0.0


def is_blank(png: bytes) -> bool:
    return ink_ratio(png) < BLANK_INK_RATIO
