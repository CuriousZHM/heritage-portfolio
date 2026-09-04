# Validation record

Date: 2026-09-04. Python 3.12.14.

- 10 tests passed for format repairs, response alignment, raw-data preservation,
  correction validation, shared-question filtering and denominator consistency.
- Imported 20 questions, 180 original score cells and 21 archived output files.
- 340 response records across 17 files aligned by exact question text.
- All nine conditions in the main PPT score table have 20 aligned responses each.
- Four auxiliary files lack reliable question boundaries. Their raw text remains preserved.
- One missing JSON comma was repaired with an audit record; question and answer content unchanged.
- Two original 5/4 score cells remain unresolved. The exploratory common-subset calculation
  excludes Question 14 for all nine conditions and retains 19 questions.
- HTML tables and coverage chart derive from the same summary object and evidence file.
- Headless Edge check: 2 tables, 1 SVG chart, 20 top-level question sections, no horizontal
  overflow at 1360px. Report and chart screenshots were visually inspected.
- Credential-pattern scan passed for the prepared folder. Sanitized notebook has no execution outputs.

No new model execution, new human grading or CV-ready percentage is claimed. The local
source notebook was cleaned on September 4, 2026 and remains excluded from Git.
The owner must separately revoke the old token; backups may retain it.
