"""Per-company evaluation: bucket classification + summary + markdown.

Builds CompanyEvaluation from SourceFirstExportResult + WarningClassificationResult
+ optional LLM supplement. Bucket cascade is a pure function over per-(company,
field) inputs; no global hardcoded field lists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal, Mapping

from financial_report_llm_extractor.field_metadata import (
    FieldTaxonomyCatalog,
    load_field_taxonomy,
)
from financial_report_llm_extractor.llm_field_extraction import JsonClient
from financial_report_llm_extractor.structured_sources.artifacts import (
    read_source_inventory,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
    SourceMappingEntry,
    load_source_mapping_catalog,
)
from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportItem,
    SourceFirstExportResult,
)
from financial_report_llm_extractor.structured_sources.mapping import (
    TurtleMappingResult,
)
from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
    evaluate_source_first_slice,
)
from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
    PeriodSpec,
)
from financial_report_llm_extractor.structured_sources.warning_classification import (
    WarningCategory,
    WarningClassificationItem,
    WarningClassificationResult,
)


BucketName = Literal[
    "clean_present",
    "unresolved_conflict",
    "llm_supplement_present",
    "terminal_unverified",
    "not_in_scope",
    "source_unavailable",
]


_TERMINAL_UNVERIFIED_CATEGORIES: frozenset[WarningCategory] = frozenset({
    "yahoo_definition_unverified",
    "pdf_required",
    "pdf_verification_required",
    "mapping_expansion_required",
})


_BENIGN_WARNING_CATEGORIES: frozenset[WarningCategory] = frozenset({
    "yahoo_pdf_verified",
    "source_policy_resolvable",
})


def classify_field(
    *,
    export_item: SourceFirstExportItem,
    warning_item: WarningClassificationItem | None,
    mapping_entry: SourceMappingEntry,
    pdf_provided: bool,
) -> tuple[BucketName, str | None]:
    """Bucket cascade. First match wins. See spec §桶分类."""
    # Bucket 1: explicit conflict from policy report.
    if export_item.conflict_classifications:
        return ("unresolved_conflict", ",".join(export_item.conflict_classifications))

    # Bucket 2: LLM supplement merged in (provider_baseline_replay sets
    # selected_source="llm" only for supplement-merged fields).
    if export_item.status == "present" and export_item.selected_source == "llm":
        return ("llm_supplement_present", None)

    # Bucket 3: Clean present from a real source.
    if export_item.status == "present" and (
        warning_item is None
        or warning_item.category in _BENIGN_WARNING_CATEGORIES
    ):
        return ("clean_present", None)

    # Bucket 4: Terminal unverified per warning_classification.
    if (
        warning_item is not None
        and warning_item.category in _TERMINAL_UNVERIFIED_CATEGORIES
    ):
        return ("terminal_unverified", warning_item.category)

    # Bucket 5: pdf_only catalog field, no PDF given → never attempted.
    if mapping_entry.source_mode == "pdf_only" and not pdf_provided:
        return ("not_in_scope", "pdf_only_without_pdf")

    # Bucket 6: source_unavailable (warning category or fallthrough).
    reason = warning_item.category if warning_item is not None else "missing"
    return ("source_unavailable", reason)


@dataclass(frozen=True)
class CompanyFieldEvaluation:
    field_id: str
    bucket: BucketName
    selected_source: str | None
    value: Decimal | None
    currency: str | None
    unit: str | None
    reason: str | None
    # Phase EC Tier 1: per-source candidate values for review of conflicts.
    # Tuple of (source_name, normalized_value_str). Populated for non-clean
    # rows where mapping_result was provided to build_company_evaluation.
    candidate_values: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CompanyEvaluation:
    company: str
    period: PeriodSpec
    market: str
    generated_at: str
    fields: tuple[CompanyFieldEvaluation, ...]
    by_bucket: Mapping[BucketName, int]
    by_priority: Mapping[str, Mapping[BucketName, int]]


_ALL_BUCKETS: tuple[BucketName, ...] = (
    "clean_present",
    "unresolved_conflict",
    "llm_supplement_present",
    "terminal_unverified",
    "not_in_scope",
    "source_unavailable",
)


def build_company_evaluation(
    *,
    company: str,
    period: PeriodSpec,
    market: str,
    export: SourceFirstExportResult,
    warning_classification: WarningClassificationResult,
    supplement: dict[str, object] | None,
    catalog: SourceMappingCatalog,
    taxonomy: FieldTaxonomyCatalog,
    pdf_provided: bool,
    mapping: TurtleMappingResult | None = None,
) -> CompanyEvaluation:
    """Aggregate per-field bucket classification into priority × bucket grid.

    Iterates over catalog.entries (the canonical denominator), looks up
    matching export.items + warning_classification.items, calls classify_field
    for each, accumulates totals.

    `supplement` parameter is currently informational (LLM merge already
    happens upstream via _merge_llm_evidence_supplement; the dict is reserved
    for future per-field LLM metadata that doesn't flow through export).

    `mapping` (optional, Phase EC Tier 1): if provided, populate
    CompanyFieldEvaluation.candidate_values for non-clean rows so the
    markdown renderer can show per-source values inline (e.g. for
    unresolved_conflict triage).
    """
    export_by_id = export.items
    warnings_by_id = warning_classification.items

    fields: list[CompanyFieldEvaluation] = []
    by_bucket: dict[BucketName, int] = {b: 0 for b in _ALL_BUCKETS}
    by_priority: dict[str, dict[BucketName, int]] = {}

    for field_id, mapping_entry in catalog.entries.items():
        export_item = export_by_id.get(field_id)
        if export_item is None:
            export_item = _missing_export_item(field_id)
        warning_item = warnings_by_id.get(field_id)

        bucket, reason = classify_field(
            export_item=export_item,
            warning_item=warning_item,
            mapping_entry=mapping_entry,
            pdf_provided=pdf_provided,
        )

        candidate_values = _collect_candidate_values(
            field_id, bucket, mapping,
        )

        fields.append(CompanyFieldEvaluation(
            field_id=field_id,
            bucket=bucket,
            selected_source=export_item.selected_source,
            value=export_item.value,
            currency=export_item.currency,
            unit=export_item.unit,
            reason=reason,
            candidate_values=candidate_values,
        ))
        by_bucket[bucket] += 1
        priority = mapping_entry.priority
        by_priority.setdefault(priority, {b: 0 for b in _ALL_BUCKETS})
        by_priority[priority][bucket] += 1

    return CompanyEvaluation(
        company=company,
        period=period,
        market=market,
        generated_at=datetime.now(timezone.utc).isoformat(),
        fields=tuple(fields),
        by_bucket=by_bucket,
        by_priority=by_priority,
    )


def _missing_export_item(field_id: str) -> SourceFirstExportItem:
    return SourceFirstExportItem(
        field_id=field_id,
        status="missing",
        selected_source=None,
        value=None,
        currency="unknown",
        unit=None,
        conflict_classifications=(),
        review_notes=(),
    )


def _collect_candidate_values(
    field_id: str,
    bucket: BucketName,
    mapping: TurtleMappingResult | None,
) -> tuple[tuple[str, str], ...]:
    """Pull per-source candidate normalized values from mapping for non-clean
    rows so the markdown renderer can show 'akshare:170.9B / yahoo:174.1B'
    inline. Returns empty tuple if mapping not provided OR field has no
    multi-source candidates OR field is clean (single selected source).
    """
    if mapping is None:
        return ()
    # Only emit candidates for buckets where the user benefits from triage.
    if bucket not in {"unresolved_conflict", "terminal_unverified", "source_unavailable"}:
        return ()
    field = mapping.fields.get(field_id)
    if field is None:
        return ()
    out: list[tuple[str, str]] = []
    for c in field.candidates:
        if c.normalized_value is None:
            continue
        out.append((c.source, _format_money_short(c.normalized_value)))
    return tuple(out)


def _format_money_short(value: Decimal) -> str:
    """Format Decimal compactly: 170,899,152,276.34 → '170.9B'."""
    f = float(value)
    abs_f = abs(f)
    if abs_f >= 1e9:
        return f"{f / 1e9:.2f}B"
    if abs_f >= 1e6:
        return f"{f / 1e6:.2f}M"
    if abs_f >= 1e3:
        return f"{f / 1e3:.2f}K"
    return f"{f:.2f}"


def render_evaluation_markdown(evaluation: CompanyEvaluation) -> str:
    """Render priority × bucket grid + per-field detail. No '% clean' framing."""
    lines: list[str] = []
    lines.append(f"# Company Evaluation: {evaluation.company}")
    lines.append("")
    lines.append(f"- Period end: {evaluation.period.period_end.isoformat()}")
    lines.append(f"- Report type: {evaluation.period.report_type}")
    lines.append(f"- Market: {evaluation.market}")
    lines.append(f"- Generated at: {evaluation.generated_at}")
    lines.append("")
    lines.append("## Coverage by priority × bucket")
    lines.append("")

    header = "| Priority | " + " | ".join(_ALL_BUCKETS) + " |"
    sep = "|----------|" + "|".join(["---"] * len(_ALL_BUCKETS)) + "|"
    lines.append(header)
    lines.append(sep)
    for priority in sorted(evaluation.by_priority.keys()):
        row = evaluation.by_priority[priority]
        cells = " | ".join(str(row[b]) for b in _ALL_BUCKETS)
        lines.append(f"| {priority} | {cells} |")
    lines.append("")

    lines.append("## Per-field detail")
    lines.append("")
    lines.append("| Field | Bucket | Source | Value | Reason |")
    lines.append("|-------|--------|--------|-------|--------|")
    for f in evaluation.fields:
        marker = "**llm**" if f.selected_source == "llm" else (f.selected_source or "")
        reason = f.reason or ""
        if f.value is not None:
            value_str = str(f.value)
        elif f.candidate_values:
            # Phase EC Tier 1: show per-source candidates inline for triage.
            value_str = " / ".join(f"{src}:{val}" for src, val in f.candidate_values)
        else:
            value_str = ""
        lines.append(
            f"| {f.field_id} | {f.bucket} | {marker} | {value_str} | {reason} |"
        )
    return "\n".join(lines) + "\n"


def run_company_evaluation(
    *,
    company: str,
    period: PeriodSpec,
    market: str,
    inventory_path: Path,
    inventory_summary_path: Path,
    catalog_path: Path,
    taxonomy_path: Path,
    pdf_path: Path | None,
    llm_config_path: Path | None,
    priorities: tuple[str, ...],
    out_dir: Path,
    json_client: JsonClient | None = None,
) -> CompanyEvaluation:
    """End-to-end: replay → optional LLM supplement → classify → write artifacts.

    Reads the cached inventory from inventory_path, runs the source-first
    slice (mapping → policy_report → export → warning_classification), and
    optionally invokes the LLM supplement step when PDF + llm-config are set.
    Writes evaluation.json + evaluation.md to out_dir.

    inventory_summary_path is currently informational (preserved for parity
    with the fetch step's output layout); future versions may consume it.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    catalog = load_source_mapping_catalog(catalog_path, priorities=priorities)
    taxonomy = load_field_taxonomy(taxonomy_path)

    records = read_source_inventory(inventory_path)

    pdf_provided = pdf_path is not None
    if pdf_provided and llm_config_path is not None:
        assert pdf_path is not None  # narrow for mypy
        _run_llm_supplement_step(
            company=company,
            pdf_path=pdf_path,
            llm_config_path=llm_config_path,
            catalog=catalog,
            taxonomy=taxonomy,
            priorities=priorities,
            out_dir=out_dir,
            json_client=json_client,
        )

    slice_result = evaluate_source_first_slice(
        out_dir,
        catalog=catalog,
        taxonomy=taxonomy,
        records=records,
        company_id=company,
        market=market,
        hk_yahoo_trust_policy=None,
        provider_semantics_catalog=None,
        # Forward explicit supplement path so the merge fires regardless of
        # out_dir name. _run_llm_supplement_step (above) wrote the file at
        # this exact path when PDF + llm-config were provided. The legacy
        # dir-name gate (combined-slice layout) doesn't apply to the
        # orchestrator's flat out_dir layout.
        llm_supplement_path=(
            (out_dir / "llm_evidence_supplement.json")
            if pdf_provided and llm_config_path is not None
            else None
        ),
    )
    export = slice_result["export_object"]
    warning_classification = slice_result["warning_classification_object"]
    mapping = slice_result.get("mapping_object")

    evaluation = build_company_evaluation(
        company=company,
        period=period,
        market=market,
        export=export,
        warning_classification=warning_classification,
        supplement=None,
        catalog=catalog,
        taxonomy=taxonomy,
        pdf_provided=pdf_provided,
        mapping=mapping,
    )

    (out_dir / "evaluation.json").write_text(
        json.dumps(
            _evaluation_to_dict(evaluation),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (out_dir / "evaluation.md").write_text(
        render_evaluation_markdown(evaluation), encoding="utf-8",
    )
    return evaluation


def _run_llm_supplement_step(
    *,
    company: str,
    pdf_path: Path,
    llm_config_path: Path,
    catalog: SourceMappingCatalog,
    taxonomy: FieldTaxonomyCatalog,
    priorities: tuple[str, ...],
    out_dir: Path,
    json_client: JsonClient | None,
) -> None:
    """Mirror llm_extraction_batch._process_one_company minus batching.

    extract_for_chunks signature is (chunks, catalog, taxonomy, client,
    company_id, pdf_path, out_dir, priorities) — derive_targets happens
    inside extract_for_chunks; do NOT call it manually here.
    """
    from financial_report_llm_extractor.chunking import build_chunk_store
    from financial_report_llm_extractor.ingestion import ingest_pdf
    from financial_report_llm_extractor.llm_transport import (
        LlmTransportConfig,
        create_llm_client,
    )
    from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
        extract_for_chunks,
        load_chunks_jsonl,
        write_llm_evidence_supplement,
    )

    ingest_dir = out_dir / "ingest"
    chunks_path = ingest_dir / "chunks.jsonl"
    if not chunks_path.exists():
        ingest_dir.mkdir(parents=True, exist_ok=True)
        ingest_result = ingest_pdf(pdf_path, ingest_dir)
        build_chunk_store(
            ingest_result.pages_path,
            ingest_result.metadata_path,
            chunks_path=chunks_path,
        )
    chunks = load_chunks_jsonl(chunks_path)

    if json_client is None:
        config = LlmTransportConfig.from_json(llm_config_path)
        json_client = create_llm_client(config)

    result = extract_for_chunks(
        chunks=chunks,
        catalog=catalog,
        taxonomy=taxonomy,
        client=json_client,
        company_id=company,
        pdf_path=pdf_path,
        out_dir=out_dir,
        priorities=priorities,
    )
    write_llm_evidence_supplement(result)


def _evaluation_to_dict(ev: CompanyEvaluation) -> dict[str, object]:
    return {
        "schema_version": "company-evaluation-v1",
        "company": ev.company,
        "period_end": ev.period.period_end.isoformat(),
        "report_type": ev.period.report_type,
        "market": ev.market,
        "generated_at": ev.generated_at,
        "summary": {
            "total_fields": len(ev.fields),
            "by_bucket": dict(ev.by_bucket),
            "by_priority": {p: dict(b) for p, b in ev.by_priority.items()},
        },
        "fields": {
            f.field_id: {
                "bucket": f.bucket,
                "selected_source": f.selected_source,
                "value": str(f.value) if f.value is not None else None,
                "currency": f.currency,
                "unit": f.unit,
                "reason": f.reason,
            }
            for f in ev.fields
        },
    }
