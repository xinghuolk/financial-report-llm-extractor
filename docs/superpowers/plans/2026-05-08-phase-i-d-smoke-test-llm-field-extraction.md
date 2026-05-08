# Phase I-D LLM Field Extraction Smoke Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify LLM extraction framework end-to-end by extracting 600519 `revenue` from a PDF chunk fixture; deliver `llm_field_extraction.py` module + 3 layers of tests (unit, integration, opt-in real LLM smoke).

**Architecture:** New module `llm_field_extraction.py` builds a deterministic JSON-schema prompt from (field_id, taxonomy metadata, chunks), calls injected `JsonClient`, parses bounded result, archives raw response. Reuses existing `LlmJsonClient` Protocol (has `complete_json()`). Chunk fixture committed to `tests/fixtures/pdf_chunks/`. Real LLM smoke gated on `REAL_LLM_SMOKE=1`.

**Tech Stack:** Python 3.11 stdlib, frozen dataclasses, Protocol, pytest, existing `LlmJsonClient`/`UrllibHttpTransport`/`OpenAiCompatibleClient`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/financial_report_llm_extractor/llm_field_extraction.py` | Module: request/result dataclasses, prompt builder, runner |
| `tests/fixtures/pdf_chunks/600519_2025_chunks.jsonl` | Income-statement chunks for 600519 (committed fixture) |
| `tests/fixtures/pdf_chunks/600519_2025_run_metadata.json` | Run metadata for the chunks |
| `tests/test_llm_field_extraction.py` | Unit + integration tests + opt-in real LLM smoke |
| `scripts/run-llm-field-extraction-smoke.sh` | Opt-in real LLM smoke runner |

---

## Task 1: Generate 600519 income statement chunks fixture

**Files:**
- Create: `tests/fixtures/pdf_chunks/600519_2025_chunks.jsonl`
- Create: `tests/fixtures/pdf_chunks/600519_2025_run_metadata.json`

This is a one-time fixture generation, not a TDD step.

- [ ] **Step 1: Locate 600519 PDF**

```bash
ls downloads/ | head -20
find downloads -name '*600519*' -type f
```
Expected: a 600519 annual report PDF in `downloads/` (likely `downloads/cn_stocks/600519/...` or similar). If multiple, pick the 2024 or 2025 annual report. If not present, STOP and ask user where to source it.

- [ ] **Step 2: Run ingestion to a temp directory**

```bash
PDF_PATH=$(find downloads -name '*600519*annual*' -type f | head -1)
mkdir -p tmp/runs/600519_chunks_gen
uv run financial-report-llm-extractor ingest \
  --pdf "$PDF_PATH" \
  --out tmp/runs/600519_chunks_gen
```
Expected: produces `tmp/runs/600519_chunks_gen/pages.jsonl` and `tmp/runs/600519_chunks_gen/run_metadata.json`.

- [ ] **Step 3: Run chunking**

```bash
uv run financial-report-llm-extractor chunk \
  --pages tmp/runs/600519_chunks_gen/pages.jsonl \
  --metadata tmp/runs/600519_chunks_gen/run_metadata.json \
  --out tmp/runs/600519_chunks_gen/chunks.jsonl
```
Expected: produces `chunks.jsonl` with all logical chunks.

- [ ] **Step 4: Filter to income statement chunks only**

The fixture should be small (target <100KB). Filter chunks where `statement_type == "income_statement"` or chunks containing the income statement page. Use a one-shot Python filter:

```bash
uv run python3 -c "
import json
income_chunks = []
with open('tmp/runs/600519_chunks_gen/chunks.jsonl') as f:
    for line in f:
        rec = json.loads(line)
        # Accept statement chunks marked income_statement OR page chunks for income statement pages
        if rec.get('statement_type') == 'income_statement':
            income_chunks.append(rec)
        elif rec.get('chunk_kind') == 'statement' and 'income' in (rec.get('statement_title','') or '').lower():
            income_chunks.append(rec)
