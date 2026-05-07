# Phase E Turtle Mapping, Derivation, And Coverage Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic source-to-Turtle mapping, minimal derivation, and reviewable coverage artifacts for fixture-backed AKShare/Yahoo inventory.

**Architecture:** Create a focused `structured_sources/mapping.py` module that converts `SourceInventoryRecord` rows into mapped Turtle fields using `SourceMappingCatalog`. Reuse the existing money normalizer and source evidence contracts, then write JSON/Markdown summaries for downstream review and later PDF/LLM fallback.

**Tech Stack:** Python 3.11 standard library, dataclasses, pytest, existing `structured_sources` contracts.

---

### Task 1: Direct Source-To-Turtle Mapping

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/mapping.py`
- Test: `tests/test_source_mapping.py`

- [x] **Step 1: Write failing tests**

Create tests for a single valid AKShare row mapping to `revenue`, including normalized money and source evidence, and for a missing field that has no candidate rows.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_source_mapping.py::test_map_source_inventory_maps_present_money_field tests/test_source_mapping.py::test_map_source_inventory_marks_missing_field -v`
Expected: FAIL because `structured_sources.mapping` does not exist.

- [x] **Step 3: Implement minimal mapper**

Implement:

- `TurtleMappingCandidate`
- `MappedTurtleField`
- `TurtleMappingResult`
- `map_source_inventory(catalog, records)`

The mapper must match `raw_field_name` or `raw_field_code` against each entry's `source_aliases`, validate source records, normalize money using `normalize_money(str(raw_value), unit_context=f"{currency} {unit}")`, and return `present` for exactly one valid candidate.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_source_mapping.py -v`
Expected: PASS for Task 1 tests.

### Task 2: Ambiguity And Derived Fields

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/mapping.py`
- Test: `tests/test_source_mapping.py`

- [x] **Step 1: Write failing tests**

Add tests for:

- two valid candidates for one field produce `ambiguous`;
- an inline catalog entry with `derivation="total_assets - total_liabilities"` produces a derived money field when both inputs are present and compatible.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_source_mapping.py::test_map_source_inventory_marks_multiple_candidates_ambiguous tests/test_source_mapping.py::test_map_source_inventory_derives_money_field_from_compatible_inputs -v`
Expected: FAIL because ambiguity and derivation are not implemented.

- [x] **Step 3: Implement ambiguity and derivation**

For direct matches:

- zero valid candidates -> `missing`;
- one valid candidate -> `present`;
- more than one valid candidate -> `ambiguous`.

For derivation:

- support `<field_id> - <field_id>`;
- require both input mapped fields to be `present` or `derived`;
- require same currency, unit, period, and scope;
- combine all input source evidence.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_source_mapping.py -v`
Expected: PASS.

### Task 3: Mapping And Coverage Artifact Writers

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/mapping.py`
- Test: `tests/test_source_mapping.py`

- [x] **Step 1: Write failing tests**

Add a test for `write_turtle_mapping_artifacts(result, output_dir)` that writes:

- `turtle_mapping.json`
- `source_coverage_summary.json`
- `source_coverage_summary.md`

The summary must include total fields, status counts, and blocker fields for `missing` and `ambiguous`.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_source_mapping.py::test_write_turtle_mapping_artifacts_writes_json_and_markdown -v`
Expected: FAIL because the writer does not exist.

- [x] **Step 3: Implement artifact writer**

Serialize mapping candidates and mapped fields with deterministic key ordering. Markdown should contain a compact status table and blocker list.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_source_mapping.py -v`
Expected: PASS.

### Task 4: Verification

- [x] **Step 1: Run source-first tests**

```bash
uv run pytest tests/test_source_mapping.py tests/test_source_coverage.py tests/test_source_artifacts.py tests/test_akshare_adapter.py tests/test_yahoo_adapter.py -v
```

Expected: PASS.

- [x] **Step 2: Run full verification**

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
git diff --check
```

Expected: PASS.
