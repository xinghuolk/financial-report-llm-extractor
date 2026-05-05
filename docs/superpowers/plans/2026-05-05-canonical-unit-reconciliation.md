# Canonical Unit Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove false AKShare/Yahoo conflicts caused by provider unit labels while preserving real value and currency disagreements.

**Architecture:** Add additive canonical-unit metadata to source mapping candidates and mapped fields, using the existing `MoneyAmount.normalized_unit` as the comparison unit. Update reconciliation to compare canonical units rather than provider-reported unit labels, then fix source-first export so equivalent/close ambiguous candidates become complete present items. Validate the behavior with unit tests and the checked-in no-network provider baseline replay fixture.

**Tech Stack:** Python 3.11 standard library, existing dataclass contracts, existing money normalizer, source mapping/reconciliation/export modules, `pytest`, `ruff`, `mypy`.

---

## File Structure

- Modify: `src/financial_report_llm_extractor/structured_sources/mapping.py`
  - Add `canonical_unit` to `TurtleMappingCandidate` and `MappedTurtleField`.
  - Populate canonical units from `normalize_money(...).normalized_unit`.
  - Use canonical units for derivation compatibility.
- Modify: `src/financial_report_llm_extractor/structured_sources/reconciliation.py`
  - Compare `canonical_unit` instead of provider `unit`.
  - Keep value disagreement conflicts explicit.
- Modify: `src/financial_report_llm_extractor/structured_sources/export.py`
  - Add `canonical_unit` to exported source-first items.
  - Promote equivalent/close ambiguous candidates with complete metadata.
- Modify: `tests/test_source_mapping.py`
  - Add mapping and derivation tests for provider unit vs canonical unit.
- Modify: `tests/test_source_reconciliation.py`
  - Add unit-label false-conflict and real-value-conflict tests.
- Modify: `tests/test_source_review_export.py`
  - Add complete metadata test for equivalent ambiguous export promotion.
- Modify: `tests/test_provider_baseline_replay.py`
  - Add no-network baseline regression for improved `600519` combined coverage and remaining real conflicts.
- Optional generated local artifacts: `tmp/runs/provider_baseline_period_replay/`
  - Re-run locally for review only; do not commit generated `tmp/` files.

## Task 1: Add Canonical Unit To Mapping Candidates

**Files:**
- Modify: `tests/test_source_mapping.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/mapping.py`

- [ ] **Step 1: Write failing candidate canonical-unit test**

Add this test to `tests/test_source_mapping.py`:

```python
def test_map_source_inventory_preserves_provider_unit_and_adds_canonical_unit() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "cash": _entry(
                "cash",
                statement_type="balance_sheet",
                source_aliases={"yahoo": ("Cash And Cash Equivalents",)},
            )
        },
    )
    records = [
        SourceInventoryRecord(
            source="yahoo",
            market="CN",
            ticker="600519.SS",
            statement_type="balance_sheet",
            period="2025-12-31",
            raw_field_name="Cash And Cash Equivalents",
            raw_value="51690610946.5",
            parsed_numeric_value=Decimal("51690610946.5"),
            currency="CNY",
            unit="raw",
            scope="consolidated",
            source_evidence=(
                SourceEvidence(
                    source="yahoo",
                    adapter="yahoo",
                    function="fixture",
                    artifact_id="yahoo_cn_600519_ss_balance_sheet",
                    raw_record_id="cash",
                    raw_field_name="Cash And Cash Equivalents",
                ),
            ),
        )
    ]

    result = map_source_inventory(catalog, records)

    mapped = result.fields["cash"]
    assert mapped.status == "present"
    assert mapped.unit == "raw"
    assert mapped.canonical_unit == "CNY"
    assert mapped.candidates[0].unit == "raw"
    assert mapped.candidates[0].canonical_unit == "CNY"
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
uv run pytest tests/test_source_mapping.py::test_map_source_inventory_preserves_provider_unit_and_adds_canonical_unit -v
```

Expected: fail with `AttributeError` or dataclass constructor error because `canonical_unit` is not defined.

- [ ] **Step 3: Implement canonical unit fields**

In `src/financial_report_llm_extractor/structured_sources/mapping.py`, add `canonical_unit` as additive metadata:

