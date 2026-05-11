# HK 15-Field Closure Before P0/P1 Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close or explicitly classify the remaining HK 15-field gaps before expanding the source mapping denominator to all P0/P1 fields.

**Architecture:** Keep the existing source-first replay pipeline as the integration point. Add small review metadata to the HK Yahoo trust policy, add a focused HK closure report beside existing replay artifacts, and tighten replay tests around the current 15-field denominator. Do not change ingestion, chunking, LLM transport, or final PDF `Evidence` contracts.

**Tech Stack:** Python 3.11 standard library, frozen dataclasses, JSON artifacts, existing pytest suite.

---

## File Structure

- Modify `field_catalog/hk_yahoo_trust_policy.json`
  - Add explicit review reasons to `net_profit` and `gross_profit` unverified rules.
- Modify `src/financial_report_llm_extractor/structured_sources/hk_yahoo_trust_policy.py`
  - Parse, validate, and serialize optional rule-level review metadata.
- Create `src/financial_report_llm_extractor/structured_sources/hk_15_field_closure.py`
  - Build a compact HK 15-field closure report from export, warning classification, provider candidates, and trust policy.
- Modify `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`
  - Write `hk_15_field_closure_report.json` and `.md` for HK slices.
  - Add artifact paths and review summary lists.
- Modify `tests/test_hk_yahoo_trust_policy.py`
  - Cover the new unverified-rule metadata.
- Create `tests/test_hk_15_field_closure.py`
  - Unit-test closure report categorization independent of full replay.
- Modify `tests/test_provider_baseline_replay.py`
  - Tighten checked-in HK replay expectations around the 9 clean fields and remaining six fields.

## Task 1: Lock the HK 15-Field Replay Baseline

**Files:**

- Modify: `tests/test_provider_baseline_replay.py`

- [ ] **Step 1: Write the failing replay baseline test**

Add this test near the existing checked-in replay assertions:

```python
def test_checked_in_hk_replay_reports_exact_15_field_closure_buckets(
    checked_in_provider_baseline_replay: CheckedInReplay,
) -> None:
    _, payload = checked_in_provider_baseline_replay
    companies = _companies_by_id(payload)
    expected_clean = {
        "cash",
        "financing_cash_flow",
        "investing_cash_flow",
        "operating_cash_flow",
        "revenue",
        "total_assets",
        "total_cur_assets",
        "total_cur_liab",
        "total_liabilities",
    }

    for company_id in HK_COMPANY_IDS:
        combined = companies[company_id]["coverage"]["combined"]
        review = companies[company_id]["review"]["combined"]
        warning_fields = review["warning_classification"]["fields_by_category"]

        assert set(combined["clean_present_fields"]) == expected_clean
        assert combined["clean_present_count"] == 9
        assert combined["total_fields"] == 15
        assert set(review["yahoo_definition_unverified_fields"]) == {
            "gross_profit",
            "net_profit",
        }
        assert warning_fields["mapping_expansion_required"] == [
            "defer_tax_liab"
        ]
        assert set(warning_fields["source_unavailable"]) == {
            "bond_payable",
            "cip",
            "invest_income",
        }
```

- [ ] **Step 2: Run the focused test and capture the current behavior**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py::test_checked_in_hk_replay_reports_exact_15_field_closure_buckets -v
```

Expected now: it may fail if current replay summaries do not expose exact clean-present fields or if warning buckets are only partially asserted.

- [ ] **Step 3: Adjust only the test if current artifact shape already supports it**

If the test fails because the existing replay already has the data under a slightly different key, change the test to use the existing key. Do not change production code in this task unless the key is missing entirely.

- [ ] **Step 4: Run the provider replay tests**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py -v
```

Expected: all tests pass or only the new closure-report expectations from later tasks are absent.

- [ ] **Step 5: Commit**

```bash
git add tests/test_provider_baseline_replay.py
git commit -m "test: lock hk 15-field replay baseline"
```

## Task 2: Add Review Reasons To HK Yahoo Trust Rules

**Files:**

- Modify: `field_catalog/hk_yahoo_trust_policy.json`
- Modify: `src/financial_report_llm_extractor/structured_sources/hk_yahoo_trust_policy.py`
- Modify: `tests/test_hk_yahoo_trust_policy.py`

