# ihatepdf

[![CI](https://github.com/akash-taurus/ihatepdf/actions/workflows/ci.yml/badge.svg)](https://github.com/akash-taurus/ihatepdf/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-4c566a)](#install)
[![Offline](https://img.shields.io/badge/network-100%25%20offline-success)](SECURITY.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

**A local-first PDF toolkit for the things you actually do to PDFs** — merge,
split, extract, rotate, reorder, compress, watermark, encrypt — with a desktop
GUI and a scriptable CLI over the same core.

No account, no upload, no page limits, no "sign up to download". Your files
never leave the machine.

---

## Contents

- [Why](#why)
- [Features](#features)
- [Install](#install)
- [Desktop app](#desktop-app)
- [CLI](#cli)
- [Page specs](#page-specs)
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
so processing is minutes-free, offline, and inspectable.

## Features

| Operation | CLI | GUI | Notes |
| --- | :-: | :-: | --- |
| Merge PDFs | ✅ | ✅ | keeps input order |
| Split | ✅ | ✅ | one file per page, fixed chunks (`--every N`), or custom groups |
| Extract pages | ✅ | ✅ | non-destructive copy |
| Delete pages | ✅ | ✅ | refuses to delete every page |
| Rotate | ✅ | ✅ | 90° / 180° / 270°, per page or whole document |
| Reorder pages | ✅ | ✅ | arbitrary order, e.g. `3,1,2` |
| Compress | ✅ | ✅ | downsample + re-encode images, deflate, garbage-collect |
| Images → PDF | ✅ | ✅ | PNG/JPG/JPEG in any order, transparent images flattened |
| PDF → images | ✅ | ✅ | PNG/JPG at a chosen DPI |
| Extract embedded images | ✅ | — | pulls original raster assets, no re-render |
| Watermark | ✅ | ✅ | centred text overlay, colour + size adjustable |
| Page numbers | ✅ | ✅ | `n / total` footer |
| Encrypt / decrypt | ✅ | ✅ | AES-256; pypdf fallback when authenticating |
| Metadata | ✅ | ✅ | read and set title/author/subject/keywords |
| Text extraction | ✅ | — | prints text to stdout for piping |

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

## Desktop app

```bash
python app/main.py
```

A PySide6 window: pick a tool on the left, drag files in, fill the fields that
tool needs, hit **Run**. Long jobs execute on a worker thread, so the window
stays responsive, and the log pane shows what was written where.

Handy details:

- Drag & drop files straight onto the list; use `↑` / `↓` to fix merge order.
- Leave the output field blank and the result lands next to your input as
  `<name>-<tool>.pdf`, or in a new folder for the multi-file tools.
- The same `core/ops.py` functions back the GUI and the CLI, so results are
  identical however you drive it.

## CLI

```bash
python cli.py <command> [options]
```

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
| `images-to-pdf` | `python cli.py images-to-pdf img1.png img2.jpg -o out.pdf` |
| `pdf-to-images` | `python cli.py pdf-to-images input.pdf -o out_dir --dpi 200 --format jpg` |
| `extract-images` | `python cli.py extract-images input.pdf -o out_dir` |
| `watermark` | `python cli.py watermark input.pdf -o out.pdf --text "CONFIDENTIAL" --fontsize 48` |
| `pagenumbers` | `python cli.py pagenumbers input.pdf -o out.pdf` |
| `encrypt` | `python cli.py encrypt input.pdf -o out.pdf --password secret` |
| `decrypt` | `python cli.py decrypt input.pdf -o out.pdf --password secret` |
| `text` | `python cli.py text input.pdf --pages "1-2"` |
| `metadata` | `python cli.py metadata input.pdf`  ·  `... --set title="Report" -o out.pdf` |

Every command accepts `-h` for its full option list. Exit code is `0` on
success and `1` on failure, with the reason on stderr — safe to use in scripts:

```bash
pdfs=$(find . -name '*.pdf')
python cli.py merge $pdfs -o all.pdf && echo "merged $(python cli.py info all.pdf)"
```

## Page specs

Most commands accept `--pages "1,3-5,8"`. Pages are **1-indexed** and inclusive.

| Spec | Meaning |
| --- | --- |
| `"1"` | page 1 only |
| `"1-3"` | pages 1, 2, 3 |
| `"1,3-5"` | pages 1, 3, 4, 5 |
| `"5-3"` | reversed ranges are normalised to `3-5` |
| *omitted* | every page (where the command allows it) |

Out-of-range or malformed specs raise a clear error rather than silently
producing a truncated file.

## Project layout

```
ihatepdf/
├── app/
│   └── main.py            # PySide6 desktop UI (thin wrapper)
├── core/
│   ├── ops.py             # all PDF logic — UI-agnostic
│   └── pagespec.py        # "1,3-5" parser + split-range parser
├── tests/
│   └── test_ops.py        # end-to-end tests on generated PDFs/images
├── .github/workflows/ci.yml
├── build_exe.ps1          # isolated-venv PyInstaller build
├── cli.py                 # argparse CLI (thin wrapper)
├── pyproject.toml         # black + pytest configuration
├── requirements.txt       # runtime dependencies
└── requirements-dev.txt   # runtime + black
```

## Design notes

- **`core/ops.py` is the whole product.** `app/main.py` and `cli.py` only parse
  input and call the same functions, so a fix lands in both front ends at once.
- **PyMuPDF is the primary engine** — fast page insertion, rendering, and image
  access. **pypdf** is a fallback for encryption edge cases; **Pillow** handles
  image decoding, flattening, and JPEG re-encoding for compression.
- **Writes are explicit.** Output paths are validated and parent directories
  created up front, and the source file is never modified in place.
- **Tests generate their own fixtures** with PyMuPDF and Pillow, so the repo
  carries no binary sample files.

## Packaging a Windows `.exe`

```powershell
powershell -ExecutionPolicy Bypass -File build_exe.ps1
# → dist\ihatepdf.exe — single file, windowed, fully offline, ~75 MB
```

Always build through `build_exe.ps1`: it uses an isolated virtualenv holding
only this app's dependencies. Building with a global Python that has
data-science packages installed pulls them all into the bundle (observed:
an 828 MB binary).

First launch may trigger a SmartScreen prompt because the binary is unsigned —
choose **More info → Run anyway**. No installer, no admin rights, no network.

## Development

```bash
pip install -r requirements-dev.txt
black .        # formatting (line length 100, configured in pyproject.toml)
pytest -q      # end-to-end tests
```

CI runs `black --check` and `pytest` on Windows and Linux for Python 3.11 and
3.13. See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## Privacy

- No network calls anywhere in the codebase — processing is local by design.
- No telemetry, analytics, accounts, or licence checks.
- The only files written are the outputs you ask for (plus auto-named results
  in your working directory when you leave the output field blank).

## Roadmap

- [x] Core operations on the shared `core/ops.py` engine
- [x] CLI front end
- [x] PySide6 desktop UI with drag & drop
- [x] PyInstaller single-file `.exe` packaging
- [ ] OCR for scanned documents (offline `ocrmypdf` / Tesseract backend)
- [ ] PDF → DOCX (headless LibreOffice hook)
- [ ] Drag thumbnail page reordering in the GUI
- [ ] Signing and form-field support

## License

[MIT](LICENSE) © Akash Maheshwari
