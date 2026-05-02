import json
from decimal import Decimal
from pathlib import Path

import pytest

from financial_report_llm_extractor.structured_sources.artifacts import (
    SourceArtifactManifest,
    SourceArtifactStore,
    build_artifact_id,
    read_source_artifact_manifest,
    read_source_inventory,
    write_source_artifact_manifest,
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


def test_read_source_inventory_rejects_non_object_line_with_line_number(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source inventory line 1 must be an object"):
        read_source_inventory(path)


def test_read_source_inventory_rejects_non_list_source_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = {
        "source": "akshare",
        "market": "HK",
        "ticker": "00001",
        "statement_type": "balance_sheet",
        "period": "2024-12-31",
        "raw_field_name": "Total assets",
        "raw_value": "100",
        "parsed_numeric_value": "100",
        "currency": "HKD",
        "unit": "HKD",
        "source_evidence": {},
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="source inventory line 1 source_evidence must be a list",
    ):
        read_source_inventory(path)


def test_read_source_inventory_rejects_invalid_parsed_numeric_value_with_line_number(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = {
        "source": "akshare",
        "market": "HK",
        "ticker": "00001",
        "statement_type": "balance_sheet",
        "period": "2024-12-31",
        "raw_field_name": "Total assets",
        "raw_value": "not numeric",
        "parsed_numeric_value": "not numeric",
        "currency": "HKD",
        "unit": "HKD",
        "source_evidence": [
            {
                "source": "akshare",
                "adapter": "akshare",
                "function": "stock_financial_hk_report_em",
                "artifact_id": "artifact-1",
                "raw_record_id": "00001:balance_sheet:2024",
                "raw_field_name": "Total assets",
            }
        ],
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="source inventory line 1 parsed_numeric_value is invalid",
    ):
        read_source_inventory(path)


def test_read_source_inventory_rejects_non_finite_parsed_numeric_value(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = {
        "source": "akshare",
        "market": "HK",
        "ticker": "00001",
        "statement_type": "balance_sheet",
        "period": "2024-12-31",
        "raw_field_name": "Total assets",
        "raw_value": "NaN",
        "parsed_numeric_value": "NaN",
        "currency": "HKD",
        "unit": "HKD",
        "source_evidence": [
            {
                "source": "akshare",
                "adapter": "akshare",
                "function": "stock_financial_hk_report_em",
                "artifact_id": "artifact-1",
                "raw_record_id": "00001:balance_sheet:2024",
                "raw_field_name": "Total assets",
            }
        ],
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="source inventory line 1 parsed_numeric_value is invalid",
    ):
        read_source_inventory(path)


def test_read_source_inventory_rejects_source_evidence_extra_key_with_path(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = {
        "source": "akshare",
        "market": "HK",
        "ticker": "00001",
        "statement_type": "balance_sheet",
        "period": "2024-12-31",
        "raw_field_name": "Total assets",
        "raw_value": "100",
        "parsed_numeric_value": "100",
        "currency": "HKD",
        "unit": "HKD",
        "source_evidence": [
            {
                "source": "akshare",
                "adapter": "akshare",
                "function": "stock_financial_hk_report_em",
                "artifact_id": "artifact-1",
                "raw_record_id": "00001:balance_sheet:2024",
                "raw_field_name": "Total assets",
                "extra": "unexpected",
            }
        ],
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="source inventory line 1 source_evidence\\[0\\]",
    ):
        read_source_inventory(path)


def test_read_source_inventory_rejects_source_evidence_missing_key_with_path(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = {
        "source": "akshare",
        "market": "HK",
        "ticker": "00001",
        "statement_type": "balance_sheet",
        "period": "2024-12-31",
        "raw_field_name": "Total assets",
        "raw_value": "100",
        "parsed_numeric_value": "100",
        "currency": "HKD",
        "unit": "HKD",
        "source_evidence": [
            {
                "source": "akshare",
                "adapter": "akshare",
                "function": "stock_financial_hk_report_em",
                "raw_record_id": "00001:balance_sheet:2024",
                "raw_field_name": "Total assets",
            }
        ],
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="source inventory line 1 source_evidence\\[0\\] artifact_id is required",
    ):
        read_source_inventory(path)


def test_source_artifact_manifest_roundtrip_includes_hash_and_sorts_entries(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path)
    second = store.write_json(
        source="yahoo",
        artifact_id="yahoo_hk_00001_income_statement",
        payload={"rows": [{"field": "Total Revenue", "value": 10}]},
    )
    first = store.write_json(
        source="akshare",
        artifact_id="akshare_hk_00001_balance_sheet",
        payload={"rows": [{"field": "Total assets", "value": 100}]},
    )
    manifest_path = tmp_path / "source_artifact_manifest.json"

    manifest = write_source_artifact_manifest(
        manifest_path,
        artifact_root=tmp_path,
        artifacts=(second, first),
    )
    loaded = read_source_artifact_manifest(manifest_path)

    assert loaded.manifest_id == manifest.manifest_id
    assert [entry.artifact_id for entry in loaded.artifacts] == [
        "akshare_hk_00001_balance_sheet",
        "yahoo_hk_00001_income_statement",
    ]
    assert all(len(entry.sha256) == 64 for entry in loaded.artifacts)
    assert loaded.artifacts[0].path == "akshare/akshare_hk_00001_balance_sheet.json"


def test_source_artifact_manifest_requires_artifact_root() -> None:
    manifest = SourceArtifactManifest(
        manifest_id="source_artifact_manifest",
        version="1",
        artifact_root="",
        artifacts=(),
    )

    with pytest.raises(ValueError, match="artifact_root"):
        manifest.validate()


def test_read_source_artifact_manifest_rejects_non_object_payload(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_artifact_manifest.json"
    path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source artifact manifest must be an object"):
        read_source_artifact_manifest(path)


def test_read_source_artifact_manifest_rejects_duplicate_artifact_id(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_artifact_manifest.json"
    entry = {
        "source": "akshare",
        "artifact_id": "artifact_1",
        "path": "akshare/artifact_1.json",
        "content_type": "application/json",
        "sha256": "a" * 64,
    }
    path.write_text(
        json.dumps(
            {
                "manifest_id": "source_artifact_manifest",
                "version": "1",
                "artifact_root": tmp_path.as_posix(),
                "artifacts": [entry, entry],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate artifact_id: artifact_1"):
        read_source_artifact_manifest(path)


def test_read_source_artifact_manifest_rejects_non_list_artifacts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_artifact_manifest.json"
    path.write_text(
        json.dumps(
            {
                "manifest_id": "source_artifact_manifest",
                "version": "1",
                "artifact_root": tmp_path.as_posix(),
                "artifacts": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source artifact manifest artifacts must be a list"):
        read_source_artifact_manifest(path)


def test_read_source_artifact_manifest_rejects_missing_manifest_id(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_artifact_manifest.json"
    path.write_text(
        json.dumps(
            {
                "version": "1",
                "artifact_root": tmp_path.as_posix(),
                "artifacts": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source artifact manifest manifest_id is required"):
        read_source_artifact_manifest(path)


def test_read_source_artifact_manifest_rejects_artifact_extra_key(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_artifact_manifest.json"
    path.write_text(
        json.dumps(
            {
                "manifest_id": "source_artifact_manifest",
                "version": "1",
                "artifact_root": tmp_path.as_posix(),
                "artifacts": [
                    {
                        "source": "akshare",
                        "artifact_id": "artifact_1",
                        "path": "akshare/artifact_1.json",
                        "content_type": "application/json",
                        "sha256": "a" * 64,
                        "extra": "unexpected",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source artifact manifest artifacts\\[0\\]"):
        read_source_artifact_manifest(path)


def test_read_source_artifact_manifest_rejects_artifact_non_string_sha256(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_artifact_manifest.json"
    path.write_text(
        json.dumps(
            {
                "manifest_id": "source_artifact_manifest",
                "version": "1",
                "artifact_root": tmp_path.as_posix(),
                "artifacts": [
                    {
                        "source": "akshare",
                        "artifact_id": "artifact_1",
                        "path": "akshare/artifact_1.json",
                        "content_type": "application/json",
                        "sha256": 123,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sha256"):
        read_source_artifact_manifest(path)
