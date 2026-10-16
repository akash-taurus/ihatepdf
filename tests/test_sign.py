"""Signing and stamping tests.

Signing needs the optional pyHanko dependency; these tests are skipped when it
is absent (as in the lean CI matrix) and run in full when it is installed. A
throwaway self-signed certificate is generated per test session, so no key
material is ever committed.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import fitz
import pytest
from PIL import Image

from core import forms, ops, sign

pytest.importorskip("pyhanko", reason="optional signing dependency")
pytest.importorskip("cryptography", reason="needed to build a test certificate")

TMP = Path(__file__).parent / "tmp"
PASSWORD = "test-password"


@pytest.fixture(scope="module")
def pfx() -> str:
    """A self-signed PKCS#12 bundle, generated locally and never committed."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    TMP.mkdir(exist_ok=True)
    path = TMP / "test-signer.p12"
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ihatepdf test signer")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    # The bundle must be password-encrypted: an unencrypted PKCS#12 has no
    # usable MAC, so loading it with a passphrase fails.
    path.write_bytes(
        pkcs12.serialize_key_and_certificates(
            b"ihatepdf test",
            key,
            cert,
            None,
            serialization.BestAvailableEncryption(PASSWORD.encode()),
        )
    )
    return str(path)


def _pdf(name: str = "signable.pdf", pages: int = 1) -> str:
    TMP.mkdir(exist_ok=True)
    path = TMP / name
    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text(fitz.Point(72, 72), f"Contract page {i + 1}")
    doc.save(str(path))
    doc.close()
    return str(path)


def test_signing_dependency_is_reported_available():
    assert sign.signing_available() is True


def test_sign_then_verify_is_intact(pfx):
    src = _pdf()
    out = str(TMP / "signed.pdf")
    result = sign.sign_pdf(src, out, pfx, PASSWORD, reason="Approval", location="Pune")
    assert result["output"] == out
    assert "ihatepdf test signer" in result["signer"]
    assert result["timestamped"] is False

    verifications = sign.verify_signatures(out)
    assert len(verifications) == 1
    assert verifications[0]["intact"] is True
    assert verifications[0]["field"] == "Signature"


def test_signature_is_visible_when_a_box_is_given(pfx):
    src = _pdf("boxed.pdf")
    out = str(TMP / "boxed-signed.pdf")
    box = [100, 100, 300, 160]
    sign.sign_pdf(src, out, pfx, PASSWORD, field_name="Approval", page=1, box=box)

    fields = forms.list_form_fields(out)
    assert len(fields) == 1
    assert fields[0]["name"] == "Approval"
    assert fields[0]["type"] == "signature"
    assert fields[0]["page"] == 1
    assert fields[0]["rect"] == pytest.approx(box, abs=1)


def test_signatures_survive_page_structure(pfx):
    src = _pdf("multi.pdf", pages=3)
    out = str(TMP / "multi-signed.pdf")
    sign.sign_pdf(src, out, pfx, PASSWORD)
    assert ops.info(out)["pages"] == 3
    assert sign.verify_signatures(out)[0]["intact"] is True


def test_stamp_then_sign_is_intact(pfx):
    """The documented workflow for a visual signature must verify cleanly."""
    src = _pdf("visual.pdf")
    stamped = str(TMP / "visual-stamped.pdf")
    sign.stamp_image(src, stamped, _signature_png("sig6.png"), width=140)

    signed = str(TMP / "visual-signed.pdf")
    sign.sign_pdf(stamped, signed, pfx, PASSWORD, box=[320, 640, 520, 700])

    verifications = sign.verify_signatures(signed)
    assert len(verifications) == 1
    assert verifications[0]["intact"] is True
    with fitz.open(signed) as doc:
        assert len(doc[0].get_images()) >= 1  # the visible stamp survived


def test_signing_rejects_bad_credentials(pfx):
    src = _pdf("creds.pdf")
    with pytest.raises(ValueError, match="Could not load the certificate"):
        sign.sign_pdf(src, str(TMP / "bad-pw.pdf"), pfx, "wrong-password")
    with pytest.raises(ValueError, match="password is empty"):
        sign.sign_pdf(src, str(TMP / "no-pw.pdf"), pfx, "")
    with pytest.raises(FileNotFoundError):
        sign.sign_pdf(src, str(TMP / "no-cert.pdf"), str(TMP / "missing.p12"), PASSWORD)


