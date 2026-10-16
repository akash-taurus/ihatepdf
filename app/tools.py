"""Tool definitions shared by the desktop app.

This module deliberately contains no Qt imports: every tool is described as
plain data (label, which option fields to show, what kind of output it writes)
plus a ``run`` function that takes a :class:`Ctx` and calls into ``core``.
That keeps the desktop app's logic testable without a display, and keeps
``app/main.py`` down to widget wiring.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from core import convert, forms, ocr, ops, sign


@dataclass
class Ctx:
    """Everything a tool needs: input files, an output path and option values."""

    inputs: list[str] = field(default_factory=list)
    out: str | None = None
    values: dict[str, Any] = field(default_factory=dict)
    #: page order from the thumbnail pane, when the user has arranged one
    order: list[int] | None = None

    def get(self, key: str, default: Any = None) -> Any:
        value = self.values.get(key, default)
        return default if value is None else value

    @property
    def first(self) -> str:
        if not self.inputs:
            raise ValueError("Add at least one input file first")
        return self.inputs[0]

    def pages(self) -> str | None:
        text = str(self.get("pages", "") or "").strip()
        return text or None


ToolRun = Callable[[Ctx], Any]


@dataclass(frozen=True)
class Tool:
    label: str
    fields: tuple[str, ...]
    output: str  # "file", "dir" or "none"
    run: ToolRun
    hint: str = ""

    def __str__(self) -> str:  # pragma: no cover - convenience for debugging
        return self.label


# ---------------------------------------------------------------- helpers


def parse_pairs(text: str | None) -> dict[str, str]:
    """Parse ``name=value`` lines (blank lines and ``#`` comments ignored)."""
    out: dict[str, str] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Expected name=value, got {line!r}")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Missing field name in {line!r}")
        out[key] = value.strip()
    return out


def parse_json_fields(text: str | None) -> list[dict]:
    """Parse the ``add-fields`` JSON array from the text box."""
    body = (text or "").strip()
    if not body:
        raise ValueError("Paste a JSON array of field objects first")
    try:
        loaded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Field JSON is invalid: {exc}") from None
    if not isinstance(loaded, list):
        raise ValueError("Field JSON must be an array of objects")
    return loaded


def _opt_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _opt_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


# ---------------------------------------------------------------- tool runs


def _merge(c: Ctx):
    return ops.merge(c.inputs, c.out or "merged.pdf")


def _split(c: Ctx):
    every = int(c.get("every", 0) or 0) or None
    ranges = _opt_str(c.get("ranges"))
    if every and ranges:
        raise ValueError("Use either 'Split every N' or explicit ranges, not both")
    if not c.out:
        raise ValueError("Choose an output folder")
    return ops.split_pdf(c.first, c.out, ranges, every)


def _extract(c: Ctx):
    return ops.extract_pages(c.first, c.pages() or "1", c.out or "extracted.pdf")


def _delete(c: Ctx):
    return ops.delete_pages(c.first, c.pages() or "1", c.out or "deleted.pdf")


def _rotate(c: Ctx):
    return ops.rotate_pages(c.first, c.out or "rotated.pdf", int(c.get("angle", 90)), c.pages())


def _reorder(c: Ctx):
    order = ",".join(str(p) for p in c.order) if c.order else _opt_str(c.get("order"))
    if not order:
        raise ValueError('Enter a page order such as "3,1,2", or load page thumbnails')
    return ops.reorder_pages(c.first, order, c.out or "reordered.pdf")


def _compress(c: Ctx):
    return ops.compress_pdf(
        c.first, c.out or "compressed.pdf", int(c.get("quality", 65)), int(c.get("dpi", 150))
    )


def _images_to_pdf(c: Ctx):
    return ops.images_to_pdf(c.inputs, c.out or "images.pdf")


def _pdf_to_images(c: Ctx):
    if not c.out:
        raise ValueError("Choose an output folder")
    return ops.pdf_to_images(
        c.first, c.out, int(c.get("dpi", 200)), str(c.get("format", "png")), c.pages()
    )


