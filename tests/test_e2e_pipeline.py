import json
from pathlib import Path
from typing import Any, cast

from financial_report_llm_extractor.chunking import build_chunk_store
from financial_report_llm_extractor.document_map import (
    write_document_map,
    write_parser_capability_probe,
)
from financial_report_llm_extractor.evaluation import write_review_summary
from financial_report_llm_extractor.extraction import run_fake_extraction
from financial_report_llm_extractor.ingestion import ingest_pdf
from financial_report_llm_extractor.retrieval import write_retrieval_probe
from financial_report_llm_extractor.statement_discovery import (
    write_catalog_mapping,
    write_row_inventory,
    write_statement_map,
)


class SyntheticReportParser:
    name = "synthetic-e2e-parser"
    version = "synthetic-e2e-v1"

    def extract_text(self, pdf_path: Path) -> str:
        return "\f".join(
            [
                """
                CONTENTS

                Financial Summary
                """,
                """
                INDEPENDENT AUDITOR'S REPORT

                We audited the consolidated financial statements.
                """,
                """
                CONSOLIDATED INCOME STATEMENT
                HK$ Million
                2025 2024

                Revenue 100 90
                Profit attributable to shareholders 20 18
                Gross profit 45 40
                """,
                """
                CONSOLIDATED STATEMENT OF FINANCIAL POSITION
                HK$ Million
                2025 2024

                Total assets 500 450
                Total liabilities 300 280
                Cash and cash equivalents 80 70
                """,
                """
                CONSOLIDATED STATEMENT OF CASH FLOWS
                HK$ Million
                2025 2024

                Net cash from operating activities 60 55
                Net cash from investing activities (25) (20)
                Net cash from financing activities (15) (10)

                Notes to the financial statements
                """,
            ]
        )


def test_default_no_network_e2e_pipeline_writes_reviewable_artifacts(
    tmp_path: Path,
) -> None:
    root_dir = tmp_path
    run_dir = root_dir / "run"
    pdf_path = tmp_path / "synthetic.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 synthetic e2e fixture\n")

    ingest_result = ingest_pdf(pdf_path, run_dir, parser=SyntheticReportParser())
    chunk_result = build_chunk_store(
        ingest_result.pages_path,
        ingest_result.metadata_path,
        chunks_path=run_dir / "chunks.jsonl",
    )
    parser_result = write_parser_capability_probe(
        ingest_result.pages_path,
        ingest_result.metadata_path,
        output_path=run_dir / "parser_capability.json",
    )
    document_result = write_document_map(
        chunk_result.chunks_path,
        output_path=run_dir / "document_map.json",
    )
    statement_result = write_statement_map(
        chunk_result.chunks_path,
        document_result.output_path,
        output_path=run_dir / "statement_map.json",
    )
    row_result = write_row_inventory(
        chunk_result.chunks_path,
        statement_result.output_path,
        output_path=run_dir / "row_inventory.json",
    )
    mapping_result = write_catalog_mapping(
        row_result.output_path,
        selected_fields=(
            "revenue",
            "net_profit",
            "total_assets",
            "total_liabilities",
            "operating_cash_flow",
        ),
        output_path=run_dir / "catalog_mapping.json",
    )
    retrieval_result = write_retrieval_probe(
        Path("field_catalog/turtle_v015_priority_fields.json"),
        chunk_result.chunks_path,
        output_path=run_dir / "retrieval_probe.json",
        priorities=("P0",),
    )
    extraction_result = run_fake_extraction(
        retrieval_result.output_path,
        output_path=run_dir / "extraction_result.json",
    )
    evaluation_result = write_review_summary(
        root_dir,
        output_path=run_dir / "evaluation_summary.json",
        fixtures=[("synthetic_2025", pdf_path.relative_to(root_dir))],
        result_paths={"synthetic_2025": extraction_result.output_path},
    )

    assert ingest_result.page_count == 5
    assert chunk_result.chunk_count >= 8
    assert parser_result.page_count == 5
    assert document_result.section_count >= 3
    assert statement_result.statement_count == 3
    assert row_result.row_count >= 8
    assert mapping_result.mapping_count == 5
    assert retrieval_result.field_count > 5
    assert extraction_result.item_count == retrieval_result.field_count
    assert evaluation_result.report_count == 1

    retrieval_payload = _read_json(retrieval_result.output_path)
    retrieval_fields = cast(list[dict[str, Any]], retrieval_payload["fields"])
    retrieval_statuses = {
        str(field["field_id"]): field["status"] for field in retrieval_fields
    }
    assert retrieval_statuses["revenue"] == "candidates_found"
    assert retrieval_statuses["total_assets"] == "candidates_found"
    assert retrieval_statuses["operating_cash_flow"] == "candidates_found"

    extraction_payload = _read_json(extraction_result.output_path)
    extraction_items = cast(list[dict[str, Any]], extraction_payload["items"])
    assert extraction_items
    assert all("field_id" in item for item in extraction_items)

    evaluation_payload = _read_json(evaluation_result.output_path)
    reports = cast(list[dict[str, Any]], evaluation_payload["reports"])
    report = reports[0]
    assert report["available"] is True
    assert report["summary"]["total_fields"] == extraction_result.item_count


def test_e2e_scripts_expose_local_pdf_and_real_llm_entrypoints() -> None:
    local_pdf_script = Path("scripts/run-local-pdf-e2e.sh")
    real_llm_script = Path("scripts/run-real-llm-smoke.sh")

    assert local_pdf_script.exists()
    assert real_llm_script.exists()

    local_pdf_text = local_pdf_script.read_text(encoding="utf-8")
    assert "quick-validate" in local_pdf_text
    assert "retrieve" in local_pdf_text
    assert "extract-fake" in local_pdf_text
    assert "evaluate" in local_pdf_text

    real_llm_text = real_llm_script.read_text(encoding="utf-8")
    assert "discover-rows-llm" in real_llm_text
    assert "SMOKE_STATEMENT_LIMIT" in real_llm_text
    assert "statement_map_smoke" in real_llm_text
    assert "deepseek" in real_llm_text
    assert "ollama" in real_llm_text
    assert "gemini" in real_llm_text
    assert "DEEPSEEK_API_KEY" in real_llm_text
    assert "OLLAMA_BASE_URL" in real_llm_text
    assert "GEMINI_API_KEY" in real_llm_text


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
