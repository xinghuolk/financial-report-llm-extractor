from decimal import Decimal

from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    ProviderRawField,
    build_provider_raw_field_index,
    normalize_match_text,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
)


def _record(
    *,
    source: str = "akshare",
    ticker: str = "600519",
    statement_type: str = "income_statement",
    period: str = "2025-12-31",
    raw_field_name: str = "营业收入",
    raw_field_code: str | None = "OPERATE_INCOME",
    value: str = "100",
) -> SourceInventoryRecord:
    evidence = SourceEvidence(
        source=source,  # type: ignore[arg-type]
        adapter=source,
        function="fn",
        artifact_id="artifact_1",
        raw_record_id=f"{source}:{ticker}:{statement_type}:{period}:{raw_field_name}",
        raw_field_name=raw_field_name,
        raw_field_code=raw_field_code,
    )
    return SourceInventoryRecord(
        source=source,  # type: ignore[arg-type]
        market="CN" if ticker == "600519" else "HK",
        ticker=ticker,
        statement_type=statement_type,
        period=period,
        raw_field_name=raw_field_name,
        raw_field_code=raw_field_code,
        raw_value=value,
        parsed_numeric_value=Decimal(value),
        currency="CNY" if ticker == "600519" else "HKD",
        unit="yuan" if ticker == "600519" else "raw",
        source_evidence=(evidence,),
    )


def test_normalize_match_text_handles_english_codes_and_chinese() -> None:
    assert normalize_match_text("TOTAL_OPERATE_INCOME") == "total operate income"
    assert normalize_match_text("Total   Revenue") == "total revenue"
    assert normalize_match_text("营业收入") == "营业收入"


def test_build_provider_raw_field_index_groups_targets_periods_and_counts() -> None:
    records = (
        _record(period="2024-12-31"),
        _record(period="2025-12-31"),
        _record(
            source="yahoo",
            ticker="0001.HK",
            raw_field_name="Total Revenue",
            raw_field_code=None,
            value="200",
        ),
    )

    index = build_provider_raw_field_index(records)

    akshare_key = ("akshare", "income_statement", "营业收入", "OPERATE_INCOME")
    yahoo_key = ("yahoo", "income_statement", "Total Revenue", None)
    assert index[akshare_key] == ProviderRawField(
        source="akshare",
        statement_type="income_statement",
        raw_field_name="营业收入",
        raw_field_code="OPERATE_INCOME",
        normalized_names=("营业收入",),
        normalized_codes=("operate income",),
        tickers=("600519",),
        periods=("2024-12-31", "2025-12-31"),
        record_count=2,
    )
    assert index[yahoo_key].tickers == ("0001.HK",)
    assert index[yahoo_key].periods == ("2025-12-31",)