def _extract_images(c: Ctx):
    if not c.out:
        raise ValueError("Choose an output folder")
    return ops.extract_images(c.first, c.out)


def _watermark(c: Ctx):
    text = str(c.get("text", "") or "").strip()
    if not text:
        raise ValueError("Enter the watermark text")
    return ops.watermark_text(
        c.first,
        c.out or "watermarked.pdf",
        text,
        int(c.get("fontsize", 48)),
        opacity=float(c.get("opacity", 0.25)),
        pages=c.pages(),
    )


def _page_numbers(c: Ctx):
    return ops.add_page_numbers(c.first, c.out or "numbered.pdf", pages=c.pages())


def _encrypt(c: Ctx):
    return ops.encrypt_pdf(c.first, c.out or "encrypted.pdf", str(c.get("password", "") or ""))


def _decrypt(c: Ctx):
    return ops.decrypt_pdf(c.first, c.out or "decrypted.pdf", str(c.get("password", "") or ""))


def _info(c: Ctx):
    return ops.info(c.first)


def _text(c: Ctx):
    text = ops.extract_text(c.first, c.pages())
    if c.out:
        Path(c.out).parent.mkdir(parents=True, exist_ok=True)
        Path(c.out).write_text(text, encoding="utf-8")
        return c.out
    return text


def _ocr(c: Ctx):
    return ocr.ocr_pdf(
        c.first,
        c.out or "searchable.pdf",
        pages=c.pages(),
        language=str(c.get("language", "eng") or "eng"),
        dpi=int(c.get("dpi", 300)),
        skip_pages_with_text=not bool(c.get("force", False)),
    )


def _ocr_text(c: Ctx):
    text = ocr.ocr_text(
        c.first,
        pages=c.pages(),
        language=str(c.get("language", "eng") or "eng"),
        dpi=int(c.get("dpi", 300)),
    )
    if c.out:
        Path(c.out).parent.mkdir(parents=True, exist_ok=True)
        Path(c.out).write_text(text, encoding="utf-8")
        return c.out
    return text


def _pdf_to_docx(c: Ctx):
    return convert.pdf_to_docx(
        c.first, c.out or "converted.docx", pages=c.pages(), engine=str(c.get("engine", "auto"))
    )


def _docx_to_pdf(c: Ctx):
    return convert.file_to_pdf(c.first, c.out or "converted.pdf")


def _form_fields(c: Ctx):
    fields = forms.list_form_fields(c.first)
    return {"count": len(fields), "fields": fields}


def _fill_form(c: Ctx):
    values = parse_pairs(c.get("values"))
    if not values:
        raise ValueError("Enter at least one name=value line")
    return forms.fill_form(
        c.first, c.out or "filled.pdf", values, flatten=bool(c.get("flatten", False))
    )


def _flatten_form(c: Ctx):
    return forms.flatten_form(c.first, c.out or "flattened.pdf")


def _add_fields(c: Ctx):
    return forms.add_form_fields(
        c.first, c.out or "with-fields.pdf", parse_json_fields(c.get("fields"))
    )


def _sign(c: Ctx):
    pfx = _opt_str(c.get("pfx"))
    if not pfx:
        raise ValueError("Choose a .p12/.pfx certificate")
    box_text = _opt_str(c.get("box"))
    box = None
    if box_text:
        parts = [p for p in box_text.replace(",", " ").split() if p]
        if len(parts) != 4:
            raise ValueError("Signature box must be four numbers: x0 y0 x1 y1")
        box = [float(p) for p in parts]
    return sign.sign_pdf(
        c.first,
        c.out or "signed.pdf",
        pfx,
        str(c.get("pfx_password", "") or ""),
        reason=_opt_str(c.get("reason")),
        location=_opt_str(c.get("location")),
        contact=_opt_str(c.get("contact")),
        page=int(c.get("page", 1) or 1),
        box=box,
    )


def _verify_signatures(c: Ctx):
    found = sign.verify_signatures(c.first)
    return {"count": len(found), "signatures": found}