```python
@dataclass(frozen=True)
class TurtleMappingCandidate:
    source: SourceName
    raw_field_name: str
    raw_field_code: str | None
    raw_value: str | int | float | None
    value: Decimal | None
    normalized_value: Decimal | None
    currency: Currency
    unit: str | None
    canonical_unit: Currency | None
    period: str | None
    scope: str
    source_evidence: tuple[SourceEvidence, ...]
    errors: tuple[str, ...] = field(default_factory=tuple)
```

```python
@dataclass(frozen=True)
class MappedTurtleField:
    field_id: str
    status: MappedFieldStatus
    value: Decimal | None = None
    normalized_value: Decimal | None = None
    currency: Currency = "unknown"
    unit: str | None = None
    canonical_unit: Currency | None = None
    period: str | None = None
    scope: str = "unknown"
    candidates: tuple[TurtleMappingCandidate, ...] = field(default_factory=tuple)
    source_evidence: tuple[SourceEvidence, ...] = field(default_factory=tuple)
    derived_from: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
```

Update both `to_dict()` methods to include `"canonical_unit": self.canonical_unit`.

In `_candidate_from_record()`, capture `money.normalized_unit`:

```python
canonical_unit: Currency | None = None
try:
    record.validate()
    money = normalize_money(
        str(record.raw_value),
        unit_context=f"{record.currency} {record.unit}",
    )
    value = money.value
    normalized_value = money.normalized_value
    canonical_unit = money.normalized_unit
except (ValueError, MoneyNormalizationError) as exc:
    errors.append(str(exc))
```

Return the candidate with `canonical_unit=canonical_unit`.

When mapping a single direct candidate, copy the candidate canonical unit:

```python
return MappedTurtleField(
    field_id=entry.field_id,
    status="present",
    value=candidate.value,
    normalized_value=candidate.normalized_value,
    currency=candidate.currency,
    unit=candidate.unit,
    canonical_unit=candidate.canonical_unit,
    period=candidate.period,
    scope=candidate.scope,
    candidates=candidates,
    source_evidence=candidate.source_evidence,
)
```

- [ ] **Step 4: Run source mapping tests**

Run:

```bash
uv run pytest tests/test_source_mapping.py -v
```

Expected: pass after updating existing expected dictionaries that serialize mapped fields.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/financial_report_llm_extractor/structured_sources/mapping.py tests/test_source_mapping.py
git commit -m "feat: add canonical unit to source mapping"
```

## Task 2: Use Canonical Units For Derivation Compatibility

**Files:**
- Modify: `tests/test_source_mapping.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/mapping.py`

- [ ] **Step 1: Write failing derivation compatibility tests**

Add these tests to `tests/test_source_mapping.py`:

```python
def test_map_source_inventory_derives_when_provider_units_differ_but_canonical_units_match() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "total_assets": _entry(
                "total_assets",
                statement_type="balance_sheet",
                source_aliases={"akshare": ("资产总计",)},
            ),
            "total_liabilities": _entry(
                "total_liabilities",
                statement_type="balance_sheet",
                source_aliases={"yahoo": ("Total Liabilities",)},
            ),
            "equity": _entry(
                "equity",
                statement_type="balance_sheet",
                source_aliases={"akshare": ("所有者权益合计",)},
                derivation="total_assets - total_liabilities",
            ),
        },
    )
    records = [
        _record("资产总计", "1000", Decimal("1000"), source="akshare", statement_type="balance_sheet"),
        SourceInventoryRecord(
            source="yahoo",
            market="CN",
            ticker="600519.SS",
            statement_type="balance_sheet",
            period="2024-12-31",
            raw_field_name="Total Liabilities",
            raw_value="400",
            parsed_numeric_value=Decimal("400"),
            currency="CNY",
            unit="raw",
            scope="consolidated",
            source_evidence=(
                SourceEvidence(
                    source="yahoo",
                    adapter="yahoo",
                    function="fixture",
                    artifact_id="yahoo_artifact",
                    raw_record_id="liab",
                    raw_field_name="Total Liabilities",
                ),
            ),
        ),
    ]

    result = map_source_inventory(catalog, records)

    mapped = result.fields["equity"]
    assert mapped.status == "derived"
    assert mapped.value == Decimal("600")
    assert mapped.unit == "yuan"
    assert mapped.canonical_unit == "CNY"
