# evaluate-company Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个 env / args 驱动的 per-(company, period) 验证 orchestrator，分两步（fetch + evaluate），输出 source-first export + 可选 LLM supplement + bucket-classified evaluation 报告，作为后续 catalog/policy/LLM-prompt 改动的常规回归验证 gate。

**Architecture:** 复用 `provider_baseline_replay._write_slice`（本计划提为 public `evaluate_source_first_slice`）作为 orchestrator 内核；新模块 `source_inventory_fetch` 把现有 `real_source_validation` 的 client 注入路径暴露成 per-(company, period) API；新模块 `company_evaluation` 是基于 `WarningClassificationResult.items[<id>].category` 的 6 桶纯函数派生 + markdown 渲染。CLI 加 `fetch-source-inventory` 与 `evaluate-company` 两个 subcommand，配 shell wrapper 做 env 入口。

**Tech Stack:** Python 3.11 stdlib, frozen dataclasses, 现有 `real_source_validation` adapter primitives, `provider_baseline_replay` 公开化的 slice writer, `llm_extraction_runner` + `chunking` + `ingestion` (PDF→chunks→LLM 流水线), `warning_classification` (桶分类源), pytest。

**Spec:** `docs/superpowers/specs/2026-05-09-evaluate-company-orchestrator-design.md`

---

## File Structure

| 文件 | 职责 |
|------|------|
| `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py` | Refactor: `_write_slice` → public `evaluate_source_first_slice`；3 个 caller 全部更新 |
| `src/financial_report_llm_extractor/structured_sources/source_inventory_fetch.py` | NEW: `PeriodSpec`、`select_records_for_period`、`fetch_source_inventory`、`build_per_company_samples`；约 280 行 |
| `src/financial_report_llm_extractor/structured_sources/company_evaluation.py` | NEW: `BucketName` Literal、`CompanyFieldEvaluation`/`CompanyEvaluation` dataclass、`classify_field` 纯函数级联、`build_company_evaluation`、`render_evaluation_markdown`、`run_company_evaluation` orchestrator；约 220 行 |
| `src/financial_report_llm_extractor/cli.py` | NEW: `fetch-source-inventory` 与 `evaluate-company` 两个 subparser dispatch |
| `tests/test_source_inventory_fetch.py` | NEW: 6 个单测 + 1 个 opt-in 集成测 |
| `tests/test_company_evaluation.py` | NEW: 5 个单测 + 1 个 opt-in 集成测 |
| `tests/test_cli.py` | MODIFY: 加 `evaluate-company` subcommand dispatch 单测 |
| `tests/test_provider_baseline_replay.py` | MODIFY: Refactor 0 后保证行为不变的回归测 |
| `scripts/run-fetch-source-inventory.sh` | NEW: env wrapper |
| `scripts/run-evaluate-company.sh` | NEW: env wrapper |
| `CLAUDE.md` | MODIFY: 阶段表新增 evaluate-company；下一步指针更新 |
| `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md` | MODIFY: §6 Validation Commands 加 evaluate-company；说明与 replay-provider-baseline 边界 |

---

## Task 0: Refactor `_write_slice` 提为公开 `evaluate_source_first_slice`

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py:213, 223, 233, 306`
- Modify: `tests/test_provider_baseline_replay.py`

- [ ] **Step 1: 写一个回归测，证明 refactor 后 replay-provider-baseline 输出不变**

新增测试到 `tests/test_provider_baseline_replay.py`（找到现有 fixture-based 测，复用 fixture）：

```python
def test_evaluate_source_first_slice_is_publicly_callable_with_same_behavior(
    tmp_path: Path,
) -> None:
    """Refactor 0 regression: 提为 public 后行为不变。"""
    from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
        evaluate_source_first_slice,
    )

    # 复用 _write_slice 现有测试 fixture（catalog + taxonomy + 6 records）
    catalog = _load_minimal_catalog()
    taxonomy = _load_minimal_taxonomy()
    records = _build_minimal_records()

    out_dir = tmp_path / "slice"
    result = evaluate_source_first_slice(
        out_dir,
        catalog=catalog,
        taxonomy=taxonomy,
        records=records,
        company_id="600519",
        market="CN",
        hk_yahoo_trust_policy=None,
        provider_semantics_catalog=None,
    )

    assert (out_dir / "source_inventory.jsonl").exists()
    assert (out_dir / "source_first_export.json").exists()
    # Existing keys preserved
    assert "coverage" in result and "review" in result and "artifact_paths" in result
    # NEW keys for downstream orchestrators
    assert "export_object" in result
    assert "warning_classification_object" in result
    assert hasattr(result["export_object"], "items")
    assert hasattr(result["warning_classification_object"], "items")
```

- [ ] **Step 2: 跑测试，应该 fail（symbol 不存在）**

Run: `uv run pytest tests/test_provider_baseline_replay.py::test_evaluate_source_first_slice_is_publicly_callable_with_same_behavior -v`
Expected: FAIL with `ImportError: cannot import name 'evaluate_source_first_slice'`

- [ ] **Step 3: 在 provider_baseline_replay.py 中重命名 `_write_slice` 为 `evaluate_source_first_slice` 并扩展 return 含活对象**

```python
# Before (line 306)
def _write_slice(
    output_dir: Path,
    *,
    catalog: Any,
    ...
) -> dict[str, Any]:
    ...
    return {
        "coverage": _export_coverage(export),
        "review": review,
        "artifact_paths": artifact_paths,
    }

# After
def evaluate_source_first_slice(
    output_dir: Path,
    *,
    catalog: Any,
    ...
) -> dict[str, Any]:
    ...
    return {
        "coverage": _export_coverage(export),
        "review": review,
        "artifact_paths": artifact_paths,
        # NEW: expose live objects so downstream orchestrators don't have to
        # re-parse JSON artifacts. Keys deliberately distinct from artifact_paths
        # to avoid type confusion.
        "export_object": export,
        "warning_classification_object": warning_classification,
    }
```

更新 3 处 caller（lines 213, 223, 233）：

```python
# Before
akshare_report = _write_slice(...)
yahoo_report = _write_slice(...)
combined_report = _write_slice(...)

# After
akshare_report = evaluate_source_first_slice(...)
yahoo_report = evaluate_source_first_slice(...)
combined_report = evaluate_source_first_slice(...)
```

- [ ] **Step 4: 跑回归测 + 整套 provider_baseline_replay 测试**

Run: `uv run pytest tests/test_provider_baseline_replay.py -v`
Expected: 所有现有测 + 新回归测都 PASS。

- [ ] **Step 5: 跑整套验证**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src tests`
Expected: 全绿（应有 +1 pass，total 495）。

- [ ] **Step 6: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py tests/test_provider_baseline_replay.py
git commit -m "refactor: promote _write_slice to public evaluate_source_first_slice

Prerequisite for evaluate-company orchestrator (per design spec
2026-05-09). All 3 internal callers updated; behavior unchanged.
Regression test added to lock the public contract.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 1: `PeriodSpec` dataclass + `select_records_for_period` 过滤器

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/source_inventory_fetch.py`
- Create: `tests/test_source_inventory_fetch.py`

- [ ] **Step 1: 写 `PeriodSpec.from_year` 失败测**

新建 `tests/test_source_inventory_fetch.py`：

```python
"""Tests for source_inventory_fetch module."""

from __future__ import annotations

from datetime import date

import pytest


def test_period_spec_year_shortcut_expands() -> None:
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
    )

    spec = PeriodSpec.from_year(2024)

    assert spec.period_end == date(2024, 12, 31)
    assert spec.report_type == "annual"


def test_period_spec_from_period_end_string_parses() -> None:
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
    )

    spec = PeriodSpec.from_period_end("2024-06-30", report_type="half_year")

    assert spec.period_end == date(2024, 6, 30)
    assert spec.report_type == "half_year"
