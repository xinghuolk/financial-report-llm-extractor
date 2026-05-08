# Phase I-A: LLM-Assisted Notes Field Extraction Spec

> Date: 2026-05-08
> Status: Draft
> Roadmap phase: Phase I-A (Bucket 3, after Phase I-D smoke validation)
> Predecessor: Phase I-D smoke test, Phase I-A feasibility demo

## Goal

Implement a generalizable LLM-assisted field extraction pipeline that
handles fields the source-first replay leaves as `source_unavailable` or
`mapping_expansion_required` — particularly HK fields whose values live in
notes / MD&A rather than main statements.

The pipeline must work on **any** company's PDF without code changes or
per-company adaptation. New issuer onboarding requires only dropping a PDF
into the input directory and rerunning.

## Non-Goals

- Replacing source-first as the primary path. LLM extraction supplements,
  never overrides, source-first results.
- Per-field prompt tuning beyond using `pdf_aliases` and
  `taxonomy.description`. (YAGNI: tuning comes when field-specific
  failures appear.)
- Auto-triggered LLM extraction inside `provider_baseline_replay`. The
  pipeline runs as a separate CLI step that produces an artifact replay
  can consume (option Z half-integration).
- LLM-driven chunk discovery (TOC parsing, two-stage LLM calls).
  Demo proved alias scoring + statement-type filtering is sufficient.
- Concurrent multi-company extraction. Single PDF, single field iteration
  loop. Performance optimization is a Phase I-B follow-up.
- Captured LLM response fixtures for replay testing. Tests use FakeJsonClient.

## Demo evidence

`scripts/phase_i_a_demo/REPORT.md` validated the approach:
- 6 HK companies × 2 fields = 12 (company, field) pairs
- 11 returned correct values; 1 confirmed real `not_found`
- Zero code changes between companies
- LLM correctly handled bilingual labels, RMB'000 notation, 5-year
  history tables, MD&A free text, and "Debtors" as trade receivables
  alias for real-estate developers

## Architecture

### New module

`src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py`

```python
@dataclass(frozen=True)
class LlmExtractionTarget:
    field_id: str
    field_description: str       # from taxonomy.description
    statement_type: str          # from taxonomy.statement_type
    value_type: str              # from taxonomy.value_type
    aliases: tuple[str, ...]     # from source_mapping.pdf_aliases (lowercased)
    chunk_strategy: Literal["alias_top_k", "broad_keyword"]
    expected_currency: str | None
    expected_unit: str | None


@dataclass(frozen=True)
class LlmExtractionRunResult:
    pdf_path: Path
    company_id: str
    chunk_count: int
    fields_attempted: tuple[str, ...]
    fields_present: tuple[str, ...]
    fields_not_found: tuple[str, ...]
    fields_failed: tuple[str, ...]
    artifact_path: Path  # llm_evidence_supplement.json
```

Public functions:

- `derive_targets(catalog, taxonomy, *, priorities=("P0", "P1"))` —
  enumerate fields where pdf_aliases exist; build LlmExtractionTarget per field.
- `select_chunks(chunks, target, *, top_k_standard=8, broad_limit=30)` —
  apply alias_top_k or broad_keyword strategy.
- `run_extraction(pdf_path, company_id, catalog, taxonomy, client, *,
  out_dir, fields=None, max_chars_per_chunk=2000)` — full pipeline:
  ingest → chunk → derive_targets → for each target: select_chunks →
  build FieldExtractionRequest → run_field_extraction → collect results.
- `write_llm_evidence_supplement(out_dir, results)` — produce
  `llm_evidence_supplement.json` listing all extracted values + raw evidence.

### Chunk selection strategy

Field's `chunk_strategy` is derived from `field_id` heuristics:
- If `pdf_aliases` ≥ 3 distinct standardized terms → `alias_top_k` (8 chunks)
- Otherwise → `broad_keyword` (≤ 30 chunks containing any token from
  `pdf_aliases` plus statement_type-typed chunks)

This is a pure function of catalog metadata. No per-field code.

### LLM extraction primitive

Reuses `llm_field_extraction.py` (Phase I-D) unchanged:
- `FieldExtractionRequest` / `FieldExtractionResult`
- `build_field_extraction_prompt()` / `run_field_extraction()`
- `unwrap_llm_content()` for OpenAI/Gemini transport unwrapping

