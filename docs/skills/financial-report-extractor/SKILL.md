---
name: financial-report-extractor
description: Use when Codex needs to run or review this project's financial report extraction workflow, including PDF ingestion, chunking, retrieval, fake extraction, OpenAI-compatible extraction, or evaluation summaries. This skill is a thin wrapper around the repository CLI and must not reimplement PDF parsing, retrieval, money normalization, validation, or artifact storage logic.
---

# Financial Report Extractor

Use the repository CLI from the project root. Keep business logic in `src/financial_report_llm_extractor/`.

## Workflow

1. Check the worktree:

```bash
git status --short
```

2. Ingest a PDF into page artifacts:

```bash
financial-report-llm-extractor ingest --pdf <report.pdf> --out <run-dir>
```

3. Build evidence blocks and logical chunks:

```bash
financial-report-llm-extractor chunk --pages <run-dir>/pages.jsonl --metadata <run-dir>/run_metadata.json --out <run-dir>/chunks.jsonl
```

4. Retrieve candidate evidence:

```bash
financial-report-llm-extractor retrieve --catalog field_catalog/turtle_v015_priority_fields.json --chunks <run-dir>/chunks.jsonl --out <run-dir>/retrieval_probe.json --priorities P0,P1
```

5. Run fake extraction when validating contracts without network access:

```bash
financial-report-llm-extractor extract-fake --retrieval-probe <run-dir>/retrieval_probe.json --out <run-dir>/extraction_result.json
```

6. Run OpenAI-compatible extraction only when config and credentials are explicitly available:

```bash
financial-report-llm-extractor extract --retrieval-probe <run-dir>/retrieval_probe.json --config <llm_config.json> --out <run-dir>/extraction_result.json --raw-response-dir <run-dir>/raw_llm_responses
```

7. Summarize reviewability:

```bash
financial-report-llm-extractor evaluate --root <repo-root> --out <run-dir>/evaluation_summary.json
```

## Guardrails

- Do not parse PDFs inside the skill.
- Do not normalize money inside the skill.
- Do not validate extraction contracts inside the skill.
- Do not store final facts inside the skill.
- Do not add issuer-specific one-off extraction patches.
- Keep provider fallback explicit and off by default.

## Review

For reviewing outputs, read `references/review-checklist.md`.

