from typing import Any

from financial_report_llm_extractor.evidence_index import build_evidence_index
from financial_report_llm_extractor.field_first_retrieval import (
    estimate_prompt_budget,
    retrieve_field_first,
)


def adversarial_field_first_records() -> list[dict[str, Any]]:
    return [
        {
            "record_type": "chunk",
            "chunk_id": "page_p0001",
            "kind": "page_text",
            "statement_kind": None,
            "page_start": 1,
            "page_end": 1,
            "block_ids": ["p0001_b0001"],
            "block_texts": {
                "p0001_b0001": (
                    "Management discussion mentions balance sheet, income statement, "
                    "cash flow, revenue, net profit, total assets and total liabilities "
                    "as planning themes without presenting the audited field rows."
                )
            },
            "text": (
                "Management discussion mentions balance sheet, income statement, "
                "cash flow, revenue, net profit, total assets and total liabilities "
                "as planning themes without presenting the audited field rows."
            ),
        },
        {
            "record_type": "chunk",
            "chunk_id": "page_p0002",
            "kind": "page_text",
            "statement_kind": None,
            "page_start": 2,
            "page_end": 2,
            "block_ids": ["p0002_b0001", "p0002_b0002"],
            "block_texts": {
                "p0002_b0001": "Revenue 2025 RMB million 125,000 2024 110,000",
                "p0002_b0002": "Net profit 2025 RMB million 46,000 2024 41,000",
            },
            "text": (
                "Revenue 2025 RMB million 125,000 2024 110,000\n"
                "Net profit 2025 RMB million 46,000 2024 41,000"
            ),
        },
        {
            "record_type": "chunk",
            "chunk_id": "page_p0003",
            "kind": "page_text",
            "statement_kind": None,
            "page_start": 3,
            "page_end": 3,
            "block_ids": ["p0003_b0001", "p0003_b0002"],
            "block_texts": {
                "p0003_b0001": "Total assets 2025 RMB million 300,000 2024 280,000",
                "p0003_b0002": "Total liabilities 2025 RMB million 90,000 2024 85,000",
            },
            "text": (
                "Total assets 2025 RMB million 300,000 2024 280,000\n"
                "Total liabilities 2025 RMB million 90,000 2024 85,000"
            ),
        },
        {
            "record_type": "chunk",
            "chunk_id": "page_p0004",
            "kind": "page_text",
            "statement_kind": None,
            "page_start": 4,
            "page_end": 4,
            "block_ids": ["p0004_b0001"],
            "block_texts": {
                "p0004_b0001": (
                    "Net cash from operating activities 2025 RMB million 52,000 2024 49,000"
                )
            },
            "text": "Net cash from operating activities 2025 RMB million 52,000 2024 49,000",
        },
    ]


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
    assert block.token_count == 3
    assert block.numeric_token_count == 2
    assert block.year_count == 0


def test_field_first_retrieval_finds_core_fields_without_statement_gate() -> None:
    records = adversarial_field_first_records()
    index = build_evidence_index(records)

    result = retrieve_field_first(
        index,
        selected_fields=(
            "revenue",
            "net_profit",
            "total_assets",
            "total_liabilities",
            "operating_cash_flow",
        ),
        top_k=3,
    )

    statuses = {field["field_id"]: field["status"] for field in result["fields"]}
    assert statuses == {
        "revenue": "candidates_found",
        "net_profit": "candidates_found",
        "total_assets": "candidates_found",
        "total_liabilities": "candidates_found",
        "operating_cash_flow": "candidates_found",
    }
    top_evidence_by_field = {
        field["field_id"]: field["candidates"][0]["evidence"] for field in result["fields"]
    }
    assert top_evidence_by_field == {
        "revenue": {
            "page": 2,
            "chunk_id": "page_p0002",
            "block_id": "p0002_b0001",
            "snippet": "Revenue 2025 RMB million 125,000 2024 110,000",
        },
        "net_profit": {
            "page": 2,
            "chunk_id": "page_p0002",
            "block_id": "p0002_b0002",
            "snippet": "Net profit 2025 RMB million 46,000 2024 41,000",
        },
        "total_assets": {
            "page": 3,
            "chunk_id": "page_p0003",
            "block_id": "p0003_b0001",
            "snippet": "Total assets 2025 RMB million 300,000 2024 280,000",
        },
        "total_liabilities": {
            "page": 3,
            "chunk_id": "page_p0003",
            "block_id": "p0003_b0002",
            "snippet": "Total liabilities 2025 RMB million 90,000 2024 85,000",
        },
        "operating_cash_flow": {
            "page": 4,
            "chunk_id": "page_p0004",
            "block_id": "p0004_b0001",
            "snippet": (
                "Net cash from operating activities 2025 RMB million 52,000 2024 49,000"
            ),
        },
    }
    for field in result["fields"]:
        candidate = field["candidates"][0]
        assert candidate["evidence"]["page"] > 0
        assert candidate["evidence"]["block_id"]
        assert candidate["evidence"]["snippet"]


