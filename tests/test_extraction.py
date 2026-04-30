import json
from pathlib import Path

from financial_report_llm_extractor.extraction import (
    FakeLlmClient,
    LlmExtractedField,
    LlmResponse,
    PromptRequest,
    run_fake_extraction,
)


def test_fake_llm_client_returns_fixture_response() -> None:
    response = LlmResponse(
        fields=(
            LlmExtractedField(
                field_id="revenue",
                status="present",
                value_raw="100",
                unit_context="HKD million",
            ),
        )
    )
    client = FakeLlmClient({"revenue": response})
    request = PromptRequest(
        field_id="revenue",
        candidates=({"evidence": {"snippet": "Revenue 100"}},),
    )

    assert client.extract(request) == response


def test_run_fake_extraction_normalizes_money_and_requires_evidence(
    tmp_path: Path,
) -> None:
    retrieval_probe = {
        "source_pdf_hash": "hash123",
        "fields": [
            {
                "field_id": "revenue",
                "status": "candidates_found",
                "candidates": [
                    {
                        "chunk_id": "stmt_income_p0005_p0005",
                        "score": 16,
                        "matched_aliases": ["Revenue"],
                        "evidence": {
                            "page": 5,
                            "chunk_id": "stmt_income_p0005_p0005",
                            "block_id": "p0005_b0001",
                            "snippet": "Revenue 100",
                        },
                    }
                ],
            },
            {
                "field_id": "cash",
                "status": "missing",
                "candidates": [],
            },
        ],
    }
    probe_path = tmp_path / "retrieval_probe.json"
    output_path = tmp_path / "extraction_result.json"
    probe_path.write_text(json.dumps(retrieval_probe), encoding="utf-8")

    client = FakeLlmClient(
        {
            "revenue": LlmResponse(
                fields=(
                    LlmExtractedField(
                        field_id="revenue",
                        status="present",
                        value_raw="100",
                        unit_context="HKD million",
                    ),
                )
            )
        }
    )

    result = run_fake_extraction(
        probe_path,
        output_path=output_path,
        llm_client=client,
    )

    assert result.output_path == output_path
    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert output["source_pdf_hash"] == "hash123"

    revenue = output["items"][0]
    assert revenue["field_id"] == "revenue"
    assert revenue["status"] == "present"
    assert revenue["money"]["normalized_value"] == "100000000"
    assert revenue["evidence"][0]["block_id"] == "p0005_b0001"

    cash = output["items"][1]
    assert cash["field_id"] == "cash"
    assert cash["status"] == "missing"


def test_present_fake_response_without_evidence_is_downgraded(
    tmp_path: Path,
) -> None:
    probe_path = tmp_path / "retrieval_probe.json"
    output_path = tmp_path / "extraction_result.json"
    probe_path.write_text(
        json.dumps(
            {
                "source_pdf_hash": "hash123",
                "fields": [
                    {
                        "field_id": "revenue",
                        "status": "missing",
                        "candidates": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    client = FakeLlmClient(
        {
            "revenue": LlmResponse(
                fields=(
                    LlmExtractedField(
                        field_id="revenue",
                        status="present",
                        value_raw="100",
                        unit_context="HKD million",
                    ),
                )
            )
        }
    )

    run_fake_extraction(probe_path, output_path=output_path, llm_client=client)

    output = json.loads(output_path.read_text(encoding="utf-8"))
    item = output["items"][0]
    assert item["field_id"] == "revenue"
    assert item["status"] == "extraction_failed"
    assert "present extracted items must include evidence" in item["errors"]
