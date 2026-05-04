# Provider Baseline Period-Scoped Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replay the checked-in provider baseline fixture through source mapping, reconciliation, and review export after selecting one latest annual period per company/source slice.

**Architecture:** Add a focused `structured_sources/provider_baseline_replay.py` orchestration module. It reads source inventory records, resolves company/source groups from `DEFAULT_PROVIDER_FIELD_CAPTURE_TARGETS`, filters each provider group to its latest annual period, then reuses existing mapping, reconciliation, and export writers. Add a thin CLI/script wrapper and keep all generated artifacts under `tmp/runs/`.

**Tech Stack:** Python 3.11 standard library, existing source inventory gzip reader, existing source mapping/reconciliation/export modules, `pytest`, `ruff`, `mypy`.

---

## File Structure

- Create: `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`
  - Period-scoped record selection.
  - Company/source grouping from provider capture targets.
  - Replay writer and JSON/Markdown summary.
- Create: `tests/test_provider_baseline_replay.py`
  - Synthetic period-selection tests.
  - Fixture-backed replay regression.
- Modify: `src/financial_report_llm_extractor/cli.py`
  - Add `replay-provider-baseline` command.
- Modify: `tests/test_cli.py`
  - Add CLI delegation test.
- Create: `scripts/run-provider-baseline-period-replay.sh`
  - Local no-network entrypoint.
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
  - Record why period-scoped replay is the next validation step.
- Modify: `docs/2026-04-30-codex-claude-handoff-prompt.md`
  - Point future agents to the replay summary and avoid whole-baseline mapping.

## Task 1: Period-Scoped Selection Helpers

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`
- Create: `tests/test_provider_baseline_replay.py`

- [ ] **Step 1: Write failing period-selection tests**

Add `tests/test_provider_baseline_replay.py`:

```python
from decimal import Decimal

from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
)
from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
    ProviderBaselineGroup,
    company_source_groups,
    select_latest_annual_records,
)


def _record(
    *,
    source: str = "akshare",
    market: str = "CN",
    ticker: str = "600519",
    statement_type: str = "income_statement",
    period: str = "2024-12-31",
    raw_field_name: str = "营业收入",
    raw_field_code: str | None = "OPERATE_INCOME",
    raw_value: str = "100",
) -> SourceInventoryRecord:
    evidence = SourceEvidence(
        source=source,  # type: ignore[arg-type]
        adapter=source,
        function=statement_type,
        artifact_id=f"{source}_{ticker}_{statement_type}",
        raw_record_id=f"{source}:{ticker}:{statement_type}:{period}:{raw_field_name}",
        raw_field_name=raw_field_name,
        raw_field_code=raw_field_code,
    )
    return SourceInventoryRecord(
        source=source,  # type: ignore[arg-type]
        market=market,
        ticker=ticker,
        statement_type=statement_type,
        period=period,
        raw_field_name=raw_field_name,
        raw_field_code=raw_field_code,
        raw_value=raw_value,
        parsed_numeric_value=Decimal(raw_value),
        currency="CNY" if market == "CN" else "HKD",
        unit="yuan" if market == "CN" else "raw",
        source_evidence=(evidence,),
    )


def test_select_latest_annual_records_ignores_interim_periods() -> None:
    records = (
        _record(period="2024-12-31", raw_value="100"),
        _record(period="2025-09-30", raw_value="200"),
        _record(period="2023-12-31", raw_value="50"),
    )

    selected = select_latest_annual_records(records)

    assert [record.period for record in selected] == ["2024-12-31"]
    assert [record.raw_value for record in selected] == ["100"]


def test_select_latest_annual_records_is_group_local() -> None:
    akshare_2025 = _record(source="akshare", ticker="600519", period="2025-12-31")
    yahoo_2024 = _record(
        source="yahoo",
        market="CN",
        ticker="600519.SS",
        period="2024-12-31",
        raw_field_name="Total Revenue",
        raw_field_code=None,
    )

    assert select_latest_annual_records((akshare_2025,)) == (akshare_2025,)
    assert select_latest_annual_records((yahoo_2024,)) == (yahoo_2024,)