```

- [ ] **Step 2: 跑测试确认 fail**

Run: `uv run pytest tests/test_source_inventory_fetch.py -v`
Expected: FAIL with `ModuleNotFoundError: source_inventory_fetch`.

- [ ] **Step 3: 创建模块骨架 + `PeriodSpec`**

`src/financial_report_llm_extractor/structured_sources/source_inventory_fetch.py`：

```python
"""Per-(company, period) live source inventory fetch for evaluate-company.

Wraps real_source_validation adapter primitives with a (company, period_end,
market)-keyed sample builder, so each call produces a single-period
source_inventory.jsonl + summary in a deterministic out_dir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

ReportType = Literal["annual", "half_year", "quarterly", "ttm"]


@dataclass(frozen=True)
class PeriodSpec:
    period_end: date
    report_type: ReportType

    @classmethod
    def from_year(cls, year: int) -> "PeriodSpec":
        return cls(period_end=date(year, 12, 31), report_type="annual")

    @classmethod
    def from_period_end(
        cls, period_end: str, report_type: ReportType = "annual"
    ) -> "PeriodSpec":
        parsed = date.fromisoformat(period_end)
        return cls(period_end=parsed, report_type=report_type)
```

- [ ] **Step 4: 跑测试确认 PASS**

Run: `uv run pytest tests/test_source_inventory_fetch.py -v`
Expected: 2 passed.

- [ ] **Step 5: 写 `select_records_for_period` 过滤器测**

追加到 `tests/test_source_inventory_fetch.py`：

```python
def _build_record(period: str, status: str = "present") -> "SourceInventoryRecord":
    from financial_report_llm_extractor.structured_sources.models import (
        SourceInventoryRecord,
    )
    return SourceInventoryRecord(
        record_id=f"r-{period}",
        provider="akshare",
        market="CN",
        ticker="600519",
        statement_type="income_statement",
        period=period,
        field="OPERATE_INCOME",
        raw_value="100",
        currency="CNY",
        unit="yuan",
        source_status=status,  # type: ignore[arg-type]
    )


def test_select_records_for_period_filters_to_target_period() -> None:
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
        select_records_for_period,
    )

    records = (
        _build_record("2023-12-31"),
        _build_record("2024-12-31"),
        _build_record("2024-12-31"),
    )

    filtered = select_records_for_period(records, PeriodSpec.from_year(2024))

    assert len(filtered) == 2
    assert all(r.period == "2024-12-31" for r in filtered)


def test_select_records_for_period_raises_on_missing_target_period() -> None:
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
        select_records_for_period,
    )

    records = (_build_record("2023-12-31"),)

    with pytest.raises(ValueError, match="2024-12-31"):
        select_records_for_period(records, PeriodSpec.from_year(2024))
```

- [ ] **Step 6: 跑测试确认 fail**

Run: `uv run pytest tests/test_source_inventory_fetch.py -v`
Expected: 2 passed + 2 failed (`select_records_for_period` not defined).

- [ ] **Step 7: 实现 `select_records_for_period`**

追加到 `source_inventory_fetch.py`：

```python
from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
)


def select_records_for_period(
    records: tuple[SourceInventoryRecord, ...],
    period: PeriodSpec,
) -> tuple[SourceInventoryRecord, ...]:
    """按 PeriodSpec.period_end 过滤记录。

    fail-loud：如果记录中没有匹配 period 的 present 记录，raise ValueError。
    与现有 _select_latest_annual_records 不同 —— 不 silently fall back to latest。
    """
    target = period.period_end.isoformat()
    matching = tuple(
        r for r in records
        if r.period is not None and r.period.startswith(target)
    )
    has_present = any(r.source_status == "present" for r in matching)
    if not has_present:
        raise ValueError(
            f"no present records for period {target}; "
            f"available periods: {sorted({r.period for r in records if r.period})}"
        )
    return matching
```

- [ ] **Step 8: 跑测试确认全 PASS**

Run: `uv run pytest tests/test_source_inventory_fetch.py -v`
Expected: 4 passed.

- [ ] **Step 9: 跑整套验证**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src tests`
Expected: 全绿（total 499）。

- [ ] **Step 10: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/source_inventory_fetch.py tests/test_source_inventory_fetch.py
git commit -m "feat: add PeriodSpec + fail-loud select_records_for_period filter

Per evaluate-company spec §模块边界. PeriodSpec.from_year(YYYY) is the
shortcut for fiscal annual; from_period_end(YYYY-MM-DD, report_type)
is the canonical form (TTM/interim future-proof).

select_records_for_period replaces the implicit 'pick latest' behavior
of _select_latest_annual_records when the caller has an explicit period
in mind. Raises rather than silently substituting a different period.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `fetch_source_inventory` + `fetch-source-inventory` CLI

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/source_inventory_fetch.py`
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `tests/test_source_inventory_fetch.py`
- Create: `scripts/run-fetch-source-inventory.sh`

- [ ] **Step 1: 写 `fetch_source_inventory` 注入式 fake-client 测**

追加到 `tests/test_source_inventory_fetch.py`：

```python
class _FakeAkshareClient:
    """Minimal AkshareLikeClient stub returning canned 600519 income statement."""

    def stock_balance_sheet_by_report_em(
        self, *, symbol: str
    ) -> list[dict[str, object]]:
        return []

    def stock_profit_sheet_by_report_em(
        self, *, symbol: str
    ) -> list[dict[str, object]]:
        assert symbol == "SH600519"
        return [
            {
                "REPORT_DATE": "2024-12-31",
                "STD_ITEM_CODE": "OPERATE_INCOME",
                "STD_ITEM_NAME": "营业收入",
                "AMOUNT": "168838700000",
            },
            {
                "REPORT_DATE": "2023-12-31",  # earlier period, must be filtered out
                "STD_ITEM_CODE": "OPERATE_INCOME",
                "STD_ITEM_NAME": "营业收入",
                "AMOUNT": "120000000000",
            },
        ]

    def stock_cash_flow_sheet_by_report_em(
        self, *, symbol: str
    ) -> list[dict[str, object]]:
        return []

    def stock_financial_hk_report_em(
        self, *, stock: str, symbol: str, indicator: str
    ) -> list[dict[str, object]]:
        return []

    def stock_financial_hk_report_metadata(
        self, *, stock: str
    ) -> list[dict[str, object]]:
        return []


def test_fetch_source_inventory_writes_period_filtered_artifacts(
    tmp_path: Path,
) -> None:
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
        fetch_source_inventory,
    )

    catalog_path = Path("field_catalog/turtle_v015_source_mapping_minimal.json")

    artifact = fetch_source_inventory(
        company="600519",
        period=PeriodSpec.from_year(2024),
        market="CN",
        providers=("akshare",),
        akshare_client=_FakeAkshareClient(),
        yahoo_client=None,
        out_dir=tmp_path,
        catalog_path=catalog_path,
    )

    inventory_path = tmp_path / "source_inventory.jsonl"
    summary_path = tmp_path / "source_inventory_summary.json"

    assert inventory_path.exists()
    assert summary_path.exists()
    assert artifact.inventory_path == inventory_path

    # Period filter applied: 2023 record is dropped.
    contents = inventory_path.read_text()
    assert "2024-12-31" in contents
    assert "2023-12-31" not in contents
```

- [ ] **Step 2: 跑测试确认 fail**

Run: `uv run pytest tests/test_source_inventory_fetch.py::test_fetch_source_inventory_writes_period_filtered_artifacts -v`
Expected: FAIL with `cannot import name 'fetch_source_inventory'`.

- [ ] **Step 3: 实现 `fetch_source_inventory`**

追加到 `source_inventory_fetch.py`：

```python
import json
from typing import Iterable, Literal

from financial_report_llm_extractor.structured_sources.akshare_adapter import (
    AkshareAdapter,
)
from financial_report_llm_extractor.structured_sources.artifacts import (
    SourceArtifactStore,
    finalize_source_artifacts,
    write_source_inventory,
)
from financial_report_llm_extractor.structured_sources.field_inventory_summary import (
    build_provider_field_inventory_summary,
)
from financial_report_llm_extractor.structured_sources.real_source_validation import (
    AkshareLikeClient,
    YahooLikeClient,
)
from financial_report_llm_extractor.structured_sources.yahoo_adapter import (
    YahooAdapter,
)


ProviderName = Literal["akshare", "yahoo"]
MarketName = Literal["CN", "HK"]


@dataclass(frozen=True)
class SourceInventoryArtifact:
    inventory_path: Path
    summary_path: Path
    record_count: int


def fetch_source_inventory(
    *,
    company: str,
    period: PeriodSpec,
    market: MarketName,
    providers: tuple[ProviderName, ...],
    akshare_client: AkshareLikeClient | None,
    yahoo_client: YahooLikeClient | None,
    out_dir: Path,
    catalog_path: Path,
) -> SourceInventoryArtifact:
    """Live fetch from injected provider clients, filtered to PeriodSpec.

    Writes source_inventory.jsonl + source_inventory_summary.json to out_dir.
    Provider-by-provider: AKShare via AkshareAdapter, Yahoo via YahooAdapter.
    Period filter applied via select_records_for_period (fail-loud).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    store = SourceArtifactStore(out_dir / "source_artifacts")

    all_records: list[SourceInventoryRecord] = []

    if "akshare" in providers:
        if akshare_client is None:
            raise ValueError("akshare client required when 'akshare' in providers")
        akshare_records = _fetch_akshare_for_company(
            company=company, market=market,
            client=akshare_client, store=store,
        )
        all_records.extend(akshare_records)

    if "yahoo" in providers:
        if yahoo_client is None:
            raise ValueError("yahoo client required when 'yahoo' in providers")
        yahoo_records = _fetch_yahoo_for_company(
            company=company, market=market,
            client=yahoo_client, store=store,
        )
        all_records.extend(yahoo_records)

    filtered = select_records_for_period(tuple(all_records), period)

    inventory_path = out_dir / "source_inventory.jsonl"
    write_source_inventory(inventory_path, filtered)

    finalize_source_artifacts(store)

    catalog_summary = build_provider_field_inventory_summary(
        records=filtered, catalog_path=catalog_path,
    )
    summary_path = out_dir / "source_inventory_summary.json"
    summary_path.write_text(
        json.dumps(catalog_summary, indent=2, ensure_ascii=False, sort_keys=True)
    )

    return SourceInventoryArtifact(
        inventory_path=inventory_path,
        summary_path=summary_path,
        record_count=len(filtered),
    )


