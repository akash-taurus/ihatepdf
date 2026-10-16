"""AcroForm support: inspect, fill, create, and flatten form fields.

Uses PyMuPDF's widget API exclusively, so no external dependency and no
network access are involved. All operations are local.
"""

from __future__ import annotations

from pathlib import Path

import fitz

from .ops import _ensure_parent

#: Friendly names for the PDF widget types we can create and fill.
FIELD_TYPES: dict[str, int] = {
    "text": fitz.PDF_WIDGET_TYPE_TEXT,
    "checkbox": fitz.PDF_WIDGET_TYPE_CHECKBOX,
    "combobox": fitz.PDF_WIDGET_TYPE_COMBOBOX,
    "listbox": fitz.PDF_WIDGET_TYPE_LISTBOX,
    "radio": fitz.PDF_WIDGET_TYPE_RADIOBUTTON,
    "button": fitz.PDF_WIDGET_TYPE_BUTTON,
    "signature": fitz.PDF_WIDGET_TYPE_SIGNATURE,
}

#: Strings we accept as "checked" for a checkbox/radio field.
_TRUE = {"1", "true", "yes", "on", "x", "checked"}


def _type_name(widget: fitz.Widget) -> str:
    try:
        return str(widget.field_type_string).lower()
    except Exception:  # pragma: no cover - defensive
        for name, code in FIELD_TYPES.items():
            if widget.field_type == code:
                return name
        return "unknown"


def _is_readonly(widget: fitz.Widget) -> bool:
    try:
        return bool(widget.field_flags & fitz.PDF_FIELD_IS_READ_ONLY)
    except Exception:  # pragma: no cover - defensive
        return False


def _is_required(widget: fitz.Widget) -> bool:
    try:
        return bool(widget.field_flags & fitz.PDF_FIELD_IS_REQUIRED)
    except Exception:  # pragma: no cover - defensive
        return False


def _choices(widget: fitz.Widget) -> list[str]:
    try:
        return [str(c) for c in (widget.choice_values or [])]
    except Exception:  # pragma: no cover - defensive
        return []


