"""Evaluation matrix and review summaries for extraction results."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvaluationFixture:
    report_id: str
    pdf_relative_path: Path


@dataclass(frozen=True)
class EvaluationReviewResult:
    output_path: Path
    report_count: int


DEFAULT_EVALUATION_FIXTURES: tuple[EvaluationFixture, ...] = (
    EvaluationFixture(
        report_id="600519_2025",
        pdf_relative_path=Path("downloads/cn_stocks/600519/annual/2025_年度报告.pdf"),
    ),
    EvaluationFixture(
        report_id="00001_2025_en",
        pdf_relative_path=Path("downloads/hk_stocks/00001/annual/2025_annual_en.pdf"),
    ),
    EvaluationFixture(
        report_id="01113_2025_en",
        pdf_relative_path=Path("downloads/hk_stocks/01113/annual/2025_annual_en.pdf"),
    ),
)


def build_evaluation_matrix(
    root_dir: Path,
    *,
    fixtures: list[tuple[str, Path]] | None = None,
) -> list[dict[str, Any]]:
    active_fixtures = fixtures or [
        (fixture.report_id, fixture.pdf_relative_path)
        for fixture in DEFAULT_EVALUATION_FIXTURES
    ]
    matrix = []
    for report_id, relative_path in active_fixtures:
        pdf_path = root_dir / relative_path
        matrix.append(
            {
                "report_id": report_id,
                "pdf_path": str(pdf_path),
                "available": pdf_path.exists(),
            }
        )
    return matrix


def summarize_extraction_result(result_path: Path) -> dict[str, Any]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    items = result.get("items", [])
    status_counts: dict[str, int] = {}
    present_with_evidence = 0
    present_without_evidence: list[str] = []
    present_money_without_normalized_value: list[str] = []

    for item in items:
        field_id = str(item.get("field_id", "unknown"))
        status = str(item.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
        if status != "present":
            continue
        evidence = item.get("evidence", [])
        if evidence:
            present_with_evidence += 1
        else:
            present_without_evidence.append(field_id)
        money = item.get("money")
        if not isinstance(money, dict) or not money.get("normalized_value"):
            present_money_without_normalized_value.append(field_id)

    return {
        "source_pdf_hash": result.get("source_pdf_hash"),
        "total_fields": len(items),
        "status_counts": status_counts,
        "present_with_evidence": present_with_evidence,
        "present_without_evidence": present_without_evidence,
        "present_money_without_normalized_value": (
            present_money_without_normalized_value
        ),
    }


def write_review_summary(
    root_dir: Path,
    *,
    output_path: Path | None = None,
    fixtures: list[tuple[str, Path]] | None = None,
    result_paths: dict[str, Path] | None = None,
) -> EvaluationReviewResult:
    matrix = build_evaluation_matrix(root_dir, fixtures=fixtures)
    results = result_paths or {}
    reports = []
    for report in matrix:
        report_id = str(report["report_id"])
        result_path = results.get(report_id)
        summary = summarize_extraction_result(result_path) if result_path else None
        reports.append({**report, "summary": summary})

    output = output_path or root_dir / "evaluation_summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "reports": reports,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return EvaluationReviewResult(output_path=output, report_count=len(reports))
