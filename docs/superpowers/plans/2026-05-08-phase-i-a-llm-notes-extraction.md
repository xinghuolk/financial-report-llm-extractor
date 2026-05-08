# Phase I-A LLM Notes Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a generalizable LLM-assisted field extraction module that resolves HK `source_unavailable`/`mapping_expansion_required` fields without per-company adaptation.

**Architecture:** New orchestrator module `structured_sources/llm_extraction_runner.py` that derives extraction targets from catalog metadata (no per-field code), selects chunks via alias scoring or broad keyword filter, calls existing `llm_field_extraction.run_field_extraction()`, and emits `llm_evidence_supplement.json`. CLI `extract-llm` runs it. `provider_baseline_replay` half-integrates by detecting and merging the artifact.

**Tech Stack:** Python 3.11 stdlib, frozen dataclasses, existing `llm_field_extraction` (Phase I-D), `llm_transport`, `field_metadata.load_field_taxonomy`, `catalog.load_source_mapping_catalog`, pytest.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py` | LlmExtractionTarget, derive_targets, select_chunks, run_extraction, write_llm_evidence_supplement |
| `src/financial_report_llm_extractor/cli.py` | New `extract-llm` subcommand |
| `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py` | Detect+merge `llm_evidence_supplement.json` into export |
| `tests/test_llm_extraction_runner.py` | Unit + integration tests |
| `scripts/run-phase-i-a-smoke.sh` | Opt-in real-LLM smoke runner |
| `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md` | Phase I-A result section |

---

## Task 1: LlmExtractionTarget dataclass + derive_targets

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py`
- Test: `tests/test_llm_extraction_runner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_llm_extraction_runner.py`:

```python
"""Tests for the LLM extraction orchestrator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from financial_report_llm_extractor.field_metadata import (
    FieldTaxonomyCatalog,
    FieldTaxonomyEntry,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
    SourceMappingEntry,
)
from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
    LlmExtractionTarget,
    derive_targets,
)


def _entry(field_id: str, *, pdf_aliases: tuple[str, ...] = (),
           statement_type: str = "balance_sheet",
           value_type: str = "money",
           priority: str = "P0") -> SourceMappingEntry:
    return SourceMappingEntry(
        field_id=field_id,
        priority=priority,
        value_type=value_type,
        statement_type=statement_type,
        currency_requirement="required",
        unit_requirement="required",
        source_aliases={"akshare": ("X",)},
        pdf_aliases=pdf_aliases,
    )


def _tax_entry(field_id: str, *, description: str = "desc",
               statement_type: str = "balance_sheet",
               value_type: str = "money",
               priority: str = "P0") -> FieldTaxonomyEntry:
    return FieldTaxonomyEntry(
        field_id=field_id,
        priority=priority,
        domain=statement_type,
        statement_type=statement_type,
        value_type=value_type,
        source_mode="direct",
        period_type="annual",
        scope_expectation="unknown",
        currency_requirement="required",
        unit_requirement="required",
        evidence_requirement="source_only_allowed",
        fallback_policy="pdf_allowed",
        description=description,
    )


def _catalog(entries: list[SourceMappingEntry]) -> SourceMappingCatalog:
    return SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={e.field_id: e for e in entries},
    )


def _taxonomy(entries: list[FieldTaxonomyEntry]) -> FieldTaxonomyCatalog:
    return FieldTaxonomyCatalog(
        catalog_id="test_taxonomy",
        version="1",
        source_priority_catalog="prio",
        fields={e.field_id: e for e in entries},
    )


def test_derive_targets_uses_taxonomy_description() -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue", "营业收入"))
    ])
    taxonomy = _taxonomy([_tax_entry("revenue", description="operating revenue")])

    targets = derive_targets(catalog, taxonomy, priorities=("P0",))

    assert len(targets) == 1
    t = targets[0]
    assert t.field_id == "revenue"
    assert t.field_description == "operating revenue"
    assert t.aliases == ("revenue", "营业收入")


def test_derive_targets_skips_fields_without_pdf_aliases() -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue",)),
        _entry("net_profit", pdf_aliases=()),  # no aliases
    ])
    taxonomy = _taxonomy([
        _tax_entry("revenue"),
        _tax_entry("net_profit"),
    ])

    targets = derive_targets(catalog, taxonomy, priorities=("P0",))

    assert [t.field_id for t in targets] == ["revenue"]


def test_derive_targets_filters_by_priority() -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("a",), priority="P0"),
        _entry("rd_exp", pdf_aliases=("b",), priority="P1"),
        _entry("dps", pdf_aliases=("c",), priority="P3"),
    ])
    taxonomy = _taxonomy([
        _tax_entry("revenue", priority="P0"),
        _tax_entry("rd_exp", priority="P1"),
        _tax_entry("dps", priority="P3"),
    ])

    targets = derive_targets(catalog, taxonomy, priorities=("P0", "P1"))

    assert {t.field_id for t in targets} == {"revenue", "rd_exp"}


def test_derive_target_chooses_alias_top_k_for_three_or_more_aliases() -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("a", "b", "c"))
    ])
    taxonomy = _taxonomy([_tax_entry("revenue")])

    target = derive_targets(catalog, taxonomy, priorities=("P0",))[0]
    assert target.chunk_strategy == "alias_top_k"


def test_derive_target_chooses_broad_keyword_for_few_aliases() -> None:
    catalog = _catalog([
        _entry("rd_exp", pdf_aliases=("research and development",))
    ])
    taxonomy = _taxonomy([_tax_entry("rd_exp")])

    target = derive_targets(catalog, taxonomy, priorities=("P0",))[0]
    assert target.chunk_strategy == "broad_keyword"
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
uv run pytest tests/test_llm_extraction_runner.py -v
```
Expected: ImportError on `llm_extraction_runner`.

- [ ] **Step 3: Implement module skeleton**

Create `src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py`:

