import json
from decimal import Decimal
from pathlib import Path

from financial_report_llm_extractor.structured_sources.real_source_validation import (
    RealSourceValidationSample,
    build_default_validation_samples,
    build_provider_field_capture_samples,
    run_captured_source_validation,
    run_real_source_validation,
)


class FakeAkshareClient:
    def stock_financial_hk_report_em(
        self,
        *,
        stock: str,
        symbol: str,
        indicator: str,
    ) -> list[dict[str, object]]:
        raise AssertionError("HK report should not be called in this test")

    def stock_financial_hk_report_metadata(
        self,
        *,
        stock: str,
    ) -> list[dict[str, object]]:
        raise AssertionError("HK metadata should not be called in this test")

    def stock_balance_sheet_by_report_em(
        self,
        *,
        symbol: str,
    ) -> list[dict[str, object]]:
        raise AssertionError("balance sheet should not be called in this test")

    def stock_profit_sheet_by_report_em(
        self,
        *,
        symbol: str,
    ) -> list[dict[str, object]]:
        assert symbol == "SH600519"
        return [
            {
                "REPORT_DATE": "2023-12-31",
                "OPERATE_INCOME": "80",
                "CURRENCY": "CNY",
            },
            {
                "REPORT_DATE": "2024-12-31",
                "OPERATE_INCOME": "100",
                "CURRENCY": "CNY",
            }
        ]

    def stock_cash_flow_sheet_by_report_em(
        self,
        *,
        symbol: str,
    ) -> list[dict[str, object]]:
        raise AssertionError("cash flow should not be called in this test")


class FakeYahooClient:
    def get_financial_statement(
        self,
        *,
        ticker: str,
        statement_type: str,
    ) -> dict[str, object]:
        assert ticker == "0001.HK"
        assert statement_type == "balance_sheet"
        return {
            "metadata": {"currency": "HKD", "report_type": "annual"},
            "rows": [
                {
                    "field": "Cash And Cash Equivalents",
                    "period": "2024-12-31",
                    "value": "100",
                }
            ],
        }


def test_real_source_validation_runs_adapters_through_mapping_flow(
    tmp_path: Path,
) -> None:
    result = run_real_source_validation(
        samples=(
            RealSourceValidationSample(
                provider="akshare",
                market="CN",
                ticker="600519",
                statement_type="income_statement",
                currency="CNY",
                unit="yuan",
                exchange="SH",
            ),
            RealSourceValidationSample(
                provider="yahoo",
                market="HK",
                ticker="0001.HK",
                statement_type="balance_sheet",
                currency="HKD",
                unit="raw",
            ),
        ),
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path,
        akshare_client=FakeAkshareClient(),
        yahoo_client=FakeYahooClient(),
    )

    assert result.summary["validation_mode"] == "real_source_adapter"
    assert result.summary["sample_count"] == 2
    assert result.summary["record_count"] == 2
    assert result.summary["status"] == "completed"
    assert result.summary["mapping_coverage"]["covered_count"] >= 1
    assert (tmp_path / "source_inventory.jsonl").exists()
    assert (tmp_path / "source_artifacts" / "akshare").exists()
    assert (tmp_path / "source_artifacts" / "yahoo").exists()
    assert (tmp_path / "turtle_mapping.json").exists()
    assert (tmp_path / "reconciliation_report.json").exists()
    assert (tmp_path / "extraction_result.json").exists()
    assert result.records[0].parsed_numeric_value == Decimal("100")


def test_real_source_validation_writes_source_artifact_manifest(
    tmp_path: Path,
) -> None:
    result = run_real_source_validation(
        samples=(
            RealSourceValidationSample(
                provider="akshare",
                market="CN",
                ticker="600519",
                statement_type="income_statement",
                currency="CNY",
                unit="yuan",
                exchange="SH",
            ),
        ),
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path,
        akshare_client=FakeAkshareClient(),
    )

    manifest_path = tmp_path / "source_artifact_manifest.json"
    assert manifest_path.exists()
    assert result.summary["artifact_paths"]["source_artifact_manifest"] == str(
        manifest_path
    )
    assert result.summary["source_artifact_count"] >= 1


def test_real_source_validation_writes_provider_field_inventory_summary(
    tmp_path: Path,
) -> None:
    result = run_real_source_validation(
        samples=(
            RealSourceValidationSample(
                provider="akshare",
                market="CN",
                ticker="600519",
                statement_type="income_statement",
                currency="CNY",
                unit="yuan",
                exchange="SH",
            ),
        ),
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path,
        akshare_client=FakeAkshareClient(),
    )

    summary_path = tmp_path / "provider_field_inventory_summary.json"
    assert summary_path.exists()
    assert result.summary["artifact_paths"]["provider_field_inventory_summary"] == str(
        summary_path
    )
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["record_count"] == 1
    assert payload["targets"][0]["raw_field_names"] == ["营业收入"]