_STATEMENT_TYPES: tuple[str, ...] = ("income_statement", "balance_sheet", "cash_flow")


def _fetch_akshare_for_company(
    *, company: str, market: MarketName,
    client: AkshareLikeClient, store: SourceArtifactStore,
) -> tuple[SourceInventoryRecord, ...]:
    adapter = AkshareAdapter(client=client, artifact_store=store)
    if market == "CN":
        exchange = "SH" if company.startswith("6") else "SZ"
        records: list[SourceInventoryRecord] = []
        for st in _STATEMENT_TYPES:
            records.extend(adapter.fetch_cn_statement_inventory(
                ticker=company, exchange=exchange,
                statement_type=st, unit="yuan",
            ))
        return tuple(records)
    # market == "HK"
    records = []
    for st in _STATEMENT_TYPES:
        records.extend(adapter.fetch_hk_statement_inventory(
            ticker=company, statement_type=st, unit="raw",
        ))
    return tuple(records)


def _fetch_yahoo_for_company(
    *, company: str, market: MarketName,
    client: YahooLikeClient, store: SourceArtifactStore,
) -> tuple[SourceInventoryRecord, ...]:
    adapter = YahooAdapter(client=client, artifact_store=store)
    if market == "HK":
        ticker, currency = f"{company}.HK", "HKD"
    elif company.startswith("6"):
        ticker, currency = f"{company}.SS", "CNY"
    else:
        ticker, currency = f"{company}.SZ", "CNY"
    records: list[SourceInventoryRecord] = []
    for st in _STATEMENT_TYPES:
        records.extend(adapter.fetch_statement_inventory(
            ticker=ticker, market=market, statement_type=st,
            currency=currency, unit="raw",
        ))
    return tuple(records)
```

方法名 verified against `akshare_adapter.py:115, :233`、`yahoo_adapter.py:37`。如果有 import 或 type 错误，参考 `real_source_validation._fetch_sample_records:265-298` 的调用样式。

- [ ] **Step 4: （此步空操作 —— 上一步已直接使用真实 method 名；保留计步避免重号）**

如本地实际签名与上面不符，更新前先 `git diff src/financial_report_llm_extractor/structured_sources/akshare_adapter.py` 确认 adapter 是否已变化。

- [ ] **Step 5: 跑测试确认 PASS**

Run: `uv run pytest tests/test_source_inventory_fetch.py -v`
Expected: 5 passed。

- [ ] **Step 6: 写 CLI subcommand 测**

新建/追加到 `tests/test_cli.py`（如已存在则追加，否则新建）：

```python
def test_fetch_source_inventory_subcommand_dispatches_correctly(
    tmp_path: Path, monkeypatch
) -> None:
    """argv → run_fetch wiring 测，主体逻辑 mock 掉。"""
    from financial_report_llm_extractor.cli import main

    captured: dict[str, object] = {}

    def fake_runner(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        "financial_report_llm_extractor.cli._run_fetch_source_inventory",
        fake_runner,
    )

    main([
        "fetch-source-inventory",
        "--company", "600519",
        "--year", "2024",
        "--market", "CN",
        "--providers", "akshare",
        "--out", str(tmp_path),
        "--catalog", "field_catalog/turtle_v015_source_mapping_minimal.json",
    ])

    assert captured["company"] == "600519"
    assert captured["market"] == "CN"
    # YEAR shortcut expanded
    from datetime import date
    assert captured["period"].period_end == date(2024, 12, 31)


def test_fetch_source_inventory_subcommand_rejects_year_and_period_end_together(
    tmp_path: Path,
) -> None:
    from financial_report_llm_extractor.cli import main

    with pytest.raises(SystemExit):
        main([
            "fetch-source-inventory",
            "--company", "600519",
            "--year", "2024",
            "--period-end", "2024-12-31",
            "--market", "CN",
            "--providers", "akshare",
            "--out", str(tmp_path),
            "--catalog", "field_catalog/turtle_v015_source_mapping_minimal.json",
        ])
```

- [ ] **Step 7: 跑测试确认 fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL（subcommand 不存在）。

- [ ] **Step 8: 在 `cli.py` 加 `fetch-source-inventory` subparser**

定位 `cli.py` 的 subparsers 块（搜 `add_parser(`），追加：

```python
fetch_source_parser = subparsers.add_parser(
    "fetch-source-inventory",
    help="Live fetch AKShare/Yahoo data for a single (company, period).",
)
fetch_source_parser.add_argument("--company", required=True)
fetch_source_parser.add_argument("--year", type=int)
fetch_source_parser.add_argument("--period-end")
fetch_source_parser.add_argument("--report-type", default="annual")
fetch_source_parser.add_argument("--market", required=True, choices=["CN", "HK"])
fetch_source_parser.add_argument("--providers", default="akshare,yahoo")
fetch_source_parser.add_argument("--out", type=Path, required=True)
fetch_source_parser.add_argument(
    "--catalog", type=Path, required=True,
    help="Source mapping catalog JSON path.",
)
```

在 dispatch 段加：

```python
if args.command == "fetch-source-inventory":
    if args.year is not None and args.period_end is not None:
        parser.error("--year and --period-end are mutually exclusive")
    if args.year is not None:
        period = PeriodSpec.from_year(args.year)
    elif args.period_end is not None:
        period = PeriodSpec.from_period_end(args.period_end, args.report_type)
    else:
        parser.error("one of --year or --period-end is required")
    providers = tuple(p.strip() for p in args.providers.split(",") if p.strip())
    _run_fetch_source_inventory(
        company=args.company,
        period=period,
        market=args.market,
        providers=providers,
        out_dir=args.out,
        catalog_path=args.catalog,
    )
    return
```

加 helper（仅业务接线，不放业务逻辑）：

```python
def _run_fetch_source_inventory(
    *, company: str, period, market: str, providers, out_dir: Path, catalog_path: Path,
) -> None:
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        fetch_source_inventory,
    )
    from financial_report_llm_extractor.structured_sources.real_source_validation import (
        PandasAkshareClient,
        YFinanceStatementClient,
    )

    akshare_client = PandasAkshareClient() if "akshare" in providers else None
    yahoo_client = YFinanceStatementClient() if "yahoo" in providers else None

    artifact = fetch_source_inventory(
        company=company,
        period=period,
        market=market,
        providers=providers,
        akshare_client=akshare_client,
        yahoo_client=yahoo_client,
        out_dir=out_dir,
        catalog_path=catalog_path,
    )
    print(json.dumps({
        "inventory_path": str(artifact.inventory_path),
        "summary_path": str(artifact.summary_path),
        "record_count": artifact.record_count,
    }, indent=2))
