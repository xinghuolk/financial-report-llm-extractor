"""Statement map, row inventory, and selected-field mapping artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StatementMapResult:
    output_path: Path
    statement_count: int


@dataclass(frozen=True)
class RowInventoryResult:
    output_path: Path
    row_count: int


@dataclass(frozen=True)
class CatalogMappingResult:
    output_path: Path
    mapping_count: int


FIELD_MAPPING_HINTS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "revenue": (("revenue", "group revenue", "turnover"), ("income_statement",)),
    "net_profit": (
        (
            "profit attributable to shareholders",
            "profit attributable to owners",
            "net profit",
            "profit for the year",
        ),
        ("income_statement",),
    ),
    "total_assets": (("total assets",), ("balance_sheet",)),
    "total_liabilities": (("total liabilities",), ("balance_sheet",)),
    "operating_cash_flow": (
        (
            "net cash from operating activities",
            "net cash generated from operating activities",
        ),
        ("cash_flow",),
    ),
}


def write_statement_map(
    chunks_path: Path,
    document_map_path: Path,
    *,
    output_path: Path | None = None,
) -> StatementMapResult:
    chunks = [
        record
        for record in _read_jsonl(chunks_path)
        if record.get("record_type") == "chunk"
    ]
    document_map = json.loads(document_map_path.read_text(encoding="utf-8"))
    audited_range = _audited_financial_statement_range(document_map)
    output = output_path or chunks_path.parent / "statement_map.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    statement_chunks = [
        chunk
        for chunk in chunks
        if chunk.get("kind") == "statement_table"
        and chunk.get("statement_kind") in {"income_statement", "balance_sheet", "cash_flow"}
        and _chunk_in_range(chunk, audited_range)
    ]
    statements = [
        _statement_payload(index, chunk)
        for index, chunk in enumerate(statement_chunks, start=1)
    ]
    output.write_text(
        json.dumps({"statements": statements}, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return StatementMapResult(output_path=output, statement_count=len(statements))


def write_row_inventory(
    chunks_path: Path,
    statement_map_path: Path,
    *,
    output_path: Path | None = None,
) -> RowInventoryResult:
    chunks = {
        str(record["chunk_id"]): record
        for record in _read_jsonl(chunks_path)
        if record.get("record_type") == "chunk"
    }
    statement_map = json.loads(statement_map_path.read_text(encoding="utf-8"))
    output = output_path or statement_map_path.parent / "row_inventory.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for statement in statement_map.get("statements", []):
        chunk = chunks.get(str(statement.get("chunk_id")))
        if chunk is None:
            continue
        rows.extend(_rows_for_statement(statement, chunk))

    output.write_text(
        json.dumps({"rows": rows}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return RowInventoryResult(output_path=output, row_count=len(rows))


def write_catalog_mapping(
    row_inventory_path: Path,
    *,
    selected_fields: tuple[str, ...],
    output_path: Path | None = None,
) -> CatalogMappingResult:
    row_inventory = json.loads(row_inventory_path.read_text(encoding="utf-8"))
    rows = [
        row for row in row_inventory.get("rows", []) if isinstance(row, dict)
    ]
    output = output_path or row_inventory_path.parent / "catalog_mapping.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    mappings = [_mapping_for_field(field_id, rows) for field_id in selected_fields]
    output.write_text(
        json.dumps(
            {"selected_fields": list(selected_fields), "mappings": mappings},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return CatalogMappingResult(output_path=output, mapping_count=len(mappings))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _audited_financial_statement_range(
    document_map: dict[str, Any],
) -> tuple[int, int] | None:
    for section in document_map.get("sections", []):
        if section.get("kind") == "audited_financial_statements":
            return int(section["page_start"]), int(section["page_end"])
    return None


def _chunk_in_range(
    chunk: dict[str, Any],
    page_range: tuple[int, int] | None,
) -> bool:
    if page_range is None:
        return True
    start, end = page_range
    return int(chunk.get("page_start", 0)) >= start and int(chunk.get("page_end", 0)) <= end


def _statement_payload(index: int, chunk: dict[str, Any]) -> dict[str, Any]:
    statement_kind = str(chunk["statement_kind"])
    return {
        "statement_id": f"stmt_{index:04d}_{statement_kind}",
        "statement_kind": statement_kind,
        "scope": _detect_scope(str(chunk.get("text", ""))),
        "page_start": chunk.get("page_start"),
        "page_end": chunk.get("page_end"),
        "title": _first_line(str(chunk.get("text", ""))),
        "unit_context": _detect_unit_context(str(chunk.get("text", ""))),
        "period_columns": _detect_period_columns(str(chunk.get("text", ""))),
        "chunk_id": chunk.get("chunk_id"),
        "evidence_blocks": list(chunk.get("block_ids", [])),
    }


def _detect_scope(text: str) -> str:
    normalized = text.lower()
    if "consolidated" in normalized or "合并" in text:
        return "consolidated"
    if "company" in normalized or "parent" in normalized:
        return "parent"
    return "unknown"


def _detect_unit_context(text: str) -> str | None:
    patterns = (
        r"HK\$ ?[Mm]illion",
        r"US\$ ?[Mm]illion",
        r"RMB'?000",
        r"RMB in thousands",
        r"RMB in millions",
        r"\$ ?[Mm]illion",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def _detect_period_columns(text: str) -> list[str]:
    years = re.findall(r"\b20\d{2}\b", text)
    result: list[str] = []
    for year in years:
        if year not in result:
            result.append(year)
    return result[:2]


def _first_line(text: str) -> str:
    return text.splitlines()[0].strip() if text.splitlines() else ""


def _rows_for_statement(
    statement: dict[str, Any],
    chunk: dict[str, Any],
) -> list[dict[str, Any]]:
    period_columns = [
        str(period) for period in statement.get("period_columns", []) if str(period)
    ]
    unit_context = statement.get("unit_context")
    currency_hint = _currency_hint(str(unit_context or ""))
    block_texts = chunk.get("block_texts", {})
    if not isinstance(block_texts, dict):
        block_texts = {}

    rows: list[dict[str, Any]] = []
    for line in str(chunk.get("text", "")).splitlines():
        parsed = _parse_statement_row(line, period_columns)
        if parsed is None:
            continue
        label, value_raw = parsed
        block_id = _block_id_for_line(block_texts, line)
        rows.append(
            {
                "statement_id": statement.get("statement_id"),
                "statement_kind": statement.get("statement_kind"),
                "row_label": label,
                "values": [
                    {
                        "period": period_columns[0] if period_columns else "current",
                        "value_raw": value_raw,
                    }
                ],
                "unit_context": unit_context,
                "currency_hint": currency_hint,
                "evidence": [
                    {
                        "page": chunk.get("page_start"),
                        "block_id": block_id,
                        "snippet": line.strip(),
                    }
                ],
            }
        )
    return rows


def _parse_statement_row(
    line: str,
    period_columns: list[str],
) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or any(period in stripped for period in period_columns):
        return None
    matches = re.findall(r"\(?-?\d[\d,]*(?:\.\d+)?\)?", stripped)
    if not matches:
        return None
    first_value = matches[0]
    label = stripped[: stripped.find(first_value)].strip(" .:-")
    if not label:
        return None
    return label, first_value


def _block_id_for_line(block_texts: dict[Any, Any], line: str) -> str | None:
    stripped = line.strip()
    for block_id, block_text in block_texts.items():
        if stripped in str(block_text):
            return str(block_id)
    if block_texts:
        return str(next(iter(block_texts)))
    return None


def _currency_hint(unit_context: str) -> str:
    lowered = unit_context.lower()
    if "hk$" in lowered or unit_context == "$ Million":
        return "HKD"
    if "us$" in lowered:
        return "USD"
    if "rmb" in lowered:
        return "CNY"
    return "unknown"


def _mapping_for_field(field_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if field_id not in FIELD_MAPPING_HINTS:
        return {
            "field_id": field_id,
            "status": "missing",
            "source_row_label": None,
            "statement_id": None,
            "mapping_confidence": 0.0,
            "mapping_reason": "selected field is not supported by demo mapping hints",
            "evidence": [],
        }
    hints, statement_hints = FIELD_MAPPING_HINTS[field_id]
    matches = [
        row
        for row in rows
        if _row_matches(row, hints, statement_hints)
    ]
    if not matches:
        return {
            "field_id": field_id,
            "status": "missing",
            "source_row_label": None,
            "statement_id": None,
            "mapping_confidence": 0.0,
            "mapping_reason": "no discovered row matched selected field aliases",
            "evidence": [],
        }
    if len(matches) > 1:
        return {
            "field_id": field_id,
            "status": "ambiguous",
            "source_row_label": None,
            "statement_id": None,
            "mapping_confidence": 0.0,
            "mapping_reason": "multiple discovered rows matched selected field aliases",
            "evidence": [evidence for row in matches for evidence in row.get("evidence", [])],
        }

    row = matches[0]
    return {
        "field_id": field_id,
        "status": "mapped",
        "source_row_label": row.get("row_label"),
        "statement_id": row.get("statement_id"),
        "mapping_confidence": 0.9,
        "mapping_reason": "row label matched selected field aliases and statement hint",
        "evidence": row.get("evidence", []),
    }


def _row_matches(
    row: dict[str, Any],
    aliases: tuple[str, ...],
    statement_hints: tuple[str, ...],
) -> bool:
    label = str(row.get("row_label", "")).lower()
    statement_kind = str(row.get("statement_kind", ""))
    return any(alias in label for alias in aliases) and (
        not statement_hints or statement_kind in statement_hints
    )
