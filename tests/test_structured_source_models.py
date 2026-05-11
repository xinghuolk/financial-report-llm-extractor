from decimal import Decimal

import pytest

from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
)


def test_source_evidence_requires_artifact_and_raw_record() -> None:
    evidence = SourceEvidence(
        source="akshare",
        adapter="akshare",
        function="stock_financial_hk_report_em",
        artifact_id="artifact-1",
        raw_record_id="00001:balance_sheet:2024",
        raw_field_name="Total assets",
    )

    evidence.validate()
    assert evidence.to_dict()["source"] == "akshare"


def test_source_inventory_money_requires_currency_and_unit() -> None:
    record = SourceInventoryRecord(
        source="akshare",
        market="HK",
        ticker="00001",
        statement_type="balance_sheet",
        period="2024-12-31",
        raw_field_name="Total assets",
        raw_value="100",
        parsed_numeric_value=Decimal("100"),
        value_type="money",
        currency="unknown",
        unit=None,
        source_evidence=(
            SourceEvidence(
                source="akshare",
                adapter="akshare",
                function="stock_financial_hk_report_em",
                artifact_id="artifact-1",
                raw_record_id="00001:balance_sheet:2024",
                raw_field_name="Total assets",
            ),
        ),
    )

    with pytest.raises(ValueError, match="money source records require currency and unit"):
        record.validate()