def test_company_source_groups_resolve_provider_tickers_from_targets() -> None:
    groups = company_source_groups()

    assert groups["600519"]["akshare"] == ProviderBaselineGroup(
        company_id="600519",
        source="akshare",
        market="CN",
        provider_ticker="600519",
    )
    assert groups["600519"]["yahoo"] == ProviderBaselineGroup(
        company_id="600519",
        source="yahoo",
        market="CN",
        provider_ticker="600519.SS",
    )
    assert groups["00001"]["yahoo"].provider_ticker == "0001.HK"
    assert groups["01113"]["yahoo"].provider_ticker == "1113.HK"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py -v
```

Expected: fail with `ModuleNotFoundError` for `provider_baseline_replay`.

- [ ] **Step 3: Implement selection helpers**

Create `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`:

```python
"""Period-scoped replay for the provider field baseline fixture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from financial_report_llm_extractor.structured_sources.capture_targets import (
    DEFAULT_PROVIDER_FIELD_CAPTURE_TARGETS,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
    SourceName,
)

ReplaySliceName = Literal["akshare_only", "yahoo_only", "combined"]


@dataclass(frozen=True)
class ProviderBaselineGroup:
    company_id: str
    source: SourceName
    market: str
    provider_ticker: str


def company_source_groups() -> dict[str, dict[SourceName, ProviderBaselineGroup]]:
    groups: dict[str, dict[SourceName, ProviderBaselineGroup]] = {}
    for target in DEFAULT_PROVIDER_FIELD_CAPTURE_TARGETS:
        company_groups = groups.setdefault(target.company_id, {})
        company_groups[target.provider] = ProviderBaselineGroup(
            company_id=target.company_id,
            source=target.provider,
            market=target.market,
            provider_ticker=target.provider_ticker,
        )
    return groups


def records_for_group(
    records: tuple[SourceInventoryRecord, ...],
    group: ProviderBaselineGroup,
) -> tuple[SourceInventoryRecord, ...]:
    return tuple(
        record
        for record in records
        if record.source == group.source
        and record.market == group.market
        and record.ticker == group.provider_ticker
    )


def select_latest_annual_records(
    records: tuple[SourceInventoryRecord, ...],
) -> tuple[SourceInventoryRecord, ...]:
    annual_periods = {
        record.period
        for record in records
        if record.source_status == "present"
        and record.period is not None
        and _is_annual_period(record.period)
    }
    if not annual_periods:
        return records
    selected_period = sorted(annual_periods)[-1]
    return tuple(
        record
        for record in records
        if record.source_status != "present" or record.period == selected_period
    )


def _is_annual_period(period: str) -> bool:
    return period.split(" ")[0].endswith("-12-31")
```

- [ ] **Step 4: Run period-selection tests**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py tests/test_provider_baseline_replay.py
git commit -m "feat: select provider baseline replay periods"
```

## Task 2: Replay Writer And Summary Artifacts

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`
- Modify: `tests/test_provider_baseline_replay.py`

- [ ] **Step 1: Add failing synthetic replay test**

Append to `tests/test_provider_baseline_replay.py`:

```python
import json
from pathlib import Path

from financial_report_llm_extractor.structured_sources.artifacts import (
    write_source_inventory,
)
from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
    write_provider_baseline_period_replay,
)


def test_write_provider_baseline_period_replay_selects_one_period_per_source(
    tmp_path: Path,
) -> None:
    inventory_path = tmp_path / "source_inventory.jsonl"
    write_source_inventory(
        inventory_path,
        (
            _record(period="2024-12-31", raw_value="100"),
            _record(period="2025-12-31", raw_value="120"),
            _record(
                source="yahoo",
                market="CN",
                ticker="600519.SS",
                statement_type="balance_sheet",
                period="2024-12-31",
                raw_field_name="Cash And Cash Equivalents",
                raw_field_code=None,
                raw_value="90",
            ),
            _record(
                source="yahoo",
                market="CN",
                ticker="600519.SS",
                statement_type="balance_sheet",
                period="2025-12-31",
                raw_field_name="Cash And Cash Equivalents",
                raw_field_code=None,
                raw_value="120",
            ),
        ),
    )

    result = write_provider_baseline_period_replay(
        inventory_path=inventory_path,
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path / "replay",
        company_ids=("600519",),
    )

    payload = json.loads(result.summary_path.read_text(encoding="utf-8"))
    company = payload["companies"][0]
    assert company["company_id"] == "600519"
    assert company["selected_periods"] == {
        "akshare": "2025-12-31",
        "yahoo": "2025-12-31",
    }
    assert company["coverage"]["akshare_only"]["covered_fields"] == ["revenue"]
    assert company["coverage"]["yahoo_only"]["covered_fields"] == ["cash"]
    assert company["coverage"]["combined"]["covered_fields"] == ["cash", "revenue"]
    assert (tmp_path / "replay" / "600519" / "combined" / "review_summary.json").exists()
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py::test_write_provider_baseline_period_replay_selects_one_period_per_source -v
```

Expected: fail because `write_provider_baseline_period_replay` is missing.

- [ ] **Step 3: Implement replay writer**

Append to `provider_baseline_replay.py`:

```python
import json
from pathlib import Path
from typing import Any

from financial_report_llm_extractor.structured_sources.artifacts import (
    read_source_inventory,
    write_source_inventory,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    load_source_mapping_catalog,
)
from financial_report_llm_extractor.structured_sources.export import (
    build_source_first_export,
    write_source_first_export_artifacts,
)
from financial_report_llm_extractor.structured_sources.mapping import (
    TurtleMappingResult,
    map_source_inventory,
    write_turtle_mapping_artifacts,
)
from financial_report_llm_extractor.structured_sources.reconciliation import (
    ReconciliationReport,
    reconcile_mapped_fields,
    write_reconciliation_report,
)


@dataclass(frozen=True)
class ProviderBaselineReplayResult:
    summary_path: Path
    markdown_path: Path
    company_count: int


def write_provider_baseline_period_replay(
    *,
    inventory_path: Path,
    catalog_path: Path,
    output_dir: Path,
    summary_path: Path | None = None,
    company_ids: tuple[str, ...] | None = None,
) -> ProviderBaselineReplayResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = read_source_inventory(inventory_path)
    catalog = load_source_mapping_catalog(catalog_path, priorities=("P0", "P1"))
    groups = company_source_groups()
    selected_company_ids = company_ids or tuple(sorted(groups))
    companies = []
    for company_id in selected_company_ids:
        company_groups = groups[company_id]
        akshare_records = select_latest_annual_records(
            records_for_group(records, company_groups["akshare"])
        )
        yahoo_records = select_latest_annual_records(
            records_for_group(records, company_groups["yahoo"])
        )
        company_dir = output_dir / company_id
        akshare_report = _write_slice(
            company_dir / "akshare_only",
            catalog=catalog,
            records=akshare_records,
        )
        yahoo_report = _write_slice(
            company_dir / "yahoo_only",
            catalog=catalog,
            records=yahoo_records,
        )
        combined_report = _write_slice(
            company_dir / "combined",
            catalog=catalog,
            records=akshare_records + yahoo_records,
        )
        companies.append(
            {
                "company_id": company_id,
                "selected_periods": {
                    "akshare": _selected_period(akshare_records),
                    "yahoo": _selected_period(yahoo_records),
                },
                "record_counts": {
                    "akshare_only": len(akshare_records),
                    "yahoo_only": len(yahoo_records),
                    "combined": len(akshare_records) + len(yahoo_records),
                },
                "coverage": {
                    "akshare_only": akshare_report["coverage"],
                    "yahoo_only": yahoo_report["coverage"],
                    "combined": combined_report["coverage"],
                },
                "review": {
                    "akshare_only": akshare_report["review"],
                    "yahoo_only": yahoo_report["review"],
                    "combined": combined_report["review"],
                },
                "artifact_paths": {
                    "akshare_only": akshare_report["artifact_paths"],
                    "yahoo_only": yahoo_report["artifact_paths"],
                    "combined": combined_report["artifact_paths"],
                },
            }
        )

    payload = {
        "report_id": "provider_baseline_period_replay",
        "catalog_id": catalog.catalog_id,
        "catalog_version": catalog.version,
        "inventory_path": str(inventory_path),
        "company_count": len(companies),
        "companies": companies,
    }
    json_path = summary_path or output_dir / "provider_baseline_period_replay_summary.json"
    markdown_path = output_dir / "provider_baseline_period_replay_summary.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_summary_markdown(payload), encoding="utf-8")
    return ProviderBaselineReplayResult(
        summary_path=json_path,
        markdown_path=markdown_path,
        company_count=len(companies),
    )


def _write_slice(
    output_dir: Path,
    *,
    catalog: Any,
    records: tuple[SourceInventoryRecord, ...],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_source_inventory(output_dir / "source_inventory.jsonl", records)
    mapping = map_source_inventory(catalog, records)
    reconciliation = reconcile_mapped_fields(mapping)
    export = build_source_first_export(mapping, reconciliation, profile="source_only")
    write_turtle_mapping_artifacts(mapping, output_dir)
    write_reconciliation_report(reconciliation, output_dir / "reconciliation_report.json")
    write_source_first_export_artifacts(export, output_dir)
    return {
        "coverage": _mapping_coverage(mapping),
        "review": _review_lists(mapping, reconciliation),
        "artifact_paths": {
            "source_inventory": str(output_dir / "source_inventory.jsonl"),
            "turtle_mapping": str(output_dir / "turtle_mapping.json"),
            "source_coverage_summary": str(output_dir / "source_coverage_summary.json"),
            "reconciliation_report": str(output_dir / "reconciliation_report.json"),
            "extraction_result": str(output_dir / "extraction_result.json"),
            "review_summary": str(output_dir / "review_summary.json"),
        },
    }


def _mapping_coverage(mapping: TurtleMappingResult) -> dict[str, object]:
    covered = sorted(
        field_id
        for field_id, field in mapping.fields.items()
        if field.status in {"present", "derived"}
    )
    total = len(mapping.fields)
    return {
        "covered_fields": covered,
        "covered_count": len(covered),
        "total_fields": total,
        "coverage_ratio": len(covered) / total if total else 0.0,
    }


def _review_lists(
    mapping: TurtleMappingResult,
    reconciliation: ReconciliationReport,
) -> dict[str, list[str]]:
    return {
        "present_fields": sorted(
            field_id
            for field_id, field in mapping.fields.items()
            if field.status in {"present", "derived"}
        ),
        "missing_fields": sorted(
            field_id
            for field_id, field in mapping.fields.items()
            if field.status == "missing"
        ),
        "ambiguous_fields": sorted(
            field_id
            for field_id, field in mapping.fields.items()
            if field.status == "ambiguous"
        ),
        "blocked_fields": sorted(
            field_id
            for field_id, field in mapping.fields.items()
            if field.status == "blocked"
        ),
        "conflict_fields": list(reconciliation.conflict_fields),
    }


def _selected_period(records: tuple[SourceInventoryRecord, ...]) -> str | None:
    periods = sorted(
        {
            record.period
            for record in records
            if record.source_status == "present" and record.period is not None
        }
    )
    if not periods:
        return None
    return periods[-1].split(" ")[0]


def _summary_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Provider Baseline Period Replay",
        "",
        f"- company_count: {payload['company_count']}",
        "",
    ]
    for company in payload["companies"]:
        lines.extend([f"## {company['company_id']}", ""])
        for slice_name in ("akshare_only", "yahoo_only", "combined"):
            coverage = company["coverage"][slice_name]
            review = company["review"][slice_name]
            lines.append(
                f"- {slice_name}: {coverage['covered_count']}/{coverage['total_fields']} "
                f"covered; conflicts={len(review['conflict_fields'])}; "
                f"ambiguous={len(review['ambiguous_fields'])}; "
                f"blocked={len(review['blocked_fields'])}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Run synthetic replay test**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Add checked-in baseline regression test**

Append:

```python
def test_provider_baseline_period_replay_uses_checked_in_fixture(
    tmp_path: Path,
) -> None:
    result = write_provider_baseline_period_replay(
        inventory_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz"
        ),
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path / "baseline",
    )

    payload = json.loads(result.summary_path.read_text(encoding="utf-8"))

    assert result.company_count == 3
    assert payload["company_count"] == 3
    assert {company["company_id"] for company in payload["companies"]} == {
        "00001",
        "01113",
        "600519",
    }
    assert all(
        company["coverage"]["combined"]["total_fields"] == 15
        for company in payload["companies"]
    )
    assert any(
        company["coverage"]["akshare_only"]["covered_count"] > 0
        or company["coverage"]["yahoo_only"]["covered_count"] > 0
        for company in payload["companies"]
    )
```

- [ ] **Step 6: Run checked-in baseline test**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py::test_provider_baseline_period_replay_uses_checked_in_fixture -v
```

Expected: pass without network calls.

- [ ] **Step 7: Commit Task 2**

```bash
git add src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py tests/test_provider_baseline_replay.py
git commit -m "feat: replay provider baseline by latest annual period"
```

## Task 3: CLI And Script Entry Points

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `tests/test_cli.py`
- Create: `scripts/run-provider-baseline-period-replay.sh`
- Modify: `tests/test_provider_baseline_replay.py`

- [ ] **Step 1: Add CLI delegation test**

Add to `tests/test_cli.py` near other fake result dataclasses:

```python
@dataclass(frozen=True)
class FakeProviderBaselineReplayResult:
    summary_path: Path
    markdown_path: Path
    company_count: int
```

Add test:

```python
def test_replay_provider_baseline_command_calls_replay_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inventory_path = tmp_path / "source_inventory.jsonl.gz"
    catalog_path = tmp_path / "catalog.json"
    output_dir = tmp_path / "replay"
    calls: list[tuple[Path, Path, Path]] = []

    def fake_write_provider_baseline_period_replay(
        *,
        inventory_path: Path,
        catalog_path: Path,
        output_dir: Path,
        summary_path: Path | None = None,
        company_ids: tuple[str, ...] | None = None,
    ) -> FakeProviderBaselineReplayResult:
        assert summary_path is None
        assert company_ids is None
        calls.append((inventory_path, catalog_path, output_dir))
        return FakeProviderBaselineReplayResult(
            summary_path=output_dir / "provider_baseline_period_replay_summary.json",
            markdown_path=output_dir / "provider_baseline_period_replay_summary.md",
            company_count=3,
        )

    monkeypatch.setattr(
        cli,
        "write_provider_baseline_period_replay",
        fake_write_provider_baseline_period_replay,
    )

    exit_code = cli.main(
        [
            "replay-provider-baseline",
            "--inventory",
            str(inventory_path),
            "--catalog",
            str(catalog_path),
            "--out",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert calls == [(inventory_path, catalog_path, output_dir)]
```

- [ ] **Step 2: Run CLI test and verify it fails**

Run:

```bash
uv run pytest tests/test_cli.py::test_replay_provider_baseline_command_calls_replay_layer -v
```

Expected: fail because command is missing.

- [ ] **Step 3: Implement CLI command**

Modify `src/financial_report_llm_extractor/cli.py`:

```python
from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
    write_provider_baseline_period_replay,
)
```

Add parser:

```python
    baseline_replay_parser = subparsers.add_parser("replay-provider-baseline")
    baseline_replay_parser.add_argument("--inventory", required=True, type=Path)
    baseline_replay_parser.add_argument("--catalog", required=True, type=Path)
    baseline_replay_parser.add_argument("--out", required=True, type=Path)
```

Add dispatch:

```python
    if args.command == "replay-provider-baseline":
        replay_result = write_provider_baseline_period_replay(
            inventory_path=args.inventory,
            catalog_path=args.catalog,
            output_dir=args.out,
        )
        print(f"companies={replay_result.company_count}")
        print(f"provider_baseline_replay_summary={replay_result.summary_path}")
        print(f"provider_baseline_replay_markdown={replay_result.markdown_path}")
        return 0
```

- [ ] **Step 4: Add script test**

Append to `tests/test_provider_baseline_replay.py`:

```python
def test_provider_baseline_period_replay_script_is_local_fixture_entrypoint() -> None:
    script = Path("scripts/run-provider-baseline-period-replay.sh").read_text(
        encoding="utf-8"
    )

    assert "replay-provider-baseline" in script
    assert "source_inventory.jsonl.gz" in script
    assert "tmp/runs/provider_baseline_period_replay" in script
```

- [ ] **Step 5: Run script test and verify it fails**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py::test_provider_baseline_period_replay_script_is_local_fixture_entrypoint -v
```

Expected: fail because script is missing.

- [ ] **Step 6: Add script**

Create `scripts/run-provider-baseline-period-replay.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-.}"
cd "${ROOT}"

INVENTORY="${INVENTORY:-tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz}"
CATALOG="${CATALOG:-field_catalog/turtle_v015_source_mapping_minimal.json}"
OUT_DIR="${OUT_DIR:-tmp/runs/provider_baseline_period_replay}"

uv run financial-report-llm-extractor replay-provider-baseline \
  --inventory "${INVENTORY}" \
  --catalog "${CATALOG}" \
  --out "${OUT_DIR}"
```

Run:

```bash
chmod +x scripts/run-provider-baseline-period-replay.sh
```

- [ ] **Step 7: Run CLI/script tests**

Run:

```bash
uv run pytest tests/test_cli.py::test_replay_provider_baseline_command_calls_replay_layer tests/test_provider_baseline_replay.py::test_provider_baseline_period_replay_script_is_local_fixture_entrypoint -v
```

Expected: both tests pass.

- [ ] **Step 8: Run script once**

Run:

```bash
scripts/run-provider-baseline-period-replay.sh
```

Expected output includes `companies=3` and writes `tmp/runs/provider_baseline_period_replay/provider_baseline_period_replay_summary.json`.

- [ ] **Step 9: Commit Task 3**

```bash
git add src/financial_report_llm_extractor/cli.py tests/test_cli.py tests/test_provider_baseline_replay.py scripts/run-provider-baseline-period-replay.sh
git commit -m "feat: add provider baseline replay cli"
```

## Task 4: Roadmap, Handoff, And Verification

**Files:**
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
- Modify: `docs/2026-04-30-codex-claude-handoff-prompt.md`

- [ ] **Step 1: Update roadmap status**

In the roadmap `Current validation status` section, replace the stale candidate report status with:

```markdown
- Source mapping catalog expansion has promoted 6 strong deterministic mappings, increasing the minimal source mapping denominator from 9 to 15.
- Whole-baseline replay without period scoping is invalid for coverage because the 5-year baseline creates `candidate periods differ` conflicts for every mapped field.
- Provider baseline period-scoped replay is now the next validation artifact:
  - `scripts/run-provider-baseline-period-replay.sh`
  - output: `tmp/runs/provider_baseline_period_replay/provider_baseline_period_replay_summary.json`
  - it selects the latest annual period per company/source before mapping.
```

- [ ] **Step 2: Update handoff guidance**

In `docs/2026-04-30-codex-claude-handoff-prompt.md`, update the current recommendation:

```markdown
- Do not map the full 6,771-row provider baseline directly; it intentionally contains 5 annual periods and will produce period conflicts.
- Use `scripts/run-provider-baseline-period-replay.sh` to inspect latest-period source-first coverage by company and provider.
- Choose subsequent mapping/PDF/LLM work from the replay summary's missing, blocked, ambiguous, and conflict fields.
```

- [ ] **Step 3: Run focused verification**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py tests/test_cli.py tests/test_real_source_validation.py -v
```

Expected: all selected tests pass.

- [ ] **Step 4: Run full verification**

Run:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
git diff --check
```

Expected: all pass.

- [ ] **Step 5: Confirm generated artifacts are untracked**

Run:

```bash
git status --short
```

Expected: no generated `tmp/` artifact is staged. The pre-existing untracked `.codex` may remain.

- [ ] **Step 6: Commit docs**

```bash
git add docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md docs/2026-04-30-codex-claude-handoff-prompt.md
git commit -m "docs: record provider baseline period replay"
```

## Final Review Checklist

- [ ] No provider, PDF, or LLM calls are used in default tests.
- [ ] Latest annual period selection is per company/source group.
- [ ] Replay summary covers `600519`, `00001`, and `01113`.
- [ ] Per-slice artifacts are written under `tmp/runs/provider_baseline_period_replay/`.
- [ ] Whole 5-year baseline is not sent directly into the mapper for coverage decisions.
- [ ] Remaining gaps are visible by present, missing, ambiguous, blocked, and conflict field lists.
- [ ] Full verification passes.
