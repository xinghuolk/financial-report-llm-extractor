from decimal import Decimal
from pathlib import Path

from financial_report_llm_extractor.structured_sources.akshare_adapter import (
    AkshareAdapter,
)
from financial_report_llm_extractor.structured_sources.artifacts import (
    SourceArtifactStore,
    finalize_source_artifacts,
)


class FakeAkshareClient:
    def stock_financial_hk_report_em(
        self,
        stock: str,
        symbol: str,
        indicator: str,
    ) -> list[dict[str, object]]:
        assert stock == "00001"
        assert symbol == "资产负债表"
        assert indicator == "年度"
        return [
            {
                "REPORT_DATE": "2024-12-31",
                "FISCAL_YEAR": "2024",
                "STD_ITEM_CODE": "HK_BAL_TOTAL_ASSETS",
                "STD_ITEM_NAME": "Total assets",
                "AMOUNT": "100",
            }
        ]

    def stock_financial_hk_report_metadata(
        self,
        stock: str,
    ) -> list[dict[str, object]]:
        assert stock == "00001"
        return [
            {
                "REPORT_DATE": "2024-12-31",
                "CURRENCY": "HKD",
                "ACCOUNT_STANDARD": "HKFRS",
                "REPORT_TYPE": "年报",
            }
        ]

    def stock_balance_sheet_by_report_em(self, symbol: str) -> list[dict[str, object]]:
        assert symbol == "SH600519"
        return [
            {
                "REPORT_DATE": "2024-12-31",
                "STD_ITEM_CODE": "CN_BAL_TOTAL_ASSETS",
                "STD_ITEM_NAME": "资产总计",
                "AMOUNT": "100,000",
            }
        ]

    def stock_profit_sheet_by_report_em(self, symbol: str) -> list[dict[str, object]]:
        assert symbol == "SH600519"
        return []

    def stock_cash_flow_sheet_by_report_em(self, symbol: str) -> list[dict[str, object]]:
        assert symbol == "SH600519"
        return []


class FakeAkshareClient01113(FakeAkshareClient):
    def stock_financial_hk_report_em(
        self,
        stock: str,
        symbol: str,
        indicator: str,
    ) -> list[dict[str, object]]:
        assert stock == "01113"
        assert symbol == "资产负债表"
        assert indicator == "年度"
        return [
            {
                "REPORT_DATE": "2024-12-31",
                "FISCAL_YEAR": "2024",
                "STD_ITEM_CODE": "HK_BAL_TOTAL_ASSETS",
                "STD_ITEM_NAME": "Total assets",
                "AMOUNT": "200",
            }
        ]

    def stock_financial_hk_report_metadata(
        self,
        stock: str,
    ) -> list[dict[str, object]]:
        assert stock == "01113"
        return [
            {
                "REPORT_DATE": "2024-12-31",
                "CURRENCY": "HKD",
                "ACCOUNT_STANDARD": "HKFRS",
                "REPORT_TYPE": "年报",
            }
        ]


def test_akshare_hk_statement_inventory_joins_metadata_and_writes_artifact(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path)
    adapter = AkshareAdapter(client=FakeAkshareClient(), artifact_store=store)

    records = adapter.fetch_hk_statement_inventory(
        ticker="00001",
        statement_type="balance_sheet",
        unit="HKD",
    )

    assert len(records) == 1
    record = records[0]
    assert record.source == "akshare"
    assert record.market == "HK"
    assert record.ticker == "00001"
    assert record.statement_type == "balance_sheet"
    assert record.period == "2024-12-31"
    assert record.fiscal_year == "2024"
    assert record.raw_field_code == "HK_BAL_TOTAL_ASSETS"
    assert record.raw_field_name == "Total assets"
    assert record.raw_value == "100"
    assert record.parsed_numeric_value == Decimal("100")
    assert record.currency == "HKD"
    assert record.unit == "HKD"
    assert record.account_standard == "HKFRS"
    assert record.report_type == "annual"
    assert record.source_evidence[0].function == "stock_financial_hk_report_em"
    assert (tmp_path / "akshare" / "akshare_hk_00001_balance_sheet.json").exists()


