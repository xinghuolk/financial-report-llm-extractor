"""Tests for llm_field_extraction module."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from financial_report_llm_extractor.llm_field_extraction import (
    FieldExtractionRequest,
    FieldExtractionResult,
    build_field_extraction_prompt,
    PROMPT_VERSION,
    SCHEMA_VERSION,
)


def test_field_extraction_request_constructs_with_required_fields() -> None:
    req = FieldExtractionRequest(
        field_id="revenue",
        field_description="operating revenue",
        statement_type="income_statement",
        value_type="money",
        chunks=({"chunk_id": "c1", "page_start": 1, "page_end": 1, "text": "..."},),
        expected_currency="HKD",
        expected_unit="raw",
    )
    assert req.field_id == "revenue"
    assert req.value_type == "money"
    assert len(req.chunks) == 1


def test_field_extraction_result_present_status() -> None:
    result = FieldExtractionResult(
        field_id="revenue",
        status="present",
        value="280036000000",
        parsed_numeric_value=Decimal("280036000000"),
        currency="HKD",
        unit="raw",
        period="2025-12-31",
        page=4,
        statement_line="营业收入",
        confidence=0.95,
        reasoning="found on income statement page 4",
        raw_response={"found": True},
        errors=(),
    )
    assert result.status == "present"
    assert result.parsed_numeric_value == Decimal("280036000000")


def test_build_prompt_includes_field_metadata_and_chunks() -> None:
    req = FieldExtractionRequest(
        field_id="revenue",
        field_description="operating revenue (营业收入)",
        statement_type="income_statement",
        value_type="money",
        chunks=(
            {"chunk_id": "c1", "page_start": 4, "page_end": 4, "text": "营业收入  168,838"},
        ),
        expected_currency="HKD",
        expected_unit="raw",
    )
    payload = build_field_extraction_prompt(req)

    assert payload["prompt_version"] == PROMPT_VERSION
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["task"] == "extract_field_value"
    assert payload["field"]["field_id"] == "revenue"  # type: ignore[index]
    assert payload["field"]["description"] == "operating revenue (营业收入)"  # type: ignore[index]
    assert payload["field"]["statement_type"] == "income_statement"  # type: ignore[index]
    assert payload["field"]["expected_currency"] == "HKD"  # type: ignore[index]
    assert len(payload["chunks"]) == 1  # type: ignore[arg-type]
    assert payload["chunks"][0]["text"] == "营业收入  168,838"  # type: ignore[index]
    # Response schema is included for the LLM to follow
    assert "response_schema" in payload
    assert "found" in payload["response_schema"]["properties"]  # type: ignore[index]


# ---------------------------------------------------------------------------
# Task 4: Runner with FakeJsonClient
# ---------------------------------------------------------------------------


class FakeJsonClient:
    """In-test fake matching the JsonClient Protocol."""

    def __init__(self, response: dict[str, object]) -> None:
        self._response = response

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        return self._response


def _sample_request() -> FieldExtractionRequest:
    return FieldExtractionRequest(
        field_id="revenue",
        field_description="operating revenue",
        statement_type="income_statement",
        value_type="money",
        chunks=(
            {"chunk_id": "c1", "page_start": 4, "page_end": 4, "text": "营业收入  168,838"},
        ),
        expected_currency="HKD",
        expected_unit="raw",
    )


def test_run_extraction_with_present_response_returns_present_result() -> None:
    from financial_report_llm_extractor.llm_field_extraction import run_field_extraction

    client = FakeJsonClient({
        "field_id": "revenue",
        "found": True,
        "value": "280036000000",
        "currency": "HKD",
        "unit": "raw",
        "period": "2025-12-31",
        "page": 4,
        "statement_line": "营业收入",
        "confidence": 0.95,
        "reasoning": "found on income statement page 4",
    })

    result = run_field_extraction(_sample_request(), client)

    assert result.status == "present"
    assert result.value == "280036000000"
    assert result.parsed_numeric_value == Decimal("280036000000")
    assert result.currency == "HKD"
    assert result.page == 4
    assert result.statement_line == "营业收入"
    assert result.errors == ()


def test_run_extraction_with_not_found_response_returns_not_found() -> None:
    from financial_report_llm_extractor.llm_field_extraction import run_field_extraction

    client = FakeJsonClient({
        "field_id": "revenue",
        "found": False,
        "reasoning": "no income statement found in chunks",
    })

    result = run_field_extraction(_sample_request(), client)

    assert result.status == "not_found"
    assert result.value is None
    assert result.parsed_numeric_value is None
