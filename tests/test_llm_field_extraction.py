"""Tests for llm_field_extraction module."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from financial_report_llm_extractor.llm_field_extraction import (
    FieldExtractionRequest,
    FieldExtractionResult,
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
