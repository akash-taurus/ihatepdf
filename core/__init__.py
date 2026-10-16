"""ihatepdf core package: UI-agnostic PDF logic.

Modules:
    ops       — merge, split, extract, delete, rotate, reorder, compress,
                convert to/from images, watermark, page numbers, encrypt,
                decrypt, text, metadata
    pagespec  — "1,3-5" page-spec and page-order parsers
    forms     — AcroForm fields: list, fill, create, flatten
    ocr       — Tesseract OCR: searchable PDF and text extraction
    convert   — PDF <-> DOCX and LibreOffice-backed conversions
    sign      — PKCS#12 digital signatures, verification, image stamps
"""

__version__ = "0.2.0"

__all__ = ["__version__", "convert", "forms", "ocr", "ops", "pagespec", "sign"]
