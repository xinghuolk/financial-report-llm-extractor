"""Per-company evaluation: bucket classification + summary + markdown.

Builds CompanyEvaluation from SourceFirstExportResult + WarningClassificationResult
+ optional LLM supplement. Bucket cascade is a pure function over per-(company,
field) inputs; no global hardcoded field lists.
"""

from __future__ import annotations

from typing import Literal

from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingEntry,
)
from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportItem,
)
from financial_report_llm_extractor.structured_sources.warning_classification import (
    WarningCategory,
    WarningClassificationItem,
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
