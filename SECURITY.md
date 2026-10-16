# Security & privacy

## Design guarantees

ihatepdf processes documents **entirely on the local machine**.

- No outbound network requests anywhere in the codebase.
- No telemetry, analytics, crash reporting, or licence/activation checks.
- No accounts and no credentials to store or leak.
- Documents are never copied outside the input/output paths you specify.

## Reporting a vulnerability

Open an issue at
<https://github.com/akash-taurus/ihatepdf/issues> describing the problem and the
version you ran (commit hash, or the `.exe` build date). Please do not attach
the confidential document that triggered it — a minimal generated PDF is enough
to reproduce most issues.

## Known limitations

- Encrypted PDFs use AES-256 on write; when decrypting, if PyMuPDF cannot
  authenticate the file, the pypdf fallback is used with the same password.
- The distributed `.exe` is unsigned, so Windows SmartScreen may warn on first
  launch. Verify the source and build it locally if that matters to you.
- A wrong password fails loudly with `Wrong password`; it never writes a
  partially decrypted file over your output path.