def test_provider_field_baseline_preserves_all_returned_period_fields(
    tmp_path: Path,
) -> None:
    class BaselineAkshareClient(FakeAkshareClient):
        def stock_profit_sheet_by_report_em(
            self,
            *,
            symbol: str,
        ) -> list[dict[str, object]]:
            assert symbol == "SH600519"
            return [
                {
                    "REPORT_DATE": "2023-12-31",
                    "STD_ITEM_CODE": "ADMIN_EXPENSE",
                    "STD_ITEM_NAME": "管理费用",
                    "AMOUNT": "20",
                },
                {
                    "REPORT_DATE": "2024-12-31",
                    "STD_ITEM_CODE": "OPERATE_INCOME",
                    "STD_ITEM_NAME": "营业收入",
                    "AMOUNT": "100",
                },
            ]

    result = run_real_source_validation(
        samples=(
            RealSourceValidationSample(
                provider="akshare",
                market="CN",
                ticker="600519",
                statement_type="income_statement",
                currency="CNY",
                unit="yuan",
                exchange="SH",
            ),
        ),
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path,
        sample_set="provider_field_baseline",
        akshare_client=BaselineAkshareClient(),
    )

    assert result.summary["record_count"] == 2

    summary_payload = json.loads(
        (tmp_path / "provider_field_inventory_summary.json").read_text(
            encoding="utf-8"
        )
    )
    target = summary_payload["targets"][0]
    assert target["raw_field_names"] == ["管理费用", "营业收入"]
    assert target["periods"] == ["2023-12-31", "2024-12-31"]

    inventory_lines = (tmp_path / "source_inventory.jsonl").read_text(
        encoding="utf-8"
    )
    assert "管理费用" in inventory_lines
    assert "营业收入" in inventory_lines
    assert "2023-12-31" in inventory_lines
    assert "2024-12-31" in inventory_lines


def test_provider_field_baseline_keeps_latest_five_annual_periods(
    tmp_path: Path,
) -> None:
    class ManyPeriodAkshareClient(FakeAkshareClient):
        def stock_profit_sheet_by_report_em(
            self,
            *,
            symbol: str,
        ) -> list[dict[str, object]]:
            assert symbol == "SH600519"
            return [
                {
                    "REPORT_DATE": period,
                    "STD_ITEM_CODE": "OPERATE_INCOME",
                    "STD_ITEM_NAME": "营业收入",
                    "AMOUNT": str(index),
                }
                for index, period in enumerate(
                    (
                        "2019-12-31",
                        "2020-12-31",
                        "2021-12-31",
                        "2022-12-31",
                        "2023-12-31",
                        "2024-12-31",
                        "2025-09-30",
                    ),
                    start=1,
                )
            ]

    result = run_real_source_validation(
        samples=(
            RealSourceValidationSample(
                provider="akshare",
                market="CN",
                ticker="600519",
                statement_type="income_statement",
                currency="CNY",
                unit="yuan",
                exchange="SH",
            ),
        ),
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path,
        sample_set="provider_field_baseline",
        akshare_client=ManyPeriodAkshareClient(),
    )

    assert result.summary["record_count"] == 5
    assert [record.period for record in result.records] == [
        "2020-12-31",
        "2021-12-31",
        "2022-12-31",
        "2023-12-31",
        "2024-12-31",
    ]


def test_real_source_validation_records_source_errors_without_aborting(
    tmp_path: Path,
) -> None:
    class FailingYahooClient:
        def get_financial_statement(
            self,
            *,
            ticker: str,
            statement_type: str,
        ) -> dict[str, object]:
            raise RuntimeError("network unavailable")

    result = run_real_source_validation(
        samples=(
            RealSourceValidationSample(
                provider="yahoo",
                market="HK",
                ticker="0001.HK",
                statement_type="income_statement",
                currency="HKD",
                unit="raw",
            ),
        ),
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path,
        yahoo_client=FailingYahooClient(),
    )

    assert result.summary["status"] == "completed_with_source_errors"
    assert result.records[0].source_status == "source_error"
    assert result.records[0].raw_field_name == "income_statement"
    assert result.summary["source_errors"][0]["error"] == "network unavailable"


