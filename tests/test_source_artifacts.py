from decimal import Decimal
from pathlib import Path

from financial_report_llm_extractor.structured_sources.artifacts import (
    SourceArtifactStore,
    build_artifact_id,
    read_source_inventory,
    write_source_inventory,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
)


def test_source_artifact_store_writes_json_under_source_directory(tmp_path: Path) -> None:
    store = SourceArtifactStore(tmp_path)
    artifact_id = build_artifact_id(
        source="akshare",
        market="HK",
        ticker="00001",
        artifact_type="balance_sheet",
    )

    artifact = store.write_json(
        source="akshare",
        artifact_id=artifact_id,
        payload={"rows": [{"STD_ITEM_NAME": "Total assets", "AMOUNT": 100}]},
    )

    assert artifact.artifact_id == "akshare_hk_00001_balance_sheet"
    assert artifact.source == "akshare"
    assert artifact.content_type == "application/json"
    assert artifact.path == "akshare/akshare_hk_00001_balance_sheet.json"
    assert (tmp_path / artifact.path).read_text(encoding="utf-8").endswith("\n")


def test_source_inventory_jsonl_roundtrip_preserves_decimal_and_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nested" / "source_inventory.jsonl"
    evidence = SourceEvidence(
        source="akshare",
        adapter="akshare",
        function="stock_financial_hk_report_em",
        artifact_id="artifact-1",
        raw_record_id="00001:balance_sheet:2024",
        raw_field_name="Total assets",
        raw_field_code="STD_ITEM_CODE",
    )
    record = SourceInventoryRecord(
        source="akshare",
        market="HK",
        ticker="00001",
        statement_type="balance_sheet",
        period="2024-12-31",
        raw_field_name="Total assets",
        raw_field_code="STD_ITEM_CODE",
        raw_value="100",
        parsed_numeric_value=Decimal("100"),
        currency="HKD",
        unit="HKD",
        source_evidence=(evidence,),
    )

    write_source_inventory(path, (record,))
    records = read_source_inventory(path)

    assert len(records) == 1
    assert records[0].parsed_numeric_value == Decimal("100")
    assert records[0].source_evidence[0].raw_field_code == "STD_ITEM_CODE"