- [ ] **Step 1: Write failing trust-policy metadata tests**

Append assertions to `test_hk_yahoo_trust_policy_exposes_verified_and_unverified_classifications`:

```python
    gross_evidence = policy.build_policy_evidence("gross_profit")
    net_evidence = policy.build_policy_evidence("net_profit")

    assert gross_evidence["definition_status_reason"] == (
        "formal annual-report gross-profit row semantics are not yet proven"
    )
    assert gross_evidence["required_proof"] == (
        "formal PDF row or deterministic derivation matching Yahoo Gross Profit"
    )
    assert net_evidence["definition_status_reason"] == (
        "Yahoo net-income semantics are not yet tied to the exact Turtle net_profit row"
    )
    assert net_evidence["required_proof"] == (
        "PDF row semantics and value match for profit attributable to owners/shareholders"
    )
```

Add a validation test:

```python
def test_hk_yahoo_trust_policy_requires_reason_for_definition_unverified_rule(
    tmp_path: Path,
) -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    for rule in payload["rules"]:
        if rule["field_id"] == "net_profit":
            rule.pop("definition_status_reason", None)
    policy_path = tmp_path / "bad_policy.json"
    policy_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="definition_status_reason is required"):
        load_hk_yahoo_trust_policy(policy_path)
```

- [ ] **Step 2: Run the tests to verify failure**

Run:

```bash
uv run pytest tests/test_hk_yahoo_trust_policy.py -v
```

Expected: fails because `HkYahooTrustRule` does not parse or emit the new metadata.

- [ ] **Step 3: Add JSON metadata to unverified rules**

Update the `gross_profit` rule in `field_catalog/hk_yahoo_trust_policy.json`:

```json
"definition_status_reason": "formal annual-report gross-profit row semantics are not yet proven",
"required_proof": "formal PDF row or deterministic derivation matching Yahoo Gross Profit"
```

Update the `net_profit` rule:

```json
"definition_status_reason": "Yahoo net-income semantics are not yet tied to the exact Turtle net_profit row",
"required_proof": "PDF row semantics and value match for profit attributable to owners/shareholders"
```

- [ ] **Step 4: Extend the dataclass and parser**

In `HkYahooTrustRule`, add fields after `allowed_yahoo_raw_fields`:

```python
    definition_status_reason: str | None = None
    required_proof: str | None = None
```

In `HkYahooTrustRule.validate()`, add:

```python
        if self.classification == "yahoo_definition_unverified":
            if not self.definition_status_reason:
                raise ValueError("definition_status_reason is required")
            if not self.required_proof:
                raise ValueError("required_proof is required")
```

In `HkYahooTrustRule.build_policy_evidence()`, add the two keys:

```python
            "definition_status_reason": self.definition_status_reason,
            "required_proof": self.required_proof,
```

In `_parse_rule()`, pass:

```python
        definition_status_reason=_optional_str(rule, "definition_status_reason"),
        required_proof=_optional_str(rule, "required_proof"),
```

Add helper:

```python
def _optional_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return str(value)
```

- [ ] **Step 5: Run trust-policy tests**

Run:

```bash
uv run pytest tests/test_hk_yahoo_trust_policy.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add field_catalog/hk_yahoo_trust_policy.json src/financial_report_llm_extractor/structured_sources/hk_yahoo_trust_policy.py tests/test_hk_yahoo_trust_policy.py
git commit -m "feat: explain unverified hk yahoo policy rules"
```

## Task 3: Add HK 15-Field Closure Report Builder

**Files:**

- Create: `src/financial_report_llm_extractor/structured_sources/hk_15_field_closure.py`
- Create: `tests/test_hk_15_field_closure.py`

- [ ] **Step 1: Write unit tests for closure categorization**

Create `tests/test_hk_15_field_closure.py`:

