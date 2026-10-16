"""AcroForm tests: create, list, fill, validate and flatten fields."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from core import forms, ops

TMP = Path(__file__).parent / "tmp"


def _base_pdf(name: str = "base.pdf", pages: int = 1) -> str:
    TMP.mkdir(exist_ok=True)
    path = TMP / name
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text(fitz.Point(72, 72), f"Form page {i + 1}")
    doc.save(str(path))
    doc.close()
    return str(path)


def _form_pdf(name: str = "form.pdf") -> str:
    base = _base_pdf(f"formsrc-{name}")
    return forms.add_form_fields(
        base,
        str(TMP / name),
        [
            {"name": "full_name", "type": "text", "page": 1, "rect": [72, 500, 300, 520]},
            {"name": "agree", "type": "checkbox", "page": 1, "rect": [72, 450, 90, 468]},
            {
                "name": "country",
                "type": "combobox",
                "page": 1,
                "rect": [72, 400, 300, 420],
                "options": ["IN", "US", "UK"],
            },
        ],
    )


def test_add_and_list_fields():
    pdf = _form_pdf("list.pdf")
    fields = forms.list_form_fields(pdf)
    assert {f["name"] for f in fields} == {"full_name", "agree", "country"}
    by_name = {f["name"]: f for f in fields}
    assert by_name["full_name"]["type"] == "text"
    assert by_name["agree"]["type"] == "checkbox"
    assert by_name["country"]["options"] == ["IN", "US", "UK"]
    assert all(f["page"] == 1 for f in fields)
    assert forms.has_form(pdf) is True
    assert forms.has_form(_base_pdf("plain.pdf")) is False


def test_fill_form_values_round_trip():
    pdf = _form_pdf("fill.pdf")
    result = forms.fill_form(
        pdf,
        str(TMP / "filled.pdf"),
        {"full_name": "Ada Lovelace", "agree": True, "country": "UK"},
    )
    assert sorted(result["filled"]) == ["agree", "country", "full_name"]
    assert result["unknown"] == []

    values = {f["name"]: f["value"] for f in forms.list_form_fields(result["output"])}
    assert values["full_name"] == "Ada Lovelace"
    assert values["country"] == "UK"
    assert str(values["agree"]).lower() not in ("", "off", "false", "none")


def test_fill_form_is_case_insensitive_and_accepts_string_booleans():
    pdf = _form_pdf("case.pdf")
    out = str(TMP / "case-filled.pdf")
    forms.fill_form(pdf, out, {"FULL_NAME": "Grace", "AGREE": "yes"})
    values = {f["name"]: f["value"] for f in forms.list_form_fields(out)}
    assert values["full_name"] == "Grace"
    assert str(values["agree"]).lower() not in ("", "off", "false", "none")


def test_fill_form_rejects_unknown_field():
    pdf = _form_pdf("unknown.pdf")
    with pytest.raises(ValueError, match="No such form field"):
        forms.fill_form(pdf, str(TMP / "nope.pdf"), {"nope": "x"})


def test_fill_form_rejects_value_outside_choices():
    pdf = _form_pdf("choices.pdf")
    with pytest.raises(ValueError, match="accepts one of"):
        forms.fill_form(pdf, str(TMP / "bad.pdf"), {"country": "Mars"})


def test_fill_form_requires_values():
    with pytest.raises(ValueError):
        forms.fill_form(_form_pdf("empty.pdf"), str(TMP / "empty-out.pdf"), {})


def test_flatten_bakes_values_and_removes_fields():
    pdf = _form_pdf("flatten.pdf")
    out = forms.flatten_form(pdf, str(TMP / "flat.pdf"))
    assert forms.list_form_fields(out) == []
    assert ops.info(out)["pages"] == 1

    filled_flat = forms.fill_form(
        pdf, str(TMP / "fill-flat.pdf"), {"full_name": "Ada"}, flatten=True
    )
    assert forms.list_form_fields(filled_flat["output"]) == []


def test_add_form_fields_validates_input():
    base = _base_pdf("validate.pdf")
    with pytest.raises(ValueError, match="Unknown field type"):
        forms.add_form_fields(
            base, str(TMP / "v1.pdf"), [{"name": "a", "type": "nope", "rect": [1, 1, 2, 2]}]
        )
    with pytest.raises(ValueError, match="rect must be"):
        forms.add_form_fields(
            base, str(TMP / "v2.pdf"), [{"name": "a", "type": "text", "rect": [1, 1]}]
        )
    with pytest.raises(ValueError, match="page out of range"):
        forms.add_form_fields(
            base,
            str(TMP / "v3.pdf"),
            [{"name": "a", "type": "text", "page": 9, "rect": [1, 1, 2, 2]}],
        )
    with pytest.raises(ValueError, match="Signature fields"):
        forms.add_form_fields(
            base, str(TMP / "v4.pdf"), [{"name": "a", "type": "signature", "rect": [1, 1, 2, 2]}]
        )
    with pytest.raises(ValueError):
        forms.add_form_fields(base, str(TMP / "v5.pdf"), [])


def test_list_form_fields_missing_file():
    with pytest.raises(FileNotFoundError):
        forms.list_form_fields(str(TMP / "does-not-exist.pdf"))
