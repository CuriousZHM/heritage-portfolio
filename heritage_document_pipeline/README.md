# Heritage planning document processing prototype

An industry-specific document processing prototype originating from Haiming Zhu's
heritage planning work. **Not an autonomous multi-agent system or a production service.**

## What is here

- `legacy/`: unchanged copies of the original three-stage implementation and runner.
  Original repository: https://github.com/CuriousZHM/agent_for_heritage
  Source commit: `eeeb5118a72221360a541ee12675cc9dba8a5f56` (local source tree was clean).
- `pipeline.py`: a new, AI-assisted maintenance runner prepared in September 2026.
  It isolates optional PDF dependencies, accepts explicit city/period metadata, validates
  output schemas and source quotations, and writes a run manifest.
- `examples/`: entirely synthetic input and explicitly hand-authored model-response fixtures.
  These contain no real government documents or data.

The new runner is engineering follow-up, **not evidence of historical project results or
the author's earlier independent implementation**. The legacy runner remains a reference,
including its original missing `historical_cities` dependency. The maintained runner removes
that dependency by requiring explicit metadata rather than inventing an official city list.

## Quick start (Python 3.11 or 3.12)

From this folder:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python pipeline.py --demo --output runs/demo-1
.venv\Scripts\python -m unittest discover -s tests -v
```

The demo makes **no network requests**. It tests document splitting, response-schema
validation, source grounding and output generation. It does **not** measure model accuracy,
PDF parsing accuracy or time savings. An existing output folder is never overwritten.

Expected: 5 blocks and 3 synthetic entities. Outputs are `parsed.md`, `indexed.jsonl`,
`entities.jsonl` and `manifest.json`. The entity records include source block and line references.
`examples/expected/` contains the verified fixture-demo outputs for comparison.
The maintenance pass tested Python 3.12.14 and Pydantic 2.13.5. The broader compatible
dependency range is declared in `requirements.txt`; other versions were not exhaustively tested.

## Live model mode (optional)

Set `OPENAI_API_KEY`, `OPENAI_MODEL` and optionally `OPENAI_BASE_URL` in your local shell.
Never paste credentials into source code, notebooks, screenshots or Git history.
Custom OpenAI-compatible providers may need endpoint-specific adaptation; this integration
has not been verified with a paid/live model in this maintenance pass.

```powershell
python pipeline.py --live --allow-remote --input private_data/plan.md --city YourCity --period 2026-2036 --output runs/live-1
```

`--allow-remote` explicitly authorizes sending document text to the configured model provider.
Do not use it for confidential materials without the data owner's permission.
The runner uses two model calls per block. No parallel workers or hidden background requests.
Retries are bounded. Schema or quotation errors abort the run instead of reporting success.

For PDFs, install `requirements-pdf.txt`. Docling is the default and may download model files
on its first run. `--pdf-parser pypdf` is a lighter alternative for PDFs with a text layer,
not a substitute for OCR or complex table reconstruction. PDF integration is optional and
has not been exercised on a real planning document in this pass.

## Limitations

- Exact quotations prevent unsupported evidence strings; they do not prove correct
  classification, completeness, or legal interpretation. Human review remains required.
- Cross-document entity resolution, robust OCR, table reconstruction and production
  monitoring are outside the validated demo.
- No claimed percentage improvement, manual-time reduction, or deployment history.
- Only the synthetic sample is prepared for public demonstration. Other inputs and outputs
  require a separate privacy and rights review before publication.

## Small next evaluation

Use permission-cleared documents and independently annotate entity names/types/source spans.
Measure entity precision and recall, parsing failures, per-document latency and model cost.
Keep annotation and model runs versioned; do not tune on the final held-out set.