### Output artifact

`llm_evidence_supplement.json` schema:

```json
{
  "schema_version": "llm-evidence-supplement-v1",
  "company_id": "00001",
  "pdf_path": "downloads/hk_stocks/00001/annual/2025_annual_en.pdf",
  "extracted_at": "2026-05-08T...",
  "items": {
    "accounts_receiv": {
      "status": "present",
      "value": "18283",
      "parsed_numeric_value": "18283",
      "currency": "HKD",
      "unit": "million",
      "page": 229,
      "statement_line": "Trade receivables (continued)...",
      "confidence": 0.95,
      "reasoning": "...",
      "raw_response_path": "tmp/runs/.../00001/accounts_receiv/...json"
    },
    ...
  }
}
```

### CLI command

```
financial-report-llm-extractor extract-llm \
  --pdf <path> \
  --company-id <id> \
  --catalog field_catalog/turtle_v015_source_mapping_minimal.json \
  --taxonomy field_catalog/turtle_v015_field_taxonomy.json \
  --llm-config <llm_config.json> \
  --out tmp/runs/llm_extraction/<company_id>/ \
  --fields accounts_receiv,acct_payable,...   # optional, default = all targets
```

Required env: `REAL_LLM_SMOKE=1` is NOT required; this command always
calls real LLM (it's the productive pipeline, not a test gate). API key
read from `llm_config.api_key_env`.

### Replay integration (option Z)

`provider_baseline_replay.py` checks for `llm_evidence_supplement.json`
under the company's directory. If present, merges items into export:
- For items where source-first export status is `source_unavailable` /
  `mapping_expansion_required` AND LLM result is `present`:
  - Set export item value/currency/unit from LLM
  - Set `pdf_evidence` to LLM evidence record
  - Add `llm_supplemented` to review_notes
  - Keep `source_evidence` empty (not from a provider)

Replay does NOT call LLM itself. The artifact must be generated
beforehand by `extract-llm` CLI.

## Validation slice

Apply to:
- 6 HK companies: 00001, 01113, 01810, 02498, 06862, 09987
- 6 target fields: accounts_receiv, acct_payable, rd_exp, fv_value_chg_gain,
  bond_payable, invest_income (initial selection — pipeline supports more)

Exit criteria:
- ≥ 80% of (company, field) pairs produce expected status:
  - `present` with verifiable PDF evidence, OR
  - `not_found` for fields the company genuinely doesn't disclose
- All extractions cite an actual PDF page; manual spot-check on 6 random
  pairs confirms PDF text matches LLM citation
- Code is fully field-driven from catalog; no hardcoded company logic
- Drop a 7th unseen HK company PDF → pipeline runs without modification

## Test strategy

### Unit tests (FakeJsonClient, in-memory chunks)

`tests/test_llm_extraction_runner.py`:

1. `test_derive_targets_uses_taxonomy_description`
2. `test_derive_targets_filters_to_priorities`
3. `test_derive_targets_skips_fields_without_pdf_aliases`
4. `test_select_chunks_alias_top_k_returns_score_ordered`
5. `test_select_chunks_broad_keyword_includes_statement_type_chunks`
6. `test_run_extraction_iterates_targets_and_collects_results`
7. `test_run_extraction_writes_llm_evidence_supplement`

### Integration test (FakeJsonClient + real fixture)

`test_run_extraction_against_00001_fixture_with_canned_responses` — uses
existing `tests/fixtures/pdf_chunks/00001_2025_chunks.jsonl` (12 chunks)
and FakeJsonClient with canned per-field responses; verifies the runner
correctly orchestrates ingest → select → extract → write.

### Opt-in real LLM smoke

`scripts/run-phase-i-a-smoke.sh` runs the CLI against 1 HK PDF
(00001) with all 6 target fields. Gated on `REAL_LLM_SMOKE=1`.
Asserts artifact is produced; spot-check of 1 field within tolerance.

### Demo coverage (already exists, not duplicated)

`scripts/phase_i_a_demo/run_demo.py` covers 6 companies × 2 fields. Will
be retained as a parallel exploration script. Phase I-A productive
pipeline replaces it for production use.

## File structure

| File | Responsibility |
|------|----------------|
| `src/.../structured_sources/llm_extraction_runner.py` | Orchestrator: derive_targets, select_chunks, run_extraction, write artifact |
| `src/.../cli.py` (modify) | New `extract-llm` subcommand |
| `src/.../structured_sources/provider_baseline_replay.py` (modify) | Detect and merge llm_evidence_supplement.json into export |
| `src/.../structured_sources/export.py` (modify) | Optional: add `llm_evidence` field to SourceFirstExportItem |
| `tests/test_llm_extraction_runner.py` | Unit + integration tests |
| `scripts/run-phase-i-a-smoke.sh` | Opt-in real-LLM smoke runner |

## Out-of-scope but anticipated follow-ups

- **Phase I-A.2**: tune for field-specific failure modes when they
  surface. Mechanism: optional `llm_extraction_override` block in
  source_mapping (chunk_strategy override, extra_aliases). YAGNI until
  failures observed.
- **Phase I-A.3**: concurrent multi-company runner for batch onboarding.
- **Phase I-A.4**: confidence calibration — collect LLM confidence vs
  human-verified accuracy; gate `present` promotion on confidence
  threshold.
- **Phase I-B**: cross-source consistency check. When source provides a
  value AND LLM provides a different value, raise consistency conflict.

## Risks

**Risk:** LLM unit/value normalization variance (demo showed 24,050.5
million vs 24,050,500,000 confusion for Xiaomi rd_exp). 
Mitigation: `parsed_numeric_value` in result; downstream money_normalizer
handles unit conversion based on returned `unit` field. Don't trust
`parsed_numeric_value` for cross-unit comparison.

**Risk:** Catalog metadata may lack good `description` or
`pdf_aliases` for some fields. Mitigation: `derive_targets` skips
fields with empty pdf_aliases, surfacing them in run summary as
"unconfigured." Operator adds aliases via catalog edit (one-time, not
per-company).

**Risk:** Token budget. 6 fields × 30 chunks × ~2000 chars = ~360KB per
company per run. DeepSeek context window is 128K, well within bounds.
For larger field sets, may need batching.

**Risk:** Cost. Each call ~3000 tokens prompt + ~500 tokens response. 6
companies × 6 fields = 36 calls × ~$0.001 each = ~$0.04 per full run on
DeepSeek. Acceptable.

**Risk:** Replay merge collisions when LLM produces a value for a field
that source-first already has clean. Mitigation: replay merge only
applies LLM value when source-first status is `source_unavailable` or
`mapping_expansion_required`. Never overrides clean source values.

## Verification commands

```bash
# Unit + integration tests
uv run pytest tests/test_llm_extraction_runner.py -v
uv run pytest -v
uv run ruff check .

# Real-LLM smoke (opt-in)
set -a; source .env; set +a
REAL_LLM_SMOKE=1 LLM_CONFIG_PATH=tmp/llm_configs/deepseek.json \
  scripts/run-phase-i-a-smoke.sh

# Production extraction for 1 company
uv run financial-report-llm-extractor extract-llm \
  --pdf downloads/hk_stocks/00001/annual/2025_annual_en.pdf \
  --company-id 00001 \
  --catalog field_catalog/turtle_v015_source_mapping_minimal.json \
  --taxonomy field_catalog/turtle_v015_field_taxonomy.json \
  --llm-config tmp/llm_configs/deepseek.json \
  --out tmp/runs/llm_extraction/00001
```

## Acceptance criteria

- New module + CLI compile and pass tests
- Unit tests: ≥ 7 covering target derivation, chunk selection, runner orchestration
- Integration test: 1 against 00001 chunks fixture
- Smoke runner: CLI works against 1 HK PDF + DeepSeek
- Artifact `llm_evidence_supplement.json` is produced and well-formed
- Replay correctly merges supplement when present (test against fixture)
- All 459 existing tests still pass + new tests pass + ruff clean
- Demo script (`scripts/phase_i_a_demo/`) retained but not modified
- Roadmap updated with Phase I-A implementation result

## Implementation phases (one plan covers all)

1. Module scaffold: dataclasses, `derive_targets`, `select_chunks`
2. `run_extraction` orchestrator + tests
3. `write_llm_evidence_supplement` + JSON schema
4. CLI command wiring
5. Replay merge integration
6. Smoke script + opt-in real-LLM test
7. Validation against 6 HK companies × 6 target fields
8. Roadmap update
