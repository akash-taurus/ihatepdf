"""Offline OCR via Tesseract, driven by PyMuPDF.

PyMuPDF talks to the Tesseract library directly, so there is no Python OCR
dependency and nothing leaves the machine. Tesseract itself must be installed
on the system (see the OCR section of the README); :func:`tesseract_available`
reports whether it is, and every function here raises an actionable error when
it is missing.
"""

from __future__ import annotations

from pathlib import Path

import fitz

from .ops import _ensure_parent
from .pagespec import parse_pagespec

#: Install hint shared by every "Tesseract is missing" error.
INSTALL_HINT = (
    "Tesseract is not installed (or TESSDATA_PREFIX is unset). Install it and retry: "
    "Windows 'winget install UB-Mannheim.TesseractOCR', "
    "macOS 'brew install tesseract', "
    "Debian/Ubuntu 'apt-get install tesseract-ocr'."
)

_AVAILABLE: bool | None = None


def tesseract_available(language: str = "eng") -> bool:
    """True if Tesseract can be reached through PyMuPDF. Result is cached."""
    global _AVAILABLE
    if _AVAILABLE is not None:
        return _AVAILABLE
    try:
        with fitz.open() as doc:
            page = doc.new_page()
            page.get_textpage_ocr(language=language, dpi=72, full=True)
        _AVAILABLE = True
    except Exception:
        _AVAILABLE = False
    return _AVAILABLE


def _textpage_ocr(page: fitz.Page, language: str, dpi: int):
    try:
        return page.get_textpage_ocr(language=language, dpi=dpi, full=True)
    except Exception as exc:  # pragma: no cover - depends on system install
        raise RuntimeError(f"{exc}. {INSTALL_HINT}") from exc


def _page_has_text(page: fitz.Page) -> bool:
    try:
        return bool(page.get_text("text").strip())
    except Exception:  # pragma: no cover - defensive
        return False


def _invisible_text(page: fitz.Page, words: list, min_fontsize: float = 4.0) -> int:
    """Paint recognised words as invisible text so the page becomes searchable.

    Returns the number of words written. Text is sized to each word's OCR box
    and shrunk until it fits, which is what makes copy/paste and search line up
    with what the reader sees.
    """
    written = 0
    for word in words:
        try:
            x0, y0, x1, y1, text = (
                float(word[0]),
                float(word[1]),
                float(word[2]),
                float(word[3]),
                word[4],
            )
        except (IndexError, TypeError, ValueError):  # pragma: no cover - defensive
            continue
        text = str(text).strip()
        if not text:
            continue
        box = fitz.Rect(x0, y0, x1, y1)
        if box.is_empty:
            continue
        fontsize = max(min_fontsize, (box.height - 1) * 0.85)
        while fontsize >= min_fontsize:
            rc = page.insert_textbox(
                box,
                text,
                fontsize=fontsize,
                render_mode=3,  # invisible: present for search/copy, not for eyes
                overlay=True,
            )
            if rc >= 0:
                written += 1
                break
            fontsize -= 0.5
    return written


def ocr_text(
    input_path: str,
    pages: str | None = None,
    language: str = "eng",
    dpi: int = 300,
) -> str:
    """Recognise text in a (scanned) PDF and return it as a string."""
    if not Path(input_path).exists():
        raise FileNotFoundError(input_path)
    chunks: list[str] = []
    with fitz.open(input_path) as doc:
        for pno in parse_pagespec(pages, doc.page_count):
            tp = _textpage_ocr(doc[pno], language, dpi)
            chunks.append(tp.extractText())
    return "\n".join(chunks)


def ocr_pdf(
    input_path: str,
    output_path: str,
    pages: str | None = None,
    language: str = "eng",
    dpi: int = 300,
    skip_pages_with_text: bool = True,
) -> dict:
    """Add a hidden, searchable text layer to a scanned PDF.

    Args:
        skip_pages_with_text: leave pages that already carry a text layer alone
            (mixed documents are common: a scanned cover followed by digital
            pages).

    Returns:
        ``{"output", "pages_processed", "pages_skipped", "words"}``.
    """
    if not Path(input_path).exists():
        raise FileNotFoundError(input_path)
    _ensure_parent(output_path)
    processed = skipped = words = 0
    with fitz.open(input_path) as doc:
        for pno in parse_pagespec(pages, doc.page_count):
            page = doc[pno]
            if skip_pages_with_text and _page_has_text(page):
                skipped += 1
                continue
            tp = _textpage_ocr(page, language, dpi)
            words += _invisible_text(page, tp.extractWORDS())
            processed += 1
        doc.save(output_path, garbage=4, deflate=True)
    return {
        "output": output_path,
        "pages_processed": processed,
        "pages_skipped": skipped,
        "words": words,
    }
