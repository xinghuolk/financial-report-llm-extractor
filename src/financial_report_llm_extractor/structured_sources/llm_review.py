"""LLM-assisted review for source-first ambiguity and consistency issues."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, cast

from financial_report_llm_extractor.models import Evidence
from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportItem,
    SourceFirstExportResult,
)
from financial_report_llm_extractor.structured_sources.models import SourceEvidence
from financial_report_llm_extractor.structured_sources.pdf_supplement import (
    PdfEvidenceSupplementResult,
)


ReviewKind = Literal["ambiguous_source_mapping", "source_pdf_consistency"]
ReviewDecision = Literal["accept_source", "reject_source", "needs_human_review", "not_reviewed"]


class JsonReviewClient(Protocol):
    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        pass


@dataclass(frozen=True)
class LlmReviewRequest:
    kind: ReviewKind
    field_id: str
    system_prompt: str
    user_payload: dict[str, object]


@dataclass(frozen=True)
class LlmReviewDecision:
    field_id: str
    kind: ReviewKind
    decision: ReviewDecision
    reason: str | None = None
    confidence: float | None = None
    errors: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "field_id": self.field_id,
            "kind": self.kind,
            "decision": self.decision,
            "reason": self.reason,
            "confidence": self.confidence,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class LlmReviewReport:
    decisions: dict[str, LlmReviewDecision]
    raw_response_paths: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "decisions": {
                decision_key: self.decisions[decision_key].to_dict()
                for decision_key in sorted(self.decisions)
            },
            "raw_response_paths": list(self.raw_response_paths),
        }


def build_llm_review_requests(
    export_result: SourceFirstExportResult,
    *,
    pdf_supplement: PdfEvidenceSupplementResult | None = None,
) -> tuple[LlmReviewRequest, ...]:
    requests: list[LlmReviewRequest] = []
    for field_id, item in export_result.items.items():
        if item.status in {"ambiguous", "conflict"}:
            requests.append(_ambiguous_source_mapping_request(item))

    if pdf_supplement is not None:
        for field_id, supplement_item in pdf_supplement.items.items():
            if supplement_item.consistency_status != "value_not_found_in_snippet":
                continue
            export_item = export_result.items.get(field_id)
            if export_item is None:
                continue
            requests.append(
                _source_pdf_consistency_request(
                    export_item,
                    supplement_item.pdf_evidence,
                    supplement_item.consistency_status,
                )
            )
    return tuple(requests)


def run_llm_reviews(
    requests: tuple[LlmReviewRequest, ...],
    client: JsonReviewClient,
    *,
    raw_response_dir: Path,
) -> LlmReviewReport:
    raw_response_dir.mkdir(parents=True, exist_ok=True)
    decisions: dict[str, LlmReviewDecision] = {}
    raw_paths: list[str] = []
    for index, request in enumerate(requests):
        raw_response = client.complete_json(
            system_prompt=request.system_prompt,
            user_payload=request.user_payload,
        )
        raw_path = raw_response_dir / _raw_filename(index, request)
        raw_path.write_text(
            json.dumps(
                {
                    "request": request.user_payload,
                    "system_prompt": request.system_prompt,
                    "raw_response": raw_response,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        raw_paths.append(str(raw_path))
        decisions[_decision_key(request)] = _parse_decision(request, raw_response)
    return LlmReviewReport(
        decisions=decisions,
        raw_response_paths=tuple(raw_paths),
    )


def _ambiguous_source_mapping_request(
    item: SourceFirstExportItem,
) -> LlmReviewRequest:
    return LlmReviewRequest(
        kind="ambiguous_source_mapping",
        field_id=item.field_id,
        system_prompt=_system_prompt(),
        user_payload={
            "kind": "ambiguous_source_mapping",
            "field_id": item.field_id,
            "export_status": item.status,
            "mapping_status": item.mapping_status,
            "reconciliation_status": item.reconciliation_status,
            "value": str(item.value) if item.value is not None else None,
            "normalized_value": (
                str(item.normalized_value)
                if item.normalized_value is not None
                else None
            ),
            "currency": item.currency,
            "unit": item.unit,
            "period": item.period,
            "scope": item.scope,
            "source_evidence": _source_evidence(item.source_evidence),
            "pdf_evidence": _pdf_evidence(item.pdf_evidence),
            "errors": list(item.errors),
            "warnings": list(item.warnings),
        },
    )


def _source_pdf_consistency_request(
    item: SourceFirstExportItem,
    pdf_evidence: tuple[Evidence, ...],
    consistency_status: str,
) -> LlmReviewRequest:
    return LlmReviewRequest(
        kind="source_pdf_consistency",
        field_id=item.field_id,
        system_prompt=_system_prompt(),
        user_payload={
            "kind": "source_pdf_consistency",
            "field_id": item.field_id,
            "export_status": item.status,
            "value": str(item.value) if item.value is not None else None,
            "normalized_value": (
                str(item.normalized_value)
                if item.normalized_value is not None
                else None
            ),
            "currency": item.currency,
            "unit": item.unit,
            "period": item.period,
            "scope": item.scope,
            "consistency_status": consistency_status,
            "source_evidence": _source_evidence(item.source_evidence),
            "pdf_evidence": _pdf_evidence(pdf_evidence),
        },
    )


def _system_prompt() -> str:
    return (
        "You are reviewing financial extraction evidence. Return strict JSON "
        "with field_id, decision, reason, and confidence. Do not invent values, "
        "do not normalize money, and do not add evidence."
    )


def _parse_decision(
    request: LlmReviewRequest,
    raw_response: dict[str, object],
) -> LlmReviewDecision:
    raw_decision = raw_response.get("decision")
    if raw_decision not in {"accept_source", "reject_source", "needs_human_review"}:
        return LlmReviewDecision(
            field_id=request.field_id,
            kind=request.kind,
            decision="not_reviewed",
            reason=str(raw_response.get("reason")) if raw_response.get("reason") else None,
            errors=("invalid or missing decision",),
        )
    decision = cast(ReviewDecision, raw_decision)
    confidence = raw_response.get("confidence")
    return LlmReviewDecision(
        field_id=str(raw_response.get("field_id") or request.field_id),
        kind=request.kind,
        decision=decision,
        reason=str(raw_response.get("reason")) if raw_response.get("reason") else None,
        confidence=float(confidence) if isinstance(confidence, int | float) else None,
    )


def _raw_filename(index: int, request: LlmReviewRequest) -> str:
    return f"{index:04d}_{request.kind}_{request.field_id}.json"


def _decision_key(request: LlmReviewRequest) -> str:
    return f"{request.kind}:{request.field_id}"


def _source_evidence(evidence_items: tuple[SourceEvidence, ...]) -> list[dict[str, object]]:
    return [dict(evidence.to_dict()) for evidence in evidence_items]


def _pdf_evidence(evidence_items: tuple[Evidence, ...]) -> list[dict[str, object]]:
    return [
        {
            "page": evidence.page,
            "chunk_id": evidence.chunk_id,
            "block_id": evidence.block_id,
            "snippet": evidence.snippet,
            "table_id": evidence.table_id,
            "cell_id": evidence.cell_id,
            "bbox": list(evidence.bbox) if evidence.bbox is not None else None,
        }
        for evidence in evidence_items
    ]
