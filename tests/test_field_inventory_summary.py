import json
from decimal import Decimal
from pathlib import Path

from financial_report_llm_extractor.structured_sources.field_inventory_summary import (
    build_provider_field_inventory_summary,
    write_provider_field_inventory_summary,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
    SourceStatus,
)


def _record(
    raw_field_name: str,
    raw_field_code: str | None,
    period: str | None,
    status: SourceStatus = "present",
) -> SourceInventoryRecord:
    return SourceInventoryRecord(
        source="akshare",
        market="CN",
        ticker="600519",
        statement_type="income_statement",
        period=period,
        raw_field_name=raw_field_name,
        raw_value="100",
        parsed_numeric_value=Decimal("100"),
        currency="CNY",
        unit="yuan",
        raw_field_code=raw_field_code,
        source_status=status,
        source_evidence=(
            SourceEvidence(
                source="akshare",
                adapter="akshare",
                function="stock_financial_report_sina",
                artifact_id="akshare_cn_600519_income_statement",
                raw_record_id=f"600519:income_statement:{raw_field_name}",
                raw_field_name=raw_field_name,
                raw_field_code=raw_field_code,
            ),
        ),
    )


def test_provider_field_inventory_summary_preserves_unmapped_raw_fields() -> None:
    summary = build_provider_field_inventory_summary(
        (
            _record("营业收入", "OPERATE_INCOME", "2024-12-31"),
            _record("管理费用", "ADMIN_EXPENSE", "2024-12-31"),
            _record("missing", None, "2024-12-31", status="missing"),
        ),
        sample_set="provider_field_baseline",
        source_artifact_count=1,
    )

    assert summary["sample_set"] == "provider_field_baseline"
    assert summary["record_count"] == 3
    assert summary["source_artifact_count"] == 1
    assert summary["status_counts"] == {"missing": 1, "present": 2}

    target = summary["targets"][0]
    assert target["source"] == "akshare"
    assert target["ticker"] == "600519"
    assert target["statement_type"] == "income_statement"
    assert target["raw_field_names"] == ["missing", "管理费用", "营业收入"]
    assert target["raw_field_codes"] == ["ADMIN_EXPENSE", "OPERATE_INCOME"]
    assert target["periods"] == ["2024-12-31"]
    assert target["currencies"] == ["CNY"]
    assert target["units"] == ["yuan"]


def test_write_provider_field_inventory_summary_writes_json(tmp_path: Path) -> None:
    out_path = tmp_path / "provider_field_inventory_summary.json"

    write_provider_field_inventory_summary(
        out_path,
        records=(_record("营业收入", "OPERATE_INCOME", "2024-12-31"),),
        sample_set="provider_field_baseline",
        source_artifact_count=None,
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["record_count"] == 1
    assert "source_artifact_count" not in payload
