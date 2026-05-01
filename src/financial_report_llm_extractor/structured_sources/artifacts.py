"""Raw source artifact and source inventory persistence."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from financial_report_llm_extractor.structured_sources.models import (
    SourceArtifact,
    SourceEvidence,
    SourceInventoryRecord,
    SourceName,
)


def build_artifact_id(
    *,
    source: SourceName,
    market: str,
    ticker: str,
    artifact_type: str,
) -> str:
    parts = (source, market, ticker, artifact_type)
    return "_".join(_slug(part) for part in parts if part)


class SourceArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write_json(
        self,
        *,
        source: SourceName,
        artifact_id: str,
        payload: Any,
    ) -> SourceArtifact:
        relative_path = Path(source) / f"{artifact_id}.json"
        full_path = self.root / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifact = SourceArtifact(
            source=source,
            artifact_id=artifact_id,
            path=relative_path.as_posix(),
            content_type="application/json",
        )
        artifact.validate()
        return artifact


def write_source_inventory(
    path: Path,
    records: Iterable[SourceInventoryRecord],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(_record_to_jsonable(record), ensure_ascii=False, sort_keys=True)
        for record in records
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def read_source_inventory(path: Path) -> tuple[SourceInventoryRecord, ...]:
    records: list[SourceInventoryRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(_record_from_jsonable(json.loads(line)))
    return tuple(records)


def _record_to_jsonable(record: SourceInventoryRecord) -> dict[str, Any]:
    record.validate()
    payload = asdict(record)
    if record.parsed_numeric_value is not None:
        payload["parsed_numeric_value"] = str(record.parsed_numeric_value)
    return payload


def _record_from_jsonable(payload: dict[str, Any]) -> SourceInventoryRecord:
    evidence = tuple(SourceEvidence(**item) for item in payload.pop("source_evidence", []))
    parsed_numeric_value = payload.get("parsed_numeric_value")
    if parsed_numeric_value is not None:
        payload["parsed_numeric_value"] = Decimal(str(parsed_numeric_value))
    record = SourceInventoryRecord(
        **payload,
        source_evidence=evidence,
    )
    record.validate()
    return record


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", value.strip().lower())
    return slug.strip("_")
