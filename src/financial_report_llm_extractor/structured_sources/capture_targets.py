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
    # AKShare HK capture targets are stamped CNY — the EastMoney feed
    # delivers CNY-converted values for every issuer regardless of its
    # reporting currency (docs/gates/2026-06-12-gross-profit-divergence-
    # investigation.md). The Yahoo HK targets below keep the issuer label.
    *_targets_for_company(
        provider="akshare",
        company_id="00001",
        provider_ticker="00001",
        market="HK",
        currency="CNY",
        unit="raw",
    ),
    *_targets_for_company(
        provider="akshare",
        company_id="01113",
        provider_ticker="01113",
        market="HK",
        currency="CNY",
        unit="raw",
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
    providers: tuple[ProviderName, ...] = ("akshare", "yahoo"),
) -> tuple[ProviderCaptureTarget, ...]:
    return tuple(
        target
        for target in DEFAULT_PROVIDER_FIELD_CAPTURE_TARGETS
        if target.provider in providers
    )