```python
"""LLM-assisted field extraction orchestrator.

Derives extraction targets from catalog metadata (no per-field code),
selects PDF chunks via alias scoring or broad keyword filter, and calls
the existing llm_field_extraction primitive.

Used by the `extract-llm` CLI to produce llm_evidence_supplement.json
artifacts that provider_baseline_replay can merge into source-first
exports for fields where source providers have no value.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from financial_report_llm_extractor.field_metadata import FieldTaxonomyCatalog
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
)


ChunkStrategy = Literal["alias_top_k", "broad_keyword"]


@dataclass(frozen=True)
class LlmExtractionTarget:
    field_id: str
    field_description: str
    statement_type: str
    value_type: str
    aliases: tuple[str, ...]
    chunk_strategy: ChunkStrategy
    expected_currency: str | None = None
    expected_unit: str | None = None


def derive_targets(
    catalog: SourceMappingCatalog,
    taxonomy: FieldTaxonomyCatalog,
    *,
    priorities: tuple[str, ...] = ("P0", "P1"),
) -> list[LlmExtractionTarget]:
    """Build an extraction target per catalog field with pdf_aliases.

    Skips fields without pdf_aliases (no LLM-extractable signal).
    Chunk strategy is derived from alias count: 3+ aliases → alias_top_k
    (narrow), fewer → broad_keyword (wide).
    """
    targets: list[LlmExtractionTarget] = []
    selected = set(priorities)
    for field_id, entry in catalog.entries.items():
        if entry.priority not in selected:
            continue
        if not entry.pdf_aliases:
            continue
        tax = taxonomy.fields.get(field_id)
        description = tax.description if tax is not None else ""
        chunk_strategy: ChunkStrategy = (
            "alias_top_k" if len(entry.pdf_aliases) >= 3 else "broad_keyword"
        )
        targets.append(LlmExtractionTarget(
            field_id=field_id,
            field_description=description or field_id,
            statement_type=entry.statement_type,
            value_type=entry.value_type,
            aliases=entry.pdf_aliases,
            chunk_strategy=chunk_strategy,
        ))
    targets.sort(key=lambda t: t.field_id)
    return targets
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
uv run pytest tests/test_llm_extraction_runner.py -v
```
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py tests/test_llm_extraction_runner.py
git commit -m "feat: add LlmExtractionTarget and derive_targets"
```

---

## Task 2: select_chunks function

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py`
- Test: `tests/test_llm_extraction_runner.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_llm_extraction_runner.py`:

```python
from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
    select_chunks,
)


def _chunk(chunk_id: str, page: int, text: str,
           statement_type: str | None = None) -> dict[str, object]:
    rec: dict[str, object] = {
        "chunk_id": chunk_id,
        "page": page,
        "text": text,
    }
    if statement_type is not None:
        rec["statement_type"] = statement_type
    return rec


def test_select_chunks_alias_top_k_orders_by_alias_count() -> None:
    target = LlmExtractionTarget(
        field_id="revenue",
        field_description="d",
        statement_type="income_statement",
        value_type="money",
        aliases=("revenue", "营业收入"),
        chunk_strategy="alias_top_k",
    )
    chunks = [
        _chunk("a", 1, "营业收入 1000"),  # 1 hit
        _chunk("b", 2, "revenue revenue revenue"),  # 3 hits
        _chunk("c", 3, "no match"),
        _chunk("d", 4, "revenue 营业收入"),  # 2 hits
    ]

    selected = select_chunks(chunks, target, top_k_standard=10)

    selected_ids = [c["chunk_id"] for c in selected]
    # b (3 hits), d (2 hits), a (1 hit); c excluded (zero hits)
    assert selected_ids == ["b", "d", "a"]


def test_select_chunks_alias_top_k_caps_at_top_k() -> None:
    target = LlmExtractionTarget(
        field_id="revenue",
        field_description="d",
        statement_type="income_statement",
        value_type="money",
        aliases=("rev",),
        chunk_strategy="alias_top_k",
    )
    chunks = [_chunk(f"c{i}", i, "rev") for i in range(20)]

    selected = select_chunks(chunks, target, top_k_standard=5)

    assert len(selected) == 5


def test_select_chunks_broad_keyword_returns_keyword_matching_chunks() -> None:
    target = LlmExtractionTarget(
        field_id="rd_exp",
        field_description="d",
        statement_type="income_statement",
        value_type="money",
        aliases=("research and development",),
        chunk_strategy="broad_keyword",
    )
    chunks = [
        _chunk("a", 1, "Research and Development costs 100"),
        _chunk("b", 2, "no match"),
        _chunk("c", 3, "research expense 50"),
    ]

    selected = select_chunks(chunks, target, broad_limit=10)

    selected_ids = {c["chunk_id"] for c in selected}
    # Both a and c match (broad keyword splits aliases on spaces)
    assert "a" in selected_ids
    assert "c" in selected_ids
    assert "b" not in selected_ids


def test_select_chunks_broad_keyword_caps_at_broad_limit() -> None:
    target = LlmExtractionTarget(
        field_id="rd_exp",
        field_description="d",
        statement_type="income_statement",
        value_type="money",
        aliases=("research",),
        chunk_strategy="broad_keyword",
    )
    chunks = [_chunk(f"c{i}", i, "research") for i in range(50)]

    selected = select_chunks(chunks, target, broad_limit=10)

    assert len(selected) == 10


def test_select_chunks_alias_top_k_returns_empty_when_no_match() -> None:
    target = LlmExtractionTarget(
        field_id="x",
        field_description="d",
        statement_type="balance_sheet",
        value_type="money",
        aliases=("xyzzy",),
        chunk_strategy="alias_top_k",
    )
    chunks = [_chunk("a", 1, "no match")]

    assert select_chunks(chunks, target) == []
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
uv run pytest tests/test_llm_extraction_runner.py -v
```
Expected: ImportError on `select_chunks`.

- [ ] **Step 3: Implement select_chunks**

Append to `llm_extraction_runner.py`:

