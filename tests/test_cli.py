"""End-to-end CLI tests: the command line is the primary user interface."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import fitz
import pytest
from PIL import Image

from cli import main
from core import forms, ocr, sign

TMP = Path(__file__).parent / "tmp" / "cli"
PASSWORD = "pw"


@pytest.fixture(scope="module")
def files() -> dict:
    TMP.mkdir(parents=True, exist_ok=True)

    base = TMP / "cli.pdf"
    doc = fitz.open()
    for i in range(3):
        doc.new_page().insert_text(fitz.Point(72, 72), f"cli fixture page {i + 1}")
    doc.save(str(base))
    doc.close()

    second = TMP / "cli-2.pdf"
    second.write_bytes(base.read_bytes())

    form = forms.add_form_fields(
        str(base),
        str(TMP / "cli-form.pdf"),
        [{"name": "full_name", "type": "text", "page": 1, "rect": [72, 500, 300, 520]}],
    )

    image = TMP / "sig.png"
    Image.new("RGBA", (200, 70), (10, 10, 10, 200)).save(image)

    pfx = ""
    if sign.signing_available():
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography.x509.oid import NameOID

        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "cli test signer")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=30))
            .sign(key, hashes.SHA256())
        )
        bundle = TMP / "cli-signer.p12"
        bundle.write_bytes(
            pkcs12.serialize_key_and_certificates(
                b"cli", key, cert, None, serialization.BestAvailableEncryption(PASSWORD.encode())
            )
        )
        pfx = str(bundle)

    return {
        "pdf": str(base),
        "pdf2": str(second),
        "form": form,
        "image": str(image),
        "pfx": pfx,
    }


def test_version_and_help_exit_cleanly(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0

    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    assert "nothing is ever uploaded" in capsys.readouterr().out


def test_capabilities_lists_backends(capsys):
    assert main(["capabilities"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["network"] == "not used"
    assert "tesseract" in payload and "libreoffice" in payload


def test_text_command_can_write_a_file(files: dict, capsys):
    target = TMP / "extracted.txt"
    assert main(["text", files["pdf"], "--pages", "1-2", "-o", str(target)]) == 0
    assert str(target) in capsys.readouterr().out
    body = target.read_text(encoding="utf-8")
    assert "cli fixture page 1" in body and "page 3" not in body


def test_form_commands_round_trip(files: dict, capsys):
    assert main(["form-fields", files["form"]]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [f["name"] for f in listed["fields"]] == ["full_name"]

    out = TMP / "cli-filled.pdf"
    assert (
        main(["fill-form", files["form"], "-o", str(out), "--set", "full_name=Ada Lovelace"]) == 0
    )
    assert json.loads(capsys.readouterr().out)["filled"] == ["full_name"]

    assert main(["form-fields", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["fields"][0]["value"] == "Ada Lovelace"

    flat = TMP / "cli-flat.pdf"
    assert main(["flatten-form", str(out), "-o", str(flat)]) == 0
    assert forms.list_form_fields(str(flat)) == []


def test_add_fields_command(files: dict, capsys):
    out = TMP / "cli-added.pdf"
    spec = json.dumps({"name": "email", "type": "text", "page": 1, "rect": [72, 400, 300, 420]})
    assert main(["add-fields", files["pdf"], "-o", str(out), "--field", spec]) == 0
    capsys.readouterr()
    assert [f["name"] for f in forms.list_form_fields(str(out))] == ["email"]


def test_pdf_to_docx_cli_writes_a_valid_docx(files: dict, capsys):
    out = TMP / "cli.docx"
    assert main(["pdf-to-docx", files["pdf"], "-o", str(out), "--engine", "builtin"]) == 0
    assert json.loads(capsys.readouterr().out)["engine"] == "builtin"
    assert out.exists() and out.stat().st_size > 0


def test_stamp_cli(files: dict, capsys):
    out = TMP / "cli-stamped.pdf"
    assert (
        main(
            [
                "stamp",
                files["pdf"],
                "-o",
                str(out),
                "--image",
                files["image"],
                "--pages",
                "1-2",
                "--width",
                "120",
                "--opacity",
                "0.6",
            ]
        )
        == 0
    )
    capsys.readouterr()
    with fitz.open(str(out)) as doc:
        assert all(len(doc[p].get_images()) >= 1 for p in range(2))


@pytest.mark.skipif(not sign.signing_available(), reason="optional signing dependency")
def test_sign_and_verify_cli(files: dict, capsys):
    signed = TMP / "cli-signed.pdf"
    assert (
        main(
            [
                "sign",
                files["pdf"],
                "-o",
                str(signed),
                "--pfx",
                files["pfx"],
                "--password",
                PASSWORD,
                "--reason",
                "Testing",
                "--box",
                "100,100,300,160",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["verify-signatures", str(signed)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["count"] == 1
    assert report["signatures"][0]["intact"] is True


@pytest.mark.skipif(not sign.signing_available(), reason="optional signing dependency")
def test_sign_cli_rejects_a_wrong_password(files: dict, capsys):
    code = main(
        [
            "sign",
            files["pdf"],
            "-o",
            str(TMP / "cli-bad.pdf"),
            "--pfx",
            files["pfx"],
            "--password",
            "nope",
        ]
    )
    assert code == 1
    assert "Could not load the certificate" in capsys.readouterr().err


@pytest.mark.skipif(ocr.tesseract_available(), reason="Tesseract is installed")
def test_ocr_cli_explains_the_missing_backend(files: dict, capsys):
    out = TMP / "cli-ocr.pdf"
    assert main(["ocr", files["pdf"], "-o", str(out), "--force"]) == 1
    assert "Tesseract is not installed" in capsys.readouterr().err


@pytest.mark.skipif(
    __import__("core.convert", fromlist=["x"]).libreoffice_available(),
    reason="LibreOffice is installed",
)
def test_docx_to_pdf_cli_explains_the_missing_backend(files: dict, capsys):
    assert main(["docx-to-pdf", files["pdf"], "-o", str(TMP / "cli-back.pdf")]) == 1
    assert "LibreOffice is not installed" in capsys.readouterr().err


def test_errors_go_to_stderr_with_a_nonzero_exit(files: dict, capsys):
    assert main(["info", str(TMP / "missing.pdf")]) == 1
    assert "error:" in capsys.readouterr().err

    assert main(["merge", files["pdf"], "-o", str(TMP / "one.pdf")]) == 1
    assert "at least 2" in capsys.readouterr().err

    assert main(["extract", files["pdf"], "--pages", "99", "-o", str(TMP / "x.pdf")]) == 1
    assert "out of range" in capsys.readouterr().err

    assert main(["fill-form", files["form"], "-o", str(TMP / "y.pdf"), "--set", "ghost=1"]) == 1
    assert "No such form field" in capsys.readouterr().err

    assert main(["fill-form", files["form"], "-o", str(TMP / "z.pdf"), "--set", "broken"]) == 1
    assert "name=value" in capsys.readouterr().err


def test_classic_commands_still_work(files: dict, capsys):
    merged = TMP / "cli-merged.pdf"
    assert main(["merge", files["pdf"], files["pdf2"], "-o", str(merged)]) == 0
    capsys.readouterr()

    assert main(["info", str(merged)]) == 0
    assert json.loads(capsys.readouterr().out)["pages"] == 6

    out_dir = TMP / "cli-split"
    assert main(["split", str(merged), "-o", str(out_dir), "--every", "3"]) == 0
    assert len([line for line in capsys.readouterr().out.splitlines() if line.strip()]) == 2

    assert main(["reorder", str(merged), "--order", "1,1", "-o", str(TMP / "cli-reo.pdf")]) == 0
    capsys.readouterr()
    assert __import__("core.ops", fromlist=["x"]).info(str(TMP / "cli-reo.pdf"))["pages"] == 2
