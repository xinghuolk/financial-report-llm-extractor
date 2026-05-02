"""Turtle field taxonomy loading and validation contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args


Priority = Literal["P0", "P1", "P2", "P3", "P4"]
FieldDomain = Literal[
    "income_statement",
    "balance_sheet",
    "cash_flow",
    "shareholder_return",
    "accounting_adjustments",
    "notes_and_mda",
]
StatementType = Literal[
    "income_statement",
    "balance_sheet",
    "cash_flow",
    "notes",
    "mda",
    "announcement",
    "mixed",
]
FieldValueType = Literal["money", "number", "percent", "text", "derived"]
SourceMode = Literal["direct", "derived", "source_optional", "pdf_only", "llm_review"]
PeriodType = Literal["duration", "point_in_time", "annual_text", "event"]
ScopeExpectation = Literal[
    "consolidated",
    "parent",
    "attributable_to_owners",
    "unknown",
    "not_applicable",
]
Requirement = Literal["required", "optional", "not_applicable"]
EvidenceRequirement = Literal[
    "source_only_allowed",
    "pdf_required",
    "llm_review_required",
]
FallbackPolicy = Literal[
    "source_required",
    "pdf_allowed",
    "llm_review_required",
    "manual_review_required",
]
PrimaryRoute = Literal[
    "akshare_direct",
    "yahoo_direct",
    "source_derived",
    "pdf_evidence",
    "llm_review",
    "unsupported_first_stage",
]
RouteSource = Literal["akshare", "yahoo", "pdf", "llm", "derived"]
RouteMode = Literal["direct", "derived", "evidence", "review", "unsupported"]
VerificationStatus = Literal["verified", "expected", "unknown", "unsupported"]


PRIMARY_ROUTE_MATCHES: dict[PrimaryRoute, tuple[RouteSource, RouteMode]] = {
    "akshare_direct": ("akshare", "direct"),
    "yahoo_direct": ("yahoo", "direct"),
    "source_derived": ("derived", "derived"),
    "pdf_evidence": ("pdf", "evidence"),
    "llm_review": ("llm", "review"),
    "unsupported_first_stage": ("derived", "unsupported"),
}


@dataclass(frozen=True)
class FieldTaxonomyEntry:
    field_id: str
    priority: Priority
    domain: FieldDomain
    statement_type: StatementType
    value_type: FieldValueType
    source_mode: SourceMode
    period_type: PeriodType
    scope_expectation: ScopeExpectation
    currency_requirement: Requirement
    unit_requirement: Requirement
    evidence_requirement: EvidenceRequirement
    fallback_policy: FallbackPolicy
    description: str

    def validate(self) -> None:
        if not self.field_id:
            raise ValueError("field_id is required")
        if not self.priority:
            raise ValueError("priority is required")
        if not self.description:
            raise ValueError("description is required")
        _validate_literal("priority", self.priority, Priority)
        _validate_literal("domain", self.domain, FieldDomain)
        _validate_literal("invalid statement_type", self.statement_type, StatementType)
        _validate_literal("invalid value_type", self.value_type, FieldValueType)
        _validate_literal("source_mode", self.source_mode, SourceMode)
        _validate_literal("invalid period_type", self.period_type, PeriodType)
        _validate_literal(
            "invalid scope_expectation",
            self.scope_expectation,
            ScopeExpectation,
        )
        _validate_literal("currency_requirement", self.currency_requirement, Requirement)
        _validate_literal("unit_requirement", self.unit_requirement, Requirement)
        _validate_literal(
            "evidence_requirement",
            self.evidence_requirement,
            EvidenceRequirement,
        )
        _validate_literal("invalid fallback_policy", self.fallback_policy, FallbackPolicy)
        if self.value_type == "money" and (
            self.currency_requirement == "not_applicable"
            or self.unit_requirement == "not_applicable"
        ):
            raise ValueError("money fields require currency/unit applicability")


@dataclass(frozen=True)
class FieldTaxonomyCatalog:
    catalog_id: str
    version: str
    source_priority_catalog: str
    fields: dict[str, FieldTaxonomyEntry]

    def validate(self) -> None:
        if not self.catalog_id:
            raise ValueError("catalog_id is required")
        if not self.version:
            raise ValueError("version is required")
        if not self.source_priority_catalog:
            raise ValueError("source_priority_catalog is required")
        for field_id, entry in self.fields.items():
            if not field_id:
                raise ValueError("taxonomy field ids cannot be empty")
            if field_id != entry.field_id:
                raise ValueError("taxonomy field id must match entry field_id")
            entry.validate()


@dataclass(frozen=True)
class CoverageRoute:
    source: RouteSource
    mode: RouteMode
    status: VerificationStatus
    statement_type: StatementType
    evidence_requirement: EvidenceRequirement

    def validate(self) -> None:
        if not self.source:
            raise ValueError("source is required")
        if not self.mode:
            raise ValueError("mode is required")
        if not self.status:
            raise ValueError("status is required")
        if not self.statement_type:
            raise ValueError("statement_type is required")
        if not self.evidence_requirement:
            raise ValueError("evidence_requirement is required")
        _validate_literal("invalid source", self.source, RouteSource)
        _validate_literal("invalid mode", self.mode, RouteMode)
        _validate_literal("invalid status", self.status, VerificationStatus)
        _validate_literal("invalid statement_type", self.statement_type, StatementType)
        _validate_literal(
            "invalid evidence_requirement",
            self.evidence_requirement,
            EvidenceRequirement,
        )


@dataclass(frozen=True)
class CoverageMatrixEntry:
    field_id: str
    domain: FieldDomain
    priority: Priority
    primary_route: PrimaryRoute
    verification: VerificationStatus
    routes: tuple[CoverageRoute, ...]
    notes: str = ""

    def validate(self) -> None:
        if not self.field_id:
            raise ValueError("coverage field_id is required")
        if not self.domain:
            raise ValueError("domain is required")
        if not self.priority:
            raise ValueError("priority is required")
        if not self.primary_route:
            raise ValueError("primary_route is required")
        if not self.verification:
            raise ValueError("verification is required")
        if not self.notes:
            raise ValueError("notes are required")
        _validate_literal("coverage domain", self.domain, FieldDomain)
        _validate_literal("coverage priority", self.priority, Priority)
        _validate_literal("invalid primary_route", self.primary_route, PrimaryRoute)
        _validate_literal("invalid verification", self.verification, VerificationStatus)
        if not self.routes:
            raise ValueError("coverage routes are required")
        for route in self.routes:
            route.validate()
        if not _primary_route_has_matching_route(self):
            raise ValueError(
                f"{self.field_id}: primary_route has no matching route"
            )
        if self.verification == "verified" and not _primary_route_is_verified(
            self
        ):
            raise ValueError(
                f"{self.field_id}: verified field requires verified primary route"
            )


@dataclass(frozen=True)
class CoverageMatrix:
    matrix_id: str
    version: str
    taxonomy_catalog: str
    fields: dict[str, CoverageMatrixEntry]

    def validate(self) -> None:
        if not self.matrix_id:
            raise ValueError("matrix_id is required")
        if not self.version:
            raise ValueError("version is required")
        if not self.taxonomy_catalog:
            raise ValueError("taxonomy_catalog is required")
        if not self.fields:
            raise ValueError("coverage fields are required")
        for field_id, entry in self.fields.items():
            if not field_id:
                raise ValueError("coverage field ids cannot be empty")
            if field_id != entry.field_id:
                raise ValueError("coverage field id must match entry field_id")
            entry.validate()


def load_field_taxonomy(path: Path) -> FieldTaxonomyCatalog:
    data = json.loads(path.read_text(encoding="utf-8"))
    fields = {
        field_id: FieldTaxonomyEntry(field_id=field_id, **metadata)
        for field_id, metadata in data["fields"].items()
    }
    taxonomy = FieldTaxonomyCatalog(
        catalog_id=data["catalog_id"],
        version=data["version"],
        source_priority_catalog=data["source_priority_catalog"],
        fields=fields,
    )
    taxonomy.validate()
    return taxonomy


def load_coverage_matrix(path: Path) -> CoverageMatrix:
    data = json.loads(path.read_text(encoding="utf-8"))
    fields = {
        field_id: CoverageMatrixEntry(
            field_id=field_id,
            domain=metadata.get("domain", ""),
            priority=metadata.get("priority", ""),
            primary_route=metadata.get("primary_route", ""),
            verification=metadata.get("verification", ""),
            routes=tuple(
                CoverageRoute(
                    source=route.get("source", ""),
                    mode=route.get("mode", ""),
                    status=route.get("status", ""),
                    statement_type=route.get("statement_type", ""),
                    evidence_requirement=route.get("evidence_requirement", ""),
                )
                for route in metadata.get("routes", [])
            ),
            notes=metadata.get("notes", ""),
        )
        for field_id, metadata in data.get("fields", {}).items()
    }
    matrix = CoverageMatrix(
        matrix_id=str(data.get("matrix_id", "")),
        version=str(data.get("version", "")),
        taxonomy_catalog=str(data.get("taxonomy_catalog", "")),
        fields=fields,
    )
    matrix.validate()
    return matrix


def load_priority_field_ids(path: Path) -> set[str]:
    priority_catalog = load_priority_catalog(path)
    return set(priority_catalog.field_priorities)


@dataclass(frozen=True)
class PriorityFieldCatalog:
    catalog_id: str
    field_priorities: dict[str, Priority]
    duplicate_field_ids: tuple[str, ...]


def load_priority_catalog(path: Path) -> PriorityFieldCatalog:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    field_priorities: dict[str, Priority] = {}
    duplicate_field_ids: set[str] = set()
    for group in catalog["priorities"]:
        priority = group["priority"]
        _validate_literal("priority", priority, Priority)
        for raw_field_id in group["fields"]:
            field_id = str(raw_field_id)
            if field_id in field_priorities:
                duplicate_field_ids.add(field_id)
                continue
            field_priorities[field_id] = priority
    return PriorityFieldCatalog(
        catalog_id=catalog["catalog_id"],
        field_priorities=field_priorities,
        duplicate_field_ids=tuple(sorted(duplicate_field_ids)),
    )


def validate_taxonomy_against_priority_catalog(
    taxonomy: FieldTaxonomyCatalog,
    priority_catalog_path: Path,
) -> None:
    priority_catalog = load_priority_catalog(priority_catalog_path)
    priority_field_ids = set(priority_catalog.field_priorities)
    taxonomy_field_ids = set(taxonomy.fields)
    missing = sorted(priority_field_ids - taxonomy_field_ids)
    unknown = sorted(taxonomy_field_ids - priority_field_ids)
    priority_mismatches = [
        field_id
        for field_id in sorted(priority_field_ids & taxonomy_field_ids)
        if taxonomy.fields[field_id].priority
        != priority_catalog.field_priorities[field_id]
    ]
    errors: list[str] = []
    if taxonomy.source_priority_catalog != priority_catalog.catalog_id:
        errors.append(
            "source_priority_catalog mismatch: "
            f"{taxonomy.source_priority_catalog} != {priority_catalog.catalog_id}"
        )
    if priority_catalog.duplicate_field_ids:
        errors.append(
            "duplicate priority catalog fields: "
            f"{', '.join(priority_catalog.duplicate_field_ids)}"
        )
    if missing:
        errors.append(f"missing taxonomy fields: {', '.join(missing)}")
    if unknown:
        errors.append(f"unknown taxonomy fields: {', '.join(unknown)}")
    if priority_mismatches:
        errors.append(f"priority mismatch: {', '.join(priority_mismatches)}")
    if errors:
        raise ValueError("; ".join(errors))


def validate_coverage_matrix_against_taxonomy(
    matrix: CoverageMatrix,
    taxonomy: FieldTaxonomyCatalog,
) -> None:
    matrix.validate()
    taxonomy.validate()
    coverage_field_ids = set(matrix.fields)
    taxonomy_field_ids = set(taxonomy.fields)
    missing = sorted(taxonomy_field_ids - coverage_field_ids)
    unknown = sorted(coverage_field_ids - taxonomy_field_ids)
    errors: list[str] = []
    if matrix.taxonomy_catalog != taxonomy.catalog_id:
        errors.append(
            "taxonomy_catalog mismatch: "
            f"{matrix.taxonomy_catalog} != {taxonomy.catalog_id}"
        )
    if missing:
        errors.append(f"missing coverage fields: {', '.join(missing)}")
    if unknown:
        errors.append(f"unknown coverage fields: {', '.join(unknown)}")
    for field_id in sorted(coverage_field_ids & taxonomy_field_ids):
        coverage_entry = matrix.fields[field_id]
        taxonomy_entry = taxonomy.fields[field_id]
        if coverage_entry.domain != taxonomy_entry.domain:
            errors.append(f"{field_id}: domain mismatch")
        if coverage_entry.priority != taxonomy_entry.priority:
            errors.append(f"{field_id}: priority mismatch")
        if (
            taxonomy_entry.source_mode in ("pdf_only", "llm_review")
            and coverage_entry.primary_route not in ("pdf_evidence", "llm_review")
        ):
            errors.append(
                f"{field_id}: source mode requires PDF or LLM route"
            )
        if (
            taxonomy_entry.source_mode == "direct"
            and coverage_entry.verification != "unknown"
            and not _direct_source_mode_has_provider_route(coverage_entry)
        ):
            errors.append(
                f"{field_id}: direct source mode requires provider route unless unknown"
            )
    if errors:
        raise ValueError("; ".join(errors))


def _primary_route_has_matching_route(entry: CoverageMatrixEntry) -> bool:
    expected_source, expected_mode = PRIMARY_ROUTE_MATCHES[entry.primary_route]
    return any(
        route.source == expected_source and route.mode == expected_mode
        for route in entry.routes
    )


def _primary_route_is_verified(entry: CoverageMatrixEntry) -> bool:
    expected_source, expected_mode = PRIMARY_ROUTE_MATCHES[entry.primary_route]
    return any(
        route.source == expected_source
        and route.mode == expected_mode
        and route.status == "verified"
        for route in entry.routes
    )


def _direct_source_mode_has_provider_route(entry: CoverageMatrixEntry) -> bool:
    if entry.primary_route not in ("akshare_direct", "yahoo_direct"):
        return False
    return any(
        route.source in ("akshare", "yahoo") and route.mode == "direct"
        for route in entry.routes
    )


def _validate_literal(name: str, value: str, literal: Any) -> None:
    if value not in get_args(literal):
        raise ValueError(f"{name} has unsupported value: {value}")
