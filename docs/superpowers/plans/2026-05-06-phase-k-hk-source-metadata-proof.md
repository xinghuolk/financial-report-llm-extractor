# Phase K HK Source Metadata Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Hong Kong AKShare and Yahoo source candidates prove currency, unit, and reporting metadata before they can count as clean present.

**Architecture:** Keep Phase K inside the existing `structured_sources` boundary. Add a small metadata proof helper only if the first tests show repeated logic across adapters, mapping, and policy. Reuse `SourceInventoryRecord`, `TurtleMappingCandidate.statement_metadata_proven`, and `SourcePolicyItem` rather than introducing a large metadata model.

**Tech Stack:** Python 3.11 standard library, frozen dataclasses, pytest, existing source-first fixture replay.

---

## File Structure

- Modify `src/financial_report_llm_extractor/structured_sources/akshare_adapter.py`: stop treating HK currency labels as clean unit labels; normalize HK source unit labels before records are created.
- Modify `src/financial_report_llm_extractor/structured_sources/yahoo_adapter.py`: preserve annual metadata from yfinance payload and keep `unit="raw"` as the normal Yahoo statement unit.
- Modify `src/financial_report_llm_extractor/structured_sources/mapping.py`: add minimal candidate proof fields, then tighten `statement_metadata_proven` so HK proof works for AKShare and Yahoo but rejects `unit == currency`.
- Modify `src/financial_report_llm_extractor/structured_sources/source_policy.py`: keep unresolved or warning status when HK primary candidates lack unit/currency/report proof.
- Modify `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`: expose metadata warning counts or field lists in the replay summary if policy already classifies them.
- Test `tests/test_akshare_adapter.py`: HK fixtures use `unit="raw"` and assert currency remains `HKD`.
- Test `tests/test_yahoo_adapter.py`: Yahoo annual metadata and raw-unit proof are preserved.
- Test `tests/test_source_mapping.py`: HK metadata proof fields are serialized, proof passes for valid AKShare/Yahoo candidates, and proof fails when `unit == currency`.
- Test `tests/test_source_policy.py`: policy blocks or warns on HK metadata proof failures.
- Test `tests/test_provider_baseline_replay.py`: provider baseline replay still distinguishes clean present and selected-with-warning for HK.

## Task 1: Normalize HK AKShare Unit Semantics

**Files:**
- Modify: `tests/test_akshare_adapter.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/akshare_adapter.py`

- [ ] **Step 1: Write failing adapter tests for HK raw unit**

Update `test_akshare_hk_statement_inventory_joins_metadata_and_writes_artifact` to call the adapter with `unit="raw"` and assert the unit is no longer `HKD`.

```python
records = adapter.fetch_hk_statement_inventory(
    ticker="00001",
    statement_type="balance_sheet",
    unit="raw",
)

record = records[0]
assert record.currency == "HKD"
assert record.unit == "raw"
assert record.account_standard == "HKFRS"
assert record.report_type == "annual"
```

Add a regression test that rejects currency-as-unit for HK present rows by normalizing to a non-clean metadata state.

```python
def test_akshare_hk_statement_inventory_does_not_use_currency_as_unit(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path)
    adapter = AkshareAdapter(client=FakeAkshareClient(), artifact_store=store)

    records = adapter.fetch_hk_statement_inventory(
        ticker="00001",
        statement_type="balance_sheet",
        unit="HKD",
    )

    assert records[0].currency == "HKD"
    assert records[0].unit == "raw"
```

- [ ] **Step 2: Run the adapter tests and verify failure**

Run:

```bash
uv run pytest tests/test_akshare_adapter.py -v
```

Expected before implementation: at least one assertion fails because HK adapter currently preserves `unit="HKD"`.

- [ ] **Step 3: Implement minimal HK unit normalization**

In `src/financial_report_llm_extractor/structured_sources/akshare_adapter.py`, add this helper near `_normalize_currency`:

```python
def _normalize_source_unit(*, market: str, currency: Currency, unit: str) -> str:
    normalized_unit = unit.strip()
    if market == "HK" and normalized_unit.upper() == currency:
        return "raw"
    return normalized_unit
```

Use it when building HK records:

