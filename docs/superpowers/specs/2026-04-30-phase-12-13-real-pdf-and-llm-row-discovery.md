# Phase 12-13 Real PDF Quick Validation And LLM Row Discovery Spec

> Date: 2026-04-30
> Status: ready for implementation planning
> Scope: Validate the discovery pipeline on a real PDF without LLM first, then add an opt-in real LLM row-discovery smoke test.

## Goal

This spec covers two phases in one implementation effort:

- Phase 12: Real PDF Quick Validation
- Phase 13: LLM-Assisted Row Discovery Smoke Test

They can live in one plan because Phase 13 depends directly on Phase 12 artifacts. The plan must still keep two gates: do not run real LLM row discovery until real PDF ingestion/chunking/document/statement artifacts are reviewable.

## Phase 12: Real PDF Quick Validation

Goal: run the current discovery pipeline on at least one real annual report without using a real LLM.

Target sample:

```text
downloads/hk_stocks/00001/annual/2025_annual_en.pdf
```

Secondary samples, optional after the target works:

```text
downloads/hk_stocks/01113/annual/2025_annual_en.pdf
downloads/cn_stocks/600519/annual/2025_年度报告.pdf
```

Expected command path:

```text
ingest
-> chunk
-> probe-parser
-> map-document
-> map-statements
-> discover-rows
-> map-fields
```

Expected artifacts:

```text
tmp/runs/quick_validation/<report_id>/
  pages.jsonl
  run_metadata.json
  chunks.jsonl
  parser_capability.json
  document_map.json
  statement_map.json
  row_inventory.json
  catalog_mapping.json
```

Phase 12 must not require an LLM API key.

## Phase 12 Requirements

### PDF Text Backend

The project currently defaults to `pdftotext -layout`. In the local environment, `pdftotext` may not be on PATH. Phase 12 must handle this explicitly:

- If `pdftotext` is available, use it.
- If not available, provide a Python fallback backend that can extract text from HK English PDFs well enough for the quick-validation demo.
- The parser capability artifact must record which backend was used.
- If the backend cannot extract useful text, fail with an explicit parser capability warning instead of silently producing empty downstream artifacts.

### Quick Validation Runner

Add a small orchestrator that uses `QuickValidationLayout` and runs the no-LLM quick-validation path for one report id and PDF path.

Recommended command:

```text
financial-report-llm-extractor quick-validate \
  --pdf downloads/hk_stocks/00001/annual/2025_annual_en.pdf \
  --report-id 00001_2025_en \
  --root .
```

This command should write all Phase 12 artifacts under:

```text
tmp/runs/quick_validation/00001_2025_en/
```

### Review Summary

Add a small JSON summary for quick validation:

```text
quick_validation_summary.json
```

It should include:

- `report_id`
- artifact paths
- parser warnings
- document section counts
- statement counts by kind
- row count
- selected field mapping statuses

## Phase 12 Success Criteria

- A no-network command can run against `00001_2025_en.pdf`.
- It produces all Phase 12 artifacts.
- It clearly reports parser limitations if text extraction is weak.
- It does not require `OPENAI_API_KEY` or any provider config.
- Tests use fixtures and injected parser backends, not real PDF tooling.

## Phase 13: LLM-Assisted Row Discovery Smoke Test

Goal: verify that a real OpenAI-compatible model can produce a `row_inventory_llm.json` from already selected statement chunks.

This is not final field extraction and not whole-PDF extraction.

Allowed LLM input:

- one statement at a time
- statement title
- statement kind
- scope
- period columns
- unit/currency context
- statement block text
- evidence block ids/pages

Forbidden LLM input:

- full PDF text
- whole report pages outside the selected statement context
- complete P0/P1 catalog as one prompt

Expected artifact:

```text
row_inventory_llm.json
```

Expected raw artifacts:

```text
prompt_payloads/
raw_llm_responses/
parsed_llm_responses/
```

## Phase 13 Requirements

### Config

Use the existing OpenAI-compatible config shape:

```json
{
  "provider": "openai-compatible",
  "model": "model-name",
  "base_url": "https://example.com/v1",
  "api_key_env": "OPENAI_API_KEY",
  "timeout_seconds": 60,
  "max_retries": 1
}
```

API key values must come from environment variables and must not be written to artifacts.

### Opt-In Only

The real LLM smoke test must be opt-in. Unit tests and default quick validation must not require network.

Recommended command:

```text
financial-report-llm-extractor discover-rows-llm \
  --chunks tmp/runs/quick_validation/00001_2025_en/chunks.jsonl \
  --statement-map tmp/runs/quick_validation/00001_2025_en/statement_map.json \
  --config llm_config.json \
  --out tmp/runs/quick_validation/00001_2025_en/row_inventory_llm.json \
  --prompt-dir tmp/runs/quick_validation/00001_2025_en/prompt_payloads \
  --raw-response-dir tmp/runs/quick_validation/00001_2025_en/raw_llm_responses \
  --parsed-response-dir tmp/runs/quick_validation/00001_2025_en/parsed_llm_responses
```

### Failure Behavior

If the provider returns malformed JSON or an unexpected schema:

- archive prompt payload
- archive raw response
- archive structured error
- fail the command clearly

Do not write a successful `row_inventory_llm.json` with partial or unvalidated rows unless rows are explicitly marked with error status.

## Phase 13 Success Criteria

- Fake/injected transport tests prove prompt/raw/parsed artifact writing.
- A real smoke command can be run manually when API key is configured.
- The prompt includes only statement-scoped evidence.
- `row_inventory_llm.json` has the same row inventory shape as the fake/rule-first output.
- Real LLM failure modes are reviewable through artifacts.

## One-Plan Feasibility

Phase 12 and Phase 13 can be implemented in one plan because:

- Phase 13 consumes Phase 12 artifacts.
- Both are quick-validation workflow work, not broad extraction quality work.
- The boundary is clear: Phase 12 is no-network; Phase 13 is opt-in network.

The plan must include a checkpoint after Phase 12. If real PDF validation cannot produce useful statement chunks, stop before Phase 13 and fix parser/chunking first.
