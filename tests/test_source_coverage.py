from decimal import Decimal

from financial_report_llm_extractor.structured_sources.catalog import SourceMappingEntry
from financial_report_llm_extractor.structured_sources.coverage import (
    evaluate_source_coverage,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
)


def test_source_coverage_reports_present_and_missing_fields() -> None:
    entries = {
        "revenue": SourceMappingEntry(
            field_id="revenue",
            priority="P0",
            value_type="money",
            statement_type="income_statement",
            currency_requirement="required",
            unit_requirement="required",
            source_aliases={"akshare": ("营业收入",), "yahoo": ("Total Revenue",)},
        ),
        "net_profit": SourceMappingEntry(
            field_id="net_profit",
            priority="P0",
            value_type="money",
            statement_type="income_statement",
            currency_requirement="required",
            unit_requirement="required",
            source_aliases={"akshare": ("净利润",), "yahoo": ("Net Income",)},
        ),
    }
    records = [
        SourceInventoryRecord(
            source="akshare",
            market="CN",
            ticker="600519",
            statement_type="income_statement",
            period="2024-12-31",
            raw_field_name="营业收入",
            raw_value="100",
            parsed_numeric_value=Decimal("100"),
            currency="CNY",
            unit="yuan",
            source_evidence=(
                SourceEvidence(
                    "akshare",
                    "akshare",
                    "fn",
                    "a1",
                    "r1",
                    "营业收入",
                ),
            ),
        )
    ]

    summary = evaluate_source_coverage(
        entries,
        records,
        required_sources=("akshare", "yahoo"),
    )

    assert summary["total_fields"] == 2
    assert summary["combined"]["covered_fields"] == 1
    assert summary["combined"]["missing_fields"] == ["net_profit"]
    assert summary["combined"]["blocked_fields"] == []
    assert summary["by_source"]["akshare"]["covered_fields"] == 1
    assert summary["by_source"]["yahoo"]["covered_fields"] == 0


def test_source_coverage_blocks_money_record_without_currency_unit() -> None:
    entries = {
        "revenue": SourceMappingEntry(
            field_id="revenue",
            priority="P0",
            value_type="money",
            statement_type="income_statement",
            currency_requirement="required",
            unit_requirement="required",
            source_aliases={"akshare": ("营业收入",)},
        )
    }
    records = [
        SourceInventoryRecord(
            source="akshare",
            market="CN",
            ticker="600519",
            statement_type="income_statement",
            period="2024-12-31",
            raw_field_name="营业收入",
            raw_value="100",
            parsed_numeric_value=Decimal("100"),
            currency="unknown",
            unit=None,
            source_evidence=(
                SourceEvidence("akshare", "akshare", "fn", "a1", "r1", "营业收入"),
            ),
        )
    ]

    summary = evaluate_source_coverage(
        entries,
        records,
        required_sources=("akshare",),
    )

    assert summary["combined"]["covered_fields"] == 0
    assert summary["combined"]["missing_fields"] == []
    assert summary["combined"]["blocked_fields"] == ["revenue"]
    assert summary["combined"]["blocker_reasons"] == {
        "revenue": ["money source records require currency and unit"]
    }
