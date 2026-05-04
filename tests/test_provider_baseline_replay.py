import json
from decimal import Decimal
from pathlib import Path

import pytest

from financial_report_llm_extractor.structured_sources.artifacts import (
    write_source_inventory,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
)
from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
    ProviderBaselineGroup,
    company_source_groups,
    select_latest_annual_records,
    write_provider_baseline_period_replay,
)


def _record(
    *,
    source: str = "akshare",
    market: str = "CN",
    ticker: str = "600519",
    statement_type: str = "income_statement",
    period: str | None = "2024-12-31",
    raw_field_name: str = "营业收入",
    raw_field_code: str | None = "OPERATE_INCOME",
    raw_value: str = "100",
    source_status: str = "present",
) -> SourceInventoryRecord:
    evidence = SourceEvidence(
        source=source,  # type: ignore[arg-type]
        adapter=source,
        function=statement_type,
        artifact_id=f"{source}_{ticker}_{statement_type}",
        raw_record_id=f"{source}:{ticker}:{statement_type}:{period}:{raw_field_name}",
        raw_field_name=raw_field_name,
        raw_field_code=raw_field_code,
    )
    return SourceInventoryRecord(
        source=source,  # type: ignore[arg-type]
        market=market,
        ticker=ticker,
        statement_type=statement_type,
        period=period,
        raw_field_name=raw_field_name,
        raw_field_code=raw_field_code,
        raw_value=raw_value,
        parsed_numeric_value=Decimal(raw_value),
        currency="CNY" if market == "CN" else "HKD",
        unit="yuan" if market == "CN" else "raw",
        source_status=source_status,  # type: ignore[arg-type]
        source_evidence=(evidence,),
    )


def test_select_latest_annual_records_ignores_interim_periods() -> None:
    records = (
        _record(period="2024-12-31", raw_value="100"),
        _record(period="2025-12-31 00:00:00", raw_value="120"),
        _record(period="2025-09-30", raw_value="200"),
        _record(period="2023-12-31", raw_value="50"),
    )

    selected = select_latest_annual_records(records)

    assert [record.period for record in selected] == ["2025-12-31"]
    assert [record.raw_value for record in selected] == ["120"]


def test_select_latest_annual_records_drops_non_present_when_annual_present() -> None:
    records = (
        _record(period="2025-12-31 00:00:00", raw_value="120"),
        _record(period=None, raw_value="0", source_status="source_error"),
    )

    selected = select_latest_annual_records(records)

    assert len(selected) == 1
    assert selected[0].source_status == "present"
    assert selected[0].period == "2025-12-31"


def test_select_latest_annual_records_keeps_all_when_no_annual_present() -> None:
    records = (
        _record(period="2025-09-30", raw_value="120"),
        _record(period=None, raw_value="0", source_status="source_error"),
    )

    selected = select_latest_annual_records(records)

    assert selected == records


def test_select_latest_annual_records_is_group_local() -> None:
    akshare_2025 = _record(
        source="akshare",
        ticker="600519",
        period="2025-12-31 00:00:00",
    )
    yahoo_2024 = _record(
        source="yahoo",
        market="CN",
        ticker="600519.SS",
        period="2024-12-31",
        raw_field_name="Total Revenue",
        raw_field_code=None,
    )

    assert select_latest_annual_records((akshare_2025,))[0].period == "2025-12-31"
    assert select_latest_annual_records((yahoo_2024,)) == (yahoo_2024,)


def test_company_source_groups_resolve_provider_tickers_from_targets() -> None:
    groups = company_source_groups()

    assert groups["600519"]["akshare"] == ProviderBaselineGroup(
        company_id="600519",
        source="akshare",
        market="CN",
        provider_ticker="600519",
    )
    assert groups["600519"]["yahoo"] == ProviderBaselineGroup(
        company_id="600519",
        source="yahoo",
        market="CN",
        provider_ticker="600519.SS",
    )
    assert groups["00001"]["yahoo"].provider_ticker == "0001.HK"
    assert groups["01113"]["yahoo"].provider_ticker == "1113.HK"


