"""Cross-source reconciliation for mapped Turtle fields."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from financial_report_llm_extractor.structured_sources.mapping import (
    TurtleMappingCandidate,
    TurtleMappingResult,
)
from financial_report_llm_extractor.structured_sources.models import SourceName


ReconciliationStatus = Literal[
    "single_source",
    "equivalent",
    "close",
    "conflict",
    "blocked",
]


@dataclass(frozen=True)
class ReconciliationItem:
    field_id: str
    status: ReconciliationStatus
    sources: tuple[SourceName, ...]
    reason: str
    max_difference: Decimal | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        if self.max_difference is not None:
            payload["max_difference"] = str(self.max_difference)
        return payload


@dataclass(frozen=True)
class ReconciliationReport:
    catalog_id: str
    catalog_version: str
    items: dict[str, ReconciliationItem]

    @property
    def conflict_fields(self) -> tuple[str, ...]:
        return tuple(
            field_id
            for field_id in sorted(self.items)
            if self.items[field_id].status == "conflict"
        )

    def to_dict(self) -> dict[str, object]:
        counts = Counter(item.status for item in self.items.values())
        return {
            "catalog_id": self.catalog_id,
            "catalog_version": self.catalog_version,
            "status_counts": dict(sorted(counts.items())),
            "conflict_fields": list(self.conflict_fields),
            "items": {
                field_id: self.items[field_id].to_dict()
                for field_id in sorted(self.items)
            },
        }


def reconcile_mapped_fields(
    result: TurtleMappingResult,
    *,
    tolerance: Decimal = Decimal("0"),
) -> ReconciliationReport:
    items = {
        field_id: _reconcile_field(field_id, field.candidates, tolerance=tolerance)
        for field_id, field in result.fields.items()
    }
    return ReconciliationReport(
        catalog_id=result.catalog_id,
        catalog_version=result.catalog_version,
        items=items,
    )


def write_reconciliation_report(
    report: ReconciliationReport,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return output_path


def _reconcile_field(
    field_id: str,
    candidates: tuple[TurtleMappingCandidate, ...],
    *,
    tolerance: Decimal,
) -> ReconciliationItem:
    sources = tuple(candidate.source for candidate in candidates)
    if not candidates:
        return ReconciliationItem(
            field_id=field_id,
            status="blocked",
            sources=sources,
            reason="field has no source candidates",
        )
    if len(candidates) == 1:
        return ReconciliationItem(
            field_id=field_id,
            status="single_source",
            sources=sources,
            reason="field has one source candidate",
        )

    metadata_error = _metadata_error(candidates)
    if metadata_error:
        return ReconciliationItem(
            field_id=field_id,
            status="conflict",
            sources=sources,
            reason=metadata_error,
        )

    values = [candidate.normalized_value for candidate in candidates]
    if any(value is None for value in values):
        return ReconciliationItem(
            field_id=field_id,
            status="blocked",
            sources=sources,
            reason="candidate normalized value missing",
        )
    normalized_values = [value for value in values if value is not None]
    max_difference = max(normalized_values) - min(normalized_values)
    if max_difference == 0:
        return ReconciliationItem(
            field_id=field_id,
            status="equivalent",
            sources=sources,
            reason="candidate normalized values are equal",
            max_difference=max_difference,
        )
    if max_difference <= tolerance:
        return ReconciliationItem(
            field_id=field_id,
            status="close",
            sources=sources,
            reason="candidate normalized values are within tolerance",
            max_difference=max_difference,
        )
    return ReconciliationItem(
        field_id=field_id,
        status="conflict",
        sources=sources,
        reason="candidate normalized values differ",
        max_difference=max_difference,
    )


def _metadata_error(candidates: tuple[TurtleMappingCandidate, ...]) -> str | None:
    if len({candidate.period for candidate in candidates}) > 1:
        return "candidate periods differ"
    if len({candidate.currency for candidate in candidates}) > 1:
        return "candidate currencies differ"
    if len({candidate.canonical_unit for candidate in candidates}) > 1:
        return "candidate canonical units differ"
    known_scopes = {
        candidate.scope for candidate in candidates if candidate.scope != "unknown"
    }
    if len(known_scopes) > 1:
        return "candidate scopes differ"
    return None
