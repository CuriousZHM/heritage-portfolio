# Heritage portfolio

Two heritage-domain projects with explicit provenance and evidence boundaries.

## Projects

- [Document processing prototype](heritage_document_pipeline/README.md): original agent code reference plus a September 2026 AI-assisted maintenance runner, synthetic offline demo, source-evidence checks and eight tests. The demo is not an AI quality benchmark. PDF and live-model operation have not been validated in this maintenance pass.
- [Q&A coursework evaluation audit](heritage_qa_evaluation/README.md): sanitized reference notebook, historical score importer, response alignment, transparent calculations and ten tests. Haiming Zhu contributed the concept, dataset curation, evaluation design and report preparation; teammates implemented the system and ran the experiments.

## Validation and limitations

All 18 offline unit tests passed on September 4, 2026. No model/API calls were made.
No 95% accuracy or time-saving claim is supported. No original scoring rubric is available;
invalid historical scores remain flagged rather than replaced with invented values.

Raw course evidence and generated reports containing archived passages and team outputs remain
local and are not included. The audit requires those local source materials to regenerate the
full report; unit tests use self-contained fixtures. Personal CV notes are also excluded.

Embedded Hugging Face credentials were removed. Optional notebook authentication reads
`HF_TOKEN` from the environment. Removing credentials from files does not revoke them:
the previous token must be revoked separately in the owner's Hugging Face settings.

This repository is private. No license or independent authorship over teammates' work is implied.
