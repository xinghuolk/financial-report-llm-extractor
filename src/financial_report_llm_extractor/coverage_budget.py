"""Coverage and prompt-budget metrics for Turtle field retrieval."""

from __future__ import annotations

import json
from pathlib import Path


def load_catalog_field_ids(
    catalog_path: Path,
    *,
    priorities: tuple[str, ...],
    explicit_fields: tuple[str, ...] = (),
) -> tuple[str, ...]:
    if explicit_fields:
        return _dedupe(explicit_fields)

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    wanted = set(priorities)
    fields: list[str] = []
    for group in catalog.get("priorities", []):
        if group.get("priority") not in wanted:
            continue
        fields.extend(str(field_id) for field_id in group.get("fields", []))
    return _dedupe(tuple(fields))


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)
