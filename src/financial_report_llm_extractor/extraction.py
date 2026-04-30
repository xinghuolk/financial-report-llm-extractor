"""Fake LLM extraction pipeline for contract validation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from financial_report_llm_extractor.models import Evidence, ExtractedItem
from financial_report_llm_extractor.money import MoneyNormalizationError, normalize_money


PROMPT_VERSION = "fake-extraction-v1"
SCHEMA_VERSION = "extracted-items-v1"

LlmFieldStatus = Literal["present", "missing", "ambiguous", "not_applicable"]


@dataclass(frozen=True)
class PromptRequest:
    field_id: str
    candidates: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class LlmExtractedField:
    field_id: str
    status: LlmFieldStatus
    value_raw: str | None = None
    unit_context: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class LlmResponse:
    fields: tuple[LlmExtractedField, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExtractionPipelineResult:
    output_path: Path
    item_count: int


class LlmClient(Protocol):
    def extract(self, request: PromptRequest) -> LlmResponse:
        pass


@dataclass(frozen=True)
class FakeLlmClient:
    responses: dict[str, LlmResponse]

    def extract(self, request: PromptRequest) -> LlmResponse:
        return self.responses.get(
            request.field_id,
            LlmResponse(
                fields=(LlmExtractedField(field_id=request.field_id, status="missing"),)
            ),
        )


def run_fake_extraction(
    retrieval_probe_path: Path,
    *,
    output_path: Path | None = None,
    llm_client: LlmClient | None = None,
) -> ExtractionPipelineResult:
    probe = json.loads(retrieval_probe_path.read_text(encoding="utf-8"))
    client = llm_client or FakeLlmClient({})
    output = output_path or retrieval_probe_path.parent / "extraction_result.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, Any]] = []
    for probe_field in probe["fields"]:
        request = PromptRequest(
            field_id=probe_field["field_id"],
            candidates=tuple(probe_field.get("candidates", [])),
        )
        response = client.extract(request)
        extracted = _first_response_field(response, request.field_id)
        item, errors = _build_extracted_item(extracted, request)
        items.append(_serialize_item(item, errors))

    output.write_text(
        json.dumps(
            {
                "source_pdf_hash": probe.get("source_pdf_hash"),
                "prompt_version": PROMPT_VERSION,
                "schema_version": SCHEMA_VERSION,
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return ExtractionPipelineResult(output_path=output, item_count=len(items))


def _first_response_field(response: LlmResponse, field_id: str) -> LlmExtractedField:
    for response_field in response.fields:
        if response_field.field_id == field_id:
            return response_field
    return LlmExtractedField(field_id=field_id, status="missing")


def _build_extracted_item(
    field: LlmExtractedField,
    request: PromptRequest,
) -> tuple[ExtractedItem, tuple[str, ...]]:
    errors: list[str] = []
    evidence = _candidate_evidence(request)
    try:
        money = None
        if field.status == "present":
            if field.value_raw is None or field.unit_context is None:
                raise ValueError("present money items must include value_raw and unit_context")
            money = normalize_money(field.value_raw, unit_context=field.unit_context)
        item = ExtractedItem(
            field_id=field.field_id,
            status=field.status,
            value_type="money",
            money=money,
            confidence=field.confidence,
            evidence=evidence,
        )
        item.validate()
        return item, tuple(errors)
    except (MoneyNormalizationError, ValueError) as error:
        errors.append(str(error))
        failed = ExtractedItem(
            field_id=field.field_id,
            status="extraction_failed",
            value_type="money",
            confidence=field.confidence,
            evidence=evidence,
        )
        failed.validate()
        return failed, tuple(errors)


def _candidate_evidence(request: PromptRequest) -> tuple[Evidence, ...]:
    if not request.candidates:
        return ()
    evidence = request.candidates[0].get("evidence", {})
    try:
        return (
            Evidence(
                page=int(evidence["page"]),
                chunk_id=str(evidence["chunk_id"]),
                block_id=str(evidence["block_id"]),
                snippet=str(evidence["snippet"]),
            ),
        )
    except (KeyError, TypeError, ValueError):
        return ()


def _serialize_item(item: ExtractedItem, errors: tuple[str, ...]) -> dict[str, Any]:
    return {
        "field_id": item.field_id,
        "status": item.status,
        "value_type": item.value_type,
        "money": _serialize_money(item),
        "confidence": item.confidence,
        "evidence": [
            {
                "page": evidence.page,
                "chunk_id": evidence.chunk_id,
                "block_id": evidence.block_id,
                "snippet": evidence.snippet,
            }
            for evidence in item.evidence
        ],
        "errors": list(errors),
    }


def _serialize_money(item: ExtractedItem) -> dict[str, str] | None:
    if item.money is None:
        return None
    return {
        "value_raw": item.money.value_raw,
        "value": str(item.money.value),
        "currency": item.money.currency,
        "unit": item.money.unit,
        "unit_multiplier": str(item.money.unit_multiplier),
        "normalized_value": str(item.money.normalized_value),
        "normalized_unit": item.money.normalized_unit,
    }
