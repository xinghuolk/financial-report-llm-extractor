import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from financial_report_llm_extractor.structured_sources.artifacts import (
    SourceArtifactManifest,
    SourceArtifactManifestEntry,
    SourceArtifactStore,
    build_artifact_id,
    read_source_artifact_manifest,
    read_source_inventory,
    validate_source_inventory_artifacts,
    write_source_artifact_manifest,
    write_source_inventory,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceArtifact,
    SourceEvidence,
    SourceInventoryRecord,
)


def _valid_source_inventory_payload() -> dict[str, object]:
    return {
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
            }
        ],
    }


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


def test_build_artifact_id_rejects_parts_that_slug_to_empty() -> None:
    with pytest.raises(ValueError, match="market cannot be converted to artifact id"):
        build_artifact_id(
            source="fixture",
            market="!!!",
            ticker="00001",
            artifact_type="balance_sheet",
        )


def test_source_artifact_store_rejects_path_traversal_artifact_id(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path)

    with pytest.raises(ValueError, match="artifact_id must be a slug segment"):
        store.write_json(source="akshare", artifact_id="../escape", payload={"x": 1})

    assert not (tmp_path / "escape.json").exists()


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


def test_read_source_inventory_reports_physical_line_number_after_blank_line(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    path.write_text("\n[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source inventory line 2 must be an object"):
        read_source_inventory(path)


def test_read_source_inventory_rejects_non_list_source_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload: dict[str, object] = {
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


def test_read_source_inventory_rejects_missing_top_level_required_key(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = _valid_source_inventory_payload()
    del payload["source"]
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source inventory line 1 source is required"):
        read_source_inventory(path)


def test_read_source_inventory_rejects_top_level_extra_key(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = _valid_source_inventory_payload()
    payload["extra"] = "unexpected"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="source inventory line 1 has unsupported keys: extra",
    ):
        read_source_inventory(path)


def test_read_source_inventory_rejects_non_string_top_level_required_field(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = _valid_source_inventory_payload()
    payload["market"] = 1
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="source inventory line 1 market must be a string",
    ):
        read_source_inventory(path)


def test_read_source_inventory_rejects_non_string_source_evidence_required_field(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = _valid_source_inventory_payload()
    source_evidence = payload["source_evidence"]
    assert isinstance(source_evidence, list)
    source_evidence[0]["artifact_id"] = ["artifact-1"]
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="source inventory line 1 source_evidence\\[0\\] artifact_id must be a string",
    ):
        read_source_inventory(path)


def test_read_source_inventory_rejects_non_string_raw_field_name(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = _valid_source_inventory_payload()
    payload["raw_field_name"] = []
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="source inventory line 1 raw_field_name must be a string",
    ):
        read_source_inventory(path)


def test_read_source_inventory_rejects_invalid_raw_value_type(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = _valid_source_inventory_payload()
    payload["raw_value"] = {}
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="source inventory line 1 raw_value must be a finite string, number, or null",
    ):
        read_source_inventory(path)


def test_read_source_inventory_rejects_non_finite_raw_value(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    path.write_text(
        '{"source":"akshare","market":"HK","ticker":"00001",'
        '"statement_type":"balance_sheet","period":"2024-12-31",'
        '"raw_field_name":"Total assets","raw_value":NaN,'
        '"currency":"HKD","unit":"HKD",'
        '"source_evidence":[{"source":"akshare","adapter":"akshare",'
        '"function":"stock_financial_hk_report_em","artifact_id":"artifact-1",'
        '"raw_record_id":"00001:balance_sheet:2024",'
        '"raw_field_name":"Total assets"}]}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="source inventory line 1 raw_value must be a finite string, number, or null",
    ):
        read_source_inventory(path)


def test_read_source_inventory_allows_empty_raw_field_name_for_non_present_status(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload: dict[str, object] = {
        "source": "akshare",
        "market": "HK",
        "ticker": "00001",
        "statement_type": "balance_sheet",
        "period": None,
        "raw_field_name": "",
        "raw_value": None,
        "source_status": "missing",
        "currency": "unknown",
        "source_evidence": [],
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    records = read_source_inventory(path)

    assert records[0].source_status == "missing"
    assert records[0].raw_field_name == ""


def test_read_source_inventory_rejects_unsupported_source_value(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = _valid_source_inventory_payload()
    payload["source"] = "bogus"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="source inventory line 1 source has unsupported value: bogus",
    ):
        read_source_inventory(path)


def test_read_source_inventory_rejects_unsupported_value_type(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = _valid_source_inventory_payload()
    payload["value_type"] = "bogus"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="source inventory line 1 value_type has unsupported value: bogus",
    ):
        read_source_inventory(path)


def test_read_source_inventory_rejects_unsupported_currency(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = _valid_source_inventory_payload()
    payload["currency"] = "EUR"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="source inventory line 1 currency has unsupported value: EUR",
    ):
        read_source_inventory(path)


def test_read_source_inventory_rejects_unsupported_source_evidence_source(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = _valid_source_inventory_payload()
    source_evidence = payload["source_evidence"]
    assert isinstance(source_evidence, list)
    source_evidence[0]["source"] = "bogus"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="source inventory line 1 source_evidence\\[0\\] source has unsupported value: bogus",
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


def test_read_source_artifact_manifest_rejects_unsupported_artifact_source(
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
                        "source": "bogus",
                        "artifact_id": "artifact_1",
                        "path": "bogus/artifact_1.json",
                        "content_type": "application/json",
                        "sha256": "a" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source has unsupported value: bogus"):
        read_source_artifact_manifest(path)


def test_write_source_artifact_manifest_rejects_artifact_path_before_reading(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}_outside_artifact.json"
    outside.write_text('{"secret": true}\n', encoding="utf-8")
    artifact = SourceArtifact(
        source="akshare",
        artifact_id="artifact_1",
        path=f"../{outside.name}",
        content_type="application/json",
    )

    try:
        with pytest.raises(ValueError, match="path must be relative"):
            write_source_artifact_manifest(
                tmp_path / "source_artifact_manifest.json",
                artifact_root=tmp_path,
                artifacts=(artifact,),
            )
    finally:
        outside.unlink(missing_ok=True)


def test_validate_source_inventory_artifacts_accepts_matching_manifest(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path)
    artifact = store.write_json(
        source="akshare",
        artifact_id="akshare_hk_00001_balance_sheet",
        payload={"rows": [{"field": "Total assets", "value": 100}]},
    )
    manifest = write_source_artifact_manifest(
        tmp_path / "source_artifact_manifest.json",
        artifact_root=tmp_path,
        artifacts=(artifact,),
    )
    evidence = SourceEvidence(
        source="akshare",
        adapter="akshare",
        function="stock_financial_hk_report_em",
        artifact_id=artifact.artifact_id,
        raw_record_id="00001:balance_sheet:2024",
        raw_field_name="Total assets",
    )
    record = SourceInventoryRecord(
        source="akshare",
        market="HK",
        ticker="00001",
        statement_type="balance_sheet",
        period="2024-12-31",
        raw_field_name="Total assets",
        raw_value="100",
        parsed_numeric_value=Decimal("100"),
        currency="HKD",
        unit="HKD",
        source_evidence=(evidence,),
    )

    validate_source_inventory_artifacts(manifest, (record,), tmp_path)


def test_validate_source_inventory_artifacts_rejects_missing_artifact_id(
    tmp_path: Path,
) -> None:
    manifest = write_source_artifact_manifest(
        tmp_path / "source_artifact_manifest.json",
        artifact_root=tmp_path,
        artifacts=(),
    )
    evidence = SourceEvidence(
        source="akshare",
        adapter="akshare",
        function="stock_financial_hk_report_em",
        artifact_id="missing_artifact",
        raw_record_id="00001:balance_sheet:2024",
        raw_field_name="Total assets",
    )
    record = SourceInventoryRecord(
        source="akshare",
        market="HK",
        ticker="00001",
        statement_type="balance_sheet",
        period="2024-12-31",
        raw_field_name="Total assets",
        raw_value="100",
        parsed_numeric_value=Decimal("100"),
        currency="HKD",
        unit="HKD",
        source_evidence=(evidence,),
    )

    with pytest.raises(ValueError, match="missing_artifact"):
        validate_source_inventory_artifacts(manifest, (record,), tmp_path)


def test_validate_source_inventory_artifacts_rejects_missing_artifact_file(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path)
    artifact = store.write_json(
        source="akshare",
        artifact_id="akshare_hk_00001_balance_sheet",
        payload={"rows": [{"field": "Total assets", "value": 100}]},
    )
    manifest = write_source_artifact_manifest(
        tmp_path / "source_artifact_manifest.json",
        artifact_root=tmp_path,
        artifacts=(artifact,),
    )
    (tmp_path / artifact.path).unlink()
    evidence = SourceEvidence(
        source="akshare",
        adapter="akshare",
        function="stock_financial_hk_report_em",
        artifact_id=artifact.artifact_id,
        raw_record_id="00001:balance_sheet:2024",
        raw_field_name="Total assets",
    )
    record = SourceInventoryRecord(
        source="akshare",
        market="HK",
        ticker="00001",
        statement_type="balance_sheet",
        period="2024-12-31",
        raw_field_name="Total assets",
        raw_value="100",
        parsed_numeric_value=Decimal("100"),
        currency="HKD",
        unit="HKD",
        source_evidence=(evidence,),
    )

    with pytest.raises(ValueError, match=artifact.artifact_id):
        validate_source_inventory_artifacts(manifest, (record,), tmp_path)


def test_validate_source_inventory_artifacts_rejects_artifact_hash_mismatch(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path)
    artifact = store.write_json(
        source="akshare",
        artifact_id="akshare_hk_00001_balance_sheet",
        payload={"rows": [{"field": "Total assets", "value": 100}]},
    )
    manifest = write_source_artifact_manifest(
        tmp_path / "source_artifact_manifest.json",
        artifact_root=tmp_path,
        artifacts=(artifact,),
    )
    (tmp_path / artifact.path).write_text('{"changed": true}\n', encoding="utf-8")
    evidence = SourceEvidence(
        source="akshare",
        adapter="akshare",
        function="stock_financial_hk_report_em",
        artifact_id=artifact.artifact_id,
        raw_record_id="00001:balance_sheet:2024",
        raw_field_name="Total assets",
    )
    record = SourceInventoryRecord(
        source="akshare",
        market="HK",
        ticker="00001",
        statement_type="balance_sheet",
        period="2024-12-31",
        raw_field_name="Total assets",
        raw_value="100",
        parsed_numeric_value=Decimal("100"),
        currency="HKD",
        unit="HKD",
        source_evidence=(evidence,),
    )

    with pytest.raises(ValueError, match=artifact.artifact_id):
        validate_source_inventory_artifacts(manifest, (record,), tmp_path)


def test_validate_source_inventory_artifacts_rejects_symlink_escape(
    tmp_path: Path,
) -> None:
    external_dir = tmp_path.parent / f"{tmp_path.name}_external"
    external_dir.mkdir()
    external_file = external_dir / "artifact.json"
    external_file.write_text('{"rows": [{"field": "Total assets", "value": 100}]}\n', encoding="utf-8")
    symlink_path = tmp_path / "akshare"
    try:
        symlink_path.symlink_to(external_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks are not supported: {exc}")

    artifact_id = "akshare_hk_00001_balance_sheet"
    manifest = SourceArtifactManifest(
        manifest_id="source_artifact_manifest",
        version="1",
        artifact_root=tmp_path.as_posix(),
        artifacts=(
            SourceArtifactManifestEntry(
                source="akshare",
                artifact_id=artifact_id,
                path="akshare/artifact.json",
                content_type="application/json",
                sha256=hashlib.sha256(external_file.read_bytes()).hexdigest(),
            ),
        ),
    )
    evidence = SourceEvidence(
        source="akshare",
        adapter="akshare",
        function="stock_financial_hk_report_em",
        artifact_id=artifact_id,
        raw_record_id="00001:balance_sheet:2024",
        raw_field_name="Total assets",
    )
    record = SourceInventoryRecord(
        source="akshare",
        market="HK",
        ticker="00001",
        statement_type="balance_sheet",
        period="2024-12-31",
        raw_field_name="Total assets",
        raw_value="100",
        parsed_numeric_value=Decimal("100"),
        currency="HKD",
        unit="HKD",
        source_evidence=(evidence,),
    )

    with pytest.raises(ValueError, match=artifact_id):
        validate_source_inventory_artifacts(manifest, (record,), tmp_path)
