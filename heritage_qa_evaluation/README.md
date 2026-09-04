# Cultural heritage Q&A: coursework evidence and evaluation

This folder packages a **team coursework project**, not a production RAG service.
Haiming Zhu's role: overall concept, dataset curation, evaluation design and report preparation.
Other team members implemented the system and ran the experiments.

The notebook shows semantic chunking, Chroma vector retrieval, BM25, reranking and
local-model generation. Its original implementation is a reference, not a verified environment
for reproducing every archived experiment. This audit does not attribute teammates' code to Haiming.

## What this maintenance pass adds (September 2026)

- A notebook copy with embedded Hugging Face credentials and old execution outputs removed.
  The local source notebook was also cleaned on September 4, 2026.
  Revoke/rotate the old token separately; deleting it from a file does not invalidate it.
- A strict importer for the original 20 questions, PPT score tables and archived model outputs.
- Syntax-only repair of missing commas in the original JSONL, recorded with line numbers.
- Exact question-text alignment fixes response logs whose numbering restarts at 1 after ten questions.
  The original number and occurrence are retained. Ambiguous records are not assigned by position.
- One canonical `evidence/evaluation.json` and one calculation function for all generated results.
- An HTML report with raw-chart reconciliation, transparent macro/micro definitions and a review queue.
- Unit tests that reject invalid counts, duplicate corrections and unreviewed score replacements.

No original scoring file is overwritten. No model or paid API is called. No new performance claim
is created. This is AI-assisted follow-up work, distinct from the original coursework.

## Run the evidence audit (Python 3.11+; standard library only)

From this folder, import a local copy of the original coursework folder once:

```powershell
python audit.py --source-dir "PATH_TO_STAT8021_PROJECT"
```

The source folder must contain `8021project-eval.pptx`, `data/8021manually_picked_QA.jsonl`
and `output/output/output-*.txt`. The importer records filenames and SHA-256 hashes,
preserves questions and answers, and records the two PPT score tables without altering scores.

After import, regenerate everything without the original folders:

```powershell
python audit.py
python -m unittest discover -s tests -v
```

Open `reports/evaluation_report.html`. `reports/summary.json` contains the same calculations.
`reports/review_queue.json` lists the scores/rubrics needing a human decision.
Expand a question in the HTML report to compare its reference answer with archived responses.
Four auxiliary output files lack usable question boundaries and remain as unparsed original text.
This does not mean those experiments were absent. The nine conditions in the main PPT table
have aligned response records after exact-text numbering repair.

## Scoring policy

The old formula counts matched reference points divided by reference points. We call it
**reference-answer point coverage**, a recall-like measure. It is not precision, factual accuracy,
or manual time saved, and it does not penalize unsupported extra claims.

Two original cells contain 5/4. Their question is excluded from *all* conditions for a clearly
labelled, provisional common-subset arithmetic comparison. Values are never clipped to 100%.
All-point comparison against the old chart is diagnostic only. No percentage is approved for a CV.
The owner confirmed that no point-level rubric is available. Question 1 has inconsistent granularity across slides.
No model/API calls are authorized for this maintenance pass; no new scores will be inferred.

## Reviewer corrections

`corrections.json` starts empty. A correction needs `question_id`, `condition`, `matched`,
`expected`, `reviewer`, `reviewed_at`, `reason`, and `evidence` (source excerpt or annotation reference).
Counts must satisfy `0 <= matched <= expected` with `expected > 0`.
Changing reference-point granularity requires regrading all affected conditions consistently.
Do not overwrite `raw_scores`. Rerun `audit.py` after review.

For a future evaluation, define unique atomic reference points, annotate each matched point
with a response quote, separately count unsupported claims, and use a fixed independent test set.
Record model identifiers, prompts, retrieved context, generation parameters and grading date.
The old outputs alone are not enough to certify fresh or production-level performance.

## Before public release

`evidence/` and `reports/` are excluded from Git until privacy/rights and coauthor review.
They include archived legal passages and team outputs. They are historical experiment materials,
not current legal advice. Do not share the original notebook or publish any access token.
Keep the sanitized reference and newly added maintenance code clearly labelled by provenance.

## Resume evidence boundary

Supported: Haiming proposed the concept, curated a 20-question dataset, designed comparisons
across context strategies/model configurations, and prepared the evaluation report.
Not supported: independently developed the full RAG stack; achieved 95% accuracy; saved 95% time;
deployed a production legal-advice system.