```python
from decimal import Decimal

from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportItem,
    SourceFirstExportResult,
)
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    FieldCandidateReportEntry,
    ProviderCandidateGroup,
    ProviderFieldCandidate,
)
from financial_report_llm_extractor.structured_sources.hk_yahoo_trust_policy import (
    HkYahooTrustPolicy,
    HkYahooTrustRule,
)
from financial_report_llm_extractor.structured_sources.hk_15_field_closure import (
    HK_15_FIELD_IDS,
    build_hk_15_field_closure_report,
)
from financial_report_llm_extractor.structured_sources.warning_classification import (
    build_warning_classification,
)


def _item(
    field_id: str,
    *,
    status: str = "missing",
    selected_source: str | None = None,
    verification_required: bool = False,
    warnings: tuple[str, ...] = (),
) -> SourceFirstExportItem:
    return SourceFirstExportItem(
        field_id=field_id,
        status=status,  # type: ignore[arg-type]
        selected_source=selected_source,
        verification_required=verification_required,
        warnings=warnings,
    )


def _candidate_entry() -> FieldCandidateReportEntry:
    return FieldCandidateReportEntry(
        priority="P1",
        statement_type="balance_sheet",
        source_mode="direct",
        status="has_candidates",
        providers={
            "yahoo": ProviderCandidateGroup(
                candidates=(
                    ProviderFieldCandidate(
                        raw_field_name="Deferred Tax Liabilities",
                        raw_field_code=None,
                        score=65,
                        strength="medium",
                        signals=("keyword_overlap", "statement_match"),
                        target_count=1,
                        period_count=1,
                        record_count=1,
                    ),
                )
            )
        },
    )


def _policy() -> HkYahooTrustPolicy:
    return HkYahooTrustPolicy(
        version=1,
        market="HK",
        provider="yahoo",
        rules=(
            HkYahooTrustRule(
                policy_id="hk_yahoo_raw_hkd_pdf_verified:revenue",
                field_id="revenue",
                classification="yahoo_pdf_verified",
                trusted_currency="HKD",
                trusted_unit="raw",
                trusted_unit_multiplier=Decimal("1"),
                allowed_yahoo_raw_fields=("Total Revenue",),
            ),
            HkYahooTrustRule(
                policy_id="hk_yahoo_raw_hkd_definition_unverified:net_profit",
                field_id="net_profit",
                classification="yahoo_definition_unverified",
                trusted_currency="HKD",
                trusted_unit="raw",
                trusted_unit_multiplier=Decimal("1"),
                allowed_yahoo_raw_fields=("Net Income",),
                definition_status_reason="Yahoo net-income semantics are not yet tied to Turtle net_profit",
                required_proof="PDF row semantics and value match",
            ),
        ),
    )


def test_hk_15_field_closure_report_classifies_remaining_gap_types() -> None:
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="catalog",
        catalog_version="1",
        items={
            field_id: _item(field_id, status="present")
            for field_id in HK_15_FIELD_IDS
        },
    )
    export.items["net_profit"] = _item(
        "net_profit",
        status="present",
        selected_source="yahoo",
        verification_required=True,
    )
    export.items["defer_tax_liab"] = _item("defer_tax_liab")
    export.items["bond_payable"] = _item("bond_payable")
    warning = build_warning_classification(
        export,
        candidate_entries={"defer_tax_liab": _candidate_entry()},
        market="HK",
        hk_yahoo_trust_policy=_policy(),
    )

    report = build_hk_15_field_closure_report(
        export=export,
        warning_classification=warning,
        candidate_entries={"defer_tax_liab": _candidate_entry()},
        policy=_policy(),
        company_id="00001",
        market="HK",
    )

    assert report.company_id == "00001"
    assert report.total_fields == 15
    assert report.items["revenue"].category == "clean_present"
    assert report.items["net_profit"].category == "yahoo_definition_unverified"
    assert report.items["net_profit"].reason == (
        "Yahoo net-income semantics are not yet tied to Turtle net_profit"
    )
    assert report.items["defer_tax_liab"].category == "mapping_expansion_required"
    assert report.items["defer_tax_liab"].candidate_sources == ("yahoo",)
    assert report.items["bond_payable"].category == "source_unavailable"
```

- [ ] **Step 2: Run the new test to verify failure**

Run:

```bash
uv run pytest tests/test_hk_15_field_closure.py -v
```

Expected: fails because `hk_15_field_closure.py` does not exist.

