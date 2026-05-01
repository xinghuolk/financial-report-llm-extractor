from decimal import Decimal
import json
from pathlib import Path

from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportItem,
    SourceFirstExportResult,
)
from financial_report_llm_extractor.structured_sources.models import SourceEvidence
from financial_report_llm_extractor.structured_sources.pdf_supplement import (
    apply_pdf_evidence_supplement,
    build_pdf_evidence_supplement,
    write_pdf_evidence_supplement,
)


def test_pdf_supplement_retrieves_evidence_for_needed_fields_only() -> None:
    export = _export_result(
        {
            "cash": _item("cash", status="needs_pdf_evidence", value=Decimal("20")),
            "revenue": _item("revenue", status="present", value=Decimal("100")),
        }
    )
    chunks = [
        _chunk(
            "chunk-cash",
            "cash and cash equivalents 20",
            field_text="Cash and cash equivalents 20",
        ),
        _chunk("chunk-revenue", "revenue 100", field_text="Revenue 100"),
    ]

    supplement = build_pdf_evidence_supplement(export, chunks)

    assert tuple(supplement.items) == ("cash",)
    item = supplement.items["cash"]
    assert item.status == "pdf_evidence_found"
    assert item.pdf_evidence[0].page == 10
    assert item.pdf_evidence[0].chunk_id == "chunk-cash"
    assert item.pdf_evidence[0].block_id == "p0010_b0001"
    assert item.pdf_evidence[0].snippet == "Cash and cash equivalents 20"


def test_pdf_supplement_marks_missing_pdf_evidence() -> None:
    export = _export_result(
        {"cash": _item("cash", status="needs_pdf_evidence", value=Decimal("20"))}
    )

    supplement = build_pdf_evidence_supplement(export, [])

    item = supplement.items["cash"]
    assert item.status == "missing_pdf_evidence"
    assert item.pdf_evidence == ()
    assert item.errors == ("no pdf retrieval candidates found",)


def test_pdf_supplement_records_value_mentioned_consistency() -> None:
    export = _export_result(
        {"cash": _item("cash", status="needs_pdf_evidence", value=Decimal("20"))}
    )

    supplement = build_pdf_evidence_supplement(
        export,
        [_chunk("chunk-cash", "cash and cash equivalents 20")],
    )

    assert supplement.items["cash"].consistency_status == "value_mentioned"


def test_pdf_supplement_records_value_not_found_consistency() -> None:
    export = _export_result(
        {"cash": _item("cash", status="needs_pdf_evidence", value=Decimal("20"))}
    )

    supplement = build_pdf_evidence_supplement(
        export,
        [_chunk("chunk-cash", "cash and cash equivalents")],
    )

    assert (
        supplement.items["cash"].consistency_status
        == "value_not_found_in_snippet"
    )


def test_apply_pdf_evidence_supplement_updates_export_result() -> None:
    export = _export_result(
        {"cash": _item("cash", status="needs_pdf_evidence", value=Decimal("20"))},
        profile="pdf_required",
    )
    supplement = build_pdf_evidence_supplement(
        export,
        [_chunk("chunk-cash", "cash and cash equivalents 20")],
    )

    updated = apply_pdf_evidence_supplement(export, supplement)

    assert updated.items["cash"].status == "present"
    assert updated.items["cash"].source_evidence == export.items["cash"].source_evidence
    assert updated.items["cash"].pdf_evidence[0].snippet == "cash and cash equivalents 20"


def test_write_pdf_evidence_supplement_writes_json(tmp_path: Path) -> None:
    export = _export_result(
        {"cash": _item("cash", status="needs_pdf_evidence", value=Decimal("20"))}
    )
    supplement = build_pdf_evidence_supplement(
        export,
        [_chunk("chunk-cash", "cash and cash equivalents 20")],
    )

    path = write_pdf_evidence_supplement(
        supplement,
        tmp_path / "pdf_evidence_supplement.json",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "pdf_evidence_supplement.json"
    assert payload["items"]["cash"]["status"] == "pdf_evidence_found"
    assert payload["items"]["cash"]["pdf_evidence"][0]["block_id"] == "p0010_b0001"


def _export_result(
    items: dict[str, SourceFirstExportItem],
    *,
    profile: str = "pdf_required",
) -> SourceFirstExportResult:
    return SourceFirstExportResult(
        profile=profile,  # type: ignore[arg-type]
        catalog_id="test",
        catalog_version="1",
        items=items,
    )


def _item(
    field_id: str,
    *,
    status: str,
    value: Decimal,
) -> SourceFirstExportItem:
    return SourceFirstExportItem(
        field_id=field_id,
        status=status,  # type: ignore[arg-type]
        value=value,
        normalized_value=value,
        currency="CNY",
        unit="yuan",
        period="2024-12-31",
        scope="consolidated",
        source_evidence=(
            SourceEvidence(
                source="akshare",
                adapter="akshare",
                function="fixture",
                artifact_id="akshare_artifact",
                raw_record_id=f"akshare:{field_id}",
                raw_field_name=field_id,
            ),
        ),
    )


def _chunk(
    chunk_id: str,
    text: str,
    *,
    field_text: str | None = None,
) -> dict[str, object]:
    block_text = field_text or text
    return {
        "record_type": "chunk",
        "chunk_id": chunk_id,
        "kind": "statement_table",
        "statement_kind": "balance_sheet",
        "page_start": 10,
        "page_end": 10,
        "block_ids": ["p0010_b0001"],
        "block_texts": {"p0010_b0001": block_text},
        "text": text,
    }
