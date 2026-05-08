# Phase I-D: LLM Field Extraction Smoke Test Spec

> Date: 2026-05-08
> Status: Draft
> Roadmap phase: Phase I prelude (D = framework verification before A = HK notes extraction)

## Goal

Verify the LLM extraction framework is end-to-end functional by running a smoke test against a known-clean field (00001 `revenue` = 280,036M HKD). Cover both fake-LLM (deterministic, always-on) and real-LLM (DeepSeek/Ollama, opt-in) code paths. Produce a reusable `llm_field_extraction.py` module that subsequent Phase I-A (HK notes extraction) builds on.

This is the smallest test that verifies: prompt construction, chunk packaging, transport invocation, JSON schema parsing, error handling, and raw response archival all work together.

## Non-Goals

- HK notes-level extraction (Phase I-A, separate spec)
- Replay pipeline integration (Phase I later)
- Per-field prompt tuning (use one generic prompt; tuning comes when notes extraction surfaces specific failures)
- Concurrent multi-field extraction (single field, single chunk batch)
- Cross-field consistency review (existing `llm_review.py` covers that)

## Architecture

### New module

`src/financial_report_llm_extractor/llm_field_extraction.py`

```python
PROMPT_VERSION = "field-extraction-v1"
SCHEMA_VERSION = "field-extraction-result-v1"


@dataclass(frozen=True)
class FieldExtractionRequest:
    field_id: str
    field_description: str       # from taxonomy.description
    statement_type: str          # from taxonomy.statement_type
    value_type: str              # "money" | "number" | "text"
    chunks: tuple[dict, ...]     # selected chunk records (page_start, page_end, text)
    expected_currency: str | None    # hint from source_mapping (e.g., "HKD")
    expected_unit: str | None        # hint from source_mapping (e.g., "raw")


@dataclass(frozen=True)
class FieldExtractionResult:
    field_id: str
    status: Literal["present", "not_found", "extraction_failed"]
    value: str | None            # raw string value LLM returned
    parsed_numeric_value: Decimal | None
    currency: str | None
    unit: str | None
    period: str | None
    page: int | None
    statement_line: str | None   # exact PDF line text
    confidence: float | None
    reasoning: str | None
    raw_response: dict[str, object]
    errors: tuple[str, ...]


def build_field_extraction_prompt(request: FieldExtractionRequest) -> dict[str, object]:
    """Build deterministic LLM prompt payload. Returns JSON-serializable dict."""


def run_field_extraction(
    request: FieldExtractionRequest,
    client: JsonClient,
    raw_response_dir: Path | None = None,
) -> FieldExtractionResult:
    """Call LLM, parse response, archive raw payload if dir given."""
```

`JsonClient` Protocol matches existing `llm_review.JsonReviewClient` and `llm_transport.LlmJsonClient` — has `complete_json(system, payload, schema_name) -> dict`.

### Prompt schema

System prompt (constant):
```
You extract financial report field values from PDF chunks.
Return strictly valid JSON matching the requested schema.
If the field value is not present in the provided chunks, return found=false.
Never fabricate values. Cite the page and exact statement line text from the chunks.
```

User payload:
```json
{
  "prompt_version": "field-extraction-v1",
  "schema_version": "field-extraction-result-v1",
  "task": "extract_field_value",
  "field": {
    "field_id": "revenue",
    "description": "<from taxonomy.fields[field_id].description>",
    "statement_type": "income_statement",
    "value_type": "money",
    "expected_currency": "HKD",
    "expected_unit": "raw"
  },
  "chunks": [
    {"chunk_id": "...", "page_start": 1, "page_end": 1, "text": "..."},
    ...
  ],
  "response_schema": {
    "type": "object",
    "required": ["field_id", "found"],
    "properties": {
      "field_id": {"type": "string"},
      "found": {"type": "boolean"},
      "value": {"type": ["string", "null"]},
      "currency": {"type": ["string", "null"]},
      "unit": {"type": ["string", "null"]},
      "period": {"type": ["string", "null"]},
      "page": {"type": ["integer", "null"]},
      "statement_line": {"type": ["string", "null"]},
      "confidence": {"type": ["number", "null"]},
      "reasoning": {"type": ["string", "null"]}
    }
  }
}
```

### Field metadata source

Pull from `field_catalog/turtle_v015_field_taxonomy.json` via existing `load_field_taxonomy()`. Fields needed:
- `description` → prompt `field.description`
- `statement_type` → prompt `field.statement_type`
- `value_type` → prompt `field.value_type`

Pull from `field_catalog/turtle_v015_source_mapping_minimal.json` for hints:
- `currency_requirement` (informational)
- Use AKShare known currency/unit context if available (e.g., "CNY/raw" for CN)

### Chunk fixture

