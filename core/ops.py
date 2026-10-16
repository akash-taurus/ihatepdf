"""Core PDF operations. UI-agnostic: both app/main.py and cli.py call these.

Primary engine: PyMuPDF (fitz). Fallbacks via pypdf where noted.
All paths are local. No network.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

try:
    from pypdf import PdfReader, PdfWriter

    _HAS_PYPDF = True
except Exception:  # pragma: no cover
    _HAS_PYPDF = False

from .pagespec import parse_order, parse_pagespec, parse_ranges_for_split

# ---------------------------------------------------------------- helpers


def _ensure_parent(path: str | os.PathLike) -> None:
    parent = Path(path).expanduser().parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)


def _page_count_fitz(path: str) -> int:
    with fitz.open(path) as doc:
        if doc.is_encrypted:
            # try empty password; caller should decrypt first if needed
            doc.authenticate("")
        return doc.page_count


# ---------------------------------------------------------------- info


def info(path: str) -> dict:
    """Return page count, metadata, size, encryption flag."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    out: dict = {
        "path": str(p),
        "size_bytes": p.stat().st_size,
        "pages": 0,
        "encrypted": False,
        "metadata": {},
    }
    with fitz.open(path) as doc:
        out["encrypted"] = bool(doc.is_encrypted)
        if doc.is_encrypted:
            # don't fail; report what we can
            try:
                doc.authenticate("")
            except Exception:
                pass
        try:
            out["pages"] = doc.page_count
        except Exception:
            out["pages"] = 0
        try:
            out["metadata"] = dict(doc.metadata or {})
        except Exception:
            out["metadata"] = {}
    return out


def get_metadata(path: str) -> dict:
    with fitz.open(path) as doc:
        return dict(doc.metadata or {})


def set_metadata(input_path: str, output_path: str, metadata: dict) -> str:
    """Set PDF metadata keys: title, author, subject, keywords, creator, producer."""
    _ensure_parent(output_path)
    with fitz.open(input_path) as doc:
        doc.set_metadata(metadata or {})
        doc.save(output_path, garbage=4, deflate=True)
    return output_path


# ---------------------------------------------------------------- merge / split / extract


def merge(input_paths: list[str], output_path: str) -> str:
    if len(input_paths) < 2:
        raise ValueError("merge needs at least 2 input files")
    for f in input_paths:
        if not Path(f).exists():
            raise FileNotFoundError(f)
    _ensure_parent(output_path)
    with fitz.open() as out:
        for f in input_paths:
            with fitz.open(f) as src:
                out.insert_pdf(src)
        out.save(output_path, garbage=4, deflate=True)
    return output_path