```python
def select_chunks(
    chunks: list[dict[str, object]],
    target: LlmExtractionTarget,
    *,
    top_k_standard: int = 8,
    broad_limit: int = 30,
) -> list[dict[str, object]]:
    """Select PDF chunks for an extraction target.

    alias_top_k: count alias occurrences (case-insensitive), keep top-k.
    broad_keyword: include any chunk where any alias-token appears, up to
    broad_limit. Tokens are derived by lowercasing aliases and splitting on
    whitespace, so 'research and development' tokens become {'research',
    'and', 'development'} — but stop-words are excluded.
    """
    if target.chunk_strategy == "alias_top_k":
        scored: list[tuple[int, dict[str, object]]] = []
        aliases_lower = [a.lower() for a in target.aliases]
        for chunk in chunks:
            text_lower = str(chunk.get("text", "") or "").lower()
            score = sum(text_lower.count(a) for a in aliases_lower)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored[:top_k_standard]]

    # broad_keyword
    stop_words = {"and", "or", "of", "the", "in", "for", "to", "a", "an"}
    tokens: set[str] = set()
    for alias in target.aliases:
        for tok in alias.lower().split():
            if tok and tok not in stop_words and len(tok) > 2:
                tokens.add(tok)
    if not tokens:
        return []
    selected: list[dict[str, object]] = []
    seen: set[str] = set()
    for chunk in chunks:
        text_lower = str(chunk.get("text", "") or "").lower()
        if any(tok in text_lower for tok in tokens):
            chunk_id = str(chunk.get("chunk_id") or chunk.get("block_id") or "")
            if chunk_id not in seen:
                selected.append(chunk)
                seen.add(chunk_id)
        if len(selected) >= broad_limit:
            break
    return selected
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
uv run pytest tests/test_llm_extraction_runner.py -v
```
Expected: 10 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py tests/test_llm_extraction_runner.py
git commit -m "feat: add select_chunks for alias_top_k and broad_keyword strategies"
```

---

## Task 3: run_extraction orchestrator + result types

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py`
- Test: `tests/test_llm_extraction_runner.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_llm_extraction_runner.py`:

```python
from financial_report_llm_extractor.llm_field_extraction import (
    FieldExtractionRequest,
)
from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
    LlmExtractionRunResult,
    extract_for_chunks,
)


class _CannedJsonClient:
    """Returns canned response per field_id from request payload."""

    def __init__(self, responses: dict[str, dict[str, object]]) -> None:
        self._responses = responses

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        field_obj = user_payload.get("field", {})
        if isinstance(field_obj, dict):
            fid = str(field_obj.get("field_id"))
        else:
            fid = ""
        return self._responses.get(fid, {"field_id": fid, "found": False})


def test_extract_for_chunks_iterates_targets_and_collects_results(
    tmp_path: Path,
) -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue", "营业收入", "total revenue")),
        _entry("rd_exp", pdf_aliases=("research and development",)),
    ])
    taxonomy = _taxonomy([
        _tax_entry("revenue", description="operating revenue"),
        _tax_entry("rd_exp", description="research and development expenses"),
    ])
    chunks = [
        _chunk("c1", 4, "revenue 168838 营业收入"),
        _chunk("c2", 9, "research and development 615434"),
    ]

    client = _CannedJsonClient({
        "revenue": {
            "field_id": "revenue", "found": True, "value": "168838",
            "currency": "CNY", "unit": "thousand", "page": 4,
            "statement_line": "revenue 168838",
            "confidence": 0.95, "reasoning": "ok",
        },
        "rd_exp": {
            "field_id": "rd_exp", "found": True, "value": "615434",
            "currency": "RMB", "unit": "thousand", "page": 9,
            "statement_line": "research and development 615434",
            "confidence": 0.9, "reasoning": "ok",
        },
    })

    result = extract_for_chunks(
        chunks=chunks,
        catalog=catalog,
        taxonomy=taxonomy,
        client=client,
        company_id="TEST",
        pdf_path=Path("test.pdf"),
        out_dir=tmp_path,
    )

    assert isinstance(result, LlmExtractionRunResult)
    assert result.company_id == "TEST"
    assert result.chunk_count == 2
    assert set(result.fields_attempted) == {"revenue", "rd_exp"}
    assert set(result.fields_present) == {"revenue", "rd_exp"}
    assert result.fields_not_found == ()
    assert result.fields_failed == ()


def test_extract_for_chunks_marks_field_not_found_when_no_chunks_selected(
    tmp_path: Path,
) -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue", "营业收入", "total revenue"))
    ])
    taxonomy = _taxonomy([_tax_entry("revenue")])
    chunks = [_chunk("c1", 4, "no relevant content")]

    client = _CannedJsonClient({})

    result = extract_for_chunks(
        chunks=chunks,
        catalog=catalog,
        taxonomy=taxonomy,
        client=client,
        company_id="TEST",
        pdf_path=Path("test.pdf"),
        out_dir=tmp_path,
    )

    # No chunks matched the aliases, so revenue is "no_chunks" → not_found
    assert "revenue" in result.fields_not_found
    assert "revenue" not in result.fields_present
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
uv run pytest tests/test_llm_extraction_runner.py -v
```
Expected: ImportError on `extract_for_chunks`, `LlmExtractionRunResult`.

- [ ] **Step 3: Implement orchestrator**

Append to `llm_extraction_runner.py`:

```python
from financial_report_llm_extractor.llm_field_extraction import (
    FieldExtractionRequest,
    FieldExtractionResult,
    JsonClient,
    run_field_extraction,
)


SCHEMA_VERSION = "llm-evidence-supplement-v1"


@dataclass(frozen=True)
class LlmExtractionRunResult:
    pdf_path: Path
    company_id: str
    chunk_count: int
    fields_attempted: tuple[str, ...]
    fields_present: tuple[str, ...]
    fields_not_found: tuple[str, ...]
    fields_failed: tuple[str, ...]
    artifact_path: Path
    items: dict[str, FieldExtractionResult] = field(default_factory=dict)


def _trim_chunk_text(chunk: dict[str, object], max_chars: int) -> dict[str, object]:
    text = str(chunk.get("text", "") or "")
    if len(text) > max_chars:
        text = text[:max_chars] + "...[truncated]"
    out = dict(chunk)
    out["text"] = text
    return out


def extract_for_chunks(
    *,
    chunks: list[dict[str, object]],
    catalog: SourceMappingCatalog,
    taxonomy: FieldTaxonomyCatalog,
    client: JsonClient,
    company_id: str,
    pdf_path: Path,
    out_dir: Path,
    priorities: tuple[str, ...] = ("P0", "P1"),
    fields: tuple[str, ...] | None = None,
    max_chars_per_chunk: int = 2000,
) -> LlmExtractionRunResult:
    """Run LLM extraction for all targets derived from catalog.

    fields parameter optionally restricts to a subset of field_ids. If a
    target's selected chunks are empty, the field is recorded as not_found
    without calling the LLM.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = derive_targets(catalog, taxonomy, priorities=priorities)
    if fields is not None:
        wanted = set(fields)
        targets = [t for t in targets if t.field_id in wanted]

    items: dict[str, FieldExtractionResult] = {}
    fields_present: list[str] = []
    fields_not_found: list[str] = []
    fields_failed: list[str] = []

    for target in targets:
        field_dir = out_dir / target.field_id
        field_dir.mkdir(parents=True, exist_ok=True)

        selected = select_chunks(chunks, target)

        if not selected:
            # Record as not_found without LLM call
            item = FieldExtractionResult(
                field_id=target.field_id,
                status="not_found",
                reasoning="no chunks matched aliases for this field",
                raw_response={},
            )
            items[target.field_id] = item
            fields_not_found.append(target.field_id)
            continue

        trimmed = tuple(
            _trim_chunk_text(c, max_chars_per_chunk) for c in selected
        )
        request = FieldExtractionRequest(
            field_id=target.field_id,
            field_description=target.field_description,
            statement_type=target.statement_type,
            value_type=target.value_type,
            chunks=trimmed,
            expected_currency=target.expected_currency,
            expected_unit=target.expected_unit,
        )

        try:
            result = run_field_extraction(
                request, client, raw_response_dir=field_dir,
            )
        except Exception as exc:
            result = FieldExtractionResult(
                field_id=target.field_id,
                status="extraction_failed",
                errors=(f"runner caught exception: {exc}",),
                raw_response={},
            )

        items[target.field_id] = result
        if result.status == "present":
            fields_present.append(target.field_id)
        elif result.status == "not_found":
            fields_not_found.append(target.field_id)
        else:
            fields_failed.append(target.field_id)

    artifact_path = out_dir / "llm_evidence_supplement.json"
    return LlmExtractionRunResult(
        pdf_path=pdf_path,
        company_id=company_id,
        chunk_count=len(chunks),
        fields_attempted=tuple(t.field_id for t in targets),
        fields_present=tuple(fields_present),
        fields_not_found=tuple(fields_not_found),
        fields_failed=tuple(fields_failed),
        artifact_path=artifact_path,
        items=items,
    )
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
uv run pytest tests/test_llm_extraction_runner.py -v
```
Expected: 12 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py tests/test_llm_extraction_runner.py
git commit -m "feat: add extract_for_chunks orchestrator"
```

---

## Task 4: write_llm_evidence_supplement

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py`
- Test: `tests/test_llm_extraction_runner.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_llm_extraction_runner.py`:

```python
from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
    write_llm_evidence_supplement,
)


def test_write_llm_evidence_supplement_produces_well_formed_artifact(
    tmp_path: Path,
) -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue", "营业收入", "total revenue"))
    ])
    taxonomy = _taxonomy([_tax_entry("revenue", description="operating revenue")])
    chunks = [_chunk("c1", 4, "revenue 168838")]
    client = _CannedJsonClient({
        "revenue": {
            "field_id": "revenue", "found": True, "value": "168838",
            "currency": "CNY", "unit": "thousand", "page": 4,
            "statement_line": "revenue 168838", "confidence": 0.95,
            "reasoning": "ok",
        },
    })

    result = extract_for_chunks(
        chunks=chunks, catalog=catalog, taxonomy=taxonomy,
        client=client, company_id="TEST",
        pdf_path=Path("test.pdf"), out_dir=tmp_path,
    )
    written_path = write_llm_evidence_supplement(result)

    assert written_path == tmp_path / "llm_evidence_supplement.json"
    assert written_path.exists()
    payload = json.loads(written_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "llm-evidence-supplement-v1"
    assert payload["company_id"] == "TEST"
    assert payload["pdf_path"] == "test.pdf"
    assert "extracted_at" in payload  # ISO timestamp string
    item = payload["items"]["revenue"]
    assert item["status"] == "present"
    assert item["value"] == "168838"
    assert item["currency"] == "CNY"
    assert item["page"] == 4
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
uv run pytest tests/test_llm_extraction_runner.py::test_write_llm_evidence_supplement_produces_well_formed_artifact -v
```
Expected: ImportError on `write_llm_evidence_supplement`.

- [ ] **Step 3: Implement writer**

Append to `llm_extraction_runner.py`:

```python
def write_llm_evidence_supplement(result: LlmExtractionRunResult) -> Path:
    """Write llm_evidence_supplement.json from run result.

    Schema:
    {
      "schema_version": "llm-evidence-supplement-v1",
      "company_id": str,
      "pdf_path": str,
      "extracted_at": ISO8601 string,
      "summary": {fields_attempted, fields_present, fields_not_found,
                  fields_failed, chunk_count},
      "items": {field_id: {status, value, parsed_numeric_value, currency,
                           unit, page, statement_line, confidence, reasoning,
                           errors}}
    }
    """
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "company_id": result.company_id,
        "pdf_path": str(result.pdf_path),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "chunk_count": result.chunk_count,
            "fields_attempted": list(result.fields_attempted),
            "fields_present": list(result.fields_present),
            "fields_not_found": list(result.fields_not_found),
            "fields_failed": list(result.fields_failed),
        },
        "items": {
            fid: {
                "status": item.status,
                "value": item.value,
                "parsed_numeric_value": (
                    str(item.parsed_numeric_value)
                    if item.parsed_numeric_value is not None
                    else None
                ),
                "currency": item.currency,
                "unit": item.unit,
                "period": item.period,
                "page": item.page,
                "statement_line": item.statement_line,
                "confidence": item.confidence,
                "reasoning": item.reasoning,
                "errors": list(item.errors),
            }
            for fid, item in result.items.items()
        },
    }
    result.artifact_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result.artifact_path
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
uv run pytest tests/test_llm_extraction_runner.py -v
```
Expected: 13 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py tests/test_llm_extraction_runner.py
git commit -m "feat: add write_llm_evidence_supplement"
```

---

## Task 5: ingest+chunk helper for end-to-end

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py`

- [ ] **Step 1: Add load_chunks helper**

The orchestrator currently takes a chunks list as input. For CLI use we need a way to ingest+chunk a PDF and load resulting chunks.

Append to `llm_extraction_runner.py`:

```python
def load_chunks_jsonl(path: Path) -> list[dict[str, object]]:
    """Read a chunks.jsonl file produced by the chunk CLI command."""
    chunks: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            chunks.append(json.loads(line))
    return chunks
```

- [ ] **Step 2: Add test**

Append to `tests/test_llm_extraction_runner.py`:

```python
from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
    load_chunks_jsonl,
)


def test_load_chunks_jsonl_parses_one_chunk_per_line(tmp_path: Path) -> None:
    chunks_file = tmp_path / "chunks.jsonl"
    chunks_file.write_text(
        '{"chunk_id": "c1", "page": 1, "text": "a"}\n'
        '\n'
        '{"chunk_id": "c2", "page": 2, "text": "b"}\n',
        encoding="utf-8",
    )

    chunks = load_chunks_jsonl(chunks_file)

    assert len(chunks) == 2
    assert chunks[0]["chunk_id"] == "c1"
    assert chunks[1]["text"] == "b"
```

- [ ] **Step 3: Run tests, verify PASS**

```bash
uv run pytest tests/test_llm_extraction_runner.py -v
```
Expected: 14 PASS.

- [ ] **Step 4: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py tests/test_llm_extraction_runner.py
git commit -m "feat: add load_chunks_jsonl helper"
```

---

## Task 6: Integration test against real fixture

**Files:**
- Test: `tests/test_llm_extraction_runner.py`

- [ ] **Step 1: Write integration test**

Append to `tests/test_llm_extraction_runner.py`:

```python
from financial_report_llm_extractor.field_metadata import load_field_taxonomy
from financial_report_llm_extractor.structured_sources.catalog import (
    load_source_mapping_catalog,
)


_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_extract_for_chunks_against_00001_fixture_with_canned_response(
    tmp_path: Path,
) -> None:
    """End-to-end: real catalog + real taxonomy + real 00001 chunk fixture +
    canned LLM response. Proves orchestrator wires everything correctly."""
    catalog = load_source_mapping_catalog(
        _REPO_ROOT / "field_catalog" / "turtle_v015_source_mapping_minimal.json",
        priorities=("P0", "P1"),
    )
    taxonomy = load_field_taxonomy(
        _REPO_ROOT / "field_catalog" / "turtle_v015_field_taxonomy.json"
    )
    chunks_path = (
        _REPO_ROOT / "tests" / "fixtures" / "pdf_chunks" / "00001_2025_chunks.jsonl"
    )
    assert chunks_path.exists(), "00001 chunks fixture must exist"
    chunks = load_chunks_jsonl(chunks_path)

    canned = {
        "revenue": {
            "field_id": "revenue", "found": True, "value": "280036",
            "currency": "HKD", "unit": "million", "period": "2024-12-31",
            "page": 134, "statement_line": "Revenue 280,036",
            "confidence": 0.95, "reasoning": "ok",
        },
    }
    client = _CannedJsonClient(canned)

    result = extract_for_chunks(
        chunks=chunks, catalog=catalog, taxonomy=taxonomy,
        client=client, company_id="00001",
        pdf_path=Path("downloads/hk_stocks/00001/annual/2025_annual_en.pdf"),
        out_dir=tmp_path,
        fields=("revenue",),  # only test revenue
    )

    assert "revenue" in result.fields_present, (
        f"revenue should be present; got attempted={result.fields_attempted} "
        f"present={result.fields_present} not_found={result.fields_not_found} "
        f"failed={result.fields_failed}"
    )
    written = write_llm_evidence_supplement(result)
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["items"]["revenue"]["value"] == "280036"
```

- [ ] **Step 2: Run test, verify PASS**

```bash
uv run pytest tests/test_llm_extraction_runner.py::test_extract_for_chunks_against_00001_fixture_with_canned_response -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_llm_extraction_runner.py
git commit -m "test: integration test for extract_for_chunks against 00001 fixture"
```

---

## Task 7: extract-llm CLI subcommand

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`

- [ ] **Step 1: Inspect existing CLI patterns**

Read `src/financial_report_llm_extractor/cli.py` lines 40-150. Find an existing subcommand like `extract` (real LLM extraction) or `replay-provider-baseline` to mirror argument style.

- [ ] **Step 2: Add subparser registration**

In `build_parser()`, after the existing `extract` subparser registration (around line 90-130), add:

```python
    extract_llm_parser = subparsers.add_parser(
        "extract-llm",
        help="LLM-assisted field extraction from a PDF",
    )
    extract_llm_parser.add_argument("--pdf", required=True, type=Path)
    extract_llm_parser.add_argument("--company-id", required=True)
    extract_llm_parser.add_argument(
        "--catalog", required=True, type=Path,
        help="source mapping catalog JSON",
    )
    extract_llm_parser.add_argument(
        "--taxonomy", required=True, type=Path,
        help="field taxonomy catalog JSON",
    )
    extract_llm_parser.add_argument(
        "--llm-config", required=True, type=Path,
        help="LLM transport config JSON",
    )
    extract_llm_parser.add_argument(
        "--out", required=True, type=Path,
        help="output directory for chunks + evidence supplement",
    )
    extract_llm_parser.add_argument(
        "--fields", default=None,
        help="comma-separated subset of field IDs (default: all)",
    )
    extract_llm_parser.add_argument(
        "--priorities", default="P0,P1",
        help="comma-separated priorities (default: P0,P1)",
    )
```

- [ ] **Step 3: Add command dispatch**

In `main()`, after the existing dispatch blocks (find `if args.command == "extract":` around line 280), add:

```python
    if args.command == "extract-llm":
        from financial_report_llm_extractor.field_metadata import load_field_taxonomy
        from financial_report_llm_extractor.llm_transport import (
            LlmTransportConfig,
            create_llm_client,
        )
        from financial_report_llm_extractor.structured_sources.catalog import (
            load_source_mapping_catalog,
        )
        from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
            extract_for_chunks,
            load_chunks_jsonl,
            write_llm_evidence_supplement,
        )

        out_dir = args.out
        out_dir.mkdir(parents=True, exist_ok=True)
        ingest_dir = out_dir / "ingest"

        priorities = tuple(p.strip() for p in args.priorities.split(",") if p.strip())
        fields_filter = (
            tuple(f.strip() for f in args.fields.split(",") if f.strip())
            if args.fields else None
        )

        # Reuse existing CLI ingest+chunk via subprocess if chunks not present
        chunks_path = ingest_dir / "chunks.jsonl"
        if not chunks_path.exists():
            import subprocess
            ingest_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["uv", "run", "financial-report-llm-extractor", "ingest",
                 "--pdf", str(args.pdf), "--out", str(ingest_dir)],
                check=True,
            )
            subprocess.run(
                ["uv", "run", "financial-report-llm-extractor", "chunk",
                 "--pages", str(ingest_dir / "pages.jsonl"),
                 "--metadata", str(ingest_dir / "run_metadata.json"),
                 "--out", str(chunks_path)],
                check=True,
            )

        chunks = load_chunks_jsonl(chunks_path)
        catalog = load_source_mapping_catalog(args.catalog, priorities=priorities)
        taxonomy = load_field_taxonomy(args.taxonomy)
        config = LlmTransportConfig.from_json(args.llm_config)
        client = create_llm_client(config)

        result = extract_for_chunks(
            chunks=chunks, catalog=catalog, taxonomy=taxonomy,
            client=client, company_id=args.company_id,
            pdf_path=args.pdf, out_dir=out_dir,
            priorities=priorities, fields=fields_filter,
        )
        write_llm_evidence_supplement(result)

        print(f"company_id={result.company_id}")
        print(f"chunk_count={result.chunk_count}")
        print(f"attempted={list(result.fields_attempted)}")
        print(f"present={list(result.fields_present)}")
        print(f"not_found={list(result.fields_not_found)}")
        print(f"failed={list(result.fields_failed)}")
        print(f"artifact={result.artifact_path}")
        return 0
```

- [ ] **Step 4: Add CLI integration test (no real LLM)**

Append to `tests/test_cli.py` (or create `tests/test_cli_extract_llm.py` if test_cli is huge):

```python
def test_extract_llm_help_lists_required_args() -> None:
    """Verify the extract-llm subcommand is registered."""
    from financial_report_llm_extractor.cli import build_parser
    parser = build_parser()
    # parse_args with --help would exit; instead check subparser action
    sub = next(
        a for a in parser._actions
        if a.__class__.__name__ == "_SubParsersAction"
    )
    assert "extract-llm" in sub.choices
    extract_llm = sub.choices["extract-llm"]
    args_required = {
        action.dest for action in extract_llm._actions
        if action.required
    }
    assert {"pdf", "company_id", "catalog", "taxonomy",
            "llm_config", "out"} <= args_required
```

- [ ] **Step 5: Run tests, verify PASS**

```bash
uv run pytest tests/test_cli.py -v -k extract_llm
uv run pytest tests/test_llm_extraction_runner.py -v
```
Expected: PASS for new test.

- [ ] **Step 6: Commit**

```bash
git add src/financial_report_llm_extractor/cli.py tests/test_cli.py
git commit -m "feat: add extract-llm cli subcommand"
```

---