def _coerce(value):
    """Normalise a checkbox/radio value to the widget's 'on' state or 'Off'."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return "On" if value.strip().lower() in _TRUE else "Off"
    return value


def list_form_fields(input_path: str) -> list[dict]:
    """Return one dict per form field, in page order.

    Each dict has: ``page`` (1-indexed), ``name``, ``type``, ``value``,
    ``options``, ``read_only``, ``required``, ``max_length`` and ``rect``.
    """
    if not Path(input_path).exists():
        raise FileNotFoundError(input_path)
    fields: list[dict] = []
    with fitz.open(input_path) as doc:
        for pno in range(doc.page_count):
            for widget in doc[pno].widgets():
                r = widget.rect
                fields.append(
                    {
                        "page": pno + 1,
                        "name": widget.field_name or "",
                        "type": _type_name(widget),
                        "value": widget.field_value,
                        "options": _choices(widget),
                        "read_only": _is_readonly(widget),
                        "required": _is_required(widget),
                        "max_length": getattr(widget, "text_maxlen", 0) or 0,
                        "rect": [round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)],
                    }
                )
    return fields


def has_form(input_path: str) -> bool:
    """True if the document contains any AcroForm fields."""
    with fitz.open(input_path) as doc:
        return bool(doc.is_form_pdf) or any(
            doc[pno].first_widget is not None for pno in range(doc.page_count)
        )


def fill_form(
    input_path: str,
    output_path: str,
    values: dict,
    flatten: bool = False,
    strict: bool = True,
) -> dict:
    """Fill form fields by name.

    Args:
        values: ``{field_name: value}``. Booleans (or "yes"/"on"/"x") check
            checkboxes and radio buttons. Names are matched case-insensitively.
        flatten: bake the filled fields into the page content and remove the
            interactive form (good for final documents).
        strict: raise if a supplied name matches no field; otherwise report it
            in the result under ``unknown``.

    Returns:
        ``{"output", "filled", "unknown", "skipped", "pages"}``.
    """
    if not values:
        raise ValueError("No field values given")
    _ensure_parent(output_path)
    wanted = {str(k).strip().lower(): v for k, v in values.items()}
    filled: list[str] = []
    skipped: list[str] = []
    with fitz.open(input_path) as doc:
        for pno in range(doc.page_count):
            for widget in doc[pno].widgets():
                name = (widget.field_name or "").strip()
                key = name.lower()
                if key not in wanted:
                    continue
                if _is_readonly(widget):
                    skipped.append(name or f"page {pno + 1}")
                    continue
                value = wanted.pop(key)
                if _type_name(widget) in ("checkbox", "radio", "button"):
                    value = _coerce(value)
                    if value in ("On", -1, True) and hasattr(widget, "on_state"):
                        value = widget.on_state() or "Yes"
                    widget.field_value = value
                else:
                    options = _choices(widget)
                    text = "" if value is None else str(value)
                    if options and text and text not in options:
                        raise ValueError(f"Field {name!r} accepts one of {options}, got {text!r}")
                    widget.field_value = text
                widget.update()
                filled.append(name)
        unknown = sorted(wanted) if wanted else []
        if strict and unknown:
            raise ValueError(
                "No such form field(s): " + ", ".join(unknown) + " — run 'form-fields' to list them"
            )
        if flatten:
            doc.bake(annots=True, widgets=True)
        elif filled:
            # Ask viewers to render widget appearances from the field values.
            doc.need_appearances = True
        pages = doc.page_count
        doc.save(output_path, garbage=4, deflate=True)
    return {
        "output": output_path,
        "filled": filled,
        "unknown": unknown,
        "skipped": skipped,
        "pages": pages,
    }


def flatten_form(input_path: str, output_path: str) -> str:
    """Make form field values permanent page content and drop the fields."""
    _ensure_parent(output_path)
    with fitz.open(input_path) as doc:
        doc.bake(annots=True, widgets=True)
        doc.save(output_path, garbage=4, deflate=True)
    return output_path


def add_form_fields(input_path: str, output_path: str, fields: list[dict]) -> str:
    """Add form fields to a PDF.

    ``fields`` is a list of dicts:

    ``{"name": "full_name", "type": "text", "page": 1,
       "rect": [x0, y0, x1, y1], "value": "", "options": [...],
       "fontsize": 11, "required": False, "tooltip": "..."}``

    ``type`` is one of ``text``, ``checkbox``, ``combobox``, ``listbox``,
    ``radio``.
    """
    if not fields:
        raise ValueError("No fields given")
    _ensure_parent(output_path)
    with fitz.open(input_path) as doc:
        for spec in fields:
            kind = str(spec.get("type", "text")).lower()
            if kind not in FIELD_TYPES:
                raise ValueError(f"Unknown field type {kind!r} — use one of {sorted(FIELD_TYPES)}")
            if kind == "signature":
                raise ValueError("Signature fields are created by the 'sign' command")
            pno = int(spec.get("page", 1)) - 1
            if not 0 <= pno < doc.page_count:
                raise ValueError(f"Field {spec.get('name')!r}: page out of range")
            rect = spec.get("rect")
            if not rect or len(rect) != 4:
                raise ValueError(f"Field {spec.get('name')!r}: rect must be [x0, y0, x1, y1]")
            # Every property must be set on the widget *before* it is added to
            # the page: add_widget writes the PDF objects from the object's
            # current state.
            widget = fitz.Widget()
            widget.field_name = str(spec["name"])
            widget.field_type = FIELD_TYPES[kind]
            widget.rect = fitz.Rect(*[float(v) for v in rect])
            widget.field_value = spec.get("value", "")
            if spec.get("fontsize"):
                widget.text_fontsize = float(spec["fontsize"])
            if spec.get("options"):
                widget.choice_values = [str(o) for o in spec["options"]]
            if spec.get("max_length"):
                widget.text_maxlen = int(spec["max_length"])
            if spec.get("tooltip"):
                widget.field_label = str(spec["tooltip"])
            flags = 0
            if spec.get("multi_line") and kind == "text":
                flags |= fitz.PDF_TX_FIELD_IS_MULTILINE
            if spec.get("required"):
                flags |= fitz.PDF_FIELD_IS_REQUIRED
            if flags:
                widget.field_flags = flags
            # The returned annotation is live; the Python Widget object is not
            # bound to the page, so it must not be updated afterwards.
            doc[pno].add_widget(widget)
        doc.need_appearances = True
        doc.save(output_path, garbage=4, deflate=True)
    return output_path