def test_signing_validates_box_and_page(pfx):
    src = _pdf("badbox.pdf")
    with pytest.raises(ValueError, match="box must be"):
        sign.sign_pdf(src, str(TMP / "badbox-out.pdf"), pfx, PASSWORD, box=[1, 2, 3])
    with pytest.raises(ValueError, match="out of range"):
        sign.sign_pdf(src, str(TMP / "badpage.pdf"), pfx, PASSWORD, page=99, box=[1, 2, 3, 4])


def test_verify_reports_nothing_for_unsigned_documents():
    assert sign.verify_signatures(_pdf("unsigned.pdf")) == []


def test_tampering_after_signing_is_detected(pfx):
    src = _pdf("tamper.pdf")
    signed = str(TMP / "tamper-signed.pdf")
    sign.sign_pdf(src, signed, pfx, PASSWORD)

    with fitz.open(signed) as doc:
        doc.new_page().insert_text(fitz.Point(72, 72), "inserted after signing")
        doc.save(str(TMP / "tampered.pdf"))

    verifications = sign.verify_signatures(str(TMP / "tampered.pdf"))
    assert all(entry.get("intact") is False for entry in verifications)


def _signature_png(name: str = "signature.png") -> str:
    TMP.mkdir(exist_ok=True)
    path = TMP / name
    Image.new("RGBA", (240, 80), (10, 10, 10, 200)).save(path)
    return str(path)


def test_stamp_image_places_an_image():
    src = _pdf("stamp.pdf")
    out = str(TMP / "stamped.pdf")
    sign.stamp_image(src, out, _signature_png(), width=140)

    with fitz.open(out) as doc:
        assert len(doc[0].get_images()) >= 1
    assert ops.info(out)["pages"] == 1


def test_stamp_image_placement_is_top_left_anchored():
    src = _pdf("stamp-place.pdf")
    out = str(TMP / "stamp-placed.pdf")
    sign.stamp_image(src, out, _signature_png("sig4.png"), x=100, y=200, width=140)

    with fitz.open(out) as doc:
        page = doc[0]
        images = page.get_images()
        assert images, "the stamp should be embedded on the page"
        rects = page.get_image_rects(images[0][0])
    assert rects
    assert rects[0].x0 == pytest.approx(100, abs=1)
    assert rects[0].y0 == pytest.approx(200, abs=1)
    assert rects[0].width == pytest.approx(140, abs=1)


def test_stamp_image_defaults_to_the_bottom_right():
    src = _pdf("stamp-corner.pdf")
    out = str(TMP / "stamp-corner-out.pdf")
    sign.stamp_image(src, out, _signature_png("sig5.png"), width=140)

    with fitz.open(out) as doc:
        page = doc[0]
        rects = page.get_image_rects(page.get_images()[0][0])
        page_w, page_h = page.rect.width, page.rect.height
    assert rects[0].x1 == pytest.approx(page_w - 36, abs=1)
    assert rects[0].y1 == pytest.approx(page_h - 36, abs=1)


def test_stamp_image_supports_opacity_and_multiple_pages():
    src = _pdf("stamp-multi.pdf", pages=2)
    out = str(TMP / "stamped-multi.pdf")
    sign.stamp_image(src, out, _signature_png("sig2.png"), pages="1-2", opacity=0.45)
    with fitz.open(out) as doc:
        assert all(len(doc[p].get_images()) >= 1 for p in range(doc.page_count))


def test_stamp_image_validates_arguments():
    src = _pdf("stamp-bad.pdf")
    png = _signature_png("sig3.png")
    with pytest.raises(ValueError, match="opacity"):
        sign.stamp_image(src, str(TMP / "o.pdf"), png, opacity=0)
    with pytest.raises(ValueError, match="out of range"):
        sign.stamp_image(src, str(TMP / "p.pdf"), png, page=7)
    with pytest.raises(FileNotFoundError):
        sign.stamp_image(src, str(TMP / "m.pdf"), str(TMP / "no.png"))
    with pytest.raises(FileNotFoundError):
        sign.stamp_image(str(TMP / "no-src.pdf"), str(TMP / "m2.pdf"), png)
