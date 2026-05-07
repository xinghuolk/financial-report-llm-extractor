# Provider Field Capture Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a replayable AKShare/Yahoo provider field capture baseline so future Turtle mapping work uses saved artifacts instead of repeated API calls.

**Architecture:** Keep provider adapters unchanged. Add a small capture target matrix, add a provider field inventory summary writer over `SourceInventoryRecord` rows, and wire the existing real source validation CLI/script to a `provider_field_baseline` sample set. PC2's artifact manifest/replay support remains the raw artifact consistency boundary.

**Tech Stack:** Python 3.11 standard library, dataclasses, pathlib/json, pytest, existing structured source adapters and validation harness.

**Prerequisite:** Execute and verify `docs/superpowers/plans/2026-05-02-phase-c-akshare-contract-integration.md` first. This plan assumes adapter-backed validation already writes and validates `source_artifact_manifest.json`.

---

## Files

- Create: `src/financial_report_llm_extractor/structured_sources/capture_targets.py`
  - Defines the provider/company/statement target matrix for one-time capture.
- Create: `src/financial_report_llm_extractor/structured_sources/field_inventory_summary.py`
  - Builds and writes `provider_field_inventory_summary.json` from source inventory records.
- Modify: `src/financial_report_llm_extractor/structured_sources/real_source_validation.py`
  - Adds `--sample-set provider_field_baseline` and writes field inventory summaries.
- Modify: `scripts/run-real-source-validation.sh`
  - Forwards `SAMPLE_SET` to the Python validation entrypoint.
- Create: `tests/test_capture_targets.py`
  - Verifies the target matrix.
- Create: `tests/test_field_inventory_summary.py`
  - Verifies raw field summary behavior.
- Modify: `tests/test_real_source_validation.py`
  - Verifies validation writes field inventory summary for adapter-backed and captured runs.
- Create: `tests/test_real_source_validation_script.py`
  - Verifies the shell wrapper forwards the provider field capture sample set.
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
  - Adds the PC3/PD0 provider field capture baseline note.

## Task 1: Capture Target Matrix

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/capture_targets.py`
- Create: `tests/test_capture_targets.py`

- [ ] **Step 1: Write failing matrix test**

Create `tests/test_capture_targets.py`:

```python
from financial_report_llm_extractor.structured_sources.capture_targets import (
    build_provider_field_capture_targets,
)


def test_provider_field_capture_targets_cover_expected_matrix() -> None:
    targets = build_provider_field_capture_targets()

    assert len(targets) == 18
    actual = {
        (
            target.provider,
            target.company_id,
            target.provider_ticker,
            target.market,
            target.statement_type,
            target.currency,
            target.unit,
            target.exchange,
        )
        for target in targets
    }

    assert (
        "akshare",
        "600519",
        "600519",
        "CN",
        "balance_sheet",
        "CNY",
        "yuan",
        "SH",
    ) in actual
    assert (
        "akshare",
        "00001",
        "00001",
        "HK",
        "income_statement",
        "HKD",
        "HKD",
        None,
    ) in actual
    assert (
        "akshare",
        "01113",
        "01113",
        "HK",
        "cash_flow",
        "HKD",
        "HKD",
        None,
    ) in actual
    assert (
        "yahoo",
        "600519",
        "600519.SS",
        "CN",
        "balance_sheet",
        "CNY",
        "raw",
        None,
    ) in actual
    assert (
        "yahoo",
        "00001",
        "0001.HK",
        "HK",
        "income_statement",
        "HKD",
        "raw",
        None,
    ) in actual
    assert (
        "yahoo",
        "01113",
        "1113.HK",
        "HK",
        "cash_flow",
        "HKD",
        "raw",
        None,
    ) in actual


def test_provider_field_capture_targets_can_filter_providers() -> None:
    targets = build_provider_field_capture_targets(providers=("akshare",))

    assert len(targets) == 9
    assert {target.provider for target in targets} == {"akshare"}