def test_write_provider_baseline_period_replay_selects_one_period_per_source(
    tmp_path: Path,
) -> None:
    inventory_path = tmp_path / "source_inventory.jsonl"
    inventory_summary_path = tmp_path / "provider_field_inventory_summary.json"
    inventory_summary_path.write_text("{}\n", encoding="utf-8")
    write_source_inventory(
        inventory_path,
        (
            _record(period="2024-12-31", raw_value="100"),
            _record(period="2025-12-31 00:00:00", raw_value="120"),
            _record(
                source="yahoo",
                market="CN",
                ticker="600519.SS",
                statement_type="balance_sheet",
                period="2024-12-31",
                raw_field_name="Cash And Cash Equivalents",
                raw_field_code=None,
                raw_value="90",
            ),
            _record(
                source="yahoo",
                market="CN",
                ticker="600519.SS",
                statement_type="balance_sheet",
                period="2025-12-31",
                raw_field_name="Cash And Cash Equivalents",
                raw_field_code=None,
                raw_value="120",
            ),
        ),
    )

    result = write_provider_baseline_period_replay(
        inventory_path=inventory_path,
        inventory_summary_path=inventory_summary_path,
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path / "replay",
        company_ids=("600519",),
    )

    payload = json.loads(result.summary_path.read_text(encoding="utf-8"))
    company = payload["companies"][0]
    assert payload["inventory_summary_path"] == str(inventory_summary_path)
    assert company["company_id"] == "600519"
    assert company["selected_periods"] == {
        "akshare": {
            "normalized": "2025-12-31",
            "raw_periods": ["2025-12-31 00:00:00"],
        },
        "yahoo": {
            "normalized": "2025-12-31",
            "raw_periods": ["2025-12-31"],
        },
    }
    assert company["coverage"]["akshare_only"]["covered_fields"] == ["revenue"]
    assert company["coverage"]["yahoo_only"]["covered_fields"] == ["cash"]
    assert company["coverage"]["combined"]["covered_fields"] == ["cash", "revenue"]
    assert "cash" in company["review"]["akshare_only"]["gap_categories"][
        "source_availability"
    ]
    assert company["review"]["combined"]["gap_categories"][
        "real_reconciliation_conflict"
    ] == []
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "present_fields: cash, revenue" in markdown
    assert "source_availability:" in markdown
    assert "review_summary: " in markdown
    assert (tmp_path / "replay" / "600519" / "combined" / "review_summary.json").exists()


def test_write_provider_baseline_period_replay_rejects_unknown_company_id(
    tmp_path: Path,
) -> None:
    inventory_path = tmp_path / "source_inventory.jsonl"
    inventory_summary_path = tmp_path / "provider_field_inventory_summary.json"
    inventory_summary_path.write_text("{}\n", encoding="utf-8")
    write_source_inventory(inventory_path, ())

    with pytest.raises(ValueError, match="unknown company ids: 99999"):
        write_provider_baseline_period_replay(
            inventory_path=inventory_path,
            inventory_summary_path=inventory_summary_path,
            catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
            output_dir=tmp_path / "replay",
            company_ids=("99999",),
        )


def test_provider_baseline_period_replay_uses_checked_in_fixture(
    tmp_path: Path,
) -> None:
    result = write_provider_baseline_period_replay(
        inventory_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz"
        ),
        inventory_summary_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json"
        ),
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path / "baseline",
    )

    payload = json.loads(result.summary_path.read_text(encoding="utf-8"))

    assert result.company_count == 3
    assert payload["company_count"] == 3
    assert {company["company_id"] for company in payload["companies"]} == {
        "00001",
        "01113",
        "600519",
    }
    assert all(
        company["coverage"]["combined"]["total_fields"] == 15
        for company in payload["companies"]
    )
    companies = {company["company_id"]: company for company in payload["companies"]}
    assert companies["600519"]["selected_periods"]["akshare"]["normalized"] == "2025-12-31"
    assert companies["600519"]["selected_periods"]["yahoo"]["normalized"] == "2025-12-31"
    assert companies["600519"]["coverage"]["akshare_only"]["covered_count"] >= 11
    assert companies["600519"]["coverage"]["yahoo_only"]["covered_count"] >= 11
    assert companies["00001"]["coverage"]["yahoo_only"]["covered_count"] >= 11
    assert companies["01113"]["coverage"]["yahoo_only"]["covered_count"] >= 11
    assert companies["600519"]["review"]["combined"]["gap_categories"][
        "real_reconciliation_conflict"
    ]
    assert companies["00001"]["review"]["combined"]["gap_categories"][
        "pdf_llm_supplement_candidates"
    ]

    for company_id in ("600519", "00001", "01113"):
        report_path = (
            tmp_path / "baseline" / company_id / "combined" / "reconciliation_report.json"
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        reasons = {item["reason"] for item in report["items"].values()}
        assert "candidate periods differ" not in reasons


def test_provider_baseline_period_replay_script_is_local_fixture_entrypoint() -> None:
    script = Path("scripts/run-provider-baseline-period-replay.sh").read_text(
        encoding="utf-8"
    )

    assert "replay-provider-baseline" in script
    assert "source_inventory.jsonl.gz" in script
    assert "provider_field_inventory_summary.json" in script
    assert "tmp/runs/provider_baseline_period_replay" in script
