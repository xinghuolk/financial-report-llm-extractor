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
    sign_normalize_fields: frozenset[str] | None = None,
) -> ReconciliationReport:
    sign_normalize_fields = sign_normalize_fields or frozenset()
    items = {
        field_id: _reconcile_field(
            field_id,
            field.candidates,
            tolerance=tolerance,
            sign_normalize=field_id in sign_normalize_fields,
        )
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
    sign_normalize: bool = False,
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

    if any(candidate.canonical_unit is None for candidate in candidates):
        return ReconciliationItem(
            field_id=field_id,
            status="blocked",
            sources=sources,
            reason="candidate canonical unit missing",
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
    if sign_normalize:
        normalized_values = [abs(v) for v in normalized_values]
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


def _normalize_period(period: str | None) -> str | None:
    """Strip trailing time component so AKShare '2024-12-31 00:00:00' and
    Yahoo '2024-12-31' compare equal. Phase EC Tier 1 fix for spurious
    'candidate periods differ' on identical-date candidates."""
    if period is None:
        return None
    return period.split(" ")[0]


def _metadata_error(candidates: tuple[TurtleMappingCandidate, ...]) -> str | None:
    if len({_normalize_period(candidate.period) for candidate in candidates}) > 1:
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
