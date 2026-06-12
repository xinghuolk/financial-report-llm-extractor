"""Per-(company, period) live source inventory fetch for evaluate-company.

Wraps real_source_validation adapter primitives with a (company, period_end,
market)-keyed sample builder, so each call produces a single-period
source_inventory.jsonl + summary in a deterministic out_dir.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
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
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
    load_source_mapping_catalog,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
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


def _preferred_provider_first(
    providers: tuple[str, ...], primary_route: str
) -> tuple[str, ...]:
    """Order providers so the primary_route provider is tried first."""
    if "yahoo" in primary_route and "yahoo" in providers:
        return ("yahoo",) + tuple(p for p in providers if p != "yahoo")
    if "akshare" in primary_route and "akshare" in providers:
        return ("akshare",) + tuple(p for p in providers if p != "akshare")
    return providers


def synthesize_absence_zero_records(
    all_records: tuple[SourceInventoryRecord, ...],
    period: PeriodSpec,
    catalog: SourceMappingCatalog,
) -> list[SourceInventoryRecord]:
    """Emit verified-0 records for sparse lines absent in the target period.

    Standardized-template providers encode statements sparsely: a non-zero
    line is emitted, a zero/none year is omitted entirely. For a field flagged
    ``absence_means_zero``, an absent target-period row is a genuine zero —
    but ONLY when the provider demonstrably tracks the line for THIS issuer
    (it reported the line in some other period) and the statement itself is
    present for the target period. This multi-period gate distinguishes
    "tracked but zero this year" (synthesize 0) from "provider never tracks
    this line" (leave missing — avoids false zeros for issuers that did buy
    back but whose provider schema lacks the line).

    Operates on the full multi-period ``all_records`` BEFORE period filtering,
    which is the only layer where the historical evidence is visible.
    """
    target = period.period_end.isoformat()
    synthesized: list[SourceInventoryRecord] = []
    for entry in catalog.entries.values():
        if not entry.absence_means_zero:
            continue
        providers = _preferred_provider_first(
            tuple(entry.source_aliases.keys()), entry.primary_route
        )
        for provider in providers:
            aliases = entry.source_aliases.get(provider, ())
            if not aliases:
                continue
            tracked = tuple(
                r
                for r in all_records
                if r.source == provider
                and r.source_status == "present"
                and (
                    r.raw_field_name in aliases
                    or (r.raw_field_code is not None and r.raw_field_code in aliases)
                )
            )
            if not tracked:
                continue
            if any(r.period is not None and r.period.startswith(target) for r in tracked):
                # Provider reported a real value this period — use it, no synth.
                break
            siblings = tuple(
                r
                for r in all_records
                if r.source == provider
                and r.source_status == "present"
                and r.statement_type == entry.statement_type
                and r.period is not None
                and r.period.startswith(target)
            )
            if not siblings:
                continue
            sibling = siblings[0]
            template = tracked[0]
            synthesized.append(
                SourceInventoryRecord(
                    source=template.source,
                    market=sibling.market,
                    ticker=sibling.ticker,
                    statement_type=entry.statement_type,
                    period=target,
                    raw_field_name=template.raw_field_name,
                    raw_value="0",
                    parsed_numeric_value=Decimal("0"),
                    value_type=entry.value_type,
                    source_status="present",
                    report_type=sibling.report_type,
                    fiscal_year=sibling.fiscal_year,
                    scope=sibling.scope,
                    account_standard=sibling.account_standard,
                    currency=sibling.currency,
                    unit=sibling.unit,
                    raw_field_code=template.raw_field_code,
                    source_evidence=(
                        SourceEvidence(
                            source=template.source,
                            adapter=template.source,
                            function="absence_means_zero",
                            artifact_id=(
                                sibling.source_evidence[0].artifact_id
                                if sibling.source_evidence
                                else f"{provider}_{entry.statement_type}"
                            ),
                            raw_record_id=(
                                f"{sibling.ticker}:{sibling.market}:"
                                f"{entry.statement_type}:{target}:"
                                f"{template.raw_field_name}:absence_zero"
                            ),
                            raw_field_name=template.raw_field_name,
                            raw_field_code=template.raw_field_code,
                        ),
                    ),
                )
            )
            break
    return synthesized


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
    cache_root: Path | None = None,
    ttl_hours: int = 24,
) -> SourceInventoryArtifact:
    """Live fetch from injected provider clients, filtered to PeriodSpec.

    Writes source_inventory.jsonl + source_inventory_summary.json to out_dir.
    Provider-by-provider: AKShare via AkshareAdapter, Yahoo via YahooAdapter.
    Period filter applied via select_records_for_period (fail-loud).

    The catalog_path is currently informational (used to scope summary
    artifact naming via sample_set); future Task 3+ work may introduce
    catalog-driven filtering.

    If cache_root is given, per-provider results are cached under
    cache_root/provider/{company}_{period_end}.json with ttl_hours TTL.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_root = out_dir / "source_artifacts"
    store = SourceArtifactStore(artifact_root)

    cache_key = period.period_end.isoformat() if cache_root is not None else None

    all_records: list[SourceInventoryRecord] = []

    if "akshare" in providers:
        if akshare_client is None:
            raise ValueError("akshare client required when 'akshare' in providers")
        akshare_records = _fetch_akshare_for_company(
            company=company,
            market=market,
            client=akshare_client,
            store=store,
            cache_root=cache_root,
            cache_key=cache_key,
            ttl_hours=ttl_hours,
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
            cache_root=cache_root,
            cache_key=cache_key,
            ttl_hours=ttl_hours,
        )
        all_records.extend(yahoo_records)

    # Sparse buyback / absence-means-zero synthesis: emit verified-0 records for
    # fields whose provider tracks the line historically but omits it this
    # period. Runs on the multi-period all_records BEFORE filtering.
    catalog = load_source_mapping_catalog(
        catalog_path, priorities=("P0", "P1", "P2", "P3", "P4")
    )
    all_records.extend(
        synthesize_absence_zero_records(tuple(all_records), period, catalog)
    )

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
    cache_root: Path | None = None,
    cache_key: str | None = None,
    ttl_hours: int = 24,
) -> tuple[SourceInventoryRecord, ...]:
    if cache_root is not None and cache_key is not None:
        from financial_report_llm_extractor.cache.provider_cache import (
            cache_get_with_artifacts,
        )
        from financial_report_llm_extractor.structured_sources.artifacts import (
            _record_from_jsonable,
        )
        cached = cache_get_with_artifacts(
            cache_root=cache_root, provider="akshare",
            company=company, period_end=cache_key,
            ttl_hours=ttl_hours,
        )
        if cached is not None:
            cached_records, cached_artifacts = cached
            try:
                records = tuple(
                    _record_from_jsonable(payload, line_number=i + 1)
                    for i, payload in enumerate(cached_records)
                )
            except (ValueError, KeyError, TypeError) as exc:
                print(
                    f"warning: akshare cache deserialize failed ({exc}); re-fetching",
                    file=sys.stderr,
                )
            else:
                # Replay artifacts into store so finalize_source_artifacts passes
                for artifact_entry in cached_artifacts:
                    store.write_json(
                        source=artifact_entry["source"],
                        artifact_id=artifact_entry["artifact_id"],
                        payload=artifact_entry["payload"],
                    )
                return records

    # Capture pre-fetch artifact count to identify this helper's contributions
    pre_len = len(store.artifacts)

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
        records_to_cache = tuple(cn_records)
    else:
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
        records_to_cache = tuple(hk_records)

    if cache_root is not None and cache_key is not None:
        from financial_report_llm_extractor.cache.provider_cache import (
            cache_put_with_artifacts,
        )
        from financial_report_llm_extractor.structured_sources.artifacts import (
            _record_to_jsonable,
        )
        new_artifacts = store.artifacts[pre_len:]
        artifact_entries = []
        for a in new_artifacts:
            blob_path = store.root / a.path
            artifact_entries.append({
                "source": a.source,
                "artifact_id": a.artifact_id,
                "payload": json.loads(blob_path.read_text(encoding="utf-8")),
            })
        cache_put_with_artifacts(
            cache_root=cache_root, provider="akshare",
            company=company, period_end=cache_key,
            records=[_record_to_jsonable(r) for r in records_to_cache],
            artifacts=artifact_entries,
        )

    return records_to_cache