- [ ] **Step 3: Implement the closure report module**

Create `src/financial_report_llm_extractor/structured_sources/hk_15_field_closure.py`:

```python
"""HK 15-field closure review artifact."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportResult,
)
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    FieldCandidateReportEntry,
)
from financial_report_llm_extractor.structured_sources.hk_yahoo_trust_policy import (
    HkYahooTrustPolicy,
)
from financial_report_llm_extractor.structured_sources.warning_classification import (
    WarningClassificationResult,
)

HK_15_FIELD_IDS: tuple[str, ...] = (
    "revenue",
    "net_profit",
    "total_assets",
    "total_liabilities",
    "cash",
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
    "bond_payable",
    "cip",
    "invest_income",
    "gross_profit",
    "total_cur_assets",
    "total_cur_liab",
    "defer_tax_liab",
)

ClosureCategory = Literal[
    "clean_present",
    "selected_with_warnings",
    "yahoo_pdf_verified",
    "yahoo_definition_unverified",
    "pdf_required",
    "mapping_expansion_required",
    "source_unavailable",
]

ALL_CLOSURE_CATEGORIES: tuple[ClosureCategory, ...] = (
    "clean_present",
    "selected_with_warnings",
    "yahoo_pdf_verified",
    "yahoo_definition_unverified",
    "pdf_required",
    "mapping_expansion_required",
    "source_unavailable",
)


@dataclass(frozen=True)
class Hk15FieldClosureItem:
    field_id: str
    category: ClosureCategory
    status: str
    selected_source: str | None
    verification_required: bool
    reason: str
    candidate_sources: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["candidate_sources"] = list(self.candidate_sources)
        return payload


@dataclass(frozen=True)
class Hk15FieldClosureReport:
    company_id: str
    market: str
    total_fields: int
    counts_by_category: dict[str, int]
    fields_by_category: dict[str, list[str]]
    items: dict[str, Hk15FieldClosureItem]

    def to_dict(self) -> dict[str, object]:
        return {
            "report_id": "hk_15_field_closure_report",
            "company_id": self.company_id,
            "market": self.market,
            "total_fields": self.total_fields,
            "counts_by_category": self.counts_by_category,
            "fields_by_category": self.fields_by_category,
            "items": {
                field_id: self.items[field_id].to_dict()
                for field_id in sorted(self.items)
            },
        }


def build_hk_15_field_closure_report(
    *,
    export: SourceFirstExportResult,
    warning_classification: WarningClassificationResult,
    candidate_entries: dict[str, FieldCandidateReportEntry],
    policy: HkYahooTrustPolicy | None,
    company_id: str,
    market: str,
) -> Hk15FieldClosureReport:
    items = {
        field_id: _item_for_field(
            field_id,
            export=export,
            warning_classification=warning_classification,
            candidate_entries=candidate_entries,
            policy=policy,
        )
        for field_id in HK_15_FIELD_IDS
    }
    counts = Counter(item.category for item in items.values())
    return Hk15FieldClosureReport(
        company_id=company_id,
        market=market,
        total_fields=len(HK_15_FIELD_IDS),
        counts_by_category={
            category: counts[category] for category in ALL_CLOSURE_CATEGORIES
        },
        fields_by_category={
            category: sorted(
                field_id
                for field_id, item in items.items()
                if item.category == category
            )
            for category in ALL_CLOSURE_CATEGORIES
        },
        items=items,
    )


def write_hk_15_field_closure_artifacts(
    report: Hk15FieldClosureReport,
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "hk_15_field_closure_report.json"
    markdown_path = output_dir / "hk_15_field_closure_report.md"
    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def _item_for_field(
    field_id: str,
    *,
    export: SourceFirstExportResult,
    warning_classification: WarningClassificationResult,
    candidate_entries: dict[str, FieldCandidateReportEntry],
    policy: HkYahooTrustPolicy | None,
) -> Hk15FieldClosureItem:
    export_item = export.items[field_id]
    warning_item = warning_classification.items.get(field_id)
    rule = policy.rule_for_field(field_id) if policy is not None else None
    candidate_sources = _candidate_sources(candidate_entries.get(field_id))
    category: ClosureCategory
    reason: str
    if warning_item is not None:
        category = warning_item.category  # type: ignore[assignment]
        reason = "; ".join(warning_item.reasons) or warning_item.category
    elif export_item.status == "present" and not export_item.verification_required and not export_item.warnings:
        category = "clean_present"
        reason = "present without warnings or PDF verification requirement"
    else:
        category = "selected_with_warnings"
        reason = "selected but still has warnings or verification requirement"
    if rule is not None and rule.classification == "yahoo_definition_unverified":
        category = "yahoo_definition_unverified"
        reason = rule.definition_status_reason or "Yahoo field definition is unverified"
    return Hk15FieldClosureItem(
        field_id=field_id,
        category=category,
        status=export_item.status,
        selected_source=export_item.selected_source,
        verification_required=export_item.verification_required,
        reason=reason,
        candidate_sources=candidate_sources,
    )


def _candidate_sources(entry: FieldCandidateReportEntry | None) -> tuple[str, ...]:
    if entry is None:
        return ()
    return tuple(sorted(entry.providers))


def _markdown(report: Hk15FieldClosureReport) -> str:
    lines = [
        "# HK 15-Field Closure Report",
        "",
        f"- company_id: {report.company_id}",
        f"- market: {report.market}",
        f"- total_fields: {report.total_fields}",
        "",
    ]
    for category, fields in report.fields_by_category.items():
        field_list = ", ".join(fields) if fields else "none"
        lines.append(f"- {category}: {field_list}")
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Run the closure module tests**

Run:

```bash
uv run pytest tests/test_hk_15_field_closure.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/hk_15_field_closure.py tests/test_hk_15_field_closure.py
git commit -m "feat: add hk 15-field closure report"
```

## Task 4: Wire Closure Report Into Provider Replay

**Files:**

- Modify: `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`
- Modify: `tests/test_provider_baseline_replay.py`

- [ ] **Step 1: Write failing provider replay artifact tests**

Add to `_assert_hk_warning_classification()` after the existing artifact checks:

```python
    assert "hk_15_field_closure_report" in company["artifact_paths"]["combined"]
    closure_path = Path(company["artifact_paths"]["combined"]["hk_15_field_closure_report"])
    assert closure_path.exists()
    if assert_artifact_payload:
        closure_payload = json.loads(closure_path.read_text(encoding="utf-8"))
        assert closure_payload["total_fields"] == 15
        assert set(closure_payload["fields_by_category"]["clean_present"]) == {
            "cash",
            "financing_cash_flow",
            "investing_cash_flow",
            "operating_cash_flow",
            "revenue",
            "total_assets",
            "total_cur_assets",
            "total_cur_liab",
            "total_liabilities",
        }
        assert set(
            closure_payload["fields_by_category"]["yahoo_definition_unverified"]
        ) == {"gross_profit", "net_profit"}
        assert closure_payload["items"]["net_profit"]["reason"]
