import json
from pathlib import Path

from financial_report_llm_extractor.chunking import (
    build_chunk_store,
    chunk_pages,
    detect_statement_kind,
    split_page_blocks,
)
from financial_report_llm_extractor.ingestion import PageRecord


def test_split_page_blocks_creates_stable_text_block_ids() -> None:
    blocks = split_page_blocks(
        PageRecord(
            page=12,
            text="Consolidated Statement of Profit or Loss\n\nRevenue 100\n\nProfit 20",
        )
    )

    assert [block.block_id for block in blocks] == ["p0012_b0001", "p0012_b0002"]
    assert [block.page for block in blocks] == [12, 12]
    assert [block.kind for block in blocks] == ["layout_line", "layout_line"]
    assert [block.text for block in blocks] == [
        "Consolidated Statement of Profit or Loss\nRevenue 100",
        "Profit 20",
    ]


def test_detect_statement_kind_supports_cn_and_hk_titles() -> None:
    assert detect_statement_kind("合并资产负债表") == "balance_sheet"
    assert detect_statement_kind("Consolidated Statement of Profit or Loss") == (
        "income_statement"
    )
    assert detect_statement_kind("Consolidated Cash Flow Statement") == "cash_flow"
    assert detect_statement_kind("Notes to the financial statements") is None


def test_chunk_pages_creates_page_blocks_and_statement_chunks() -> None:
    pages = [
        PageRecord(
            page=1,
            text=(
                "Annual Report 2025\n\n"
                "Consolidated Statement of Financial Position\n"
                "Total assets 100\n"
            ),
        ),
        PageRecord(page=2, text="Total liabilities 40\nEquity 60"),
        PageRecord(
            page=3,
            text="Consolidated Statement of Cash Flows\nNet cash from operations 10",
        ),
    ]

    store = chunk_pages(pages, source_pdf_hash="hash123")

    assert store.source_pdf_hash == "hash123"
    assert [block.block_id for block in store.blocks] == [
        "p0001_b0001",
        "p0001_b0002",
        "p0002_b0001",
        "p0003_b0001",
    ]
    assert [chunk.chunk_id for chunk in store.chunks] == [
        "page_p0001",
        "page_p0002",
        "page_p0003",
        "stmt_balance_sheet_p0001_p0002",
        "stmt_cash_flow_p0003_p0003",
    ]

    statement = store.chunks[3]
    assert statement.kind == "statement_table"
    assert statement.page_start == 1
    assert statement.page_end == 2
    assert statement.block_ids == ("p0001_b0002", "p0002_b0001")
    assert "Total liabilities 40" in statement.text


def test_final_statement_chunk_stops_before_trailing_notes_section() -> None:
    pages = [
        PageRecord(
            page=10,
            text="Consolidated Statement of Cash Flows\nNet cash from operations 10",
        ),
        PageRecord(
            page=11,
            text="Notes to the financial statements\n1. General information",
        ),
    ]

    store = chunk_pages(pages, source_pdf_hash="hash123")

    statement = next(
        chunk for chunk in store.chunks if chunk.chunk_id == "stmt_cash_flow_p0010_p0010"
    )
    assert statement.block_ids == ("p0010_b0001",)
    assert "Notes to the financial statements" not in statement.text


def test_build_chunk_store_writes_chunks_jsonl_and_metadata(tmp_path: Path) -> None:
    pages_path = tmp_path / "pages.jsonl"
    metadata_path = tmp_path / "run_metadata.json"
    chunks_path = tmp_path / "chunks.jsonl"

    pages_path.write_text(
        "\n".join(
            [
                json.dumps({"page": 1, "text": "合并利润表\n营业收入 100"}),
                json.dumps({"page": 2, "text": "合并现金流量表\n经营活动现金流量 20"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps(
            {
                "source_pdf_hash": "hash123",
                "parser_version": "fake-parser:1",
                "chunker_version": "none",
                "artifacts": {
                    "pages": str(pages_path),
                    "metadata": str(metadata_path),
                },
            }
        ),
        encoding="utf-8",
    )

    result = build_chunk_store(
        pages_path,
        metadata_path,
        chunks_path=chunks_path,
    )

    assert result.block_count == 2
    assert result.chunk_count == 4
    assert result.chunks_path == chunks_path

    records = [
        json.loads(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["record_type"] == "block"
    assert records[0]["source_pdf_hash"] == "hash123"
    assert records[-1]["record_type"] == "chunk"
    assert records[-1]["chunk_id"] == "stmt_cash_flow_p0002_p0002"

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["chunker_version"] == "phase2-logical-chunks-v1"
    assert metadata["artifacts"]["chunks"] == str(chunks_path)


def test_build_chunk_store_creates_nested_output_directory(tmp_path: Path) -> None:
    pages_path = tmp_path / "pages.jsonl"
    metadata_path = tmp_path / "run_metadata.json"
    chunks_path = tmp_path / "nested" / "artifacts" / "chunks.jsonl"

    pages_path.write_text(
        json.dumps({"page": 1, "text": "合并资产负债表\n资产总计 100"}) + "\n",
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps({"source_pdf_hash": "hash123", "artifacts": {}}),
        encoding="utf-8",
    )

    result = build_chunk_store(
        pages_path,
        metadata_path,
        chunks_path=chunks_path,
    )

    assert result.chunks_path == chunks_path
    assert chunks_path.exists()
