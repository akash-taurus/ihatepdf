# ihatepdf

[![CI](https://github.com/akash-taurus/ihatepdf/actions/workflows/ci.yml/badge.svg)](https://github.com/akash-taurus/ihatepdf/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-4c566a)](#install)
[![Offline](https://img.shields.io/badge/network-100%25%20offline-success)](SECURITY.md)
[![Tests](https://img.shields.io/badge/tests-131%20passing-brightgreen)](#development)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

**A local-first PDF toolkit for the things you actually do to PDFs** — merge,
split, extract, rotate, reorder by thumbnail, compress, watermark, page-number,
encrypt, OCR, sign, fill and flatten forms, convert to DOCX or images — with a
desktop GUI and a scriptable CLI over the same core.

No account, no upload, no page limits, no "sign up to download". Your documents
never leave the machine.

---

## Contents

- [Why](#why)
- [Features](#features)
- [Install](#install)
- [Desktop app](#desktop-app)
- [CLI](#cli)
- [Page specs](#page-specs)
- [OCR](#ocr)
- [Forms](#forms)
- [Digital signatures](#digital-signatures)
- [Conversion](#conversion)
- [Project layout](#project-layout)
- [Design notes](#design-notes)
- [Packaging a Windows `.exe`](#packaging-a-windows-exe)
- [Development](#development)
- [Privacy](#privacy)
- [Roadmap](#roadmap)
- [License](#license)

## Why

Most "free online PDF" sites ask you to upload a contract, a bank statement, or
a passport scan to a server you know nothing about, then paywall the download.
ihatepdf does the same jobs locally: PyMuPDF and Pillow do the work in-process,
so processing is free, offline, and inspectable.

## Features

| Operation | CLI | GUI | Notes |
| --- | :-: | :-: | --- |
| Merge PDFs | ✅ | ✅ | keeps input order |
| Split | ✅ | ✅ | one file per page, fixed chunks (`--every N`), or custom groups |
| Extract pages | ✅ | ✅ | non-destructive copy |
| Delete pages | ✅ | ✅ | refuses to delete every page |
| Rotate | ✅ | ✅ | 90° / 180° / 270°, per page or whole document |
| Reorder pages | ✅ | ✅ | by spec (`3,1,2`) or **drag page thumbnails**; pages may repeat |
| Compress | ✅ | ✅ | downsample + re-encode images, deflate, garbage-collect |
| Images → PDF | ✅ | ✅ | PNG/JPG in any order, transparency flattened |
| PDF → images | ✅ | ✅ | PNG/JPG at a chosen DPI |
| Extract embedded images | ✅ | ✅ | pulls original raster assets, no re-render |
| Watermark | ✅ | ✅ | text overlay with adjustable opacity |
| Page numbers | ✅ | ✅ | `n / total` footer |
| Encrypt / decrypt | ✅ | ✅ | AES-256; pypdf fallback when authenticating |
| Metadata | ✅ | — | read and set title/author/subject/keywords |
| Text extraction | ✅ | ✅ | to stdout, a file, or the log pane |
| **OCR → searchable PDF** | ✅ | ✅ | Tesseract, offline; skips pages that already have text |
| **OCR → text** | ✅ | ✅ | recognises scans without touching the original |
| **Fill form fields** | ✅ | ✅ | by name, case-insensitive, optional flattening |
| **Create form fields** | ✅ | ✅ | text, checkbox, combobox, listbox from JSON |
| **Flatten forms** | ✅ | ✅ | bakes values into page content |
| **Digital signatures** | ✅ | ✅ | PKCS#12 (`.p12`/`.pfx`), invisible or placed, verifiable offline |
| **Verify signatures** | ✅ | ✅ | reports intact / valid / trusted + coverage |
| **Stamp an image** | ✅ | ✅ | scanned signature, seal or logo, with opacity |
| **PDF → DOCX** | ✅ | ✅ | LibreOffice when installed, built-in text writer otherwise |
| **DOCX/ODT → PDF** | ✅ | ✅ | LibreOffice headless |
| **Backend report** | ✅ | ✅ | `capabilities` — what is installed right now |

## Install

Requires **Python 3.10+**.

```bash
git clone https://github.com/akash-taurus/ihatepdf.git
cd ihatepdf
python -m venv .venv
# Windows:  .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
```

Optional backends (each unlocks one feature, all off by default):

```bash
pip install -r requirements-optional.txt   # pyHanko signing
# plus the Tesseract binary for OCR and LibreOffice for Office conversion —
# see requirements-optional.txt for per-platform install commands
```

## Desktop app

```bash
python app/main.py
```

A PySide6 window: choose a tool on the left (or filter the list), drag files in,
fill in the few fields that tool needs, and hit **Run**.

- **Only the relevant options are shown.** Fields are hidden and re-shown per
  tool, so nothing you typed is ever thrown away when you switch.
- **Drag & drop** files or whole folders onto the input list; `↑`/`↓` fix the
  order used by Merge.
- **Background execution.** Every job runs on a worker thread with a progress
  indicator, so the window never freezes — OCR and compression included.
- **Page-order tab.** Load a PDF, see real page thumbnails (rendered in the
  background as they become ready), drag them into the order you want, or use
  Move/Reverse/Reset, then save. The Reorder tool reuses that arrangement.
- **Backend awareness.** Tools whose optional backend is missing are marked `⚠`
  with the reason, and the log reports what is available at startup.

## CLI

```bash
python cli.py <command> [options]      # python cli.py --version
```

**Documents**

| Command | Example |
| --- | --- |
| `info` | `python cli.py info sample.pdf` |
| `merge` | `python cli.py merge a.pdf b.pdf -o merged.pdf` |
| `split` | `python cli.py split input.pdf -o out_dir --every 2` |
| `extract` | `python cli.py extract input.pdf --pages "1,3-5" -o out.pdf` |
| `delete` | `python cli.py delete input.pdf --pages "2" -o out.pdf` |
| `rotate` | `python cli.py rotate input.pdf --pages "1-3" --angle 90 -o out.pdf` |
| `reorder` | `python cli.py reorder input.pdf --order "3,1,2" -o out.pdf` |
| `compress` | `python cli.py compress input.pdf -o small.pdf --image-quality 60 --dpi 150` |
| `watermark` | `python cli.py watermark input.pdf -o out.pdf --text "CONFIDENTIAL" --opacity 0.2` |
| `pagenumbers` | `python cli.py pagenumbers input.pdf -o out.pdf` |
| `encrypt` / `decrypt` | `python cli.py encrypt input.pdf -o out.pdf --password secret` |
| `metadata` | `python cli.py metadata input.pdf` · `... --set title=Report -o out.pdf` |
| `text` | `python cli.py text input.pdf --pages "1-2" -o report.txt` |

**Images**

| Command | Example |
| --- | --- |
| `images-to-pdf` | `python cli.py images-to-pdf img1.png img2.jpg -o out.pdf` |
| `pdf-to-images` | `python cli.py pdf-to-images input.pdf -o out_dir --dpi 200 --format jpg` |
| `extract-images` | `python cli.py extract-images input.pdf -o out_dir` |
| `stamp` | `python cli.py stamp input.pdf -o out.pdf --image sig.png --pages "1" --width 160 --opacity 0.8` |

**OCR**

| Command | Example |
| --- | --- |
| `ocr` | `python cli.py ocr scan.pdf -o searchable.pdf --language eng --dpi 300` |
| `ocr-text` | `python cli.py ocr-text scan.pdf -o scan.txt --language eng+deu` |

**Forms and signing**

| Command | Example |
| --- | --- |
| `form-fields` | `python cli.py form-fields input.pdf` |
| `add-fields` | `python cli.py add-fields in.pdf -o out.pdf --field '{"name":"email","type":"text","rect":[72,500,300,520]}'` |
| `fill-form` | `python cli.py fill-form in.pdf -o out.pdf --set full_name="Ada Lovelace" --flatten` |
| `flatten-form` | `python cli.py flatten-form in.pdf -o out.pdf` |
| `sign` | `python cli.py sign in.pdf -o signed.pdf --pfx me.p12 --password ••• --reason "Approved" --box "100,100,300,160"` |
| `verify-signatures` | `python cli.py verify-signatures signed.pdf` |

**Conversion and diagnostics**

| Command | Example |
| --- | --- |
| `pdf-to-docx` | `python cli.py pdf-to-docx in.pdf -o out.docx --engine auto` |
| `docx-to-pdf` | `python cli.py docx-to-pdf in.docx -o out.pdf` |
| `capabilities` | `python cli.py capabilities` |

Every command accepts `-h`. Exit code is `0` on success and `1` on failure,
with the reason on stderr — safe to script:

```bash
python cli.py merge $(ls *.pdf) -o all.pdf && python cli.py info all.pdf
python cli.py fill-form invoice.pdf -o filled.pdf --json values.json \
  && python cli.py sign filled.pdf -o final.pdf --pfx me.p12 --password "$PW"
```

A JSON object file (`--json`) is handy for long form values, and `--field`
accepts repeatable JSON objects so generated forms can be scripted.

## Page specs

Most commands accept `--pages "1,3-5,8"`. Pages are **1-indexed** and inclusive.

| Spec | Meaning |
| --- | --- |
| `"1"` | page 1 only |
| `"1-3"` | pages 1, 2, 3 |
| `"1,3-5"` | pages 1, 3, 4, 5 |
| `"5-3"` | reversed ranges are normalised to `3-5` |
| *omitted* | every page (where the command allows it) |

`reorder --order` is different on purpose: it preserves the order you give,
accepts a subset, and repeats pages (`"2,2,1"` duplicates page 2).

Out-of-range or malformed specs raise a clear error instead of silently
producing a truncated file.

## OCR

Tesseract runs locally through PyMuPDF — no Python OCR dependency and no
network call. Install the binary:

| Platform | Command |
| --- | --- |
| Windows | `winget install UB-Mannheim.TesseractOCR` |
| macOS | `brew install tesseract` |
| Debian/Ubuntu | `apt-get install tesseract-ocr` |

```bash
python cli.py ocr scan.pdf -o searchable.pdf --language eng --dpi 300
```

`ocr` writes an invisible text layer sized to each recognised word, so the
result is searchable and copy-pasteable while looking unchanged. Pages that
already have a text layer are skipped (mixed digital/scanned documents are
common); pass `--force` to OCR everything, and `--language eng+deu` for
multi-language documents. `ocr-text` returns just the recognised text.

## Forms

```bash
python cli.py form-fields contract.pdf
python cli.py fill-form contract.pdf -o signed-form.pdf \
  --set full_name="Ada Lovelace" agree=yes country=UK --flatten
```

- Field names are matched case-insensitively; `yes`/`true`/`on`/`x` check boxes.
- Values for choice fields are validated against the field's own options.
- `--flatten` bakes the values into the page and removes the interactive form —
  useful for final copies that should not be edited further.
- New fields can be added from JSON (`add-fields`) with types `text`,
  `checkbox`, `combobox`, `listbox` and options for read-only/required/limits.

## Digital signatures

Signing needs the optional pyHanko dependency and a PKCS#12 bundle you already
own (most CAs and `openssl pkcs12 -export` produce one):

```bash
pip install -r requirements-optional.txt
python cli.py sign contract.pdf -o signed.pdf --pfx me.p12 --password "$PFX_PW" \
  --reason "Approved" --location "Pune" --box "100,100,300,160"
python cli.py verify-signatures signed.pdf
```

- Signatures are embedded in the PDF and verified offline. Nothing is uploaded,
  and no timestamp authority is contacted unless you pass `--timestamp-url`.
- `--box "x0,y0,x1,y1"` places a visible signature field; coordinates are points
  measured from the page's **top-left** (as viewers show it). Omit it for an
  invisible signature and pair it with `stamp` for a visual one:
  `stamp` first, then `sign`.
- `verify-signatures` reports `intact` (bytes unchanged since signing), `valid`,
  `trusted` (chains to a locally trusted CA) and coverage. A self-signed test
  certificate is reported intact but untrusted — that is the correct answer.

## Conversion

```bash
python cli.py pdf-to-docx report.pdf -o report.docx          # auto engine
python cli.py pdf-to-docx scan.pdf -o scan.docx --engine builtin
python cli.py docx-to-pdf letter.docx -o letter.pdf          # needs LibreOffice
```

- With **LibreOffice** installed, conversion is full-fidelity and headless.
- Without it, **PDF → DOCX still works**: a built-in writer emits a valid OOXML
  package with one paragraph per line and page breaks preserved. Layout and
  images are not carried over — that is a deliberate trade for zero external
  dependencies, and `--engine` lets you choose explicitly.

## Project layout

```
ihatepdf/
├── app/
│   ├── main.py            # PySide6 window: widget wiring only
│   ├── tools.py           # tool catalogue: UI-free and unit-tested
│   ├── thumbnails.py      # page-thumbnail reordering pane
│   └── worker.py          # QThread wrapper + log formatting
├── core/
│   ├── ops.py             # core PDF logic (merge … metadata)
│   ├── pagespec.py        # "1,3-5" spec and page-order parsers
│   ├── forms.py           # AcroForm: list/fill/create/flatten
│   ├── ocr.py             # Tesseract OCR + searchable text layer
│   ├── convert.py         # PDF <-> DOCX, LibreOffice, capabilities
│   └── sign.py            # PKCS#12 signing, verification, image stamps
├── tests/                 # ops, pagespec, forms, ocr, convert, sign, cli, app, gui
├── .github/workflows/ci.yml
├── build_exe.ps1          # isolated-venv PyInstaller build
├── cli.py                 # argparse CLI with a dispatch table
├── pyproject.toml         # black + pytest configuration
├── requirements.txt       # runtime dependencies
├── requirements-dev.txt   # runtime + black
└── requirements-optional.txt
```

## Design notes

- **`core/` is the whole product.** The GUI and CLI only parse input and call
  the same functions, so one fix lands in both front ends.
- **The desktop app declares tools as data.** `app/tools.py` holds no Qt code,
  which is why the whole catalogue is unit-tested without a display.
- **PyMuPDF is the primary engine** — page insertion, rendering, widgets and
  image access. **pypdf** is a fallback for encryption edge cases; **Pillow**
  handles image decoding, flattening, and JPEG re-encoding for compression.
- **Optional backends degrade loudly.** Missing Tesseract, LibreOffice or
  pyHanko raises an actionable error (and marks the tool with `⚠` in the GUI);
  no feature silently does nothing.
- **Writes are explicit.** Output paths are validated and parent directories
  created up front, and the source file is never modified in place.
- **Tests generate their own fixtures** with PyMuPDF and Pillow — no binary
  samples in the repo, and signing tests mint a throwaway certificate at run
  time.

## Packaging a Windows `.exe`

```powershell
powershell -ExecutionPolicy Bypass -File build_exe.ps1
# → dist\ihatepdf.exe — single file, windowed, fully offline, ~75 MB
```

Always build through `build_exe.ps1`: it uses an isolated virtualenv holding
only this app's dependencies. Building with a global Python that has
data-science packages installed pulls them all into the bundle (observed: an
828 MB binary).

The frozen app inherits the same optional backends: install Tesseract and/or
LibreOffice on the machine and OCR/conversion light up — the GUI reports which
are present at startup. pyHanko is a Python package, so signing inside the
`.exe` needs it added to the build venv (`requirements-optional.txt` is not
installed by the script).

First launch may trigger a SmartScreen prompt because the binary is unsigned —
choose **More info → Run anyway**. No installer, no admin rights, no network.

## Development

```bash
pip install -r requirements-dev.txt
black .        # formatting (line length 100, configured in pyproject.toml)
pytest -q      # 131 tests; backend-specific tests skip when it is not installed
```

The suite is split so it can be run at whatever depth you have installed:

| File | Covers |
| --- | --- |
| `tests/test_ops.py` | core document operations, validation, watermark opacity |
| `tests/test_pagespec.py` | page specs and the reorder parser |
| `tests/test_forms.py` | creating, listing, filling, validating and flattening fields |
| `tests/test_ocr.py` | searchable-layer writer, pipeline wiring, real OCR of an image-only scan |
| `tests/test_convert.py` | built-in DOCX validity, engine selection, real LibreOffice round trip |
| `tests/test_sign.py` | real signing + verification, tamper detection, stamping |
| `tests/test_cli.py` | every new command end to end, including exit codes |
| `tests/test_app_tools.py` | all 27 desktop tools, without Qt |
| `tests/test_gui.py` | the window and thumbnail pane, offscreen |

CI runs four jobs: **core** (Windows + Linux, Python 3.11/3.13, formatting +
tests with no optional backends at all), **optional** (pyHanko signing
exercised for real), **backends** (Tesseract and LibreOffice installed, so OCR
and the Office round trip run against real binaries rather than skipping) and
**desktop** (PySide6, `QT_QPA_PLATFORM=offscreen`). See
[CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## Privacy

- No network calls anywhere in the codebase — processing is local by design.
  Signing contacts a timestamp authority **only** if you pass `--timestamp-url`.
- No telemetry, analytics, accounts, or licence checks.
- The only files written are the outputs you ask for (plus auto-named results
  in your working directory when you leave the output field blank).

## Roadmap

- [x] Core operations on the shared `core/` engine
- [x] CLI front end
- [x] PySide6 desktop UI with drag & drop and per-tool options
- [x] PyInstaller single-file `.exe` packaging
- [x] OCR for scanned documents (offline Tesseract backend)
- [x] PDF → DOCX (LibreOffice, with a built-in fallback)
- [x] Page reordering by dragging thumbnails in the GUI
- [x] Digital signing (PKCS#12) and form-field support
- [ ] Redaction with true content removal
- [ ] Bookmarks / outline and page-number editing
- [ ] Batch mode: run one tool over a folder tree
- [ ] N-up / booklet imposition
- [ ] Certified signatures and visible signature appearances with images
- [ ] PDF/A output

## License

[MIT](LICENSE) © Akash Maheshwari
