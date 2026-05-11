"""Source-first review export artifacts."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal, Mapping

from financial_report_llm_extractor.models import Currency, Evidence
from financial_report_llm_extractor.structured_sources.mapping import (
    MappedTurtleField,
    TurtleMappingCandidate,
    TurtleMappingResult,
)
from financial_report_llm_extractor.structured_sources.models import SourceEvidence
from financial_report_llm_extractor.structured_sources.reconciliation import (
    ReconciliationReport,
    ReconciliationStatus,
)
from financial_report_llm_extractor.structured_sources.source_policy import (
    SourcePolicyItem,
    SourcePolicyReport,
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
    canonical_unit: Currency | None = None
    period: str | None = None
    scope: str = "unknown"
    source_evidence: tuple[SourceEvidence, ...] = field(default_factory=tuple)
    pdf_evidence: tuple[Evidence, ...] = field(default_factory=tuple)
    mapping_status: str | None = None
    reconciliation_status: ReconciliationStatus | None = None
    derived_from: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    selection_status: str | None = None
    selected_source: str | None = None
    verification_required: bool = False
    conflict_classifications: tuple[str, ...] = field(default_factory=tuple)
    review_notes: tuple[str, ...] = field(default_factory=tuple)
    trust_policy_evidence: Mapping[str, object] | None = None

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
            "canonical_unit": self.canonical_unit,
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
            "selection_status": self.selection_status,
            "selected_source": self.selected_source,
            "verification_required": self.verification_required,
            "conflict_classifications": list(self.conflict_classifications),
            "review_notes": list(self.review_notes),
            "trust_policy_evidence": self.trust_policy_evidence,
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
    source_policy_report: SourcePolicyReport | None = None,
) -> SourceFirstExportResult:
    pdf_evidence_by_field = pdf_evidence_by_field or {}
    items: dict[str, SourceFirstExportItem] = {}
    for field_id, mapped_field in mapping_result.fields.items():
        reconciliation_item = reconciliation_report.items.get(field_id)
        policy_item = (
            source_policy_report.items.get(field_id)
            if source_policy_report is not None
            else None
        )
        items[field_id] = _build_item(
            mapped_field,
            reconciliation_item.status if reconciliation_item is not None else None,
            profile=profile,
            pdf_evidence=pdf_evidence_by_field.get(field_id, ()),
            policy_item=policy_item,
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
        "selected_with_warnings_fields": sorted(
            field_id
            for field_id, item in result.items.items()
            if item.status == "present" and (item.warnings or item.verification_required)
        ),
        "unresolved_conflict_fields": sorted(
            field_id
            for field_id, item in result.items.items()
            if item.selection_status == "unresolved_conflict"
        ),
        "fields_requiring_pdf_evidence": sorted(
            field_id
            for field_id, item in result.items.items()
            if item.status == "needs_pdf_evidence" or item.verification_required
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
    policy_item: SourcePolicyItem | None = None,
) -> SourceFirstExportItem:
    status = _export_status(field, reconciliation_status)
    errors = field.errors
    warnings: tuple[str, ...] = ()
    value = field.value
    normalized_value = field.normalized_value
    currency = field.currency
    unit = field.unit
    canonical_unit = field.canonical_unit
    period = field.period
    scope = field.scope
    source_evidence = field.source_evidence
    selection_status = policy_item.selection_status if policy_item is not None else None
    selected_source: str | None = None
    verification_required = (
        policy_item.verification_required if policy_item is not None else False
    )
    conflict_classifications = (
        policy_item.conflict_classifications if policy_item is not None else ()
    )
    # Intentionally exclude field.review_notes (e.g., null_interpreted_as_zero):
    # those are mapping-layer audit signals only and must not gate clean_present.
    # See docs/superpowers/specs/2026-05-08-phase-h0-null-as-zero-policy.md.
    review_notes = (
        tuple(policy_item.conflict_classifications) if policy_item is not None else ()
    )
    trust_policy_evidence = (
        policy_item.trust_policy_evidence if policy_item is not None else None
    )
    if policy_item is not None:
        warnings = policy_item.warnings
    policy_unresolved = (
        policy_item is not None
        and policy_item.selection_status == "unresolved_conflict"
    )

    if (
        field.status == "ambiguous"
        and reconciliation_status in {"equivalent", "close"}
        and not policy_unresolved
    ):
        candidate = _representative_candidate(field.candidates)
        value = candidate.value
        normalized_value = candidate.normalized_value
        currency = candidate.currency
        unit = candidate.unit
        canonical_unit = candidate.canonical_unit
        period = candidate.period
        scope = candidate.scope
        source_evidence = tuple(
            evidence
            for candidate in field.candidates
            for evidence in candidate.source_evidence
        )
        errors = ()
        if policy_item is None:
            warnings = (
                f"multiple source candidates reconciled as {reconciliation_status}",
            )

    if policy_unresolved:
        status = "conflict"

    if (
        policy_item is not None
        and policy_item.selection_status in {"selected_primary", "selected_single_source"}
        and policy_item.selected_candidate is not None
    ):
        candidate = policy_item.selected_candidate
        status = "present"
        value = candidate.value
        normalized_value = candidate.normalized_value
        currency = candidate.currency
        unit = candidate.unit
        canonical_unit = candidate.canonical_unit
        period = candidate.period
        scope = candidate.scope
        source_evidence = candidate.source_evidence
        errors = ()
        warnings = policy_item.warnings
        selected_source = candidate.source

    # Phase H2.4 #3: derived clean_present rows (status="present" via the
    # derived branch in source_policy) carry no selected_candidate, so the
    # block above leaves selected_source=None. Fall back to the underlying
    # source_evidence: when all evidence shares a single provider (the
    # derivation's operand provider), surface that as selected_source so
    # reviewers can audit the derivation source. Multi-provider derivations
    # are rejected at the mapping layer (mapping.py:271-279), so this stays
    # deterministic.
    if (
        selected_source is None
        and status == "present"
        and source_evidence
    ):
        evidence_sources = {ev.source for ev in source_evidence}
        if len(evidence_sources) == 1:
            selected_source = next(iter(evidence_sources))

    if status == "present" and profile == "pdf_required" and not pdf_evidence:
        status = "needs_pdf_evidence"
        warnings = warnings + ("pdf evidence is required by export profile",)

    return SourceFirstExportItem(
        field_id=field.field_id,
        status=status,
        value=value,
        normalized_value=normalized_value,
        currency=currency,
        unit=unit,
        canonical_unit=canonical_unit,
        period=period,
        scope=scope,
        source_evidence=source_evidence,
        pdf_evidence=pdf_evidence,
        mapping_status=field.status,
        reconciliation_status=reconciliation_status,
        derived_from=field.derived_from,
        errors=errors,
        warnings=warnings,
        selection_status=selection_status,
        selected_source=selected_source,
        verification_required=verification_required,
        conflict_classifications=conflict_classifications,
        review_notes=review_notes,
        trust_policy_evidence=trust_policy_evidence,
    )


def _export_status(
    field: MappedTurtleField,
    reconciliation_status: ReconciliationStatus | None,
) -> ExportItemStatus:
    if field.status in {"present", "derived"}:
        return "present"
    if field.status == "missing":
        return "missing"
    if field.status == "blocked":
        return "blocked"
    if field.status == "ambiguous":
        if reconciliation_status == "blocked":
            return "blocked"
        if reconciliation_status == "conflict":
            return "conflict"
        if reconciliation_status in {"equivalent", "close"}:
            return "present"
        return "ambiguous"
    return "blocked"


def _representative_candidate(
    candidates: tuple[TurtleMappingCandidate, ...],
) -> TurtleMappingCandidate:
    source_rank = {"akshare": 0, "yahoo": 1}
    return sorted(
        candidates,
        key=lambda candidate: (
            source_rank.get(candidate.source, 99),
            candidate.source,
            candidate.raw_field_name,
            candidate.raw_field_code or "",
        ),
    )[0]


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