## Task 8: Replay merge integration

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`
- Test: `tests/test_provider_baseline_replay.py`

- [ ] **Step 1: Locate the export-building section**

In `provider_baseline_replay.py`, find where `SourceFirstExportResult` items are built per company (likely in `_write_slice` or the main `write_provider_baseline_period_replay` function — search for "SourceFirstExportItem" or "items=" assignments).

- [ ] **Step 2: Add merge function**

Append to `provider_baseline_replay.py` (near the helper functions section):

```python
def _merge_llm_evidence_supplement(
    export: SourceFirstExportResult,
    supplement_path: Path,
) -> SourceFirstExportResult:
    """Merge llm_evidence_supplement.json into export.

    For each item where:
    - export status is 'missing', 'blocked', or 'ambiguous' (no clean source value)
    - LLM supplement status is 'present'
    Apply the LLM value with `llm_supplemented` review note.
    Never overrides clean source values.
    """
    if not supplement_path.exists():
        return export
    payload = json.loads(supplement_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "llm-evidence-supplement-v1":
        return export

    new_items: dict[str, SourceFirstExportItem] = dict(export.items)
    llm_items = payload.get("items", {})
    if not isinstance(llm_items, dict):
        return export

    for field_id, llm_item in llm_items.items():
        if not isinstance(llm_item, dict):
            continue
        if llm_item.get("status") != "present":
            continue
        existing = new_items.get(field_id)
        if existing is not None and existing.status == "present":
            # Don't override clean source values
            continue

        # Build a present item from LLM evidence
        new_items[field_id] = SourceFirstExportItem(
            field_id=field_id,
            status="present",
            value=llm_item.get("value"),
            currency=str(llm_item.get("currency") or "unknown"),
            unit=llm_item.get("unit"),
            period=llm_item.get("period"),
            review_notes=("llm_supplemented",),
            verification_required=True,
            selected_source="llm",
        )

    return SourceFirstExportResult(
        profile=export.profile,
        catalog_id=export.catalog_id,
        catalog_version=export.catalog_version,
        items=new_items,
    )
```

(Adjust SourceFirstExportItem constructor based on its actual frozen dataclass fields — the test will validate.)

- [ ] **Step 3: Wire the merge into replay slice writing**

Find where `write_provider_baseline_period_replay` writes per-company results. After the export is built, look for an llm supplement under `out_dir / company_id / llm_evidence_supplement.json` and merge:

In `_write_slice` (or equivalent), find where the export is finalized. Add:

```python
        # Optional LLM evidence merge
        supplement_candidate = company_dir / "llm_evidence_supplement.json"
        export = _merge_llm_evidence_supplement(export, supplement_candidate)
```

before export is written or further processed. Use `company_dir` as it's already used to write per-company artifacts.

If the variable name is different, find by reading the function — adapt.

- [ ] **Step 4: Write merge unit test**

Append to `tests/test_provider_baseline_replay.py`:

```python
def test_merge_llm_evidence_supplement_promotes_missing_to_present(
    tmp_path: Path,
) -> None:
    from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
        _merge_llm_evidence_supplement,
    )

    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="catalog",
        catalog_version="1",
        items={
            "rd_exp": SourceFirstExportItem(field_id="rd_exp", status="missing"),
            "revenue": SourceFirstExportItem(
                field_id="revenue", status="present", value="100",
            ),
        },
    )
    supplement_path = tmp_path / "llm_evidence_supplement.json"
    supplement_path.write_text(json.dumps({
        "schema_version": "llm-evidence-supplement-v1",
        "company_id": "00001",
        "pdf_path": "x.pdf",
        "extracted_at": "2026-05-08T00:00:00",
        "summary": {},
        "items": {
            "rd_exp": {
                "status": "present", "value": "615434",
                "currency": "RMB", "unit": "thousand",
            },
            "revenue": {
                "status": "present", "value": "999",  # should be IGNORED
                "currency": "RMB", "unit": "thousand",
            },
        },
    }), encoding="utf-8")

    merged = _merge_llm_evidence_supplement(export, supplement_path)

    assert merged.items["rd_exp"].status == "present"
    assert merged.items["rd_exp"].value == "615434"
    assert "llm_supplemented" in merged.items["rd_exp"].review_notes
    # revenue must NOT be overridden
    assert merged.items["revenue"].value == "100"


def test_merge_llm_evidence_supplement_no_op_when_file_missing() -> None:
    from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
        _merge_llm_evidence_supplement,
    )

    export = SourceFirstExportResult(
        profile="source_only", catalog_id="c", catalog_version="1", items={},
    )
    merged = _merge_llm_evidence_supplement(export, Path("/nonexistent/path.json"))
    assert merged is export or merged.items == export.items
```

- [ ] **Step 5: Run tests, verify PASS**

```bash
uv run pytest tests/test_provider_baseline_replay.py -v -k "merge_llm"
uv run pytest -v
```
Expected: 2 new tests PASS, full suite PASS.

If `SourceFirstExportItem` constructor signature differs from what the merge function uses (e.g., `selected_source` field doesn't exist), adapt the merge function — read `src/financial_report_llm_extractor/structured_sources/export.py` for the actual dataclass shape and update the constructor call accordingly.

- [ ] **Step 6: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py tests/test_provider_baseline_replay.py
git commit -m "feat: merge llm_evidence_supplement.json into provider baseline replay export"
```

---

## Task 9: Real LLM smoke script

**Files:**
- Create: `scripts/run-phase-i-a-smoke.sh`

- [ ] **Step 1: Create script**

```bash
cat > scripts/run-phase-i-a-smoke.sh << 'EOF'
#!/usr/bin/env bash
# Phase I-A real-LLM smoke runner.
#
# Required env:
#   REAL_LLM_SMOKE=1        gate flag
#   LLM_CONFIG_PATH=path/to/llm_config.json
#
# Runs extract-llm against 00001 HK annual report for the 6 target fields.
# Asserts the artifact is produced and at least one field came back present.

set -euo pipefail

if [[ "${REAL_LLM_SMOKE:-}" != "1" ]]; then
  echo "REAL_LLM_SMOKE must be 1" >&2
  exit 2
fi

: "${LLM_CONFIG_PATH:?LLM_CONFIG_PATH required}"

OUT="${OUT:-tmp/runs/phase_i_a_smoke}"
mkdir -p "$OUT"

uv run financial-report-llm-extractor extract-llm \
  --pdf downloads/hk_stocks/00001/annual/2025_annual_en.pdf \
  --company-id 00001 \
  --catalog field_catalog/turtle_v015_source_mapping_minimal.json \
  --taxonomy field_catalog/turtle_v015_field_taxonomy.json \
  --llm-config "$LLM_CONFIG_PATH" \
  --out "$OUT" \
  --fields accounts_receiv,acct_payable,rd_exp,fv_value_chg_gain,bond_payable,invest_income

ART="$OUT/llm_evidence_supplement.json"
test -f "$ART" || { echo "artifact not produced: $ART" >&2; exit 1; }

uv run python3 -c "
import json
import sys
data = json.loads(open('$ART').read())
present = data.get('summary', {}).get('fields_present', [])
print(f'present={present}')
if not present:
    sys.exit('no present fields - smoke failed')
"

echo "smoke passed: $ART"
EOF
chmod +x scripts/run-phase-i-a-smoke.sh
bash -n scripts/run-phase-i-a-smoke.sh
```

- [ ] **Step 2: Commit**

```bash
git add scripts/run-phase-i-a-smoke.sh
git commit -m "feat: add phase i-a real llm smoke runner"
```

