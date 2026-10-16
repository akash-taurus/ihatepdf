# Security & privacy

## Design guarantees

ihatepdf processes documents **entirely on the local machine**.

- No outbound network requests anywhere in the codebase, with one deliberate
  exception: `sign --timestamp-url <url>` contacts the RFC 3161 authority you
  name. Without that flag, signing makes no network call at all.
- No telemetry, analytics, crash reporting, or licence/activation checks.
- No accounts and no credentials to store or leak. Passwords and PKCS#12
  passphrases are used in memory for the operation and never written anywhere.
- Documents are never copied outside the input/output paths you specify.
- OCR, form handling, conversion and signature verification are local:
  Tesseract, LibreOffice and pyHanko run as local processes only.

## Reporting a vulnerability

Open an issue at
<https://github.com/akash-taurus/ihatepdf/issues> describing the problem and the
version you ran (commit hash, or the `.exe` build date). Please do not attach
the confidential document that triggered it — a minimal generated PDF is enough
to reproduce most issues. If the report involves key material, say so without
including the key.

## Known limitations

- Encrypted PDFs use AES-256 on write; when decrypting, if PyMuPDF cannot
  authenticate the file, the pypdf fallback is used with the same password.
- A wrong password or certificate passphrase fails loudly (`Wrong password`,
  `Could not load the certificate`) and never writes a partial output.
- **Self-signed certificates are reported as intact but not trusted.** That is
  the correct answer: trust requires a chain to a certificate authority in your
  local trust store. pyHanko validates against the local trust list; nothing is
  fetched from the network during verification.
- `sign` and `stamp` take the certificate path and passphrase from the command
  line, which is visible in your shell history and process list. Prefer an
  environment variable (`--password "$PFX_PW"`) or the GUI's masked field.
- The distributed `.exe` is unsigned, so Windows SmartScreen may warn on first
  launch. Verify the source and build it locally if that matters to you.
- OCR output quality is Tesseract's, and OCR of a low-resolution scan is only as
  good as the scan. Nothing about OCR leaves the machine.