print(f'filtered chunks: {len(income_chunks)}')
import os
os.makedirs('tests/fixtures/pdf_chunks', exist_ok=True)
with open('tests/fixtures/pdf_chunks/600519_2025_chunks.jsonl', 'w') as out:
    for rec in income_chunks:
        out.write(json.dumps(rec, ensure_ascii=False) + '\n')
"
```

If 0 chunks were filtered, broaden to take the first 5 chunks (likely covers the income statement) — inspect `chunks.jsonl` and pick by page range. Also check if `chunk_kind` field exists; field names may differ.

If income_statement chunks aren't available with that exact field, fall back to taking ALL chunks under 200KB total. The smoke test only needs 600519 chunks — if filtering proves brittle, just commit a small full-chunks fixture.

- [ ] **Step 5: Copy run metadata**

```bash
cp tmp/runs/600519_chunks_gen/run_metadata.json tests/fixtures/pdf_chunks/600519_2025_run_metadata.json
```

- [ ] **Step 6: Verify fixture size and content**

```bash
ls -la tests/fixtures/pdf_chunks/
wc -l tests/fixtures/pdf_chunks/600519_2025_chunks.jsonl
head -1 tests/fixtures/pdf_chunks/600519_2025_chunks.jsonl | python3 -m json.tool | head -20
```
Expected: file size <200KB. First chunk is valid JSON with `chunk_id`, page info, and text containing income-statement-like content.

If the chunks don't include the income statement (no "营业收入" text in any chunk), STOP — investigate which chunks contain revenue and adjust filter.

```bash
grep -l "营业收入" tests/fixtures/pdf_chunks/600519_2025_chunks.jsonl && echo "FOUND revenue text"
```

- [ ] **Step 7: Commit fixture**

```bash
git add tests/fixtures/pdf_chunks/600519_2025_chunks.jsonl tests/fixtures/pdf_chunks/600519_2025_run_metadata.json
git commit -m "test: add 600519 income statement chunk fixture for llm smoke"
```

---

## Task 2: FieldExtractionRequest and FieldExtractionResult dataclasses

**Files:**
- Create: `src/financial_report_llm_extractor/llm_field_extraction.py`
- Test: `tests/test_llm_field_extraction.py`

- [ ] **Step 1: Write failing test for dataclass shape**

Create `tests/test_llm_field_extraction.py`:

```python
from decimal import Decimal
from pathlib import Path

from financial_report_llm_extractor.llm_field_extraction import (
    FieldExtractionRequest,
    FieldExtractionResult,
)


def test_field_extraction_request_constructs_with_required_fields() -> None:
    req = FieldExtractionRequest(
        field_id="revenue",
        field_description="operating revenue",
        statement_type="income_statement",
        value_type="money",
        chunks=({"chunk_id": "c1", "page_start": 1, "page_end": 1, "text": "..."},),
        expected_currency="CNY",
        expected_unit="yuan",
    )
    assert req.field_id == "revenue"
    assert req.value_type == "money"
    assert len(req.chunks) == 1


