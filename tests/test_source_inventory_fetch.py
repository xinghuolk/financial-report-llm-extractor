"""Tests for source_inventory_fetch module."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
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