def test_captured_source_validation_reuses_saved_inventory_without_clients(
    tmp_path: Path,
) -> None:
    result = run_captured_source_validation(
        inventory_path=Path(
            "tests/fixtures/akshare/600519_income_statement_2025_required_fields.jsonl"
        ),
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path,
    )

    assert result.summary["validation_mode"] == "captured_source_inventory"
    assert result.summary["status"] == "completed"
    assert result.summary["record_count"] == 4
    assert result.summary["mapping_coverage"]["covered_fields"] == [
        "net_profit",
        "revenue",
    ]
    assert "source_artifact_manifest" not in result.summary["artifact_paths"]
    assert "source_artifact_count" not in result.summary
    assert (tmp_path / "source_inventory.jsonl").exists()
    assert (tmp_path / "extraction_result.json").exists()
    summary_path = tmp_path / "provider_field_inventory_summary.json"
    assert summary_path.exists()
    assert result.summary["artifact_paths"]["provider_field_inventory_summary"] == str(
        summary_path
    )
    assert not (tmp_path / "source_artifact_manifest.json").exists()


def test_captured_source_validation_combined_akshare_fixtures_cover_minimal_fields(
    tmp_path: Path,
) -> None:
    result = run_captured_source_validation(
        inventory_path=Path(
            "tests/fixtures/akshare/600519_combined_statements_2025_required_fields.jsonl"
        ),
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path,
    )

    assert result.summary["validation_mode"] == "captured_source_inventory"
    assert result.summary["status"] == "completed"
    assert result.summary["record_count"] == 10
    assert result.summary["mapping_coverage"]["covered_fields"] == [
        "cash",
        "net_profit",
        "operating_cash_flow",
        "revenue",
        "total_assets",
        "total_cur_assets",
        "total_cur_liab",
        "total_liabilities",
    ]
    assert result.summary["mapping_coverage"]["covered_count"] == 8
    assert result.summary["mapping_coverage"]["total_fields"] == 15
    review_summary = json.loads(
        (tmp_path / "review_summary.json").read_text(encoding="utf-8")
    )
    assert review_summary["missing_fields"] == [
        "bond_payable",
        "cip",
        "defer_tax_liab",
        "financing_cash_flow",
        "gross_profit",
        "invest_income",
        "investing_cash_flow",
    ]


def test_captured_source_validation_yahoo_fixture_covers_income_fields(
    tmp_path: Path,
) -> None:
    result = run_captured_source_validation(
        inventory_path=Path(
            "tests/fixtures/yahoo/0001_hk_income_statement_2025_required_fields.jsonl"
        ),
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path,
    )

    assert result.summary["validation_mode"] == "captured_source_inventory"
    assert result.summary["status"] == "completed"
    assert result.summary["record_count"] == 5
    assert result.summary["mapping_coverage"]["covered_fields"] == [
        "gross_profit",
        "net_profit",
        "revenue",
    ]
    assert result.summary["mapping_coverage"]["covered_count"] == 3
    assert result.summary["mapping_coverage"]["total_fields"] == 15
    review_summary = json.loads(
        (tmp_path / "review_summary.json").read_text(encoding="utf-8")
    )
    assert review_summary["present_fields"] == [
        "gross_profit",
        "net_profit",
        "revenue",
    ]
    assert "gross_profit" not in review_summary["missing_fields"]
    assert "net_profit" not in review_summary["missing_fields"]
    assert "revenue" not in review_summary["missing_fields"]
    assert "financing_cash_flow" in review_summary["missing_fields"]
    assert "investing_cash_flow" in review_summary["missing_fields"]


def test_real_source_validation_script_is_opt_in() -> None:
    script = Path("scripts/run-real-source-validation.sh").read_text(encoding="utf-8")

    assert "REAL_SOURCE_VALIDATION=1" in script
    assert "PYTHONPATH=src" in script
    assert "real_source_validation" in script
    assert "--inventory-fixture" in script
    assert "--akshare-cn-statements" in script


def test_default_validation_samples_can_request_multiple_akshare_statements() -> None:
    samples = build_default_validation_samples(
        providers=("akshare",),
        akshare_cn_statements=("balance_sheet", "cash_flow"),
    )

    assert tuple(sample.statement_type for sample in samples) == (
        "balance_sheet",
        "cash_flow",
    )
    assert {sample.ticker for sample in samples} == {"600519"}


def test_provider_field_capture_sample_set_builds_full_target_matrix() -> None:
    samples = build_provider_field_capture_samples(providers=("akshare", "yahoo"))

    assert len(samples) == 18
    assert RealSourceValidationSample(
        provider="akshare",
        market="CN",
        ticker="600519",
        statement_type="balance_sheet",
        currency="CNY",
        unit="yuan",
        exchange="SH",
    ) in samples
    assert RealSourceValidationSample(
        provider="yahoo",
        market="HK",
        ticker="1113.HK",
        statement_type="cash_flow",
        currency="HKD",
        unit="raw",
    ) in samples
