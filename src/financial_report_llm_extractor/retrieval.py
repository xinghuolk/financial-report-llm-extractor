"""Candidate evidence retrieval from chunk artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


Priority = Literal["P0", "P1", "P2", "P3", "P4"]
RetrievalStatus = Literal["candidates_found", "missing"]


FIELD_HINTS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "revenue": (("revenue", "营业收入", "收入"), ("income_statement",)),
    "operating_cost": (("operating cost", "营业成本", "成本"), ("income_statement",)),
    "operating_profit": (("operating profit", "营业利润"), ("income_statement",)),
    "net_profit": (
        (
            "net profit",
            "profit for the year",
            "profit attributable to shareholders",
            "profit attributable to owners",
            "净利润",
        ),
        ("income_statement",),
    ),
    "gross_profit": (("gross profit", "毛利"), ("income_statement",)),
    "total_assets": (("total assets", "资产总计", "总资产"), ("balance_sheet",)),
    "total_liabilities": (("total liabilities", "负债合计", "总负债"), ("balance_sheet",)),
    "cash": (("cash and cash equivalents", "cash", "货币资金", "现金及现金等价物"), ("balance_sheet",)),
    "operating_cash_flow": (
        ("net cash from operating activities", "经营活动现金流量", "经营活动产生的现金流量"),
        ("cash_flow",),
    ),
    "investing_cash_flow": (
        ("net cash from investing activities", "投资活动现金流量", "投资活动产生的现金流量"),
        ("cash_flow",),
    ),
    "financing_cash_flow": (
        ("net cash from financing activities", "筹资活动现金流量", "筹资活动产生的现金流量"),
        ("cash_flow",),
    ),
}


@dataclass(frozen=True)
class FieldSpec:
    field_id: str
    priority: Priority
    aliases: tuple[str, ...]
    statement_hints: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalCandidate:
    chunk_id: str
    score: float
    matched_aliases: tuple[str, ...]
    evidence: dict[str, Any]


@dataclass(frozen=True)
class RetrievalProbeResult:
    output_path: Path
    field_count: int


def load_field_specs(
    catalog_path: Path,
    *,
    priorities: tuple[str, ...] = ("P0", "P1"),
) -> list[FieldSpec]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    wanted = set(priorities)
    specs: list[FieldSpec] = []
    for group in catalog["priorities"]:
        priority = group["priority"]
        if priority not in wanted:
            continue
        for field_id in group["fields"]:
            aliases, statement_hints = FIELD_HINTS.get(field_id, ((field_id,), ()))
            normalized_aliases = _dedupe((field_id, *aliases))
            specs.append(
                FieldSpec(
                    field_id=field_id,
                    priority=priority,
                    aliases=normalized_aliases,
                    statement_hints=statement_hints,
                )
            )
    return specs


def retrieve_candidates(
    field_id: str,
    chunks: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[RetrievalCandidate]:
    aliases, statement_hints = FIELD_HINTS.get(field_id, ((field_id,), ()))
    aliases = _dedupe((field_id, *aliases))
    candidates: list[RetrievalCandidate] = []
    for chunk in chunks:
        text = str(chunk.get("text", ""))
        matched_aliases = _matched_aliases(text, aliases)
        if not matched_aliases:
            continue
        score = float(len(matched_aliases) * 10)
        if chunk.get("statement_kind") in statement_hints:
            score += 5
        if chunk.get("kind") == "statement_table":
            score += 1
        candidates.append(
            RetrievalCandidate(
                chunk_id=str(chunk["chunk_id"]),
                score=score,
                matched_aliases=matched_aliases,
                evidence=_build_evidence(chunk, matched_aliases[0]),
            )
        )

    return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)[:limit]


def write_retrieval_probe(
    catalog_path: Path,
    chunks_path: Path,
    *,
    output_path: Path | None = None,
    priorities: tuple[str, ...] = ("P0", "P1"),
) -> RetrievalProbeResult:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    chunks = _read_chunk_records(chunks_path)
    specs = load_field_specs(catalog_path, priorities=priorities)
    source_pdf_hash = _first_source_pdf_hash(chunks)
    output = output_path or chunks_path.parent / "retrieval_probe.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    fields = []
    for spec in specs:
        candidates = retrieve_candidates(spec.field_id, chunks)
        fields.append(
            {
                "field_id": spec.field_id,
                "priority": spec.priority,
                "status": "candidates_found" if candidates else "missing",
                "aliases": list(spec.aliases),
                "statement_hints": list(spec.statement_hints),
                "candidates": [
                    {
                        "chunk_id": candidate.chunk_id,
                        "score": candidate.score,
                        "matched_aliases": list(candidate.matched_aliases),
                        "evidence": candidate.evidence,
                    }
                    for candidate in candidates
                ],
            }
        )

    output.write_text(
        json.dumps(
            {
                "catalog_id": catalog["catalog_id"],
                "catalog_version": catalog["version"],
                "source_pdf_hash": source_pdf_hash,
                "priorities": list(priorities),
                "fields": fields,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return RetrievalProbeResult(output_path=output, field_count=len(fields))


def _read_chunk_records(chunks_path: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for line in chunks_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("record_type") == "chunk":
            chunks.append(record)
    return chunks


def _first_source_pdf_hash(chunks: list[dict[str, Any]]) -> str | None:
    for chunk in chunks:
        value = chunk.get("source_pdf_hash")
        if isinstance(value, str) and value:
            return value
    return None


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


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


def _build_evidence(chunk: dict[str, Any], alias: str) -> dict[str, Any]:
    text = str(chunk.get("text", ""))
    block_id, snippet = _matching_block_evidence(chunk, alias)
    return {
        "page": chunk.get("page_start"),
        "chunk_id": chunk.get("chunk_id"),
        "block_id": block_id,
        "snippet": snippet or _snippet_for_alias(text, alias),
    }


def _matching_block_evidence(
    chunk: dict[str, Any],
    alias: str,
) -> tuple[str | None, str | None]:
    block_texts = chunk.get("block_texts")
    if not isinstance(block_texts, dict):
        return _first_block_id(chunk), None

    lowered_alias = alias.lower()
    for block_id, block_text in block_texts.items():
        text = str(block_text)
        if lowered_alias in text.lower():
            return str(block_id), _snippet_for_alias(text, alias)
    return _first_block_id(chunk), None


def _first_block_id(chunk: dict[str, Any]) -> str | None:
    block_ids = chunk.get("block_ids", [])
    if isinstance(block_ids, list) and block_ids:
        return str(block_ids[0])
    return None


def _snippet_for_alias(text: str, alias: str) -> str:
    lowered_alias = alias.lower()
    for line in text.splitlines():
        if lowered_alias in line.lower():
            return line.strip()
    return text.splitlines()[0].strip() if text.splitlines() else ""
