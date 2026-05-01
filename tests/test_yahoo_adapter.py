from decimal import Decimal
from pathlib import Path

from financial_report_llm_extractor.structured_sources.artifacts import (
    SourceArtifactStore,
)
from financial_report_llm_extractor.structured_sources.yahoo_adapter import (
    YahooAdapter,
)


class FakeYahooClient:
    def get_financial_statement(
        self,
        *,
        ticker: str,
        statement_type: str,
    ) -> dict[str, object]:
        assert ticker == "0001.HK"
        assert statement_type == "income_statement"
        return {
            "metadata": {"currency": "HKD", "report_type": "annual"},
            "rows": [
                {
                    "field": "Total Revenue",
                    "period": "2024-12-31",
                    "value": "100",
                }
            ],
        }


class EmptyYahooClient:
    def get_financial_statement(
        self,
        *,
        ticker: str,
        statement_type: str,
    ) -> dict[str, object]:
        assert ticker == "0001.HK"
        assert statement_type == "cash_flow"
        return {"metadata": {"currency": "HKD"}, "rows": []}


def test_yahoo_statement_inventory_writes_raw_artifact_and_records_rows(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path)
    adapter = YahooAdapter(client=FakeYahooClient(), artifact_store=store)

    records = adapter.fetch_statement_inventory(
        ticker="0001.HK",
        market="HK",
        statement_type="income_statement",
        currency="HKD",
        unit="raw",
    )

    assert len(records) == 1
    record = records[0]
    assert record.source == "yahoo"
    assert record.market == "HK"
    assert record.ticker == "0001.HK"
    assert record.statement_type == "income_statement"
    assert record.period == "2024-12-31"
    assert record.report_type == "annual"
    assert record.raw_field_name == "Total Revenue"
    assert record.raw_value == "100"
    assert record.parsed_numeric_value == Decimal("100")
    assert record.currency == "HKD"
    assert record.unit == "raw"
    assert record.source_evidence[0].function == "get_financial_statement"
    assert (tmp_path / "yahoo" / "yahoo_hk_0001_hk_income_statement.json").exists()


def test_yahoo_statement_inventory_returns_missing_record_for_empty_statement(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path)
    adapter = YahooAdapter(client=EmptyYahooClient(), artifact_store=store)

    records = adapter.fetch_statement_inventory(
        ticker="0001.HK",
        market="HK",
        statement_type="cash_flow",
        currency="HKD",
        unit="raw",
    )

    assert len(records) == 1
    record = records[0]
    assert record.source == "yahoo"
    assert record.source_status == "missing"
    assert record.raw_field_name == "cash_flow"
    assert record.source_evidence[0].artifact_id == "yahoo_hk_0001_hk_cash_flow"
