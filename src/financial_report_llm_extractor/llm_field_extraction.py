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

from financial_report_llm_extractor.llm_transport import response_json_text


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
    absence_means_zero: bool = False


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
    payload: dict[str, object] = {
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
    if request.absence_means_zero:
        payload["zero_inference"] = {
            "enabled": True,
            "instruction": (
                f"This field is a sparse {request.statement_type} line item. "
                f"If the {request.statement_type} section IS present in the "
                "chunks (other line items of that section are visible) but it "
                "contains NO line for this field, the value is genuinely zero "
                "for the period: return found=true with value='0' and cite the "
                "section's completeness in reasoning (e.g. 'financing "
                "activities fully listed, no share repurchase line'). Only "
                "return found=false if the relevant statement section itself is "
                "absent from the chunks."
            ),
        }
    return payload


SYSTEM_PROMPT = (
    "You extract financial report field values from PDF chunks.\n"
    "Return strictly valid JSON matching the requested schema.\n"
    "\n"
    "Rules:\n"
    "- If the field value is genuinely not present in the provided chunks, "
    "return found=false with reasoning.\n"
    "- expected_currency and expected_unit in the request are hints only — "
    "if the actual reported currency/unit differs, still extract the value "
    "and report the ACTUAL currency/unit (e.g., 'RMB', 'thousand'). "
    "Downstream code handles unit/currency conversion.\n"
    "- Never fabricate values. Cite the page and exact statement line text "
    "from the chunks (statement_line should be the literal text from the PDF).\n"
    "- For values reported in thousands (often marked 'RMB'000', '$'000', or "
    "in a thousands column), return the literal number AND set unit='thousand'. "
    "Do not pre-convert to millions.\n"
    "- For values reported in millions (often marked 'HK$ million', "
    "'$ Million', '人民币百万元'), return the literal number AND set "
    "unit='million'.\n"
    "- value must be the numeric string as it appears in the PDF (with "
    "commas removed if a clean number; e.g., '346,347' becomes '346347')."
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

    # Real LLM transports (OpenAI-compatible, Gemini) return wrapped responses.
    # Unwrap to the inner JSON content if needed; FakeJsonClient returns the
    # content directly so unwrap_llm_content is idempotent for that case.
    content = unwrap_llm_content(raw)

    return _parse_response(request, content, raw_response=raw)


def unwrap_llm_content(raw: dict[str, object]) -> dict[str, object]:
    """Extract inner JSON content from wrapped LLM responses.

    Detects three response shapes:
    - Already-parsed content (FakeJsonClient): has top-level keys like
      'found' or 'field_id'. Returned as-is.
    - OpenAI-compatible (DeepSeek, Ollama, OpenAI): has 'choices' array
      with 'message.content' string that holds the JSON.
    - Gemini: has 'candidates' array with 'content.parts[0].text' string.

    Returns the inner JSON dict. Raises ValueError if a wrapped shape is
    detected but malformed.
    """
    # Already parsed (FakeJsonClient or pre-unwrapped): no transport keys.
    if (
        "choices" not in raw
        and "candidates" not in raw
        and "output" not in raw
        and not ("content" in raw and isinstance(raw.get("content"), list))
    ):
        return raw

    if (
        "choices" in raw
        or "candidates" in raw
        or "output" in raw
        or ("content" in raw and isinstance(raw.get("content"), list))
    ):
        parsed = json.loads(response_json_text(raw))
        if isinstance(parsed, dict):
            return parsed
        raise ValueError(f"LLM response content must be a JSON object: {raw!r}")

    raise ValueError(f"unable to unwrap LLM response: {raw!r}")


def _parse_response(
    request: FieldExtractionRequest,
    raw: dict[str, object],
    *,
    raw_response: dict[str, object] | None = None,
) -> FieldExtractionResult:
    errors: list[str] = []
    archive = raw_response if raw_response is not None else raw

    found = raw.get("found")
    if not isinstance(found, bool):
        errors.append("response missing or invalid 'found' field")
        return FieldExtractionResult(
            field_id=request.field_id,
            status="extraction_failed",
            raw_response=archive,
            errors=tuple(errors),
        )

    if not found:
        return FieldExtractionResult(
            field_id=request.field_id,
            status="not_found",
            reasoning=_str_or_none(raw.get("reasoning")),
            raw_response=archive,
        )

    value_raw = _str_or_none(raw.get("value"))
    parsed_numeric_value: Decimal | None = None
    # Phase I-C: only attempt Decimal parse for numeric value types.
    # Text fields (e.g., dividend_plan, segment_revenue_profit) carry
    # narrative content where Decimal parsing is meaningless.
    is_numeric_field = request.value_type in ("money", "number")
    if value_raw is not None and is_numeric_field:
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
        raw_response=archive,
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
