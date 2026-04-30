"""Field-first retrieval over block-level evidence."""

from __future__ import annotations

import re
from typing import Any

from financial_report_llm_extractor.evidence_index import EvidenceBlock, EvidenceIndex
from financial_report_llm_extractor.retrieval import FIELD_HINTS


UNIT_HINT_RE = re.compile(
    r"rmb|cny|hkd|usd|hk\$|us\$|million|thousand|人民币|港元|美元|百万元|千元|万元|亿元",
    re.IGNORECASE,
)


def retrieve_field_first(
    index: EvidenceIndex,
    selected_fields: tuple[str, ...],
    *,
    top_k: int = 8,
) -> dict[str, Any]:
    fields = []
    for field_id in selected_fields:
        aliases, statement_hints = FIELD_HINTS.get(field_id, ((field_id,), ()))
        aliases = _dedupe((field_id, *aliases))
        candidates = _retrieve_block_candidates(
            field_id=field_id,
            aliases=aliases,
            statement_hints=statement_hints,
            blocks=index.blocks,
            top_k=top_k,
        )
        fields.append(
            {
                "field_id": field_id,
                "status": "candidates_found" if candidates else "missing",
                "candidates": candidates,
            }
        )
    return {"fields": fields}


def estimate_prompt_budget(result: dict[str, Any]) -> dict[str, Any]:
    fields = []
    total_candidate_text_chars = 0
    for field in result.get("fields", []):
        candidates = field.get("candidates", [])
        candidate_text_chars = sum(
            len(str(candidate.get("text", ""))) for candidate in candidates
        )
        total_candidate_text_chars += candidate_text_chars
        fields.append(
            {
                "field_id": str(field.get("field_id", "")),
                "candidate_text_chars": candidate_text_chars,
                "candidate_count": len(candidates),
            }
        )
    return {
        "total_candidate_text_chars": total_candidate_text_chars,
        "fields": fields,
    }


def _retrieve_block_candidates(
    *,
    field_id: str,
    aliases: tuple[str, ...],
    statement_hints: tuple[str, ...],
    blocks: tuple[EvidenceBlock, ...],
    top_k: int,
) -> list[dict[str, Any]]:
    candidates_by_block_id: dict[str, dict[str, Any]] = {}
    for ordinal, block in enumerate(blocks):
        matched_aliases = _matched_aliases(block.text, aliases)
        if not matched_aliases:
            continue

        score = _score_block(block, matched_aliases, statement_hints)
        candidate = {
            "field_id": field_id,
            "chunk_id": block.chunk_id,
            "score": score,
            "matched_aliases": list(matched_aliases),
            "text": block.text,
            "evidence": {
                "page": block.page,
                "chunk_id": block.chunk_id,
                "block_id": block.block_id,
                "snippet": _snippet_for_alias(block.text, matched_aliases[0]),
            },
            "_ordinal": ordinal,
        }
        existing = candidates_by_block_id.get(block.block_id)
        if existing is None or _is_better_candidate(candidate, existing):
            candidates_by_block_id[block.block_id] = candidate

    ranked = sorted(
        candidates_by_block_id.values(),
        key=lambda candidate: (-candidate["score"], candidate["_ordinal"]),
    )[:top_k]
    for candidate in ranked:
        del candidate["_ordinal"]
    return ranked


def _score_block(
    block: EvidenceBlock,
    matched_aliases: tuple[str, ...],
    statement_hints: tuple[str, ...],
) -> float:
    value_numeric_count = max(0, block.numeric_token_count - block.year_count)
    numeric_density = (
        value_numeric_count / block.token_count if block.token_count else 0.0
    )
    score = float(len(matched_aliases) * 100)
    score += numeric_density * 60
    score += min(value_numeric_count, 4)
    score += min(block.year_count, 4) * 2
    score += min(len(UNIT_HINT_RE.findall(block.text)), 3) * 2
    if block.statement_kind in statement_hints:
        score += 10
    return score


def _is_better_candidate(
    candidate: dict[str, Any],
    existing: dict[str, Any],
) -> bool:
    return (candidate["score"], -candidate["_ordinal"]) > (
        existing["score"],
        -existing["_ordinal"],
    )


def _matched_aliases(text: str, aliases: tuple[str, ...]) -> tuple[str, ...]:
    lowered = text.lower()
    matches = [alias for alias in aliases if alias.lower() in lowered]
    longest_first = sorted(matches, key=len, reverse=True)
    kept: list[str] = []
    for alias in longest_first:
        if any(alias.lower() in longer.lower() for longer in kept):
            continue
        kept.append(alias)
    return tuple(alias for alias in aliases if alias in kept)


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _snippet_for_alias(text: str, alias: str) -> str:
    lowered_alias = alias.lower()
    for line in text.splitlines():
        if lowered_alias in line.lower():
            return line.strip()
    return text.splitlines()[0].strip() if text.splitlines() else ""
