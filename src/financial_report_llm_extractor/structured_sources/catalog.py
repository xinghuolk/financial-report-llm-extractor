"""Turtle source mapping catalog loading."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_args

from financial_report_llm_extractor.field_metadata import (
    FallbackPolicy,
    FieldDomain,
    PrimaryRoute,
    Requirement,
    SourceMode,
    StatementType,
    VerificationStatus,
)
from financial_report_llm_extractor.structured_sources.models import SourceValueType


REFERENCED_REQUIRED_METADATA = (
    "value_type",
    "statement_type",
    "domain",
    "source_mode",
    "primary_route",
    "verification_status",
    "currency_requirement",
    "unit_requirement",
    "fallback_policy",
)


@dataclass(frozen=True)
class SourceSemanticVariants:
    primary: tuple[str, ...] = field(default_factory=tuple)
    related: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MarketSourcePolicy:
    primary_route: str
    cross_check_routes: tuple[str, ...] = field(default_factory=tuple)
    on_conflict: str = "preserve_conflict"
    single_source_requires_pdf: bool = False


@dataclass(frozen=True)
class SourcePolicy:
    semantic_concept: str
    semantic_variants: dict[str, SourceSemanticVariants] = field(default_factory=dict)
    market_policies: dict[str, MarketSourcePolicy] = field(default_factory=dict)
    verification_requirement: str = "none"


@dataclass(frozen=True)
class SourceMappingEntry:
    field_id: str
    priority: str
    value_type: SourceValueType
    statement_type: str
    currency_requirement: Requirement
    unit_requirement: Requirement
    source_aliases: dict[str, tuple[str, ...]]
    domain: str = "unknown"
    source_mode: str = "direct"
    primary_route: str = "akshare_direct"
    verification_status: str = "unknown"
    period_expectation: str = "annual"
    scope_expectation: str = "unknown"
    pdf_aliases: tuple[str, ...] = field(default_factory=tuple)
    derivation: str | None = None
    fallback_policy: str = "pdf_allowed"
    source_policy: SourcePolicy | None = None

    def validate(self) -> None:
        if not self.field_id:
            raise ValueError("field_id is required")
        if not self.priority:
            raise ValueError("priority is required")
        if not self.statement_type:
            raise ValueError("statement_type is required")
        if not self.source_aliases:
            raise ValueError("source_aliases is required")
        _validate_literal("invalid value_type", self.value_type, SourceValueType)
        _validate_literal("invalid statement_type", self.statement_type, StatementType)
        if self.domain != "unknown":
            _validate_literal("domain", self.domain, FieldDomain)
        _validate_literal("source_mode", self.source_mode, SourceMode)
        _validate_literal("invalid primary_route", self.primary_route, PrimaryRoute)
        _validate_literal(
            "invalid verification_status",
            self.verification_status,
            VerificationStatus,
        )
        _validate_literal("currency_requirement", self.currency_requirement, Requirement)
        _validate_literal("unit_requirement", self.unit_requirement, Requirement)
        _validate_literal("invalid fallback_policy", self.fallback_policy, FallbackPolicy)


@dataclass(frozen=True)
class SourceMappingCatalog:
    catalog_id: str
    version: str
    entries: dict[str, SourceMappingEntry]

    def validate(self) -> None:
        if not self.catalog_id:
            raise ValueError("catalog_id is required")
        if not self.version:
            raise ValueError("version is required")
        if not self.entries:
            raise ValueError("entries is required")
        for field_id, entry in self.entries.items():
            if field_id != entry.field_id:
                raise ValueError("entry key must match field_id")
            entry.validate()


def load_source_mapping_catalog(
    catalog_path: Path,
    *,
    priorities: tuple[str, ...],
) -> SourceMappingCatalog:
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("source mapping catalog must be an object")
    has_referenced_metadata = bool(
        raw.get("taxonomy_catalog") or raw.get("coverage_matrix")
    )
    selected_priorities = set(priorities)
    priority_by_field: dict[str, str] = {}
    raw_priorities = raw.get("priorities", [])
    if not isinstance(raw_priorities, list):
        raise ValueError("source mapping priorities must be a list")
    for group in raw_priorities:
        if not isinstance(group, dict):
            raise ValueError("source mapping priority entry must be an object")
        priority = str(group.get("priority", ""))
        if priority not in selected_priorities:
            continue
        raw_priority_fields = group.get("fields", [])
        if not isinstance(raw_priority_fields, list):
            raise ValueError("source mapping priority fields must be a list")
        for field_id in raw_priority_fields:
            priority_by_field.setdefault(str(field_id), priority)

    mappings: dict[str, Any] = raw.get("source_mappings", {})
    if not isinstance(mappings, dict):
        raise ValueError("source_mappings must be an object")
    entries: dict[str, SourceMappingEntry] = {}
    for field_id, priority in priority_by_field.items():
        mapping = mappings.get(field_id, {})
        if not isinstance(mapping, dict):
            raise ValueError("source mapping entry must be an object")
        if has_referenced_metadata:
            _require_referenced_metadata(field_id, mapping)
            _validate_referenced_metadata_values(mapping)
        raw_aliases = mapping.get("source_aliases", {})
        if not isinstance(raw_aliases, dict):
            raise ValueError("source_aliases must be an object")
        aliases: dict[str, tuple[str, ...]] = {}
        for source, values in raw_aliases.items():
            if not isinstance(values, list):
                raise ValueError("source alias values must be a list")
            aliases[str(source)] = tuple(str(alias) for alias in values)
        statement_type = str(mapping.get("statement_type", "unknown"))
        entry = SourceMappingEntry(
            field_id=field_id,
            priority=priority,
            value_type=mapping.get("value_type", "money"),
            statement_type=statement_type,
            currency_requirement=mapping.get("currency_requirement", "required"),
            unit_requirement=mapping.get("unit_requirement", "required"),
            source_aliases=aliases,
            domain=mapping.get("domain", _default_domain(statement_type)),
            source_mode=mapping.get("source_mode", "direct"),
            primary_route=mapping.get("primary_route", "akshare_direct"),
            verification_status=mapping.get("verification_status", "unknown"),
            period_expectation=mapping.get("period_expectation", "annual"),
            scope_expectation=mapping.get("scope_expectation", "unknown"),
            pdf_aliases=tuple(str(alias) for alias in mapping.get("pdf_aliases", [])),
            derivation=mapping.get("derivation"),
            fallback_policy=mapping.get("fallback_policy", "pdf_allowed"),
            source_policy=_parse_source_policy(mapping.get("source_policy")),
        )
        entry.validate()
        entries[field_id] = entry

    catalog = SourceMappingCatalog(
        catalog_id=str(raw.get("catalog_id", "")),
        version=str(raw.get("version", "")),
        entries=entries,
    )
    catalog.validate()
    return catalog


def _parse_source_policy(raw_policy: object) -> SourcePolicy | None:
    if raw_policy is None:
        return None
    if not isinstance(raw_policy, dict):
        raise ValueError("source_policy must be an object")

    raw_variants = raw_policy.get("semantic_variants", {})
    if not isinstance(raw_variants, dict):
        raise ValueError("source_policy semantic_variants must be an object")
    variants: dict[str, SourceSemanticVariants] = {}
    for source, value in raw_variants.items():
        if not isinstance(value, dict):
            raise ValueError("source_policy semantic variant must be an object")
        variants[str(source)] = SourceSemanticVariants(
            primary=tuple(str(item) for item in value.get("primary", [])),
            related=tuple(str(item) for item in value.get("related", [])),
        )

    raw_market_policies = raw_policy.get("market_policies", {})
    if not isinstance(raw_market_policies, dict):
        raise ValueError("source_policy market_policies must be an object")
    market_policies: dict[str, MarketSourcePolicy] = {}
    for market, value in raw_market_policies.items():
        if not isinstance(value, dict):
            raise ValueError("source_policy market policy must be an object")
        market_policies[str(market)] = MarketSourcePolicy(
            primary_route=str(value.get("primary_route", "")),
            cross_check_routes=tuple(
                str(item) for item in value.get("cross_check_routes", [])
            ),
            on_conflict=str(value.get("on_conflict", "preserve_conflict")),
            single_source_requires_pdf=bool(
                value.get("single_source_requires_pdf", False)
            ),
        )

    return SourcePolicy(
        semantic_concept=str(raw_policy.get("semantic_concept", "")),
        semantic_variants=variants,
        market_policies=market_policies,
        verification_requirement=str(raw_policy.get("verification_requirement", "none")),
    )


def _require_referenced_metadata(field_id: str, mapping: dict[str, Any]) -> None:
    for key in REFERENCED_REQUIRED_METADATA:
        if key not in mapping:
            raise ValueError(
                f"{field_id}: {key} is required in referenced source mapping catalog"
            )


def _validate_referenced_metadata_values(mapping: dict[str, Any]) -> None:
    _validate_literal("domain", str(mapping["domain"]), FieldDomain)


def _default_domain(statement_type: str) -> str:
    if statement_type in {"income_statement", "balance_sheet", "cash_flow"}:
        return statement_type
    if statement_type in {"notes", "mda"}:
        return "notes_and_mda"
    return "income_statement"


def _validate_literal(name: str, value: str, literal: Any) -> None:
    if value not in get_args(literal):
        raise ValueError(f"{name} has unsupported value: {value}")
