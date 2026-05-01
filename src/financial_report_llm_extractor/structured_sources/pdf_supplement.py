"""Selected PDF evidence supplement for source-first exports."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path
from typing import Literal

from financial_report_llm_extractor.models import Evidence
from financial_report_llm_extractor.retrieval import retrieve_candidates
from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportItem,
    SourceFirstExportResult,
)


PdfSupplementStatus = Literal["pdf_evidence_found", "missing_pdf_evidence"]
ConsistencyStatus = Literal[
    "value_mentioned",
    "value_not_found_in_snippet",
    "not_checked",
]


@dataclass(frozen=True)
class PdfEvidenceSupplementItem:
    field_id: str
    status: PdfSupplementStatus
    pdf_evidence: tuple[Evidence, ...] = field(default_factory=tuple)
    consistency_status: ConsistencyStatus = "not_checked"
    errors: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "field_id": self.field_id,
            "status": self.status,
            "pdf_evidence": [
                _pdf_evidence_to_dict(evidence) for evidence in self.pdf_evidence
            ],
            "consistency_status": self.consistency_status,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class PdfEvidenceSupplementResult:
    profile: str
    catalog_id: str
    catalog_version: str
    items: dict[str, PdfEvidenceSupplementItem]

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


def build_pdf_evidence_supplement(
    export_result: SourceFirstExportResult,
    chunks: list[dict[str, object]],
    *,
    fields: tuple[str, ...] | None = None,
    limit: int = 1,
) -> PdfEvidenceSupplementResult:
    selected_fields = fields or tuple(
        field_id
        for field_id, item in export_result.items.items()
        if item.status == "needs_pdf_evidence"
    )
    items = {
        field_id: _build_item(
            field_id,
            export_result.items[field_id],
            chunks,
            limit=limit,
        )
        for field_id in selected_fields
        if field_id in export_result.items
    }
    return PdfEvidenceSupplementResult(
        profile=export_result.profile,
        catalog_id=export_result.catalog_id,
        catalog_version=export_result.catalog_version,
        items=items,
    )


def apply_pdf_evidence_supplement(
    export_result: SourceFirstExportResult,
    supplement: PdfEvidenceSupplementResult,
) -> SourceFirstExportResult:
    updated_items = dict(export_result.items)
    for field_id, supplement_item in supplement.items.items():
        export_item = updated_items.get(field_id)
        if export_item is None or not supplement_item.pdf_evidence:
            continue
        status = "present" if export_item.status == "needs_pdf_evidence" else export_item.status
        updated_items[field_id] = replace(
            export_item,
            status=status,
            pdf_evidence=supplement_item.pdf_evidence,
        )
    return SourceFirstExportResult(
        profile=export_result.profile,
        catalog_id=export_result.catalog_id,
        catalog_version=export_result.catalog_version,
        items=updated_items,
    )


def write_pdf_evidence_supplement(
    supplement: PdfEvidenceSupplementResult,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(supplement.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return output_path


def _build_item(
    field_id: str,
    export_item: SourceFirstExportItem,
    chunks: list[dict[str, object]],
    *,
    limit: int,
) -> PdfEvidenceSupplementItem:
    candidates = retrieve_candidates(field_id, chunks, limit=limit)
    evidence: list[Evidence] = []
    errors: list[str] = []
    for candidate in candidates:
        try:
            evidence.append(_evidence_from_dict(candidate.evidence))
        except ValueError as exc:
            errors.append(str(exc))

    if not evidence:
        return PdfEvidenceSupplementItem(
            field_id=field_id,
            status="missing_pdf_evidence",
            errors=tuple(errors) or ("no pdf retrieval candidates found",),
        )

    return PdfEvidenceSupplementItem(
        field_id=field_id,
        status="pdf_evidence_found",
        pdf_evidence=tuple(evidence),
        consistency_status=_consistency_status(export_item, tuple(evidence)),
        errors=tuple(errors),
    )


def _evidence_from_dict(raw: dict[str, object]) -> Evidence:
    page = raw.get("page")
    chunk_id = raw.get("chunk_id")
    block_id = raw.get("block_id")
    snippet = raw.get("snippet")
    evidence = Evidence(
        page=int(page) if isinstance(page, int) else 0,
        chunk_id=str(chunk_id) if chunk_id else "",
        block_id=str(block_id) if block_id else "",
        snippet=str(snippet) if snippet else "",
    )
    evidence.validate()
    return evidence


def _consistency_status(
    export_item: SourceFirstExportItem,
    evidence: tuple[Evidence, ...],
) -> ConsistencyStatus:
    value = export_item.value or export_item.normalized_value
    if value is None:
        return "not_checked"
    needle = _normalize_text(_decimal_to_string(value))
    haystack = _normalize_text(" ".join(item.snippet for item in evidence))
    if needle and needle in haystack:
        return "value_mentioned"
    return "value_not_found_in_snippet"


def _decimal_to_string(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f")


def _normalize_text(value: str) -> str:
    return value.replace(",", "").replace(" ", "").lower()


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