```

- [ ] **Step 2: Run the failing provider replay test**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py -v
```

Expected: fails because replay does not yet write `hk_15_field_closure_report`.

- [ ] **Step 3: Import and call the closure report writer**

In `provider_baseline_replay.py`, add imports:

```python
from financial_report_llm_extractor.structured_sources.hk_15_field_closure import (
    build_hk_15_field_closure_report,
    write_hk_15_field_closure_artifacts,
)
```

After warning classification is built in `_write_slice()`, add:

```python
    hk_15_field_closure_artifacts: dict[str, Path] = {}
    if market.upper() == "HK":
        closure_report = build_hk_15_field_closure_report(
            export=export,
            warning_classification=warning_classification,
            candidate_entries=candidate_report.fields,
            policy=slice_hk_yahoo_trust_policy,
            company_id=company_id,
            market=market,
        )
        hk_15_field_closure_artifacts = write_hk_15_field_closure_artifacts(
            closure_report,
            output_dir,
        )
```

Add artifact paths:

```python
    if hk_15_field_closure_artifacts:
        artifact_paths["hk_15_field_closure_report"] = str(
            hk_15_field_closure_artifacts["json"]
        )
        artifact_paths["hk_15_field_closure_markdown"] = str(
            hk_15_field_closure_artifacts["markdown"]
        )
```