def test_akshare_cn_statement_inventory_uses_market_symbol_and_cny(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path)
    adapter = AkshareAdapter(client=FakeAkshareClient(), artifact_store=store)

    records = adapter.fetch_cn_statement_inventory(
        ticker="600519",
        exchange="SH",
        statement_type="balance_sheet",
        unit="yuan",
    )

    assert len(records) == 1
    record = records[0]
    assert record.market == "CN"
    assert record.ticker == "600519"
    assert record.statement_type == "balance_sheet"
    assert record.period == "2024-12-31"
    assert record.raw_field_name == "资产总计"
    assert record.raw_field_code == "CN_BAL_TOTAL_ASSETS"
    assert record.raw_value == "100,000"
    assert record.parsed_numeric_value == Decimal("100000")
    assert record.currency == "CNY"
    assert record.unit == "yuan"
    assert record.source_evidence[0].function == "stock_balance_sheet_by_report_em"
    assert (tmp_path / "akshare" / "akshare_cn_600519_balance_sheet.json").exists()


def test_akshare_cn_inventory_replay_validates_against_manifest(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path / "source_artifacts")
    adapter = AkshareAdapter(client=FakeAkshareClient(), artifact_store=store)

    records = adapter.fetch_cn_statement_inventory(
        ticker="600519",
        exchange="SH",
        statement_type="balance_sheet",
        unit="yuan",
    )
    manifest = finalize_source_artifacts(
        artifact_root=tmp_path / "source_artifacts",
        artifacts=store.artifacts,
        records=records,
        manifest_path=tmp_path / "source_artifact_manifest.json",
    )

    assert manifest.artifacts[0].artifact_id == "akshare_cn_600519_balance_sheet"


def test_akshare_hk_00001_inventory_replay_validates_against_manifest(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path / "source_artifacts")
    adapter = AkshareAdapter(client=FakeAkshareClient(), artifact_store=store)

    records = adapter.fetch_hk_statement_inventory(
        ticker="00001",
        statement_type="balance_sheet",
        unit="HKD",
    )
    manifest = finalize_source_artifacts(
        artifact_root=tmp_path / "source_artifacts",
        artifacts=store.artifacts,
        records=records,
        manifest_path=tmp_path / "source_artifact_manifest.json",
    )

    assert manifest.artifacts[0].artifact_id == "akshare_hk_00001_balance_sheet"
    assert records[0].currency == "HKD"


def test_akshare_hk_01113_inventory_replay_validates_against_manifest(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path / "source_artifacts")
    adapter = AkshareAdapter(client=FakeAkshareClient01113(), artifact_store=store)

    records = adapter.fetch_hk_statement_inventory(
        ticker="01113",
        statement_type="balance_sheet",
        unit="HKD",
    )
    manifest = finalize_source_artifacts(
        artifact_root=tmp_path / "source_artifacts",
        artifacts=store.artifacts,
        records=records,
        manifest_path=tmp_path / "source_artifact_manifest.json",
    )

    assert manifest.artifacts[0].artifact_id == "akshare_hk_01113_balance_sheet"
    assert records[0].currency == "HKD"


def test_akshare_hk_statement_inventory_returns_unsupported_record(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path)
    adapter = AkshareAdapter(client=FakeAkshareClient(), artifact_store=store)

    records = adapter.fetch_hk_statement_inventory(
        ticker="00001",
        statement_type="equity_statement",
        unit="HKD",
    )

    assert len(records) == 1
    record = records[0]
    assert record.source_status == "unsupported"
    assert record.market == "HK"
    assert record.raw_field_name == "equity_statement"
    assert record.source_evidence[0].function == "unsupported_statement_type"
    assert (tmp_path / "akshare" / "akshare_hk_00001_equity_statement.json").exists()


def test_akshare_cn_statement_inventory_returns_missing_record_for_empty_rows(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path)
    adapter = AkshareAdapter(client=FakeAkshareClient(), artifact_store=store)

    records = adapter.fetch_cn_statement_inventory(
        ticker="600519",
        exchange="SH",
        statement_type="income_statement",
        unit="yuan",
    )

    assert len(records) == 1
    record = records[0]
    assert record.source_status == "missing"
    assert record.market == "CN"
    assert record.raw_field_name == "income_statement"
    assert record.source_evidence[0].function == "stock_profit_sheet_by_report_em"
    assert (tmp_path / "akshare" / "akshare_cn_600519_income_statement.json").exists()