```

加 import 顶部：`from financial_report_llm_extractor.structured_sources.source_inventory_fetch import PeriodSpec`。

- [ ] **Step 9: 跑测试确认 PASS**

Run: `uv run pytest tests/test_cli.py -v -k fetch_source_inventory`
Expected: 2 passed。

- [ ] **Step 10: 写 shell wrapper**

`scripts/run-fetch-source-inventory.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-.}"
cd "${ROOT}"

if [[ -z "${COMPANY:-}" ]]; then
  echo "COMPANY is required (e.g., COMPANY=600519)" >&2
  exit 2
fi
if [[ -z "${MARKET:-}" ]]; then
  echo "MARKET is required (CN or HK)" >&2
  exit 2
fi

CATALOG="${CATALOG:-field_catalog/turtle_v015_source_mapping_minimal.json}"
PROVIDERS="${PROVIDERS:-akshare,yahoo}"

if [[ -n "${YEAR:-}" && -n "${PERIOD_END:-}" ]]; then
  echo "YEAR and PERIOD_END are mutually exclusive" >&2
  exit 2
fi
if [[ -n "${YEAR:-}" ]]; then
  PERIOD_FLAG="--year ${YEAR}"
  PERIOD_LABEL="${YEAR}-12-31"
elif [[ -n "${PERIOD_END:-}" ]]; then
  PERIOD_FLAG="--period-end ${PERIOD_END} --report-type ${REPORT_TYPE:-annual}"
  PERIOD_LABEL="${PERIOD_END}"
else
  echo "YEAR or PERIOD_END is required" >&2
  exit 2
fi

OUT_DIR="${OUT_DIR:-tmp/runs/${COMPANY}_${PERIOD_LABEL}}"
mkdir -p "${OUT_DIR}"

uv run financial-report-llm-extractor fetch-source-inventory \
  --company "${COMPANY}" \
  ${PERIOD_FLAG} \
  --market "${MARKET}" \
  --providers "${PROVIDERS}" \
  --catalog "${CATALOG}" \
  --out "${OUT_DIR}"
```

```bash
chmod +x scripts/run-fetch-source-inventory.sh
```

- [ ] **Step 11: 跑整套验证**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src tests`
Expected: 全绿。

- [ ] **Step 12: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/source_inventory_fetch.py src/financial_report_llm_extractor/cli.py tests/test_source_inventory_fetch.py tests/test_cli.py scripts/run-fetch-source-inventory.sh
git commit -m "feat: fetch-source-inventory subcommand for per-(company, period) live fetch

New subcommand wraps real_source_validation adapter primitives with
period-filtered output. PeriodSpec carries period_end + report_type
so future TTM / interim extensions don't need a new shape.

Shell wrapper scripts/run-fetch-source-inventory.sh accepts env vars
(COMPANY, YEAR or PERIOD_END, MARKET, PROVIDERS, OUT_DIR, CATALOG)
with sensible defaults.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `classify_field` 桶级联纯函数

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/company_evaluation.py`
- Create: `tests/test_company_evaluation.py`

- [ ] **Step 1: 写 6 个桶分别一例的测**

新建 `tests/test_company_evaluation.py`：

```python
"""Tests for company_evaluation module: bucket cascade + orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def _make_export_item(
    field_id: str = "revenue",
    *,
    status: str = "present",
    selected_source: str | None = "akshare",
    conflict_classifications: tuple[str, ...] = (),
    review_notes: tuple[str, ...] = (),
    value_decimal: str = "100",
) -> Any:
    """Construct minimal SourceFirstExportItem for tests.

    Note: SourceFirstExportItem.value is `Decimal | None`, not `str`. Tests use
    Decimal(value_decimal) for present items.
    """
    from decimal import Decimal
    from financial_report_llm_extractor.structured_sources.export import (
        SourceFirstExportItem,
    )
    return SourceFirstExportItem(
        field_id=field_id,
        status=status,  # type: ignore[arg-type]
        selected_source=selected_source,
        value=Decimal(value_decimal) if status == "present" else None,
        currency="CNY",
        unit="raw",
        conflict_classifications=conflict_classifications,
        review_notes=review_notes,
    )


def _make_warning_item(category: str, *, field_id: str = "x") -> Any:
    from financial_report_llm_extractor.structured_sources.warning_classification import (
        WarningClassificationItem,
    )
    # 字段对应实际 dataclass —— 8 fields total.
    return WarningClassificationItem(
        field_id=field_id,
        category=category,  # type: ignore[arg-type]
        status="missing",
        reasons=(),
        review_notes=(),
        warnings=(),
        selected_source=None,
        candidate_sources=(),
        verification_required=False,
    )


def _make_mapping_entry(source_mode: str = "direct") -> Any:
    from financial_report_llm_extractor.structured_sources.catalog import (
        SourceMappingEntry,
    )
    return SourceMappingEntry(
        field_id="revenue",
        priority="P0",
        value_type="money",
        statement_type="income_statement",
        domain="income_statement",
        source_mode=source_mode,
        primary_route="akshare_direct",
        verification_status="expected",
        currency_requirement="required",
        unit_requirement="required",
        fallback_policy="pdf_allowed",
        source_aliases={},
        pdf_aliases=(),
    )


def test_classify_clean_present() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, reason = classify_field(
        export_item=_make_export_item(),
        warning_item=None,
        supplement_item=None,
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "clean_present"
    assert reason is None


def test_classify_unresolved_conflict() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, reason = classify_field(
        export_item=_make_export_item(conflict_classifications=("provider_value_mismatch",)),
        warning_item=None,
        supplement_item=None,
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "unresolved_conflict"
    assert "provider_value_mismatch" in (reason or "")


def test_classify_llm_supplement_present() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, _ = classify_field(
        export_item=_make_export_item(selected_source="llm"),
        warning_item=None,
        supplement_item=None,
        mapping_entry=_make_mapping_entry(source_mode="pdf_only"),
        pdf_provided=True,
    )

    assert bucket == "llm_supplement_present"


def test_classify_terminal_unverified_for_yahoo_definition_unverified() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, reason = classify_field(
        export_item=_make_export_item(status="missing", selected_source=None),
        warning_item=_make_warning_item("yahoo_definition_unverified"),
        supplement_item=None,
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "terminal_unverified"
    assert reason == "yahoo_definition_unverified"


def test_classify_not_in_scope_pdf_only_without_pdf() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, _ = classify_field(
        export_item=_make_export_item(status="missing", selected_source=None),
        warning_item=None,
        supplement_item=None,
        mapping_entry=_make_mapping_entry(source_mode="pdf_only"),
        pdf_provided=False,
    )

    assert bucket == "not_in_scope"


def test_classify_source_unavailable_default() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, reason = classify_field(
        export_item=_make_export_item(status="missing", selected_source=None),
        warning_item=_make_warning_item("source_unavailable"),
        supplement_item=None,
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "source_unavailable"
    assert reason == "source_unavailable"


def test_classify_cn_gross_profit_clean_not_terminal() -> None:
    """Review §"全局列表会错杀 CN clean": gross_profit clean via akshare_direct
    must land in clean_present, not terminal_unverified — even though it
    appears in the roadmap "Locked Terminal States" cohort that the original
    spec hardcoded."""
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, _ = classify_field(
        export_item=_make_export_item(field_id="gross_profit", selected_source="akshare"),
        warning_item=None,  # 关键：CN clean 时无 warning
        supplement_item=None,
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "clean_present"
```

- [ ] **Step 2: 跑测试确认 fail**

Run: `uv run pytest tests/test_company_evaluation.py -v`
Expected: 7 ImportErrors（模块不存在）。

- [ ] **Step 3: 实现 `classify_field`**

新建 `src/financial_report_llm_extractor/structured_sources/company_evaluation.py`：

```python
"""Per-company evaluation: bucket classification + summary + markdown.

