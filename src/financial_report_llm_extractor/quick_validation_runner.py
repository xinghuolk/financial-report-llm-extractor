"""No-network quick validation workflow for one real report PDF."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from financial_report_llm_extractor.chunking import build_chunk_store
from financial_report_llm_extractor.document_map import (
    write_document_map,
    write_parser_capability_probe,
)
from financial_report_llm_extractor.ingestion import PdfTextParser, ingest_pdf
from financial_report_llm_extractor.quick_validation import (
    QuickValidationLayout,
    prepare_quick_validation_layout,
)
from financial_report_llm_extractor.statement_discovery import (
    write_catalog_mapping,
    write_row_inventory,
    write_statement_map,
)


DEFAULT_SELECTED_FIELDS = (
    "revenue",
    "net_profit",
    "total_assets",
    "total_liabilities",
    "operating_cash_flow",
)


@dataclass(frozen=True)
class QuickValidationResult:
    run_dir: Path
    artifacts: dict[str, Path]


def run_quick_validation(
    *,
    pdf_path: Path,
    report_id: str,
    root_dir: Path,
    parser: PdfTextParser | None = None,
    selected_fields: tuple[str, ...] = DEFAULT_SELECTED_FIELDS,
) -> QuickValidationResult:
    layout = prepare_quick_validation_layout(root_dir, report_id)

    ingest_pdf(pdf_path, layout.run_dir, parser=parser)
    build_chunk_store(
        layout.pages_path,
        layout.metadata_path,
        chunks_path=layout.chunks_path,
    )
    parser_capability_result = write_parser_capability_probe(
        layout.pages_path,
        layout.metadata_path,
        output_path=layout.run_dir / "parser_capability.json",
    )
    document_map_result = write_document_map(
        layout.chunks_path,
        output_path=layout.run_dir / "document_map.json",
    )
    statement_map_result = write_statement_map(
        layout.chunks_path,
        document_map_result.output_path,
        output_path=layout.run_dir / "statement_map.json",
    )
    row_inventory_result = write_row_inventory(
        layout.chunks_path,
        statement_map_result.output_path,
        output_path=layout.run_dir / "row_inventory.json",
    )
    catalog_mapping_result = write_catalog_mapping(
        row_inventory_result.output_path,
        selected_fields=selected_fields,
        output_path=layout.run_dir / "catalog_mapping.json",
    )
    summary_path = layout.run_dir / "quick_validation_summary.json"
    artifacts = _artifact_paths(
        layout,
        parser_capability_result.output_path,
        document_map_result.output_path,
        statement_map_result.output_path,
        row_inventory_result.output_path,
        catalog_mapping_result.output_path,
        summary_path,
    )
    _write_summary(report_id, artifacts, summary_path)
    return QuickValidationResult(run_dir=layout.run_dir, artifacts=artifacts)


def _artifact_paths(
    layout: QuickValidationLayout,
    parser_capability_path: Path,
    document_map_path: Path,
    statement_map_path: Path,
    row_inventory_path: Path,
    catalog_mapping_path: Path,
    summary_path: Path,
) -> dict[str, Path]:
    return {
        "pages": layout.pages_path,
        "metadata": layout.metadata_path,
        "chunks": layout.chunks_path,
        "parser_capability": parser_capability_path,
        "document_map": document_map_path,
        "statement_map": statement_map_path,
        "row_inventory": row_inventory_path,
        "catalog_mapping": catalog_mapping_path,
        "summary": summary_path,
    }


def _write_summary(
    report_id: str,
    artifacts: dict[str, Path],
    summary_path: Path,
) -> None:
    parser_capability = _read_json(artifacts["parser_capability"])
    document_map = _read_json(artifacts["document_map"])
    statement_map = _read_json(artifacts["statement_map"])
    row_inventory = _read_json(artifacts["row_inventory"])
    catalog_mapping = _read_json(artifacts["catalog_mapping"])

    statements = [
        statement
        for statement in statement_map.get("statements", [])
        if isinstance(statement, dict)
    ]
    rows = [row for row in row_inventory.get("rows", []) if isinstance(row, dict)]
    mappings = [
        mapping
        for mapping in catalog_mapping.get("mappings", [])
        if isinstance(mapping, dict)
    ]

    summary = {
        "report_id": report_id,
        "artifacts": {name: str(path) for name, path in artifacts.items()},
        "parser_warnings": parser_capability.get("warnings", []),
        "document_section_count": len(document_map.get("sections", [])),
        "statement_counts_by_kind": _statement_counts_by_kind(statements),
        "row_count": len(rows),
        "selected_field_mapping_statuses": {
            str(mapping.get("field_id")): str(mapping.get("status"))
            for mapping in mappings
        },
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _statement_counts_by_kind(statements: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for statement in statements:
        kind = str(statement.get("statement_kind"))
        counts[kind] = counts.get(kind, 0) + 1
    return counts
