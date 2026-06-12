"""LLM-assisted field extraction orchestrator.

Derives extraction targets from catalog metadata (no per-field code),
selects PDF chunks via alias scoring or broad keyword filter, and calls
the existing llm_field_extraction primitive.

Used by the `extract-llm` CLI to produce llm_evidence_supplement.json
artifacts that provider_baseline_replay can merge into source-first
exports for fields where source providers have no value.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from financial_report_llm_extractor.field_metadata import FieldTaxonomyCatalog
from financial_report_llm_extractor.llm_field_extraction import (
    FieldExtractionRequest,
    FieldExtractionResult,
    JsonClient,
    run_field_extraction,
)
from financial_report_llm_extractor.structured_sources.alias_matching import (
    PreparedText,
    match_alias,
    prepare_text,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
)


SCHEMA_VERSION = "llm-evidence-supplement-v1"


_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_whitespace(s: str) -> str:
    return _WHITESPACE_RE.sub(" ", s).strip()


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
    absence_means_zero: bool = False
    alias_normalization: bool = False
    # Taxonomy scope_expectation (e.g. "parent" for parent-company-only
    # fields); gates the absence_means_zero statement-section fallback.
    scope_expectation: str = "unknown"


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
            absence_means_zero=entry.absence_means_zero,
            alias_normalization=catalog.alias_normalization,
            scope_expectation=(
                tax.scope_expectation if tax is not None else "unknown"
            ),
        ))
    targets.sort(key=lambda t: t.field_id)
    return targets


def select_chunks(
    chunks: list[dict[str, object]],
    target: LlmExtractionTarget,
    *,
    top_k_standard: int = 8,
    broad_limit: int = 30,
    section_pages: Mapping[str, tuple[int, ...]] | None = None,
    prepared_cache: dict[str, PreparedText] | None = None,
) -> list[dict[str, object]]:
    """Select PDF chunks for an extraction target.

    alias_top_k: count alias occurrences (case-insensitive), keep top-k.
    With target.alias_normalization on, ranking becomes the spec PR-3 key
    (exact_score, in_statement_section, normalized_score) — normalized
    token-window matches let near-miss phrasings enter the candidate set,
    and section membership demotes prose pages. Flag off → identical to
    the historical exact-only behavior (key reduces to (exact, 0, 0) and
    stable sort preserves tie order).
    broad_keyword: unchanged (normalization out of scope per spec PR-3).
    """
    if target.chunk_strategy == "alias_top_k":
        # Normalize whitespace so multi-word aliases survive PDF-layout
        # line wrapping ("trade and notes\nreceivables" → "trade and notes
        # receivables").
        aliases_norm = [_normalize_whitespace(a.lower()) for a in target.aliases]
        use_norm = target.alias_normalization
        type_pages: tuple[int, ...] = ()
        if use_norm and section_pages is not None:
            type_pages = section_pages.get(target.statement_type, ())
        ranked: list[tuple[tuple[int, int, int], dict[str, object]]] = []
        for chunk in chunks:
            text = str(chunk.get("text", "") or "")
            text_norm = _normalize_whitespace(text.lower())
            exact = sum(text_norm.count(a) for a in aliases_norm)
            norm_score = 0
            if use_norm:
                cid = str(chunk.get("chunk_id") or chunk.get("block_id") or "")
                prepared: PreparedText | None = None
                if prepared_cache is not None and cid:
                    prepared = prepared_cache.get(cid)
                    if prepared is None:
                        prepared = prepare_text(text)
                        prepared_cache[cid] = prepared
                else:
                    prepared = prepare_text(text)
                for alias in target.aliases:
                    m = match_alias(alias, text, prepared=prepared)
                    if m is not None and m.kind == "normalized":
                        norm_score += m.count
            if exact > 0 or norm_score > 0:
                # Section bonus is block-record-scoped: aggregated records
                # carry page_start/page_end (no 'page') so _chunk_page is
                # None for them — exact-count dominance covers those.
                in_sec = 1 if (
                    use_norm and _chunk_page(chunk) in type_pages
                ) else 0
                ranked.append(((exact, in_sec, norm_score), chunk))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in ranked[:top_k_standard]]

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


# Bilingual (EN + 中文) anchor phrases that identify a statement section, used
# by the absence_means_zero fallback. Phrases are pre-lowercased; matching is
# case-insensitive and whitespace-normalized. Kept deliberately specific
# ("statement of cash flows", not bare "cash flow") so an incidental mention in
# prose does not masquerade as the section itself.
_STATEMENT_SECTION_ANCHORS: dict[str, tuple[str, ...]] = {
    "income_statement": (
        "income statement",
        "statement of profit or loss",
        "statement of comprehensive income",
        "综合损益表",
        "利润表",
        "损益表",
    ),
    "balance_sheet": (
        "balance sheet",
        "statement of financial position",
        "资产负债表",
        "财务状况表",
    ),
    "cash_flow": (
        "statement of cash flows",
        "cash flow statement",
        "financing activities",
        "现金流量表",
        "筹资活动",
        "融资活动",
    ),
}


def _chunk_page(chunk: dict[str, object]) -> int | None:
    try:
        return int(str(chunk.get("page")))
    except (TypeError, ValueError):
        return None


# Statements run a handful of pages; an anchored statement-table range longer
# than this is chunker noise (its loose detection can span MD&A sections) and
# must not flood the section map.
_MAX_ANCHORED_RANGE_PAGES = 8


def statement_section_pages(
    chunks: list[dict[str, object]],
) -> dict[str, tuple[int, ...]]:
    """Pages belonging to each statement section.

    Two passes. (1) Anchor pages: block-record text matching a statement
    anchor phrase (when no block records are present — synthetic tests —
    all given records are scanned). (2) Continuation pages: a
    statement-table chunk range whose START page is an anchor page of the
    same type extends the section across the whole range — multi-page
    statements rarely repeat the title on continuation pages. The
    start-page-anchored requirement filters the chunker's loose statement
    detection (it can label MD&A spans as statements), and ranges longer
    than _MAX_ANCHORED_RANGE_PAGES are ignored as noise.
    """
    blocks = [c for c in chunks if c.get("record_type") == "block"]
    out: dict[str, set[int]] = {k: set() for k in _STATEMENT_SECTION_ANCHORS}
    for chunk in blocks or chunks:
        text = " ".join(str(chunk.get("text", "") or "").lower().split())
        page = _chunk_page(chunk)
        if page is None:
            continue
        for stype, anchors in _STATEMENT_SECTION_ANCHORS.items():
            if any(" ".join(a.split()) in text for a in anchors):
                out[stype].add(page)

    for chunk in chunks:
        if chunk.get("record_type") != "chunk":
            continue
        kind = str(chunk.get("statement_kind") or "")
        if kind not in out:
            continue
        try:
            start = int(str(chunk.get("page_start")))
            end = int(str(chunk.get("page_end")))
        except (TypeError, ValueError):
            continue
        if (
            start in out[kind]
            and start <= end
            and end - start < _MAX_ANCHORED_RANGE_PAGES
        ):
            out[kind].update(range(start, end + 1))

    return {k: tuple(sorted(v)) for k, v in out.items()}


def select_statement_section_chunks(
    chunks: list[dict[str, object]],
    target: LlmExtractionTarget,
    *,
    top_k: int = 8,
) -> list[dict[str, object]]:
    """Fallback chunk selection for ``absence_means_zero`` fields.

    When a field's own aliases match no chunk, the line is plausibly a genuine
    zero rather than missing — but the LLM can only confirm that if it sees the
    enclosing statement section. This selects chunks belonging to
    ``target.statement_type``, preferring explicit ``statement_type`` chunk
    metadata when present, otherwise matching the section's anchor phrases in
    chunk text (bilingual EN/中文). Returns an empty list when the section is
    not represented at all, which the runner treats as a real not_found.
    """
    anchors = _STATEMENT_SECTION_ANCHORS.get(target.statement_type, ())
    if not anchors:
        return []
    anchors_norm = [_normalize_whitespace(a) for a in anchors]
    scored: list[tuple[int, dict[str, object]]] = []
    for chunk in chunks:
        st = chunk.get("statement_type")
        if st is not None and str(st) == target.statement_type:
            # Explicit metadata match dominates anchor-text scoring.
            scored.append((1_000_000, chunk))
            continue
        text_norm = _normalize_whitespace(
            str(chunk.get("text", "") or "").lower()
        )
        score = sum(text_norm.count(a) for a in anchors_norm)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:top_k]]


@dataclass(frozen=True)
class LlmExtractionRunResult:
    pdf_path: Path
    company_id: str
    chunk_count: int
    fields_attempted: tuple[str, ...]
    fields_present: tuple[str, ...]
    fields_not_found: tuple[str, ...]
    fields_failed: tuple[str, ...]
    artifact_path: Path
    llm_provider: str | None = None
    llm_model: str | None = None
    items: dict[str, FieldExtractionResult] = field(default_factory=dict)


def _normalized_text_offsets(text: str) -> tuple[str, list[int]]:
    """Lowercase + collapse whitespace runs, tracking raw offsets.

    Returns (normalized_text, offsets) where offsets[i] is the raw-text
    index that produced normalized character i — so a match found in the
    normalized text maps back to its raw position even when the alias is
    wrapped across a pdftotext line break ("one-off\\nitem"). Characters
    whose lowercase form changes length (e.g. "İ") are kept as-is to
    preserve the 1:1 offset map.
    """
    norm_chars: list[str] = []
    offsets: list[int] = []
    prev_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_space:
                continue
            norm_chars.append(" ")
            offsets.append(i)
            prev_space = True
        else:
            low = ch.lower()
            norm_chars.append(low if len(low) == 1 else ch)
            offsets.append(i)
            prev_space = False
    return "".join(norm_chars), offsets


_TRIM_MAX_SITES = 8
_TRIM_MAX_OFFSETS_PER_ALIAS = 16


def _trim_chunk_text(
    chunk: dict[str, object],
    max_chars: int,
    aliases: tuple[str, ...] = (),
) -> dict[str, object]:
    """Return a copy of chunk with text reduced to ~max_chars.

    Head-truncation alone systematically drops bottom-of-page content:
    the 00001 FY2025 one-off itemization sat at offset ~7.5k of a 7.9k
    page-text chunk, so the LLM never received it. When the text
    overflows, excerpt windows around alias matches instead; texts with
    no alias match keep the historical head-truncate behavior.

    Window construction (2026-06-12 review hardening):
    - alias matching is whitespace-normalized (same class of matching as
      select_chunks), so a line-wrapped alias still anchors a window;
    - match offsets are capped PER ALIAS, so one generic alias cannot
      exhaust the budget before a later, more specific alias is scanned;
    - when there are more sites than windows, sites are picked evenly
      across the sorted span (head AND tail), not earliest-first;
    - leftover budget after overlap-merging is redistributed by growing
      the merged windows, so clustered matches don't shrink the output
      far below max_chars;
    - a head slice is always prepended when no window covers the text
      start (period headers live there), and gaps carry explicit
      "[...skipped N chars...]" markers instead of a bare ellipsis.
    """
    text = str(chunk.get("text", "") or "")
    out = dict(chunk)
    if len(text) <= max_chars:
        out["text"] = text
        return out

    norm_text, norm_offsets = _normalized_text_offsets(text)
    raw_sites: list[int] = []
    for alias in aliases:
        needle = _normalize_whitespace(alias.lower())
        if not needle:
            continue
        start = 0
        found = 0
        while found < _TRIM_MAX_OFFSETS_PER_ALIAS:
            i = norm_text.find(needle, start)
            if i < 0:
                break
            raw_sites.append(norm_offsets[i])
            found += 1
            start = i + 1

    if not raw_sites:
        out["text"] = text[:max_chars] + "...[truncated]"
        return out

    sites = sorted(set(raw_sites))
    if len(sites) > _TRIM_MAX_SITES:
        # Even spread across the sorted sites keeps both head and tail
        # anchors — earliest-first selection re-created the motivating
        # bug whenever a generic alias was dense in the page's prose.
        step = (len(sites) - 1) / (_TRIM_MAX_SITES - 1)
        sites = sorted({sites[round(i * step)] for i in range(_TRIM_MAX_SITES)})

    head_reserve = 200 if sites[0] > 0 else 0
    budget = max(max_chars - head_reserve, 200)

    def _build_spans(per: int) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        for i in sites:
            s = max(0, i - per // 3)
            e = min(len(text), i + per)
            if spans and s <= spans[-1][1]:
                spans[-1] = (spans[-1][0], max(spans[-1][1], e))
            else:
                spans.append((s, e))
        return spans

    per = max(budget // len(sites), 200)
    spans = _build_spans(per)
    # Redistribute the budget freed by overlap-merging: grow the per-site
    # window until the merged spans use the budget (or stop shrinking the
    # gap). Loop is bounded — `per` grows geometrically.
    for _ in range(6):
        total = sum(e - s for s, e in spans)
        if total >= budget or total >= len(text):
            break
        grown = _build_spans(max(per + 1, per * budget // max(total, 1)))
        if sum(e - s for s, e in grown) <= total:
            break
        per = max(per + 1, per * budget // max(total, 1))
        spans = grown

    pieces: list[str] = []
    total = 0
    if head_reserve and spans[0][0] > 0:
        # Keep the top-of-page header (statement title / period labels) —
        # period misattribution is a known LLM failure mode when the
        # header is cut away from the matched rows.
        head_end = min(head_reserve, spans[0][0])
        pieces.append(text[:head_end])
        total += head_end
        last_end = head_end
    else:
        last_end = 0
    for s, e in spans:
        if s < last_end:
            s = last_end
        if s >= e:
            continue
        seg = text[s:e]
        if total + len(seg) > max_chars:
            seg = seg[: max(0, max_chars - total)]
        if not seg:
            break
        if s > last_end:
            pieces.append(f"\n[...skipped {s - last_end} chars...]\n")
        pieces.append(seg)
        total += len(seg)
        last_end = s + len(seg)
        if total >= max_chars:
            break
    if last_end < len(text):
        pieces.append(f"\n[...skipped {len(text) - last_end} chars...]")
    out["text"] = "".join(pieces)
    return out


def extract_for_chunks(
    *,
    chunks: list[dict[str, object]],
    catalog: SourceMappingCatalog,
    taxonomy: FieldTaxonomyCatalog,
    client: JsonClient,
    company_id: str,
    pdf_path: Path,
    out_dir: Path,
    priorities: tuple[str, ...] = ("P0", "P1"),
    fields: tuple[str, ...] | None = None,
    max_chars_per_chunk: int = 2000,
    confidence_threshold: float | None = None,
) -> LlmExtractionRunResult:
    """Run LLM extraction for all targets derived from catalog.

    fields parameter optionally restricts to a subset of field_ids. If a
    target's selected chunks are empty, the field is recorded as not_found
    without calling the LLM.

    confidence_threshold (Phase I-A.2 follow-up #4): if set, fields whose
    LLM-reported confidence is below the threshold are demoted from
    `present` to `extraction_failed` with a `low_confidence` error. Default
    None means no gating. The threshold should be calibrated against
    human-verified accuracy data (see VALIDATION.md follow-ups).
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = derive_targets(catalog, taxonomy, priorities=priorities)
    if fields is not None:
        wanted = set(fields)
        targets = [t for t in targets if t.field_id in wanted]

    items: dict[str, FieldExtractionResult] = {}
    fields_present: list[str] = []
    fields_not_found: list[str] = []
    fields_failed: list[str] = []

    section_pages: dict[str, tuple[int, ...]] | None = None
    prepared_cache: dict[str, PreparedText] | None = None
    if catalog.alias_normalization:
        # statement_section_pages filters block records internally and
        # extends with anchored statement-table ranges (continuation pages).
        section_pages = statement_section_pages(chunks)
        prepared_cache = {}

    for target in targets:
        field_dir = out_dir / target.field_id
        field_dir.mkdir(parents=True, exist_ok=True)

        selected = select_chunks(
            chunks, target,
            section_pages=section_pages,
            prepared_cache=prepared_cache,
        )

        if (
            not selected
            and target.absence_means_zero
            and target.scope_expectation != "parent"
        ):
            # The line (and its aliases) is absent. For absence_means_zero
            # fields that can be a genuine 0, fall back to the enclosing
            # statement section so the LLM's zero_inference can fire — an empty
            # alias match would otherwise bail to not_found before the request
            # is ever built.
            #
            # Parent-scope fields are excluded: section anchors key on
            # statement_type only, so this fallback would feed the
            # CONSOLIDATED statement to a parent-company-only field and
            # authorize a zero (or a consolidated value) from the wrong
            # scope. For those fields zero inference fires only when the
            # parent section itself was alias-retrieved.
            selected = select_statement_section_chunks(chunks, target)

        if not selected:
            item = FieldExtractionResult(
                field_id=target.field_id,
                status="not_found",
                reasoning="no chunks matched aliases for this field",
                raw_response={},
            )
            items[target.field_id] = item
            fields_not_found.append(target.field_id)
            continue

        trimmed = tuple(
            _trim_chunk_text(c, max_chars_per_chunk, aliases=target.aliases)
            for c in selected
        )
        request = FieldExtractionRequest(
            field_id=target.field_id,
            field_description=target.field_description,
            statement_type=target.statement_type,
            value_type=target.value_type,
            chunks=trimmed,
            expected_currency=target.expected_currency,
            expected_unit=target.expected_unit,
            absence_means_zero=target.absence_means_zero,
        )

        try:
            result = run_field_extraction(
                request, client, raw_response_dir=field_dir,
            )
        except Exception as exc:
            result = FieldExtractionResult(
                field_id=target.field_id,
                status="extraction_failed",
                errors=(f"runner caught exception: {exc}",),
                raw_response={},
            )

        # Confidence gating (Phase I-A.2 follow-up #4).
        # Use dataclasses.replace so future FieldExtractionResult fields are
        # automatically preserved without manual copy-paste.
        if (
            confidence_threshold is not None
            and result.status == "present"
            and result.confidence is not None
            and result.confidence < confidence_threshold
        ):
            import dataclasses
            result = dataclasses.replace(
                result,
                status="extraction_failed",
                errors=result.errors + (
                    f"low_confidence: {result.confidence} < threshold "
                    f"{confidence_threshold}",
                ),
            )

        items[target.field_id] = result
        if result.status == "present":
            fields_present.append(target.field_id)
        elif result.status == "not_found":
            fields_not_found.append(target.field_id)
        else:
            fields_failed.append(target.field_id)

    artifact_path = out_dir / "llm_evidence_supplement.json"
    return LlmExtractionRunResult(
        pdf_path=pdf_path,
        company_id=company_id,
        chunk_count=len(chunks),
        fields_attempted=tuple(t.field_id for t in targets),
        fields_present=tuple(fields_present),
        fields_not_found=tuple(fields_not_found),
        fields_failed=tuple(fields_failed),
        artifact_path=artifact_path,
        items=items,
    )


def write_llm_evidence_supplement(result: LlmExtractionRunResult) -> Path:
    """Write llm_evidence_supplement.json from run result.

    Schema:
    {
      "schema_version": "llm-evidence-supplement-v1",
      "company_id": str,
      "pdf_path": str,
      "llm_provider": str | null,
      "llm_model": str | null,
      "extracted_at": ISO8601 string,
      "summary": {fields_attempted, fields_present, fields_not_found,
                  fields_failed, chunk_count},
      "items": {field_id: {status, value, parsed_numeric_value, currency,
                           unit, page, statement_line, confidence, reasoning,
                           errors}}
    }
    """
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "company_id": result.company_id,
        "pdf_path": str(result.pdf_path),
        "llm_provider": result.llm_provider,
        "llm_model": result.llm_model,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "chunk_count": result.chunk_count,
            "fields_attempted": list(result.fields_attempted),
            "fields_present": list(result.fields_present),
            "fields_not_found": list(result.fields_not_found),
            "fields_failed": list(result.fields_failed),
        },
        "items": {
            fid: {
                "status": item.status,
                "value": item.value,
                "parsed_numeric_value": (
                    str(item.parsed_numeric_value)
                    if item.parsed_numeric_value is not None
                    else None
                ),
                "currency": item.currency,
                "unit": item.unit,
                "period": item.period,
                "page": item.page,
                "statement_line": item.statement_line,
                "confidence": item.confidence,
                "reasoning": item.reasoning,
                "errors": list(item.errors),
            }
            for fid, item in result.items.items()
        },
    }
    result.artifact_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result.artifact_path


def load_chunks_jsonl(path: Path) -> list[dict[str, object]]:
    """Read a chunks.jsonl file produced by the chunk CLI command."""
    chunks: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            chunks.append(json.loads(line))
    return chunks
