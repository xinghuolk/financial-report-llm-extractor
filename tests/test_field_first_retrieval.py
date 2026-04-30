from typing import Any

from financial_report_llm_extractor.evidence_index import build_evidence_index


def test_build_evidence_index_reads_block_level_evidence() -> None:
    records: list[dict[str, Any]] = [
        {
            "record_type": "chunk",
            "chunk_id": "page_p0001",
            "kind": "page_text",
            "statement_kind": None,
            "page_start": 1,
            "page_end": 1,
            "block_ids": ["p0001_b0001"],
            "block_texts": {"p0001_b0001": "Revenue 100 90"},
            "text": "Revenue 100 90",
        }
    ]

    index = build_evidence_index(records)

    assert len(index.blocks) == 1
    block = index.blocks[0]
    assert block.block_id == "p0001_b0001"
    assert block.page == 1
    assert block.chunk_id == "page_p0001"
    assert block.numeric_token_count == 2
    assert block.year_count == 0


def test_build_evidence_index_uses_block_record_page_for_multi_page_chunks() -> None:
    records: list[dict[str, Any]] = [
        {
            "record_type": "block",
            "block_id": "p0001_b0001",
            "page": 1,
            "text": "Revenue 100",
        },
        {
            "record_type": "block",
            "block_id": "p0002_b0001",
            "page": 2,
            "text": "Profit 90",
        },
        {
            "record_type": "chunk",
            "chunk_id": "stmt_income_statement_p0001_p0002",
            "kind": "statement_table",
            "statement_kind": "income_statement",
            "page_start": 1,
            "page_end": 2,
            "block_ids": ["p0001_b0001", "p0002_b0001"],
            "block_texts": {
                "p0001_b0001": "Revenue 100",
                "p0002_b0001": "Profit 90",
            },
            "text": "Revenue 100\nProfit 90",
        },
    ]

    index = build_evidence_index(records)

    blocks_by_id = {block.block_id: block for block in index.blocks}
    assert blocks_by_id["p0002_b0001"].page == 2
    assert blocks_by_id["p0002_b0001"].text == "Profit 90"


def test_build_evidence_index_counts_common_numeric_tokens_once() -> None:
    records: list[dict[str, Any]] = [
        {
            "record_type": "chunk",
            "chunk_id": "page_p0001",
            "kind": "page_text",
            "statement_kind": None,
            "page_start": 1,
            "page_end": 1,
            "block_ids": ["p0001_b0001"],
            "block_texts": {
                "p0001_b0001": "Year 2025 Amounts 1000 1234.56 (1234) -1234"
            },
            "text": "Year 2025 Amounts 1000 1234.56 (1234) -1234",
        }
    ]

    index = build_evidence_index(records)

    block = index.blocks[0]
    assert block.year_count == 1
    assert block.numeric_token_count == 5
