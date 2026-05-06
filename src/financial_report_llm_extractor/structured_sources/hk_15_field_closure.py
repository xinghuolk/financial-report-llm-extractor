"""HK 15-field source-first closure report artifacts."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Mapping, cast

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
from financial_report_llm_extractor.structured_sources.warning_classification import (
    WarningCategory,
    WarningClassificationItem,
    WarningClassificationResult,
)


HK_15_FIELD_IDS: tuple[str, ...] = (
    "revenue",
    "net_profit",
    "total_assets",
    "total_liabilities",
    "cash",
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
    "bond_payable",
    "cip",
    "invest_income",
    "gross_profit",
    "total_cur_assets",
    "total_cur_liab",
    "defer_tax_liab",
)

ClosureCategory = Literal[
    "clean_present",
    "selected_with_warnings",
    "yahoo_pdf_verified",
    "yahoo_definition_unverified",
    "pdf_required",
    "mapping_expansion_required",
    "source_unavailable",
]

ALL_CLOSURE_CATEGORIES: tuple[ClosureCategory, ...] = (
    "clean_present",
    "selected_with_warnings",
    "yahoo_pdf_verified",
    "yahoo_definition_unverified",
    "pdf_required",
    "mapping_expansion_required",
    "source_unavailable",
)


@dataclass(frozen=True)
class Hk15FieldClosureItem:
    field_id: str
    category: ClosureCategory
    status: str
    reason: str | None
    reasons: tuple[str, ...]
    selected_source: str | None
    candidate_sources: tuple[str, ...]
    verification_required: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        payload["candidate_sources"] = list(self.candidate_sources)
        payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class Hk15FieldClosureReport:
    company_id: str
    market: str
    total_fields: int
    counts_by_category: dict[ClosureCategory, int]
    fields_by_category: dict[ClosureCategory, list[str]]
    items: dict[str, Hk15FieldClosureItem]

    def to_dict(self) -> dict[str, object]:
        return {
            "company_id": self.company_id,
            "market": self.market,
            "total_fields": self.total_fields,
            "counts_by_category": self.counts_by_category,
            "fields_by_category": self.fields_by_category,
            "items": {
                field_id: self.items[field_id].to_dict()
                for field_id in HK_15_FIELD_IDS
                if field_id in self.items
            },
        }


def build_hk_15_field_closure_report(
    *,
    export: SourceFirstExportResult,
    warning_classification: WarningClassificationResult,
    candidate_entries: Mapping[str, FieldCandidateReportEntry],
    policy: HkYahooTrustPolicy | None,
    company_id: str,
    market: str,
) -> Hk15FieldClosureReport:
    items = {
        field_id: _closure_item(
            field_id,
            export.items.get(field_id),
            warning_classification.items.get(field_id),
            candidate_entries.get(field_id),
            policy=policy,
        )
        for field_id in HK_15_FIELD_IDS
    }
    counts = Counter(item.category for item in items.values())
    counts_by_category = {
        category: counts[category] for category in ALL_CLOSURE_CATEGORIES
    }
    fields_by_category = {
        category: sorted(
            field_id
            for field_id, item in items.items()
            if item.category == category
        )
        for category in ALL_CLOSURE_CATEGORIES
    }
    return Hk15FieldClosureReport(
        company_id=company_id,
        market=market,
        total_fields=len(HK_15_FIELD_IDS),
        counts_by_category=counts_by_category,
        fields_by_category=fields_by_category,
        items=items,
    )


def write_hk_15_field_closure_artifacts(
    report: Hk15FieldClosureReport,
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "hk_15_field_closure_report.json"
    markdown_path = output_dir / "hk_15_field_closure_report.md"
    payload = report.to_dict()
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def _closure_item(
    field_id: str,
    item: SourceFirstExportItem | None,
    warning_item: WarningClassificationItem | None,
    candidate_entry: FieldCandidateReportEntry | None,
    *,
    policy: HkYahooTrustPolicy | None,
) -> Hk15FieldClosureItem:
    policy_reason = _definition_unverified_reason(field_id, item, policy)
    if policy_reason is not None:
        return Hk15FieldClosureItem(
            field_id=field_id,
            category="yahoo_definition_unverified",
            status=item.status if item is not None else "missing",
            reason=policy_reason,
            reasons=(policy_reason,),
            selected_source=item.selected_source if item is not None else None,
            candidate_sources=_candidate_sources(candidate_entry, warning_item),
            verification_required=(
                item.verification_required if item is not None else False
            ),
            warnings=item.warnings if item is not None else (),
        )

    if item is not None and _is_clean_present(item):
        clean_reasons: tuple[str, ...] = (
            "present_without_warnings_or_verification_required",
        )
        return Hk15FieldClosureItem(
            field_id=field_id,
            category="clean_present",
            status=item.status,
            reason=_first_reason(clean_reasons),
            reasons=clean_reasons,
            selected_source=item.selected_source,
            candidate_sources=_candidate_sources(candidate_entry, warning_item),
            verification_required=item.verification_required,
            warnings=item.warnings,
        )

    if warning_item is not None:
        warning_category = _closure_category_from_warning(warning_item.category)
        return Hk15FieldClosureItem(
            field_id=field_id,
            category=warning_category,
            status=warning_item.status,
            reason=_first_reason(warning_item.reasons),
            reasons=warning_item.reasons,
            selected_source=warning_item.selected_source,
            candidate_sources=warning_item.candidate_sources,
            verification_required=warning_item.verification_required,
            warnings=warning_item.warnings,
        )

    category: ClosureCategory
    if item is not None and item.status == "missing":
        category = (
            "mapping_expansion_required"
            if _has_provider_candidates(candidate_entry)
            else "source_unavailable"
        )
    elif item is None:
        category = (
            "mapping_expansion_required"
            if _has_provider_candidates(candidate_entry)
            else "source_unavailable"
        )
    else:
        category = "selected_with_warnings"

    reasons: tuple[str, ...] = _fallback_reasons(item, candidate_entry)
    return Hk15FieldClosureItem(
        field_id=field_id,
        category=category,
        status=item.status if item is not None else "missing",
        reason=_first_reason(reasons),
        reasons=reasons,
        selected_source=item.selected_source if item is not None else None,
        candidate_sources=_candidate_sources(candidate_entry, warning_item),
        verification_required=item.verification_required if item is not None else False,
        warnings=item.warnings if item is not None else (),
    )


def _closure_category_from_warning(category: WarningCategory) -> ClosureCategory:
    if category in {
        "yahoo_pdf_verified",
        "yahoo_definition_unverified",
        "pdf_required",
        "mapping_expansion_required",
        "source_unavailable",
    }:
        return cast(ClosureCategory, category)
    if category == "pdf_verification_required":
        return "pdf_required"
    return "selected_with_warnings"


def _definition_unverified_reason(
    field_id: str,
    item: SourceFirstExportItem | None,
    policy: HkYahooTrustPolicy | None,
) -> str | None:
    if item is None or item.status != "present" or item.selected_source != "yahoo":
        return None
    if policy is None:
        return None
    rule = policy.rule_for_field(field_id)
    if rule is None or rule.classification != "yahoo_definition_unverified":
        return None
    return rule.definition_status_reason


def _is_clean_present(item: SourceFirstExportItem | None) -> bool:
    return (
        item is not None
        and item.status == "present"
        and not item.verification_required
        and not item.warnings
    )


def _fallback_reasons(
    item: SourceFirstExportItem | None,
    candidate_entry: FieldCandidateReportEntry | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if item is None:
        reasons.append("field_absent_from_export")
    elif item.status == "missing":
        reasons.append(
            "provider_candidates_present"
            if _has_provider_candidates(candidate_entry)
            else "provider_candidates_absent"
        )
    if item is not None and item.verification_required:
        reasons.append("verification_required")
    if item is not None:
        reasons.extend(f"warning:{warning}" for warning in item.warnings)
    return tuple(dict.fromkeys(reasons))


def _candidate_sources(
    candidate_entry: FieldCandidateReportEntry | None,
    warning_item: WarningClassificationItem | None,
) -> tuple[str, ...]:
    if warning_item is not None:
        return warning_item.candidate_sources
    if candidate_entry is None:
        return ()
    return tuple(sorted(candidate_entry.providers))


def _has_provider_candidates(candidate_entry: FieldCandidateReportEntry | None) -> bool:
    return bool(candidate_entry is not None and candidate_entry.providers)


def _first_reason(reasons: tuple[str, ...]) -> str | None:
    return reasons[0] if reasons else None


def _markdown(report: Hk15FieldClosureReport) -> str:
    lines = [
        "# HK 15-Field Closure Report",
        "",
        f"- company_id: {report.company_id}",
        f"- market: {report.market}",
        f"- total_fields: {report.total_fields}",
        "",
        "## Categories",
        "",
    ]
    for category in ALL_CLOSURE_CATEGORIES:
        fields = report.fields_by_category[category]
        field_text = ", ".join(fields) if fields else "none"
        lines.append(f"- {category}: {report.counts_by_category[category]} ({field_text})")
    return "\n".join(lines) + "\n"