```python
currency = _normalize_currency(metadata.get("CURRENCY"))
record = SourceInventoryRecord(
    source="akshare",
    market="HK",
    ticker=ticker,
    statement_type=statement_type,
    period=period,
    report_type=_normalize_report_type(_optional_str(metadata.get("REPORT_TYPE"))),
    fiscal_year=_optional_str(row.get("FISCAL_YEAR")),
    account_standard=_optional_str(metadata.get("ACCOUNT_STANDARD")),
    raw_field_name=raw_field_name,
    raw_field_code=raw_field_code,
    raw_value=_raw_value(row.get("AMOUNT")),
    parsed_numeric_value=_parse_decimal(row.get("AMOUNT")),
    currency=currency,
    unit=_normalize_source_unit(market="HK", currency=currency, unit=unit),
    source_evidence=(evidence,),
)
```

Also use the helper in HK missing and unsupported status records.

- [ ] **Step 4: Run focused adapter tests**

Run:

```bash
uv run pytest tests/test_akshare_adapter.py -v
```

Expected: all AKShare adapter tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/financial_report_llm_extractor/structured_sources/akshare_adapter.py tests/test_akshare_adapter.py
git commit -m "fix: normalize hk akshare unit metadata"
```

## Task 2: Add Minimal Candidate Metadata Proof Fields

**Files:**
- Modify: `tests/test_source_mapping.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/mapping.py`

- [ ] **Step 1: Add tests for HK proof fields**

Add tests near the existing `statement_metadata_proven` coverage:

```python
def test_map_source_inventory_serializes_hk_akshare_metadata_proof_fields() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "total_assets": _entry(
                "total_assets",
                source_aliases={"akshare": ("资产总计",)},
                statement_type="balance_sheet",
            )
        },
    )
    records = [
        SourceInventoryRecord(
            source="akshare",
            market="HK",
            ticker="00001",
            statement_type="balance_sheet",
            period="2025-12-31",
            raw_field_name="资产总计",
            raw_value="100",
            parsed_numeric_value=Decimal("100"),
            report_type="annual",
            account_standard="HKFRS",
            currency="HKD",
            unit="raw",
            source_evidence=(_source_evidence("akshare", "资产总计"),),
        )
    ]

    result = map_source_inventory(catalog, records)

    candidate = result.fields["total_assets"].candidates[0]
    assert candidate.statement_metadata_proven is True
    assert candidate.unit_multiplier == Decimal("1")
    assert candidate.currency_proof_source == "akshare_statement_metadata"
    assert candidate.unit_proof_source == "source_unit:raw"
    assert candidate.reporting_metadata_proof_source == "akshare_hk_metadata_join"

    payload = candidate.to_dict()
    assert payload["unit_multiplier"] == "1"
    assert payload["currency_proof_source"] == "akshare_statement_metadata"
    assert payload["unit_proof_source"] == "source_unit:raw"
    assert payload["reporting_metadata_proof_source"] == "akshare_hk_metadata_join"
```

```python
def test_map_source_inventory_marks_hk_yahoo_annual_raw_metadata_proven() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "total_assets": _entry(
                "total_assets",
                source_aliases={"yahoo": ("Total Assets",)},
                statement_type="balance_sheet",
            )
        },
    )
    records = [
        SourceInventoryRecord(
            source="yahoo",
            market="HK",
            ticker="0001.HK",
            statement_type="balance_sheet",
            period="2025-12-31",
            raw_field_name="Total Assets",
            raw_value="100",
            parsed_numeric_value=Decimal("100"),
            report_type="annual",
            currency="HKD",
            unit="raw",
            source_evidence=(_source_evidence("yahoo", "Total Assets"),),
        )
    ]

    result = map_source_inventory(catalog, records)

    candidate = result.fields["total_assets"].candidates[0]
    assert candidate.statement_metadata_proven is True
    assert candidate.unit_multiplier == Decimal("1")
    assert candidate.currency_proof_source == "yahoo_statement_metadata"
    assert candidate.unit_proof_source == "source_unit:raw"
    assert candidate.reporting_metadata_proof_source == "yahoo_annual_statement"
```

```python
def test_map_source_inventory_marks_hk_akshare_metadata_unproven_when_unit_is_currency() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "total_assets": _entry(
                "total_assets",
                source_aliases={"akshare": ("资产总计",)},
                statement_type="balance_sheet",
            )
        },
    )
    records = [
        SourceInventoryRecord(
            source="akshare",
            market="HK",
            ticker="00001",
            statement_type="balance_sheet",
            period="2025-12-31",
            raw_field_name="资产总计",
            raw_value="100",
            parsed_numeric_value=Decimal("100"),
            report_type="annual",
            account_standard="HKFRS",
            currency="HKD",
            unit="HKD",
            source_evidence=(_source_evidence("akshare", "资产总计"),),
        )
    ]

    result = map_source_inventory(catalog, records)

    candidate = result.fields["total_assets"].candidates[0]
    assert candidate.statement_metadata_proven is False
    assert candidate.unit_multiplier == Decimal("1")
    assert candidate.unit_proof_source == "invalid_currency_as_unit"
