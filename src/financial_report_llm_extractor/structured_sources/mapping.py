"""Deterministic source-to-Turtle mapping."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

from financial_report_llm_extractor.models import Currency
from financial_report_llm_extractor.money import MoneyNormalizationError, normalize_money
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
    SourceMappingEntry,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
    SourceName,
)


MappedFieldStatus = Literal["present", "missing", "ambiguous", "derived", "blocked"]


@dataclass(frozen=True)
class TurtleMappingCandidate:
    source: SourceName
    raw_field_name: str
    raw_field_code: str | None
    raw_value: str | int | float | None
    value: Decimal | None
    normalized_value: Decimal | None
    currency: Currency
    unit: str | None
    period: str | None
    scope: str
    source_evidence: tuple[SourceEvidence, ...]
    errors: tuple[str, ...] = field(default_factory=tuple)
    canonical_unit: Currency | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        for key in ("value", "normalized_value"):
            if payload[key] is not None:
                payload[key] = str(payload[key])
        return payload


@dataclass(frozen=True)
class MappedTurtleField:
    field_id: str
    status: MappedFieldStatus
    value: Decimal | None = None
    normalized_value: Decimal | None = None
    currency: Currency = "unknown"
    unit: str | None = None
    canonical_unit: Currency | None = None
    period: str | None = None
    scope: str = "unknown"
    candidates: tuple[TurtleMappingCandidate, ...] = field(default_factory=tuple)
    source_evidence: tuple[SourceEvidence, ...] = field(default_factory=tuple)
    derived_from: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)

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
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "source_evidence": [evidence.to_dict() for evidence in self.source_evidence],
            "derived_from": list(self.derived_from),
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class TurtleMappingResult:
    catalog_id: str
    catalog_version: str
    fields: dict[str, MappedTurtleField]

    def to_dict(self) -> dict[str, object]:
        return {
            "catalog_id": self.catalog_id,
            "catalog_version": self.catalog_version,
            "fields": {
                field_id: self.fields[field_id].to_dict()
                for field_id in sorted(self.fields)
            },
        }


def map_source_inventory(
    catalog: SourceMappingCatalog,
    records: list[SourceInventoryRecord] | tuple[SourceInventoryRecord, ...],
) -> TurtleMappingResult:
    catalog.validate()
    mapped: dict[str, MappedTurtleField] = {}
    for field_id, entry in catalog.entries.items():
        mapped[field_id] = _map_direct_field(entry, records)

    for field_id, entry in catalog.entries.items():
        if not entry.derivation or mapped[field_id].status != "missing":
            continue
        mapped[field_id] = _derive_field(entry, mapped)

    return TurtleMappingResult(
        catalog_id=catalog.catalog_id,
        catalog_version=catalog.version,
        fields=mapped,
    )


def write_turtle_mapping_artifacts(
    result: TurtleMappingResult,
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    mapping_path = output_dir / "turtle_mapping.json"
    summary_path = output_dir / "source_coverage_summary.json"
    markdown_path = output_dir / "source_coverage_summary.md"

    mapping_payload = result.to_dict()
    summary_payload = build_source_mapping_summary(result)
    mapping_path.write_text(
        json.dumps(mapping_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_summary_markdown(summary_payload), encoding="utf-8")

    return {
        "mapping": mapping_path,
        "coverage_json": summary_path,
        "coverage_markdown": markdown_path,
    }


def build_source_mapping_summary(result: TurtleMappingResult) -> dict[str, object]:
    counts = Counter(field.status for field in result.fields.values())
    blocker_fields = {
        "missing": sorted(
            field_id
            for field_id, field in result.fields.items()
            if field.status == "missing"
        ),
        "ambiguous": sorted(
            field_id
            for field_id, field in result.fields.items()
            if field.status == "ambiguous"
        ),
    }
    return {
        "catalog_id": result.catalog_id,
        "catalog_version": result.catalog_version,
        "total_fields": len(result.fields),
        "status_counts": dict(sorted(counts.items())),
        "blocker_fields": blocker_fields,
    }


def _map_direct_field(
    entry: SourceMappingEntry,
    records: list[SourceInventoryRecord] | tuple[SourceInventoryRecord, ...],
) -> MappedTurtleField:
    matched_candidates = tuple(
        _candidate_from_record(record)
        for record in records
        if _record_matches_entry(record, entry)
    )
    if not matched_candidates:
        return MappedTurtleField(
            field_id=entry.field_id,
            status="missing",
            errors=("no source candidates matched catalog aliases",),
        )
    candidates = tuple(
        candidate for candidate in matched_candidates if not candidate.errors
    )
    if not candidates:
        return MappedTurtleField(
            field_id=entry.field_id,
            status="blocked",
            candidates=matched_candidates,
            errors=("matched source candidates failed validation or normalization",),
        )
    candidates = _apply_alias_precedence(entry, candidates)
    if len(candidates) > 1:
        return MappedTurtleField(
            field_id=entry.field_id,
            status="ambiguous",
            candidates=candidates,
            errors=("multiple source candidates matched catalog aliases",),
        )
    candidate = candidates[0]
    return MappedTurtleField(
        field_id=entry.field_id,
        status="present",
        value=candidate.value,
        normalized_value=candidate.normalized_value,
        currency=candidate.currency,
        unit=candidate.unit,
        canonical_unit=candidate.canonical_unit,
        period=candidate.period,
        scope=candidate.scope,
        candidates=candidates,
        source_evidence=candidate.source_evidence,
    )


def _derive_field(
    entry: SourceMappingEntry,
    mapped: dict[str, MappedTurtleField],
) -> MappedTurtleField:
    assert entry.derivation is not None
    parts = entry.derivation.split()
    if len(parts) != 3 or parts[1] != "-":
        return MappedTurtleField(
            field_id=entry.field_id,
            status="blocked",
            errors=(f"unsupported derivation: {entry.derivation}",),
        )

    left = mapped.get(parts[0])
    right = mapped.get(parts[2])
    if left is None or right is None:
        return MappedTurtleField(
            field_id=entry.field_id,
            status="blocked",
            errors=(f"derivation input missing from catalog: {entry.derivation}",),
        )
    if left.status not in {"present", "derived"} or right.status not in {
        "present",
        "derived",
    }:
        return MappedTurtleField(
            field_id=entry.field_id,
            status="blocked",
            errors=(f"derivation input not present: {entry.derivation}",),
        )
    compatibility_error = _compatibility_error(left, right)
    if compatibility_error:
        return MappedTurtleField(
            field_id=entry.field_id,
            status="blocked",
            errors=(compatibility_error,),
        )
    if left.value is None or right.value is None:
        return MappedTurtleField(
            field_id=entry.field_id,
            status="blocked",
            errors=("derivation input value missing",),
        )

    value = left.value - right.value
    normalized_value = (
        left.normalized_value - right.normalized_value
        if left.normalized_value is not None and right.normalized_value is not None
        else None
    )
    return MappedTurtleField(
        field_id=entry.field_id,
        status="derived",
        value=value,
        normalized_value=normalized_value,
        currency=left.currency,
        unit=left.unit,
        canonical_unit=left.canonical_unit,
        period=left.period,
        scope=left.scope,
        source_evidence=left.source_evidence + right.source_evidence,
        derived_from=(left.field_id, right.field_id),
    )


def _record_matches_entry(
    record: SourceInventoryRecord,
    entry: SourceMappingEntry,
) -> bool:
    if record.source_status != "present":
        return False
    aliases = entry.source_aliases.get(record.source, ())
    return record.raw_field_name in aliases or (
        record.raw_field_code is not None and record.raw_field_code in aliases
    )


def _candidate_from_record(record: SourceInventoryRecord) -> TurtleMappingCandidate:
    errors: list[str] = []
    value: Decimal | None = None
    normalized_value: Decimal | None = None
    canonical_unit: Currency | None = None
    try:
        record.validate()
        money = normalize_money(
            str(record.raw_value),
            unit_context=f"{record.currency} {record.unit}",
        )
        value = money.value
        normalized_value = money.normalized_value
        canonical_unit = money.normalized_unit
    except (ValueError, MoneyNormalizationError) as exc:
        errors.append(str(exc))

    return TurtleMappingCandidate(
        source=record.source,
        raw_field_name=record.raw_field_name,
        raw_field_code=record.raw_field_code,
        raw_value=record.raw_value,
        value=value,
        normalized_value=normalized_value,
        currency=record.currency,
        unit=record.unit,
        period=record.period,
        scope=record.scope,
        source_evidence=record.source_evidence,
        canonical_unit=canonical_unit,
        errors=tuple(errors),
    )


def _apply_alias_precedence(
    entry: SourceMappingEntry,
    candidates: tuple[TurtleMappingCandidate, ...],
) -> tuple[TurtleMappingCandidate, ...]:
    best_rank_by_source: dict[SourceName, int] = {}
    for candidate in candidates:
        rank = _alias_rank(entry, candidate)
        best_rank_by_source[candidate.source] = min(
            rank,
            best_rank_by_source.get(candidate.source, rank),
        )
    return tuple(
        candidate
        for candidate in candidates
        if _alias_rank(entry, candidate) == best_rank_by_source[candidate.source]
    )


def _alias_rank(entry: SourceMappingEntry, candidate: TurtleMappingCandidate) -> int:
    aliases = entry.source_aliases.get(candidate.source, ())
    for index, alias in enumerate(aliases):
        if candidate.raw_field_name == alias or candidate.raw_field_code == alias:
            return index
    return len(aliases)


def _compatibility_error(
    left: MappedTurtleField,
    right: MappedTurtleField,
) -> str | None:
    if left.currency != right.currency:
        return "derivation inputs use different currencies"
    if left.period != right.period:
        return "derivation inputs use different periods"
    if left.scope != right.scope:
        return "derivation inputs use different scopes"
    if left.canonical_unit != right.canonical_unit:
        return "derivation inputs use different canonical units"
    return None


def _summary_markdown(summary: dict[str, object]) -> str:
    status_counts = summary["status_counts"]
    assert isinstance(status_counts, dict)
    blocker_fields = summary["blocker_fields"]
    assert isinstance(blocker_fields, dict)

    lines = [
        "# Source Coverage Summary",
        "",
        f"- total_fields: {summary['total_fields']}",
        "",
        "| status | count |",
        "| --- | ---: |",
    ]
    for status, count in status_counts.items():
        lines.append(f"| {status} | {count} |")
    lines.extend(["", "## Blockers", ""])
    for status in ("missing", "ambiguous"):
        fields = blocker_fields.get(status, [])
        if fields:
            lines.append(f"- {status}: {', '.join(fields)}")
        else:
            lines.append(f"- {status}: none")
    return "\n".join(lines) + "\n"
