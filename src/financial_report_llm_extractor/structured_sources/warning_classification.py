"""Actionable warning classification for source-first replay outputs."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportItem,
    SourceFirstExportResult,
)
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    FieldCandidateReportEntry,
)
from financial_report_llm_extractor.structured_sources.hk_yahoo_trust_policy import (
    HkYahooTrustPolicy,
)


WarningCategory = Literal[
    "yahoo_pdf_verified",
    "yahoo_definition_unverified",
    "pdf_required",
    "source_policy_resolvable",
    "pdf_verification_required",
    "mapping_expansion_required",
    "source_unavailable",
]

ALL_WARNING_CATEGORIES: tuple[WarningCategory, ...] = (
    "yahoo_pdf_verified",
    "yahoo_definition_unverified",
    "pdf_required",
    "source_policy_resolvable",
    "pdf_verification_required",
    "mapping_expansion_required",
    "source_unavailable",
)

PDF_REASON_NOTES = {
    "fx_like_ratio",
    "metadata_currency_suspected",
    "semantic_mismatch",
    "normalized_value_conflict",
    "single_source_unverified",
}

SOURCE_POLICY_REASON_NOTES = {
    "currency_metadata_required",
    "currency_as_unit",
    "statement_metadata_unproven",
}


@dataclass(frozen=True)
class WarningClassificationItem:
    field_id: str
    category: WarningCategory
    status: str
    reasons: tuple[str, ...]
    review_notes: tuple[str, ...]
    warnings: tuple[str, ...]
    selected_source: str | None
    candidate_sources: tuple[str, ...]
    verification_required: bool

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        payload["review_notes"] = list(self.review_notes)
        payload["warnings"] = list(self.warnings)
        payload["candidate_sources"] = list(self.candidate_sources)
        return payload


@dataclass(frozen=True)
class WarningClassificationResult:
    items: dict[str, WarningClassificationItem]

    @property
    def counts_by_category(self) -> dict[str, int]:
        counts = Counter(item.category for item in self.items.values())
        return {category: counts[category] for category in ALL_WARNING_CATEGORIES}

    @property
    def fields_by_category(self) -> dict[str, list[str]]:
        return {
            category: sorted(
                field_id
                for field_id, item in self.items.items()
                if item.category == category
            )
            for category in ALL_WARNING_CATEGORIES
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "counts_by_category": self.counts_by_category,
            "fields_by_category": self.fields_by_category,
            "items": {
                field_id: self.items[field_id].to_dict()
                for field_id in sorted(self.items)
            },
        }


def build_warning_classification(
    export: SourceFirstExportResult,
    *,
    candidate_entries: dict[str, FieldCandidateReportEntry],
    market: str | None = None,
    hk_yahoo_trust_policy: HkYahooTrustPolicy | None = None,
) -> WarningClassificationResult:
    items = {
        field_id: _classify_item(
            field_id,
            item,
            candidate_entries.get(field_id),
            market=market,
            hk_yahoo_trust_policy=hk_yahoo_trust_policy,
        )
        for field_id, item in export.items.items()
        if not _is_clean_present(
            field_id,
            item,
            market=market,
            hk_yahoo_trust_policy=hk_yahoo_trust_policy,
        )
    }
    return WarningClassificationResult(items=items)


def write_warning_classification_artifacts(
    result: WarningClassificationResult,
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "warning_classification.json"
    markdown_path = output_dir / "warning_classification.md"
    payload = result.to_dict()
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def _classify_item(
    field_id: str,
    item: SourceFirstExportItem,
    candidate_entry: FieldCandidateReportEntry | None,
    *,
    market: str | None,
    hk_yahoo_trust_policy: HkYahooTrustPolicy | None,
) -> WarningClassificationItem:
    candidate_sources = _candidate_sources(candidate_entry)
    reasons = _reasons(item=item, candidate_entry=candidate_entry)
    category = _category_for_item(
        field_id=field_id,
        item=item,
        candidate_entry=candidate_entry,
        reasons=reasons,
        market=market,
        hk_yahoo_trust_policy=hk_yahoo_trust_policy,
    )
    return WarningClassificationItem(
        field_id=field_id,
        category=category,
        status=item.status,
        reasons=reasons,
        review_notes=item.review_notes,
        warnings=item.warnings,
        selected_source=item.selected_source,
        candidate_sources=candidate_sources,
        verification_required=item.verification_required,
    )


def _category_for_item(
    *,
    field_id: str,
    item: SourceFirstExportItem,
    candidate_entry: FieldCandidateReportEntry | None,
    reasons: tuple[str, ...],
    market: str | None,
    hk_yahoo_trust_policy: HkYahooTrustPolicy | None,
) -> WarningCategory:
    if item.status == "missing":
        return (
            "mapping_expansion_required"
            if _has_provider_candidates(candidate_entry)
            else "source_unavailable"
        )
    hk_yahoo_category = _hk_yahoo_category(
        field_id=field_id,
        item=item,
        market=market,
        hk_yahoo_trust_policy=hk_yahoo_trust_policy,
    )
    if hk_yahoo_category is not None:
        return hk_yahoo_category
    if _requires_pdf_verification(item, reasons):
        return "pdf_verification_required"
    if SOURCE_POLICY_REASON_NOTES.intersection(reasons):
        return "source_policy_resolvable"
    return "source_policy_resolvable"


def _hk_yahoo_category(
    *,
    field_id: str,
    item: SourceFirstExportItem,
    market: str | None,
    hk_yahoo_trust_policy: HkYahooTrustPolicy | None,
) -> WarningCategory | None:
    if not _is_hk_yahoo_policy_context(
        market=market,
        hk_yahoo_trust_policy=hk_yahoo_trust_policy,
    ):
        return None
    assert hk_yahoo_trust_policy is not None
    if item.selected_source != "yahoo":
        return None
    rule = hk_yahoo_trust_policy.rule_for_field(field_id)
    if rule is not None:
        if rule.classification == "yahoo_pdf_verified":
            return "yahoo_pdf_verified"
        if rule.classification == "yahoo_definition_unverified":
            return "yahoo_definition_unverified"
    if item.status in {"present", "ambiguous", "conflict", "needs_pdf_evidence"}:
        return "pdf_required"
    return None


def _is_hk_yahoo_policy_context(
    *,
    market: str | None,
    hk_yahoo_trust_policy: HkYahooTrustPolicy | None,
) -> bool:
    return (
        hk_yahoo_trust_policy is not None
        and market is not None
        and market.upper() == "HK"
        and hk_yahoo_trust_policy.market == "HK"
        and hk_yahoo_trust_policy.provider == "yahoo"
    )


def _requires_pdf_verification(
    item: SourceFirstExportItem,
    reasons: tuple[str, ...],
) -> bool:
    return (
        item.status == "needs_pdf_evidence"
        or item.verification_required
        or item.reconciliation_status == "conflict"
        or "reconciliation_conflict" in reasons
        or bool(PDF_REASON_NOTES.intersection(reasons))
    )


def _reasons(
    *,
    item: SourceFirstExportItem,
    candidate_entry: FieldCandidateReportEntry | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    reasons.extend(item.review_notes)
    reasons.extend(item.conflict_classifications)
    if item.reconciliation_status == "conflict":
        reasons.append("reconciliation_conflict")
    if item.verification_required:
        reasons.append("verification_required")
    if item.status == "missing":
        reasons.append(
            "provider_candidates_present"
            if _has_provider_candidates(candidate_entry)
            else "provider_candidates_absent"
        )
    if item.warnings:
        reasons.extend(f"warning:{warning}" for warning in item.warnings)
    return tuple(dict.fromkeys(reasons))


def _candidate_sources(
    candidate_entry: FieldCandidateReportEntry | None,
) -> tuple[str, ...]:
    if candidate_entry is None:
        return ()
    return tuple(sorted(candidate_entry.providers))


def _has_provider_candidates(candidate_entry: FieldCandidateReportEntry | None) -> bool:
    return bool(candidate_entry is not None and candidate_entry.providers)


def _is_clean_present(
    field_id: str,
    item: SourceFirstExportItem,
    *,
    market: str | None,
    hk_yahoo_trust_policy: HkYahooTrustPolicy | None,
) -> bool:
    if (
        _is_hk_yahoo_policy_context(
            market=market,
            hk_yahoo_trust_policy=hk_yahoo_trust_policy,
        )
        and item.selected_source == "yahoo"
        and hk_yahoo_trust_policy is not None
        and hk_yahoo_trust_policy.rule_for_field(field_id) is not None
    ):
        return False
    return (
        item.status == "present"
        and not item.warnings
        and not item.review_notes
        and not item.conflict_classifications
        and not item.verification_required
    )


def _markdown(payload: dict[str, object]) -> str:
    fields_by_category = payload["fields_by_category"]
    counts_by_category = payload["counts_by_category"]
    assert isinstance(fields_by_category, dict)
    assert isinstance(counts_by_category, dict)
    lines = ["# Warning Classification", ""]
    for category in ALL_WARNING_CATEGORIES:
        fields = fields_by_category.get(category, [])
        field_text = ", ".join(fields) if isinstance(fields, list) and fields else "none"
        count = counts_by_category.get(category, 0)
        lines.append(f"- {category}: {count} ({field_text})")
    return "\n".join(lines) + "\n"
