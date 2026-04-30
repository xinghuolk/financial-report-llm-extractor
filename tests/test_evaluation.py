import json
from pathlib import Path

from financial_report_llm_extractor.evaluation import (
    DEFAULT_EVALUATION_FIXTURES,
    build_evaluation_matrix,
    summarize_extraction_result,
    write_review_summary,
)


def test_default_evaluation_fixtures_include_roadmap_reports() -> None:
    fixture_ids = {fixture.report_id for fixture in DEFAULT_EVALUATION_FIXTURES}

    assert fixture_ids == {"600519_2025", "00001_2025_en", "01113_2025_en"}


def test_build_evaluation_matrix_marks_pdf_availability(tmp_path: Path) -> None:
    existing_pdf = tmp_path / "downloads" / "cn" / "report.pdf"
    missing_pdf = tmp_path / "downloads" / "hk" / "missing.pdf"
    existing_pdf.parent.mkdir(parents=True)
    existing_pdf.write_bytes(b"%PDF-1.4")

    matrix = build_evaluation_matrix(
        tmp_path,
        fixtures=[
            ("cn_report", existing_pdf.relative_to(tmp_path)),
            ("hk_report", missing_pdf.relative_to(tmp_path)),
        ],
    )

    assert matrix == [
        {
            "report_id": "cn_report",
            "pdf_path": str(existing_pdf),
            "available": True,
        },
        {
            "report_id": "hk_report",
            "pdf_path": str(missing_pdf),
            "available": False,
        },
    ]


def test_summarize_extraction_result_counts_statuses_and_evidence(tmp_path: Path) -> None:
    result_path = tmp_path / "extraction_result.json"
    result_path.write_text(
        json.dumps(
            {
                "source_pdf_hash": "hash123",
                "items": [
                    {
                        "field_id": "revenue",
                        "status": "present",
                        "money": {"normalized_value": "100000000"},
                        "evidence": [{"page": 5, "chunk_id": "c1", "block_id": "b1"}],
                    },
                    {
                        "field_id": "cash",
                        "status": "present",
                        "money": None,
                        "evidence": [],
                    },
                    {
                        "field_id": "net_profit",
                        "status": "missing",
                        "money": None,
                        "evidence": [],
                    },
                    {
                        "field_id": "operating_cash_flow",
                        "status": "ambiguous",
                        "money": None,
                        "evidence": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_extraction_result(result_path)

    assert summary["total_fields"] == 4
    assert summary["status_counts"] == {
        "present": 2,
        "missing": 1,
        "ambiguous": 1,
    }
    assert summary["present_with_evidence"] == 1
    assert summary["present_without_evidence"] == ["cash"]
    assert summary["present_money_without_normalized_value"] == ["cash"]


def test_write_review_summary_combines_matrix_and_results(tmp_path: Path) -> None:
    report_pdf = tmp_path / "downloads" / "report.pdf"
    result_path = tmp_path / "runs" / "report" / "extraction_result.json"
    output_path = tmp_path / "evaluation_summary.json"
    report_pdf.parent.mkdir(parents=True)
    result_path.parent.mkdir(parents=True)
    report_pdf.write_bytes(b"%PDF-1.4")
    result_path.write_text(
        json.dumps(
            {
                "source_pdf_hash": "hash123",
                "items": [{"field_id": "revenue", "status": "missing"}],
            }
        ),
        encoding="utf-8",
    )

    review = write_review_summary(
        tmp_path,
        output_path=output_path,
        fixtures=[("report", report_pdf.relative_to(tmp_path))],
        result_paths={"report": result_path},
    )

    assert review.output_path == output_path
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["reports"][0]["report_id"] == "report"
    assert payload["reports"][0]["available"] is True
    assert payload["reports"][0]["summary"]["status_counts"] == {"missing": 1}
