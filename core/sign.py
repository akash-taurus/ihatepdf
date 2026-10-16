"""Digital signatures and visible stamps.

Signing uses `pyHanko <https://github.com/MatthiasValvekens/pyHanko>`_ (an
optional dependency, imported lazily) with a PKCS#12 bundle (``.p12``/``.pfx``)
you already own. Signatures are cryptographic, embedded in the PDF, and
verifiable offline; nothing is uploaded and no timestamp authority is contacted
unless you pass a timestamp URL.

The image stamping helper is independent of pyHanko and covers the "wet
signature" case: a scanned or drawn signature, a company seal, or a logo.
"""

from __future__ import annotations

import io
from pathlib import Path

import fitz
from PIL import Image

from .ops import _ensure_parent
from .pagespec import parse_pagespec

INSTALL_HINT = (
    "Signing needs pyHanko: 'pip install -r requirements-optional.txt' "
    "(installs pyhanko + cryptography)."
)


def signing_available() -> bool:
    """True if the optional signing dependency is importable."""
    try:
        import pyhanko.sign.signers  # noqa: F401
    except Exception:
        return False
    return True


def _require_pyhanko():
    try:
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import signers
        from pyhanko.sign.fields import SigFieldSpec
    except Exception as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError(f"{exc}. {INSTALL_HINT}") from exc
    return signers, SigFieldSpec, IncrementalPdfFileWriter


def _subject_string(cert) -> str:
    """Best-effort RFC 4514 style name for an asn1crypto or cryptography cert."""
    if cert is None:
        return ""
    subject = getattr(cert, "subject", cert)
    rfc4514 = getattr(subject, "rfc4514_string", None)
    if callable(rfc4514):
        try:
            return str(rfc4514())
        except Exception:  # pragma: no cover - defensive
            pass
    pretty = getattr(subject, "human_friendly", None)
    if pretty:
        return str(pretty).strip()
    native = getattr(subject, "native", None)
    if native:
        try:
            return ", ".join(f"{k}={v}" for k, v in dict(native).items())
        except Exception:  # pragma: no cover - defensive
            pass
    return str(subject)


def sign_pdf(
    input_path: str,
    output_path: str,
    pfx_path: str,
    password: str,
    field_name: str = "Signature",
    reason: str | None = None,
    location: str | None = None,
    contact: str | None = None,
    page: int = 1,
    box: tuple[float, float, float, float] | list[float] | None = None,
    timestamp_url: str | None = None,
) -> dict:
    """Apply a cryptographic signature using a PKCS#12 certificate.

    Args:
        box: optional ``[x0, y0, x1, y1]`` for a visible signature field, in PDF
            points measured from the **top-left** corner of the page (``y``
            grows downwards), which is the convention used by PDF viewers. The
            value is converted to PDF user space internally. Without a box the
            signature is invisible and can be paired with :func:`stamp_image`
            for a visual one.
        timestamp_url: optional RFC 3161 timestamp authority. Defaults to no
            network access at all.

    Returns:
        ``{"output", "field", "signer", "timestamped"}``.
    """
    if not Path(input_path).exists():
        raise FileNotFoundError(input_path)
    if not Path(pfx_path).exists():
        raise FileNotFoundError(pfx_path)
    if not password:
        raise ValueError("Certificate password is empty")

    # Validate caller arguments before reaching for the optional dependency, so
    # a bad box or page number is reported as such even without pyHanko.
    box_bounds: tuple[float, float, float, float] | None = None
    if box:
        if len(box) != 4:
            raise ValueError("box must be [x0, y0, x1, y1]")
        with fitz.open(input_path) as doc:
            if not 1 <= int(page) <= doc.page_count:
                raise ValueError(f"Page {page} out of range (1-{doc.page_count})")
            page_height = doc[int(page) - 1].mediabox.height
        x0, top, x1, bottom = (float(v) for v in box)
        if x1 < x0:
            x0, x1 = x1, x0
        if bottom < top:
            top, bottom = bottom, top
        # PyHanko places fields in PDF user space (origin bottom-left), so the
        # top-left based box the caller gave us is flipped vertically here.
        box_bounds = (
            round(x0),
            round(page_height - bottom),
            round(x1),
            round(page_height - top),
        )

    signers, SigFieldSpec, IncrementalPdfFileWriter = _require_pyhanko()
    _ensure_parent(output_path)

    signer = signers.SimpleSigner.load_pkcs12(pfx_file=pfx_path, passphrase=password.encode())
    if signer is None:
        raise ValueError("Could not load the certificate — check the .p12/.pfx password")

    timestamper = None
    if timestamp_url:
        from pyhanko.sign.timestamps import HTTPTimeStamper

        timestamper = HTTPTimeStamper(timestamp_url)

    meta = signers.PdfSignatureMetadata(
        field_name=field_name,
        reason=reason,
        location=location,
        contact_info=contact,
    )
    field_spec = (
        SigFieldSpec(
            sig_field_name=field_name,
            on_page=int(page) - 1,
            box=tuple(int(v) for v in box_bounds),
        )
        if box_bounds
        else None
    )

    with open(input_path, "rb") as src, open(output_path, "wb") as dst:
        writer = IncrementalPdfFileWriter(src)
        signers.sign_pdf(
            writer,
            signature_meta=meta,
            signer=signer,
            timestamper=timestamper,
            new_field_spec=field_spec,
            existing_fields_only=field_spec is None and _has_sig_field(input_path, field_name),
            output=dst,
        )

    return {
        "output": output_path,
        "field": field_name,
        "signer": _subject_string(getattr(signer, "signing_cert", None)),
        "timestamped": bool(timestamp_url),
    }