def _fetch_yahoo_for_company(
    *,
    company: str,
    market: MarketName,
    client: YahooLikeClient,
    store: SourceArtifactStore,
    cache_root: Path | None = None,
    cache_key: str | None = None,
    ttl_hours: int = 24,
) -> tuple[SourceInventoryRecord, ...]:
    if cache_root is not None and cache_key is not None:
        from financial_report_llm_extractor.cache.provider_cache import (
            cache_get_with_artifacts,
        )
        from financial_report_llm_extractor.structured_sources.artifacts import (
            _record_from_jsonable,
        )
        cached = cache_get_with_artifacts(
            cache_root=cache_root, provider="yahoo",
            company=company, period_end=cache_key,
            ttl_hours=ttl_hours,
        )
        if cached is not None:
            cached_records, cached_artifacts = cached
            try:
                records = tuple(
                    _record_from_jsonable(payload, line_number=i + 1)
                    for i, payload in enumerate(cached_records)
                )
            except (ValueError, KeyError, TypeError) as exc:
                print(
                    f"warning: yahoo cache deserialize failed ({exc}); re-fetching",
                    file=sys.stderr,
                )
            else:
                # Replay artifacts into store so finalize_source_artifacts passes
                for artifact_entry in cached_artifacts:
                    store.write_json(
                        source=artifact_entry["source"],
                        artifact_id=artifact_entry["artifact_id"],
                        payload=artifact_entry["payload"],
                    )
                return records

    # Capture pre-fetch artifact count to identify this helper's contributions
    pre_len = len(store.artifacts)

    adapter = YahooAdapter(client=client, artifact_store=store)
    ticker: str
    currency: Literal["CNY", "HKD", "USD"]
    if market == "HK":
        ticker = f"{_yahoo_hk_ticker(company)}.HK"
        currency = hk_issuer_financial_currency(company)
    elif company.startswith("6"):
        ticker, currency = f"{company}.SS", "CNY"
    else:
        ticker, currency = f"{company}.SZ", "CNY"
    records_list: list[SourceInventoryRecord] = []
    for st in _STATEMENT_TYPES:
        records_list.extend(
            adapter.fetch_statement_inventory(
                ticker=ticker,
                market=market,
                statement_type=st,
                currency=currency,
                unit="raw",
            )
        )
    records_to_cache = tuple(records_list)

    if cache_root is not None and cache_key is not None:
        from financial_report_llm_extractor.cache.provider_cache import (
            cache_put_with_artifacts,
        )
        from financial_report_llm_extractor.structured_sources.artifacts import (
            _record_to_jsonable,
        )
        new_artifacts = store.artifacts[pre_len:]
        artifact_entries = []
        for a in new_artifacts:
            blob_path = store.root / a.path
            artifact_entries.append({
                "source": a.source,
                "artifact_id": a.artifact_id,
                "payload": json.loads(blob_path.read_text(encoding="utf-8")),
            })
        cache_put_with_artifacts(
            cache_root=cache_root, provider="yahoo",
            company=company, period_end=cache_key,
            records=[_record_to_jsonable(r) for r in records_to_cache],
            artifacts=artifact_entries,
        )

    return records_to_cache


