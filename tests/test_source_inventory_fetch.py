"""Tests for source_inventory_fetch module."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from financial_report_llm_extractor.structured_sources.catalog import (
        SourceMappingCatalog,
    )
    from financial_report_llm_extractor.structured_sources.models import (
        SourceInventoryRecord,
    )


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


def _build_record(period: str, source_status: str = "present") -> "SourceInventoryRecord":
    """Construct a minimal SourceInventoryRecord. Note actual dataclass fields
    differ from the original plan stub — verify against
    src/financial_report_llm_extractor/structured_sources/models.py:66-104.

    Required fields: source, market, ticker, statement_type, period,
    raw_field_name, raw_value. For present-status money records, validate()
    requires currency, unit, and a source_evidence tuple — but construction
    alone doesn't trigger validate(); only to_dict() does. select_records_for_period
    doesn't serialize, so a minimal construction is sufficient for these tests.
    """
    from financial_report_llm_extractor.structured_sources.models import (
        SourceInventoryRecord,
    )
    return SourceInventoryRecord(
        source="akshare",
        market="CN",
        ticker="600519",
        statement_type="income_statement",
        period=period,
        raw_field_name="OPERATE_INCOME",
        raw_value="100",
        currency="CNY",
        unit="yuan",
        source_status=source_status,  # type: ignore[arg-type]
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


class _RepurchaseHistoryYahooClient:
    """Yahoo client whose cash flow tracks 'Repurchase Of Capital Stock' in
    2022 but NOT in 2024 — plus a present 2024 cash-flow line so the statement
    is present for the target period."""

    def get_financial_statement(
        self, *, ticker: str, statement_type: str
    ) -> dict[str, object]:
        if statement_type != "cash_flow":
            return {"metadata": {}, "rows": []}
        return {
            "metadata": {"report_type": "annual"},
            "rows": [
                {
                    "field": "Repurchase Of Capital Stock",
                    "period": "2022-12-31",
                    "value": "-197000000",
                },
                {  # statement present in target period (a different line)
                    "field": "Cash Dividends Paid",
                    "period": "2024-12-31",
                    "value": "-9433000000",
                },
            ],
        }


def test_fetch_source_inventory_synthesizes_zero_for_tracked_absent_field(
    tmp_path: Path,
) -> None:
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
        fetch_source_inventory,
    )

    catalog_path = Path("field_catalog/turtle_v015_source_mapping_minimal.json")

    fetch_source_inventory(
        company="00001",
        period=PeriodSpec.from_year(2024),
        market="HK",
        providers=("yahoo",),
        akshare_client=None,
        yahoo_client=_RepurchaseHistoryYahooClient(),
        out_dir=tmp_path,
        catalog_path=catalog_path,
    )

    import json as _json

    rows = [
        _json.loads(line)
        for line in (tmp_path / "source_inventory.jsonl").read_text().splitlines()
        if line.strip()
    ]
    repurchase = [
        r for r in rows if r.get("raw_field_name") == "Repurchase Of Capital Stock"
    ]
    assert len(repurchase) == 1, "expected one synthesized repurchase=0 record"
    rec = repurchase[0]
    assert rec["period"].startswith("2024-12-31")
    assert rec["parsed_numeric_value"] == "0"
    assert rec["source_status"] == "present"


def test_yahoo_hk_ticker_strips_leading_zeroes_and_keeps_four_digit_minimum() -> None:
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        _yahoo_hk_ticker,
    )

    assert _yahoo_hk_ticker("00001") == "0001"
    assert _yahoo_hk_ticker("01113") == "1113"
    assert _yahoo_hk_ticker("01810") == "1810"


def test_hk_issuer_financial_currency_maps_known_reporters() -> None:
    """Phase HK-B.5.1: HK issuer → financial-statement reporting currency.

    Source-of-truth is the PDF spot-check captured in
    docs/phase_hk_b_5_recon.md. Known issuers map to their reporting
    currency; unknown HK issuers fall back to HKD (pre-fix default).
    """
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        hk_issuer_financial_currency,
    )

    # HKD reporters (HK locals)
    assert hk_issuer_financial_currency("00001") == "HKD"
    assert hk_issuer_financial_currency("01113") == "HKD"

    # CNY (RMB) reporters
    assert hk_issuer_financial_currency("01810") == "CNY"
    assert hk_issuer_financial_currency("02498") == "CNY"
    assert hk_issuer_financial_currency("06862") == "CNY"

    # USD reporter
    assert hk_issuer_financial_currency("09987") == "USD"

    # Unknown HK ticker → HKD default (preserves pre-Phase-HK-B.5.1 behavior).
    assert hk_issuer_financial_currency("99999") == "HKD"


# ---------------------------------------------------------------------------
# Inventory-layer absence-means-zero synthesis (sparse buyback verified 0)
# ---------------------------------------------------------------------------


def _repurchase_catalog() -> "SourceMappingCatalog":
    from financial_report_llm_extractor.structured_sources.catalog import (
        SourceMappingCatalog,
        SourceMappingEntry,
    )
    return SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "repurchase_of_stock": SourceMappingEntry(
                field_id="repurchase_of_stock",
                priority="P2",
                value_type="money",
                statement_type="cash_flow",
                currency_requirement="required",
                unit_requirement="required",
                source_aliases={"yahoo": ("Repurchase Of Capital Stock",)},
                primary_route="yahoo_direct",
                absence_means_zero=True,
            )
        },
    )


def _cf_record(
    raw_field_name: str,
    period: str,
    *,
    source: str = "yahoo",
    statement_type: str = "cash_flow",
    value: str = "-8518000000",
) -> "SourceInventoryRecord":
    from financial_report_llm_extractor.structured_sources.models import (
        SourceEvidence,
        SourceInventoryRecord,
    )
    return SourceInventoryRecord(
        source=source,  # type: ignore[arg-type]
        market="HK",
        ticker="00001",
        statement_type=statement_type,
        period=period,
        raw_field_name=raw_field_name,
        raw_value=value,
        currency="HKD",
        unit="HKD",
        source_status="present",
        source_evidence=(
            SourceEvidence(
                source=source,  # type: ignore[arg-type]
                adapter=source,
                function="fixture",
                artifact_id=f"{source}_hk_00001_{statement_type}",
                raw_record_id=f"{source}:{raw_field_name}:{period}",
                raw_field_name=raw_field_name,
            ),
        ),
    )


def _synthesize(
    all_records: list["SourceInventoryRecord"], period_year: int = 2025
) -> list["SourceInventoryRecord"]:
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
        synthesize_absence_zero_records,
    )
    return synthesize_absence_zero_records(
        tuple(all_records), PeriodSpec.from_year(period_year), _repurchase_catalog()
    )


def test_synthesize_zero_when_tracked_but_absent_in_target_period() -> None:
    """Provider tracked the line historically + statement present + absent this
    period → synthesize a present 0 for the target period (00001 case)."""
    records = [
        _cf_record("Repurchase Of Capital Stock", "2021-12-31", value="-1239000000"),
        _cf_record("Repurchase Of Capital Stock", "2022-12-31", value="-197000000"),
        _cf_record("Cash Dividends Paid", "2025-12-31"),  # statement present 2025
    ]

    synth = _synthesize(records)

    assert len(synth) == 1
    rec = synth[0]
    assert rec.source == "yahoo"
    assert rec.statement_type == "cash_flow"
    assert rec.raw_field_name == "Repurchase Of Capital Stock"
    assert rec.period == "2025-12-31"
    assert rec.source_status == "present"
    assert rec.parsed_numeric_value == Decimal("0")
    assert rec.currency == "HKD"
    assert rec.unit == "HKD"
    rec.validate()  # must be a structurally valid present money record


def test_no_synthesis_when_provider_never_tracked_the_line() -> None:
    """Provider has no repurchase row in ANY period → absence is 'not tracked',
    not zero. Must NOT synthesize (600519 / Moutai false-zero guard)."""
    records = [
        _cf_record("Cash Dividends Paid", "2024-12-31"),
        _cf_record("Cash Dividends Paid", "2025-12-31"),
    ]

    assert _synthesize(records) == []


def test_no_synthesis_when_value_present_in_target_period() -> None:
    """Provider reported a real repurchase value this period → use it, no synth."""
    records = [
        _cf_record("Repurchase Of Capital Stock", "2025-12-31", value="-500000000"),
        _cf_record("Cash Dividends Paid", "2025-12-31"),
    ]

    assert _synthesize(records) == []


def test_no_synthesis_when_statement_absent_in_target_period() -> None:
    """Tracked historically, but the cash_flow statement itself is absent this
    period → cannot assert zero (no completeness evidence)."""
    records = [
        _cf_record("Repurchase Of Capital Stock", "2021-12-31", value="-1239000000"),
        # No 2025 cash_flow records at all.
    ]

    assert _synthesize(records) == []
