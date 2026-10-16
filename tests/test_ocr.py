"""OCR tests.

Tesseract is a system binary, so the searchable-layer logic is verified two
ways: directly, through the invisible-text writer, and end to end through the
pipeline with a stubbed OCR text page. The real Tesseract path is exercised
only when the binary is present on the machine.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from core import ocr, ops

TMP = Path(__file__).parent / "tmp"


def _pdf(name: str, text: str | None = "digital text") -> str:
    TMP.mkdir(exist_ok=True)
    path = TMP / name
    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_text(fitz.Point(72, 72), text)
    doc.save(str(path))
    doc.close()
    return str(path)


class _StubTextPage:
    """Mimics the two TextPage methods the OCR module relies on."""

    def __init__(self, words: list[tuple], text: str) -> None:
        self._words, self._text = words, text

    def extractWORDS(self) -> list[tuple]:
        return self._words

    def extractText(self) -> str:
        return self._text


def test_tesseract_availability_is_a_bool():
    assert isinstance(ocr.tesseract_available(), bool)


def test_invisible_layer_makes_a_page_searchable():
    doc = fitz.open()
    page = doc.new_page()
    words = [
        (72, 120, 200, 136, "Searchable", 0, 0, 0),
        (72, 150, 240, 166, "invoice", 0, 1, 0),
    ]
    assert ocr._invisible_text(page, words) == 2

    text = page.get_text("text")
    assert "Searchable" in text and "invoice" in text
    assert len(page.search_for("Searchable")) == 1
    stamp = doc[0].get_text("text")
    assert stamp.strip() != ""  # nothing rendered, but the layer is there
    doc.close()


def test_invisible_layer_skips_unusable_entries():
    doc = fitz.open()
    page = doc.new_page()
    assert ocr._invisible_text(page, [(1, 2, 3), (10, 10, 30, 20, "   "), "junk"]) == 0
    doc.close()


def test_ocr_pdf_writes_a_searchable_copy(monkeypatch):
    src = _pdf("scan.pdf", text=None)  # a "scanned" page: no text layer
    words = [(72, 300, 260, 318, "INVOICE", 0, 0, 0), (72, 330, 300, 348, "TOTAL", 0, 1, 0)]
    monkeypatch.setattr(
        ocr, "_textpage_ocr", lambda page, language, dpi: _StubTextPage(words, "INVOICE TOTAL")
    )

    out = str(TMP / "scan-ocr.pdf")
    result = ocr.ocr_pdf(src, out, dpi=150)
    assert result["pages_processed"] == 1
    assert result["pages_skipped"] == 0
    assert result["words"] == 2

    with fitz.open(out) as doc:
        text = doc[0].get_text("text")
    assert "INVOICE" in text and "TOTAL" in text
    assert ops.info(out)["pages"] == 1


def test_ocr_pdf_leaves_pages_that_already_have_text(monkeypatch):
    src = _pdf("already.pdf")
    calls: list[int] = []

    def fake(page, language, dpi):
        calls.append(1)
        return _StubTextPage([], "")

    monkeypatch.setattr(ocr, "_textpage_ocr", fake)
    result = ocr.ocr_pdf(src, str(TMP / "already-ocr.pdf"))
    assert result["pages_skipped"] == 1
    assert result["pages_processed"] == 0
    assert calls == []  # the OCR engine was never invoked


def test_ocr_pdf_can_force_reprocessing(monkeypatch):
    src = _pdf("force.pdf")
    monkeypatch.setattr(ocr, "_textpage_ocr", lambda page, language, dpi: _StubTextPage([], ""))
    result = ocr.ocr_pdf(src, str(TMP / "force-ocr.pdf"), skip_pages_with_text=False)
    assert result["pages_processed"] == 1


def test_ocr_text_returns_recognised_text(monkeypatch):
    src = _pdf("text.pdf", text=None)
    monkeypatch.setattr(
        ocr, "_textpage_ocr", lambda page, language, dpi: _StubTextPage([], "recognised body")
    )
    assert ocr.ocr_text(src, dpi=150).strip() == "recognised body"


def test_ocr_missing_input_raises():
    with pytest.raises(FileNotFoundError):
        ocr.ocr_pdf(str(TMP / "nope.pdf"), str(TMP / "nope-ocr.pdf"))
    with pytest.raises(FileNotFoundError):
        ocr.ocr_text(str(TMP / "nope.pdf"))


@pytest.mark.skipif(ocr.tesseract_available(), reason="Tesseract is installed")
def test_missing_tesseract_gives_an_actionable_error():
    src = _pdf("needs-tesseract.pdf", text=None)
    with pytest.raises(RuntimeError, match="Tesseract is not installed"):
        ocr.ocr_pdf(src, str(TMP / "no-tess.pdf"))


def _scanned_pdf(name: str, words: str = "INVOICE") -> str:
    """A genuinely image-only PDF: the text is rendered to pixels, then the
    page is rebuilt from that image so no text layer exists."""
    TMP.mkdir(exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=595, height=400)
    page.insert_text(fitz.Point(60, 200), words, fontsize=64)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    doc.close()

    scanned = fitz.open()
    target = scanned.new_page(width=595, height=400)
    target.insert_image(target.rect, pixmap=pix)
    path = TMP / name
    scanned.save(str(path))
    scanned.close()
    return str(path)


@pytest.mark.skipif(not ocr.tesseract_available(), reason="Tesseract is required for real OCR")
def test_real_ocr_makes_a_scanned_page_searchable():
    src = _scanned_pdf("scanned-real.pdf")
    with fitz.open(src) as doc:
        assert doc[0].get_text("text").strip() == ""  # nothing to fall back on

    out = str(TMP / "scanned-real-ocr.pdf")
    result = ocr.ocr_pdf(src, out, dpi=200)
    assert result["pages_processed"] == 1
    assert result["words"] > 0

    with fitz.open(out) as doc:
        recognised = doc[0].get_text("text").upper()
    assert "INVOICE" in recognised, recognised


@pytest.mark.skipif(not ocr.tesseract_available(), reason="Tesseract is required for real OCR")
def test_real_ocr_text_returns_recognised_content():
    src = _scanned_pdf("scanned-text-real.pdf", words="RECEIPT")
    text = ocr.ocr_text(src, dpi=200)
    assert "RECEIPT" in text.upper(), text
