"""Provider field inventory summary artifacts."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
)


def build_provider_field_inventory_summary(
    records: Iterable[SourceInventoryRecord],
    *,
    sample_set: str,
    source_artifact_count: int | None = None,
) -> dict[str, Any]:
    record_tuple = tuple(records)
    for record in record_tuple:
        record.validate()

    target_groups: dict[
        tuple[str, str, str, str], list[SourceInventoryRecord]
    ] = defaultdict(list)
    status_counts = Counter(record.source_status for record in record_tuple)
    for record in record_tuple:
        target_groups[
            (record.source, record.market, record.ticker, record.statement_type)
        ].append(record)

    summary: dict[str, Any] = {
        "sample_set": sample_set,
        "record_count": len(record_tuple),
        "status_counts": dict(sorted(status_counts.items())),
        "targets": [
            _target_summary(target_key, tuple(target_records))
            for target_key, target_records in sorted(target_groups.items())
        ],
    }
    if source_artifact_count is not None:
        summary["source_artifact_count"] = source_artifact_count
    return summary


def write_provider_field_inventory_summary(
    path: Path,
    *,
    records: Iterable[SourceInventoryRecord],
    sample_set: str,
    source_artifact_count: int | None = None,
) -> dict[str, Any]:
    summary = build_provider_field_inventory_summary(
        records,
        sample_set=sample_set,
        source_artifact_count=source_artifact_count,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def _target_summary(
    target_key: tuple[str, str, str, str],
    records: tuple[SourceInventoryRecord, ...],
) -> dict[str, Any]:
    source, market, ticker, statement_type = target_key
    return {
        "source": source,
        "market": market,
        "ticker": ticker,
        "statement_type": statement_type,
        "record_count": len(records),
        "status_counts": dict(
            sorted(Counter(record.source_status for record in records).items())
        ),
        "raw_field_names": _sorted_present(record.raw_field_name for record in records),
        "raw_field_codes": _sorted_present(record.raw_field_code for record in records),
        "periods": _sorted_present(record.period for record in records),
        "currencies": _sorted_present(record.currency for record in records),
        "units": _sorted_present(record.unit for record in records),
    }


def _sorted_present(values: Iterable[str | None]) -> list[str]:
    return sorted({value for value in values if value})