Builds CompanyEvaluation from SourceFirstExportResult + WarningClassificationResult
+ optional LLM supplement. Bucket cascade is a pure function over per-(company,
field) inputs; no global hardcoded field lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingEntry,
)
from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportItem,
)
from financial_report_llm_extractor.structured_sources.warning_classification import (
    WarningClassificationItem,
)


BucketName = Literal[
    "clean_present",
    "unresolved_conflict",
    "llm_supplement_present",
    "terminal_unverified",
    "not_in_scope",
    "source_unavailable",
]


_TERMINAL_UNVERIFIED_CATEGORIES: frozenset[str] = frozenset({
    "yahoo_definition_unverified",
    "pdf_required",
    "pdf_verification_required",
    "mapping_expansion_required",
})


def classify_field(
    *,
    export_item: SourceFirstExportItem,
    warning_item: WarningClassificationItem | None,
    supplement_item: object | None,  # LLM evidence dict; placeholder for future shape
    mapping_entry: SourceMappingEntry,
    pdf_provided: bool,
) -> tuple[BucketName, str | None]:
    """Bucket cascade. First match wins. See spec §桶分类."""
    # Bucket 1: explicit conflict from policy report.
    if export_item.conflict_classifications:
        return ("unresolved_conflict", ",".join(export_item.conflict_classifications))

    # Bucket 2: LLM supplement merged in (provider_baseline_replay sets
    # selected_source="llm" only for supplement-merged fields).
    if export_item.status == "present" and export_item.selected_source == "llm":
        return ("llm_supplement_present", None)

    # Bucket 3: Clean present from a real source.
    if export_item.status == "present" and warning_item is None:
        return ("clean_present", None)

    # Bucket 4: Terminal unverified per warning_classification.
    if warning_item is not None and warning_item.category in _TERMINAL_UNVERIFIED_CATEGORIES:
        return ("terminal_unverified", warning_item.category)

    # Bucket 5: pdf_only catalog field, no PDF given → never attempted.
    if mapping_entry.source_mode == "pdf_only" and not pdf_provided:
        return ("not_in_scope", "pdf_only_without_pdf")

    # Bucket 6: source_unavailable (warning category or fallthrough).
    reason = warning_item.category if warning_item is not None else "missing"
    return ("source_unavailable", reason)
```

- [ ] **Step 4: 跑 7 个桶测确认全 PASS**

Run: `uv run pytest tests/test_company_evaluation.py -v`
Expected: 7 passed.

- [ ] **Step 5: 跑整套验证**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src tests`
Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/company_evaluation.py tests/test_company_evaluation.py
git commit -m "feat: company_evaluation classify_field 6-bucket cascade

Pure function over per-(company, field) inputs. Buckets derived from
WarningClassificationResult.items[<id>].category + export.status +
selected_source + mapping.source_mode + pdf_provided flag. No global
hardcoded field lists — CN gross_profit clean correctly lands in
clean_present even though it appears in roadmap 'Locked Terminal States'
cohort.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `build_company_evaluation` + `render_evaluation_markdown`

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/company_evaluation.py`
- Modify: `tests/test_company_evaluation.py`

- [ ] **Step 1: 写 `build_company_evaluation` 计数测**

追加到 `tests/test_company_evaluation.py`：

```python
def test_build_company_evaluation_counts_buckets_and_priorities() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        build_company_evaluation,
    )
    from financial_report_llm_extractor.structured_sources.export import (
        SourceFirstExportResult,
    )
    from financial_report_llm_extractor.structured_sources.warning_classification import (
        WarningClassificationResult,
    )

    catalog = _build_minimal_catalog()  # helper: 3 fields P0=revenue, P1=gross_profit, P3=dividend_plan
    taxonomy = _build_minimal_taxonomy()

    export = SourceFirstExportResult(items=(
        _make_export_item("revenue", status="present", selected_source="akshare"),
        _make_export_item("gross_profit", status="missing", selected_source=None),
        _make_export_item("dividend_plan", status="missing", selected_source=None),
    ))
    warning = WarningClassificationResult(items={
        "gross_profit": _make_warning_item("yahoo_definition_unverified"),
    })

    evaluation = build_company_evaluation(
        company="01113",
        period=PeriodSpec.from_year(2024),
        market="HK",
        export=export,
        warning_classification=warning,
        supplement=None,
        catalog=catalog,
        taxonomy=taxonomy,
        pdf_provided=False,
    )

    assert evaluation.by_bucket["clean_present"] == 1
    assert evaluation.by_bucket["terminal_unverified"] == 1
    assert evaluation.by_bucket["not_in_scope"] == 1  # dividend_plan pdf_only

    assert evaluation.by_priority["P0"]["clean_present"] == 1
    assert evaluation.by_priority["P1"]["terminal_unverified"] == 1
    assert evaluation.by_priority["P3"]["not_in_scope"] == 1
```

加 helpers `_build_minimal_catalog`、`_build_minimal_taxonomy`、import `PeriodSpec` 到测试顶部。

- [ ] **Step 2: 跑测试确认 fail**

Expected: ImportError on `build_company_evaluation`。

- [ ] **Step 3: 实现 `build_company_evaluation`**

追加到 `company_evaluation.py`：

```python
from datetime import datetime, timezone

from financial_report_llm_extractor.field_metadata import FieldTaxonomyCatalog
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
)
from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportResult,
)
from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
    PeriodSpec,
)
from financial_report_llm_extractor.structured_sources.warning_classification import (
    WarningClassificationResult,
)


from decimal import Decimal


@dataclass(frozen=True)
class CompanyFieldEvaluation:
    field_id: str
    bucket: BucketName
    selected_source: str | None
    value: Decimal | None      # 与 SourceFirstExportItem.value 同型
    currency: str | None
    unit: str | None
    reason: str | None


@dataclass(frozen=True)
class CompanyEvaluation:
    company: str
    period: PeriodSpec
    market: str
    generated_at: str
    fields: tuple[CompanyFieldEvaluation, ...]
    by_bucket: Mapping[BucketName, int]
    by_priority: Mapping[str, Mapping[BucketName, int]]


_ALL_BUCKETS: tuple[BucketName, ...] = (
    "clean_present", "unresolved_conflict", "llm_supplement_present",
    "terminal_unverified", "not_in_scope", "source_unavailable",
)


def build_company_evaluation(
    *,
    company: str,
    period: PeriodSpec,
    market: str,
    export: SourceFirstExportResult,
    warning_classification: WarningClassificationResult,
    supplement: dict[str, object] | None,
    catalog: SourceMappingCatalog,
    taxonomy: FieldTaxonomyCatalog,
    pdf_provided: bool,
) -> CompanyEvaluation:
    export_by_id = {item.field_id: item for item in export.items}
    warnings_by_id = warning_classification.items

    fields: list[CompanyFieldEvaluation] = []
    by_bucket: dict[BucketName, int] = {b: 0 for b in _ALL_BUCKETS}
    by_priority: dict[str, dict[BucketName, int]] = {}

    for field_id, mapping_entry in catalog.entries.items():
        export_item = export_by_id.get(field_id)
        if export_item is None:
            # Catalog entry with no export row → treat as missing.
            export_item = _missing_export_item(field_id)
        warning_item = warnings_by_id.get(field_id)
        supplement_item = (supplement or {}).get(field_id)

        bucket, reason = classify_field(
            export_item=export_item,
            warning_item=warning_item,
            supplement_item=supplement_item,
            mapping_entry=mapping_entry,
            pdf_provided=pdf_provided,
        )

        fields.append(CompanyFieldEvaluation(
            field_id=field_id,
            bucket=bucket,
            selected_source=export_item.selected_source,
            value=export_item.value,
            currency=export_item.currency,
            unit=export_item.unit,
            reason=reason,
        ))
        by_bucket[bucket] += 1
        priority = mapping_entry.priority
        by_priority.setdefault(priority, {b: 0 for b in _ALL_BUCKETS})
        by_priority[priority][bucket] += 1

    return CompanyEvaluation(
        company=company,
        period=period,
        market=market,
        generated_at=datetime.now(timezone.utc).isoformat(),
        fields=tuple(fields),
        by_bucket=by_bucket,
        by_priority=by_priority,
    )