```

```python
def test_map_source_inventory_blocks_derivation_when_currencies_differ() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "total_assets": _entry(
                "total_assets",
                statement_type="balance_sheet",
                source_aliases={"akshare": ("资产总计",)},
            ),
            "total_liabilities": _entry(
                "total_liabilities",
                statement_type="balance_sheet",
                source_aliases={"yahoo": ("Total Liabilities",)},
            ),
            "equity": _entry(
                "equity",
                statement_type="balance_sheet",
                source_aliases={"akshare": ("所有者权益合计",)},
                derivation="total_assets - total_liabilities",
            ),
        },
    )
    records = [
        _record("资产总计", "1000", Decimal("1000"), source="akshare", statement_type="balance_sheet"),
        SourceInventoryRecord(
            source="yahoo",
            market="HK",
            ticker="0001.HK",
            statement_type="balance_sheet",
            period="2024-12-31",
            raw_field_name="Total Liabilities",
            raw_value="400",
            parsed_numeric_value=Decimal("400"),
            currency="HKD",
            unit="raw",
            scope="consolidated",
            source_evidence=(
                SourceEvidence(
                    source="yahoo",
                    adapter="yahoo",
                    function="fixture",
                    artifact_id="yahoo_artifact",
                    raw_record_id="liab",
                    raw_field_name="Total Liabilities",
                ),
            ),
        ),
    ]

    result = map_source_inventory(catalog, records)

    mapped = result.fields["equity"]
    assert mapped.status == "blocked"
    assert mapped.errors == ("derivation inputs use different currencies",)
```

- [ ] **Step 2: Run focused derivation tests and verify the first fails**

Run:

```bash
uv run pytest tests/test_source_mapping.py::test_map_source_inventory_derives_when_provider_units_differ_but_canonical_units_match tests/test_source_mapping.py::test_map_source_inventory_blocks_derivation_when_currencies_differ -v
```

Expected: first test fails with `derivation inputs use different units`; second test protects the existing currency incompatibility guard.

- [ ] **Step 3: Update derivation compatibility**

In `_compatibility_error()` in `mapping.py`, replace provider-unit comparison with canonical-unit comparison:

```python
if left.canonical_unit != right.canonical_unit:
    return "derivation inputs use different canonical units"
```

Keep currency, period, and scope checks before the canonical-unit check. In `_derive_field()`, set `canonical_unit=left.canonical_unit`.

- [ ] **Step 4: Run source mapping tests**

Run:

```bash
uv run pytest tests/test_source_mapping.py -v
```

Expected: pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/financial_report_llm_extractor/structured_sources/mapping.py tests/test_source_mapping.py
git commit -m "fix: derive fields using canonical units"
```

## Task 3: Reconcile By Canonical Unit And Normalized Value

**Files:**
- Modify: `tests/test_source_reconciliation.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/reconciliation.py`

- [ ] **Step 1: Write failing reconciliation tests**

Add these tests to `tests/test_source_reconciliation.py`:

```python
def test_reconcile_treats_provider_unit_labels_as_equivalent_when_canonical_units_match() -> None:
    result = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "cash": MappedTurtleField(
                field_id="cash",
                status="ambiguous",
                candidates=(
                    _candidate(
                        "akshare",
                        Decimal("51690610946.5"),
                        unit="yuan",
                        canonical_unit="CNY",
                    ),
                    _candidate(
                        "yahoo",
                        Decimal("51690610946.5"),
                        unit="raw",
                        canonical_unit="CNY",
                    ),
                ),
                errors=("multiple source candidates matched catalog aliases",),
            )
        },
    )

    report = reconcile_mapped_fields(result)

    item = report.items["cash"]
    assert item.status == "equivalent"
    assert item.reason == "candidate normalized values are equal"
    assert item.max_difference == Decimal("0.0")
```