def test_adversarial_fixture_demonstrates_statement_first_risk() -> None:
    records = adversarial_field_first_records()
    statement_chunks = [
        record
        for record in records
        if record.get("record_type") == "chunk"
        and record.get("kind") == "statement_table"
    ]

    assert len(statement_chunks) < 3


def test_field_first_retrieval_prompt_budget_stays_bounded() -> None:
    selected_fields = (
        "revenue",
        "net_profit",
        "total_assets",
        "total_liabilities",
        "operating_cash_flow",
    )
    records = adversarial_field_first_records()
    index = build_evidence_index(records)

    result = retrieve_field_first(index, selected_fields=selected_fields, top_k=3)
    budget = estimate_prompt_budget(result)

    assert budget["total_candidate_text_chars"] < 12_000
    fields_by_id = {field["field_id"]: field for field in budget["fields"]}
    assert set(fields_by_id) == set(selected_fields)
    for field_id in selected_fields:
        assert fields_by_id[field_id]["candidate_count"] <= 3
        assert fields_by_id[field_id]["candidate_text_chars"] > 0


def test_field_first_retrieval_prefers_numeric_density_without_statement_gate() -> None:
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
                "p0001_b0001": (
                    "Revenue performance narrative references 10 20 30 40 50 60 70 80 "
                    "while discussing strategy operations channels customers product "
                    "mix market expansion execution risks seasonality outlook governance "
                    "initiatives capacity pricing distribution and management priorities."
                )
            },
            "text": (
                "Revenue performance narrative references 10 20 30 40 50 60 70 80 "
                "while discussing strategy operations channels customers product "
                "mix market expansion execution risks seasonality outlook governance "
                "initiatives capacity pricing distribution and management priorities."
            ),
        },
        {
            "record_type": "chunk",
            "chunk_id": "page_p0002",
            "kind": "page_text",
            "statement_kind": None,
            "page_start": 2,
            "page_end": 2,
            "block_ids": ["p0002_b0001"],
            "block_texts": {
                "p0002_b0001": "Revenue 125,000 110,000",
            },
            "text": "Revenue 125,000 110,000",
        },
    ]
    index = build_evidence_index(records)

    result = retrieve_field_first(index, selected_fields=("revenue",), top_k=2)

    candidates = result["fields"][0]["candidates"]
    assert candidates[0]["evidence"]["block_id"] == "p0002_b0001"


def test_field_first_retrieval_collapses_duplicate_block_candidates() -> None:
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
                "p0001_b0001": "Revenue 125,000 110,000",
            },
            "text": "Revenue 125,000 110,000",
        },
        {
            "record_type": "chunk",
            "chunk_id": "stmt_income_statement_p0001",
            "kind": "statement_table",
            "statement_kind": "income_statement",
            "page_start": 1,
            "page_end": 1,
            "block_ids": ["p0001_b0001"],
            "block_texts": {
                "p0001_b0001": "Revenue 125,000 110,000",
            },
            "text": "Revenue 125,000 110,000",
        },
        {
            "record_type": "chunk",
            "chunk_id": "page_p0002",
            "kind": "page_text",
            "statement_kind": None,
            "page_start": 2,
            "page_end": 2,
            "block_ids": ["p0002_b0001"],
            "block_texts": {
                "p0002_b0001": "Revenue 98,000 87,000",
            },
            "text": "Revenue 98,000 87,000",
        },
    ]
    index = build_evidence_index(records)

    result = retrieve_field_first(index, selected_fields=("revenue",), top_k=2)

    candidates = result["fields"][0]["candidates"]
    assert [candidate["evidence"]["block_id"] for candidate in candidates] == [
        "p0001_b0001",
        "p0002_b0001",
    ]
    assert candidates[0]["evidence"]["chunk_id"] == "stmt_income_statement_p0001"


def test_field_first_retrieval_ranks_value_rows_above_year_headers() -> None:
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
                "p0001_b0001": "Revenue 2025 2024",
            },
            "text": "Revenue 2025 2024",
        },
        {
            "record_type": "chunk",
            "chunk_id": "page_p0002",
            "kind": "page_text",
            "statement_kind": None,
            "page_start": 2,
            "page_end": 2,
            "block_ids": ["p0002_b0001"],
            "block_texts": {
                "p0002_b0001": "Revenue 125,000 110,000",
            },
            "text": "Revenue 125,000 110,000",
        },
    ]
    index = build_evidence_index(records)

    result = retrieve_field_first(index, selected_fields=("revenue",), top_k=2)

    candidates = result["fields"][0]["candidates"]
    assert candidates[0]["evidence"]["block_id"] == "p0002_b0001"


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
    assert block.token_count == 7
    assert block.year_count == 1
    assert block.numeric_token_count == 5
