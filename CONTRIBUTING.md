# Contributing

Thanks for taking a look at ihatepdf. Bug reports and pull requests are welcome.

## Ground rules

- **Everything stays local.** No feature may upload a document, call a network
  API, or add telemetry. OCR / conversion backends must be fully offline.
- **`core/ops.py` stays UI-agnostic.** The desktop app and the CLI are thin
  wrappers; new functionality belongs in `core/`, then gets wired to both.
- Prefer PyMuPDF (fitz) for new operations; reach for pypdf only when PyMuPDF
  cannot do the job.

## Development setup

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Before opening a pull request

```bash
black .        # formatting (line length 100, configured in pyproject.toml)
pytest -q      # tests must pass
```

Tests live in `tests/` and generate their own PDFs/images in `tests/tmp/`
(git-ignored), so no fixtures need to be committed. Please add a test for any
new operation in `core/ops.py`.

## Reporting bugs

Include the command you ran (or the tool selected in the GUI), the expected
result, and the actual result or traceback. If it is reproducible, mention the
PDF's page count and whether it is encrypted, signed, or scanned — those three
properties account for most edge cases.