- [ ] **Step 4: Run provider replay tests**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py tests/test_provider_baseline_replay.py
git commit -m "feat: write hk 15-field closure replay artifact"
```

## Task 5: Verify Defer Tax Liability Mapping-Expansion Outcome

**Files:**

- Modify: `tests/test_source_mapping_expansion.py`

- [ ] **Step 1: Add a focused assertion for `defer_tax_liab`**

Extend `test_write_source_mapping_expansion_review_uses_real_candidate_report`:

```python
    all_decisions = {
        (item["field_id"], item["source"]): item
        for section in ("promoted", "deferred", "blocked")
        for item in payload[section]
    }
    defer_tax_decisions = [
        item
        for section in ("promoted", "deferred", "blocked")
        for item in payload[section]
        if item["field_id"] == "defer_tax_liab"
    ]

    assert defer_tax_decisions
    assert ("defer_tax_liab", "akshare") in all_decisions or (
        "defer_tax_liab",
        "yahoo",
    ) in all_decisions
    assert not any(item["action"] == "promote" for item in defer_tax_decisions)
```

This locks the current fixture-backed decision: `defer_tax_liab` has a mapping-expansion path, but this phase must not silently promote an alias without deterministic evidence.

- [ ] **Step 2: Run the mapping-expansion test**

Run:

```bash
uv run pytest tests/test_source_mapping_expansion.py::test_write_source_mapping_expansion_review_uses_real_candidate_report -v
```

Expected: pass if the existing captured baseline already produces a non-promoted `defer_tax_liab` decision; fail if the review code does not expose a decision for the field.

- [ ] **Step 3: If no decision is exposed, adjust review output to list mapped missing fields with provider candidates**

In `source_mapping_expansion.py`, update `_decisions_from_candidate_report()` so it still records a deferred decision when a field has provider candidates but the top candidate is not deterministic. Use the existing `decide_candidate_promotion()` function; do not add new action types.

- [ ] **Step 4: Run focused mapping tests**

Run:

```bash
uv run pytest tests/test_source_mapping_expansion.py tests/test_field_candidate_discovery.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_source_mapping_expansion.py src/financial_report_llm_extractor/structured_sources/source_mapping_expansion.py
git commit -m "test: lock defer tax liability mapping review"
```

## Task 6: Final Verification And Roadmap Note

**Files:**

- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`

- [ ] **Step 1: Add a short roadmap update after Phase M**

Under the Phase M implementation result, add:

```markdown
Follow-up before Phase N:

- HK 15-field closure runs before full 33-field expansion.
- The closure artifact reports `net_profit`, `gross_profit`, `defer_tax_liab`,
  `bond_payable`, `cip`, and `invest_income` in explicit review buckets.
- Phase N should start only after replay no longer confuses unverified,
  mapping-blocked, and source-unavailable fields.
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
uv run pytest tests/test_hk_yahoo_trust_policy.py tests/test_hk_15_field_closure.py tests/test_warning_classification.py tests/test_provider_baseline_replay.py tests/test_source_mapping_expansion.py tests/test_field_candidate_discovery.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Run static checks**

Run:

```bash
uv run ruff check .
uv run mypy src tests
```

Expected: both pass.

- [ ] **Step 4: Run full tests**

Run:

```bash
uv run pytest -v
```

Expected: pass, or reproduce only the known pre-existing `akshare_cn_600519_balance_sheet` fixture hash mismatch from Phase M.

- [ ] **Step 5: Commit final docs**

```bash
git add docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md
git commit -m "docs: record hk 15-field closure follow-up"
```

## Self-Review

- Spec coverage: tasks cover the 9 clean fields, `net_profit`, `gross_profit`, `defer_tax_liab`, `bond_payable`, `cip`, `invest_income`, replay artifacts, and validation.
- Placeholder scan: no unresolved placeholders are intentionally left in the plan.
- Type consistency: new report types use existing `SourceFirstExportResult`, `WarningClassificationResult`, `FieldCandidateReportEntry`, and `HkYahooTrustPolicy` names from current code.
