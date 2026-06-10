"""Pre-flight PDF alias audit (spec PR-1, component 2).

Zero-LLM diagnostic: simulates what the production retrieval would feed
the LLM (calls the REAL derive_targets / select_chunks /
select_statement_section_chunks — never reimplements selection) and adds
alias-level exact/normalized diagnostics over record_type=="block"
chunks only (chunks.jsonl stores each text 3 ways; blocks carry exact
pages and avoid double counting).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

from financial_report_llm_extractor.field_metadata import FieldTaxonomyCatalog
from financial_report_llm_extractor.structured_sources.alias_matching import (
    match_alias,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
)
from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
    _STATEMENT_SECTION_ANCHORS,  # noqa: PLC2701
    LlmExtractionTarget,
    derive_targets,
    select_chunks,
    select_statement_section_chunks,
)

FieldAuditStatus = Literal[
    "exact_hit", "prose_only_hit", "normalized_only_hit", "no_hit"
]


@dataclass(frozen=True)
class AliasHit:
    alias: str
    kind: Literal["exact", "normalized"]
    page: int | None
    count: int
    in_statement_section: bool | None
    matched_text: str


@dataclass(frozen=True)
class SelectedChunk:
    chunk_id: str
    page: int | None
    via: Literal["alias_top_k", "broad_keyword", "section_fallback"]


@dataclass(frozen=True)
class FieldAuditResult:
    field_id: str
    status: FieldAuditStatus
    hits: tuple[AliasHit, ...] = ()
    selected_chunks: tuple[SelectedChunk, ...] = ()
    suggested_aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditReport:
    pdf_path: str
    catalog_version: str
    generated_at: str
    section_anchor_coverage: dict[str, tuple[int, ...]]
    fields: dict[str, FieldAuditResult] = field(default_factory=dict)

    @property
    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {
            "exact_hit": 0,
            "prose_only_hit": 0,
            "normalized_only_hit": 0,
            "no_hit": 0,
        }
        for r in self.fields.values():
            out[r.status] += 1
        return out


def _page_of(chunk: dict[str, object]) -> int | None:
    raw = chunk.get("page")
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return None


def _chunk_id_of(chunk: dict[str, object]) -> str:
    return str(chunk.get("chunk_id") or chunk.get("block_id") or "")


def _section_pages(
    blocks: list[dict[str, object]],
) -> dict[str, tuple[int, ...]]:
    """Pages whose block text matches a statement-type anchor phrase."""
    out: dict[str, set[int]] = {k: set() for k in _STATEMENT_SECTION_ANCHORS}
    for chunk in blocks:
        text = " ".join(str(chunk.get("text", "") or "").lower().split())
        page = _page_of(chunk)
        if page is None:
            continue
        for stype, anchors in _STATEMENT_SECTION_ANCHORS.items():
            if any(" ".join(a.split()) in text for a in anchors):
                out[stype].add(page)
    return {k: tuple(sorted(v)) for k, v in out.items()}


_SUGGESTION_STRIP = ",.;:"


def _audit_field(
    target: LlmExtractionTarget,
    blocks: list[dict[str, object]],
    all_chunks: list[dict[str, object]],
    section_pages: dict[str, tuple[int, ...]],
) -> FieldAuditResult:
    hits: list[AliasHit] = []
    in_section_pages = section_pages.get(target.statement_type)
    for alias in target.aliases:
        for chunk in blocks:
            m = match_alias(alias, str(chunk.get("text", "") or ""))
            if m is None:
                continue
            page = _page_of(chunk)
            in_section: bool | None = None
            if in_section_pages is not None:
                in_section = page in in_section_pages
            hits.append(AliasHit(
                alias=alias, kind=m.kind, page=page, count=m.count,
                in_statement_section=in_section,
                matched_text=m.matched_text,
            ))

    exact = [h for h in hits if h.kind == "exact"]
    normalized = [h for h in hits if h.kind == "normalized"]
    status: FieldAuditStatus
    if exact and any(h.in_statement_section in (True, None) for h in exact):
        status = "exact_hit"
    elif exact:
        status = "prose_only_hit"
    elif normalized:
        status = "normalized_only_hit"
    else:
        status = "no_hit"

    suggested = tuple(dict.fromkeys(
        h.matched_text.strip(_SUGGESTION_STRIP).lower()
        for h in normalized
    ))

    selected = select_chunks(all_chunks, target)
    via: Literal["alias_top_k", "broad_keyword", "section_fallback"] = cast(
        Literal["alias_top_k", "broad_keyword", "section_fallback"],
        target.chunk_strategy,
    )
    if not selected and target.absence_means_zero:
        selected = select_statement_section_chunks(all_chunks, target)
        via = "section_fallback"
    selected_chunks = tuple(
        SelectedChunk(chunk_id=_chunk_id_of(c), page=_page_of(c), via=via)
        for c in selected
    )

    return FieldAuditResult(
        field_id=target.field_id, status=status, hits=tuple(hits),
        selected_chunks=selected_chunks, suggested_aliases=suggested,
    )


def audit_chunks(
    *,
    chunks: list[dict[str, object]],
    catalog: SourceMappingCatalog,
    taxonomy: FieldTaxonomyCatalog,
    priorities: tuple[str, ...],
    pdf_path: Path,
) -> AuditReport:
    blocks = [c for c in chunks if c.get("record_type") == "block"]
    section_pages = _section_pages(blocks)
    targets = derive_targets(catalog, taxonomy, priorities=priorities)
    fields = {
        t.field_id: _audit_field(t, blocks, chunks, section_pages)
        for t in targets
    }
    return AuditReport(
        pdf_path=str(pdf_path),
        catalog_version=catalog.version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        section_anchor_coverage=section_pages,
        fields=fields,
    )