```

- [ ] **Step 2: Run failing matrix test**

Run:

```bash
uv run pytest tests/test_capture_targets.py -v
```

Expected: FAIL because `capture_targets.py` does not exist.

- [ ] **Step 3: Implement capture target matrix**

Create `src/financial_report_llm_extractor/structured_sources/capture_targets.py`:

```python
"""Provider field capture target matrix."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from financial_report_llm_extractor.models import Currency


ProviderName = Literal["akshare", "yahoo"]
StatementType = Literal["balance_sheet", "income_statement", "cash_flow"]


@dataclass(frozen=True)
class ProviderCaptureTarget:
    provider: ProviderName
    company_id: str
    provider_ticker: str
    market: str
    statement_type: StatementType
    currency: Currency
    unit: str
    exchange: str | None = None


_STATEMENTS: tuple[StatementType, ...] = (
    "balance_sheet",
    "income_statement",
    "cash_flow",
)


def _targets_for_company(
    *,
    provider: ProviderName,
    company_id: str,
    provider_ticker: str,
    market: str,
    currency: Currency,
    unit: str,
    exchange: str | None = None,
) -> tuple[ProviderCaptureTarget, ...]:
    return tuple(
        ProviderCaptureTarget(
            provider=provider,
            company_id=company_id,
            provider_ticker=provider_ticker,
            market=market,
            statement_type=statement_type,
            currency=currency,
            unit=unit,
            exchange=exchange,
        )
        for statement_type in _STATEMENTS
    )


DEFAULT_PROVIDER_FIELD_CAPTURE_TARGETS: tuple[ProviderCaptureTarget, ...] = (
    *_targets_for_company(
        provider="akshare",
        company_id="600519",
        provider_ticker="600519",
        market="CN",
        currency="CNY",
        unit="yuan",
        exchange="SH",
    ),
    *_targets_for_company(
        provider="akshare",
        company_id="00001",
        provider_ticker="00001",
        market="HK",
        currency="HKD",
        unit="HKD",
    ),
    *_targets_for_company(
        provider="akshare",
        company_id="01113",
        provider_ticker="01113",
        market="HK",
        currency="HKD",
        unit="HKD",
    ),
    *_targets_for_company(
        provider="yahoo",
        company_id="600519",
        provider_ticker="600519.SS",
        market="CN",
        currency="CNY",
        unit="raw",
    ),
    *_targets_for_company(
        provider="yahoo",
        company_id="00001",
        provider_ticker="0001.HK",
        market="HK",
        currency="HKD",
        unit="raw",
    ),
    *_targets_for_company(
        provider="yahoo",
        company_id="01113",
        provider_ticker="1113.HK",
        market="HK",
        currency="HKD",
        unit="raw",
    ),
)


def build_provider_field_capture_targets(
    *,
    providers: tuple[ProviderName, ...] = ("akshare", "yahoo"),
) -> tuple[ProviderCaptureTarget, ...]:
    provider_set = set(providers)
    return tuple(
        target
        for target in DEFAULT_PROVIDER_FIELD_CAPTURE_TARGETS
        if target.provider in provider_set
    )
```

- [ ] **Step 4: Run matrix tests**

Run:

```bash
uv run pytest tests/test_capture_targets.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add src/financial_report_llm_extractor/structured_sources/capture_targets.py tests/test_capture_targets.py
git commit -m "feat: define provider field capture targets"
```

## Task 2: Provider Field Inventory Summary

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/field_inventory_summary.py`
- Create: `tests/test_field_inventory_summary.py`

- [ ] **Step 1: Write failing summary test**

Create `tests/test_field_inventory_summary.py`:

```python
import json
from decimal import Decimal
from pathlib import Path

from financial_report_llm_extractor.structured_sources.field_inventory_summary import (
    build_provider_field_inventory_summary,
    write_provider_field_inventory_summary,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
    SourceStatus,
)


def _record(
    *,
    raw_field_name: str,
    raw_field_code: str | None,
    period: str,
    status: SourceStatus = "present",
) -> SourceInventoryRecord:
    return SourceInventoryRecord(
        source="akshare",
        market="CN",
        ticker="600519",
        statement_type="income_statement",
        period=period,
        raw_field_name=raw_field_name,
        raw_field_code=raw_field_code,
        raw_value="100",
        parsed_numeric_value=Decimal("100"),
        currency="CNY",
        unit="yuan",
        source_status=status,
        source_evidence=(
            SourceEvidence(
                source="akshare",
                adapter="akshare",
                function="stock_profit_sheet_by_report_em",
                artifact_id="akshare_cn_600519_income_statement",
                raw_record_id=f"600519:CN:income_statement:{period}:{raw_field_name}",
                raw_field_name=raw_field_name,
                raw_field_code=raw_field_code,
            ),
        ),
    )


def test_provider_field_inventory_summary_preserves_unmapped_raw_fields() -> None:
    summary = build_provider_field_inventory_summary(
        (
            _record(
                raw_field_name="营业收入",
                raw_field_code="OPERATE_INCOME",
                period="2024-12-31",
            ),
            _record(
                raw_field_name="管理费用",
                raw_field_code="ADMIN_EXPENSE",
                period="2024-12-31",
            ),
            _record(
                raw_field_name="missing",
                raw_field_code=None,
                period="2024-12-31",
                status="missing",
            ),
        ),
        sample_set="provider_field_baseline",
        source_artifact_count=1,
    )

    assert summary["sample_set"] == "provider_field_baseline"
    assert summary["record_count"] == 3
    assert summary["source_artifact_count"] == 1
    assert summary["status_counts"] == {"missing": 1, "present": 2}
    target = summary["targets"][0]
    assert target["source"] == "akshare"
    assert target["ticker"] == "600519"
    assert target["statement_type"] == "income_statement"
    assert target["raw_field_names"] == ["missing", "管理费用", "营业收入"]
    assert target["raw_field_codes"] == ["ADMIN_EXPENSE", "OPERATE_INCOME"]
    assert target["periods"] == ["2024-12-31"]
    assert target["currencies"] == ["CNY"]
    assert target["units"] == ["yuan"]


def test_write_provider_field_inventory_summary_writes_json(tmp_path: Path) -> None:
    path = tmp_path / "provider_field_inventory_summary.json"

    write_provider_field_inventory_summary(
        path,
        records=(
            _record(
                raw_field_name="营业收入",
                raw_field_code="OPERATE_INCOME",
                period="2024-12-31",
            ),
        ),
        sample_set="provider_field_baseline",
        source_artifact_count=None,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["record_count"] == 1
    assert "source_artifact_count" not in payload
```

- [ ] **Step 2: Run failing summary test**

Run:

```bash
uv run pytest tests/test_field_inventory_summary.py -v
```

Expected: FAIL because `field_inventory_summary.py` does not exist.

- [ ] **Step 3: Implement summary builder**

Create `src/financial_report_llm_extractor/structured_sources/field_inventory_summary.py`:

```python
"""Summaries of provider raw fields observed in source inventory records."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
)


