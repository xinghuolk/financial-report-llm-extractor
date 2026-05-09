"""Tests for source_inventory_fetch module."""

from __future__ import annotations

from datetime import date
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