```

If `_source_evidence()` is not already available in the file, add this helper:

```python
def _source_evidence(source: str, raw_field_name: str) -> SourceEvidence:
    return SourceEvidence(
        source=source,  # type: ignore[arg-type]
        adapter=source,
        function="fixture",
        artifact_id=f"{source}_artifact",
        raw_record_id=f"{source}:{raw_field_name}",
        raw_field_name=raw_field_name,
    )
```

- [ ] **Step 2: Run mapping tests and verify failure**

Run:

```bash
uv run pytest tests/test_source_mapping.py -v
```

Expected before implementation: tests fail because `TurtleMappingCandidate` does not yet expose `unit_multiplier`, `currency_proof_source`, `unit_proof_source`, or `reporting_metadata_proof_source`.

- [ ] **Step 3: Add fields to `TurtleMappingCandidate`**

In `src/financial_report_llm_extractor/structured_sources/mapping.py`, extend the dataclass:

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
    period: str | None
    scope: str
    source_evidence: tuple[SourceEvidence, ...]
    errors: tuple[str, ...] = field(default_factory=tuple)
    canonical_unit: Currency | None = None
    statement_metadata_proven: bool = False
    unit_multiplier: Decimal | None = None
    currency_proof_source: str | None = None
    unit_proof_source: str | None = None
    reporting_metadata_proof_source: str | None = None
```

Update `to_dict()` so `unit_multiplier` serializes as a string:

```python
def to_dict(self) -> dict[str, object]:
    payload = asdict(self)
    for key in ("value", "normalized_value", "unit_multiplier"):
        if payload[key] is not None:
            payload[key] = str(payload[key])
    return payload
```

- [ ] **Step 4: Implement source-aware metadata proof**

In `src/financial_report_llm_extractor/structured_sources/mapping.py`, replace `_statement_metadata_proven()` with:

```python
def _statement_metadata_proven(record: SourceInventoryRecord) -> bool:
    if record.market != "HK":
        return False
    if record.currency in {"unknown", "ambiguous"}:
        return False
    if record.unit is None or record.unit.upper() == record.currency:
        return False
    if record.report_type != "annual":
        return False
    if record.source == "akshare":
        return bool(record.account_standard)
    if record.source == "yahoo":
        return True
    return False
```

Add helper functions below `_statement_metadata_proven()`:

```python
def _currency_proof_source(record: SourceInventoryRecord) -> str | None:
    if record.currency in {"unknown", "ambiguous"}:
        return None
    if record.source == "akshare" and record.market == "HK":
        return "akshare_statement_metadata"
    if record.source == "yahoo":
        return "yahoo_statement_metadata"
    return f"{record.source}_record_currency"


def _unit_proof_source(record: SourceInventoryRecord) -> str | None:
    if record.unit is None:
        return None
    if record.currency not in {"unknown", "ambiguous"} and record.unit.upper() == record.currency:
        return "invalid_currency_as_unit"
    return f"source_unit:{record.unit}"


def _reporting_metadata_proof_source(record: SourceInventoryRecord) -> str | None:
    if not _statement_metadata_proven(record):
        return None
    if record.source == "akshare" and record.market == "HK":
        return "akshare_hk_metadata_join"
    if record.source == "yahoo" and record.report_type == "annual":
        return "yahoo_annual_statement"
    return None
```

In `_candidate_from_record()`, set the new fields after `normalize_money()` succeeds:

```python
unit_multiplier: Decimal | None = None
try:
    record.validate()
    money = normalize_money(
        str(record.raw_value),
        unit_context=f"{record.currency} {record.unit}",
    )
    value = money.value
    normalized_value = money.normalized_value
    canonical_unit = money.normalized_unit
    unit_multiplier = money.unit_multiplier
except (ValueError, MoneyNormalizationError) as exc:
    errors.append(str(exc))
```

Then pass the proof fields into `TurtleMappingCandidate`:

```python
return TurtleMappingCandidate(
    source=record.source,
    raw_field_name=record.raw_field_name,
    raw_field_code=record.raw_field_code,
    raw_value=record.raw_value,
    value=value,
    normalized_value=normalized_value,
    currency=record.currency,
    unit=record.unit,
    period=record.period,
    scope=record.scope,
    source_evidence=record.source_evidence,
    canonical_unit=canonical_unit,
    errors=tuple(errors),
    statement_metadata_proven=_statement_metadata_proven(record),
    unit_multiplier=unit_multiplier,
    currency_proof_source=_currency_proof_source(record),
    unit_proof_source=_unit_proof_source(record),
    reporting_metadata_proof_source=_reporting_metadata_proof_source(record),
)
```

- [ ] **Step 5: Run mapping tests**

Run:

```bash
uv run pytest tests/test_source_mapping.py -v
```

Expected: mapping tests pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/financial_report_llm_extractor/structured_sources/mapping.py tests/test_source_mapping.py
git commit -m "fix: expose hk source metadata proof"
```

## Task 3: Keep HK Policy Warnings Accurate

**Files:**
- Modify: `tests/test_source_policy.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/source_policy.py`

- [ ] **Step 1: Add a policy test for proven Yahoo primary metadata**

Add a test near `test_source_policy_requires_hk_primary_statement_metadata_proof_for_yahoo`:

```python
def test_source_policy_allows_hk_yahoo_primary_when_statement_metadata_is_proven() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            field_id: _entry(
                field_id,
                SourcePolicy(
                    semantic_concept="reported statement line",
                    market_policies={
                        "HK": MarketSourcePolicy(
                            primary_route="yahoo_direct",
                            cross_check_routes=("akshare_direct",),
                            on_conflict="select_primary_require_pdf",
                        )
                    },
                    verification_requirement="pdf_required_on_conflict",
                ),
            )
            for field_id in ("total_assets", "total_cur_assets", "total_liabilities")
        },
    )
    mapping = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "total_assets": _field(
                "total_assets",
                Decimal("100"),
                Decimal("110.71499745"),
                yahoo_statement_metadata_proven=True,
            ),
            "total_cur_assets": _field(
                "total_cur_assets",
                Decimal("50"),
                Decimal("55.357498725"),
                yahoo_statement_metadata_proven=True,
            ),
            "total_liabilities": _field(
                "total_liabilities",
                Decimal("20"),
                Decimal("22.14299949"),
                yahoo_statement_metadata_proven=True,
            ),
        },
    )
    reconciliation = reconcile_mapped_fields(mapping)

    report = build_source_policy_report(
        catalog,
        mapping,
        reconciliation,
        market="HK",
        company_id="00001",
    )

    item = report.items["total_assets"]
    assert item.selection_status == "selected_primary"
    assert item.selected_candidate is not None
    assert item.selected_candidate.source == "yahoo"
    assert item.verification_required is True
    assert item.conflict_classifications == (
        "fx_like_ratio",
        "metadata_currency_suspected",
    )
```

Update the `_field()` helper so it can pass Yahoo proof through:

```python
def _field(
    field_id: str,
    akshare_value: Decimal,
    yahoo_value: Decimal,
    *,
    akshare_statement_metadata_proven: bool = True,
    yahoo_statement_metadata_proven: bool = False,
    period: str = "2025-12-31",
) -> MappedTurtleField:
    return MappedTurtleField(
        field_id=field_id,
        status="ambiguous",
        candidates=(
            _candidate(
                "akshare",
                "总资产",
                "TOTAL_ASSETS",
                akshare_value,
                currency="HKD",
                statement_metadata_proven=akshare_statement_metadata_proven,
                period=period,
            ),
            _candidate(
                "yahoo",
                "Total Assets",
                None,
                yahoo_value,
                currency="HKD",
                period=period,
                statement_metadata_proven=yahoo_statement_metadata_proven,
            ),
        ),
        errors=("multiple source candidates matched catalog aliases",),
    )
```

- [ ] **Step 2: Run source policy tests and verify failure**

Run:

```bash
uv run pytest tests/test_source_policy.py -v
```

Expected before implementation: the new test may fail if source policy still treats Yahoo primary proof as missing.

- [ ] **Step 3: Keep source policy logic focused on primary candidate proof**

Inspect `_requires_hk_primary_statement_metadata()` in `source_policy.py`. It should remain source-neutral:

```python
def _requires_hk_primary_statement_metadata(
    market: str | None,
    candidate: TurtleMappingCandidate,
    classifications: tuple[ConflictClassification, ...],
) -> bool:
    return (
        market == "HK"
        and "metadata_currency_suspected" in classifications
        and not candidate.statement_metadata_proven
    )
