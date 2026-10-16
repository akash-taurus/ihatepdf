"""Format conversion: PDF -> DOCX, and Office documents -> PDF.

Two engines, in order of preference:

1. **LibreOffice headless** (``soffice``) — full-fidelity conversion when it is
   installed. Nothing is uploaded; the conversion runs as a local subprocess.
2. **Built-in DOCX writer** — a dependency-free fallback that extracts the text
   layer and emits a valid ``.docx`` package. Layout is not preserved, but it
   works everywhere, instantly, with no external binary.

The engine actually used is reported in the result and by :func:`capabilities`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import fitz

from .ops import _ensure_parent
from .pagespec import parse_pagespec

#: Extra places to look for LibreOffice when it is not on PATH.
_SOFFICE_CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
    "/snap/bin/libreoffice",
)

#: LibreOffice target filters per output suffix.
_LO_FILTERS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "doc",
    ".odt": "odt",
    ".txt": "txt",
    ".xlsx": "xlsx",
}


def soffice_path() -> str | None:
    """Path to the LibreOffice binary, or None when it is not installed."""
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    for candidate in _SOFFICE_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def libreoffice_available() -> bool:
    return soffice_path() is not None


def _run_libreoffice(input_path: str, output_path: str, target_suffix: str) -> str:
    """Convert with LibreOffice headless into the output path's directory."""
    binary = soffice_path()
    if binary is None:
        raise RuntimeError(
            "LibreOffice is not installed, so this conversion is unavailable. "
            "Install it (https://www.libreoffice.org/download) or export to DOCX "
            "instead, which has a built-in fallback."
        )
    target = target_suffix.lstrip(".").lower()
    if f".{target}" not in _LO_FILTERS:
        raise ValueError(f"Unsupported LibreOffice target {target!r}")
    out = Path(output_path)
    _ensure_parent(output_path)
    with tempfile.TemporaryDirectory(prefix="ihatepdf-lo-") as workdir:
        # -env:UserInstallation keeps the conversion from touching (or locking)
        # a user's real LibreOffice profile, which also makes runs repeatable.
        cmd = [
            binary,
            f"-env:UserInstallation=file:///{Path(workdir).as_posix()}",
            "--headless",
            "--norestore",
            "--convert-to",
            target,
            "--outdir",
            workdir,
            str(Path(input_path).resolve()),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        produced = sorted(Path(workdir).glob(f"*.{target}"))
        if proc.returncode != 0 or not produced:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            raise RuntimeError(
                "LibreOffice conversion failed"
                + (f": {detail[-1]}" if detail else f" (exit {proc.returncode})")
            )
        shutil.move(str(produced[0]), str(out))
    return output_path


def _docx_package(pages: list[list[str]], title: str, creator: str) -> dict[str, str]:
    """Minimal, valid OOXML package: one paragraph per line, breaks between pages."""
    body: list[str] = []
    for index, lines in enumerate(pages):
        if index:
            body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        if not lines:
            body.append('<w:p><w:r><w:t xml:space="preserve"> </w:t></w:r></w:p>')
            continue
        for line in lines:
            text = escape(line, {'"': "&quot;"})
            body.append('<w:p><w:r><w:t xml:space="preserve">' f"{text}" "</w:t></w:r></w:p>")
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>" + "".join(body) + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>'
        "</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        "</Relationships>"
    )
    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:docDefaults><w:rPrDefault><w:rPr>"
        '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/>'
        "</w:rPr></w:rPrDefault></w:docDefaults></w:styles>"
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{escape(title)}</dc:title><dc:creator>{escape(creator)}</dc:creator>"
        "<cp:lastModifiedBy>ihatepdf</cp:lastModifiedBy>"
        "</cp:coreProperties>"
    )
    return {
        "[Content_Types].xml": content_types,
        "_rels/.rels": rels,
        "word/document.xml": document,
        "word/_rels/document.xml.rels": doc_rels,
        "word/styles.xml": styles,
        "docProps/core.xml": core,
    }


def pdf_text_pages(input_path: str, pages: str | None = None) -> list[list[str]]:
    """Text of each selected page, split into lines (one entry per page)."""
    with fitz.open(input_path) as doc:
        return [
            doc[pno].get_text("text").splitlines() or [""]
            for pno in parse_pagespec(pages, doc.page_count)
        ]


def pdf_to_docx(
    input_path: str,
    output_path: str,
    pages: str | None = None,
    engine: str = "auto",
) -> dict:
    """Convert a PDF to DOCX.

    Args:
        engine: ``auto`` (LibreOffice when available, else built-in),
            ``libreoffice`` to insist on full fidelity, or ``builtin`` to force
            the dependency-free text-based writer.

    Returns:
        ``{"output", "engine", "pages"}``.
    """
    if not Path(input_path).exists():
        raise FileNotFoundError(input_path)
    if engine not in ("auto", "libreoffice", "builtin"):
        raise ValueError("engine must be auto, libreoffice or builtin")
    if engine == "libreoffice" or (engine == "auto" and libreoffice_available()):
        _run_libreoffice(input_path, output_path, ".docx")
        used = "libreoffice"
    else:
        _ensure_parent(output_path)
        with fitz.open(input_path) as doc:
            title = str((doc.metadata or {}).get("title") or Path(input_path).stem)
            creator = str((doc.metadata or {}).get("author") or "ihatepdf")
            count = doc.page_count
        parts = _docx_package(pdf_text_pages(input_path, pages), title, creator)
        with ZipFile(output_path, "w", ZIP_DEFLATED) as zf:
            for name, data in parts.items():
                zf.writestr(name, data.encode("utf-8"))
        used = "builtin"
    with fitz.open(input_path) as doc:
        count = len(parse_pagespec(pages, doc.page_count))
    return {"output": output_path, "engine": used, "pages": count}


def file_to_pdf(input_path: str, output_path: str) -> str:
    """Convert a Word/ODT/text document to PDF with LibreOffice headless."""
    return _run_libreoffice(input_path, output_path, ".pdf")


def capabilities() -> dict:
    """Report which optional local backends are usable right now."""
    from . import ocr

    return {
        "pymupdf": fitz.version[0],
        "libreoffice": soffice_path() or False,
        "tesseract": ocr.tesseract_available(),
        "builtin_docx": True,
        "network": "not used",
        "platform": os.name,
    }
