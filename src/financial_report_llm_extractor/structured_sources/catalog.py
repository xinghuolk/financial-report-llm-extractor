"""Turtle source mapping catalog loading."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from financial_report_llm_extractor.structured_sources.models import SourceValueType


Requirement = Literal["required", "optional", "not_applicable"]


@dataclass(frozen=True)
class SourceMappingEntry:
    field_id: str
    priority: str
    value_type: SourceValueType
    statement_type: str
    currency_requirement: Requirement
    unit_requirement: Requirement
    source_aliases: dict[str, tuple[str, ...]]
    period_expectation: str = "annual"
    scope_expectation: str = "unknown"
    pdf_aliases: tuple[str, ...] = field(default_factory=tuple)
    derivation: str | None = None
    fallback_policy: str = "pdf_allowed"

    def validate(self) -> None:
        if not self.field_id:
            raise ValueError("field_id is required")
        if not self.priority:
            raise ValueError("priority is required")
        if not self.statement_type:
            raise ValueError("statement_type is required")
        if not self.source_aliases:
            raise ValueError("source_aliases is required")


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
    selected_priorities = set(priorities)
    priority_by_field: dict[str, str] = {}
    for group in raw.get("priorities", []):
        priority = str(group.get("priority", ""))
        if priority not in selected_priorities:
            continue
        for field_id in group.get("fields", []):
            priority_by_field.setdefault(str(field_id), priority)

    mappings: dict[str, Any] = raw.get("source_mappings", {})
    entries: dict[str, SourceMappingEntry] = {}
    for field_id, priority in priority_by_field.items():
        mapping = mappings.get(field_id, {})
        aliases = {
            str(source): tuple(str(alias) for alias in values)
            for source, values in mapping.get("source_aliases", {}).items()
        }
        entry = SourceMappingEntry(
            field_id=field_id,
            priority=priority,
            value_type=mapping.get("value_type", "money"),
            statement_type=mapping.get("statement_type", "unknown"),
            currency_requirement=mapping.get("currency_requirement", "required"),
            unit_requirement=mapping.get("unit_requirement", "required"),
            source_aliases=aliases,
            period_expectation=mapping.get("period_expectation", "annual"),
            scope_expectation=mapping.get("scope_expectation", "unknown"),
            pdf_aliases=tuple(str(alias) for alias in mapping.get("pdf_aliases", [])),
            derivation=mapping.get("derivation"),
            fallback_policy=mapping.get("fallback_policy", "pdf_allowed"),
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

