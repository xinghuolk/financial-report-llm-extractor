# Field-First Retrieval Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate that full-PDF evidence indexing plus field-first retrieval can find core financial fields without relying on statement discovery as a hard gate.

**Architecture:** Add a small experimental evidence index and field-first retriever beside the existing statement-first path. Default tests use synthetic adversarial chunks and no LLM. A separate opt-in script reports metrics on a local real PDF without changing production extraction behavior.

**Tech Stack:** Python 3.11, pytest, JSONL artifacts, existing CLI artifacts, Bash.

---

### Task 1: Evidence Index Contract

**Files:**
- Create: `src/financial_report_llm_extractor/evidence_index.py`
- Create: `tests/test_field_first_retrieval.py`

- [x] Write a failing test that builds an evidence index from `chunks.jsonl` records.

Use a tiny fixture with block and chunk records:

```python
def test_build_evidence_index_reads_block_level_evidence() -> None:
    records = [
        {
            "record_type": "chunk",
            "chunk_id": "page_p0001",
            "kind": "page_text",
            "statement_kind": None,
            "page_start": 1,
            "page_end": 1,
            "block_ids": ["p0001_b0001"],
            "block_texts": {"p0001_b0001": "Revenue 100 90"},
            "text": "Revenue 100 90",
        }
    ]

    index = build_evidence_index(records)

    assert len(index.blocks) == 1
    block = index.blocks[0]
    assert block.block_id == "p0001_b0001"
    assert block.page == 1
    assert block.chunk_id == "page_p0001"
    assert block.numeric_token_count == 2
    assert block.year_count == 0
```

- [x] Run `uv run pytest tests/test_field_first_retrieval.py::test_build_evidence_index_reads_block_level_evidence -v`.
- [x] Implement `EvidenceBlock`, `EvidenceIndex`, and `build_evidence_index(records)`.
- [x] Run the same test and confirm it passes.

### Task 2: Field-First Retriever

**Files:**
- Modify: `src/financial_report_llm_extractor/evidence_index.py`
- Create: `src/financial_report_llm_extractor/field_first_retrieval.py`
- Modify: `tests/test_field_first_retrieval.py`

- [x] Write a failing test where noisy MD&A text contains statement-like words but the real field rows are plain blocks.

The test should assert that selected fields are found without requiring `statement_kind`:

```python
def test_field_first_retrieval_finds_core_fields_without_statement_gate() -> None:
    records = adversarial_field_first_records()
    index = build_evidence_index(records)

    result = retrieve_field_first(
        index,
        selected_fields=(
            "revenue",
            "net_profit",
            "total_assets",
            "total_liabilities",
            "operating_cash_flow",
        ),
        top_k=3,
    )

    statuses = {field["field_id"]: field["status"] for field in result["fields"]}
    assert statuses == {
        "revenue": "candidates_found",
        "net_profit": "candidates_found",
        "total_assets": "candidates_found",
        "total_liabilities": "candidates_found",
        "operating_cash_flow": "candidates_found",
    }
    for field in result["fields"]:
        candidate = field["candidates"][0]
        assert candidate["evidence"]["page"] > 0
        assert candidate["evidence"]["block_id"]
        assert candidate["evidence"]["snippet"]
```

- [x] Run the test and confirm it fails because `retrieve_field_first` does not exist.
- [x] Implement `retrieve_field_first(index, selected_fields, top_k=8)`.
- [x] Scoring must use existing aliases from `retrieval.FIELD_HINTS`, numeric density, year/unit hints, and optional statement kind bonus.
- [x] Run `uv run pytest tests/test_field_first_retrieval.py -v`.

### Task 3: Statement-First Failure Contrast

**Files:**
- Modify: `tests/test_field_first_retrieval.py`

- [x] Add a test showing the same adversarial fixture is unsafe for statement-first gating.

Expected assertion shape:

```python
def test_adversarial_fixture_demonstrates_statement_first_risk() -> None:
    records = adversarial_field_first_records()
    statement_chunks = [
        record
        for record in records
        if record.get("record_type") == "chunk"
        and record.get("kind") == "statement_table"
    ]

    assert len(statement_chunks) < 3
```

- [x] Run `uv run pytest tests/test_field_first_retrieval.py -v`.
- [x] If this test is too tied to chunk internals, adjust fixture records rather than production statement discovery.

### Task 4: Prompt Budget Metrics

**Files:**
- Modify: `src/financial_report_llm_extractor/field_first_retrieval.py`
- Modify: `tests/test_field_first_retrieval.py`

- [x] Add `estimate_prompt_budget(result)` that returns per-field and total candidate text characters.
- [x] Write a test asserting top-k retrieval for the adversarial fixture stays below `12_000` characters.
- [x] Run `uv run pytest tests/test_field_first_retrieval.py -v`.

### Task 5: Optional Real-PDF Metrics Script

**Files:**
- Create: `scripts/run-field-first-validation.sh`
- Modify: `tests/test_field_first_retrieval.py`

- [x] Add a test asserting the script exists and mentions `quick-validate`, `field-first`, and no LLM command.
- [x] Implement script defaults:

```bash
PDF="${PDF:-downloads/hk_stocks/00001/annual/2025_annual_en.pdf}"
REPORT_ID="${REPORT_ID:-00001_2025_en}"
ROOT="${ROOT:-.}"
SELECTED_FIELDS="${SELECTED_FIELDS:-revenue,net_profit,total_assets,total_liabilities,operating_cash_flow}"
```

- [x] Script should run `quick-validate`, then call a small Python one-liner/module to print:
  - selected fields
  - status per field
  - top candidate page/block
  - per-field prompt chars
  - total prompt chars
- [x] It must not call `discover-rows-llm`, `extract`, or any network provider.
- [x] Run `bash -n scripts/run-field-first-validation.sh`.

### Task 6: Documentation

**Files:**
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
- Modify: `docs/design/2026-04-30-llm-first-turtle-financial-extraction-design.md`

- [x] Document that statement discovery is an optional ranking signal, not the required main gate, if validation passes.
- [x] Document that full PDF enters the local evidence index, while LLM prompts remain top-k bounded.

### Task 7: Verification

- [x] Run `uv run pytest tests/test_field_first_retrieval.py -v`.
- [x] Run `uv run pytest -v`.
- [x] Run `uv run ruff check .`.
- [x] Run `uv run mypy src tests`.
- [x] Run `git diff --check`.

### Task 8: Commit

- [x] Commit with `test: validate field-first retrieval path`.
