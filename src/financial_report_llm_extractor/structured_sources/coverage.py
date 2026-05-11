"""Source-first Turtle coverage evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from financial_report_llm_extractor.structured_sources.catalog import SourceMappingEntry
from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
    SourceName,
)


def evaluate_source_coverage(
    entries: Mapping[str, SourceMappingEntry],
    records: Sequence[SourceInventoryRecord],
    *,
    required_sources: tuple[SourceName, ...],
) -> dict[str, Any]:
    fields = list(entries.values())
    by_source = {
        source: _coverage_for_source(fields, records, source=source)
        for source in required_sources
    }
    combined_missing: list[str] = []
    combined_blocked: list[str] = []
    combined_blocker_reasons: dict[str, list[str]] = {}
    combined_covered = 0
    for entry in fields:
        status = _entry_status(entry, records)
        if status["status"] == "covered":
            combined_covered += 1
        elif status["status"] == "blocked":
            combined_blocked.append(entry.field_id)
            combined_blocker_reasons[entry.field_id] = status["reasons"]
        else:
            combined_missing.append(entry.field_id)

    total = len(fields)
    return {
        "total_fields": total,
        "by_source": by_source,
        "combined": {
            "covered_fields": combined_covered,
            "missing_fields": combined_missing,
            "blocked_fields": combined_blocked,
            "blocker_reasons": combined_blocker_reasons,
            "coverage_ratio": combined_covered / total if total else 0.0,
        },
    }


def summarize_source_coverage_by_metadata(
    entries: Mapping[str, SourceMappingEntry],
) -> dict[str, object]:
    by_domain: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_source_mode: dict[str, int] = {}
    by_primary_route: dict[str, int] = {}
    for entry in entries.values():
        by_domain[entry.domain] = by_domain.get(entry.domain, 0) + 1
        by_priority[entry.priority] = by_priority.get(entry.priority, 0) + 1
        by_source_mode[entry.source_mode] = (
            by_source_mode.get(entry.source_mode, 0) + 1
        )
        by_primary_route[entry.primary_route] = (
            by_primary_route.get(entry.primary_route, 0) + 1
        )
    return {
        "total_fields": len(entries),
        "by_domain": dict(sorted(by_domain.items())),
        "by_priority": dict(sorted(by_priority.items())),
        "by_source_mode": dict(sorted(by_source_mode.items())),
        "by_primary_route": dict(sorted(by_primary_route.items())),
    }


def _coverage_for_source(
    entries: Sequence[SourceMappingEntry],
    records: Sequence[SourceInventoryRecord],
    *,
    source: SourceName,
) -> dict[str, Any]:
    covered = 0
    missing: list[str] = []
    blocked: list[str] = []
    blocker_reasons: dict[str, list[str]] = {}
    source_records = [record for record in records if record.source == source]
    for entry in entries:
        status = _entry_status(entry, source_records)
        if status["status"] == "covered":
            covered += 1
        elif status["status"] == "blocked":
            blocked.append(entry.field_id)
            blocker_reasons[entry.field_id] = status["reasons"]
        else:
            missing.append(entry.field_id)
    total = len(entries)
    return {
        "covered_fields": covered,
        "missing_fields": missing,
        "blocked_fields": blocked,
        "blocker_reasons": blocker_reasons,
        "coverage_ratio": covered / total if total else 0.0,
    }


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


def _entry_status(
    entry: SourceMappingEntry,
    records: Sequence[SourceInventoryRecord],
) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    saw_matching_record = False
    for record in records:
        if not _record_matches_entry(record, entry):
            continue
        saw_matching_record = True
        try:
            record.validate()
        except ValueError as exc:
            blocked_reasons.append(str(exc))
            continue
        return {"status": "covered", "reasons": []}
    if blocked_reasons:
        return {"status": "blocked", "reasons": sorted(set(blocked_reasons))}
    if saw_matching_record:
        return {"status": "blocked", "reasons": ["matching record is not valid"]}
    return {"status": "missing", "reasons": []}
