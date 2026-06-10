"""Pre-flight PDF alias audit (spec PR-1, component 2).

Zero-LLM diagnostic: simulates what the production retrieval would feed
the LLM (calls the REAL derive_targets / select_chunks /
select_statement_section_chunks — never reimplements selection) and adds
alias-level exact/normalized diagnostics over record_type=="block"
chunks only (chunks.jsonl stores each text 3 ways; blocks carry exact
pages and avoid double counting).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from financial_report_llm_extractor.field_metadata import FieldTaxonomyCatalog
from financial_report_llm_extractor.structured_sources.alias_matching import (
    PreparedText,
    _EDGE_PUNCT,
    match_alias,
    prepare_text,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
)
from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
    LlmExtractionTarget,
    _chunk_page,
    derive_targets,
    select_chunks,
    select_statement_section_chunks,
    statement_section_pages,
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
    company: str | None = None
    market: str | None = None
    year: int | None = None

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


def _chunk_id_of(chunk: dict[str, object]) -> str:
    return str(chunk.get("chunk_id") or chunk.get("block_id") or "")


def _audit_field(
    target: LlmExtractionTarget,
    prepared_blocks: list[tuple[dict[str, object], PreparedText]],
    all_chunks: list[dict[str, object]],
    section_pages: dict[str, tuple[int, ...]],
    prepared_cache: dict[str, PreparedText],
) -> FieldAuditResult:
    hits: list[AliasHit] = []
    pages_for_type = section_pages.get(target.statement_type)
    in_section_pages = pages_for_type if pages_for_type else None
    for alias in target.aliases:
        for chunk, ptext in prepared_blocks:
            m = match_alias(alias, str(chunk.get("text", "") or ""),
                            prepared=ptext)
            if m is None:
                continue
            page = _chunk_page(chunk)
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
        h.matched_text.strip(_EDGE_PUNCT).lower()
        for h in normalized
    ))

    selected = select_chunks(
        all_chunks, target,
        section_pages=section_pages,
        prepared_cache=prepared_cache,
    )
    via: Literal["alias_top_k", "broad_keyword", "section_fallback"]
    if not selected and target.absence_means_zero:
        selected = select_statement_section_chunks(all_chunks, target)
        via = "section_fallback"
    else:
        via = target.chunk_strategy
    selected_chunks = tuple(
        SelectedChunk(chunk_id=_chunk_id_of(c), page=_chunk_page(c), via=via)
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
    alias_normalization_override: bool | None = None,
    company: str | None = None,
    market: str | None = None,
    year: int | None = None,
) -> AuditReport:
    if alias_normalization_override is not None:
        catalog = replace(
            catalog, alias_normalization=alias_normalization_override,
        )
    blocks = [c for c in chunks if c.get("record_type") == "block"]
    prepared_blocks: list[tuple[dict[str, object], PreparedText]] = [
        (c, prepare_text(str(c.get("text", "") or ""))) for c in blocks
    ]
    section_pages = statement_section_pages(blocks)
    # Shared across fields so flag-on selection doesn't re-fold every chunk
    # per field; seeded with the block folds already computed above.
    prepared_cache: dict[str, PreparedText] = {
        _chunk_id_of(c): p for c, p in prepared_blocks if _chunk_id_of(c)
    }
    targets = derive_targets(catalog, taxonomy, priorities=priorities)
    fields = {
        t.field_id: _audit_field(
            t, prepared_blocks, chunks, section_pages, prepared_cache,
        )
        for t in targets
    }
    return AuditReport(
        pdf_path=str(pdf_path),
        catalog_version=catalog.version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        section_anchor_coverage=section_pages,
        fields=fields,
        company=company,
        market=market,
        year=year,
    )


def write_alias_audit(report: AuditReport, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    empty_anchor_types = sorted(
        k for k, v in report.section_anchor_coverage.items() if not v
    )
    payload = {
        "schema_version": "alias_audit_v1",
        "pdf_path": report.pdf_path,
        "company": report.company,
        "market": report.market,
        "year": report.year,
        "catalog_version": report.catalog_version,
        "generated_at": report.generated_at,
        "section_anchor_coverage": {
            k: list(v) for k, v in sorted(report.section_anchor_coverage.items())
        },
        "warnings": {
            # spec: every statement_type must resolve >=1 page, else the
            # absence_means_zero fallback is silently dead for this PDF
            "empty_anchor_statement_types": empty_anchor_types,
        },
        "fields": {
            fid: {
                "status": r.status,
                "selected_chunks": [
                    {"chunk_id": c.chunk_id, "page": c.page, "via": c.via}
                    for c in r.selected_chunks
                ],
                "hits": [
                    {"alias": h.alias, "kind": h.kind, "page": h.page,
                     "count": h.count,
                     "in_statement_section": h.in_statement_section,
                     "matched_text": h.matched_text}
                    for h in r.hits
                ],
                "suggested_aliases": list(r.suggested_aliases),
            }
            for fid, r in sorted(report.fields.items())
        },
        "summary": report.summary,
    }
    (out_dir / "alias_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# PDF Alias Audit", "",
        f"- PDF: `{report.pdf_path}`",
        f"- Catalog: {report.catalog_version}",
        f"- Summary: {report.summary}",
    ]
    if empty_anchor_types:
        lines.append(
            f"- ⚠️ No anchor pages found for: {', '.join(empty_anchor_types)}"
        )
    lines += [
        "",
        "| Field | Status | Hits (alias@page) | Suggested |",
        "|---|---|---|---|",
    ]
    for fid, r in sorted(report.fields.items()):
        escaped_pipe = "\\|"
        hits = "; ".join(
            f"{h.alias.replace('|', escaped_pipe)}@p{h.page}[{h.kind}]"
            for h in r.hits
        )
        sugg = "; ".join(a.replace("|", escaped_pipe) for a in r.suggested_aliases)
        lines.append(f"| `{fid}` | {r.status} | {hits} | {sugg} |")
    (out_dir / "alias_audit.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8",
    )


def emit_catalog_patch(report: AuditReport, out_dir: Path) -> None:
    adds = {
        fid: list(r.suggested_aliases)
        for fid, r in sorted(report.fields.items())
        if r.suggested_aliases
    }
    payload = {
        "schema_version": "alias_catalog_patch_v1",
        "note": "review-gated suggestions; apply manually to "
                "field_catalog/turtle_v015_source_mapping_minimal.json",
        "add_pdf_aliases": adds,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "catalog_patch.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
