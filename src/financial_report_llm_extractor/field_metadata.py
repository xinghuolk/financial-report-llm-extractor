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
SourceMode = Literal["direct", "derived", "source_optional", "pdf_only", "llm_review"]
Requirement = Literal["required", "optional", "not_applicable"]
EvidenceRequirement = Literal[
    "source_only_allowed",
    "pdf_required",
    "llm_review_required",
]


@dataclass(frozen=True)
class FieldTaxonomyEntry:
    field_id: str
    priority: Priority
    domain: FieldDomain
    statement_type: str
    value_type: str
    source_mode: SourceMode
    period_type: str
    scope_expectation: str
    currency_requirement: Requirement
    unit_requirement: Requirement
    evidence_requirement: EvidenceRequirement
    fallback_policy: str
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
        _validate_literal("source_mode", self.source_mode, SourceMode)
        _validate_literal("currency_requirement", self.currency_requirement, Requirement)
        _validate_literal("unit_requirement", self.unit_requirement, Requirement)
        _validate_literal(
            "evidence_requirement",
            self.evidence_requirement,
            EvidenceRequirement,
        )
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


def _validate_literal(name: str, value: str, literal: Any) -> None:
    if value not in get_args(literal):
        raise ValueError(f"{name} has unsupported value: {value}")