`tests/fixtures/pdf_chunks/00001_2025_chunks.jsonl` — generated once from `downloads/...00001...pdf`. Source the income statement page subset (use `statement_type` filter).

`tests/fixtures/pdf_chunks/00001_2025_run_metadata.json` — corresponding metadata.

Generate via existing CLI:
```bash
financial-report-llm-extractor ingest --pdf <path> --out tmp/...
financial-report-llm-extractor chunk --pages tmp/.../pages.jsonl --metadata tmp/.../run_metadata.json --out tests/fixtures/pdf_chunks/00001_2025_chunks.jsonl
```

Filter or trim if file is too large for a fixture; smoke test only needs income statement chunks for revenue.

## Test Strategy

### Layer 1: Unit (FakeLlmClient, no fixture)
File: `tests/test_llm_field_extraction.py`

Tests:
- `test_build_prompt_includes_field_description_and_chunks`
- `test_run_extraction_with_canned_present_response_returns_present_result`
- `test_run_extraction_with_canned_not_found_response_returns_not_found`
- `test_run_extraction_with_malformed_response_returns_extraction_failed_with_errors`
- `test_run_extraction_archives_raw_response_when_dir_given`

Use a `FakeJsonClient` that returns pre-canned JSON dicts.

### Layer 2: Integration (FakeLlmClient + real fixture)
Same test file.

Tests:
- `test_run_extraction_with_real_chunks_and_canned_response_succeeds` — load `tests/fixtures/pdf_chunks/00001_2025_chunks.jsonl`, build request, FakeLlmClient returns canned `{found: true, value: "280036000000", ...}`, assert FieldExtractionResult.value matches.

This proves the chunk packaging path works against actual chunk records.

### Layer 3: Real LLM smoke (opt-in)
File: `scripts/run-llm-field-extraction-smoke.sh` (new)

Gated on `REAL_LLM_SMOKE=1`. Reads `LLM_CONFIG=<llm_config.json>` (existing convention from `llm_transport.py`).

Behavior:
- Loads 00001 chunks fixture
- Builds revenue request
- Calls real DeepSeek (or whatever provider config points to)
- Asserts `result.parsed_numeric_value` is within ±5% of 280,036,000,000 (LLM value tolerance)
- Archives raw response to `tmp/runs/llm_smoke/`

Provide `tests/test_llm_field_extraction.py::test_real_llm_smoke_when_enabled` that:
- Skips if `REAL_LLM_SMOKE != "1"` (use `pytest.mark.skipif`)
- Otherwise reads config from `LLM_CONFIG_PATH` env, runs smoke, asserts within tolerance

## Acceptance Criteria

- 5+ new unit tests pass against FakeLlmClient
- 1 integration test passes against real chunk fixture
- 1 real-LLM smoke test passes when `REAL_LLM_SMOKE=1` and DeepSeek (or Ollama) configured
- Real-LLM test cleanly skips when env unset; doesn't fail CI
- `uv run pytest -v` all green (450 + ~6 new = ~456)
- `uv run ruff check .` clean
- Raw responses archived to `tmp/runs/llm_smoke/` when smoke runs

## Risk and Mitigation

**Risk:** LLM returns numeric value as string with formatting variations ("280,036,000,000" or "168.84B" or "168838.10百万元"). Mitigation: result includes both raw `value` (string as returned) and `parsed_numeric_value` (Decimal after best-effort parse). Smoke test asserts on parsed value with tolerance.

**Risk:** Real LLM fails intermittently or returns nondeterministic output. Mitigation: smoke test is opt-in only, never in default `pytest`. Tolerance band ±5% absorbs minor LLM variance. Multiple retries via `LlmTransportConfig.max_retries`.

**Risk:** Chunk fixture too large for repo (PDFs are big). Mitigation: filter chunks to income statement pages only for revenue smoke. Target <100KB JSONL.

**Risk:** Prompt design doesn't generalize to notes extraction. Acceptance: this is just smoke; Phase I-A may evolve the prompt for notes-specific patterns. The `prompt_version` field allows future schema upgrades.

## Implementation Sketch

5 tasks:

1. Generate 00001 chunks fixture (via existing CLI, one-time, committed)
2. Implement `llm_field_extraction.py` module (request, result, prompt builder, runner)
3. Add unit tests against FakeJsonClient
4. Add integration test against real chunk fixture
5. Add opt-in real-LLM smoke test + script

Detailed plan in companion plan doc.

## Verification Commands

```bash
uv run pytest tests/test_llm_field_extraction.py -v
uv run pytest -v
uv run ruff check .

# Real LLM smoke (requires API key)
REAL_LLM_SMOKE=1 LLM_CONFIG_PATH=path/to/llm_config.json scripts/run-llm-field-extraction-smoke.sh
```