```python
def test_reconcile_keeps_same_canonical_unit_value_disagreements_as_conflicts() -> None:
    result = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "revenue": MappedTurtleField(
                field_id="revenue",
                status="ambiguous",
                candidates=(
                    _candidate(
                        "akshare",
                        Decimal("168838102514.79"),
                        unit="yuan",
                        canonical_unit="CNY",
                    ),
                    _candidate(
                        "yahoo",
                        Decimal("172054171890.91"),
                        unit="raw",
                        canonical_unit="CNY",
                    ),
                ),
                errors=("multiple source candidates matched catalog aliases",),
            )
        },
    )

    report = reconcile_mapped_fields(result)

    item = report.items["revenue"]
    assert item.status == "conflict"
    assert item.reason == "candidate normalized values differ"
    assert item.max_difference == Decimal("3216069376.12")
```

```python
def test_reconcile_conflicts_when_canonical_units_differ() -> None:
    result = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "cash": MappedTurtleField(
                field_id="cash",
                status="ambiguous",
                candidates=(
                    _candidate("akshare", Decimal("100"), canonical_unit="CNY"),
                    _candidate("yahoo", Decimal("100"), unit="raw", canonical_unit="HKD"),
                ),
                errors=("multiple source candidates matched catalog aliases",),
            )
        },
    )

    report = reconcile_mapped_fields(result)

    item = report.items["cash"]
    assert item.status == "conflict"
    assert item.reason == "candidate canonical units differ"
```

Update the existing helper in `tests/test_source_reconciliation.py` so existing tests keep their defaults while new tests can pass canonical units:

```python
def _candidate(
    source: SourceName,
    normalized_value: Decimal,
    *,
    period: str = "2024-12-31",
    currency: str = "CNY",
    unit: str = "yuan",
    canonical_unit: str | None = "CNY",
    scope: str = "consolidated",
) -> TurtleMappingCandidate:
    return TurtleMappingCandidate(
        source=source,
        raw_field_name="Revenue",
        raw_field_code=None,
        raw_value=str(normalized_value),
        value=normalized_value,
        normalized_value=normalized_value,
        currency=currency,  # type: ignore[arg-type]
        unit=unit,
        canonical_unit=canonical_unit,  # type: ignore[arg-type]
        period=period,
        scope=scope,
        source_evidence=(
            SourceEvidence(
                source=source,
                adapter=source,
                function="fixture",
                artifact_id=f"{source}_artifact",
                raw_record_id=f"{source}:revenue",
                raw_field_name="Revenue",
            ),
        ),
    )
```

- [ ] **Step 2: Run focused reconciliation tests and verify the first fails**

Run:

```bash
uv run pytest tests/test_source_reconciliation.py -v
```

Expected: false-equivalence test fails because reconciliation still checks provider `unit`.

- [ ] **Step 3: Update metadata comparison**

In `src/financial_report_llm_extractor/structured_sources/reconciliation.py`, change `_metadata_error()`:

```python
if len({candidate.canonical_unit for candidate in candidates}) > 1:
    return "candidate canonical units differ"
```

Remove the provider `unit` comparison from reconciliation. Keep currency and period comparisons. Add scope comparison that ignores unknown scopes:

```python
known_scopes = {candidate.scope for candidate in candidates if candidate.scope != "unknown"}
if len(known_scopes) > 1:
    return "candidate scopes differ"
```

- [ ] **Step 4: Run reconciliation tests**

Run:

```bash
uv run pytest tests/test_source_reconciliation.py -v
```

