"""Source-first review export artifacts."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

from financial_report_llm_extractor.models import Currency, Evidence
from financial_report_llm_extractor.structured_sources.mapping import (
    MappedTurtleField,
    TurtleMappingResult,
)
from financial_report_llm_extractor.structured_sources.models import SourceEvidence
from financial_report_llm_extractor.structured_sources.reconciliation import (
    ReconciliationReport,
    ReconciliationStatus,
)


ExportProfile = Literal["source_only", "pdf_required"]
ExportItemStatus = Literal[
    "present",
    "missing",
    "ambiguous",
    "conflict",
    "needs_pdf_evidence",
    "blocked",
]


@dataclass(frozen=True)
class SourceFirstExportItem:
    field_id: str
    status: ExportItemStatus
    value: Decimal | None = None
    normalized_value: Decimal | None = None
    currency: Currency = "unknown"
    unit: str | None = None
    period: str | None = None
    scope: str = "unknown"
    source_evidence: tuple[SourceEvidence, ...] = field(default_factory=tuple)
    pdf_evidence: tuple[Evidence, ...] = field(default_factory=tuple)
    mapping_status: str | None = None
    reconciliation_status: ReconciliationStatus | None = None
    derived_from: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "field_id": self.field_id,
            "status": self.status,
            "value": str(self.value) if self.value is not None else None,
            "normalized_value": (
                str(self.normalized_value) if self.normalized_value is not None else None
            ),
            "currency": self.currency,
            "unit": self.unit,
            "period": self.period,
            "scope": self.scope,
            "source_evidence": [
                evidence.to_dict() for evidence in self.source_evidence
            ],
            "pdf_evidence": [
                _pdf_evidence_to_dict(evidence) for evidence in self.pdf_evidence
            ],
            "mapping_status": self.mapping_status,
            "reconciliation_status": self.reconciliation_status,
            "derived_from": list(self.derived_from),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class SourceFirstExportResult:
    profile: ExportProfile
    catalog_id: str
    catalog_version: str
    items: dict[str, SourceFirstExportItem]

    @property
    def summary(self) -> dict[str, object]:
        return build_review_summary(self)

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "catalog_id": self.catalog_id,
            "catalog_version": self.catalog_version,
            "items": {
                field_id: self.items[field_id].to_dict()
                for field_id in sorted(self.items)
            },
        }


def build_source_first_export(
    mapping_result: TurtleMappingResult,
    reconciliation_report: ReconciliationReport,
    *,
    profile: ExportProfile,
    pdf_evidence_by_field: dict[str, tuple[Evidence, ...]] | None = None,
) -> SourceFirstExportResult:
    pdf_evidence_by_field = pdf_evidence_by_field or {}
    items: dict[str, SourceFirstExportItem] = {}
    for field_id, mapped_field in mapping_result.fields.items():
        reconciliation_item = reconciliation_report.items.get(field_id)
        items[field_id] = _build_item(
            mapped_field,
            reconciliation_item.status if reconciliation_item is not None else None,
            profile=profile,
            pdf_evidence=pdf_evidence_by_field.get(field_id, ()),
        )
    return SourceFirstExportResult(
        profile=profile,
        catalog_id=mapping_result.catalog_id,
        catalog_version=mapping_result.catalog_version,
        items=items,
    )


def build_review_summary(result: SourceFirstExportResult) -> dict[str, object]:
    status_counts = Counter(item.status for item in result.items.values())
    return {
        "profile": result.profile,
        "catalog_id": result.catalog_id,
        "catalog_version": result.catalog_version,
        "total_fields": len(result.items),
        "status_counts": dict(sorted(status_counts.items())),
        "present_fields": _fields_with_status(result, "present"),
        "conflict_fields": _fields_with_status(result, "conflict"),
        "fields_requiring_pdf_evidence": _fields_with_status(
            result,
            "needs_pdf_evidence",
        ),
        "missing_fields": _fields_with_status(result, "missing"),
        "ambiguous_fields": _fields_with_status(result, "ambiguous"),
        "blocked_fields": _fields_with_status(result, "blocked"),
    }


def write_source_first_export_artifacts(
    result: SourceFirstExportResult,
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    extraction_path = output_dir / "extraction_result.json"
    summary_path = output_dir / "review_summary.json"
    extraction_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(result.summary, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return {
        "extraction_result": extraction_path,
        "review_summary": summary_path,
    }


def _build_item(
    field: MappedTurtleField,
    reconciliation_status: ReconciliationStatus | None,
    *,
    profile: ExportProfile,
    pdf_evidence: tuple[Evidence, ...],
) -> SourceFirstExportItem:
    status = _export_status(field, reconciliation_status)
    errors = field.errors
    warnings: tuple[str, ...] = ()
    value = field.value
    normalized_value = field.normalized_value
    source_evidence = field.source_evidence

    if field.status == "ambiguous" and reconciliation_status in {"equivalent", "close"}:
        candidate = field.candidates[0]
        value = candidate.value
        normalized_value = candidate.normalized_value
        source_evidence = tuple(
            evidence
            for candidate in field.candidates
            for evidence in candidate.source_evidence
        )
        warnings = (f"multiple source candidates reconciled as {reconciliation_status}",)

    if status == "present" and profile == "pdf_required" and not pdf_evidence:
        status = "needs_pdf_evidence"
        warnings = warnings + ("pdf evidence is required by export profile",)

    return SourceFirstExportItem(
        field_id=field.field_id,
        status=status,
        value=value,
        normalized_value=normalized_value,
        currency=field.currency,
        unit=field.unit,
        period=field.period,
        scope=field.scope,
        source_evidence=source_evidence,
        pdf_evidence=pdf_evidence,
        mapping_status=field.status,
        reconciliation_status=reconciliation_status,
        derived_from=field.derived_from,
        errors=errors,
        warnings=warnings,
    )


def _export_status(
    field: MappedTurtleField,
    reconciliation_status: ReconciliationStatus | None,
) -> ExportItemStatus:
    if reconciliation_status == "conflict":
        return "conflict"
    if field.status in {"present", "derived"}:
        return "present"
    if field.status == "missing":
        return "missing"
    if field.status == "blocked":
        return "blocked"
    if field.status == "ambiguous":
        if reconciliation_status in {"equivalent", "close"}:
            return "present"
        return "ambiguous"
    return "blocked"


def _fields_with_status(
    result: SourceFirstExportResult,
    status: ExportItemStatus,
) -> list[str]:
    return sorted(
        field_id for field_id, item in result.items.items() if item.status == status
    )


def _pdf_evidence_to_dict(evidence: Evidence) -> dict[str, object]:
    evidence.validate()
    return {
        "page": evidence.page,
        "chunk_id": evidence.chunk_id,
        "block_id": evidence.block_id,
        "snippet": evidence.snippet,
        "table_id": evidence.table_id,
        "cell_id": evidence.cell_id,
        "bbox": list(evidence.bbox) if evidence.bbox is not None else None,
    }
