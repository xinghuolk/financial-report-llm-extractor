# Provider Field Candidate Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline candidate discovery report that maps Turtle P0/P1 fields to observed AKShare/Yahoo raw fields from the checked-in provider baseline fixture.

**Architecture:** Add a focused `structured_sources/field_candidate_discovery.py` module that reads taxonomy, minimal source mappings, provider inventory, and field summary, then writes JSON and Markdown reports. Keep this phase deterministic: no network calls, no LLM calls, and no mutation of `field_catalog/turtle_v015_source_mapping_minimal.json`. Add a small CLI wrapper once the module API is stable.

**Tech Stack:** Python 3.11 standard library, existing dataclasses/loaders, `pytest`, existing CLI patterns in `src/financial_report_llm_extractor/cli.py`.

---

## File Structure

- Create: `src/financial_report_llm_extractor/structured_sources/field_candidate_discovery.py`
  - Owns raw provider field indexing, deterministic matching, JSON report writing, and Markdown report writing.
- Create: `tests/test_field_candidate_discovery.py`
  - Unit tests for indexes, candidate scoring, fixture replay, report writing, and Markdown output.
- Modify: `src/financial_report_llm_extractor/cli.py`
  - Adds `discover-provider-fields` command after the module is tested.
- Modify: `tests/test_cli.py`
  - Adds one CLI delegation test.
- Use existing:
  - `src/financial_report_llm_extractor/field_metadata.py`
  - `src/financial_report_llm_extractor/structured_sources/catalog.py`
  - `src/financial_report_llm_extractor/structured_sources/artifacts.py`
  - `field_catalog/turtle_v015_field_taxonomy.json`
  - `field_catalog/turtle_v015_source_mapping_minimal.json`
  - `tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz`
  - `tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json`

## Task 1: Raw Provider Field Index

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/field_candidate_discovery.py`
- Test: `tests/test_field_candidate_discovery.py`

- [ ] **Step 1: Write failing tests for raw field indexing**

Add `tests/test_field_candidate_discovery.py`:

```python
from decimal import Decimal

from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    ProviderRawField,
    build_provider_raw_field_index,
    normalize_match_text,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
)


def _record(
    *,
    source: str = "akshare",
    ticker: str = "600519",
    statement_type: str = "income_statement",
    period: str = "2025-12-31",
    raw_field_name: str = "营业收入",
    raw_field_code: str | None = "OPERATE_INCOME",
    value: str = "100",
) -> SourceInventoryRecord:
    evidence = SourceEvidence(
        source=source,  # type: ignore[arg-type]
        adapter=source,
        function="fn",
        artifact_id="artifact_1",
        raw_record_id=f"{source}:{ticker}:{statement_type}:{period}:{raw_field_name}",
        raw_field_name=raw_field_name,
        raw_field_code=raw_field_code,
    )
    return SourceInventoryRecord(
        source=source,  # type: ignore[arg-type]
        market="CN" if ticker == "600519" else "HK",
        ticker=ticker,
        statement_type=statement_type,
        period=period,
        raw_field_name=raw_field_name,
        raw_field_code=raw_field_code,
        raw_value=value,
        parsed_numeric_value=Decimal(value),
        currency="CNY" if ticker == "600519" else "HKD",
        unit="yuan" if ticker == "600519" else "raw",
        source_evidence=(evidence,),
    )


def test_normalize_match_text_handles_english_codes_and_chinese() -> None:
    assert normalize_match_text("TOTAL_OPERATE_INCOME") == "total operate income"
    assert normalize_match_text("Total   Revenue") == "total revenue"
    assert normalize_match_text("营业收入") == "营业收入"


