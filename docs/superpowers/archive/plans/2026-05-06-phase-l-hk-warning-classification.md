# Phase L HK Warning Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic HK warning classification queue to provider baseline replay so HK non-clean fields are split into source-policy, PDF verification, mapping-expansion, and source-unavailable work.

**Architecture:** Create a small classification module inside `structured_sources` that consumes existing source-first export items plus a company/slice-local provider candidate report. Integrate it into provider baseline replay after mapping/reconciliation/policy/export, without adding network calls or expanding the source mapping catalog.

**Tech Stack:** Python 3.11 standard library, frozen dataclasses, existing source-first replay fixtures, pytest.

---

## File Structure

- Create `src/financial_report_llm_extractor/structured_sources/warning_classification.py`: warning classification contracts, category precedence, JSON/Markdown writers.
- Create `tests/test_warning_classification.py`: focused unit tests for category precedence and company/slice-local candidate awareness.
- Modify `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`: build a slice-local candidate report, write warning classification artifacts, and expose classification summary in replay JSON/Markdown.
- Modify `src/financial_report_llm_extractor/cli.py`: add `--taxonomy` to `replay-provider-baseline`, defaulting to `field_catalog/turtle_v015_field_taxonomy.json`.
- Modify `tests/test_cli.py`: assert replay CLI forwards the taxonomy path.
- Modify `scripts/run-provider-baseline-period-replay.sh`: pass the taxonomy path through an environment override.
- Modify `tests/test_provider_baseline_replay.py`: assert `00001` and `01113` category output and artifact paths.
- Modify `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`: record Phase L status after implementation.

## Task 1: Add Warning Classification Contracts

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/warning_classification.py`
- Create: `tests/test_warning_classification.py`

- [ ] **Step 1: Write failing tests for category precedence**

Create `tests/test_warning_classification.py` with:

```python
from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportItem,
    SourceFirstExportResult,
)
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    FieldCandidateReportEntry,
    ProviderCandidateGroup,
    ProviderFieldCandidate,
)
from financial_report_llm_extractor.structured_sources.warning_classification import (
    build_warning_classification,
)


def _item(
    field_id: str,
    *,
    status: str = "missing",
    review_notes: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
    verification_required: bool = False,
    reconciliation_status: str | None = None,
    selected_source: str | None = None,
) -> SourceFirstExportItem:
    return SourceFirstExportItem(
        field_id=field_id,
        status=status,  # type: ignore[arg-type]
        review_notes=review_notes,
        warnings=warnings,
        verification_required=verification_required,
        reconciliation_status=reconciliation_status,  # type: ignore[arg-type]
        selected_source=selected_source,
    )


