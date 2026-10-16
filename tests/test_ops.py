"""Smoke tests for core ops. Run: pytest -q. All local, uses generated PDFs."""

from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image

from core import ops

TMP = Path(__file__).parent / "tmp"
TMP.mkdir(exist_ok=True)


def _make_pdf(path: Path, pages: int = 3, text: str = "hello") -> str:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text(fitz.Point(72, 72), f"{text} p{i + 1}")
    doc.save(str(path))
    doc.close()
    return str(path)


def test_merge_split_extract_rotate():
    a = _make_pdf(TMP / "a.pdf", 2, "A")
    b = _make_pdf(TMP / "b.pdf", 2, "B")
    merged = ops.merge([a, b], str(TMP / "merged.pdf"))
    assert ops.info(merged)["pages"] == 4

    parts = ops.split_pdf(merged, str(TMP / "split"), every=2)
    assert len(parts) == 2 and all(ops.info(p)["pages"] == 2 for p in parts)

    ext = ops.extract_pages(merged, "1,4", str(TMP / "ext.pdf"))
    assert ops.info(ext)["pages"] == 2

    dele = ops.delete_pages(merged, "1", str(TMP / "del.pdf"))
    assert ops.info(dele)["pages"] == 3

    rot = ops.rotate_pages(merged, str(TMP / "rot.pdf"), 90, "1-2")
    assert ops.info(rot)["pages"] == 4

    reo = ops.reorder_pages(merged, "4,3,2,1", str(TMP / "reo.pdf"))
    assert ops.info(reo)["pages"] == 4


def test_images_roundtrip_and_text():
    img1 = TMP / "i1.png"
    img2 = TMP / "i2.png"
    Image.new("RGB", (200, 200), (255, 0, 0)).save(img1)
    Image.new("RGB", (200, 200), (0, 0, 255)).save(img2)
    pdf = ops.images_to_pdf([str(img1), str(img2)], str(TMP / "imgs.pdf"))
    assert ops.info(pdf)["pages"] == 2
    rendered = ops.pdf_to_images(pdf, str(TMP / "render"), dpi=72)
    assert len(rendered) == 2

    src = _make_pdf(TMP / "t.pdf", 1, "searchme")
    assert "searchme" in ops.extract_text(src)


def test_encrypt_decrypt_watermark_compress():
    src = _make_pdf(TMP / "s.pdf", 2, "secret")
    enc = ops.encrypt_pdf(src, str(TMP / "enc.pdf"), "pw123")
    assert ops.info(enc)["encrypted"] is True
    dec = ops.decrypt_pdf(enc, str(TMP / "dec.pdf"), "pw123")
    assert ops.info(dec)["pages"] == 2

    wm = ops.watermark_text(src, str(TMP / "wm.pdf"), "DRAFT")
    assert ops.info(wm)["pages"] == 2

    rep = ops.compress_pdf(src, str(TMP / "small.pdf"))
    assert Path(rep["output"]).exists()

    pn = ops.add_page_numbers(src, str(TMP / "pn.pdf"))
    assert ops.info(pn)["pages"] == 2