Expected: pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/financial_report_llm_extractor/structured_sources/reconciliation.py tests/test_source_reconciliation.py
git commit -m "fix: reconcile source candidates by canonical unit"
```

## Task 4: Export Complete Metadata For Equivalent Ambiguous Candidates

**Files:**
- Modify: `tests/test_source_review_export.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/export.py`

- [ ] **Step 1: Write failing export promotion test**

Add this test to `tests/test_source_review_export.py`:

```python
def test_source_first_export_promotes_equivalent_ambiguous_candidates_with_candidate_metadata() -> None:
    akshare_evidence = SourceEvidence(
        source="akshare",
        adapter="akshare",
        function="fixture",
        artifact_id="akshare_cash",
        raw_record_id="a",
        raw_field_name="货币资金",
    )
    yahoo_evidence = SourceEvidence(
        source="yahoo",
        adapter="yahoo",
        function="fixture",
        artifact_id="yahoo_cash",
        raw_record_id="y",
        raw_field_name="Cash And Cash Equivalents",
    )
    mapping = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "cash": MappedTurtleField(
                field_id="cash",
                status="ambiguous",
                candidates=(
                    TurtleMappingCandidate(
                        source="akshare",
                        raw_field_name="货币资金",
                        raw_field_code="MONETARYFUNDS",
                        raw_value="100",
                        value=Decimal("100"),
                        normalized_value=Decimal("100"),
                        currency="CNY",
                        unit="yuan",
                        canonical_unit="CNY",
                        period="2025-12-31",
                        scope="consolidated",
                        source_evidence=(akshare_evidence,),
                    ),
                    TurtleMappingCandidate(
                        source="yahoo",
                        raw_field_name="Cash And Cash Equivalents",
                        raw_field_code=None,
                        raw_value="100",
                        value=Decimal("100"),
                        normalized_value=Decimal("100"),
                        currency="CNY",
                        unit="raw",
                        canonical_unit="CNY",
                        period="2025-12-31",
                        scope="consolidated",
                        source_evidence=(yahoo_evidence,),
                    ),
                ),
                errors=("multiple source candidates matched catalog aliases",),
            )
        },
    )
    reconciliation = reconcile_mapped_fields(mapping)

    exported = build_source_first_export(
        mapping,
        reconciliation,
        profile="source_only",
    )

    item = exported.items["cash"]
    assert item.status == "present"
    assert item.value == Decimal("100")
    assert item.normalized_value == Decimal("100")
    assert item.currency == "CNY"
    assert item.unit == "yuan"
    assert item.canonical_unit == "CNY"
    assert item.period == "2025-12-31"
    assert item.scope == "consolidated"
    assert len(item.source_evidence) == 2
    assert item.errors == ()
    assert item.warnings == ("multiple source candidates reconciled as equivalent",)
```

- [ ] **Step 2: Run focused export test and verify it fails**

Run:

```bash
uv run pytest tests/test_source_review_export.py::test_source_first_export_promotes_equivalent_ambiguous_candidates_with_candidate_metadata -v
```

Expected: fail because ambiguous mapped fields currently export default field metadata instead of representative candidate metadata, and `canonical_unit` is not exported.

- [ ] **Step 3: Add canonical unit to export item**

In `SourceFirstExportItem`, add:

```python
canonical_unit: Currency | None = None
```

Include it in `to_dict()`:

```python
"canonical_unit": self.canonical_unit,
```

Update the import from `financial_report_llm_extractor.structured_sources.mapping` so `export.py` can type the representative helper:

```python
from financial_report_llm_extractor.structured_sources.mapping import (
    MappedTurtleField,
    TurtleMappingCandidate,
    TurtleMappingResult,
)
```

- [ ] **Step 4: Promote representative candidate metadata**

In `_build_item()`, when `field.status == "ambiguous"` and reconciliation is `equivalent` or `close`, select a deterministic representative:

```python
def _representative_candidate(
    candidates: tuple[TurtleMappingCandidate, ...],
) -> TurtleMappingCandidate:
    source_rank = {"akshare": 0, "yahoo": 1}
    return sorted(
        candidates,
        key=lambda candidate: (
            source_rank.get(candidate.source, 99),
            candidate.raw_field_name,
            candidate.raw_field_code or "",
        ),
    )[0]