def _candidate_entry(field_id: str) -> FieldCandidateReportEntry:
    return FieldCandidateReportEntry(
        priority="P0",
        statement_type="balance_sheet",
        source_mode="direct",
        status="has_candidates",
        providers={
            "yahoo": ProviderCandidateGroup(
                candidates=(
                    ProviderFieldCandidate(
                        raw_field_name="Non Current Deferred Taxes Liabilities",
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


def test_warning_classification_uses_mapping_expansion_for_missing_with_candidates() -> None:
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test",
        catalog_version="1",
        items={
            "defer_tax_liab": _item("defer_tax_liab"),
            "bond_payable": _item("bond_payable"),
        },
    )

    result = build_warning_classification(
        export,
        candidate_entries={"defer_tax_liab": _candidate_entry("defer_tax_liab")},
    )

    assert result.fields_by_category["mapping_expansion_required"] == [
        "defer_tax_liab"
    ]
    assert result.fields_by_category["source_unavailable"] == ["bond_payable"]


def test_warning_classification_prioritizes_pdf_verification_over_metadata_notes() -> None:
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test",
        catalog_version="1",
        items={
            "total_assets": _item(
                "total_assets",
                status="conflict",
                review_notes=("metadata_currency_suspected", "statement_metadata_unproven"),
                verification_required=True,
                reconciliation_status="conflict",
            )
        },
    )

    result = build_warning_classification(export, candidate_entries={})

    assert result.fields_by_category["pdf_verification_required"] == ["total_assets"]
    item = result.items["total_assets"]
    assert item.category == "pdf_verification_required"
    assert "reconciliation_conflict" in item.reasons
    assert "statement_metadata_unproven" in item.reasons


def test_warning_classification_marks_metadata_only_issue_source_policy_resolvable() -> None:
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test",
        catalog_version="1",
        items={
            "cash": _item(
                "cash",
                status="conflict",
                review_notes=("currency_as_unit", "statement_metadata_unproven"),
                verification_required=True,
            )
        },
    )

    result = build_warning_classification(export, candidate_entries={})

    assert result.fields_by_category["source_policy_resolvable"] == ["cash"]


def test_warning_classification_uses_verification_required_for_pdf_queue() -> None:
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test",
        catalog_version="1",
        items={
            "revenue": _item(
                "revenue",
                status="present",
                warnings=("single source selected; PDF verification required",),
                verification_required=True,
                selected_source="yahoo",
            )
        },
    )

    result = build_warning_classification(export, candidate_entries={})

    assert result.fields_by_category["pdf_verification_required"] == ["revenue"]
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_warning_classification.py -v
```

Expected: import error for missing `warning_classification` module.

- [ ] **Step 3: Implement classification dataclasses and helpers**

Create `src/financial_report_llm_extractor/structured_sources/warning_classification.py`:

```python
"""Actionable warning classification for source-first replay outputs."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportItem,
    SourceFirstExportResult,
)
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    FieldCandidateReportEntry,
)


WarningCategory = Literal[
    "source_policy_resolvable",
    "pdf_verification_required",
    "mapping_expansion_required",
    "source_unavailable",
]

ALL_WARNING_CATEGORIES: tuple[WarningCategory, ...] = (
    "source_policy_resolvable",
    "pdf_verification_required",
    "mapping_expansion_required",
    "source_unavailable",
)

PDF_REASON_NOTES = {
    "fx_like_ratio",
    "metadata_currency_suspected",
    "semantic_mismatch",
    "normalized_value_conflict",
    "single_source_unverified",
}

SOURCE_POLICY_REASON_NOTES = {
    "currency_metadata_required",
    "currency_as_unit",
    "statement_metadata_unproven",
}


@dataclass(frozen=True)
class WarningClassificationItem:
    field_id: str
    category: WarningCategory
    status: str
    reasons: tuple[str, ...]
    review_notes: tuple[str, ...]
    warnings: tuple[str, ...]
    selected_source: str | None
    candidate_sources: tuple[str, ...]
    verification_required: bool

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        payload["review_notes"] = list(self.review_notes)
        payload["warnings"] = list(self.warnings)
        payload["candidate_sources"] = list(self.candidate_sources)
        return payload


@dataclass(frozen=True)
class WarningClassificationResult:
    items: dict[str, WarningClassificationItem]

    @property
    def counts_by_category(self) -> dict[str, int]:
        counts = Counter(item.category for item in self.items.values())
        return {category: counts[category] for category in ALL_WARNING_CATEGORIES}

    @property
    def fields_by_category(self) -> dict[str, list[str]]:
        return {
            category: sorted(
                field_id
                for field_id, item in self.items.items()
                if item.category == category
            )
            for category in ALL_WARNING_CATEGORIES
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "counts_by_category": self.counts_by_category,
            "fields_by_category": self.fields_by_category,
            "items": {
                field_id: self.items[field_id].to_dict()
                for field_id in sorted(self.items)
            },
        }


def build_warning_classification(
    export: SourceFirstExportResult,
    *,
    candidate_entries: dict[str, FieldCandidateReportEntry],
) -> WarningClassificationResult:
    items = {
        field_id: _classify_item(field_id, item, candidate_entries.get(field_id))
        for field_id, item in export.items.items()
        if not _is_clean_present(item)
    }
    return WarningClassificationResult(items=items)


def write_warning_classification_artifacts(
    result: WarningClassificationResult,
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "warning_classification.json"
    markdown_path = output_dir / "warning_classification.md"
    payload = result.to_dict()
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}
```

- [ ] **Step 4: Implement category precedence**

Add below the writers:

```python
def _classify_item(
    field_id: str,
    item: SourceFirstExportItem,
    candidate_entry: FieldCandidateReportEntry | None,
) -> WarningClassificationItem:
    candidate_sources = _candidate_sources(candidate_entry)
    reasons = _reasons(item=item, candidate_entry=candidate_entry)
    category = _category_for_item(
        item=item,
        candidate_entry=candidate_entry,
        reasons=reasons,
    )
    return WarningClassificationItem(
        field_id=field_id,
        category=category,
        status=item.status,
        reasons=reasons,
        review_notes=item.review_notes,
        warnings=item.warnings,
        selected_source=item.selected_source,
        candidate_sources=candidate_sources,
        verification_required=item.verification_required,
    )


def _category_for_item(
    *,
    item: SourceFirstExportItem,
    candidate_entry: FieldCandidateReportEntry | None,
    reasons: tuple[str, ...],
) -> WarningCategory:
    if item.status == "missing":
        return (
            "mapping_expansion_required"
            if _has_provider_candidates(candidate_entry)
            else "source_unavailable"
        )
    if _requires_pdf_verification(item, reasons):
        return "pdf_verification_required"
    if SOURCE_POLICY_REASON_NOTES.intersection(reasons):
        return "source_policy_resolvable"
    if item.status in {"ambiguous", "blocked"} and _has_provider_candidates(candidate_entry):
        return "mapping_expansion_required"
    return "source_policy_resolvable"


def _requires_pdf_verification(
    item: SourceFirstExportItem,
    reasons: tuple[str, ...],
) -> bool:
    return (
        item.status == "needs_pdf_evidence"
        or item.verification_required
        or item.reconciliation_status == "conflict"
        or "reconciliation_conflict" in reasons
        or bool(PDF_REASON_NOTES.intersection(reasons))
    )


def _reasons(
    *,
    item: SourceFirstExportItem,
    candidate_entry: FieldCandidateReportEntry | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    reasons.extend(item.review_notes)
    if item.reconciliation_status == "conflict":
        reasons.append("reconciliation_conflict")
    if item.verification_required:
        reasons.append("verification_required")
    if item.status == "missing":
        reasons.append(
            "provider_candidates_present"
            if _has_provider_candidates(candidate_entry)
            else "provider_candidates_absent"
        )
    if item.warnings:
        reasons.extend(f"warning:{warning}" for warning in item.warnings)
    return tuple(dict.fromkeys(reasons))


def _candidate_sources(
    candidate_entry: FieldCandidateReportEntry | None,
) -> tuple[str, ...]:
    if candidate_entry is None:
        return ()
    return tuple(sorted(candidate_entry.providers))


def _has_provider_candidates(candidate_entry: FieldCandidateReportEntry | None) -> bool:
    return bool(candidate_entry is not None and candidate_entry.providers)


def _is_clean_present(item: SourceFirstExportItem) -> bool:
    return (
        item.status == "present"
        and not item.warnings
        and not item.review_notes
        and not item.verification_required
    )


def _markdown(payload: dict[str, object]) -> str:
    fields_by_category = payload["fields_by_category"]
    counts_by_category = payload["counts_by_category"]
    assert isinstance(fields_by_category, dict)
    assert isinstance(counts_by_category, dict)
    lines = ["# Warning Classification", ""]
    for category in ALL_WARNING_CATEGORIES:
        fields = fields_by_category.get(category, [])
        field_text = ", ".join(fields) if isinstance(fields, list) and fields else "none"
        lines.append(f"- {category}: {counts_by_category.get(category, 0)} ({field_text})")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 5: Run focused classification tests**

Run:

```bash
uv run pytest tests/test_warning_classification.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/financial_report_llm_extractor/structured_sources/warning_classification.py tests/test_warning_classification.py
git commit -m "feat: classify source warning queues"
```

## Task 2: Integrate Classification Into Provider Replay

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`
- Modify: `tests/test_provider_baseline_replay.py`

- [ ] **Step 1: Write failing replay assertions for HK categories**

Extend `test_provider_baseline_replay_reports_policy_selected_and_clean_counts`:

```python
expected_pdf_fields = {
    "gross_profit",
    "net_profit",
    "revenue",
    "total_assets",
    "total_cur_assets",
    "total_cur_liab",
    "total_liabilities",
}
for company_id in ("00001", "01113"):
    warning_classification = companies[company_id]["review"]["combined"][
        "warning_classification"
    ]
    assert set(
        warning_classification["fields_by_category"]["pdf_verification_required"]
    ) >= expected_pdf_fields
    assert warning_classification["fields_by_category"][
        "mapping_expansion_required"
    ] == ["defer_tax_liab"]
    assert set(
        warning_classification["fields_by_category"]["source_unavailable"]
    ) >= {"bond_payable", "cip", "invest_income"}
    assert "warning_classification" in companies[company_id]["artifact_paths"][
        "combined"
    ]
```

- [ ] **Step 2: Run replay test and verify failure**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py::test_provider_baseline_replay_reports_policy_selected_and_clean_counts -v
```

Expected: `KeyError: 'warning_classification'`.

- [ ] **Step 3: Add taxonomy and candidate discovery imports**

In `provider_baseline_replay.py`, add:

```python
from financial_report_llm_extractor.field_metadata import (
    FieldTaxonomyCatalog,
    load_field_taxonomy,
)
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    discover_provider_field_candidates,
)
from financial_report_llm_extractor.structured_sources.warning_classification import (
    build_warning_classification,
    write_warning_classification_artifacts,
)
```

- [ ] **Step 4: Thread taxonomy into replay**

Update `write_provider_baseline_period_replay()` signature:

```python
def write_provider_baseline_period_replay(
    *,
    inventory_path: Path,
    inventory_summary_path: Path,
    catalog_path: Path,
    output_dir: Path,
    taxonomy_path: Path = Path("field_catalog/turtle_v015_field_taxonomy.json"),
    output_summary_path: Path | None = None,
    company_ids: tuple[str, ...] | None = None,
) -> ProviderBaselineReplayResult:
```

After loading the catalog:

```python
taxonomy = load_field_taxonomy(taxonomy_path)
```

Pass `taxonomy=taxonomy` into all three `_write_slice()` calls.

- [ ] **Step 5: Build slice-local candidate report and classification**

Update `_write_slice()` signature:

```python
def _write_slice(
    output_dir: Path,
    *,
    catalog: Any,
    taxonomy: FieldTaxonomyCatalog,
    records: tuple[SourceInventoryRecord, ...],
    company_id: str,
    market: str,
) -> dict[str, Any]:
```

After `export = build_source_first_export(...)`, add:

```python
candidate_report = discover_provider_field_candidates(
    taxonomy_entries=taxonomy.fields,
    mapping_entries=catalog.entries,
    records=records,
    priorities=("P0", "P1"),
    fixture=f"provider_baseline_period_replay:{company_id}:{market}",
    taxonomy_catalog=taxonomy.catalog_id,
    mapping_catalog=catalog.catalog_id,
)
warning_classification = build_warning_classification(
    export,
    candidate_entries=candidate_report.fields,
)
```

Write artifacts after existing artifacts:

```python
warning_artifacts = write_warning_classification_artifacts(
    warning_classification,
    output_dir,
)
```

Return classification and artifact paths:

```python
return {
    "coverage": _export_coverage(export),
    "review": {
        **_review_lists(export),
        "warning_classification": warning_classification.to_dict(),
    },
    "artifact_paths": {
        "source_inventory": str(output_dir / "source_inventory.jsonl"),
        "turtle_mapping": str(output_dir / "turtle_mapping.json"),
        "source_coverage_summary": str(output_dir / "source_coverage_summary.json"),
        "reconciliation_report": str(output_dir / "reconciliation_report.json"),
        "source_policy_report": str(output_dir / "source_policy_report.json"),
        "extraction_result": str(output_dir / "extraction_result.json"),
        "review_summary": str(output_dir / "review_summary.json"),
        "warning_classification": str(warning_artifacts["json"]),
        "warning_classification_markdown": str(warning_artifacts["markdown"]),
    },
}
```

- [ ] **Step 6: Add Markdown summary lines**

In `_summary_markdown()`, after `fields_requiring_pdf_evidence`, add:

```python
classification = review["warning_classification"]
classification_fields = classification["fields_by_category"]
lines.extend(
    [
        "  - warning_classification:",
        "    - source_policy_resolvable: "
        f"{_format_field_list(classification_fields['source_policy_resolvable'])}",
        "    - pdf_verification_required: "
        f"{_format_field_list(classification_fields['pdf_verification_required'])}",
        "    - mapping_expansion_required: "
        f"{_format_field_list(classification_fields['mapping_expansion_required'])}",
        "    - source_unavailable: "
        f"{_format_field_list(classification_fields['source_unavailable'])}",
    ]
)
```

- [ ] **Step 7: Run replay tests**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py -v
```

Expected: all replay tests pass.

- [ ] **Step 8: Commit Task 2**

```bash
git add src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py tests/test_provider_baseline_replay.py
git commit -m "feat: add hk warning classification replay"
```

## Task 3: Expose Taxonomy In CLI And Script

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `scripts/run-provider-baseline-period-replay.sh`

- [ ] **Step 1: Write failing CLI test update**

In `test_replay_provider_baseline_command_calls_replay_layer`, add:

```python
taxonomy_path = tmp_path / "taxonomy.json"
calls: list[tuple[Path, Path, Path, Path, Path]] = []
```

Update fake signature:

```python
def fake_write_provider_baseline_period_replay(
    *,
    inventory_path: Path,
    inventory_summary_path: Path,
    catalog_path: Path,
    output_dir: Path,
    taxonomy_path: Path,
    output_summary_path: Path | None = None,
    company_ids: tuple[str, ...] | None = None,
) -> FakeProviderBaselineReplayResult:
    assert output_summary_path is None
    assert company_ids is None
    calls.append(
        (inventory_path, inventory_summary_path, catalog_path, output_dir, taxonomy_path)
    )
```

Add CLI args:

```python
"--taxonomy",
str(taxonomy_path),
```

Assert:

```python
assert calls == [
    (inventory_path, inventory_summary_path, catalog_path, output_dir, taxonomy_path)
]
```

- [ ] **Step 2: Run CLI test and verify failure**

Run:

```bash
uv run pytest tests/test_cli.py::test_replay_provider_baseline_command_calls_replay_layer -v
```

Expected: parser does not accept `--taxonomy`.

- [ ] **Step 3: Add CLI argument and forward it**

In `build_parser()`:

```python
baseline_replay_parser.add_argument(
    "--taxonomy",
    default=Path("field_catalog/turtle_v015_field_taxonomy.json"),
    type=Path,
)
```

In `main()` replay call:

```python
taxonomy_path=args.taxonomy,
```

- [ ] **Step 4: Update script**

In `scripts/run-provider-baseline-period-replay.sh`, add:

```bash
TAXONOMY="${TAXONOMY:-field_catalog/turtle_v015_field_taxonomy.json}"
```

Pass:

```bash
  --taxonomy "${TAXONOMY}" \
```

- [ ] **Step 5: Run focused CLI and script tests**

Run:

```bash
uv run pytest tests/test_cli.py::test_replay_provider_baseline_command_calls_replay_layer tests/test_provider_baseline_replay.py::test_provider_baseline_period_replay_script_is_local_fixture_entrypoint -v
```

Expected: both tests pass.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/financial_report_llm_extractor/cli.py tests/test_cli.py scripts/run-provider-baseline-period-replay.sh
git commit -m "feat: pass taxonomy to provider replay"
```

## Task 4: Validate Real Fixture Classification Shape

**Files:**
- Modify: `tests/test_provider_baseline_replay.py`

- [ ] **Step 1: Add artifact-level assertions**

In `test_provider_baseline_period_replay_uses_checked_in_fixture`, after building `companies`, add:

```python
for company_id in ("00001", "01113"):
    combined = companies[company_id]
    classification = combined["review"]["combined"]["warning_classification"]
    assert classification["counts_by_category"]["pdf_verification_required"] >= 7
    assert "defer_tax_liab" in classification["fields_by_category"][
        "mapping_expansion_required"
    ]
    assert set(classification["fields_by_category"]["source_unavailable"]) >= {
        "bond_payable",
        "cip",
        "invest_income",
    }
    classification_path = Path(
        combined["artifact_paths"]["combined"]["warning_classification"]
    )
    assert classification_path.exists()
    payload = json.loads(classification_path.read_text(encoding="utf-8"))
    assert payload["items"]["revenue"]["category"] == "pdf_verification_required"
```

- [ ] **Step 2: Run fixture replay test**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py::test_provider_baseline_period_replay_uses_checked_in_fixture -v
```

Expected: test passes.

- [ ] **Step 3: Run provider replay script once**

Run:

```bash
scripts/run-provider-baseline-period-replay.sh
```

Expected: command exits 0 and writes `tmp/runs/provider_baseline_period_replay/provider_baseline_period_replay_summary.json`.

- [ ] **Step 4: Inspect generated summary**

Run:

```bash
.venv/bin/python -c "import json; from pathlib import Path; p=Path('tmp/runs/provider_baseline_period_replay/provider_baseline_period_replay_summary.json'); data=json.loads(p.read_text()); print({c['company_id']: c['review']['combined']['warning_classification']['fields_by_category'] for c in data['companies'] if c['company_id'] in {'00001','01113'}})"
```

Expected: `00001` and `01113` both show `pdf_verification_required`, `mapping_expansion_required`, and `source_unavailable` field lists.

- [ ] **Step 5: Commit Task 4**

Generated `tmp/runs/...` artifacts are verification outputs only. Do not commit them.

```bash
git add tests/test_provider_baseline_replay.py
git commit -m "test: verify hk warning classification fixtures"
```

## Task 5: Update Roadmap And Run Verification

**Files:**
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`

- [ ] **Step 1: Update Phase L roadmap status**

Under Phase L, add an implementation status note:

```markdown
Implementation status:

- Warning classification artifacts are written per provider replay slice.
- HK `00001` and `01113` combined slices expose:
  - PDF verification queue
  - mapping expansion queue
  - source unavailable queue
- The PDF fallback input is now bounded to `pdf_verification_required`.
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
uv run pytest tests/test_warning_classification.py tests/test_provider_baseline_replay.py tests/test_cli.py -v
```

Expected: all focused tests pass.

- [ ] **Step 3: Run full verification**

Run:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
git diff --check
```

Expected: all commands pass.

- [ ] **Step 4: Commit Task 5**

```bash
git add docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md
git commit -m "docs: record hk warning classification status"
```

## Self-Review

- Spec coverage: Tasks cover the classification contract, company/slice-local candidate input, replay output, CLI/script access, fixture validation, and roadmap update.
- Placeholder scan: The plan contains no TBD/TODO markers or open implementation slots.
- Type consistency: Category names match the spec exactly: `source_policy_resolvable`, `pdf_verification_required`, `mapping_expansion_required`, `source_unavailable`.
- Scope check: The plan does not expand source mapping to 33 fields, refresh provider fixtures, or run PDF/LLM fallback.
