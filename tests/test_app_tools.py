"""Every desktop-app tool, exercised without a display.

``app.tools`` deliberately holds no Qt code, so each tool can be run against a
:class:`Ctx` directly. That keeps the GUI's behaviour verified in the lean CI
matrix, where PySide6 is not installed.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import fitz
import pytest
from PIL import Image

from app import tools
from core import convert, ocr, ops

TMP = Path(__file__).parent / "tmp" / "app-tools"


@pytest.fixture(scope="module")
def fixtures() -> dict:
    """Base documents, a form, images and a certificate used by the tools."""
    TMP.mkdir(parents=True, exist_ok=True)

    png = TMP / "logo.png"
    Image.new("RGBA", (120, 60), (200, 40, 40, 220)).save(png)
    png2 = TMP / "photo.png"
    Image.new("RGB", (300, 200), (30, 90, 200)).save(png2)

    base = TMP / "base.pdf"
    doc = fitz.open()
    for i in range(2):
        page = doc.new_page()
        page.insert_text(fitz.Point(72, 72), f"ihatepdf fixture page {i + 1}")
    doc[0].insert_image(fitz.Rect(72, 200, 200, 260), filename=str(png2))
    doc.save(str(base))
    doc.close()

    form = TMP / "form.pdf"
    doc = fitz.open(str(base))
    doc.save(str(form))
    doc.close()
    from core import forms

    form_path = forms.add_form_fields(
        str(form),
        str(TMP / "form-fields.pdf"),
        [{"name": "full_name", "type": "text", "page": 1, "rect": [72, 500, 300, 520]}],
    )

    # Always provide a bundle path: with pyHanko installed this is a real
    # certificate, without it a placeholder file that lets the tool reach the
    # "optional dependency missing" error the tests assert on.
    bundle = TMP / "signer.p12"
    if tools.sign.signing_available():
        pfx = _make_certificate(bundle)
    else:
        bundle.write_bytes(b"placeholder for a missing optional dependency")
        pfx = str(bundle)

    copy = TMP / "base-copy.pdf"
    copy.write_bytes(base.read_bytes())

    # A real Word document for the DOCX -> PDF tool (the builtin writer makes
    # one without needing LibreOffice installed at fixture time).
    docx = convert.pdf_to_docx(str(base), str(TMP / "base.docx"), engine="builtin")

    return {
        "pdf": str(base),
        "pdf2": str(copy),
        "docx": docx["output"],
        "form": form_path,
        "png": str(png),
        "png2": str(png2),
        "pfx": pfx,
        "dir": str(TMP),
    }


def _make_certificate(path: Path, password: str = "pw") -> str:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "app tools signer")])
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
    path.write_bytes(
        pkcs12.serialize_key_and_certificates(
            b"app tools", key, cert, None, serialization.BestAvailableEncryption(password.encode())
        )
    )
    return str(path)


#: A sensible value for every option field the tools can show.
FIELD_VALUES: dict[str, object] = {
    "pages": "1",
    "ranges": "",
    "every": 0,
    "angle": 90,
    "order": "2,1",
    "quality": 60,
    "dpi": 100,
    "format": "png",
    "text": "DRAFT",
    "fontsize": 40,
    "opacity": 0.5,
    "password": "pw",
    "language": "eng",
    "engine": "builtin",
    "force": False,
    "flatten": False,
    "values": "full_name=Ada Lovelace",
    "fields": '[{"name": "added", "type": "text", "page": 1, "rect": [72, 300, 300, 320]}]',
    "reason": "Approval",
    "location": "Pune",
    "page": 1,
    "box": "",
    "width": 120,
    "x": "",
    "y": "",
    # File-picker fields: real paths are injected from the fixtures below.
    "pfx": "",
    "pfx_password": "",
    "image": "",
}

#: Tools whose input must be a form document.
FORM_TOOLS = {"List form fields", "Fill form", "Flatten form"}

#: Tools replaced by a capability error when the optional backend is missing.
#: These must line up with app.tools.requirements_met().
NEEDS = {
    "OCR (searchable PDF)": "Tesseract",
    "OCR to text": "Tesseract",
    "DOCX to PDF": "LibreOffice",
    "Sign (PKCS#12)": "pyHanko",
    "Verify signatures": "pyHanko",
}


def _ctx_for(tool: tools.Tool, fixtures: dict, out_dir: Path) -> tools.Ctx:
    values = {fid: FIELD_VALUES[fid] for fid in tool.fields if fid in FIELD_VALUES}
    if "pfx" in tool.fields:
        values["pfx"] = fixtures["pfx"]
        values["pfx_password"] = "pw"
    if "image" in tool.fields:
        values["image"] = fixtures["png"]
    if tool.label == "OCR (searchable PDF)":
        # The fixture already has a text layer, so force the OCR path; the
        # skip behaviour is covered separately below.
        values["force"] = True

    inputs = [fixtures["form"] if tool.label in FORM_TOOLS else fixtures["pdf"]]
    if tool.label == "DOCX to PDF":
        inputs = [fixtures["docx"]]
    if tool.label in tools.MULTI_INPUT:
        inputs = (
            [fixtures["png"], fixtures["png2"]]
            if tool.label == "Images to PDF"
            else [fixtures["pdf"], fixtures["pdf2"]]
        )

    if tool.output == "none":
        out = None
    elif tool.output == "dir":
        out = str(out_dir / tool.label.lower().replace(" ", "-"))
    else:
        suffix = {"docx": ".docx", "txt": ".txt"}.get(tool.output, ".pdf")
        out = str(out_dir / f"{tool.label.lower().replace(' ', '-')}{suffix}")
    return tools.Ctx(inputs=inputs, out=out, values=values)


def test_every_tool_is_described_and_unique():
    labels = [tool.label for tool in tools.TOOLS]
    assert len(labels) == len(set(labels))
    for tool in tools.TOOLS:
        assert tool.output in {"file", "dir", "txt", "docx", "none"}, tool.label
        for field_id in tool.fields:
            assert field_id in FIELD_VALUES, f"{tool.label} uses unknown field {field_id}"


def test_backend_requirements_match_the_tool_expectations(monkeypatch):
    """A tool must not need a backend that NEEDS in this file does not declare."""
    backends = ("Tesseract", "LibreOffice", "pyHanko")

    def pretend_only(present: set[str]) -> None:
        monkeypatch.setattr(
            tools.ocr, "tesseract_available", lambda *a, **k: "Tesseract" in present
        )
        monkeypatch.setattr(
            tools.convert, "libreoffice_available", lambda: "LibreOffice" in present
        )
        monkeypatch.setattr(tools.sign, "signing_available", lambda: "pyHanko" in present)

    for tool in tools.TOOLS:
        for missing_backend in backends:
            pretend_only({b for b in backends if b != missing_backend})
            available, _reason = tools.requirements_met(tool.label)
            expected = NEEDS.get(tool.label) != missing_backend
            assert available is expected, (
                f"{tool.label} with {missing_backend} unavailable: "
                f"requirements_met()={available}, expected {expected}"
            )


def _backend_missing(label: str) -> bool:
    """Is the optional backend this tool needs absent on this machine?"""
    if label not in NEEDS:
        return False
    return {
        "Tesseract": not ocr.tesseract_available(),
        "LibreOffice": not tools.convert.libreoffice_available(),
        "pyHanko": not tools.sign.signing_available(),
    }[NEEDS[label]]


@pytest.mark.parametrize("tool", tools.TOOLS, ids=lambda t: t.label)
def test_tool_runs_and_produces_output(tool: tools.Tool, fixtures: dict, tmp_path: Path):
    if _backend_missing(tool.label):
        # Missing backends must surface as a clear error, never a silent no-op.
        with pytest.raises(RuntimeError, match=NEEDS[tool.label]):
            tool.run(_ctx_for(tool, fixtures, tmp_path))
        return
    ctx = _ctx_for(tool, fixtures, tmp_path)
    result = tool.run(ctx)

    assert result is not None, f"{tool.label} returned nothing"
    if tool.output == "dir":
        assert Path(ctx.out).is_dir()
        assert sorted(Path(ctx.out).iterdir()), f"{tool.label} wrote no files"
    elif tool.output == "file":
        assert Path(ctx.out).exists(), f"{tool.label} wrote no output"
    if tool.label == "Extract text":
        assert "ihatepdf fixture" in Path(ctx.out).read_text(encoding="utf-8")
    if tool.label == "Info":
        assert result["pages"] == 2


def test_ocr_tool_skips_pages_that_already_have_text(fixtures: dict, tmp_path: Path):
    """Digital pages must not require Tesseract at all."""
    tool = next(t for t in tools.TOOLS if t.label == "OCR (searchable PDF)")
    ctx = _ctx_for(tool, fixtures, tmp_path)
    ctx.values["force"] = False
    ctx.values["pages"] = ""  # every page
    result = tool.run(ctx)
    assert result["pages_skipped"] == 2
    assert result["pages_processed"] == 0
    assert Path(result["output"]).exists()


def test_reorder_tool_prefers_the_thumbnail_order(fixtures: dict, tmp_path: Path):
    tool = next(t for t in tools.TOOLS if t.label == "Reorder pages")
    ctx = _ctx_for(tool, fixtures, tmp_path)
    ctx.order = [2, 1, 1]  # as arranged in the thumbnails tab
    out = tool.run(ctx)
    assert ops.info(out)["pages"] == 3


def test_fill_form_tool_flattens_when_asked(fixtures: dict, tmp_path: Path):
    from core import forms

    tool = next(t for t in tools.TOOLS if t.label == "Fill form")
    ctx = _ctx_for(tool, fixtures, tmp_path)
    ctx.values["flatten"] = True
    result = tool.run(ctx)
    assert result["filled"] == ["full_name"]
    assert forms.list_form_fields(result["output"]) == []


def test_tools_validate_their_options(fixtures: dict, tmp_path: Path):
    def run_tool(label: str, **values):
        tool = next(t for t in tools.TOOLS if t.label == label)
        ctx = _ctx_for(tool, fixtures, tmp_path)
        ctx.values.update(values)
        return tool.run(ctx)

    with pytest.raises(ValueError, match="either"):
        run_tool("Split PDF", ranges="1-2", every=2)
    with pytest.raises(ValueError, match="watermark text"):
        run_tool("Watermark", text="  ")
    with pytest.raises(ValueError, match="at least one name=value"):
        run_tool("Fill form", values="")
    with pytest.raises(ValueError, match="four numbers"):
        run_tool("Sign (PKCS#12)", pfx=fixtures["pfx"], box="1 2 3")
    with pytest.raises(ValueError, match="image to stamp"):
        run_tool("Stamp image", image="")
    with pytest.raises(ValueError, match="page order"):
        run_tool("Reorder pages", order="")


def test_missing_pyhanko_surfaces_the_install_hint(monkeypatch, fixtures: dict, tmp_path: Path):
    """The no-pyHanko path (as in the lean CI job) must explain itself."""
    tool = next(t for t in tools.TOOLS if t.label == "Sign (PKCS#12)")
    ctx = _ctx_for(tool, fixtures, tmp_path)

    def boom():
        raise RuntimeError(tools.sign.INSTALL_HINT)

    monkeypatch.setattr(tools.sign, "_require_pyhanko", boom)
    with pytest.raises(RuntimeError, match="pyHanko"):
        tool.run(ctx)


@pytest.mark.skipif(not tools.sign.signing_available(), reason="optional signing dependency")
def test_sign_tool_rejects_a_bad_box(fixtures: dict, tmp_path: Path):
    tool = next(t for t in tools.TOOLS if t.label == "Sign (PKCS#12)")
    ctx = _ctx_for(tool, fixtures, tmp_path)
    ctx.values["box"] = "10 20 30"
    with pytest.raises(ValueError, match="four numbers"):
        tool.run(ctx)


def test_parse_pairs_and_json_fields():
    parsed = tools.parse_pairs("a=1\n\n# comment\nb = two ")
    assert parsed == {"a": "1", "b": "two"}
    with pytest.raises(ValueError, match="name=value"):
        tools.parse_pairs("nonsense")
    assert tools.parse_json_fields('[{"name": "a"}]') == [{"name": "a"}]
    with pytest.raises(ValueError, match="array"):
        tools.parse_json_fields('{"name": "a"}')
    with pytest.raises(ValueError, match="invalid"):
        tools.parse_json_fields("{oops}")
    with pytest.raises(ValueError, match="Paste a JSON array"):
        tools.parse_json_fields("")


def test_missing_backends_are_reported(monkeypatch):
    monkeypatch.setattr(tools.ocr, "tesseract_available", lambda *a, **k: False)
    monkeypatch.setattr(tools.convert, "libreoffice_available", lambda: False)
    monkeypatch.setattr(tools.sign, "signing_available", lambda: False)

    missing = tools.unavailable_tools()
    assert "Tesseract" in missing["OCR (searchable PDF)"]
    assert "LibreOffice" in missing["DOCX to PDF"]
    assert "pyHanko" in missing["Sign (PKCS#12)"]
    assert "Verify signatures" in missing
    assert "Merge PDFs" not in missing
    assert tools.requirements_met("Merge PDFs") == (True, "")


def test_backend_checks_pass_when_everything_is_present(monkeypatch):
    monkeypatch.setattr(tools.ocr, "tesseract_available", lambda *a, **k: True)
    monkeypatch.setattr(tools.convert, "libreoffice_available", lambda: True)
    monkeypatch.setattr(tools.sign, "signing_available", lambda: True)
    assert tools.unavailable_tools() == {}


def test_fallbacks_when_no_output_path_is_given(fixtures: dict, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # default names land in the working directory

    compress = next(t for t in tools.TOOLS if t.label == "Compress")
    result = compress.run(tools.Ctx(inputs=[fixtures["pdf"]], out=None, values={}))
    assert Path(result["output"]).name == "compressed.pdf"
    assert Path(result["output"]).exists()

    text_tool = next(t for t in tools.TOOLS if t.label == "Extract text")
    assert "ihatepdf fixture" in text_tool.run(
        tools.Ctx(inputs=[fixtures["pdf"]], out=None, values={})
    )