```

Use the representative's metadata:

```python
candidate = _representative_candidate(field.candidates)
value = candidate.value
normalized_value = candidate.normalized_value
currency = candidate.currency
unit = candidate.unit
canonical_unit = candidate.canonical_unit
period = candidate.period
scope = candidate.scope
source_evidence = tuple(
    evidence
    for candidate in field.candidates
    for evidence in candidate.source_evidence
)
errors = ()
```

Initialize local metadata before the conditional:

```python
currency = field.currency
unit = field.unit
canonical_unit = field.canonical_unit
period = field.period
scope = field.scope
```

Return `SourceFirstExportItem(..., canonical_unit=canonical_unit, period=period, scope=scope, currency=currency, unit=unit, ...)`.

- [ ] **Step 5: Run export tests**

Run:

```bash
uv run pytest tests/test_source_review_export.py -v
```

Expected: pass after updating serialized expected payloads if any.

- [ ] **Step 6: Commit Task 4**

```bash
git add src/financial_report_llm_extractor/structured_sources/export.py tests/test_source_review_export.py
git commit -m "fix: export reconciled candidate metadata"
```

## Task 5: Provider Baseline Regression

**Files:**
- Modify: `tests/test_provider_baseline_replay.py`

- [ ] **Step 1: Add no-network baseline coverage regression**

Add this test to `tests/test_provider_baseline_replay.py`:

```python
def test_provider_baseline_replay_combined_uses_canonical_units_for_600519(tmp_path: Path) -> None:
    result = write_provider_baseline_period_replay(
        inventory_path=Path("tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz"),
        inventory_summary_path=Path("tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json"),
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path,
        company_ids=("600519",),
    )

    company = result.summary["companies"][0]
    combined = company["coverage"]["combined"]
    review = company["review"]["combined"]
    assert combined["covered_count"] >= 12
    assert "cash" in review["present_fields"]
    assert "operating_cash_flow" in review["present_fields"]
    assert "total_assets" in review["present_fields"]
    assert "total_cur_assets" in review["present_fields"]
    assert "total_cur_liab" in review["present_fields"]
    assert "total_liabilities" in review["present_fields"]
    assert "revenue" in review["conflict_fields"]
    assert "net_profit" in review["conflict_fields"]

    reconciliation = json.loads(
        Path(company["artifact_paths"]["combined"]["reconciliation_report"]).read_text(
            encoding="utf-8"
        )
    )
    assert reconciliation["items"]["cash"]["status"] == "equivalent"
    assert reconciliation["items"]["cash"]["reason"] == "candidate normalized values are equal"
    assert reconciliation["items"]["revenue"]["status"] == "conflict"
    assert reconciliation["items"]["revenue"]["reason"] == "candidate normalized values differ"
```

- [ ] **Step 2: Run focused baseline test and verify it fails before Tasks 1-4**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py::test_provider_baseline_replay_combined_uses_canonical_units_for_600519 -v
```

Expected before implementation: fail because combined coverage is still `6/15` and cash is a unit conflict.

- [ ] **Step 3: Run provider baseline replay tests**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py -v
```

Expected after implementation: pass.

- [ ] **Step 4: Optionally regenerate local review artifacts**

Run:

```bash
scripts/run-provider-baseline-period-replay.sh
```

Expected: writes updated artifacts under `tmp/runs/provider_baseline_period_replay/`. Do not commit generated `tmp/` files.

- [ ] **Step 5: Commit Task 5**

```bash
git add tests/test_provider_baseline_replay.py
git commit -m "test: cover provider baseline canonical unit replay"
```

## Task 6: Full Verification

**Files:**
- No code files beyond previous tasks.

- [ ] **Step 1: Run focused structured-source tests**

Run:

```bash
uv run pytest tests/test_source_mapping.py tests/test_source_reconciliation.py tests/test_source_review_export.py tests/test_provider_baseline_replay.py -v
```

Expected: pass.

- [ ] **Step 2: Run full test suite**

Run:

```bash
uv run pytest -v
```

Expected: pass.

- [ ] **Step 3: Run lint**

Run:

```bash
uv run ruff check .
```

Expected: pass.

- [ ] **Step 4: Run type checking**

Run:

```bash
uv run mypy src tests
```

Expected: pass.

- [ ] **Step 5: Run whitespace diff check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 6: Commit final verification note if docs are updated**

If implementation updates roadmap or handoff after verification, commit those docs:

```bash
git add docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md docs/2026-04-30-codex-claude-handoff-prompt.md
git commit -m "docs: record canonical unit reconciliation progress"
```

## Self-Review

- Spec coverage: Tasks 1-4 implement canonical unit mapping, derivation, reconciliation, and export behavior. Task 5 covers provider baseline replay success criteria. Task 6 covers verification.
- Placeholder scan: no placeholder markers or open-ended implementation steps remain.
- Type consistency: `canonical_unit` is consistently modeled as `Currency | None` on mapping candidates, mapped fields, and export items.
- Scope check: this plan does not add aliases, call APIs, perform FX conversion, or choose an authoritative provider for real value disagreements.