def _stamp(c: Ctx):
    image = _opt_str(c.get("image"))
    if not image:
        raise ValueError("Choose the image to stamp")
    pages = c.pages()
    width = _opt_float(c.get("width"))
    return sign.stamp_image(
        c.first,
        c.out or "stamped.pdf",
        image,
        page=int(c.get("page", 1) or 1),
        x=_opt_float(c.get("x")),
        y=_opt_float(c.get("y")),
        width=width,
        opacity=float(c.get("opacity", 1.0)),
        pages=pages,
    )


# ---------------------------------------------------------------- catalogue

TOOLS: list[Tool] = [
    Tool("Merge PDFs", (), "file", _merge, "Merges every listed file, top to bottom."),
    Tool(
        "Split PDF",
        ("ranges", "every"),
        "dir",
        _split,
        "One file per page unless ranges/every are set.",
    ),
    Tool("Extract pages", ("pages",), "file", _extract),
    Tool("Delete pages", ("pages",), "file", _delete),
    Tool("Rotate pages", ("angle", "pages"), "file", _rotate),
    Tool(
        "Reorder pages",
        ("order",),
        "file",
        _reorder,
        "Page thumbnails in the second tab win when loaded.",
    ),
    Tool("Compress", ("quality", "dpi"), "file", _compress),
    Tool("Images to PDF", (), "file", _images_to_pdf),
    Tool("PDF to images", ("dpi", "format", "pages"), "dir", _pdf_to_images),
    Tool("Extract embedded images", (), "dir", _extract_images),
    Tool("Watermark", ("text", "fontsize", "opacity", "pages"), "file", _watermark),
    Tool("Page numbers", ("pages",), "file", _page_numbers),
    Tool("Encrypt", ("password",), "file", _encrypt),
    Tool("Decrypt", ("password",), "file", _decrypt),
    Tool("Info", (), "none", _info),
    Tool("Extract text", ("pages",), "txt", _text, "Leave the output blank to print to the log."),
    Tool(
        "OCR (searchable PDF)",
        ("language", "dpi", "pages", "force"),
        "file",
        _ocr,
        "Needs the Tesseract binary installed locally.",
    ),
    Tool("OCR to text", ("language", "dpi", "pages"), "txt", _ocr_text),
    Tool(
        "PDF to DOCX",
        ("engine", "pages"),
        "docx",
        _pdf_to_docx,
        "Uses LibreOffice when installed, else the built-in writer.",
    ),
    Tool("DOCX to PDF", (), "file", _docx_to_pdf, "Needs LibreOffice installed locally."),
    Tool("List form fields", (), "none", _form_fields),
    Tool("Add form fields", ("fields",), "file", _add_fields),
    Tool("Fill form", ("values", "flatten"), "file", _fill_form),
    Tool("Flatten form", (), "file", _flatten_form),
    Tool(
        "Sign (PKCS#12)",
        ("pfx", "pfx_password", "reason", "location", "page", "box"),
        "file",
        _sign,
        "Needs the optional pyHanko dependency.",
    ),
    Tool("Verify signatures", (), "none", _verify_signatures),
    Tool("Stamp image", ("image", "page", "width", "x", "y", "opacity"), "file", _stamp),
]

#: Tools that work on a whole list of files rather than just the first one.
MULTI_INPUT = {"Merge PDFs", "Images to PDF"}


def requirements_met(label: str) -> tuple[bool, str]:
    """Whether a tool's optional backend is present, with a reason if not."""
    if label.startswith("OCR"):
        if not ocr.tesseract_available():
            return False, "Tesseract is not installed (see README)"
    elif label == "DOCX to PDF":
        if not convert.libreoffice_available():
            return False, "LibreOffice is not installed"
    elif label.startswith("Sign") or label == "Verify signatures":
        if not sign.signing_available():
            return False, "pyHanko is not installed (requirements-optional.txt)"
    return True, ""


def unavailable_tools() -> dict[str, str]:
    """``{tool label: reason}`` for tools whose backend is missing right now."""
    missing: dict[str, str] = {}
    for tool in TOOLS:
        ok, reason = requirements_met(tool.label)
        if not ok:
            missing[tool.label] = reason
    return missing
