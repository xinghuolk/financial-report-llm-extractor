import json
from pathlib import Path

from financial_report_llm_extractor.document_map import (
    write_document_map,
    write_parser_capability_probe,
)


def test_write_parser_capability_probe_reports_quality_signals(
    tmp_path: Path,
) -> None:
    pages_path = tmp_path / "pages.jsonl"
    metadata_path = tmp_path / "run_metadata.json"
    output_path = tmp_path / "parser_capability.json"
    pages_path.write_text(
        "\n".join(
            [
                json.dumps({"page": 1, "text": "Contents\nFinancial Summary"}),
                json.dumps(
                    {
                        "page": 2,
                        "text": (
                            "Consolidated Statement of Financial Position\n"
                            "Total assets 100"
                        ),
                    }
                ),
                json.dumps({"page": 3, "text": "附注"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps(
            {
                "source_pdf_hash": "hash123",
                "parser_name": "fixture-parser",
                "parser_version": "v1",
            }
        ),
        encoding="utf-8",
    )

    result = write_parser_capability_probe(
        pages_path,
        metadata_path,
        output_path=output_path,
    )

    assert result.output_path == output_path
    assert result.page_count == 3
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["parser_name"] == "fixture-parser"
    assert payload["parser_version"] == "v1"
    assert payload["source_pdf_hash"] == "hash123"
    assert payload["page_count"] == 3
    assert payload["non_empty_page_count"] == 3
    assert payload["average_chars_per_page"] > 10
    assert payload["contains_cjk"] is True
    assert payload["contains_financial_statement_terms"] is True
    assert payload["warnings"] == []


def test_write_document_map_detects_core_report_sections(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    output_path = tmp_path / "document_map.json"
    records = [
        _block("p0001_b0001", 1, "Contents\nFinancial Summary 6"),
        _block("p0006_b0001", 6, "Five Year Financial Summary\nRevenue 100"),
        _block("p0010_b0001", 10, "Management Discussion and Analysis\nRevenue"),
        _block("p0128_b0001", 128, "Independent Auditor's Report"),
        _block(
            "p0134_b0001",
            134,
            "Consolidated Statement of Comprehensive Income\nRevenue 100",
        ),
        _block("p0138_b0001", 138, "Consolidated Balance Sheet\nTotal assets 200"),
        _block(
            "p0142_b0001",
            142,
            "Consolidated Statement of Cash Flows\nNet cash from operations 30",
        ),
        _block("p0144_b0001", 144, "Notes to the Financial Statements"),
    ]
    chunks_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    result = write_document_map(chunks_path, output_path=output_path)

    assert result.output_path == output_path
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    sections = {section["kind"]: section for section in payload["sections"]}
    assert result.section_count == 6
    assert sections["contents"]["page_start"] == 1
    assert sections["financial_summary"]["page_start"] == 6
    assert sections["management_discussion"]["page_start"] == 10
    assert sections["independent_auditor_report"]["page_start"] == 128
    assert sections["audited_financial_statements"]["page_start"] == 134
    assert sections["audited_financial_statements"]["page_end"] == 142
    assert sections["notes_to_financial_statements"]["page_start"] == 144
    assert sections["audited_financial_statements"]["evidence"][0]["block_id"] == (
        "p0134_b0001"
    )


def _block(block_id: str, page: int, text: str) -> dict[str, object]:
    return {
        "record_type": "block",
        "source_pdf_hash": "hash123",
        "block_id": block_id,
        "page": page,
        "kind": "layout_line",
        "text": text,
    }
