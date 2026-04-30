# Phase 10 Parser Capability Probe And Document Map Spec

> Date: 2026-04-30
> Status: ready for implementation
> Scope: Add the first rule-first document structure demo before statement/row discovery.

## Goal

Phase 10 validates that the pipeline can inspect extracted page/block artifacts and produce a reviewable document map. It does not extract final fields and does not ask the LLM to process the whole PDF.

The phase produces two artifacts:

- `parser_capability.json`
- `document_map.json`

## Inputs

- `pages.jsonl` from ingestion.
- `run_metadata.json` from ingestion.
- `chunks.jsonl` from chunking.

Tests use synthetic artifacts. They must not require real PDF tooling or network.

## Parser Capability Probe

The parser capability probe records whether the extracted page text looks usable for downstream document mapping.

Required fields:

- `parser_name`
- `parser_version`
- `source_pdf_hash`
- `page_count`
- `non_empty_page_count`
- `average_chars_per_page`
- `contains_cjk`
- `contains_financial_statement_terms`
- `warnings`

Warnings should be explicit rather than silent:

- `no_pages_extracted`
- `low_text_volume`
- `no_financial_statement_terms_detected`

## Document Map

The document map is a rule-first section detector over block records. It should distinguish:

- `contents`
- `financial_summary`
- `management_discussion`
- `independent_auditor_report`
- `audited_financial_statements`
- `notes_to_financial_statements`

Every section should include:

- `kind`
- `page_start`
- `page_end`
- `confidence`
- `evidence`

Evidence entries include:

- `page`
- `block_id`
- `snippet`

## CLI

Add two thin CLI commands:

```text
financial-report-llm-extractor probe-parser --pages <pages.jsonl> --metadata <run_metadata.json> --out <parser_capability.json>
financial-report-llm-extractor map-document --chunks <chunks.jsonl> --out <document_map.json>
```

## Success Criteria

- Synthetic tests prove parser probe warnings and section detection.
- `map-document` can separate financial summary / MD&A / auditor report / formal statements in a small fixture.
- CLI delegates to the document-map layer.
- `uv run pytest -v`, `uv run ruff check .`, and `uv run mypy src tests` pass.