def _missing_export_item(field_id: str) -> SourceFirstExportItem:
    return SourceFirstExportItem(
        field_id=field_id, status="missing", selected_source=None,
        value=None, currency=None, unit=None,
        conflict_classifications=(), review_notes=(),
    )
```

- [ ] **Step 4: 跑测试确认 PASS**

Run: `uv run pytest tests/test_company_evaluation.py::test_build_company_evaluation_counts_buckets_and_priorities -v`
Expected: 1 passed。

- [ ] **Step 5: 写 markdown 渲染测**

追加：

```python
def test_render_evaluation_markdown_lists_priority_bucket_grid() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        render_evaluation_markdown,
    )

    evaluation = _build_sample_evaluation()  # 用上述 helpers 造一个
    md = render_evaluation_markdown(evaluation)

    assert "01113" in md  # company
    assert "2024-12-31" in md  # period
    assert "| clean_present |" in md or "clean_present" in md
    assert "P0" in md and "P3" in md
    # 不出现 "% clean" 字面 —— 与 drift §177 一致
    assert "% clean" not in md.lower()
    assert "/ total" not in md.lower()
```

- [ ] **Step 6: 跑测试确认 fail**

Expected: ImportError。

- [ ] **Step 7: 实现 `render_evaluation_markdown`**

追加到 `company_evaluation.py`：

```python
def render_evaluation_markdown(evaluation: CompanyEvaluation) -> str:
    lines: list[str] = []
    lines.append(f"# Company Evaluation: {evaluation.company}")
    lines.append("")
    lines.append(f"- Period end: {evaluation.period.period_end.isoformat()}")
    lines.append(f"- Report type: {evaluation.period.report_type}")
    lines.append(f"- Market: {evaluation.market}")
    lines.append(f"- Generated at: {evaluation.generated_at}")
    lines.append("")
    lines.append("## Coverage by priority × bucket")
    lines.append("")

    header = "| Priority | " + " | ".join(_ALL_BUCKETS) + " |"
    sep = "|----------|" + "|".join(["---"] * len(_ALL_BUCKETS)) + "|"
    lines.append(header)
    lines.append(sep)
    for priority in sorted(evaluation.by_priority.keys()):
        row = evaluation.by_priority[priority]
        cells = " | ".join(str(row[b]) for b in _ALL_BUCKETS)
        lines.append(f"| {priority} | {cells} |")
    lines.append("")

    lines.append("## Per-field detail")
    lines.append("")
    lines.append("| Field | Bucket | Source | Value | Reason |")
    lines.append("|-------|--------|--------|-------|--------|")
    for f in evaluation.fields:
        marker = "**llm**" if f.selected_source == "llm" else (f.selected_source or "")
        reason = f.reason or ""
        value = f.value or ""
        lines.append(
            f"| {f.field_id} | {f.bucket} | {marker} | {value} | {reason} |"
        )
    return "\n".join(lines) + "\n"
```

- [ ] **Step 8: 跑测试确认 PASS**

Run: `uv run pytest tests/test_company_evaluation.py -v`
Expected: 全绿。

- [ ] **Step 9: 跑整套验证**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src tests`
Expected: 全绿。

- [ ] **Step 10: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/company_evaluation.py tests/test_company_evaluation.py
git commit -m "feat: build_company_evaluation summary + render_evaluation_markdown

Aggregates per-field bucket classification into priority × bucket grid.
Markdown renderer outputs full 6-bucket distribution per priority — no
'% clean' or 'X/N total' framing per drift analysis §177.

LLM-supplemented fields get **llm** marker in the source column so a
human reviewer can immediately distinguish them from provider-verified
values.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `run_company_evaluation` orchestrator + `evaluate-company` CLI

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/company_evaluation.py`
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `tests/test_company_evaluation.py`
- Modify: `tests/test_cli.py`
- Create: `scripts/run-evaluate-company.sh`

- [ ] **Step 1: 写 orchestrator end-to-end fake-stack 测**

追加到 `tests/test_company_evaluation.py`：

```python
def test_orchestrator_with_fake_stack_writes_all_artifacts(
    tmp_path: Path,
) -> None:
    """End-to-end with fake provider clients + fake LLM client + canned chunks."""
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        run_company_evaluation,
    )
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec, fetch_source_inventory,
    )
    from tests.test_source_inventory_fetch import _FakeAkshareClient

    # 1. Fake fetch
    fetch_source_inventory(
        company="600519",
        period=PeriodSpec.from_year(2024),
        market="CN",
        providers=("akshare",),
        akshare_client=_FakeAkshareClient(),
        yahoo_client=None,
        out_dir=tmp_path,
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
    )

    # 2. Run evaluation (no PDF → skip LLM step)
    evaluation = run_company_evaluation(
        company="600519",
        period=PeriodSpec.from_year(2024),
        market="CN",
        inventory_path=tmp_path / "source_inventory.jsonl",
        inventory_summary_path=tmp_path / "source_inventory_summary.json",
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        taxonomy_path=Path("field_catalog/turtle_v015_field_taxonomy.json"),
        pdf_path=None,
        llm_config_path=None,
        priorities=("P0", "P1", "P2", "P3"),
        out_dir=tmp_path,
    )

    assert (tmp_path / "source_first_export.json").exists()
    assert (tmp_path / "evaluation.json").exists()
    assert (tmp_path / "evaluation.md").exists()
    assert evaluation.company == "600519"
    # revenue should be clean_present after fake fetch
    revenue = next(f for f in evaluation.fields if f.field_id == "revenue")
    assert revenue.bucket == "clean_present"
```

- [ ] **Step 2: 写 policy_report wiring 测（review §"少了 build_source_policy_report"）**

```python
def test_orchestrator_wires_policy_report_so_conflicts_classified(
    tmp_path: Path,
) -> None:
    """A constructed AKShare↔Yahoo conflict must reach unresolved_conflict bucket.

    Without build_source_policy_report wiring, conflict_classifications stays
    empty and the bucket would silently mis-classify as clean_present.
    """
    # 构造同一字段两 provider 不同值的 inventory
    inventory_path = tmp_path / "source_inventory.jsonl"
    _write_conflict_inventory(inventory_path, field="OPERATE_INCOME",
                              akshare_value="100", yahoo_value="200")
    summary_path = tmp_path / "source_inventory_summary.json"
    summary_path.write_text("{}")

    evaluation = run_company_evaluation(
        company="600519",
        period=PeriodSpec.from_year(2024),
        market="CN",
        inventory_path=inventory_path,
        inventory_summary_path=summary_path,
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        taxonomy_path=Path("field_catalog/turtle_v015_field_taxonomy.json"),
        pdf_path=None,
        llm_config_path=None,
        priorities=("P0",),
        out_dir=tmp_path,
    )

    revenue = next(f for f in evaluation.fields if f.field_id == "revenue")
    assert revenue.bucket == "unresolved_conflict"
    assert revenue.reason and "conflict" in revenue.reason.lower()
```

实现 `_write_conflict_inventory` helper（写两条 different value records 到 jsonl）。

- [ ] **Step 3: 跑测试确认 fail**

Run: `uv run pytest tests/test_company_evaluation.py -v -k orchestrator`
Expected: ImportError on `run_company_evaluation`。

- [ ] **Step 4: 实现 `run_company_evaluation`**

追加到 `company_evaluation.py`：

```python
import json
from pathlib import Path

