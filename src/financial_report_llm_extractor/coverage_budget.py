"""Coverage and prompt-budget metrics for Turtle field retrieval."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from financial_report_llm_extractor.evidence_index import build_evidence_index
from financial_report_llm_extractor.field_first_retrieval import (
    estimate_prompt_budget,
    retrieve_field_first,
)


def load_catalog_field_ids(
    catalog_path: Path,
    *,
    priorities: tuple[str, ...],
    explicit_fields: tuple[str, ...] = (),
) -> tuple[str, ...]:
    if explicit_fields:
        return _dedupe(explicit_fields)

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    wanted = set(priorities)
    fields: list[str] = []
    for group in catalog.get("priorities", []):
        if group.get("priority") not in wanted:
            continue
        fields.extend(str(field_id) for field_id in group.get("fields", []))
    return _dedupe(tuple(fields))


def build_coverage_metrics(
    records: list[dict[str, Any]],
    *,
    selected_fields: tuple[str, ...],
    top_k_values: tuple[int, ...],
) -> list[dict[str, Any]]:
    index = build_evidence_index(records)
    metrics: list[dict[str, Any]] = []
    for top_k in top_k_values:
        retrieval = retrieve_field_first(index, selected_fields, top_k=top_k)
        budget = estimate_prompt_budget(retrieval)
        budget_by_field = {
            str(field["field_id"]): field for field in budget.get("fields", [])
        }
        field_metrics = [
            _field_metric(field, budget_by_field.get(str(field.get("field_id")), {}))
            for field in retrieval.get("fields", [])
        ]
        missing_fields = [
            str(field["field_id"])
            for field in field_metrics
            if field["status"] != "candidates_found"
        ]
        covered_fields = len(field_metrics) - len(missing_fields)
        total_chars = int(budget["total_candidate_text_chars"])
        total_fields = len(field_metrics)
        metrics.append(
            {
                "top_k": top_k,
                "total_fields": total_fields,
                "covered_fields": covered_fields,
                "missing_fields": missing_fields,
                "coverage_ratio": covered_fields / total_fields if total_fields else 0.0,
                "total_candidate_text_chars": total_chars,
                "rough_token_estimate": math.ceil(total_chars / 4),
                "fields": field_metrics,
            }
        )
    return metrics


def _field_metric(
    field: dict[str, Any],
    budget_field: dict[str, Any],
) -> dict[str, Any]:
    candidates = field.get("candidates", [])
    first_candidate = candidates[0] if candidates else {}
    evidence = first_candidate.get("evidence", {})
    return {
        "field_id": str(field.get("field_id", "")),
        "status": str(field.get("status", "missing")),
        "candidate_count": int(budget_field.get("candidate_count", len(candidates))),
        "candidate_text_chars": int(budget_field.get("candidate_text_chars", 0)),
        "top_score": first_candidate.get("score"),
        "top_evidence": {
            "page": evidence.get("page"),
            "chunk_id": evidence.get("chunk_id"),
            "block_id": evidence.get("block_id"),
            "snippet": evidence.get("snippet"),
        },
    }


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)