def build_provider_field_inventory_summary(
    records: Iterable[SourceInventoryRecord],
    *,
    sample_set: str,
    source_artifact_count: int | None = None,
) -> dict[str, Any]:
    record_tuple = tuple(records)
    status_counts = Counter(record.source_status for record in record_tuple)
    grouped: dict[tuple[str, str, str, str], list[SourceInventoryRecord]] = defaultdict(list)
    for record in record_tuple:
        record.validate()
        key = (record.source, record.market, record.ticker, record.statement_type)
        grouped[key].append(record)

    targets = []
    for (source, market, ticker, statement_type), target_records in sorted(grouped.items()):
        target_status_counts = Counter(record.source_status for record in target_records)
        targets.append(
            {
                "source": source,
                "market": market,
                "ticker": ticker,
                "statement_type": statement_type,
                "record_count": len(target_records),
                "status_counts": dict(sorted(target_status_counts.items())),
                "raw_field_names": sorted(
                    {record.raw_field_name for record in target_records if record.raw_field_name}
                ),
                "raw_field_codes": sorted(
                    {
                        record.raw_field_code
                        for record in target_records
                        if record.raw_field_code
                    }
                ),
                "periods": sorted({record.period for record in target_records if record.period}),
                "currencies": sorted(
                    {record.currency for record in target_records if record.currency}
                ),
                "units": sorted({record.unit for record in target_records if record.unit}),
            }
        )

    summary: dict[str, Any] = {
        "sample_set": sample_set,
        "record_count": len(record_tuple),
        "status_counts": dict(sorted(status_counts.items())),
        "targets": targets,
    }
    if source_artifact_count is not None:
        summary["source_artifact_count"] = source_artifact_count
    return summary