from financial_report_llm_extractor.field_metadata import load_field_taxonomy
from financial_report_llm_extractor.llm_field_extraction import JsonClient
from financial_report_llm_extractor.structured_sources.catalog import (
    load_source_mapping_catalog,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
)
from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
    evaluate_source_first_slice,
)


def run_company_evaluation(
    *,
    company: str,
    period: PeriodSpec,
    market: str,
    inventory_path: Path,
    inventory_summary_path: Path,
    catalog_path: Path,
    taxonomy_path: Path,
    pdf_path: Path | None,
    llm_config_path: Path | None,
    priorities: tuple[str, ...],
    out_dir: Path,
    json_client: JsonClient | None = None,
) -> CompanyEvaluation:
    """End-to-end: replay → optional LLM supplement → classify → write artifacts."""
    out_dir.mkdir(parents=True, exist_ok=True)
    catalog = load_source_mapping_catalog(catalog_path, priorities=priorities)
    taxonomy = load_field_taxonomy(taxonomy_path)

    records = read_source_inventory(inventory_path)

    pdf_provided = pdf_path is not None
    if pdf_provided and llm_config_path is not None:
        _run_llm_supplement_step(
            company=company, pdf_path=pdf_path, llm_config_path=llm_config_path,
            catalog=catalog, taxonomy=taxonomy,
            priorities=priorities, out_dir=out_dir,
            json_client=json_client,
        )

    slice_result = evaluate_source_first_slice(
        out_dir,
        catalog=catalog,
        taxonomy=taxonomy,
        records=records,
        company_id=company,
        market=market,
        hk_yahoo_trust_policy=None,
        provider_semantics_catalog=None,
    )
    export = slice_result["export_object"]  # SourceFirstExportResult (Task 0 NEW key)
    warning_classification = slice_result["warning_classification_object"]  # WarningClassificationResult

    evaluation = build_company_evaluation(
        company=company, period=period, market=market,
        export=export, warning_classification=warning_classification,
        supplement=None,  # supplement-merged values already inside export via _merge_llm_evidence_supplement
        catalog=catalog, taxonomy=taxonomy,
        pdf_provided=pdf_provided,
    )

    (out_dir / "evaluation.json").write_text(
        json.dumps(_evaluation_to_dict(evaluation), indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    (out_dir / "evaluation.md").write_text(
        render_evaluation_markdown(evaluation), encoding="utf-8",
    )
    return evaluation


# 直接复用现有 read_source_inventory（artifacts.py:259）—— 不要新写 from_dict。
from financial_report_llm_extractor.structured_sources.artifacts import (
    read_source_inventory,
)
# 不需要 _read_inventory_records helper；run_company_evaluation 直接：
#   records = read_source_inventory(inventory_path)


def _run_llm_supplement_step(
    *,
    company: str,
    pdf_path: Path,
    llm_config_path: Path,
    catalog,
    taxonomy,
    priorities: tuple[str, ...],
    out_dir: Path,
    json_client: JsonClient | None,
) -> None:
    """Mirror llm_extraction_batch._process_one_company minus batching."""
    from financial_report_llm_extractor.chunking import build_chunk_store
    from financial_report_llm_extractor.ingestion import ingest_pdf
    from financial_report_llm_extractor.llm_transport import (
        LlmTransportConfig, create_llm_client,
    )
    from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
        derive_targets, extract_for_chunks, load_chunks_jsonl,
        write_llm_evidence_supplement,
    )

    ingest_dir = out_dir / "ingest"
    chunks_path = ingest_dir / "chunks.jsonl"
    if not chunks_path.exists():
        ingest_dir.mkdir(parents=True, exist_ok=True)
        ingest_result = ingest_pdf(pdf_path, ingest_dir)
        build_chunk_store(
            ingest_result.pages_path, ingest_result.metadata_path,
            chunks_path=chunks_path,
        )
    chunks = load_chunks_jsonl(chunks_path)

    targets = derive_targets(catalog, taxonomy, priorities=priorities)
    if json_client is None:
        config = LlmTransportConfig.from_path(llm_config_path)
        json_client = create_llm_client(config)

    result = extract_for_chunks(
        targets=targets, chunks=chunks, client=json_client,
        out_dir=out_dir, pdf_path=pdf_path, company_id=company,
    )
    write_llm_evidence_supplement(result)


def _evaluation_to_dict(ev: CompanyEvaluation) -> dict[str, object]:
    return {
        "schema_version": "company-evaluation-v1",
        "company": ev.company,
        "period_end": ev.period.period_end.isoformat(),
        "report_type": ev.period.report_type,
        "market": ev.market,
        "generated_at": ev.generated_at,
        "summary": {
            "total_fields": len(ev.fields),
            "by_bucket": dict(ev.by_bucket),
            "by_priority": {p: dict(b) for p, b in ev.by_priority.items()},
        },
        "fields": {
            f.field_id: {
                "bucket": f.bucket,
                "selected_source": f.selected_source,
                "value": str(f.value) if f.value is not None else None,
                "currency": f.currency,
                "unit": f.unit,
                "reason": f.reason,
            }
            for f in ev.fields
        },
    }
```

注意：本步骤依赖 Task 0 已扩展 `evaluate_source_first_slice` 返回 dict 含 `export_object` 与 `warning_classification_object` 键。Task 0 Step 1 的回归测已锁定这两个 key 的存在。

- [ ] **Step 5: 跑测试确认 PASS**

Run: `uv run pytest tests/test_company_evaluation.py -v`
Expected: 全绿。如有键名 mismatch，调整 dict access。

- [ ] **Step 6: 写 evaluate-company CLI 测**

追加到 `tests/test_cli.py`：

```python
def test_evaluate_company_subcommand_dispatches_correctly(
    tmp_path: Path, monkeypatch
) -> None:
    from financial_report_llm_extractor.cli import main

    captured: dict[str, object] = {}

    def fake_runner(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        "financial_report_llm_extractor.cli._run_evaluate_company",
        fake_runner,
    )

    inv = tmp_path / "source_inventory.jsonl"
    inv.write_text("")
    inv_summary = tmp_path / "source_inventory_summary.json"
    inv_summary.write_text("{}")

    main([
        "evaluate-company",
        "--company", "600519",
        "--year", "2024",
        "--market", "CN",
        "--inventory", str(inv),
        "--inventory-summary", str(inv_summary),
        "--catalog", "field_catalog/turtle_v015_source_mapping_minimal.json",
        "--taxonomy", "field_catalog/turtle_v015_field_taxonomy.json",
        "--out", str(tmp_path),
    ])

    assert captured["company"] == "600519"
    assert captured["market"] == "CN"
    assert captured["pdf_path"] is None
```

- [ ] **Step 7: 跑测试确认 fail**

Expected: 命令不存在。

- [ ] **Step 8: 在 `cli.py` 加 `evaluate-company` subparser + dispatch**

```python
evaluate_parser = subparsers.add_parser(
    "evaluate-company",
    help="Per-(company, period) source-first + optional LLM evaluation.",
)
evaluate_parser.add_argument("--company", required=True)
evaluate_parser.add_argument("--year", type=int)
evaluate_parser.add_argument("--period-end")
evaluate_parser.add_argument("--report-type", default="annual")
evaluate_parser.add_argument("--market", required=True, choices=["CN", "HK"])
evaluate_parser.add_argument("--inventory", type=Path, required=True)
evaluate_parser.add_argument("--inventory-summary", type=Path, required=True)
evaluate_parser.add_argument("--catalog", type=Path, required=True)
evaluate_parser.add_argument("--taxonomy", type=Path, required=True)
evaluate_parser.add_argument("--pdf", type=Path)
evaluate_parser.add_argument("--llm-config", type=Path)
evaluate_parser.add_argument("--priorities", default="P0,P1,P2,P3")
evaluate_parser.add_argument("--out", type=Path, required=True)
```

dispatch：

```python
if args.command == "evaluate-company":
    if args.year is not None and args.period_end is not None:
        parser.error("--year and --period-end are mutually exclusive")
    if args.year is not None:
        period = PeriodSpec.from_year(args.year)
    elif args.period_end is not None:
        period = PeriodSpec.from_period_end(args.period_end, args.report_type)
    else:
        parser.error("one of --year or --period-end is required")
    priorities = tuple(p.strip() for p in args.priorities.split(",") if p.strip())
    _run_evaluate_company(
        company=args.company, period=period, market=args.market,
        inventory_path=args.inventory,
        inventory_summary_path=args.inventory_summary,
        catalog_path=args.catalog, taxonomy_path=args.taxonomy,
        pdf_path=args.pdf, llm_config_path=args.llm_config,
        priorities=priorities, out_dir=args.out,
    )
    return
```

加 helper：

```python
def _run_evaluate_company(**kwargs: object) -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        run_company_evaluation,
    )
    evaluation = run_company_evaluation(**kwargs)  # type: ignore[arg-type]
    print(json.dumps({
        "company": evaluation.company,
        "summary": dict(evaluation.by_bucket),
    }, indent=2))