def _has_sig_field(input_path: str, field_name: str) -> bool:
    with fitz.open(input_path) as doc:
        for pno in range(doc.page_count):
            for widget in doc[pno].widgets():
                if (
                    widget.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE
                    and widget.field_name == field_name
                ):
                    return True
    return False


def verify_signatures(input_path: str) -> list[dict]:
    """Inspect every embedded signature. Verification is fully local.

    A signature is reported as ``intact`` when the bytes it covers are
    unchanged, and ``trusted`` only when it chains to a certificate authority
    known to the local trust store — a self-signed certificate is intact but
    not trusted, which is correct and expected.
    """
    if not Path(input_path).exists():
        raise FileNotFoundError(input_path)
    _require_pyhanko()
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature

    results: list[dict] = []
    with open(input_path, "rb") as fh:
        reader = PdfFileReader(fh)
        for embedded in reader.embedded_signatures:
            entry: dict = {"field": embedded.field_name}
            try:
                status = validate_pdf_signature(embedded)
                entry.update(
                    {
                        "intact": bool(getattr(status, "intact", False)),
                        "valid": bool(getattr(status, "valid", False)),
                        "trusted": bool(getattr(status, "trusted", False)),
                        "coverage": _coverage_name(getattr(status, "coverage", "")),
                        "signer": _subject_string(getattr(status, "signing_cert", None)),
                        "signed_at": str(getattr(status, "signer_reported_dt", "") or ""),
                    }
                )
            except Exception as exc:
                entry.update({"intact": False, "valid": False, "trusted": False, "error": str(exc)})
            results.append(entry)
    return results


def _coverage_name(coverage) -> str:
    """``SignatureCoverageLevel.ENTIRE_FILE`` -> ``entire_file``."""
    text = str(coverage or "")
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text.lower()


def stamp_image(
    input_path: str,
    output_path: str,
    image_path: str,
    page: int = 1,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    opacity: float = 1.0,
    pages: str | None = None,
) -> str:
    """Overlay an image (signature, seal, logo) on one or more pages.

    By default the image lands in the bottom-right corner with a 36pt margin,
    which is where a signature usually goes. Pass ``x``/``y`` to set the
    top-left corner of the image yourself: both are PDF points measured from
    the page's **top-left**, matching what viewers show. Transparency is
    preserved, so a PNG signature on a transparent background drops in cleanly.
    """
    if not Path(input_path).exists():
        raise FileNotFoundError(input_path)
    if not Path(image_path).exists():
        raise FileNotFoundError(image_path)
    if not 0.0 < opacity <= 1.0:
        raise ValueError("opacity must be in (0, 1]")
    _ensure_parent(output_path)

    stream = _prepared_image(image_path, opacity)
    with fitz.open(input_path) as doc:
        target_pages = [int(page) - 1] if pages is None else parse_pagespec(pages, doc.page_count)
        for pno in target_pages:
            if not 0 <= pno < doc.page_count:
                raise ValueError(f"Page {pno + 1} out of range (1-{doc.page_count})")
            rect = doc[pno].rect
            probe = fitz.open(stream=stream, filetype="png")
            iw, ih = probe[0].rect.width, probe[0].rect.height
            probe.close()
            w = float(width or 160.0)
            h = w * (ih / iw) if iw else w
            # PyMuPDF rects for insert_image are top-left anchored, y downwards.
            left = (rect.x1 - 36 - w) if x is None else float(x)
            top = (rect.y1 - 36 - h) if y is None else float(y)
            doc[pno].insert_image(
                fitz.Rect(left, top, left + w, top + h),
                stream=stream,
                overlay=True,
                keep_proportion=True,
            )
        doc.save(output_path, garbage=4, deflate=True)
    return output_path


def _prepared_image(image_path: str, opacity: float) -> bytes:
    """Normalised PNG bytes, with ``opacity`` folded into the alpha channel."""
    with Image.open(image_path) as img:
        rgba = img.convert("RGBA")
        if opacity < 1.0:
            alpha = rgba.getchannel("A").point(lambda v: int(v * opacity))
            rgba.putalpha(alpha)
        buf = io.BytesIO()
        rgba.save(buf, "PNG")
    return buf.getvalue()
