"""LLM-assisted field extraction orchestrator.

Derives extraction targets from catalog metadata (no per-field code),
selects PDF chunks via alias scoring or broad keyword filter, and calls
the existing llm_field_extraction primitive.

Used by the `extract-llm` CLI to produce llm_evidence_supplement.json
artifacts that provider_baseline_replay can merge into source-first
exports for fields where source providers have no value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from financial_report_llm_extractor.field_metadata import FieldTaxonomyCatalog
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
)


ChunkStrategy = Literal["alias_top_k", "broad_keyword"]


@dataclass(frozen=True)
class LlmExtractionTarget:
    field_id: str
    field_description: str
    statement_type: str
    value_type: str
    aliases: tuple[str, ...]
    chunk_strategy: ChunkStrategy
    expected_currency: str | None = None
    expected_unit: str | None = None


def derive_targets(
    catalog: SourceMappingCatalog,
    taxonomy: FieldTaxonomyCatalog,
    *,
    priorities: tuple[str, ...] = ("P0", "P1"),
) -> list[LlmExtractionTarget]:
    """Build an extraction target per catalog field with pdf_aliases.

    Skips fields without pdf_aliases (no LLM-extractable signal).
    Chunk strategy is derived from alias count: 3+ aliases → alias_top_k
    (narrow), fewer → broad_keyword (wide).
    """
    targets: list[LlmExtractionTarget] = []
    selected = set(priorities)
    for field_id, entry in catalog.entries.items():
        if entry.priority not in selected:
            continue
        if not entry.pdf_aliases:
            continue
        tax = taxonomy.fields.get(field_id)
        description = tax.description if tax is not None else ""
        chunk_strategy: ChunkStrategy = (
            "alias_top_k" if len(entry.pdf_aliases) >= 3 else "broad_keyword"
        )
        targets.append(LlmExtractionTarget(
            field_id=field_id,
            field_description=description or field_id,
            statement_type=entry.statement_type,
            value_type=entry.value_type,
            aliases=entry.pdf_aliases,
            chunk_strategy=chunk_strategy,
        ))
    targets.sort(key=lambda t: t.field_id)
    return targets


def select_chunks(
    chunks: list[dict[str, object]],
    target: LlmExtractionTarget,
    *,
    top_k_standard: int = 8,
    broad_limit: int = 30,
) -> list[dict[str, object]]:
    """Select PDF chunks for an extraction target.

    alias_top_k: count alias occurrences (case-insensitive), keep top-k.
    broad_keyword: include any chunk where any alias-token appears, up to
    broad_limit. Tokens are derived by lowercasing aliases and splitting on
    whitespace, so 'research and development' tokens become {'research',
    'and', 'development'} — but stop-words are excluded.
    """
    if target.chunk_strategy == "alias_top_k":
        scored: list[tuple[int, dict[str, object]]] = []
        aliases_lower = [a.lower() for a in target.aliases]
        for chunk in chunks:
            text_lower = str(chunk.get("text", "") or "").lower()
            score = sum(text_lower.count(a) for a in aliases_lower)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored[:top_k_standard]]

    # broad_keyword
    stop_words = {"and", "or", "of", "the", "in", "for", "to", "a", "an"}
    tokens: set[str] = set()
    for alias in target.aliases:
        for tok in alias.lower().split():
            if tok and tok not in stop_words and len(tok) > 2:
                tokens.add(tok)
    if not tokens:
        return []
    selected: list[dict[str, object]] = []
    seen: set[str] = set()
    for chunk in chunks:
        text_lower = str(chunk.get("text", "") or "").lower()
        if any(tok in text_lower for tok in tokens):
            chunk_id = str(chunk.get("chunk_id") or chunk.get("block_id") or "")
            if chunk_id not in seen:
                selected.append(chunk)
                seen.add(chunk_id)
        if len(selected) >= broad_limit:
            break
    return selected
