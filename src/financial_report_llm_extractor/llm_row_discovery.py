"""LLM-assisted row discovery from statement-scoped evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from financial_report_llm_extractor.llm_transport import (
    HttpTransport,
    LlmTransportConfig,
    create_llm_client,
    response_json_text,
)


PROMPT_VERSION = "row-discovery-v1"
SCHEMA_VERSION = "row-inventory-v1"


@dataclass(frozen=True)
class LlmRowDiscoveryResult:
    output_path: Path
    row_count: int
    prompt_count: int
    raw_response_count: int


def build_row_discovery_prompt_payload(
    statement: dict[str, Any],
    chunk: dict[str, Any],
) -> dict[str, Any]:
    return {
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "task": "discover_statement_rows",
        "statement": {
            "statement_id": statement.get("statement_id"),
            "statement_kind": statement.get("statement_kind"),
            "title": statement.get("title"),
            "scope": statement.get("scope"),
            "period_columns": statement.get("period_columns", []),
            "unit_context": statement.get("unit_context"),
            "chunk_id": statement.get("chunk_id"),
            "page_start": chunk.get("page_start"),
            "page_end": chunk.get("page_end"),
            "evidence_blocks": _statement_evidence_blocks(statement, chunk),
        },
        "response_schema": {
            "type": "object",
            "required": ["rows"],
            "properties": {
                "rows": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["row_label", "values", "evidence"],
                    },
                }
            },
        },
    }


def _statement_evidence_blocks(
    statement: dict[str, Any],
    chunk: dict[str, Any],
) -> list[dict[str, Any]]:
    requested_block_ids = [
        str(block_id)
        for block_id in statement.get("evidence_blocks", [])
        if str(block_id)
    ]
    block_texts = chunk.get("block_texts", {})
    if not isinstance(block_texts, dict):
        return []
    page = chunk.get("page_start")
    return [
        {
            "block_id": block_id,
            "page": page,
            "text": str(block_texts[block_id]),
        }
        for block_id in requested_block_ids
        if block_id in block_texts
    ]


def write_llm_row_inventory(
    chunks_path: Path,
    statement_map_path: Path,
    *,
    config_path: Path,
    output_path: Path,
    prompt_dir: Path,
    raw_response_dir: Path,
    parsed_response_dir: Path,
    transport: HttpTransport | None = None,
) -> LlmRowDiscoveryResult:
    config = LlmTransportConfig.from_json(config_path)
    client = create_llm_client(config, transport=transport)
    chunks = _read_chunks_by_id(chunks_path)
    statements = _read_statements(statement_map_path)
    rows: list[dict[str, Any]] = []

    prompt_dir.mkdir(parents=True, exist_ok=True)
    raw_response_dir.mkdir(parents=True, exist_ok=True)
    parsed_response_dir.mkdir(parents=True, exist_ok=True)

    for index, statement in enumerate(statements, start=1):
        chunk = chunks.get(str(statement.get("chunk_id")))
        if chunk is None:
            continue
        prompt_payload = build_row_discovery_prompt_payload(statement, chunk)
        _write_json(prompt_dir / f"prompt_{index:04d}.json", prompt_payload)
        raw_response = client.complete_json(
            system_prompt=(
                "Return strict JSON with a rows array. Use only the "
                "provided statement evidence blocks."
            ),
            user_payload=prompt_payload,
        )
        _write_json(raw_response_dir / f"raw_response_{index:04d}.json", raw_response)
        try:
            parsed = _parse_row_response(raw_response)
        except ValueError as error:
            _write_json(
                parsed_response_dir / f"error_{index:04d}.json",
                {"status": "error", "error": str(error)},
            )
            raise
        _write_json(parsed_response_dir / f"parsed_response_{index:04d}.json", parsed)
        rows.extend(_rows_with_statement_context(statement, parsed.get("rows", [])))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output_path, {"rows": rows})
    return LlmRowDiscoveryResult(
        output_path=output_path,
        row_count=len(rows),
        prompt_count=len(statements),
        raw_response_count=len(statements),
    )


def _read_chunks_by_id(chunks_path: Path) -> dict[str, dict[str, Any]]:
    chunks: dict[str, dict[str, Any]] = {}
    for line in chunks_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("record_type") == "chunk":
            chunks[str(record["chunk_id"])] = record
    return chunks


def _read_statements(statement_map_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(statement_map_path.read_text(encoding="utf-8"))
    return [
        statement
        for statement in payload.get("statements", [])
        if isinstance(statement, dict)
    ]


def _parse_row_response(raw_response: dict[str, object]) -> dict[str, Any]:
    try:
        parsed = json.loads(_response_json_text(raw_response))
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("malformed LLM row discovery JSON") from error
    if not isinstance(parsed, dict) or not isinstance(parsed.get("rows"), list):
        raise ValueError("malformed LLM row discovery JSON")
    return parsed


def _response_json_text(raw_response: dict[str, object]) -> str:
    return response_json_text(raw_response)


def _rows_with_statement_context(
    statement: dict[str, Any],
    rows: Any,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, dict):
            continue
        enriched = dict(row)
        enriched.setdefault("statement_id", statement.get("statement_id"))
        enriched.setdefault("statement_kind", statement.get("statement_kind"))
        result.append(enriched)
    return result


def _write_json(path: Path, payload: dict[str, Any] | dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