```

- [ ] **Step 9: 跑测试确认 PASS**

Run: `uv run pytest tests/test_cli.py -v -k evaluate_company`
Expected: PASS。

- [ ] **Step 10: 写 shell wrapper**

`scripts/run-evaluate-company.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-.}"
cd "${ROOT}"

if [[ -z "${COMPANY:-}" ]]; then
  echo "COMPANY is required" >&2; exit 2
fi
if [[ -z "${MARKET:-}" ]]; then
  echo "MARKET is required (CN or HK)" >&2; exit 2
fi

CATALOG="${CATALOG:-field_catalog/turtle_v015_source_mapping_minimal.json}"
TAXONOMY="${TAXONOMY:-field_catalog/turtle_v015_field_taxonomy.json}"
PRIORITIES="${PRIORITIES:-P0,P1,P2,P3}"

if [[ -n "${YEAR:-}" && -n "${PERIOD_END:-}" ]]; then
  echo "YEAR and PERIOD_END are mutually exclusive" >&2; exit 2
fi
if [[ -n "${YEAR:-}" ]]; then
  PERIOD_FLAG="--year ${YEAR}"
  PERIOD_LABEL="${YEAR}-12-31"
elif [[ -n "${PERIOD_END:-}" ]]; then
  PERIOD_FLAG="--period-end ${PERIOD_END} --report-type ${REPORT_TYPE:-annual}"
  PERIOD_LABEL="${PERIOD_END}"
else
  echo "YEAR or PERIOD_END is required" >&2; exit 2
fi

OUT_DIR="${OUT_DIR:-tmp/runs/${COMPANY}_${PERIOD_LABEL}}"
INVENTORY="${INVENTORY:-${OUT_DIR}/source_inventory.jsonl}"
INVENTORY_SUMMARY="${INVENTORY_SUMMARY:-${OUT_DIR}/source_inventory_summary.json}"

PDF_FLAG=""
if [[ -n "${PDF_PATH:-}" ]]; then
  PDF_FLAG="--pdf ${PDF_PATH}"
fi
LLM_FLAG=""
if [[ -n "${LLM_CONFIG:-}" ]]; then
  LLM_FLAG="--llm-config ${LLM_CONFIG}"
fi

mkdir -p "${OUT_DIR}"

uv run financial-report-llm-extractor evaluate-company \
  --company "${COMPANY}" \
  ${PERIOD_FLAG} \
  --market "${MARKET}" \
  --inventory "${INVENTORY}" \
  --inventory-summary "${INVENTORY_SUMMARY}" \
  --catalog "${CATALOG}" \
  --taxonomy "${TAXONOMY}" \
  ${PDF_FLAG} \
  ${LLM_FLAG} \
  --priorities "${PRIORITIES}" \
  --out "${OUT_DIR}"
```

```bash
chmod +x scripts/run-evaluate-company.sh
```

- [ ] **Step 11: 跑整套验证**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src tests`
Expected: 全绿 (~510 tests)。

- [ ] **Step 12: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/company_evaluation.py src/financial_report_llm_extractor/cli.py tests/test_company_evaluation.py tests/test_cli.py scripts/run-evaluate-company.sh
git commit -m "feat: evaluate-company subcommand orchestrator + shell wrapper

Wires evaluate_source_first_slice (Task 0) + optional ingest+chunk+LLM
supplement (mirroring _process_one_company) + classify_field +
build_company_evaluation. Writes evaluation.json + evaluation.md to
out_dir alongside provider artifacts.

Shell wrapper accepts COMPANY, YEAR or PERIOD_END, MARKET, PDF_PATH,
LLM_CONFIG, OUT_DIR with sensible defaults that align with
fetch-source-inventory's output layout (tmp/runs/<company>_<period>/).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`

- [ ] **Step 1: 更新 CLAUDE.md 阶段表 + 下一步指针**

在阶段表（line 50-52 附近）追加：

```markdown
| evaluate-company | `structured_sources/source_inventory_fetch.py` + `company_evaluation.py` | 单 (公司, 期末) 验证 orchestrator：fetch-source-inventory + evaluate-company 两步 CLI；输出 source_first_export.json + 可选 llm_evidence_supplement.json + evaluation.json + evaluation.md |
```

修改"下一步"指针（line 80）："...下一步候选：合并到 main..." 中加入"用 `evaluate-company` 跑回归"。

- [ ] **Step 2: 更新 roadmap §6 Validation Commands**

在 `## 6. Validation Commands` 段加：

```markdown
### Per-(company, period) end-to-end validation

```bash
# Step 1: live fetch (env-driven shell wrapper)
COMPANY=600519 YEAR=2024 MARKET=CN PROVIDERS=akshare \
  scripts/run-fetch-source-inventory.sh

# Step 2: evaluate (deterministic from cache; auto-runs LLM if PDF given)
COMPANY=600519 YEAR=2024 MARKET=CN \
  PDF_PATH=downloads/cn_stocks/600519/annual/2024_年度报告.pdf \
  LLM_CONFIG=tmp/llm_configs/deepseek.json \
  scripts/run-evaluate-company.sh
```

Outputs land in `tmp/runs/${COMPANY}_${PERIOD_END}/`:
`source_inventory.jsonl`, `source_inventory_summary.json`,
`source_first_export.json`, `llm_evidence_supplement.json` (if PDF set),
`evaluation.json`, `evaluation.md`.

`evaluate-company` 与 `replay-provider-baseline` 的边界：
- `evaluate-company`：单 (公司, 期末)，可选 live 或 fixture，含 LLM supplement，输出 bucket-classified evaluation
- `replay-provider-baseline`：多公司 batch，仅从已有 fixture replay，输出 multi-slice export
```

- [ ] **Step 3: 跑整套验证**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src tests`
Expected: 全绿（doc-only 改动不影响）。

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md
git commit -m "docs: add evaluate-company to CLAUDE.md + roadmap §6 validation commands

CLAUDE.md phase table gains the orchestrator entry; '下一步' pointer
mentions evaluate-company as the regression check after catalog /
policy / LLM-prompt changes.

Roadmap §6 documents the two-step env-driven workflow plus the
evaluate-company vs replay-provider-baseline boundary so future Claude
sessions don't reach for the wrong command.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Acceptance Criteria

- All 6 tasks completed in order; each commit independently green (`pytest + ruff + mypy`).
- ≥ 11 new unit tests added (counted in Task 1-5).
- `replay-provider-baseline` regression test passes (Task 0 ensures behavior unchanged).
- `evaluate-company` end-to-end demo on 600519 / 2024 produces all 4 artifacts (gated by `REAL_SOURCE_VALIDATION=1` + DeepSeek key — manual smoke after Task 6).
- 600519 CN `gross_profit` evaluation.json bucket = `clean_present` (not `terminal_unverified`) — verified by `test_classify_cn_gross_profit_clean_not_terminal`.
- `evaluation.md` contains no "% clean" or "X / total" framing — verified by `test_render_evaluation_markdown_lists_priority_bucket_grid`.
- CLAUDE.md and roadmap §6 updated.