def split_pdf(
    input_path: str,
    output_dir: str,
    ranges: str | None = None,
    every: int | None = None,
    prefix: str = "page",
) -> list[str]:
    """Split a PDF.

    - ranges="1-2,3-5": one output per group.
    - every=N: chunks of N pages.
    - default: one file per page.
    Returns list of written files.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(input_path).stem
    with fitz.open(input_path) as doc:
        n = doc.page_count
        if every is not None:
            if every < 1:
                raise ValueError("--every must be >= 1")
            groups = [list(range(i, min(i + every, n))) for i in range(0, n, every)]
        elif ranges:
            groups = parse_ranges_for_split(ranges, n)
        else:
            groups = [[i] for i in range(n)]
        written: list[str] = []
        for idx, group in enumerate(groups, start=1):
            with fitz.open() as chunk:
                for pno in group:
                    chunk.insert_pdf(doc, from_page=pno, to_page=pno)
                if len(group) == 1:
                    name = f"{stem}-{prefix}-{group[0] + 1}.pdf"
                else:
                    name = f"{stem}-part-{idx:02d}-p{group[0] + 1}-{group[-1] + 1}.pdf"
                dest = str(out_dir / name)
                chunk.save(dest, garbage=4, deflate=True)
                written.append(dest)
    return written


def extract_pages(input_path: str, pages: str, output_path: str) -> str:
    with fitz.open(input_path) as doc:
        keep = parse_pagespec(pages, doc.page_count)
        _ensure_parent(output_path)
        with fitz.open() as out:
            for pno in keep:
                out.insert_pdf(doc, from_page=pno, to_page=pno)
            out.save(output_path, garbage=4, deflate=True)
    return output_path


def delete_pages(input_path: str, pages: str, output_path: str) -> str:
    with fitz.open(input_path) as doc:
        drop = set(parse_pagespec(pages, doc.page_count))
        keep = [i for i in range(doc.page_count) if i not in drop]
        if not keep:
            raise ValueError("Cannot delete all pages")
        _ensure_parent(output_path)
        with fitz.open() as out:
            for pno in keep:
                out.insert_pdf(doc, from_page=pno, to_page=pno)
            out.save(output_path, garbage=4, deflate=True)
    return output_path


def rotate_pages(input_path: str, output_path: str, angle: int, pages: str | None = None) -> str:
    """Rotate pages by 90/180/270 (clockwise)."""
    if angle not in (90, 180, 270, 0, -90, -180, -270):
        raise ValueError("angle must be one of 90/180/270 (or negatives)")
    angle = angle % 360
    with fitz.open(input_path) as doc:
        targets = set(parse_pagespec(pages, doc.page_count))
        for pno in targets:
            page = doc[pno]
            page.set_rotation((page.rotation + angle) % 360)
        _ensure_parent(output_path)
        doc.save(output_path, garbage=4, deflate=True)
    return output_path


def reorder_pages(input_path: str, order: str, output_path: str) -> str:
    """Reorder pages. order like "3,1,2" (1-indexed, order preserved).

    A subset is allowed — only the listed pages are kept, in that order. Pages
    may also be repeated, which duplicates them.
    """
    with fitz.open(input_path) as doc:
        raw = parse_order(order, doc.page_count)
        _ensure_parent(output_path)
        with fitz.open() as out:
            for pno in raw:
                out.insert_pdf(doc, from_page=pno, to_page=pno)
            out.save(output_path, garbage=4, deflate=True)
    return output_path


# ---------------------------------------------------------------- compress


def compress_pdf(
    input_path: str,
    output_path: str,
    image_quality: int = 65,
    dpi: int = 150,
    garbage: int = 4,
) -> dict:
    """Reduce file size.

    Strategy (all local):
    1. Downsample + re-encode embedded raster images (JPEG quality).
    2. Save with garbage collection + deflate + clean.
    Returns dict with before/after bytes + ratio.
    """
    if not 1 <= image_quality <= 100:
        raise ValueError("image-quality must be 1-100")
    before = Path(input_path).stat().st_size
    _ensure_parent(output_path)
    with fitz.open(input_path) as doc:
        for xref in range(1, doc.xref_length()):
            try:
                if doc.xref_get_key(xref, "Subtype")[1] != "/Image":
                    continue
                pix = fitz.Pixmap(doc, xref)
                # skip masks / tiny images
                if pix.n - pix.alpha > 3 or pix.w < 32 or pix.h < 32:
                    continue
                # target max dimension from dpi heuristic (A4 @ dpi)
                max_side = int(dpi * 8.27)
                img = Image.frombytes("RGB" if pix.n < 4 else "RGBA", [pix.w, pix.h], pix.samples)
                if pix.n >= 4:
                    img = img.convert("RGB")
                scale = min(1.0, max_side / max(img.size))
                if scale < 1.0:
                    img = img.resize(
                        (int(img.width * scale), int(img.height * scale)), Image.LANCZOS
                    )
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=image_quality, optimize=True)
                doc.update_stream(xref, buf.getvalue())
            except Exception:
                continue
        doc.save(output_path, garbage=garbage, deflate=True, clean=True)
    after = Path(output_path).stat().st_size
    return {
        "output": output_path,
        "before_bytes": before,
        "after_bytes": after,
        "saved_bytes": before - after,
        "ratio": (after / before) if before else 1.0,
    }


# ---------------------------------------------------------------- convert


def images_to_pdf(image_paths: list[str], output_path: str) -> str:
    if not image_paths:
        raise ValueError("No images given")
    for f in image_paths:
        if not Path(f).exists():
            raise FileNotFoundError(f)
    _ensure_parent(output_path)
    # Pillow: first image + append rest (all RGB, A4-ish default 150dpi sizing via pixels)
    imgs: list[Image.Image] = []
    for f in image_paths:
        im = Image.open(f)
        if im.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            if im.mode == "P":
                im = im.convert("RGBA")
            if "A" in im.getbands():
                bg.paste(im, mask=im.split()[-1])
                im = bg
            else:
                im = im.convert("RGB")
        else:
            im = im.convert("RGB")
        imgs.append(im)
    imgs[0].save(output_path, save_all=True, append_images=imgs[1:])
    for im in imgs:
        try:
            im.close()
        except Exception:
            pass
    return output_path


def pdf_to_images(
    input_path: str,
    output_dir: str,
    dpi: int = 200,
    fmt: str = "png",
    pages: str | None = None,
    prefix: str = "page",
) -> list[str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(input_path).stem
    fmt = fmt.lower().lstrip(".")
    if fmt not in ("png", "jpg", "jpeg"):
        raise ValueError("format must be png or jpg")
    written: list[str] = []
    with fitz.open(input_path) as doc:
        targets = parse_pagespec(pages, doc.page_count)
        zoom = dpi / 72.0
        for pno in targets:
            page = doc[pno]
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            ext = "jpg" if fmt in ("jpg", "jpeg") else "png"
            dest = str(out_dir / f"{stem}-{prefix}-{pno + 1:03d}.{ext}")
            pix.save(dest)
            written.append(dest)
    return written


def extract_images(input_path: str, output_dir: str) -> list[str]:
    """Extract embedded raster images (no re-render)."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with fitz.open(input_path) as doc:
        for pno in range(doc.page_count):
            for img_i, img in enumerate(doc.get_page_images(pno)):
                xref = img[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n > 4:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    dest = str(out_dir / f"p{pno + 1:03d}-img{img_i}-{xref}.png")
                    pix.save(dest)
                    written.append(dest)
                except Exception:
                    continue
    return written


# ---------------------------------------------------------------- watermark / page numbers


def watermark_text(
    input_path: str,
    output_path: str,
    text: str,
    fontsize: int = 48,
    color: tuple[float, float, float] = (0.8, 0.1, 0.1),
    rotate: int = 0,
    opacity: float = 0.25,
    pages: str | None = None,
) -> str:
    if not text:
        raise ValueError("watermark text is empty")
    if int(rotate) % 90 != 0:
        raise ValueError("watermark rotate must be a multiple of 90 (0/90/180/270)")
    if not 0.0 < opacity <= 1.0:
        raise ValueError("watermark opacity must be in (0, 1]")
    _ensure_parent(output_path)
    with fitz.open(input_path) as doc:
        targets = parse_pagespec(pages, doc.page_count)
        for pno in targets:
            page = doc[pno]
            rect = page.rect
            cx, cy = rect.width / 2, rect.height / 2
            # Rough horizontal centring: the built-in fonts are proportional, so
            # estimate the text width from the size and character count.
            page.insert_text(
                fitz.Point(cx - len(text) * fontsize * 0.28, cy),
                text,
                fontsize=fontsize,
                color=color,
                rotate=rotate,
                overlay=True,
                fill_opacity=opacity,
            )
        doc.save(output_path, garbage=4, deflate=True)
    return output_path


def add_page_numbers(
    input_path: str,
    output_path: str,
    fontsize: int = 10,
    margin: int = 36,
    pages: str | None = None,
) -> str:
    _ensure_parent(output_path)
    with fitz.open(input_path) as doc:
        targets = parse_pagespec(pages, doc.page_count)
        for i in targets:
            page = doc[i]
            label = f"{i + 1} / {doc.page_count}"
            page.insert_text(
                fitz.Point(page.rect.width / 2 - 20, page.rect.height - margin),
                label,
                fontsize=fontsize,
                color=(0.4, 0.4, 0.4),
                overlay=True,
            )
        doc.save(output_path, garbage=4, deflate=True)
    return output_path


# ---------------------------------------------------------------- encrypt / decrypt


def encrypt_pdf(
    input_path: str, output_path: str, password: str, owner_password: str | None = None
) -> str:
    if not password:
        raise ValueError("password is empty")
    _ensure_parent(output_path)
    with fitz.open(input_path) as doc:
        doc.save(
            output_path,
            garbage=4,
            deflate=True,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw=password,
            owner_pw=owner_password or password,
        )
    return output_path


def decrypt_pdf(input_path: str, output_path: str, password: str) -> str:
    _ensure_parent(output_path)
    with fitz.open(input_path) as doc:
        if doc.is_encrypted:
            if not doc.authenticate(password):
                # try pypdf fallback with same password
                if _HAS_PYPDF:
                    reader = PdfReader(input_path, password=password)
                    writer = PdfWriter()
                    for pg in reader.pages:
                        writer.add_page(pg)
                    with open(output_path, "wb") as f:
                        writer.write(f)
                    return output_path
                raise ValueError("Wrong password")
        doc.save(output_path, garbage=4, deflate=True)
    return output_path


# ---------------------------------------------------------------- text


def extract_text(input_path: str, pages: str | None = None) -> str:
    with fitz.open(input_path) as doc:
        targets = parse_pagespec(pages, doc.page_count)
        return "\n".join(doc[pno].get_text("text") for pno in targets)
