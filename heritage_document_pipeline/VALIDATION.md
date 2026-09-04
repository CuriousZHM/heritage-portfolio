# Validation record

Date: 2026-09-04. Runtime: Python 3.12.14, Pydantic 2.13.5.

- 8 unit/integration tests passed.
- The synthetic Markdown fixture completed the maintained pipeline with 5 blocks and 3 entities.
- Expected outputs are saved under `examples/expected/` and labelled `fixture-demo`.
- Tests cover source line references, empty input, schema validation, unsupported evidence,
  fixture/input mismatch, output preservation and explicit live-mode consent.
- A credential-pattern scan passed for this prepared folder.
- Four legacy source files match the original local repository byte-for-byte.

Not validated: live model API behaviour, model quality, Docling PDF/OCR conversion, real
planning documents, latency improvement or production deployment. No API credentials were used.
The demo is an engineering check with authored fixtures, not an AI performance experiment.
