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
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
)


SCHEMA_VERSION = "llm-evidence-supplement-v1"


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
    items: dict[str, FieldExtractionResult] = field(default_factory=dict)


def _trim_chunk_text(chunk: dict[str, object], max_chars: int) -> dict[str, object]:
    """Return a copy of chunk with text truncated to max_chars."""
    text = str(chunk.get("text", "") or "")
    if len(text) > max_chars:
        text = text[:max_chars] + "...[truncated]"
    out = dict(chunk)
    out["text"] = text
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
) -> LlmExtractionRunResult:
    """Run LLM extraction for all targets derived from catalog.

    fields parameter optionally restricts to a subset of field_ids. If a
    target's selected chunks are empty, the field is recorded as not_found
    without calling the LLM.
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

    for target in targets:
        field_dir = out_dir / target.field_id
        field_dir.mkdir(parents=True, exist_ok=True)

        selected = select_chunks(chunks, target)

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
            _trim_chunk_text(c, max_chars_per_chunk) for c in selected
        )
        request = FieldExtractionRequest(
            field_id=target.field_id,
            field_description=target.field_description,
            statement_type=target.statement_type,
            value_type=target.value_type,
            chunks=trimmed,
            expected_currency=target.expected_currency,
            expected_unit=target.expected_unit,
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