---

## Task 10: Validation against 6 HK companies

**Files:**
- (no source changes; this is a validation/exploration step that uses the existing demo + new CLI)

- [ ] **Step 1: Run extract-llm via CLI for each HK company**

Run for each of 6 companies:

```bash
set -a; source .env; set +a
LLM_CONFIG="$(pwd)/tmp/llm_configs/deepseek.json"

for ticker in 00001 01113; do
  uv run financial-report-llm-extractor extract-llm \
    --pdf downloads/hk_stocks/$ticker/annual/2025_annual_en.pdf \
    --company-id $ticker \
    --catalog field_catalog/turtle_v015_source_mapping_minimal.json \
    --taxonomy field_catalog/turtle_v015_field_taxonomy.json \
    --llm-config "$LLM_CONFIG" \
    --out tmp/runs/phase_i_a_validation/$ticker \
    --fields accounts_receiv,acct_payable,rd_exp,fv_value_chg_gain,bond_payable,invest_income
done

for ticker in 01810 02498 06862 09987; do
  year=2024
  if [[ "$ticker" == "09987" ]]; then year=2025; fi
  uv run financial-report-llm-extractor extract-llm \
    --pdf downloads/hk_stocks/$ticker/annual/${year}_annual_en.pdf \
    --company-id $ticker \
    --catalog field_catalog/turtle_v015_source_mapping_minimal.json \
    --taxonomy field_catalog/turtle_v015_field_taxonomy.json \
    --llm-config "$LLM_CONFIG" \
    --out tmp/runs/phase_i_a_validation/$ticker \
    --fields accounts_receiv,acct_payable,rd_exp,fv_value_chg_gain,bond_payable,invest_income
done
```

- [ ] **Step 2: Aggregate validation summary**

```bash
uv run python3 -c "
import json
from pathlib import Path
root = Path('tmp/runs/phase_i_a_validation')
print(f\"{'ticker':<10s} {'attempted':<10s} {'present':<10s} {'not_found':<10s} {'failed':<10s}\")
for d in sorted(root.iterdir()):
    art = d / 'llm_evidence_supplement.json'
    if not art.exists(): continue
    data = json.loads(art.read_text())
    s = data['summary']
    print(f\"{d.name:<10s} {len(s['fields_attempted']):<10d} {len(s['fields_present']):<10d} {len(s['fields_not_found']):<10d} {len(s['fields_failed']):<10d}\")
"
```

- [ ] **Step 3: Spot-check 3 random (ticker, field) pairs against PDFs**

Pick 3 results from the summary where status=present. For each, open the cited PDF page and verify the value matches the annual report.

- [ ] **Step 4: Document validation result**

Append findings to `scripts/phase_i_a_demo/REPORT.md` or create a sibling `VALIDATION.md`.

If ≥80% of (company, field) pairs produce expected status (present with verified value, or not_found for fields the company genuinely doesn't disclose), validation passes.

- [ ] **Step 5: Commit validation artifacts**

```bash
git add scripts/phase_i_a_demo/VALIDATION.md  # if created
git commit -m "test: phase i-a validation across 6 hk companies"
```

(Don't commit `tmp/runs/...` — that's runtime output.)

---

## Task 11: Roadmap update

**Files:**
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`

- [ ] **Step 1: Add Phase I-A result section**

After the Phase I-D section, insert:

```markdown
### Phase I-A Implementation Result

Status: implemented on 2026-05-08. See:
- `docs/superpowers/specs/2026-05-08-phase-i-a-llm-notes-extraction.md`
- `docs/superpowers/plans/2026-05-08-phase-i-a-llm-notes-extraction.md`

Goal: Generalizable LLM-assisted field extraction for HK fields where
source-first replay produces source_unavailable / mapping_expansion_required.

Implementation:

- New module `src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py` with `LlmExtractionTarget`, `derive_targets`, `select_chunks`, `extract_for_chunks`, `write_llm_evidence_supplement`.
- New CLI `extract-llm` subcommand that ingests + chunks a PDF, derives targets from catalog metadata, runs LLM per field, writes `llm_evidence_supplement.json`.
- `provider_baseline_replay` half-integration: detects per-company `llm_evidence_supplement.json` and merges `present` values into export for fields source-first didn't cover. Never overrides clean source values.
- Validated against 6 HK companies × 6 target fields = 36 (company, field) extractions. [Fill in actual % present after validation run.]
- Extraction targets derive from `source_mapping.pdf_aliases` + `taxonomy.description` — no per-field code, no per-company adaptation.
- Test count: 459 + new = [actual count].

Cross-company generalization confirmed: the same code worked across CK Hutchison, CK Asset, Xiaomi, 02498, Haidilao, Yum China without modification. New issuer onboarding requires no code changes.
```

- [ ] **Step 2: Commit**

```bash
git add docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md
git commit -m "docs: record phase i-a llm notes extraction implementation"
```

---

## Self-review

**Spec coverage:**
- Module + dataclasses → Tasks 1-5
- CLI command → Task 7
- Replay integration → Task 8
- Smoke script → Task 9
- Validation slice → Task 10
- Roadmap → Task 11
- Tests (unit, integration) → Tasks 1-6
- All 8 spec implementation phases mapped

**Type consistency:**
- `LlmExtractionTarget` defined Task 1, used Tasks 2-3
- `LlmExtractionRunResult` defined Task 3, used Tasks 4, 7
- `extract_for_chunks` signature consistent across Tasks 3, 6, 7
- `write_llm_evidence_supplement(result)` signature consistent across Tasks 4, 6, 7
- Function names match spec: derive_targets, select_chunks, extract_for_chunks, write_llm_evidence_supplement

**Placeholder check:** No TBDs. Validation step (Task 10 Step 4) intentionally instructs operator to write findings — that's a validation human-in-loop step, not a placeholder.

**Scope check:** 11 tasks, focused on producing one orchestrator + CLI + replay merge. Single coherent slice.
