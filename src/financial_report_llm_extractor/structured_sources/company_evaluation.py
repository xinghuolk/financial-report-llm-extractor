"""Per-company evaluation: bucket classification + summary + markdown.

Builds CompanyEvaluation from SourceFirstExportResult + WarningClassificationResult
+ optional LLM supplement. Bucket cascade is a pure function over per-(company,
field) inputs; no global hardcoded field lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Mapping

from financial_report_llm_extractor.field_metadata import FieldTaxonomyCatalog
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
    SourceMappingEntry,
)
from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportItem,
    SourceFirstExportResult,
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
) -> CompanyEvaluation:
    """Aggregate per-field bucket classification into priority × bucket grid.

    Iterates over catalog.entries (the canonical denominator), looks up
    matching export.items + warning_classification.items, calls classify_field
    for each, accumulates totals.

    `supplement` parameter is currently informational (LLM merge already
    happens upstream via _merge_llm_evidence_supplement; the dict is reserved
    for future per-field LLM metadata that doesn't flow through export).
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

        fields.append(CompanyFieldEvaluation(
            field_id=field_id,
            bucket=bucket,
            selected_source=export_item.selected_source,
            value=export_item.value,
            currency=export_item.currency,
            unit=export_item.unit,
            reason=reason,
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
        value_str = str(f.value) if f.value is not None else ""
        lines.append(
            f"| {f.field_id} | {f.bucket} | {marker} | {value_str} | {reason} |"
        )
    return "\n".join(lines) + "\n"
