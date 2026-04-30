import json
from pathlib import Path

from financial_report_llm_extractor.statement_discovery import (
    write_catalog_mapping,
    write_row_inventory,
    write_statement_map,
)


def test_write_statement_map_detects_formal_statement_chunks(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    document_map_path = tmp_path / "document_map.json"
    output_path = tmp_path / "statement_map.json"
    records = [
        _chunk(
            "stmt_summary_income_p0006_p0006",
            "income_statement",
            6,
            "Consolidated Income Statement\nRevenue 999",
            ["p0006_b0001"],
            {"p0006_b0001": "Consolidated Income Statement\nRevenue 999"},
        ),
        _chunk(
            "stmt_income_p0134_p0134",
            "income_statement",
            134,
            "CONSOLIDATED INCOME STATEMENT\nFor the year ended 31 December 2025\n"
            "2025 2024\n$ Million\nRevenue 100 90\n"
            "Profit attributable to shareholders 20 18",
            ["p0134_b0001"],
            {
                "p0134_b0001": (
                    "CONSOLIDATED INCOME STATEMENT\n"
                    "For the year ended 31 December 2025\n"
                    "2025 2024\n$ Million\nRevenue 100 90"
                )
            },
        ),
        _chunk(
            "stmt_balance_sheet_p0138_p0138",
            "balance_sheet",
            138,
            "CONSOLIDATED STATEMENT OF FINANCIAL POSITION\n"
            "2025 2024\n$ Million\nTotal assets 200 180\n"
            "Total liabilities 120 100",
            ["p0138_b0001"],
            {"p0138_b0001": "CONSOLIDATED STATEMENT OF FINANCIAL POSITION"},
        ),
        _chunk(
            "stmt_cash_flow_p0142_p0142",
            "cash_flow",
            142,
            "CONSOLIDATED STATEMENT OF CASH FLOWS\n"
            "2025 2024\n$ Million\nNet cash from operating activities 30 25",
            ["p0142_b0001"],
            {"p0142_b0001": "CONSOLIDATED STATEMENT OF CASH FLOWS"},
        ),
    ]
    chunks_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    document_map_path.write_text(
        json.dumps(
            {
                "sections": [
                    {
                        "kind": "audited_financial_statements",
                        "page_start": 130,
                        "page_end": 145,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = write_statement_map(
        chunks_path,
        document_map_path,
        output_path=output_path,
    )

    assert result.output_path == output_path
    assert result.statement_count == 3
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    statements = payload["statements"]
    assert [statement["statement_kind"] for statement in statements] == [
        "income_statement",
        "balance_sheet",
        "cash_flow",
    ]
    assert statements[0]["statement_id"] == "stmt_0001_income_statement"
    assert statements[0]["chunk_id"] == "stmt_income_p0134_p0134"
    assert statements[0]["unit_context"] == "$ Million"
    assert statements[0]["period_columns"] == ["2025", "2024"]
    assert statements[0]["evidence_blocks"] == ["p0134_b0001"]


def test_write_row_inventory_extracts_statement_rows(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    statement_map_path = tmp_path / "statement_map.json"
    output_path = tmp_path / "row_inventory.json"
    chunks_path.write_text(
        json.dumps(
            _chunk(
                "stmt_income_p0134_p0134",
                "income_statement",
                134,
                "CONSOLIDATED INCOME STATEMENT\n2025 2024\n$ Million\n"
                "Revenue 100 90\nProfit attributable to shareholders 20 18",
                ["p0134_b0001", "p0134_b0002"],
                {
                    "p0134_b0001": "CONSOLIDATED INCOME STATEMENT\n2025 2024\n$ Million",
                    "p0134_b0002": (
                        "Revenue 100 90\n"
                        "Profit attributable to shareholders 20 18"
                    ),
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )
    statement_map_path.write_text(
        json.dumps(
            {
                "statements": [
                    {
                        "statement_id": "stmt_0001_income_statement",
                        "statement_kind": "income_statement",
                        "unit_context": "$ Million",
                        "period_columns": ["2025", "2024"],
                        "chunk_id": "stmt_income_p0134_p0134",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = write_row_inventory(
        chunks_path,
        statement_map_path,
        output_path=output_path,
    )

    assert result.output_path == output_path
    assert result.row_count == 2
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    rows = payload["rows"]
    assert rows[0]["statement_id"] == "stmt_0001_income_statement"
    assert rows[0]["row_label"] == "Revenue"
    assert rows[0]["values"] == [{"period": "2025", "value_raw": "100"}]
    assert rows[0]["unit_context"] == "$ Million"
    assert rows[0]["currency_hint"] == "HKD"
    assert rows[0]["evidence"][0]["page"] == 134
    assert rows[0]["evidence"][0]["block_id"] == "p0134_b0002"
    assert rows[0]["evidence"][0]["snippet"] == "Revenue 100 90"


def test_write_catalog_mapping_maps_selected_fields(tmp_path: Path) -> None:
    row_inventory_path = tmp_path / "row_inventory.json"
    output_path = tmp_path / "catalog_mapping.json"
    row_inventory_path.write_text(
        json.dumps(
            {
                "rows": [
                    _row("stmt_income", "income_statement", "Revenue", "100"),
                    _row(
                        "stmt_income",
                        "income_statement",
                        "Profit attributable to shareholders",
                        "20",
                    ),
                    _row("stmt_balance", "balance_sheet", "Total assets", "200"),
                    _row("stmt_balance", "balance_sheet", "Total liabilities", "120"),
                    _row(
                        "stmt_cash",
                        "cash_flow",
                        "Net cash from operating activities",
                        "30",
                    ),
                ]
            }
        ),
        encoding="utf-8",
    )

    result = write_catalog_mapping(
        row_inventory_path,
        selected_fields=(
            "revenue",
            "net_profit",
            "total_assets",
            "total_liabilities",
            "operating_cash_flow",
            "cash",
        ),
        output_path=output_path,
    )

    assert result.output_path == output_path
    assert result.mapping_count == 6
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    mappings = {mapping["field_id"]: mapping for mapping in payload["mappings"]}
    assert mappings["revenue"]["status"] == "mapped"
    assert mappings["revenue"]["source_row_label"] == "Revenue"
    assert mappings["revenue"]["statement_id"] == "stmt_income"
    assert mappings["revenue"]["mapping_confidence"] == 0.9
    assert mappings["revenue"]["evidence"][0]["snippet"] == "Revenue 100"
    assert mappings["cash"]["status"] == "missing"
    assert mappings["cash"]["evidence"] == []


def _chunk(
    chunk_id: str,
    statement_kind: str,
    page: int,
    text: str,
    block_ids: list[str],
    block_texts: dict[str, str],
) -> dict[str, object]:
    return {
        "record_type": "chunk",
        "source_pdf_hash": "hash123",
        "chunk_id": chunk_id,
        "kind": "statement_table",
        "statement_kind": statement_kind,
        "page_start": page,
        "page_end": page,
        "block_ids": block_ids,
        "block_texts": block_texts,
        "text": text,
    }


def _row(
    statement_id: str,
    statement_kind: str,
    row_label: str,
    value_raw: str,
) -> dict[str, object]:
    return {
        "statement_id": statement_id,
        "statement_kind": statement_kind,
        "row_label": row_label,
        "values": [{"period": "2025", "value_raw": value_raw}],
        "unit_context": "$ Million",
        "currency_hint": "HKD",
        "evidence": [
            {
                "page": 1,
                "block_id": f"{statement_id}_block",
                "snippet": f"{row_label} {value_raw}",
            }
        ],
    }