def _yahoo_hk_ticker(company: str) -> str:
    stripped = company.lstrip("0") or "0"
    return stripped.zfill(4)


# Phase HK-B.5.1: HK issuer-to-financial-currency map. Yahoo HK historically
# hardcoded currency=HKD on every HK record (the trading-market currency for
# the listed share), but issuers report financials in their functional
# reporting currency which often differs (Xiaomi → CNY, Yum China → USD).
# This map stamps YAHOO inventory records with the issuer's reporting
# currency so downstream consumers get correct-currency claims.
#
# 2026-06-12: the map must NOT be applied to the AKShare HK path — the
# EastMoney feed delivers CNY-converted values for every issuer (full-cohort
# verification in docs/gates/2026-06-12-gross-profit-divergence-
# investigation.md), so AKShare HK records are stamped CNY.
#
# Source of truth: PDF spot-check from each issuer's most recent annual
# report (see docs/phase_hk_b_5_recon.md).
#
# Unknown issuers fall back to "HKD" — the historical default. This matches
# pre-Phase-HK-B.5.1 behavior for any HK ticker not in the map and avoids
# silently changing currency for cohorts that haven't been spot-checked.
# Future work: live-detect via yfinance.Ticker.info.financialCurrency
# instead of relying on a manual map; tracked as a §7 follow-up.
HK_ISSUER_FINANCIAL_CURRENCY: dict[str, Literal["CNY", "HKD", "USD"]] = {
    "00001": "HKD",  # HSBC Holdings / CK Hutchison — HK$ reporter
    "01113": "HKD",  # CK Asset Holdings — HK$ reporter (property)
    "01810": "CNY",  # Xiaomi — RMB reporter
    "02498": "CNY",  # RMB reporter
    "06862": "CNY",  # RMB reporter
    "09987": "USD",  # Yum China — US$ reporter (US-domiciled, HK-listed)
    "00392": "CNY",  # Beijing Enterprises Holdings — RMB reporter (functional currency changed from HKD to RMB)
    "02669": "CNY",  # China Overseas Property Services — RMB reporter
    "03320": "CNY",  # China Resources Pharmaceutical — RMB reporter
}


def hk_issuer_financial_currency(company: str) -> Literal["CNY", "HKD", "USD"]:
    """Return the issuer's financial-statement reporting currency.

    See `HK_ISSUER_FINANCIAL_CURRENCY` for the spot-checked map. Unknown
    issuers default to HKD (preserves pre-Phase-HK-B.5.1 behavior).
    """
    return HK_ISSUER_FINANCIAL_CURRENCY.get(company, "HKD")
