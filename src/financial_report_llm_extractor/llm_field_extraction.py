"""LLM-assisted field extraction from PDF chunks.

Used for fields where source-first providers don't have the value or
ambiguity remains after deterministic resolution. The LLM extracts a single
field's value from selected PDF chunks. Output is evidence-grounded:
must cite page and statement_line, or report not_found.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal, Protocol


PROMPT_VERSION = "field-extraction-v1"
SCHEMA_VERSION = "field-extraction-result-v1"


FieldExtractionStatus = Literal["present", "not_found", "extraction_failed"]


@dataclass(frozen=True)
class FieldExtractionRequest:
    field_id: str
    field_description: str
    statement_type: str
    value_type: str
    chunks: tuple[dict[str, object], ...]
    expected_currency: str | None = None
    expected_unit: str | None = None


@dataclass(frozen=True)
class FieldExtractionResult:
    field_id: str
    status: FieldExtractionStatus
    value: str | None = None
    parsed_numeric_value: Decimal | None = None
    currency: str | None = None
    unit: str | None = None
    period: str | None = None
    page: int | None = None
    statement_line: str | None = None
    confidence: float | None = None
    reasoning: str | None = None
    raw_response: dict[str, object] = field(default_factory=dict)
    errors: tuple[str, ...] = ()


def build_field_extraction_prompt(
    request: FieldExtractionRequest,
) -> dict[str, object]:
    """Build a deterministic JSON-serializable LLM prompt payload."""
    return {
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "task": "extract_field_value",
        "field": {
            "field_id": request.field_id,
            "description": request.field_description,
            "statement_type": request.statement_type,
            "value_type": request.value_type,
            "expected_currency": request.expected_currency,
            "expected_unit": request.expected_unit,
        },
        "chunks": [
            {
                "chunk_id": str(chunk.get("chunk_id", "")),
                "page_start": chunk.get("page_start", chunk.get("page")),
                "page_end": chunk.get("page_end", chunk.get("page")),
                "text": str(chunk.get("text", "")),
            }
            for chunk in request.chunks
        ],
        "response_schema": {
            "type": "object",
            "required": ["field_id", "found"],
            "properties": {
                "field_id": {"type": "string"},
                "found": {"type": "boolean"},
                "value": {"type": ["string", "null"]},
                "currency": {"type": ["string", "null"]},
                "unit": {"type": ["string", "null"]},
                "period": {"type": ["string", "null"]},
                "page": {"type": ["integer", "null"]},
                "statement_line": {"type": ["string", "null"]},
                "confidence": {"type": ["number", "null"]},
                "reasoning": {"type": ["string", "null"]},
            },
        },
    }


SYSTEM_PROMPT = (
    "You extract financial report field values from PDF chunks. "
    "Return strictly valid JSON matching the requested schema. "
    "If the field value is not present in the provided chunks, return found=false. "
    "Never fabricate values. Cite the page and exact statement line text from the chunks."
)


class JsonClient(Protocol):
    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        ...


def run_field_extraction(
    request: FieldExtractionRequest,
    client: JsonClient,
    raw_response_dir: Path | None = None,
) -> FieldExtractionResult:
    """Call LLM, parse response, optionally archive raw payload."""
    payload = build_field_extraction_prompt(request)
    raw = client.complete_json(
        system_prompt=SYSTEM_PROMPT,
        user_payload=payload,
    )

    if raw_response_dir is not None:
        raw_response_dir.mkdir(parents=True, exist_ok=True)
        archive_path = raw_response_dir / f"{request.field_id}_{PROMPT_VERSION}.json"
        archive_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return _parse_response(request, raw)


def _parse_response(
    request: FieldExtractionRequest,
    raw: dict[str, object],
) -> FieldExtractionResult:
    errors: list[str] = []

    found = raw.get("found")
    if not isinstance(found, bool):
        errors.append("response missing or invalid 'found' field")
        return FieldExtractionResult(
            field_id=request.field_id,
            status="extraction_failed",
            raw_response=raw,
            errors=tuple(errors),
        )

    if not found:
        return FieldExtractionResult(
            field_id=request.field_id,
            status="not_found",
            reasoning=_str_or_none(raw.get("reasoning")),
            raw_response=raw,
        )

    value_raw = _str_or_none(raw.get("value"))
    parsed_numeric_value: Decimal | None = None
    if value_raw is not None:
        try:
            parsed_numeric_value = Decimal(value_raw.replace(",", "").strip())
        except (InvalidOperation, ValueError):
            errors.append(f"unparseable numeric value: {value_raw!r}")

    return FieldExtractionResult(
        field_id=request.field_id,
        status="present" if not errors else "extraction_failed",
        value=value_raw,
        parsed_numeric_value=parsed_numeric_value,
        currency=_str_or_none(raw.get("currency")),
        unit=_str_or_none(raw.get("unit")),
        period=_str_or_none(raw.get("period")),
        page=_int_or_none(raw.get("page")),
        statement_line=_str_or_none(raw.get("statement_line")),
        confidence=_float_or_none(raw.get("confidence")),
        reasoning=_str_or_none(raw.get("reasoning")),
        raw_response=raw,
        errors=tuple(errors),
    )


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):  # bool is subclass of int; reject
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
