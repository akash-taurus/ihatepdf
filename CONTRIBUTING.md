# Contributing

Thanks for taking a look at ihatepdf. Bug reports and pull requests are welcome.

## Ground rules

- **Everything stays local.** No feature may upload a document, call a network
  API, or add telemetry. The single exception is already in the code: signing
  with an explicit RFC 3161 timestamp URL. OCR, forms, signing and conversion
  all run offline.
- **`core/` is the product.** PDF logic belongs in a `core/` module, never in
  the GUI or the CLI. Both front ends are thin wrappers over the same functions,
  so one fix lands in both.
- **Prefer PyMuPDF (fitz)** for new operations; reach for pypdf only when
  PyMuPDF cannot do the job, and Pillow for raster work.
- **Optional backends stay optional.** Tesseract, LibreOffice and pyHanko are
  detected at run time, never required. A missing backend must raise an
  actionable `RuntimeError` (patched tests rely on the wording) and show up in
  `capabilities` and the GUI's `⚠` markers.

## Development setup

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements-dev.txt          # black + runtime deps
pip install -r requirements-optional.txt     # optional: exercises signing tests
```

To try the GUI headlessly (CI does this):

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_gui.py
```

## Adding a feature

1. **Core** — add the operation to the right module and validate its arguments
   with `ValueError`/`FileNotFoundError` so both front ends report clearly.
2. **CLI** — add a subparser in `build_parser()` and a handler to `HANDLERS` in
   `cli.py`. Handlers just call core and return a value; `_print_result` handles
   printing (strings, path lists, or JSON).
3. **Desktop** — add a `Tool(...)` entry in `app/tools.py`. If it needs new
   options, add the field to `FIELD_DEFS` in `app/main.py` too. No Qt code goes
   in `app/tools.py`: that is what keeps the whole catalogue testable without a
   display.
4. **Tests** — add a case to the matching file in `tests/`. Core behaviour goes
   in a core test, the tool wiring is picked up automatically by
   `tests/test_app_tools.py` (it iterates the catalogue), and user-facing
   commands get a line in `tests/test_cli.py`.
5. **Docs** — update the feature and command tables in `README.md`, and tick the
   roadmap item if you closed one.

## Before opening a pull request

```bash
black .        # formatting (line length 100, configured in pyproject.toml)
pytest -q      # tests must pass
```

Tests generate their own PDFs, images and certificates in `tests/tmp/`
(git-ignored), so nothing binary is ever committed. Tests that need an optional
backend use `skipif`/`importorskip` so the lean matrix keeps working.

CI runs three jobs: `core` (Windows + Linux, Python 3.11/3.13), `optional`
(pyHanko signing exercised for real) and `desktop` (PySide6, offscreen). Keep
all three green.

## Reporting bugs

Include the command you ran (or the tool selected in the GUI), the expected
result, and the actual result or traceback, plus the output of
`python cli.py capabilities`. If it is reproducible, mention the PDF's page
count and whether it is encrypted, signed, scanned, or form-based — those four
properties account for most edge cases.
