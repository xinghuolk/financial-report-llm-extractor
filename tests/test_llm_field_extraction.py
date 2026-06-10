"""Tests for llm_field_extraction module."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

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


def test_build_prompt_omits_zero_inference_by_default() -> None:
    req = FieldExtractionRequest(
        field_id="revenue",
        field_description="operating revenue",
        statement_type="income_statement",
        value_type="money",
        chunks=({"chunk_id": "c1", "page_start": 4, "page_end": 4, "text": "..."},),
    )
    payload = build_field_extraction_prompt(req)
    assert "zero_inference" not in payload


def test_build_prompt_includes_zero_inference_when_flag_set() -> None:
    req = FieldExtractionRequest(
        field_id="repurchase_of_stock",
        field_description="repurchase of capital stock",
        statement_type="cash_flow",
        value_type="money",
        chunks=(
            {
                "chunk_id": "c1",
                "page_start": 139,
                "page_end": 139,
                "text": "Financing activities ... Dividends paid ...",
            },
        ),
        absence_means_zero=True,
    )
    payload = build_field_extraction_prompt(req)
    assert "zero_inference" in payload
    block = payload["zero_inference"]  # type: ignore[index]
    assert block["enabled"] is True  # type: ignore[index]
    # The instruction must tell the LLM that an absent line in a present
    # statement section means a genuine zero (found=true, value='0').
    instruction = str(block["instruction"]).lower()  # type: ignore[index]
    assert "found=true" in instruction
    assert "0" in instruction
    assert "cash_flow" in instruction


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


def test_unwrap_llm_content_reads_codex_responses_shape() -> None:
    from financial_report_llm_extractor.llm_field_extraction import unwrap_llm_content

    raw: dict[str, object] = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps({"field_id": "revenue", "found": False}),
                    }
                ],
            }
        ]
    }

    assert unwrap_llm_content(raw)["found"] is False


def test_unwrap_llm_content_reads_anthropic_messages_shape() -> None:
    from financial_report_llm_extractor.llm_field_extraction import unwrap_llm_content

    raw: dict[str, object] = {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"field_id": "revenue", "found": False}),
            }
        ]
    }

    assert unwrap_llm_content(raw)["found"] is False


# ---------------------------------------------------------------------------
# Task 5: Malformed response and raw archival
# ---------------------------------------------------------------------------


def test_run_extraction_with_malformed_response_marks_extraction_failed() -> None:
    from financial_report_llm_extractor.llm_field_extraction import run_field_extraction

    client = FakeJsonClient({"unexpected": "shape"})  # missing 'found'

    result = run_field_extraction(_sample_request(), client)

    assert result.status == "extraction_failed"
    assert any("found" in err for err in result.errors)
    assert result.raw_response == {"unexpected": "shape"}


def test_run_extraction_with_unparseable_value_marks_extraction_failed() -> None:
    from financial_report_llm_extractor.llm_field_extraction import run_field_extraction

    client = FakeJsonClient({
        "field_id": "revenue",
        "found": True,
        "value": "not-a-number",
        "currency": "HKD",
    })

    result = run_field_extraction(_sample_request(), client)

    assert result.status == "extraction_failed"
    assert any("unparseable" in err for err in result.errors)
    assert result.value == "not-a-number"  # raw value preserved


def test_run_extraction_archives_raw_response(tmp_path: Path) -> None:
    from financial_report_llm_extractor.llm_field_extraction import (
        PROMPT_VERSION,
        run_field_extraction,
    )

    client = FakeJsonClient({
        "field_id": "revenue",
        "found": True,
        "value": "280036000000",
    })

    run_field_extraction(_sample_request(), client, raw_response_dir=tmp_path)

    archive_path = tmp_path / f"revenue_{PROMPT_VERSION}.json"
    assert archive_path.exists()
    archived = json.loads(archive_path.read_text(encoding="utf-8"))
    assert archived["value"] == "280036000000"


# ---------------------------------------------------------------------------
# Task 6: Integration test against real chunk fixture
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "pdf_chunks"
CHUNKS_FIXTURE = FIXTURE_DIR / "00001_2025_chunks.jsonl"


def _load_fixture_chunks() -> tuple[dict[str, object], ...]:
    chunks: list[dict[str, object]] = []
    for line in CHUNKS_FIXTURE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            chunks.append(json.loads(line))
    return tuple(chunks)


def test_run_extraction_against_real_fixture_with_canned_response() -> None:
    from financial_report_llm_extractor.llm_field_extraction import run_field_extraction

    assert CHUNKS_FIXTURE.exists(), (
        f"Fixture missing: {CHUNKS_FIXTURE}. Run Task 1 to generate it."
    )

    chunks = _load_fixture_chunks()
    assert len(chunks) > 0, "fixture must contain at least one chunk"

    request = FieldExtractionRequest(
        field_id="revenue",
        field_description="operating revenue",
        statement_type="income_statement",
        value_type="money",
        chunks=chunks,
        expected_currency="HKD",
        expected_unit="raw",
    )

    # Canned LLM response with the known true value for 00001 2024 revenue
    canned_response = {
        "field_id": "revenue",
        "found": True,
        "value": "280036000000",
        "currency": "HKD",
        "unit": "raw",
        "period": "2024-12-31",
        "page": 134,
        "statement_line": "Revenue",
        "confidence": 0.95,
        "reasoning": "found on income statement page 134",
    }
    client = FakeJsonClient(canned_response)

    result = run_field_extraction(request, client)

    assert result.status == "present"
    assert result.parsed_numeric_value == Decimal("280036000000")
    assert result.currency == "HKD"
    assert result.page == 134


# ---------------------------------------------------------------------------
# Task 7: Opt-in real LLM smoke test
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("REAL_LLM_SMOKE") != "1",
    reason="Set REAL_LLM_SMOKE=1 and LLM_CONFIG_PATH to run real LLM smoke",
)
def test_real_llm_smoke_extracts_revenue_within_tolerance() -> None:
    from financial_report_llm_extractor.llm_field_extraction import run_field_extraction
    from financial_report_llm_extractor.llm_transport import (
        LlmTransportConfig,
        create_llm_client,
    )

    config_path = Path(os.environ["LLM_CONFIG_PATH"])
    config = LlmTransportConfig.from_json(config_path)
    client = create_llm_client(config)

    chunks = _load_fixture_chunks()
    request = FieldExtractionRequest(
        field_id="revenue",
        field_description="operating revenue",
        statement_type="income_statement",
        value_type="money",
        chunks=chunks,
        expected_currency="HKD",
        expected_unit="million",
    )

    archive_dir = Path("tmp/runs/llm_smoke")
    result = run_field_extraction(request, client, raw_response_dir=archive_dir)

    assert result.status == "present", (
        f"smoke failed: status={result.status} errors={result.errors} "
        f"raw={result.raw_response}"
    )
    assert result.parsed_numeric_value is not None

    # LLM should return PDF literal value (280,036 in HK$ million) or the
    # raw value (280,036,000,000). Either form proves framework correctness;
    # money normalizer downstream handles the unit conversion.
    expected_literal = Decimal("280036")
    expected_raw = Decimal("280036000000")
    val = result.parsed_numeric_value
    literal_delta = abs(val - expected_literal) / expected_literal
    raw_delta = abs(val - expected_raw) / expected_raw
    assert literal_delta < Decimal("0.01") or raw_delta < Decimal("0.05"), (
        f"smoke value {val} not within tolerance of either "
        f"PDF literal {expected_literal} (±1%) or raw {expected_raw} (±5%); "
        f"unit returned: {result.unit!r}"
    )


def test_extract_text_field_skips_decimal_parse() -> None:
    """Phase I-C: text-typed fields should not attempt Decimal parsing.
    Long narrative values must be returned as-is in `value` without
    extraction_failed errors.
    """
    from financial_report_llm_extractor.llm_field_extraction import run_field_extraction

    request = FieldExtractionRequest(
        field_id="dividend_plan",
        field_description="Dividend plan disclosure text.",
        statement_type="announcement",
        value_type="text",
        chunks=({"chunk_id": "c1", "page": 50, "text": "..."},),
        expected_currency=None,
        expected_unit=None,
    )
    canned = {
        "field_id": "dividend_plan",
        "found": True,
        "value": "Final dividend of HKD 1.20 per share for the year ended 31 December 2024, payable on 1 May 2025.",
        "currency": None,
        "unit": None,
        "page": 50,
        "statement_line": "Dividend Plan",
        "confidence": 0.9,
        "reasoning": "from notice section",
    }
    client = FakeJsonClient(canned)
    result = run_field_extraction(request, client)

    assert result.status == "present"
    assert result.value == canned["value"]
    assert result.parsed_numeric_value is None
    assert result.errors == ()
