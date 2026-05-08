"""Fixture-driven end-to-end source-first evaluation."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from financial_report_llm_extractor.structured_sources.artifacts import (
    write_source_inventory,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
    load_source_mapping_catalog,
)
from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportResult,
    build_source_first_export,
    write_source_first_export_artifacts,
)
from financial_report_llm_extractor.structured_sources.mapping import (
    TurtleMappingResult,
    map_source_inventory,
    write_turtle_mapping_artifacts,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
    SourceName,
)
from financial_report_llm_extractor.structured_sources.pdf_supplement import (
    apply_pdf_evidence_supplement,
    build_pdf_evidence_supplement,
    write_pdf_evidence_supplement,
)
from financial_report_llm_extractor.structured_sources.reconciliation import (
    ReconciliationReport,
    reconcile_mapped_fields,
    write_reconciliation_report,
)


@dataclass(frozen=True)
class SourceFirstEvaluationFixture:
    report_id: str
    records: tuple[SourceInventoryRecord, ...]
    chunks: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class SourceFirstEvaluationResult:
    output_path: Path
    summary: dict[str, Any]


def default_source_first_evaluation_fixtures() -> tuple[SourceFirstEvaluationFixture, ...]:
    return tuple(
        SourceFirstEvaluationFixture(
            report_id=report_id,
            records=(
                _fixture_record(
                    report_id=report_id,
                    source="akshare",
                    raw_field_name="营业收入",
                    raw_value="100",
                ),
                _fixture_record(
                    report_id=report_id,
                    source="yahoo",
                    raw_field_name="Cash And Cash Equivalents",
                    raw_value="20",
                ),
            ),
            chunks=(
                _fixture_chunk("chunk-revenue", "revenue 100"),
                _fixture_chunk("chunk-cash", "cash and cash equivalents 20"),
            ),
        )
        for report_id in ("600519", "00001", "01113")
    )


def run_default_source_first_fixture_evaluation(
    *,
    catalog_path: Path,
    output_dir: Path,
) -> SourceFirstEvaluationResult:
    catalog = load_source_mapping_catalog(catalog_path, priorities=("P0", "P1", "P2"))
    return run_source_first_evaluation(
        fixtures=default_source_first_evaluation_fixtures(),
        catalog=catalog,
        output_dir=output_dir,
    )


def run_source_first_evaluation(
    *,
    fixtures: tuple[SourceFirstEvaluationFixture, ...],
    catalog: SourceMappingCatalog,
    output_dir: Path,
) -> SourceFirstEvaluationResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    reports = [
        _evaluate_fixture(fixture, catalog, output_dir / fixture.report_id)
        for fixture in fixtures
    ]
    summary = {
        "catalog_id": catalog.catalog_id,
        "catalog_version": catalog.version,
        "report_count": len(reports),
        "reports": reports,
    }
    output_path = output_dir / "evaluation_summary.json"
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return SourceFirstEvaluationResult(output_path=output_path, summary=summary)


def _evaluate_fixture(
    fixture: SourceFirstEvaluationFixture,
    catalog: SourceMappingCatalog,
    report_dir: Path,
) -> dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)
    write_source_inventory(report_dir / "source_inventory.jsonl", fixture.records)

    akshare_mapping = _mapping_for_source(catalog, fixture.records, "akshare")
    yahoo_mapping = _mapping_for_source(catalog, fixture.records, "yahoo")
    combined_mapping = map_source_inventory(catalog, fixture.records)
    reconciliation = reconcile_mapped_fields(combined_mapping)
    export = build_source_first_export(
        combined_mapping,
        reconciliation,
        profile="pdf_required",
    )
    supplement = build_pdf_evidence_supplement(export, list(fixture.chunks))
    supplemented_export = apply_pdf_evidence_supplement(export, supplement)

    write_turtle_mapping_artifacts(combined_mapping, report_dir)
    write_reconciliation_report(reconciliation, report_dir / "reconciliation_report.json")
    write_pdf_evidence_supplement(supplement, report_dir / "pdf_evidence_supplement.json")
    write_source_first_export_artifacts(supplemented_export, report_dir)

    coverage = {
        "akshare_only": _mapping_coverage(akshare_mapping),
        "yahoo_only": _mapping_coverage(yahoo_mapping),
        "combined": _mapping_coverage(combined_mapping),
        "combined_pdf_supplement": _export_coverage(supplemented_export),
    }
    return {
        "report_id": fixture.report_id,
        "coverage": coverage,
        "remaining_gaps": _remaining_gaps(
            combined_mapping,
            reconciliation,
            supplemented_export,
        ),
        "artifact_paths": {
            "source_inventory": str(report_dir / "source_inventory.jsonl"),
            "turtle_mapping": str(report_dir / "turtle_mapping.json"),
            "source_coverage_summary": str(report_dir / "source_coverage_summary.json"),
            "reconciliation_report": str(report_dir / "reconciliation_report.json"),
            "pdf_evidence_supplement": str(report_dir / "pdf_evidence_supplement.json"),
            "extraction_result": str(report_dir / "extraction_result.json"),
            "review_summary": str(report_dir / "review_summary.json"),
        },
    }


def _mapping_for_source(
    catalog: SourceMappingCatalog,
    records: tuple[SourceInventoryRecord, ...],
    source: SourceName,
) -> TurtleMappingResult:
    return map_source_inventory(
        catalog,
        tuple(record for record in records if record.source == source),
    )


def _mapping_coverage(mapping: TurtleMappingResult) -> dict[str, object]:
    covered = [
        field_id
        for field_id, field in mapping.fields.items()
        if field.status in {"present", "derived"}
    ]
    total = len(mapping.fields)
    return {
        "covered_fields": sorted(covered),
        "covered_count": len(covered),
        "total_fields": total,
        "coverage_ratio": len(covered) / total if total else 0.0,
    }


def _export_coverage(export: SourceFirstExportResult) -> dict[str, object]:
    covered = [
        field_id
        for field_id, item in export.items.items()
        if item.status == "present"
    ]
    total = len(export.items)
    return {
        "covered_fields": sorted(covered),
        "covered_count": len(covered),
        "total_fields": total,
        "coverage_ratio": len(covered) / total if total else 0.0,
    }


def _remaining_gaps(
    mapping: TurtleMappingResult,
    reconciliation: ReconciliationReport,
    export: SourceFirstExportResult,
) -> dict[str, list[str]]:
    return {
        "source_availability": sorted(
            field_id
            for field_id, field in mapping.fields.items()
            if field.status == "missing"
        ),
        "source_mapping": sorted(
            field_id
            for field_id, field in mapping.fields.items()
            if field.status == "blocked"
        ),
        "pdf_supplement": sorted(
            field_id
            for field_id, item in export.items.items()
            if item.status == "needs_pdf_evidence"
        ),
        "llm_review": sorted(
            set(reconciliation.conflict_fields)
            | {
                field_id
                for field_id, item in export.items.items()
                if item.status == "ambiguous"
            }
        ),
    }


def _fixture_record(
    *,
    report_id: str,
    source: SourceName,
    raw_field_name: str,
    raw_value: str,
) -> SourceInventoryRecord:
    return SourceInventoryRecord(
        source=source,
        market="CN" if report_id == "600519" else "HK",
        ticker=report_id,
        statement_type="income_statement",
        period="2024-12-31",
        raw_field_name=raw_field_name,
        raw_value=raw_value,
        parsed_numeric_value=Decimal(raw_value),
        currency="CNY" if report_id == "600519" else "HKD",
        unit="yuan" if report_id == "600519" else "HKD",
        scope="consolidated",
        source_evidence=(
            SourceEvidence(
                source=source,
                adapter=source,
                function="fixture",
                artifact_id=f"{source}_{report_id}",
                raw_record_id=f"{source}:{report_id}:{raw_field_name}",
                raw_field_name=raw_field_name,
            ),
        ),
    )


def _fixture_chunk(chunk_id: str, text: str) -> dict[str, object]:
    return {
        "record_type": "chunk",
        "chunk_id": chunk_id,
        "kind": "statement_table",
        "page_start": 10,
        "page_end": 10,
        "block_ids": ["p0010_b0001"],
        "block_texts": {"p0010_b0001": text},
        "text": text,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("tmp/runs/source_first_evaluation"),
    )
    args = parser.parse_args(argv)
    result = run_default_source_first_fixture_evaluation(
        catalog_path=args.catalog,
        output_dir=args.out_dir,
    )
    print(f"evaluation_summary={result.output_path}")
    print(f"report_count={result.summary['report_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
