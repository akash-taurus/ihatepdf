"""Conversion tests. The built-in DOCX writer is verified without LibreOffice."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

import fitz
import pytest

from core import convert

TMP = Path(__file__).parent / "tmp"


def _text_pdf(name: str = "convert.pdf", pages: int = 2) -> str:
    TMP.mkdir(exist_ok=True)
    path = TMP / name
    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text(fitz.Point(72, 72), f"Hello ihatepdf page {i + 1}")
    doc.save(str(path))
    doc.close()
    return str(path)


def test_builtin_docx_is_a_valid_package_with_our_text():
    src = _text_pdf()
    out = str(TMP / "builtin.docx")
    result = convert.pdf_to_docx(src, out, engine="builtin")
    assert result["engine"] == "builtin"
    assert result["pages"] == 2

    with ZipFile(out) as zf:
        names = set(zf.namelist())
        assert {"[Content_Types].xml", "_rels/.rels", "word/document.xml"} <= names
        for name in names:
            if name.endswith(".xml") or name.endswith(".rels"):
                ET.fromstring(zf.read(name))  # every part must be well-formed
        document = zf.read("word/document.xml").decode("utf-8")
    assert "Hello ihatepdf page 1" in document
    assert "Hello ihatepdf page 2" in document
    assert document.count('<w:br w:type="page"/>') == 1  # one break between 2 pages


def test_builtin_docx_escapes_markup():
    TMP.mkdir(exist_ok=True)
    src = TMP / "escape.pdf"
    doc = fitz.open()
    doc.new_page().insert_text(fitz.Point(72, 72), 'a & b <c> "d"')
    doc.save(str(src))
    doc.close()

    out = str(TMP / "escape.docx")
    convert.pdf_to_docx(str(src), out, engine="builtin")
    with ZipFile(out) as zf:
        document = zf.read("word/document.xml").decode("utf-8")
    ET.fromstring(document)  # would blow up if the text was not escaped
    assert "&amp;" in document and "&lt;c&gt;" in document


def test_builtin_docx_page_subset():
    src = _text_pdf("subset.pdf", 3)
    out = str(TMP / "subset.docx")
    result = convert.pdf_to_docx(src, out, pages="2", engine="builtin")
    assert result["pages"] == 1
    with ZipFile(out) as zf:
        document = zf.read("word/document.xml").decode("utf-8")
    assert "page 2" in document and "page 1" not in document


@pytest.mark.skipif(convert.libreoffice_available(), reason="LibreOffice is installed")
def test_libreoffice_paths_fail_loudly_when_absent():
    src = _text_pdf("lo.pdf")
    with pytest.raises(RuntimeError, match="LibreOffice is not installed"):
        convert.pdf_to_docx(src, str(TMP / "lo.docx"), engine="libreoffice")
    with pytest.raises(RuntimeError, match="LibreOffice is not installed"):
        convert.file_to_pdf(src, str(TMP / "lo-back.pdf"))


def test_engine_auto_picks_what_is_available():
    src = _text_pdf("auto.pdf")
    result = convert.pdf_to_docx(src, str(TMP / "auto.docx"), engine="auto")
    expected = "libreoffice" if convert.libreoffice_available() else "builtin"
    assert result["engine"] == expected


def test_engine_argument_is_validated():
    src = _text_pdf("badengine.pdf")
    with pytest.raises(ValueError):
        convert.pdf_to_docx(src, str(TMP / "bad.docx"), engine="wishful")


def test_conversion_missing_input_raises():
    with pytest.raises(FileNotFoundError):
        convert.pdf_to_docx(str(TMP / "nope.pdf"), str(TMP / "nope.docx"))


def test_pdf_text_pages_and_capabilities():
    src = _text_pdf("caps.pdf", 3)
    assert len(convert.pdf_text_pages(src)) == 3
    assert len(convert.pdf_text_pages(src, "1,3")) == 2

    caps = convert.capabilities()
    assert caps["builtin_docx"] is True
    assert caps["network"] == "not used"
    assert "tesseract" in caps and "libreoffice" in caps