```

If the test fails because `_primary_candidate()` is selecting the wrong source, fix the source policy test helper or catalog policy first. Do not add provider-specific branches unless the selected candidate itself lacks proof.

- [ ] **Step 4: Run focused policy tests**

Run:

```bash
uv run pytest tests/test_source_policy.py -v
```

Expected: all source policy tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/financial_report_llm_extractor/structured_sources/source_policy.py tests/test_source_policy.py
git commit -m "fix: classify hk metadata proof warnings"
```

## Task 4: Expose Metadata Warning And Blocker Fields In Provider Replay

**Files:**
- Modify: `tests/test_provider_baseline_replay.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`

- [ ] **Step 1: Add replay summary assertions for present warnings and blockers**

Extend `test_provider_baseline_replay_reports_policy_selected_and_clean_counts`:

```python
hk_combined = companies["00001"]["review"]["combined"]
assert "present_metadata_warning_fields" in hk_combined
assert "metadata_blocker_fields" in hk_combined
assert set(hk_combined["selected_with_warnings_fields"]) >= set(
    hk_combined["present_metadata_warning_fields"]
)
assert set(hk_combined["fields_requiring_pdf_evidence"]) >= set(
    hk_combined["metadata_blocker_fields"]
)
```

- [ ] **Step 2: Run replay tests and verify failure**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py -v
```

Expected before implementation: `present_metadata_warning_fields` and `metadata_blocker_fields` are missing from review output.

- [ ] **Step 3: Add present warning and blocker lists to `_review_lists()`**

In `provider_baseline_replay.py`, add these lists to `field_lists`:

```python
"present_metadata_warning_fields": sorted(
    field_id
    for field_id, item in export.items.items()
    if item.status == "present"
    and (
        any(
            note in {
                "currency_metadata_required",
                "metadata_currency_suspected",
            }
            for note in item.review_notes
        )
        or any("currency metadata" in warning for warning in item.warnings)
    )
),
"metadata_blocker_fields": sorted(
    field_id
    for field_id, item in export.items.items()
    if item.status != "present"
    and any(
        note in {
            "currency_metadata_required",
            "metadata_currency_suspected",
        }
        for note in item.review_notes
    )
),
```

Add the markdown line near `selected_with_warnings_fields`:

```python
"  - present_metadata_warning_fields: "
f"{_format_field_list(review['present_metadata_warning_fields'])}",
"  - metadata_blocker_fields: "
f"{_format_field_list(review['metadata_blocker_fields'])}",
```

- [ ] **Step 4: Run replay tests**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py -v
```

Expected: replay tests pass and summary includes `present_metadata_warning_fields` and `metadata_blocker_fields`.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py tests/test_provider_baseline_replay.py
git commit -m "feat: expose hk metadata warning fields"
```

## Task 5: Run Phase K Verification

**Files:**
- No source edits unless verification finds a regression.

- [ ] **Step 1: Run the focused Phase K test set**

Run:

```bash
uv run pytest tests/test_akshare_adapter.py tests/test_yahoo_adapter.py tests/test_source_mapping.py tests/test_source_policy.py tests/test_provider_baseline_replay.py -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full test suite if time allows**

Run:

```bash
uv run pytest -v
```

Expected: full suite passes.

- [ ] **Step 3: Run static checks**

Run:

```bash
uv run ruff check .
uv run mypy src tests
```

Expected: both commands pass.

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git status --short
git diff --check
```

Expected: only intended source/test files are modified; `git diff --check` reports no whitespace errors.

- [ ] **Step 5: Final commit**

If Tasks 1 to 4 were not committed individually, make one final commit:

```bash
git add src/financial_report_llm_extractor/structured_sources/akshare_adapter.py src/financial_report_llm_extractor/structured_sources/mapping.py src/financial_report_llm_extractor/structured_sources/source_policy.py src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py tests/test_akshare_adapter.py tests/test_source_mapping.py tests/test_source_policy.py tests/test_provider_baseline_replay.py
git commit -m "fix: prove hk source metadata before clean coverage"
```

## Self-Review

- Spec coverage: The tasks cover HK currency/unit separation, AKShare metadata proof, Yahoo metadata proof, source policy classification, and replay visibility.
- Placeholder scan: The plan contains no unresolved placeholder markers or open implementation slots.
- Type consistency: The plan reuses existing `SourceInventoryRecord` and `SourcePolicyItem`, extends `TurtleMappingCandidate` with minimal proof fields, and keeps provider replay summary additions explicit.
