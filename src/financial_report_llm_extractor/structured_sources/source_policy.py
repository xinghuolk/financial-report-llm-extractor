"""Source policy selection and conflict classification."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

from financial_report_llm_extractor.structured_sources.catalog import (
    MarketSourcePolicy,
    SourceMappingCatalog,
    SourceMappingEntry,
)
from financial_report_llm_extractor.structured_sources.mapping import (
    MappedTurtleField,
    TurtleMappingCandidate,
    TurtleMappingResult,
)
from financial_report_llm_extractor.structured_sources.reconciliation import (
    ReconciliationReport,
    ReconciliationStatus,
)

ConflictClassification = Literal[
    "semantic_mismatch",
    "fx_like_ratio",
    "metadata_currency_suspected",
    "normalized_value_conflict",
    "missing_source_candidate",
    "single_source_unverified",
    "currency_metadata_required",
]
SelectionStatus = Literal[
    "selected_primary",
    "selected_single_source",
    "unresolved_conflict",
    "missing",
    "blocked",
]


@dataclass(frozen=True)
class SourcePolicyItem:
    field_id: str
    selection_status: SelectionStatus
    selected_candidate: TurtleMappingCandidate | None = None
    conflict_classifications: tuple[ConflictClassification, ...] = field(
        default_factory=tuple
    )
    verification_required: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)
    reconciliation_status: ReconciliationStatus | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "field_id": self.field_id,
            "selection_status": self.selection_status,
            "selected_candidate": (
                self.selected_candidate.to_dict()
                if self.selected_candidate is not None
                else None
            ),
            "conflict_classifications": list(self.conflict_classifications),
            "verification_required": self.verification_required,
            "warnings": list(self.warnings),
            "reconciliation_status": self.reconciliation_status,
        }


@dataclass(frozen=True)
class SourcePolicyReport:
    catalog_id: str
    catalog_version: str
    company_id: str | None
    market: str | None
    items: dict[str, SourcePolicyItem]

    def to_dict(self) -> dict[str, object]:
        return {
            "catalog_id": self.catalog_id,
            "catalog_version": self.catalog_version,
            "company_id": self.company_id,
            "market": self.market,
            "items": {
                field_id: self.items[field_id].to_dict()
                for field_id in sorted(self.items)
            },
        }


def build_source_policy_report(
    catalog: SourceMappingCatalog,
    mapping: TurtleMappingResult,
    reconciliation: ReconciliationReport,
    *,
    market: str | None = None,
    company_id: str | None = None,
) -> SourcePolicyReport:
    ratio_fields = _fx_like_fields(mapping)
    items: dict[str, SourcePolicyItem] = {}
    for field_id, mapped_field in mapping.fields.items():
        entry = catalog.entries[field_id]
        reconciliation_item = reconciliation.items.get(field_id)
        reconciliation_status = (
            reconciliation_item.status if reconciliation_item is not None else None
        )
        items[field_id] = _resolve_field(
            entry,
            mapped_field,
            market=market,
            reconciliation_status=reconciliation_status,
            fx_like=field_id in ratio_fields,
        )
    return SourcePolicyReport(
        catalog_id=mapping.catalog_id,
        catalog_version=mapping.catalog_version,
        company_id=company_id,
        market=market,
        items=items,
    )


def write_source_policy_report(report: SourcePolicyReport, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return output_path


def _resolve_field(
    entry: SourceMappingEntry,
    field: MappedTurtleField,
    *,
    market: str | None,
    reconciliation_status: ReconciliationStatus | None,
    fx_like: bool,
) -> SourcePolicyItem:
    if field.status == "missing":
        return SourcePolicyItem(
            field_id=field.field_id,
            selection_status="missing",
            conflict_classifications=("missing_source_candidate",),
            reconciliation_status=reconciliation_status,
        )
    if field.status == "blocked":
        return SourcePolicyItem(
            field_id=field.field_id,
            selection_status="blocked",
            reconciliation_status=reconciliation_status,
        )
    if field.status in {"present", "derived"} and field.candidates:
        return _resolve_single_source(entry, field, market, reconciliation_status)

    classifications = _classifications(entry, field, fx_like=fx_like)
    candidate = _primary_candidate(entry, field, market)
    if candidate is not None and _requires_currency_metadata(candidate):
        return SourcePolicyItem(
            field_id=field.field_id,
            selection_status="unresolved_conflict",
            conflict_classifications=classifications
            + ("currency_metadata_required",),
            verification_required=True,
            warnings=("selected primary candidate lacks proven currency metadata",),
            reconciliation_status=reconciliation_status,
        )
    if reconciliation_status in {"equivalent", "close"}:
        return SourcePolicyItem(
            field_id=field.field_id,
            selection_status="selected_primary",
            selected_candidate=candidate or field.candidates[0],
            reconciliation_status=reconciliation_status,
        )

    market_policy = _market_policy(entry, market)
    if (
        candidate is not None
        and market_policy is not None
        and market_policy.on_conflict == "select_primary_require_pdf"
    ):
        return SourcePolicyItem(
            field_id=field.field_id,
            selection_status="selected_primary",
            selected_candidate=candidate,
            conflict_classifications=classifications,
            verification_required=True,
            warnings=tuple(
                f"source policy selected primary candidate despite {classification}"
                for classification in classifications
            ),
            reconciliation_status=reconciliation_status,
        )
    return SourcePolicyItem(
        field_id=field.field_id,
        selection_status="unresolved_conflict",
        conflict_classifications=classifications or ("normalized_value_conflict",),
        verification_required=True,
        reconciliation_status=reconciliation_status,
    )


def _resolve_single_source(
    entry: SourceMappingEntry,
    field: MappedTurtleField,
    market: str | None,
    reconciliation_status: ReconciliationStatus | None,
) -> SourcePolicyItem:
    candidate = field.candidates[0]
    market_policy = _market_policy(entry, market)
    requires_pdf = bool(
        market_policy is not None and market_policy.single_source_requires_pdf
    )
    classifications: tuple[ConflictClassification, ...] = (
        ("single_source_unverified",) if requires_pdf else ()
    )
    return SourcePolicyItem(
        field_id=field.field_id,
        selection_status="selected_single_source",
        selected_candidate=candidate,
        conflict_classifications=classifications,
        verification_required=requires_pdf,
        warnings=(
            ("single source candidate requires PDF verification",)
            if requires_pdf
            else ()
        ),
        reconciliation_status=reconciliation_status,
    )


def _classifications(
    entry: SourceMappingEntry,
    field: MappedTurtleField,
    *,
    fx_like: bool,
) -> tuple[ConflictClassification, ...]:
    classifications: list[ConflictClassification] = []
    if _semantic_mismatch(entry, field):
        classifications.append("semantic_mismatch")
    if fx_like:
        classifications.extend(["fx_like_ratio", "metadata_currency_suspected"])
    if not classifications and _values_differ(field):
        classifications.append("normalized_value_conflict")
    return tuple(classifications)


def _semantic_mismatch(entry: SourceMappingEntry, field: MappedTurtleField) -> bool:
    policy = entry.source_policy
    if policy is None:
        return False
    for candidate in field.candidates + field.policy_evidence_candidates:
        variants = policy.semantic_variants.get(candidate.source)
        if variants is None:
            continue
        label = candidate.raw_field_code or candidate.raw_field_name
        if label in variants.related:
            return True
    return False


def _values_differ(field: MappedTurtleField) -> bool:
    values = {
        candidate.normalized_value
        for candidate in field.candidates
        if candidate.normalized_value is not None
    }
    return len(values) > 1


def _requires_currency_metadata(candidate: TurtleMappingCandidate) -> bool:
    return (
        candidate.currency in {"unknown", "ambiguous"}
        or candidate.unit is None
        or candidate.canonical_unit is None
    )


def _market_policy(
    entry: SourceMappingEntry,
    market: str | None,
) -> MarketSourcePolicy | None:
    if entry.source_policy is None or market is None:
        return None
    return entry.source_policy.market_policies.get(market)


def _primary_candidate(
    entry: SourceMappingEntry,
    field: MappedTurtleField,
    market: str | None,
) -> TurtleMappingCandidate | None:
    market_policy = _market_policy(entry, market)
    if market_policy is None:
        return None
    primary_source = market_policy.primary_route.split("_", 1)[0]
    source_candidates = [
        candidate
        for candidate in field.candidates
        if candidate.source == primary_source
    ]
    if not source_candidates:
        return None
    if entry.source_policy is None:
        return source_candidates[0]
    variants = entry.source_policy.semantic_variants.get(primary_source)
    if variants is None:
        return source_candidates[0]
    for primary_label in variants.primary:
        for candidate in source_candidates:
            if (
                candidate.raw_field_code == primary_label
                or candidate.raw_field_name == primary_label
            ):
                return candidate
    return source_candidates[0]


def _fx_like_fields(
    mapping: TurtleMappingResult,
    *,
    relative_tolerance: Decimal = Decimal("0.001"),
) -> set[str]:
    ratios: list[tuple[str, Decimal]] = []
    for field_id, mapped_field in mapping.fields.items():
        if len(mapped_field.candidates) != 2:
            continue
        akshare_candidate = _candidate_for_source(mapped_field, "akshare")
        yahoo_candidate = _candidate_for_source(mapped_field, "yahoo")
        if akshare_candidate is None or yahoo_candidate is None:
            continue
        if akshare_candidate.period != yahoo_candidate.period:
            continue
        base = akshare_candidate.normalized_value
        other = yahoo_candidate.normalized_value
        if base is None or base == Decimal("0") or other is None:
            continue
        ratio = other / base
        if ratio == 1:
            continue
        ratios.append((field_id, ratio))
    for _, ratio in ratios:
        similar = [
            other_field_id
            for other_field_id, other_ratio in ratios
            if _relative_difference(ratio, other_ratio) <= relative_tolerance
        ]
        if len(similar) >= 3:
            return set(similar)
    return set()


def _candidate_for_source(
    field: MappedTurtleField,
    source: str,
) -> TurtleMappingCandidate | None:
    for candidate in field.candidates:
        if candidate.source == source:
            return candidate
    return None


def _relative_difference(left: Decimal, right: Decimal) -> Decimal:
    denominator = max(abs(left), abs(right))
    if denominator == 0:
        return Decimal("0")
    return abs(left - right) / denominator
