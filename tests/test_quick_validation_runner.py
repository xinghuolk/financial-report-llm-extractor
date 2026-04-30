import json
from dataclasses import dataclass
from pathlib import Path

from financial_report_llm_extractor.quick_validation_runner import run_quick_validation


@dataclass(frozen=True)
class FakeParser:
    name: str = "fake-parser"
    version: str = "fake-parser:1"

    def extract_text(self, pdf_path: Path) -> str:
        return (
            "Contents\n\n"
            "CONSOLIDATED INCOME STATEMENT\n"
            "2025 2024\n"
            "$ Million\n"
            "Revenue 100 90\n"
            "Profit attributable to shareholders 20 18\n"
        )


def test_run_quick_validation_writes_phase_12_artifacts(tmp_path: Path) -> None:
    pdf_path = tmp_path / "00001_2025_en.pdf"
    pdf_path.write_bytes(b"fake-pdf")

    result = run_quick_validation(
        pdf_path=pdf_path,
        report_id="00001_2025_en",
        root_dir=tmp_path,
        parser=FakeParser(),
        selected_fields=("revenue", "net_profit"),
    )

    run_dir = tmp_path / "tmp" / "runs" / "quick_validation" / "00001_2025_en"
    expected_paths = {
        "pages": run_dir / "pages.jsonl",
        "metadata": run_dir / "run_metadata.json",
        "chunks": run_dir / "chunks.jsonl",
        "parser_capability": run_dir / "parser_capability.json",
        "document_map": run_dir / "document_map.json",
        "statement_map": run_dir / "statement_map.json",
        "row_inventory": run_dir / "row_inventory.json",
        "catalog_mapping": run_dir / "catalog_mapping.json",
        "summary": run_dir / "quick_validation_summary.json",
    }

    assert result.run_dir == run_dir
    assert result.artifacts == expected_paths
    assert all(path.exists() for path in expected_paths.values())

    summary = json.loads(expected_paths["summary"].read_text(encoding="utf-8"))
    assert summary["report_id"] == "00001_2025_en"
    assert summary["parser_warnings"] == []
    assert summary["document_section_count"] == 2
    assert summary["statement_counts_by_kind"] == {"income_statement": 1}
    assert summary["row_count"] == 2
    assert summary["selected_field_mapping_statuses"] == {
        "revenue": "mapped",
        "net_profit": "mapped",
    }
