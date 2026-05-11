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

from financial_report_llm_extractor.structured_sources.akshare_adapter import (
    AkshareAdapter,
)
from financial_report_llm_extractor.structured_sources.artifacts import (
    SourceArtifactStore,
    finalize_source_artifacts,
    write_source_inventory,
)
from financial_report_llm_extractor.structured_sources.field_inventory_summary import (
    write_provider_field_inventory_summary,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
)
from financial_report_llm_extractor.structured_sources.real_source_validation import (
    AkshareLikeClient,
    YahooLikeClient,
)
from financial_report_llm_extractor.structured_sources.yahoo_adapter import (
    YahooAdapter,
)

ReportType = Literal["annual", "half_year", "quarterly", "ttm"]
ProviderName = Literal["akshare", "yahoo"]
MarketName = Literal["CN", "HK"]


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


@dataclass(frozen=True)
class SourceInventoryArtifact:
    inventory_path: Path
    summary_path: Path
    record_count: int


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


_STATEMENT_TYPES: tuple[str, ...] = ("income_statement", "balance_sheet", "cash_flow")


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

    The catalog_path is currently informational (used to scope summary
    artifact naming via sample_set); future Task 3+ work may introduce
    catalog-driven filtering.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_root = out_dir / "source_artifacts"
    store = SourceArtifactStore(artifact_root)

    all_records: list[SourceInventoryRecord] = []

    if "akshare" in providers:
        if akshare_client is None:
            raise ValueError("akshare client required when 'akshare' in providers")
        akshare_records = _fetch_akshare_for_company(
            company=company,
            market=market,
            client=akshare_client,
            store=store,
        )
        all_records.extend(akshare_records)

    if "yahoo" in providers:
        if yahoo_client is None:
            raise ValueError("yahoo client required when 'yahoo' in providers")
        yahoo_records = _fetch_yahoo_for_company(
            company=company,
            market=market,
            client=yahoo_client,
            store=store,
        )
        all_records.extend(yahoo_records)

    filtered = select_records_for_period(tuple(all_records), period)

    inventory_path = out_dir / "source_inventory.jsonl"
    write_source_inventory(inventory_path, filtered)

    manifest = finalize_source_artifacts(
        artifact_root=artifact_root,
        artifacts=store.artifacts,
        records=filtered,
        manifest_path=out_dir / "source_artifact_manifest.json",
    )

    sample_set = (
        f"fetch_source_inventory:{company}:{period.period_end.isoformat()}:"
        f"{catalog_path.stem}"
    )
    summary_path = out_dir / "source_inventory_summary.json"
    write_provider_field_inventory_summary(
        summary_path,
        records=filtered,
        sample_set=sample_set,
        source_artifact_count=len(manifest.artifacts),
    )

    return SourceInventoryArtifact(
        inventory_path=inventory_path,
        summary_path=summary_path,
        record_count=len(filtered),
    )


def _fetch_akshare_for_company(
    *,
    company: str,
    market: MarketName,
    client: AkshareLikeClient,
    store: SourceArtifactStore,
) -> tuple[SourceInventoryRecord, ...]:
    adapter = AkshareAdapter(client=client, artifact_store=store)
    if market == "CN":
        exchange = "SH" if company.startswith("6") else "SZ"
        cn_records: list[SourceInventoryRecord] = []
        for st in _STATEMENT_TYPES:
            cn_records.extend(
                adapter.fetch_cn_statement_inventory(
                    ticker=company,
                    exchange=exchange,
                    statement_type=st,
                    unit="yuan",
                )
            )
        return tuple(cn_records)
    # market == "HK"
    hk_records: list[SourceInventoryRecord] = []
    for st in _STATEMENT_TYPES:
        hk_records.extend(
            adapter.fetch_hk_statement_inventory(
                ticker=company,
                statement_type=st,
                unit="raw",
            )
        )
    return tuple(hk_records)


def _fetch_yahoo_for_company(
    *,
    company: str,
    market: MarketName,
    client: YahooLikeClient,
    store: SourceArtifactStore,
) -> tuple[SourceInventoryRecord, ...]:
    adapter = YahooAdapter(client=client, artifact_store=store)
    ticker: str
    currency: Literal["CNY", "HKD"]
    if market == "HK":
        ticker, currency = f"{_yahoo_hk_ticker(company)}.HK", "HKD"
    elif company.startswith("6"):
        ticker, currency = f"{company}.SS", "CNY"
    else:
        ticker, currency = f"{company}.SZ", "CNY"
    records: list[SourceInventoryRecord] = []
    for st in _STATEMENT_TYPES:
        records.extend(
            adapter.fetch_statement_inventory(
                ticker=ticker,
                market=market,
                statement_type=st,
                currency=currency,
                unit="raw",
            )
        )
    return tuple(records)


def _yahoo_hk_ticker(company: str) -> str:
    stripped = company.lstrip("0") or "0"
    return stripped.zfill(4)
