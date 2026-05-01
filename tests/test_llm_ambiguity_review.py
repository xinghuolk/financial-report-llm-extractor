from decimal import Decimal
import json
from pathlib import Path
from typing import Any, cast

from financial_report_llm_extractor.models import Evidence
from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportItem,
    SourceFirstExportResult,
)
from financial_report_llm_extractor.structured_sources.llm_review import (
    build_llm_review_requests,
    run_llm_reviews,
)
from financial_report_llm_extractor.structured_sources.models import SourceEvidence
from financial_report_llm_extractor.structured_sources.pdf_supplement import (
    PdfEvidenceSupplementItem,
    PdfEvidenceSupplementResult,
)


def test_build_review_requests_selects_ambiguous_and_consistency_items() -> None:
    export = _export_result(
        {
            "revenue": _export_item("revenue", status="conflict"),
            "cash": _export_item("cash", status="present"),
        }
    )
    supplement = PdfEvidenceSupplementResult(
        profile="pdf_required",
        catalog_id="test",
        catalog_version="1",
        items={
            "cash": PdfEvidenceSupplementItem(
                field_id="cash",
                status="pdf_evidence_found",
                pdf_evidence=(_pdf_evidence("Cash 99"),),
                consistency_status="value_not_found_in_snippet",
            )
        },
    )

    requests = build_llm_review_requests(export, pdf_supplement=supplement)

    assert [request.kind for request in requests] == [
        "ambiguous_source_mapping",
        "source_pdf_consistency",
    ]
    assert requests[0].field_id == "revenue"
    assert requests[0].user_payload["source_evidence"]
    assert requests[1].field_id == "cash"
    assert requests[1].user_payload["pdf_evidence"]


def test_run_llm_reviews_archives_raw_request_response_and_parses_decision(
    tmp_path: Path,
) -> None:
    export = _export_result({"revenue": _export_item("revenue", status="conflict")})
    requests = build_llm_review_requests(export)
    client = FakeReviewClient(
        [
            {
                "field_id": "revenue",
                "decision": "needs_human_review",
                "reason": "AKShare and Yahoo disagree.",
                "confidence": 0.42,
            }
        ]
    )

    report = run_llm_reviews(requests, client, raw_response_dir=tmp_path)

    decision = report.decisions["revenue"]
    assert decision.decision == "needs_human_review"
    assert decision.reason == "AKShare and Yahoo disagree."
    assert decision.confidence == 0.42
    first_payload = cast(dict[str, Any], client.calls[0]["user_payload"])
    assert first_payload["field_id"] == "revenue"

    raw_files = sorted(tmp_path.glob("*.json"))
    assert len(raw_files) == 1
    payload = json.loads(raw_files[0].read_text(encoding="utf-8"))
    assert payload["request"]["field_id"] == "revenue"
    assert payload["raw_response"]["decision"] == "needs_human_review"


def test_run_llm_reviews_archives_malformed_response_and_marks_not_reviewed(
    tmp_path: Path,
) -> None:
    export = _export_result({"revenue": _export_item("revenue", status="conflict")})
    requests = build_llm_review_requests(export)
    client = FakeReviewClient([{"field_id": "revenue", "reason": "missing decision"}])

    report = run_llm_reviews(requests, client, raw_response_dir=tmp_path)

    decision = report.decisions["revenue"]
    assert decision.decision == "not_reviewed"
    assert decision.errors == ("invalid or missing decision",)
    assert len(list(tmp_path.glob("*.json"))) == 1


class FakeReviewClient:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_payload": user_payload,
            }
        )
        return self.responses.pop(0)


def _export_result(
    items: dict[str, SourceFirstExportItem],
) -> SourceFirstExportResult:
    return SourceFirstExportResult(
        profile="pdf_required",
        catalog_id="test",
        catalog_version="1",
        items=items,
    )


def _export_item(field_id: str, *, status: str) -> SourceFirstExportItem:
    return SourceFirstExportItem(
        field_id=field_id,
        status=status,  # type: ignore[arg-type]
        value=Decimal("100"),
        normalized_value=Decimal("100"),
        currency="CNY",
        unit="yuan",
        period="2024-12-31",
        scope="consolidated",
        source_evidence=(
            SourceEvidence(
                source="akshare",
                adapter="akshare",
                function="fixture",
                artifact_id="akshare_artifact",
                raw_record_id=f"akshare:{field_id}",
                raw_field_name=field_id,
            ),
        ),
        pdf_evidence=(_pdf_evidence(f"{field_id} 100"),)
        if status == "present"
        else (),
        errors=("source conflict",) if status == "conflict" else (),
    )


def _pdf_evidence(snippet: str) -> Evidence:
    return Evidence(
        page=10,
        chunk_id="chunk-10",
        block_id="p0010_b0001",
        snippet=snippet,
    )