def write_provider_field_inventory_summary(
    path: Path,
    *,
    records: Iterable[SourceInventoryRecord],
    sample_set: str,
    source_artifact_count: int | None = None,
) -> dict[str, Any]:
    summary = build_provider_field_inventory_summary(
        records,
        sample_set=sample_set,
        source_artifact_count=source_artifact_count,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary
```

- [ ] **Step 4: Run summary tests**

Run:

```bash
uv run pytest tests/test_field_inventory_summary.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add src/financial_report_llm_extractor/structured_sources/field_inventory_summary.py tests/test_field_inventory_summary.py
git commit -m "feat: summarize provider field inventory"
```

## Task 3: Validation CLI Integration

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/real_source_validation.py`
- Modify: `scripts/run-real-source-validation.sh`
- Modify: `tests/test_real_source_validation.py`
- Create: `tests/test_real_source_validation_script.py`

- [ ] **Step 1: Write failing validation summary test**

Add to `tests/test_real_source_validation.py`:

```python
def test_real_source_validation_writes_provider_field_inventory_summary(
    tmp_path: Path,
) -> None:
    result = run_real_source_validation(
        samples=(
            RealSourceValidationSample(
                provider="akshare",
                market="CN",
                ticker="600519",
                statement_type="income_statement",
                currency="CNY",
                unit="yuan",
                exchange="SH",
            ),
        ),
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path,
        akshare_client=FakeAkshareClient(),
    )

    summary_path = tmp_path / "provider_field_inventory_summary.json"
    assert summary_path.exists()
    assert result.summary["artifact_paths"]["provider_field_inventory_summary"] == str(summary_path)
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["record_count"] == 1
    assert payload["targets"][0]["raw_field_names"] == ["营业收入"]
```

Extend `test_captured_source_validation_reuses_saved_inventory_without_clients`:

```python
    field_summary_path = tmp_path / "provider_field_inventory_summary.json"
    assert field_summary_path.exists()
    assert result.summary["artifact_paths"]["provider_field_inventory_summary"] == str(field_summary_path)
```

- [ ] **Step 2: Run failing validation summary test**

Run:

```bash
uv run pytest tests/test_real_source_validation.py::test_real_source_validation_writes_provider_field_inventory_summary -v
```

Expected: FAIL because validation does not write `provider_field_inventory_summary.json`.

- [ ] **Step 3: Wire field summary writer**

In `real_source_validation.py`, import:

```python
from financial_report_llm_extractor.structured_sources.field_inventory_summary import (
    write_provider_field_inventory_summary,
)
```

Update `_write_validation_outputs()` to accept:

```python
    sample_set: str,
    source_artifact_count: int | None = None,
```

Update `run_real_source_validation()` to accept:

```python
    sample_set: str = "real_source_adapter",
```

After writing mapping/reconciliation/export artifacts, add:

```python
    field_inventory_summary_path = output_dir / "provider_field_inventory_summary.json"
    write_provider_field_inventory_summary(
        field_inventory_summary_path,
        records=records,
        sample_set=sample_set,
        source_artifact_count=source_artifact_count,
    )
```

In the summary `artifact_paths`, add:

```python
            "provider_field_inventory_summary": str(field_inventory_summary_path),
```

Pass the `run_real_source_validation()` `sample_set` argument through to `_write_validation_outputs()`. Pass `sample_set="captured_source_inventory"` from `run_captured_source_validation()`.

This plan depends on PC2. Use the `source_artifact_count` value produced by PC2 for adapter-backed validation runs. Captured validation runs pass `source_artifact_count=None`.

- [ ] **Step 4: Run validation summary tests**

Run:

```bash
uv run pytest tests/test_real_source_validation.py -v
```

Expected: PASS.

- [ ] **Step 5: Write failing sample-set test**

Add to `tests/test_real_source_validation.py`:

```python
def test_provider_field_capture_sample_set_builds_full_target_matrix() -> None:
    samples = build_provider_field_capture_samples(providers=("akshare", "yahoo"))

    assert len(samples) == 18
    assert RealSourceValidationSample(
        provider="akshare",
        market="CN",
        ticker="600519",
        statement_type="balance_sheet",
        currency="CNY",
        unit="yuan",
        exchange="SH",
    ) in samples
    assert RealSourceValidationSample(
        provider="yahoo",
        market="HK",
        ticker="1113.HK",
        statement_type="cash_flow",
        currency="HKD",
        unit="raw",
    ) in samples
```

- [ ] **Step 6: Run failing sample-set test**

Run:

```bash
uv run pytest tests/test_real_source_validation.py::test_provider_field_capture_sample_set_builds_full_target_matrix -v
```

Expected: FAIL because `build_provider_field_capture_samples()` is not defined.

- [ ] **Step 7: Implement sample-set builder and CLI option**

In `real_source_validation.py`, import:

```python
from financial_report_llm_extractor.structured_sources.capture_targets import (
    ProviderName,
    build_provider_field_capture_targets,
)
```

Add:

```python
def build_provider_field_capture_samples(
    *,
    providers: tuple[ProviderName, ...] = ("akshare", "yahoo"),
) -> tuple[RealSourceValidationSample, ...]:
    return tuple(
        RealSourceValidationSample(
            provider=target.provider,
            market=target.market,
            ticker=target.provider_ticker,
            statement_type=target.statement_type,
            currency=target.currency,
            unit=target.unit,
            exchange=target.exchange,
        )
        for target in build_provider_field_capture_targets(providers=providers)
    )
```

In `main()`, add:

```python
    parser.add_argument(
        "--sample-set",
        choices=("default", "provider_field_baseline"),
        default="default",
        help="Validation sample set to run.",
    )
```

Replace the final `samples=build_default_validation_samples(...)` block with:

```python
        samples = (
            build_provider_field_capture_samples(providers=providers)
            if args.sample_set == "provider_field_baseline"
            else build_default_validation_samples(
                providers=providers,
                akshare_cn_statements=akshare_cn_statements,
            )
        )
        result = run_real_source_validation(
            samples=samples,
            catalog_path=args.catalog,
            output_dir=args.out_dir,
            sample_set=args.sample_set,
        )
```

- [ ] **Step 8: Update shell script forwarding**

In `scripts/run-real-source-validation.sh`, add after `INVENTORY_FIXTURE`:

```bash
SAMPLE_SET="${SAMPLE_SET:-default}"
```

In the real-provider branch, pass:

```bash
    --sample-set "${SAMPLE_SET}" \
```

The real-provider command should become:

```bash
  PYTHONPATH=src "${PYTHON_BIN}" -m financial_report_llm_extractor.structured_sources.real_source_validation \
    --catalog "${CATALOG}" \
    --out-dir "${OUT_DIR}" \
    --providers "${PROVIDERS}" \
    --sample-set "${SAMPLE_SET}" \
    --akshare-cn-statements "${AKSHARE_CN_STATEMENTS}"
```

- [ ] **Step 9: Write script forwarding test**

Create `tests/test_real_source_validation_script.py`:

```python
from pathlib import Path


def test_real_source_validation_script_forwards_sample_set() -> None:
    script = Path("scripts/run-real-source-validation.sh").read_text(encoding="utf-8")

    assert 'SAMPLE_SET="${SAMPLE_SET:-default}"' in script
    assert '--sample-set "${SAMPLE_SET}"' in script
```

- [ ] **Step 10: Run integration tests**

Run:

```bash
uv run pytest tests/test_capture_targets.py tests/test_field_inventory_summary.py tests/test_real_source_validation.py tests/test_real_source_validation_script.py -v
```

Expected: PASS.

- [ ] **Step 11: Commit Task 3**

Run:

```bash
git add src/financial_report_llm_extractor/structured_sources/real_source_validation.py scripts/run-real-source-validation.sh tests/test_real_source_validation.py tests/test_real_source_validation_script.py
git commit -m "feat: add provider field capture sample set"
```

## Task 4: Roadmap And Capture Workflow

**Files:**
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`

- [ ] **Step 1: Update roadmap Phase C/D notes**

In the Phase C implementation note, add:

```markdown
- PC3/PD0 should capture the target AKShare/Yahoo provider field baseline once, save raw artifacts plus `provider_field_inventory_summary.json`, and drive subsequent mapping work from captured fixtures.
```

In the validation command section, add:

```bash
REAL_SOURCE_VALIDATION=1 \
SAMPLE_SET=provider_field_baseline \
PROVIDERS=akshare,yahoo \
OUT_DIR=tmp/runs/provider_field_capture_baseline \
scripts/run-real-source-validation.sh
```

- [ ] **Step 2: Run docs sanity checks**

Run:

```bash
rg -n "provider_field_baseline|provider_field_inventory_summary" docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md docs/superpowers/specs/2026-05-02-provider-field-capture-baseline.md docs/superpowers/plans/2026-05-02-provider-field-capture-baseline.md
git diff --check
```

Expected: `rg` finds the new workflow references and `git diff --check` exits 0.

- [ ] **Step 3: Run full verification**

Run:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
git diff --check
```

Expected: all commands pass.

- [ ] **Step 4: Commit Task 4**

Run:

```bash
git add docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md
git commit -m "docs: document provider field capture workflow"
```

## Manual Capture Gate

Run this only after PC2 and Tasks 1-4 are complete:

```bash
REAL_SOURCE_VALIDATION=1 \
SAMPLE_SET=provider_field_baseline \
PROVIDERS=akshare,yahoo \
OUT_DIR=tmp/runs/provider_field_capture_baseline \
scripts/run-real-source-validation.sh
```

Review these outputs before promoting fixtures:

```text
tmp/runs/provider_field_capture_baseline/source_artifacts/
tmp/runs/provider_field_capture_baseline/source_artifact_manifest.json
tmp/runs/provider_field_capture_baseline/source_inventory.jsonl
tmp/runs/provider_field_capture_baseline/provider_field_inventory_summary.json
tmp/runs/provider_field_capture_baseline/real_source_validation_summary.json
```

Promote only a successful, reviewed capture to:

```text
tests/fixtures/provider_captures/provider_field_baseline/
```

## Self-Review

- Spec coverage: Task 1 covers the target matrix; Task 2 covers the raw field summary; Task 3 covers validation/script integration; Task 4 covers roadmap workflow; the manual capture gate covers one-time real provider use.
- Red-flag scan: no task uses fill-in wording; each code step includes concrete code or exact commands.
- Type consistency: the plan consistently uses `ProviderCaptureTarget`, `build_provider_field_capture_targets()`, `build_provider_field_capture_samples()`, and `provider_field_inventory_summary.json`.