def test_build_provider_raw_field_index_groups_targets_periods_and_counts() -> None:
    records = (
        _record(period="2024-12-31"),
        _record(period="2025-12-31"),
        _record(
            source="yahoo",
            ticker="0001.HK",
            raw_field_name="Total Revenue",
            raw_field_code=None,
            value="200",
        ),
    )

    index = build_provider_raw_field_index(records)

    akshare_key = ("akshare", "income_statement", "营业收入", "OPERATE_INCOME")
    yahoo_key = ("yahoo", "income_statement", "Total Revenue", None)
    assert index[akshare_key] == ProviderRawField(
        source="akshare",
        statement_type="income_statement",
        raw_field_name="营业收入",
        raw_field_code="OPERATE_INCOME",
        normalized_names=("营业收入",),
        normalized_codes=("operate income",),
        tickers=("600519",),
        periods=("2024-12-31", "2025-12-31"),
        record_count=2,
    )
    assert index[yahoo_key].tickers == ("0001.HK",)
    assert index[yahoo_key].periods == ("2025-12-31",)
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
uv run pytest tests/test_field_candidate_discovery.py::test_normalize_match_text_handles_english_codes_and_chinese tests/test_field_candidate_discovery.py::test_build_provider_raw_field_index_groups_targets_periods_and_counts -v
```

Expected: fail with `ModuleNotFoundError` for `field_candidate_discovery`.

- [ ] **Step 3: Implement raw field index**

Create `src/financial_report_llm_extractor/structured_sources/field_candidate_discovery.py`:

```python
"""Provider raw field candidate discovery for Turtle mappings."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from typing import Iterable, Literal

from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
    SourceName,
)

CandidateStrength = Literal["strong", "medium", "weak"]
FieldCandidateStatus = Literal[
    "has_candidates",
    "no_candidates",
    "not_applicable",
    "catalog_gap",
]

_COMMON_WORDS = {
    "and",
    "the",
    "of",
    "from",
    "to",
    "for",
    "net",
    "total",
}


@dataclass(frozen=True)
class ProviderRawField:
    source: SourceName
    statement_type: str
    raw_field_name: str
    raw_field_code: str | None
    normalized_names: tuple[str, ...]
    normalized_codes: tuple[str, ...]
    tickers: tuple[str, ...]
    periods: tuple[str, ...]
    record_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class _RawFieldBucket:
    source: SourceName
    statement_type: str
    raw_field_name: str
    raw_field_code: str | None
    tickers: set[str]
    periods: set[str]
    record_count: int


def normalize_match_text(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if re.search(r"[\u4e00-\u9fff]", text):
        return re.sub(r"\s+", "", text)
    text = text.replace("_", " ")
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"[^0-9A-Za-z]+", " ", text)
    return " ".join(text.lower().split())


def build_provider_raw_field_index(
    records: Iterable[SourceInventoryRecord],
) -> dict[tuple[str, str, str, str | None], ProviderRawField]:
    grouped: dict[tuple[str, str, str, str | None], _RawFieldBucket] = {}
    for record in records:
        if record.source_status != "present":
            continue
        key = (
            record.source,
            record.statement_type,
            record.raw_field_name,
            record.raw_field_code,
        )
        bucket = grouped.setdefault(
            key,
            _RawFieldBucket(
                source=record.source,
                statement_type=record.statement_type,
                raw_field_name=record.raw_field_name,
                raw_field_code=record.raw_field_code,
                tickers=set(),
                periods=set(),
                record_count=0,
            ),
        )
        bucket.tickers.add(record.ticker)
        if record.period is not None:
            bucket.periods.add(record.period)
        bucket.record_count += 1

    index: dict[tuple[str, str, str, str | None], ProviderRawField] = {}
    for key, bucket in grouped.items():
        raw_field_name = bucket.raw_field_name
        raw_field_code = bucket.raw_field_code
        normalized_names = tuple(
            value
            for value in (normalize_match_text(raw_field_name),)
            if value
        )
        normalized_codes = tuple(
            value
            for value in (
                normalize_match_text(raw_field_code)
                if isinstance(raw_field_code, str)
                else "",
            )
            if value
        )
        index[key] = ProviderRawField(
            source=bucket.source,
            statement_type=bucket.statement_type,
            raw_field_name=raw_field_name,
            raw_field_code=raw_field_code,
            normalized_names=normalized_names,
            normalized_codes=normalized_codes,
            tickers=tuple(sorted(bucket.tickers)),
            periods=tuple(sorted(bucket.periods)),
            record_count=bucket.record_count,
        )
    return index
```

- [ ] **Step 4: Run tests and verify Task 1 passes**

Run:

```bash
uv run pytest tests/test_field_candidate_discovery.py::test_normalize_match_text_handles_english_codes_and_chinese tests/test_field_candidate_discovery.py::test_build_provider_raw_field_index_groups_targets_periods_and_counts -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/financial_report_llm_extractor/structured_sources/field_candidate_discovery.py tests/test_field_candidate_discovery.py
git commit -m "feat: index provider raw fields"
```

## Task 2: Candidate Matching And JSON Report

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/field_candidate_discovery.py`
- Modify: `tests/test_field_candidate_discovery.py`

- [ ] **Step 1: Write failing tests for candidate generation**

Append to `tests/test_field_candidate_discovery.py`:

```python
from financial_report_llm_extractor.field_metadata import FieldTaxonomyEntry
from financial_report_llm_extractor.structured_sources.catalog import SourceMappingEntry
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    ProviderFieldCandidate,
    discover_provider_field_candidates,
)


def _taxonomy_entry(
    field_id: str = "revenue",
    *,
    priority: str = "P0",
    statement_type: str = "income_statement",
    source_mode: str = "direct",
    value_type: str = "money",
    period_type: str = "duration",
    scope_expectation: str = "consolidated",
    currency_requirement: str = "required",
    unit_requirement: str = "required",
    evidence_requirement: str = "source_only_allowed",
    description: str = "Revenue from operations for the reporting period.",
) -> FieldTaxonomyEntry:
    return FieldTaxonomyEntry(
        field_id=field_id,
        priority=priority,  # type: ignore[arg-type]
        domain=(
            statement_type
            if statement_type in {"income_statement", "balance_sheet", "cash_flow"}
            else "notes_and_mda"
        ),  # type: ignore[arg-type]
        statement_type=statement_type,  # type: ignore[arg-type]
        value_type=value_type,  # type: ignore[arg-type]
        source_mode=source_mode,  # type: ignore[arg-type]
        period_type=period_type,  # type: ignore[arg-type]
        scope_expectation=scope_expectation,  # type: ignore[arg-type]
        currency_requirement=currency_requirement,  # type: ignore[arg-type]
        unit_requirement=unit_requirement,  # type: ignore[arg-type]
        evidence_requirement=evidence_requirement,  # type: ignore[arg-type]
        fallback_policy="pdf_allowed",
        description=description,
    )


def _mapping_entry(
    field_id: str = "revenue",
    *,
    priority: str = "P0",
    statement_type: str = "income_statement",
) -> SourceMappingEntry:
    return SourceMappingEntry(
        field_id=field_id,
        priority=priority,
        value_type="money",
        statement_type=statement_type,
        currency_requirement="required",
        unit_requirement="required",
        source_aliases={
            "akshare": ("营业收入", "OPERATE_INCOME"),
            "yahoo": ("Total Revenue",),
        },
        domain=statement_type,
        source_mode="direct",
        primary_route="akshare_direct",
        verification_status="verified",
        fallback_policy="pdf_allowed",
    )


def test_discover_provider_field_candidates_marks_existing_aliases_strong() -> None:
    records = (
        _record(
            period="2024-12-31",
            raw_field_name="营业收入",
            raw_field_code="OPERATE_INCOME",
        ),
        _record(
            period="2025-12-31",
            raw_field_name="营业收入",
            raw_field_code="OPERATE_INCOME",
        ),
        _record(
            source="yahoo",
            ticker="0001.HK",
            raw_field_name="Total Revenue",
            raw_field_code=None,
            value="200",
        ),
    )

    report = discover_provider_field_candidates(
        taxonomy_entries={"revenue": _taxonomy_entry()},
        mapping_entries={"revenue": _mapping_entry()},
        records=records,
        priorities=("P0",),
    )

    field = report.fields["revenue"]
    assert field.status == "has_candidates"
    assert field.providers["akshare"].candidates[0] == ProviderFieldCandidate(
        raw_field_name="营业收入",
        raw_field_code="OPERATE_INCOME",
        score=100,
        strength="strong",
        signals=("existing_alias", "statement_match", "period_support"),
        target_count=1,
        period_count=2,
        record_count=2,
    )
    assert field.providers["yahoo"].candidates[0].strength == "strong"


def test_discover_provider_field_candidates_marks_pdf_only_not_applicable() -> None:
    report = discover_provider_field_candidates(
        taxonomy_entries={
            "audit_opinion": _taxonomy_entry(
                field_id="audit_opinion",
                priority="P4",
                statement_type="notes",
                source_mode="pdf_only",
                value_type="text",
                period_type="annual_text",
                scope_expectation="not_applicable",
                currency_requirement="not_applicable",
                unit_requirement="not_applicable",
                evidence_requirement="pdf_required",
                description="Audit opinion text.",
            )
        },
        mapping_entries={},
        records=(),
        priorities=("P4",),
    )

    assert report.fields["audit_opinion"].status == "not_applicable"
    assert report.fields["audit_opinion"].providers == {}


def test_discover_provider_field_candidates_marks_cross_provider_support() -> None:
    mapping = SourceMappingEntry(
        field_id="revenue",
        priority="P0",
        value_type="money",
        statement_type="income_statement",
        currency_requirement="required",
        unit_requirement="required",
        source_aliases={
            "akshare": ("Total Revenue",),
            "yahoo": ("Total Revenue",),
        },
        domain="income_statement",
        source_mode="direct",
        primary_route="akshare_direct",
        verification_status="expected",
        fallback_policy="pdf_allowed",
    )
    report = discover_provider_field_candidates(
        taxonomy_entries={"revenue": _taxonomy_entry()},
        mapping_entries={"revenue": mapping},
        records=(
            _record(
                source="akshare",
                raw_field_name="Total Revenue",
                raw_field_code=None,
            ),
            _record(
                source="yahoo",
                ticker="0001.HK",
                raw_field_name="Total Revenue",
                raw_field_code=None,
            ),
        ),
        priorities=("P0",),
    )

    akshare_candidate = report.fields["revenue"].providers["akshare"].candidates[0]
    yahoo_candidate = report.fields["revenue"].providers["yahoo"].candidates[0]
    assert "cross_provider_support" in akshare_candidate.signals
    assert "cross_provider_support" in yahoo_candidate.signals
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run pytest tests/test_field_candidate_discovery.py::test_discover_provider_field_candidates_marks_existing_aliases_strong tests/test_field_candidate_discovery.py::test_discover_provider_field_candidates_marks_pdf_only_not_applicable tests/test_field_candidate_discovery.py::test_discover_provider_field_candidates_marks_cross_provider_support -v
```

Expected: fail because `ProviderFieldCandidate` and `discover_provider_field_candidates` are not implemented.

- [ ] **Step 3: Implement candidate dataclasses and discovery**

Append to `field_candidate_discovery.py`:

```python
from financial_report_llm_extractor.field_metadata import FieldTaxonomyEntry
from financial_report_llm_extractor.structured_sources.catalog import SourceMappingEntry


@dataclass(frozen=True)
class ProviderFieldCandidate:
    raw_field_name: str
    raw_field_code: str | None
    score: int
    strength: CandidateStrength
    signals: tuple[str, ...]
    target_count: int
    period_count: int
    record_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderCandidateGroup:
    candidates: tuple[ProviderFieldCandidate, ...]

    def to_dict(self) -> dict[str, object]:
        return {"candidates": [candidate.to_dict() for candidate in self.candidates]}


@dataclass(frozen=True)
class FieldCandidateReportEntry:
    priority: str
    statement_type: str
    source_mode: str
    status: FieldCandidateStatus
    providers: dict[str, ProviderCandidateGroup]

    def to_dict(self) -> dict[str, object]:
        return {
            "priority": self.priority,
            "statement_type": self.statement_type,
            "source_mode": self.source_mode,
            "status": self.status,
            "providers": {
                source: group.to_dict()
                for source, group in sorted(self.providers.items())
            },
        }


@dataclass(frozen=True)
class ProviderFieldCandidateReport:
    report_id: str
    version: str
    taxonomy_catalog: str
    mapping_catalog: str
    fixture: str
    priorities: tuple[str, ...]
    fields: dict[str, FieldCandidateReportEntry]

    @property
    def summary(self) -> dict[str, int]:
        statuses = [entry.status for entry in self.fields.values()]
        return {
            "field_count": len(statuses),
            "fields_with_candidates": statuses.count("has_candidates"),
            "fields_without_candidates": statuses.count("no_candidates"),
            "not_applicable_fields": statuses.count("not_applicable"),
            "catalog_gap_fields": statuses.count("catalog_gap"),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "report_id": self.report_id,
            "version": self.version,
            "taxonomy_catalog": self.taxonomy_catalog,
            "mapping_catalog": self.mapping_catalog,
            "fixture": self.fixture,
            "priorities": list(self.priorities),
            "fields": {
                field_id: entry.to_dict()
                for field_id, entry in sorted(self.fields.items())
            },
            "summary": self.summary,
        }


def discover_provider_field_candidates(
    *,
    taxonomy_entries: dict[str, FieldTaxonomyEntry],
    mapping_entries: dict[str, SourceMappingEntry],
    records: Iterable[SourceInventoryRecord],
    priorities: tuple[str, ...] = ("P0", "P1"),
    fixture: str = "provider_field_baseline",
    taxonomy_catalog: str = "turtle_v015_field_taxonomy",
    mapping_catalog: str = "turtle_v015_source_mapping_minimal",
) -> ProviderFieldCandidateReport:
    raw_index = build_provider_raw_field_index(records)
    selected_priorities = set(priorities)
    fields: dict[str, FieldCandidateReportEntry] = {}
    for field_id, taxonomy in sorted(taxonomy_entries.items()):
        if taxonomy.priority not in selected_priorities:
            continue
        if taxonomy.source_mode in {"pdf_only", "llm_review"}:
            fields[field_id] = FieldCandidateReportEntry(
                priority=taxonomy.priority,
                statement_type=taxonomy.statement_type,
                source_mode=taxonomy.source_mode,
                status="not_applicable",
                providers={},
            )
            continue

        mapping = mapping_entries.get(field_id)
        provider_groups: dict[str, ProviderCandidateGroup] = {}
        for source in ("akshare", "yahoo"):
            candidates = _rank_provider_candidates(
                field_id=field_id,
                taxonomy=taxonomy,
                mapping=mapping,
                source=source,
                raw_fields=raw_index.values(),
            )
            if candidates:
                provider_groups[source] = ProviderCandidateGroup(candidates=candidates)
        provider_groups = _add_cross_provider_support(provider_groups)
        if provider_groups:
            status: FieldCandidateStatus = "has_candidates"
        elif mapping is None:
            status = "catalog_gap"
        else:
            status = "no_candidates"
        fields[field_id] = FieldCandidateReportEntry(
            priority=taxonomy.priority,
            statement_type=taxonomy.statement_type,
            source_mode=taxonomy.source_mode,
            status=status,
            providers=provider_groups,
        )

    return ProviderFieldCandidateReport(
        report_id="provider_field_candidate_report",
        version="1",
        taxonomy_catalog=taxonomy_catalog,
        mapping_catalog=mapping_catalog,
        fixture=fixture,
        priorities=priorities,
        fields=fields,
    )


def _rank_provider_candidates(
    *,
    field_id: str,
    taxonomy: FieldTaxonomyEntry,
    mapping: SourceMappingEntry | None,
    source: str,
    raw_fields: Iterable[ProviderRawField],
) -> tuple[ProviderFieldCandidate, ...]:
    source_aliases = set(mapping.source_aliases.get(source, ())) if mapping else set()
    normalized_aliases = {normalize_match_text(alias) for alias in source_aliases}
    field_tokens = _field_tokens(field_id, taxonomy)
    candidates: list[ProviderFieldCandidate] = []
    for raw in raw_fields:
        if raw.source != source:
            continue
        if raw.statement_type != taxonomy.statement_type:
            continue
        signals: list[str] = ["statement_match"]
        raw_labels = {
            raw.raw_field_name,
            raw.raw_field_code or "",
            *raw.normalized_names,
            *raw.normalized_codes,
        }
        normalized_raw_labels = {
            normalize_match_text(label)
            for label in raw_labels
            if label
        }
        if source_aliases.intersection(raw_labels) or normalized_aliases.intersection(
            normalized_raw_labels
        ):
            signals.insert(0, "existing_alias")
        elif normalized_raw_labels.intersection(field_tokens):
            signals.insert(0, "exact_text")
        elif _keyword_overlap(field_tokens, normalized_raw_labels) >= 2:
            signals.insert(0, "keyword_overlap")
        else:
            continue
        if len(raw.periods) > 1:
            signals.append("period_support")
        if len(raw.tickers) > 1:
            signals.append("provider_presence")
        score = _score_signals(signals)
        candidates.append(
            ProviderFieldCandidate(
                raw_field_name=raw.raw_field_name,
                raw_field_code=raw.raw_field_code,
                score=score,
                strength=_strength_for_score(score),
                signals=tuple(signals),
                target_count=len(raw.tickers),
                period_count=len(raw.periods),
                record_count=raw.record_count,
            )
        )
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                -candidate.score,
                candidate.raw_field_name,
                candidate.raw_field_code or "",
            ),
        )[:10]
    )


def _add_cross_provider_support(
    provider_groups: dict[str, ProviderCandidateGroup],
) -> dict[str, ProviderCandidateGroup]:
    if set(provider_groups) != {"akshare", "yahoo"}:
        return provider_groups
    provider_labels = {
        source: {
            normalize_match_text(candidate.raw_field_name)
            for candidate in group.candidates
        }
        for source, group in provider_groups.items()
    }
    shared_labels = provider_labels["akshare"].intersection(provider_labels["yahoo"])
    if not shared_labels:
        return provider_groups

    updated: dict[str, ProviderCandidateGroup] = {}
    for source, group in provider_groups.items():
        updated_candidates: list[ProviderFieldCandidate] = []
        for candidate in group.candidates:
            if normalize_match_text(candidate.raw_field_name) not in shared_labels:
                updated_candidates.append(candidate)
                continue
            signals = tuple((*candidate.signals, "cross_provider_support"))
            score = min(candidate.score + 5, 100)
            updated_candidates.append(
                replace(
                    candidate,
                    score=score,
                    strength=_strength_for_score(score),
                    signals=signals,
                )
            )
        updated[source] = ProviderCandidateGroup(candidates=tuple(updated_candidates))
    return updated


def _field_tokens(field_id: str, taxonomy: FieldTaxonomyEntry) -> set[str]:
    values = [field_id, taxonomy.description]
    tokens: set[str] = set()
    for value in values:
        normalized = normalize_match_text(value)
        tokens.add(normalized)
        tokens.update(part for part in normalized.split() if part not in _COMMON_WORDS)
    return {token for token in tokens if token}


def _keyword_overlap(field_tokens: set[str], raw_labels: set[str]) -> int:
    raw_tokens: set[str] = set()
    for label in raw_labels:
        raw_tokens.add(label)
        raw_tokens.update(part for part in label.split() if part not in _COMMON_WORDS)
    return len(field_tokens.intersection(raw_tokens))


def _score_signals(signals: list[str]) -> int:
    score = 0
    if "existing_alias" in signals:
        score += 80
    if "exact_text" in signals:
        score += 70
    if "keyword_overlap" in signals:
        score += 40
    if "statement_match" in signals:
        score += 10
    if "period_support" in signals:
        score += 10
    if "provider_presence" in signals:
        score += 5
    return min(score, 100)


def _strength_for_score(score: int) -> CandidateStrength:
    if score >= 90:
        return "strong"
    if score >= 60:
        return "medium"
    return "weak"
```

- [ ] **Step 4: Run candidate tests**

Run:

```bash
uv run pytest tests/test_field_candidate_discovery.py::test_discover_provider_field_candidates_marks_existing_aliases_strong tests/test_field_candidate_discovery.py::test_discover_provider_field_candidates_marks_pdf_only_not_applicable tests/test_field_candidate_discovery.py::test_discover_provider_field_candidates_marks_cross_provider_support -v
```

Expected: all three selected tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/financial_report_llm_extractor/structured_sources/field_candidate_discovery.py tests/test_field_candidate_discovery.py
git commit -m "feat: discover provider field candidates"
```

## Task 3: Report Writers And Fixture Regression

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/field_candidate_discovery.py`
- Modify: `tests/test_field_candidate_discovery.py`

- [ ] **Step 1: Write failing tests for JSON/Markdown writers and real fixture summary**

Append:

```python
import json
from pathlib import Path

from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    write_provider_field_candidate_report,
)


def test_write_provider_field_candidate_report_writes_json_and_markdown(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "candidate_report"

    result = write_provider_field_candidate_report(
        taxonomy_path=Path("field_catalog/turtle_v015_field_taxonomy.json"),
        mapping_catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        inventory_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz"
        ),
        summary_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json"
        ),
        output_dir=output_dir,
        priorities=("P0", "P1"),
    )

    assert result.json_path == output_dir / "provider_field_candidate_report.json"
    assert result.markdown_path == output_dir / "provider_field_candidate_report.md"
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["report_id"] == "provider_field_candidate_report"
    assert payload["summary"]["field_count"] == 33
    assert payload["summary"]["inventory_record_count"] == 6771
    assert payload["fields"]["revenue"]["status"] == "has_candidates"
    assert "akshare" in payload["fields"]["revenue"]["providers"]
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "## P0" in markdown
    assert "`revenue`" in markdown
    assert "akshare" in markdown
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
uv run pytest tests/test_field_candidate_discovery.py::test_write_provider_field_candidate_report_writes_json_and_markdown -v
```

Expected: fail because `write_provider_field_candidate_report` is missing.

- [ ] **Step 3: Implement writers**

Extend the module imports at the top so they are:

```python
import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable, Literal

from financial_report_llm_extractor.field_metadata import load_field_taxonomy
from financial_report_llm_extractor.structured_sources.artifacts import read_source_inventory
from financial_report_llm_extractor.structured_sources.catalog import (
    load_source_mapping_catalog,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
    SourceName,
)
```

Append to module:

```python


@dataclass(frozen=True)
class ProviderFieldCandidateReportResult:
    json_path: Path
    markdown_path: Path
    field_count: int


def write_provider_field_candidate_report(
    *,
    taxonomy_path: Path,
    mapping_catalog_path: Path,
    inventory_path: Path,
    summary_path: Path,
    output_dir: Path,
    priorities: tuple[str, ...] = ("P0", "P1"),
) -> ProviderFieldCandidateReportResult:
    taxonomy = load_field_taxonomy(taxonomy_path)
    mapping_catalog = load_source_mapping_catalog(
        mapping_catalog_path,
        priorities=priorities,
    )
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    records = read_source_inventory(inventory_path)
    report = discover_provider_field_candidates(
        taxonomy_entries=taxonomy.fields,
        mapping_entries=mapping_catalog.entries,
        records=records,
        priorities=priorities,
        taxonomy_catalog=taxonomy.catalog_id,
        mapping_catalog=mapping_catalog.catalog_id,
    )
    report_dict = report.to_dict()
    summary_dict = dict(report.summary)
    summary_dict["inventory_record_count"] = int(summary_payload["record_count"])
    summary_dict["source_artifact_count"] = int(
        summary_payload["source_artifact_count"]
    )
    report_dict["summary"] = summary_dict

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "provider_field_candidate_report.json"
    markdown_path = output_dir / "provider_field_candidate_report.md"
    json_path.write_text(
        json.dumps(report_dict, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        _candidate_report_markdown(
            report,
            inventory_record_count=int(summary_payload["record_count"]),
            source_artifact_count=int(summary_payload["source_artifact_count"]),
        ),
        encoding="utf-8",
    )
    return ProviderFieldCandidateReportResult(
        json_path=json_path,
        markdown_path=markdown_path,
        field_count=len(report.fields),
    )


def _candidate_report_markdown(
    report: ProviderFieldCandidateReport,
    *,
    inventory_record_count: int,
    source_artifact_count: int,
) -> str:
    lines = [
        "# Provider Field Candidate Report",
        "",
        f"- Fixture: `{report.fixture}`",
        f"- Priorities: `{','.join(report.priorities)}`",
        f"- Fields: `{len(report.fields)}`",
        f"- Inventory records: `{inventory_record_count}`",
        f"- Source artifacts: `{source_artifact_count}`",
        "",
    ]
    priorities = sorted({entry.priority for entry in report.fields.values()})
    for priority in priorities:
        lines.extend([f"## {priority}", ""])
        for field_id, entry in sorted(report.fields.items()):
            if entry.priority != priority:
                continue
            lines.append(f"### `{field_id}`")
            lines.append("")
            lines.append(
                f"- Status: `{entry.status}`; statement: `{entry.statement_type}`; "
                f"mode: `{entry.source_mode}`"
            )
            if not entry.providers:
                lines.append("")
                continue
            for source, group in sorted(entry.providers.items()):
                lines.append(f"- Provider `{source}`")
                for candidate in group.candidates[:5]:
                    code = candidate.raw_field_code or ""
                    lines.append(
                        f"  - `{candidate.raw_field_name}` `{code}` "
                        f"score={candidate.score} strength=`{candidate.strength}` "
                        f"signals={','.join(candidate.signals)} "
                        f"targets={candidate.target_count} periods={candidate.period_count}"
                    )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Run writer test**

Run:

```bash
uv run pytest tests/test_field_candidate_discovery.py::test_write_provider_field_candidate_report_writes_json_and_markdown -v
```

Expected: pass.

- [ ] **Step 5: Run all candidate discovery tests**

Run:

```bash
uv run pytest tests/test_field_candidate_discovery.py -v
```

Expected: all candidate discovery tests pass.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/financial_report_llm_extractor/structured_sources/field_candidate_discovery.py tests/test_field_candidate_discovery.py
git commit -m "feat: write provider field candidate report"
```

## Task 4: CLI Command

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI delegation test**

Add a fake result dataclass near the other fakes in `tests/test_cli.py`:

```python
@dataclass(frozen=True)
class FakeProviderFieldCandidateResult:
    json_path: Path
    markdown_path: Path
    field_count: int
```

Add test:

```python
def test_discover_provider_fields_command_calls_candidate_discovery_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    taxonomy_path = tmp_path / "taxonomy.json"
    mapping_path = tmp_path / "mapping.json"
    inventory_path = tmp_path / "source_inventory.jsonl.gz"
    summary_path = tmp_path / "provider_field_inventory_summary.json"
    output_dir = tmp_path / "candidate_report"
    calls: list[tuple[Path, Path, Path, Path, Path, tuple[str, ...]]] = []

    def fake_write_provider_field_candidate_report(
        *,
        taxonomy_path: Path,
        mapping_catalog_path: Path,
        inventory_path: Path,
        summary_path: Path,
        output_dir: Path,
        priorities: tuple[str, ...] = ("P0", "P1"),
    ) -> FakeProviderFieldCandidateResult:
        calls.append(
            (
                taxonomy_path,
                mapping_catalog_path,
                inventory_path,
                summary_path,
                output_dir,
                priorities,
            )
        )
        return FakeProviderFieldCandidateResult(
            json_path=output_dir / "provider_field_candidate_report.json",
            markdown_path=output_dir / "provider_field_candidate_report.md",
            field_count=33,
        )

    monkeypatch.setattr(
        cli,
        "write_provider_field_candidate_report",
        fake_write_provider_field_candidate_report,
    )

    exit_code = cli.main(
        [
            "discover-provider-fields",
            "--taxonomy",
            str(taxonomy_path),
            "--mapping-catalog",
            str(mapping_path),
            "--inventory",
            str(inventory_path),
            "--summary",
            str(summary_path),
            "--out",
            str(output_dir),
            "--priorities",
            "P0,P1",
        ]
    )

    assert exit_code == 0
    assert calls == [
        (
            taxonomy_path,
            mapping_path,
            inventory_path,
            summary_path,
            output_dir,
            ("P0", "P1"),
        )
    ]
```

- [ ] **Step 2: Run CLI test and verify it fails**

Run:

```bash
uv run pytest tests/test_cli.py::test_discover_provider_fields_command_calls_candidate_discovery_layer -v
```

Expected: fail because parser does not know `discover-provider-fields`.

- [ ] **Step 3: Add CLI import, parser, and dispatch**

Modify `src/financial_report_llm_extractor/cli.py`.

Add import near other imports:

```python
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    write_provider_field_candidate_report,
)
```

Add parser near source/report commands:

```python
    provider_fields_parser = subparsers.add_parser("discover-provider-fields")
    provider_fields_parser.add_argument("--taxonomy", required=True, type=Path)
    provider_fields_parser.add_argument("--mapping-catalog", required=True, type=Path)
    provider_fields_parser.add_argument("--inventory", required=True, type=Path)
    provider_fields_parser.add_argument("--summary", required=True, type=Path)
    provider_fields_parser.add_argument("--out", required=True, type=Path)
    provider_fields_parser.add_argument("--priorities", default="P0,P1")
```

Add dispatch before final return:

```python
    if args.command == "discover-provider-fields":
        priorities = tuple(
            priority.strip()
            for priority in args.priorities.split(",")
            if priority.strip()
        )
        result = write_provider_field_candidate_report(
            taxonomy_path=args.taxonomy,
            mapping_catalog_path=args.mapping_catalog,
            inventory_path=args.inventory,
            summary_path=args.summary,
            output_dir=args.out,
            priorities=priorities,
        )
        print(f"fields={result.field_count}")
        print(f"candidate_report_path={result.json_path}")
        print(f"candidate_markdown_path={result.markdown_path}")
        return 0
```

- [ ] **Step 4: Run CLI test**

Run:

```bash
uv run pytest tests/test_cli.py::test_discover_provider_fields_command_calls_candidate_discovery_layer -v
```

Expected: pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/financial_report_llm_extractor/cli.py tests/test_cli.py
git commit -m "feat: add provider field discovery cli"
```

## Task 5: End-To-End Fixture Verification

**Files:**
- Modify: `tests/test_field_candidate_discovery.py`
- Generated but not committed: `tmp/runs/provider_field_candidate_discovery/`

- [ ] **Step 1: Add an end-to-end CLI-free fixture test**

Append:

```python
def test_provider_field_candidate_report_fixture_summary_is_stable(
    tmp_path: Path,
) -> None:
    result = write_provider_field_candidate_report(
        taxonomy_path=Path("field_catalog/turtle_v015_field_taxonomy.json"),
        mapping_catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        inventory_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz"
        ),
        summary_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json"
        ),
        output_dir=tmp_path,
        priorities=("P0", "P1"),
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["field_count"] == 33
    assert payload["summary"]["inventory_record_count"] == 6771
    assert payload["summary"]["fields_with_candidates"] >= 9
    revenue_candidates = payload["fields"]["revenue"]["providers"]["akshare"][
        "candidates"
    ]
    total_assets_candidates = payload["fields"]["total_assets"]["providers"]["yahoo"][
        "candidates"
    ]
    assert revenue_candidates[0]["strength"] == "strong"
    assert total_assets_candidates[0]["strength"] == "strong"
```

- [ ] **Step 2: Run the fixture summary test**

Run:

```bash
uv run pytest tests/test_field_candidate_discovery.py::test_provider_field_candidate_report_fixture_summary_is_stable -v
```

Expected: pass with `field_count == 33` and `inventory_record_count == 6771`.

- [ ] **Step 3: Run the real command locally without network**

Run:

```bash
uv run financial-report-llm-extractor discover-provider-fields \
  --taxonomy field_catalog/turtle_v015_field_taxonomy.json \
  --mapping-catalog field_catalog/turtle_v015_source_mapping_minimal.json \
  --inventory tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz \
  --summary tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json \
  --out tmp/runs/provider_field_candidate_discovery \
  --priorities P0,P1
```

Expected:

```text
fields=33
candidate_report_path=tmp/runs/provider_field_candidate_discovery/provider_field_candidate_report.json
candidate_markdown_path=tmp/runs/provider_field_candidate_discovery/provider_field_candidate_report.md
```

- [ ] **Step 4: Inspect generated summary**

Run:

```bash
jq '.summary' tmp/runs/provider_field_candidate_discovery/provider_field_candidate_report.json
```

Expected: `field_count` is `33`, and `fields_with_candidates` is nonzero.

- [ ] **Step 5: Run full verification**

Run:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
git diff --check
```

Expected: all pass.

- [ ] **Step 6: Commit Task 5**

```bash
git add tests/test_field_candidate_discovery.py
git commit -m "test: validate provider field discovery fixture"
```

## Final Review Checklist

- [ ] `field_candidate_discovery.py` does not import AKShare, yfinance, or LLM modules.
- [ ] Candidate discovery reads only local inventory/metadata files.
- [ ] No code modifies `field_catalog/turtle_v015_source_mapping_minimal.json`.
- [ ] `.jsonl.gz` fixture remains readable through `read_source_inventory()`.
- [ ] Generated `tmp/runs/provider_field_candidate_discovery/` artifacts are not committed.
- [ ] Full verification passes.