def test_field_extraction_result_present_status() -> None:
    result = FieldExtractionResult(
        field_id="revenue",
        status="present",
        value="168838102514.79",
        parsed_numeric_value=Decimal("168838102514.79"),
        currency="CNY",
        unit="yuan",
        period="2025-12-31",
        page=4,
        statement_line="营业收入",
        confidence=0.95,
        reasoning="found on income statement page 4",
        raw_response={"found": True},
        errors=(),
    )
    assert result.status == "present"
    assert result.parsed_numeric_value == Decimal("168838102514.79")
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
uv run pytest tests/test_llm_field_extraction.py -v
```
Expected: ImportError — `llm_field_extraction` module does not exist.

- [ ] **Step 3: Create module skeleton with dataclasses**

Create `src/financial_report_llm_extractor/llm_field_extraction.py`:

```python
"""LLM-assisted field extraction from PDF chunks.

Used for fields where source-first providers don't have the value or
ambiguity remains after deterministic resolution. The LLM extracts a single
field's value from selected PDF chunks. Output is evidence-grounded:
must cite page and statement_line, or report not_found.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal, Protocol


PROMPT_VERSION = "field-extraction-v1"
SCHEMA_VERSION = "field-extraction-result-v1"


FieldExtractionStatus = Literal["present", "not_found", "extraction_failed"]


@dataclass(frozen=True)
class FieldExtractionRequest:
    field_id: str
    field_description: str
    statement_type: str
    value_type: str
    chunks: tuple[dict[str, object], ...]
    expected_currency: str | None = None
    expected_unit: str | None = None


@dataclass(frozen=True)
class FieldExtractionResult:
    field_id: str
    status: FieldExtractionStatus
    value: str | None = None
    parsed_numeric_value: Decimal | None = None
    currency: str | None = None
    unit: str | None = None
    period: str | None = None
    page: int | None = None
    statement_line: str | None = None
    confidence: float | None = None
    reasoning: str | None = None
    raw_response: dict[str, object] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
```

- [ ] **Step 4: Run test, verify PASS**

```bash
uv run pytest tests/test_llm_field_extraction.py -v
```
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/llm_field_extraction.py tests/test_llm_field_extraction.py
git commit -m "feat: add FieldExtractionRequest and FieldExtractionResult dataclasses"
```

---

## Task 3: Prompt builder

**Files:**
- Modify: `src/financial_report_llm_extractor/llm_field_extraction.py`
- Test: `tests/test_llm_field_extraction.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_llm_field_extraction.py`:

```python
from financial_report_llm_extractor.llm_field_extraction import (
    build_field_extraction_prompt,
    PROMPT_VERSION,
    SCHEMA_VERSION,
)


def test_build_prompt_includes_field_metadata_and_chunks() -> None:
    req = FieldExtractionRequest(
        field_id="revenue",
        field_description="operating revenue (营业收入)",
        statement_type="income_statement",
        value_type="money",
        chunks=(
            {"chunk_id": "c1", "page_start": 4, "page_end": 4, "text": "营业收入  168,838"},
        ),
        expected_currency="CNY",
        expected_unit="yuan",
    )
    payload = build_field_extraction_prompt(req)

    assert payload["prompt_version"] == PROMPT_VERSION
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["task"] == "extract_field_value"
    assert payload["field"]["field_id"] == "revenue"
    assert payload["field"]["description"] == "operating revenue (营业收入)"
    assert payload["field"]["statement_type"] == "income_statement"
    assert payload["field"]["expected_currency"] == "CNY"
    assert len(payload["chunks"]) == 1
    assert payload["chunks"][0]["text"] == "营业收入  168,838"
    # Response schema is included for the LLM to follow
    assert "response_schema" in payload
    assert "found" in payload["response_schema"]["properties"]
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
uv run pytest tests/test_llm_field_extraction.py::test_build_prompt_includes_field_metadata_and_chunks -v
```
Expected: ImportError on `build_field_extraction_prompt`.

- [ ] **Step 3: Implement prompt builder**

Append to `src/financial_report_llm_extractor/llm_field_extraction.py`:

```python
def build_field_extraction_prompt(
    request: FieldExtractionRequest,
) -> dict[str, object]:
    """Build a deterministic JSON-serializable LLM prompt payload."""
    return {
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "task": "extract_field_value",
        "field": {
            "field_id": request.field_id,
            "description": request.field_description,
            "statement_type": request.statement_type,
            "value_type": request.value_type,
            "expected_currency": request.expected_currency,
            "expected_unit": request.expected_unit,
        },
        "chunks": [
            {
                "chunk_id": str(chunk.get("chunk_id", "")),
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
                "text": str(chunk.get("text", "")),
            }
            for chunk in request.chunks
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
                "reasoning": {"type": ["string", "null"]},
            },
        },
    }


SYSTEM_PROMPT = (
    "You extract financial report field values from PDF chunks. "
    "Return strictly valid JSON matching the requested schema. "
    "If the field value is not present in the provided chunks, return found=false. "
    "Never fabricate values. Cite the page and exact statement line text from the chunks."
)
```

- [ ] **Step 4: Run test, verify PASS**

```bash
uv run pytest tests/test_llm_field_extraction.py -v
```
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ tests/
git commit -m "feat: add field extraction prompt builder"
```

---

## Task 4: Extraction runner with FakeJsonClient

**Files:**
- Modify: `src/financial_report_llm_extractor/llm_field_extraction.py`
- Test: `tests/test_llm_field_extraction.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_llm_field_extraction.py`:

```python
class FakeJsonClient:
    """In-test fake matching the JsonClient Protocol."""

    def __init__(self, response: dict[str, object]) -> None:
        self._response = response

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        return self._response


def _sample_request() -> FieldExtractionRequest:
    return FieldExtractionRequest(
        field_id="revenue",
        field_description="operating revenue",
        statement_type="income_statement",
        value_type="money",
        chunks=(
            {"chunk_id": "c1", "page_start": 4, "page_end": 4, "text": "营业收入  168,838"},
        ),
        expected_currency="CNY",
        expected_unit="yuan",
    )


def test_run_extraction_with_present_response_returns_present_result() -> None:
    from financial_report_llm_extractor.llm_field_extraction import run_field_extraction

    client = FakeJsonClient({
        "field_id": "revenue",
        "found": True,
        "value": "168838102514.79",
        "currency": "CNY",
        "unit": "yuan",
        "period": "2025-12-31",
        "page": 4,
        "statement_line": "营业收入",
        "confidence": 0.95,
        "reasoning": "found on income statement page 4",
    })

    result = run_field_extraction(_sample_request(), client)

    assert result.status == "present"
    assert result.value == "168838102514.79"
    assert result.parsed_numeric_value == Decimal("168838102514.79")
    assert result.currency == "CNY"
    assert result.page == 4
    assert result.statement_line == "营业收入"
    assert result.errors == ()


def test_run_extraction_with_not_found_response_returns_not_found() -> None:
    from financial_report_llm_extractor.llm_field_extraction import run_field_extraction

    client = FakeJsonClient({
        "field_id": "revenue",
        "found": False,
        "reasoning": "no income statement found in chunks",
    })

    result = run_field_extraction(_sample_request(), client)

    assert result.status == "not_found"
    assert result.value is None
    assert result.parsed_numeric_value is None
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
uv run pytest tests/test_llm_field_extraction.py -v
```
Expected: ImportError on `run_field_extraction`.

- [ ] **Step 3: Implement runner**

Append to `src/financial_report_llm_extractor/llm_field_extraction.py`:

```python
class JsonClient(Protocol):
    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        ...


def run_field_extraction(
    request: FieldExtractionRequest,
    client: JsonClient,
    raw_response_dir: Path | None = None,
) -> FieldExtractionResult:
    """Call LLM, parse response, optionally archive raw payload."""
    payload = build_field_extraction_prompt(request)
    raw = client.complete_json(
        system_prompt=SYSTEM_PROMPT,
        user_payload=payload,
    )

    if raw_response_dir is not None:
        raw_response_dir.mkdir(parents=True, exist_ok=True)
        archive_path = raw_response_dir / f"{request.field_id}_{PROMPT_VERSION}.json"
        archive_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return _parse_response(request, raw)


def _parse_response(
    request: FieldExtractionRequest,
    raw: dict[str, object],
) -> FieldExtractionResult:
    errors: list[str] = []

    found = raw.get("found")
    if not isinstance(found, bool):
        errors.append("response missing or invalid 'found' field")
        return FieldExtractionResult(
            field_id=request.field_id,
            status="extraction_failed",
            raw_response=raw,
            errors=tuple(errors),
        )

    if not found:
        return FieldExtractionResult(
            field_id=request.field_id,
            status="not_found",
            reasoning=_str_or_none(raw.get("reasoning")),
            raw_response=raw,
        )

    value_raw = _str_or_none(raw.get("value"))
    parsed_numeric_value: Decimal | None = None
    if value_raw is not None:
        try:
            parsed_numeric_value = Decimal(value_raw.replace(",", "").strip())
        except (InvalidOperation, ValueError):
            errors.append(f"unparseable numeric value: {value_raw!r}")

    return FieldExtractionResult(
        field_id=request.field_id,
        status="present" if not errors else "extraction_failed",
        value=value_raw,
        parsed_numeric_value=parsed_numeric_value,
        currency=_str_or_none(raw.get("currency")),
        unit=_str_or_none(raw.get("unit")),
        period=_str_or_none(raw.get("period")),
        page=_int_or_none(raw.get("page")),
        statement_line=_str_or_none(raw.get("statement_line")),
        confidence=_float_or_none(raw.get("confidence")),
        reasoning=_str_or_none(raw.get("reasoning")),
        raw_response=raw,
        errors=tuple(errors),
    )


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):  # bool is subclass of int; reject
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
uv run pytest tests/test_llm_field_extraction.py -v
```
Expected: 5 PASS (3 from before + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/ tests/
git commit -m "feat: implement run_field_extraction with response parsing"
```

---

## Task 5: Malformed response handling + raw archive

**Files:**
- Test: `tests/test_llm_field_extraction.py` (no module changes; runner already handles this)

- [ ] **Step 1: Write failing test for malformed response**

Add to `tests/test_llm_field_extraction.py`:

```python
def test_run_extraction_with_malformed_response_marks_extraction_failed() -> None:
    from financial_report_llm_extractor.llm_field_extraction import run_field_extraction

    client = FakeJsonClient({"unexpected": "shape"})  # missing 'found'

    result = run_field_extraction(_sample_request(), client)

    assert result.status == "extraction_failed"
    assert any("found" in err for err in result.errors)
    assert result.raw_response == {"unexpected": "shape"}


def test_run_extraction_with_unparseable_value_marks_extraction_failed() -> None:
    from financial_report_llm_extractor.llm_field_extraction import run_field_extraction

    client = FakeJsonClient({
        "field_id": "revenue",
        "found": True,
        "value": "not-a-number",
        "currency": "CNY",
    })

    result = run_field_extraction(_sample_request(), client)

    assert result.status == "extraction_failed"
    assert any("unparseable" in err for err in result.errors)
    assert result.value == "not-a-number"  # raw value preserved


def test_run_extraction_archives_raw_response(tmp_path: Path) -> None:
    from financial_report_llm_extractor.llm_field_extraction import (
        PROMPT_VERSION,
        run_field_extraction,
    )

    client = FakeJsonClient({
        "field_id": "revenue",
        "found": True,
        "value": "168838102514.79",
    })

    result = run_field_extraction(_sample_request(), client, raw_response_dir=tmp_path)

    archive_path = tmp_path / f"revenue_{PROMPT_VERSION}.json"
    assert archive_path.exists()
    archived = json.loads(archive_path.read_text(encoding="utf-8"))
    assert archived["value"] == "168838102514.79"


import json  # add at top of file if not present
```

- [ ] **Step 2: Run tests, verify PASS**

```bash
uv run pytest tests/test_llm_field_extraction.py -v
```
Expected: 8 PASS. The runner from Task 4 already handles these cases; new tests should pass without code changes.

If any fail, fix the runner (likely missing edge case in `_parse_response`).

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "test: cover malformed response and raw archival in field extraction"
```

---

## Task 6: Integration test against real chunk fixture

**Files:**
- Test: `tests/test_llm_field_extraction.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_llm_field_extraction.py`:

```python
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "pdf_chunks"
CHUNKS_FIXTURE = FIXTURE_DIR / "600519_2025_chunks.jsonl"


def _load_fixture_chunks() -> tuple[dict[str, object], ...]:
    chunks: list[dict[str, object]] = []
    for line in CHUNKS_FIXTURE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            chunks.append(json.loads(line))
    return tuple(chunks)


def test_run_extraction_against_real_fixture_with_canned_response() -> None:
    from financial_report_llm_extractor.llm_field_extraction import run_field_extraction

    assert CHUNKS_FIXTURE.exists(), (
        f"Fixture missing: {CHUNKS_FIXTURE}. Run Task 1 to generate it."
    )

    chunks = _load_fixture_chunks()
    assert len(chunks) > 0, "fixture must contain at least one chunk"

    request = FieldExtractionRequest(
        field_id="revenue",
        field_description="operating revenue (营业收入)",
        statement_type="income_statement",
        value_type="money",
        chunks=chunks,
        expected_currency="CNY",
        expected_unit="yuan",
    )

    # Canned LLM response with the known true value for 600519 2024 revenue
    canned_response = {
        "field_id": "revenue",
        "found": True,
        "value": "168838102514.79",
        "currency": "CNY",
        "unit": "yuan",
        "period": "2024-12-31",
        "page": 4,
        "statement_line": "营业收入",
        "confidence": 0.95,
        "reasoning": "found on income statement",
    }
    client = FakeJsonClient(canned_response)

    result = run_field_extraction(request, client)

    assert result.status == "present"
    assert result.parsed_numeric_value == Decimal("168838102514.79")
    # Verify the prompt actually packaged the chunks (indirectly: client got them)
```

- [ ] **Step 2: Run test, verify PASS**

```bash
uv run pytest tests/test_llm_field_extraction.py::test_run_extraction_against_real_fixture_with_canned_response -v
```
Expected: PASS (assumes Task 1 fixture exists).

If fixture missing, the test surfaces a clear error pointing to Task 1.

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "test: integration test for field extraction against 600519 fixture"
```

---

## Task 7: Opt-in real LLM smoke test

**Files:**
- Test: `tests/test_llm_field_extraction.py`
- Create: `scripts/run-llm-field-extraction-smoke.sh`

- [ ] **Step 1: Write opt-in smoke test (skipped by default)**

Add to `tests/test_llm_field_extraction.py`:

```python
import os

import pytest


@pytest.mark.skipif(
    os.environ.get("REAL_LLM_SMOKE") != "1",
    reason="Set REAL_LLM_SMOKE=1 and LLM_CONFIG_PATH to run real LLM smoke",
)
def test_real_llm_smoke_extracts_revenue_within_tolerance() -> None:
    from financial_report_llm_extractor.llm_field_extraction import run_field_extraction
    from financial_report_llm_extractor.llm_transport import (
        LlmTransportConfig,
        create_llm_client,
    )

    config_path = Path(os.environ["LLM_CONFIG_PATH"])
    config = LlmTransportConfig.from_json(config_path)
    client = create_llm_client(config)

    chunks = _load_fixture_chunks()
    request = FieldExtractionRequest(
        field_id="revenue",
        field_description="operating revenue (营业收入)",
        statement_type="income_statement",
        value_type="money",
        chunks=chunks,
        expected_currency="CNY",
        expected_unit="yuan",
    )

    archive_dir = Path("tmp/runs/llm_smoke")
    result = run_field_extraction(request, client, raw_response_dir=archive_dir)

    assert result.status == "present", (
        f"smoke failed: status={result.status} errors={result.errors} "
        f"raw={result.raw_response}"
    )
    assert result.parsed_numeric_value is not None

    expected = Decimal("168838102514.79")
    delta = abs(result.parsed_numeric_value - expected)
    tolerance = expected * Decimal("0.05")
    assert delta < tolerance, (
        f"smoke value {result.parsed_numeric_value} outside ±5% of {expected}"
    )
```

- [ ] **Step 2: Run test, verify it skips**

```bash
uv run pytest tests/test_llm_field_extraction.py::test_real_llm_smoke_extracts_revenue_within_tolerance -v
```
Expected: SKIPPED (REAL_LLM_SMOKE not set).

Then verify all other tests still PASS:
```bash
uv run pytest tests/test_llm_field_extraction.py -v
```
Expected: 8 PASS, 1 SKIPPED.

- [ ] **Step 3: Create smoke script**

Create `scripts/run-llm-field-extraction-smoke.sh`:

```bash
#!/usr/bin/env bash
# Run the opt-in real-LLM smoke for 600519 revenue.
#
# Required env:
#   REAL_LLM_SMOKE=1
#   LLM_CONFIG_PATH=path/to/llm_config.json
#
# Example llm_config.json (DeepSeek):
# {
#   "provider": "deepseek",
#   "base_url": "https://api.deepseek.com/v1",
#   "model": "deepseek-v4-flash",
#   "api_key_env": "DEEPSEEK_API_KEY",
#   "max_retries": 2,
#   "timeout_seconds": 60
# }

set -euo pipefail

if [[ "${REAL_LLM_SMOKE:-}" != "1" ]]; then
  echo "REAL_LLM_SMOKE must be set to 1 to run the smoke." >&2
  exit 2
fi

if [[ -z "${LLM_CONFIG_PATH:-}" ]]; then
  echo "LLM_CONFIG_PATH must be set to a llm_config.json path." >&2
  exit 2
fi

uv run pytest tests/test_llm_field_extraction.py::test_real_llm_smoke_extracts_revenue_within_tolerance -v -s
```

```bash
chmod +x scripts/run-llm-field-extraction-smoke.sh
```

- [ ] **Step 4: Verify script syntax**

```bash
bash -n scripts/run-llm-field-extraction-smoke.sh
```
Expected: no output (syntax OK).

- [ ] **Step 5: Commit**

```bash
git add tests/test_llm_field_extraction.py scripts/run-llm-field-extraction-smoke.sh
git commit -m "test: add opt-in real llm smoke for 600519 revenue extraction"
```

---

## Task 8: Full verification

- [ ] **Step 1: Full test suite**

```bash
uv run pytest -v
```
Expected: 450 (existing) + 9 (new tests, 1 skipped) = 458 passed, 1 skipped.

- [ ] **Step 2: Lint**

```bash
uv run ruff check .
```
Expected: clean.

- [ ] **Step 3: Update roadmap**

Add a new section to `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md` after the H1 result section:

```markdown
### Phase I-D Implementation Result

Status: implemented on 2026-05-08. See:
- `docs/superpowers/specs/2026-05-08-phase-i-d-smoke-test-llm-field-extraction.md`
- `docs/superpowers/plans/2026-05-08-phase-i-d-smoke-test-llm-field-extraction.md`

Goal: Verify LLM extraction framework end-to-end before notes-level extraction (Phase I-A).

Implementation result:

- New module `src/financial_report_llm_extractor/llm_field_extraction.py` with `FieldExtractionRequest`/`FieldExtractionResult` dataclasses, deterministic JSON-schema prompt builder, and runner with raw response archival.
- Chunk fixture committed at `tests/fixtures/pdf_chunks/600519_2025_chunks.jsonl`.
- 8 unit/integration tests against FakeJsonClient pass.
- 1 opt-in real-LLM smoke test (`REAL_LLM_SMOKE=1` + `LLM_CONFIG_PATH=...`) extracts 600519 revenue within ±5% of 168,838,102,514.79 CNY.
- Smoke runner script at `scripts/run-llm-field-extraction-smoke.sh`.

Phase I-A (HK notes-level extraction) builds on this module. The prompt schema and result dataclass should be reused; field-specific prompt overrides come when notes-pattern failures surface.
```

- [ ] **Step 4: Commit**

```bash
git add docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md
git commit -m "docs: record phase i-d llm field extraction smoke test result"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Plan task |
|--------------|-----------|
| New module `llm_field_extraction.py` | Tasks 2-5 |
| Prompt schema | Task 3 |
| Field metadata source | Task 3 (description/statement_type/value_type passed via FieldExtractionRequest) |
| Chunk fixture | Task 1 |
| Layer 1 unit tests | Tasks 4, 5 |
| Layer 2 integration test | Task 6 |
| Layer 3 real LLM smoke | Task 7 |
| Acceptance criteria (8+ tests, ruff, smoke skipping) | Task 8 |
| Raw archival | Task 4 + Task 5 verification |

All sections covered.

**Type consistency check:**

- `FieldExtractionRequest` definition (Task 2) uses same fields as Task 3-7 references
- `FieldExtractionResult` `parsed_numeric_value: Decimal | None` consistent across tasks
- `JsonClient` Protocol with `complete_json(*, system_prompt, user_payload)` matches existing `LlmJsonClient` in `llm_transport.py:117`
- `PROMPT_VERSION` and `SCHEMA_VERSION` constants consistent

**Placeholder check:** None found.

Plan complete.
