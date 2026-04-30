import json
from pathlib import Path
from typing import Any

from financial_report_llm_extractor.retrieval import (
    load_field_specs,
    retrieve_candidates,
    write_retrieval_probe,
)


def test_load_field_specs_enriches_p0_p1_aliases_and_statement_hints(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "catalog_id": "test_catalog",
                "version": "v1",
                "priorities": [
                    {"priority": "P0", "name": "core", "fields": ["revenue"]},
                    {"priority": "P1", "name": "enhanced", "fields": ["gross_profit"]},
                    {"priority": "P2", "name": "later", "fields": ["dps"]},
                ],
            }
        ),
        encoding="utf-8",
    )

    specs = load_field_specs(catalog_path, priorities=("P0", "P1"))

    assert [spec.field_id for spec in specs] == ["revenue", "gross_profit"]
    revenue = specs[0]
    assert revenue.priority == "P0"
    assert "revenue" in revenue.aliases
    assert "营业收入" in revenue.aliases
    assert revenue.statement_hints == ("income_statement",)


def test_retrieve_candidates_scores_alias_and_statement_matches() -> None:
    chunks: list[dict[str, Any]] = [
        {
            "record_type": "chunk",
            "chunk_id": "stmt_income_statement_p0005_p0005",
            "kind": "statement_table",
            "statement_kind": "income_statement",
            "page_start": 5,
            "page_end": 5,
            "block_ids": ["p0005_b0001"],
            "text": "营业收入 100\n营业成本 60",
        },
        {
            "record_type": "chunk",
            "chunk_id": "page_p0010",
            "kind": "page_text",
            "statement_kind": None,
            "page_start": 10,
            "page_end": 10,
            "block_ids": ["p0010_b0001"],
            "text": "Company profile and revenue discussion",
        },
    ]

    candidates = retrieve_candidates("revenue", chunks, limit=2)

    assert [candidate.chunk_id for candidate in candidates] == [
        "stmt_income_statement_p0005_p0005",
        "page_p0010",
    ]
    assert candidates[0].score > candidates[1].score
    assert candidates[0].matched_aliases == ("营业收入",)
    assert candidates[0].evidence["page"] == 5
    assert candidates[0].evidence["chunk_id"] == "stmt_income_statement_p0005_p0005"
    assert candidates[0].evidence["block_id"] == "p0005_b0001"
    assert candidates[0].evidence["snippet"] == "营业收入 100"


def test_retrieve_candidates_uses_matching_block_for_evidence() -> None:
    chunks: list[dict[str, Any]] = [
        {
            "record_type": "chunk",
            "chunk_id": "stmt_balance_sheet_p0005_p0005",
            "kind": "statement_table",
            "statement_kind": "balance_sheet",
            "page_start": 5,
            "page_end": 5,
            "block_ids": ["p0005_b0001", "p0005_b0002"],
            "text": "Revenue 100\nCash and cash equivalents 30",
            "block_texts": {
                "p0005_b0001": "Revenue 100",
                "p0005_b0002": "Cash and cash equivalents 30",
            },
        }
    ]

    candidates = retrieve_candidates("cash", chunks)

    assert candidates[0].evidence["block_id"] == "p0005_b0002"
    assert candidates[0].evidence["snippet"] == "Cash and cash equivalents 30"


def test_write_retrieval_probe_marks_missing_fields_explicitly(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    chunks_path = tmp_path / "chunks.jsonl"
    output_path = tmp_path / "retrieval_probe.json"

    catalog_path.write_text(
        json.dumps(
            {
                "catalog_id": "test_catalog",
                "version": "v1",
                "priorities": [
                    {"priority": "P0", "name": "core", "fields": ["revenue", "cash"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    chunks_path.write_text(
        json.dumps(
            {
                "record_type": "chunk",
                "source_pdf_hash": "hash123",
                "chunk_id": "stmt_income_statement_p0005_p0005",
                "kind": "statement_table",
                "statement_kind": "income_statement",
                "page_start": 5,
                "page_end": 5,
                "block_ids": ["p0005_b0001"],
                "text": "Revenue 100",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = write_retrieval_probe(
        catalog_path,
        chunks_path,
        output_path=output_path,
        priorities=("P0",),
    )

    assert result.output_path == output_path
    assert result.field_count == 2

    probe = json.loads(output_path.read_text(encoding="utf-8"))
    assert probe["catalog_id"] == "test_catalog"
    assert probe["source_pdf_hash"] == "hash123"
    assert probe["fields"][0]["field_id"] == "revenue"
    assert probe["fields"][0]["status"] == "candidates_found"
    assert probe["fields"][1]["field_id"] == "cash"
    assert probe["fields"][1]["status"] == "missing"
    assert probe["fields"][1]["candidates"] == []
