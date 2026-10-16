"""ihatepdf CLI — thin wrapper over the core modules. All local."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core import __version__, convert, forms, ocr, ops, sign

# ---------------------------------------------------------------- output


def _print_result(result) -> None:
    """Print whatever a handler returned: paths, path lists, or JSON dicts."""
    if isinstance(result, str):
        print(result)
    elif isinstance(result, (list, tuple)):
        for item in result:
            print(item)
    else:
        print(json.dumps(result, indent=2, default=str))


def _pairs(items: list[str] | None, what: str) -> dict:
    """Turn ['k=v', ...] into {'k': 'v'}, rejecting malformed entries."""
    out: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"{what} must look like name=value, got {item!r}")
        key, value = item.split("=", 1)
        out[key.strip()] = value
    return out


def _load_json(path: str, what: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(path) from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON for {what}: {exc}") from None


def _rect(text: str) -> list[float]:
    parts = [p.strip() for p in text.replace(",", " ").split()]
    if len(parts) != 4:
        raise ValueError("box must have four numbers: x0 y0 x1 y1")
    return [float(p) for p in parts]


# ---------------------------------------------------------------- handlers


def _merge(a):
    return ops.merge(a.inputs, a.output)


def _split(a):
    return ops.split_pdf(a.input, a.output_dir, a.ranges, a.every)


def _info(a):
    return ops.info(a.input)


def _extract(a):
    return ops.extract_pages(a.input, a.pages, a.output)


def _delete(a):
    return ops.delete_pages(a.input, a.pages, a.output)


def _rotate(a):
    return ops.rotate_pages(a.input, a.output, a.angle, a.pages)


def _reorder(a):
    return ops.reorder_pages(a.input, a.order, a.output)


def _compress(a):
    return ops.compress_pdf(a.input, a.output, a.image_quality, a.dpi)


def _images_to_pdf(a):
    return ops.images_to_pdf(a.inputs, a.output)


def _pdf_to_images(a):
    return ops.pdf_to_images(a.input, a.output_dir, a.dpi, a.format, a.pages)


def _extract_images(a):
    return ops.extract_images(a.input, a.output_dir)


def _watermark(a):
    return ops.watermark_text(
        a.input, a.output, a.text, a.fontsize, opacity=a.opacity, pages=a.pages
    )


def _page_numbers(a):
    return ops.add_page_numbers(a.input, a.output, pages=a.pages)


def _encrypt(a):
    return ops.encrypt_pdf(a.input, a.output, a.password)


def _decrypt(a):
    return ops.decrypt_pdf(a.input, a.output, a.password)


def _text(a):
    text = ops.extract_text(a.input, a.pages)
    if a.output:
        Path(a.output).parent.mkdir(parents=True, exist_ok=True)
        Path(a.output).write_text(text, encoding="utf-8")
        return a.output
    return text


def _metadata(a):
    if not a.set:
        return ops.get_metadata(a.input)
    if not a.output:
        raise ValueError("--output is required together with --set")
    return ops.set_metadata(a.input, a.output, _pairs(a.set, "--set"))


def _capabilities(a):
    return convert.capabilities()


# --- OCR


def _ocr(a):
    return ocr.ocr_pdf(
        a.input,
        a.output,
        pages=a.pages,
        language=a.language,
        dpi=a.dpi,
        skip_pages_with_text=not a.force,
    )


def _ocr_text(a):
    text = ocr.ocr_text(a.input, pages=a.pages, language=a.language, dpi=a.dpi)
    if a.output:
        Path(a.output).parent.mkdir(parents=True, exist_ok=True)
        Path(a.output).write_text(text, encoding="utf-8")
        return a.output
    return text


# --- conversion


def _pdf_to_docx(a):
    return convert.pdf_to_docx(a.input, a.output, pages=a.pages, engine=a.engine)


def _docx_to_pdf(a):
    return convert.file_to_pdf(a.input, a.output)


# --- forms


def _form_fields(a):
    fields = forms.list_form_fields(a.input)
    return {"count": len(fields), "fields": fields}


def _fill_form(a):
    values = _pairs(a.set, "--set")
    if a.json:
        loaded = _load_json(a.json, "form values")
        if not isinstance(loaded, dict):
            raise ValueError(f"{a.json} must contain a JSON object of field values")
        values.update({str(k): v for k, v in loaded.items()})
    return forms.fill_form(a.input, a.output, values, flatten=a.flatten)


def _flatten_form(a):
    return forms.flatten_form(a.input, a.output)


def _add_fields(a):
    specs: list[dict] = []
    if a.json:
        loaded = _load_json(a.json, "form fields")
        if not isinstance(loaded, list):
            raise ValueError(f"{a.json} must contain a JSON array of field objects")
        specs.extend(loaded)
    for raw in a.field or []:
        try:
            specs.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(f"--field expects a JSON object: {exc}") from None
    return forms.add_form_fields(a.input, a.output, specs)


# --- signing


def _sign(a):
    return sign.sign_pdf(
        a.input,
        a.output,
        a.pfx,
        a.password,
        field_name=a.field,
        reason=a.reason,
        location=a.location,
        contact=a.contact,
        page=a.page,
        box=_rect(a.box) if a.box else None,
        timestamp_url=a.timestamp_url,
    )


def _verify_signatures(a):
    found = sign.verify_signatures(a.input)
    return {"count": len(found), "signatures": found}


def _stamp(a):
    pages = a.pages or str(a.page)
    return sign.stamp_image(
        a.input,
        a.output,
        a.image,
        page=a.page,
        x=a.x,
        y=a.y,
        width=a.width,
        opacity=a.opacity,
        pages=pages,
    )


HANDLERS = {
    "info": _info,
    "merge": _merge,
    "split": _split,
    "extract": _extract,
    "delete": _delete,
    "rotate": _rotate,
    "reorder": _reorder,
    "compress": _compress,
    "images-to-pdf": _images_to_pdf,
    "pdf-to-images": _pdf_to_images,
    "extract-images": _extract_images,
    "watermark": _watermark,
    "pagenumbers": _page_numbers,
    "encrypt": _encrypt,
    "decrypt": _decrypt,
    "text": _text,
    "metadata": _metadata,
    "ocr": _ocr,
    "ocr-text": _ocr_text,
    "pdf-to-docx": _pdf_to_docx,
    "docx-to-pdf": _docx_to_pdf,
    "form-fields": _form_fields,
    "fill-form": _fill_form,
    "flatten-form": _flatten_form,
    "add-fields": _add_fields,
    "sign": _sign,
    "verify-signatures": _verify_signatures,
    "stamp": _stamp,
    "capabilities": _capabilities,
}


# ---------------------------------------------------------------- parser


def _pages_arg(parser: argparse.ArgumentParser, required: bool = False) -> None:
    parser.add_argument(
        "--pages",
        required=required,
        default=None,
        help='page spec such as "1,3-5" (default: all pages)',
    )


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="ihatepdf",
        description="Local-first PDF toolkit — nothing is ever uploaded.",
    )
    ap.add_argument("--version", action="version", version=f"ihatepdf {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    s = sub.add_parser("info", help="Show page count / metadata")
    s.add_argument("input")

    s = sub.add_parser("merge", help="Merge PDFs in order")
    s.add_argument("inputs", nargs="+")
    s.add_argument("-o", "--output", required=True)

    s = sub.add_parser("split", help="Split PDF")
    s.add_argument("input")
    s.add_argument("-o", "--output-dir", required=True)
    s.add_argument("--ranges", default=None, help='"1-2,3-5" (default: one file per page)')
    s.add_argument("--every", type=int, default=None, help="fixed chunk size in pages")

    s = sub.add_parser("extract", help="Extract pages into a new PDF")
    s.add_argument("input")
    _pages_arg(s, required=True)
    s.add_argument("-o", "--output", required=True)

    s = sub.add_parser("delete", help="Delete pages")
    s.add_argument("input")
    _pages_arg(s, required=True)
    s.add_argument("-o", "--output", required=True)

    s = sub.add_parser("rotate", help="Rotate pages clockwise")
    s.add_argument("input")
    s.add_argument("--angle", type=int, required=True, choices=[90, 180, 270, -90, -180, -270])
    _pages_arg(s)
    s.add_argument("-o", "--output", required=True)

    s = sub.add_parser("reorder", help='Reorder / duplicate pages, e.g. --order "3,1,2"')
    s.add_argument("input")
    s.add_argument("--order", required=True)
    s.add_argument("-o", "--output", required=True)

    s = sub.add_parser("compress", help="Reduce file size")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--image-quality", type=int, default=65, help="JPEG quality 1-100")
    s.add_argument("--dpi", type=int, default=150, help="downsampling target")

    s = sub.add_parser("images-to-pdf", help="Images -> PDF")
    s.add_argument("inputs", nargs="+")
    s.add_argument("-o", "--output", required=True)

    s = sub.add_parser("pdf-to-images", help="PDF -> images")
    s.add_argument("input")
    s.add_argument("-o", "--output-dir", required=True)
    s.add_argument("--dpi", type=int, default=200)
    s.add_argument("--format", default="png", choices=["png", "jpg"])
    _pages_arg(s)

    s = sub.add_parser("extract-images", help="Extract embedded images as-is")
    s.add_argument("input")
    s.add_argument("-o", "--output-dir", required=True)

    s = sub.add_parser("watermark", help="Text watermark overlay")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--text", required=True)
    s.add_argument("--fontsize", type=int, default=48)
    s.add_argument("--opacity", type=float, default=0.25)
    _pages_arg(s)

    s = sub.add_parser("pagenumbers", help="Add page numbers")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    _pages_arg(s)

    s = sub.add_parser("encrypt", help="Encrypt with AES-256")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--password", required=True)

    s = sub.add_parser("decrypt", help="Decrypt")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--password", required=True)

    s = sub.add_parser("text", help="Extract the text layer")
    s.add_argument("input")
    _pages_arg(s)
    s.add_argument("-o", "--output", default=None, help="write to a .txt file instead of stdout")

    s = sub.add_parser("metadata", help="Get or set metadata")
    s.add_argument("input")
    s.add_argument("--set", nargs="*", default=None, metavar="key=value")
    s.add_argument("-o", "--output", default=None)

    # --- OCR ------------------------------------------------------------
    s = sub.add_parser("ocr", help="Add a searchable text layer to a scanned PDF")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    _pages_arg(s)
    s.add_argument("--language", default="eng", help="Tesseract language code(s), e.g. eng+deu")
    s.add_argument("--dpi", type=int, default=300)
    s.add_argument("--force", action="store_true", help="OCR pages that already have text")

    s = sub.add_parser("ocr-text", help="OCR the PDF and print the recognised text")
    s.add_argument("input")
    _pages_arg(s)
    s.add_argument("--language", default="eng")
    s.add_argument("--dpi", type=int, default=300)
    s.add_argument("-o", "--output", default=None, help="write to a .txt file instead of stdout")

    # --- conversion -----------------------------------------------------
    s = sub.add_parser("pdf-to-docx", help="Convert PDF -> DOCX")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    _pages_arg(s)
    s.add_argument(
        "--engine",
        default="auto",
        choices=["auto", "libreoffice", "builtin"],
        help="auto uses LibreOffice when installed, else the built-in writer",
    )

    s = sub.add_parser("docx-to-pdf", help="Convert DOCX/ODT/DOC -> PDF (needs LibreOffice)")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)

    # --- forms ----------------------------------------------------------
    s = sub.add_parser("form-fields", help="List form fields")
    s.add_argument("input")

    s = sub.add_parser("fill-form", help="Fill form fields by name")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--set", nargs="*", default=None, metavar="name=value")
    s.add_argument("--json", default=None, help="JSON file with a {name: value} object")
    s.add_argument("--flatten", action="store_true", help="bake values in and drop the form")

    s = sub.add_parser("flatten-form", help="Flatten a form into page content")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)

    s = sub.add_parser("add-fields", help="Add form fields")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    s.add_argument(
        "--field",
        action="append",
        default=None,
        help='JSON field object, repeatable, e.g. \'{"name":"a","type":"text","rect":[72,500,300,520]}\'',
    )
    s.add_argument("--json", default=None, help="JSON file with an array of field objects")

    # --- signing --------------------------------------------------------
    s = sub.add_parser("sign", help="Apply a PKCS#12 digital signature")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--pfx", required=True, help="path to a .p12/.pfx bundle")
    s.add_argument("--password", required=True, help="bundle password")
    s.add_argument("--field", default="Signature", help="signature field name")
    s.add_argument("--reason", default=None)
    s.add_argument("--location", default=None)
    s.add_argument("--contact", default=None)
    s.add_argument("--page", type=int, default=1, help="page for a visible signature box")
    s.add_argument("--box", default=None, help='"x0,y0,x1,y1" from the page\'s top-left corner')
    s.add_argument("--timestamp-url", default=None, help="RFC 3161 authority (network opt-in)")

    s = sub.add_parser("verify-signatures", help="Verify embedded signatures locally")
    s.add_argument("input")

    s = sub.add_parser("stamp", help="Overlay an image (signature, seal, logo) on pages")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--image", required=True)
    s.add_argument("--page", type=int, default=1)
    _pages_arg(s)
    s.add_argument("--x", type=float, default=None, help="left edge, from the page's left side")
    s.add_argument("--y", type=float, default=None, help="top edge, from the page's top side")
    s.add_argument("--width", type=float, default=None, help="image width in points")
    s.add_argument("--opacity", type=float, default=1.0)

    sub.add_parser("capabilities", help="Report which optional backends are available")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _print_result(HANDLERS[args.cmd](args))
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
