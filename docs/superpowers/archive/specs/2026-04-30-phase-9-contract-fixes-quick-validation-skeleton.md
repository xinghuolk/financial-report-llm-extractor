# Phase 9 Contract Fixes And Quick Validation Skeleton Spec

> Date: 2026-04-30
> Status: ready for implementation planning
> Scope: Fix known evidence/artifact contract gaps and define the minimum run skeleton needed before document-map and row-discovery demos.

## Goal

Phase 9 prepares the project for a fast end-to-end validation of the revised discovery architecture. It does not implement document map, statement map, or row discovery yet. Instead, it fixes the contract bugs that would make those demos unreliable and establishes a minimal quick-validation run layout.

The next phases will rely on Phase 9 artifacts, so the core requirement is simple: every generated artifact must be traceable, reviewable, and safe to use as LLM input or validation evidence.

## Problem

Current foundation code can ingest, chunk, retrieve, fake-extract, call a real OpenAI-compatible transport, and evaluate summary artifacts. However, review has identified contract risks:

- Retrieval evidence can point to the wrong block when a candidate chunk spans multiple blocks.
- Custom chunk output paths must create parent directories consistently.
- Unparseable LLM raw responses must be archived before parse failures are raised or downgraded.

These are not cosmetic bugs. The revised architecture depends on evidence block correctness and raw artifact availability. If Phase 10 document-map decisions or Phase 11 row inventories are built from wrong block pointers or missing raw responses, later review cannot tell whether an error came from parsing, retrieval, LLM output, mapping, or validation.

## Non-Goals

Phase 9 does not implement:

- document map
- statement map
- row discovery
- catalog mapping
- full P0/P1 extraction
- new PDF parser backends
- real LLM smoke tests that require network
- UI, database, batch queue, or report downloader

## Required Behavior

### Evidence Block Selection

Retrieval evidence must select a block that contains the matched alias, matched value snippet, or strongest available match text. When the candidate is a multi-block statement chunk, the evidence `block_id` must not default to the first block unless the first block is actually the best matching block.

If no block contains a clear alias/snippet match, retrieval may fall back to the highest-scoring block in the chunk, but the fallback should be deterministic and test-covered.

### Nested Artifact Output

Chunk output must create parent directories for explicit `--out` paths. This should match the existing behavior of ingestion and retrieval artifact writers.

The quick-validation convention should use repository-local paths:

```text
tmp/
  runs/
    quick_validation/
      <report_id>/
        pages.jsonl
        chunks.jsonl
        retrieval_probe.json
        prompt_payloads/
        raw_llm_responses/
        parsed_llm_responses/
        extraction_result.json
        run_metadata.json
```

Phase 9 only needs to define and exercise the skeleton. Later phases will add `document_map.json`, `statement_map.json`, `row_inventory.json`, and `catalog_mapping.json`.

### Raw LLM Archival On Parse Failure

The LLM transport path must archive the raw provider response even when:

- provider content is malformed JSON
- expected schema fields are missing
- response shape is unexpected
- parsed response construction fails

The raw artifact should be available for review together with a structured parse/transport error. API key values must never be written to artifacts.

### Fake/No-Network Demo Path

Phase 9 should keep a no-network path available. It can be a small helper, documented command sequence, or CLI-adjacent skeleton that proves nested quick-validation artifact directories can be populated without real provider access.

The fake path does not need to produce correct financial extraction. It only needs to prove artifact wiring and contract behavior.

## Artifacts

Minimum Phase 9 artifacts:

- `chunks.jsonl`
- `retrieval_probe.json`
- `raw_llm_responses/*.json`
- `parsed_llm_responses/*.json` when parsing succeeds
- `extraction_result.json` or structured error result
- `run_metadata.json`

Recommended metadata fields:

- `run_id`
- `report_id`
- `source_pdf_path` when available
- `source_pdf_hash` when available
- `parser_name`
- `parser_version`
- `chunker_version`
- `prompt_version`
- `schema_version`
- `provider`
- `model`
- `base_url`
- `artifacts`
- `errors`

## Test Strategy

Phase 9 tests should be focused and synthetic:

- Build a chunk with multiple blocks where the alias appears in the second block; retrieval evidence must cite the second block.
- Write chunks to a nested path; parent directories must be created.
- Inject a malformed OpenAI-compatible response; raw response must be archived.
- Exercise a quick-validation skeleton path under a temporary directory; artifacts must be placed under the expected nested run directory.

Tests must not require network or real PDF tooling.

## Success Criteria

Phase 9 is complete when:

- All known review findings for retrieval evidence, chunk output directories, and raw LLM archival are fixed.
- Focused tests cover each fix.
- The quick-validation run layout is defined and testable.
- Fake/no-network artifact generation can run under `tmp/runs/quick_validation/<report_id>/` or an equivalent temporary test path.
- `uv run pytest -v`, `uv run ruff check .`, and `uv run mypy src tests` pass or any local tool limitation is documented.
