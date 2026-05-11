"""Source policy selection and conflict classification."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal, Mapping

from financial_report_llm_extractor.structured_sources.catalog import (
    MarketSourcePolicy,
    SourceMappingCatalog,
    SourceMappingEntry,
)
from financial_report_llm_extractor.structured_sources.hk_yahoo_trust_policy import (
    HkYahooTrustPolicy,
)
from financial_report_llm_extractor.structured_sources.mapping import (
    MappedTurtleField,
    TurtleMappingCandidate,
    TurtleMappingResult,
)
from financial_report_llm_extractor.structured_sources.provider_semantics import (
    ProviderSemanticsCatalog,
)
from financial_report_llm_extractor.structured_sources.reconciliation import (
    ReconciliationReport,
    ReconciliationStatus,
)

ConflictClassification = Literal[
    "semantic_mismatch",
    "fx_like_ratio",
    "metadata_currency_suspected",
    "normalized_value_conflict",
    "missing_source_candidate",
    "single_source_unverified",
    "currency_metadata_required",
    "currency_as_unit",
    "statement_metadata_unproven",
]
SelectionStatus = Literal[
    "selected_primary",
    "selected_single_source",
    "unresolved_conflict",
    "missing",
    "blocked",
]


@dataclass(frozen=True)
class SourcePolicyItem:
    field_id: str
    selection_status: SelectionStatus
    selected_candidate: TurtleMappingCandidate | None = None
    conflict_classifications: tuple[ConflictClassification, ...] = field(
        default_factory=tuple
    )
    verification_required: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)
    reconciliation_status: ReconciliationStatus | None = None
    trust_policy_evidence: Mapping[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "field_id": self.field_id,
            "selection_status": self.selection_status,
            "selected_candidate": (
                self.selected_candidate.to_dict()
                if self.selected_candidate is not None
                else None
            ),
            "conflict_classifications": list(self.conflict_classifications),
            "verification_required": self.verification_required,
            "warnings": list(self.warnings),
            "reconciliation_status": self.reconciliation_status,
            "trust_policy_evidence": self.trust_policy_evidence,
        }


@dataclass(frozen=True)
class SourcePolicyReport:
    catalog_id: str
    catalog_version: str
    company_id: str | None
    market: str | None
    items: dict[str, SourcePolicyItem]

    def to_dict(self) -> dict[str, object]:
        return {
            "catalog_id": self.catalog_id,
            "catalog_version": self.catalog_version,
            "company_id": self.company_id,
            "market": self.market,
            "items": {
                field_id: self.items[field_id].to_dict()
                for field_id in sorted(self.items)
            },
        }


def build_source_policy_report(
    catalog: SourceMappingCatalog,
    mapping: TurtleMappingResult,
    reconciliation: ReconciliationReport,
    *,
    market: str | None = None,
    company_id: str | None = None,
    hk_yahoo_trust_policy: HkYahooTrustPolicy | None = None,
    provider_semantics_catalog: ProviderSemanticsCatalog | None = None,
) -> SourcePolicyReport:
    ratio_fields = _fx_like_fields(mapping)
    items: dict[str, SourcePolicyItem] = {}
    for field_id, mapped_field in mapping.fields.items():
        entry = catalog.entries[field_id]
        reconciliation_item = reconciliation.items.get(field_id)
        reconciliation_status = (
            reconciliation_item.status if reconciliation_item is not None else None
        )
        items[field_id] = _resolve_field(
            entry,
            mapped_field,
            market=market,
            company_id=company_id,
            reconciliation_status=reconciliation_status,
            fx_like=field_id in ratio_fields,
            hk_yahoo_trust_policy=hk_yahoo_trust_policy,
            provider_semantics_catalog=provider_semantics_catalog,
        )
    return SourcePolicyReport(
        catalog_id=mapping.catalog_id,
        catalog_version=mapping.catalog_version,
        company_id=company_id,
        market=market,
        items=items,
    )


def write_source_policy_report(report: SourcePolicyReport, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return output_path


def _resolve_field(
    entry: SourceMappingEntry,
    field: MappedTurtleField,
    *,
    market: str | None,
    company_id: str | None = None,
    reconciliation_status: ReconciliationStatus | None,
    fx_like: bool,
    hk_yahoo_trust_policy: HkYahooTrustPolicy | None,
    provider_semantics_catalog: ProviderSemanticsCatalog | None,
) -> SourcePolicyItem:
    if field.status == "missing":
        return SourcePolicyItem(
            field_id=field.field_id,
            selection_status="missing",
            conflict_classifications=("missing_source_candidate",),
            reconciliation_status=reconciliation_status,
        )
    if field.status == "blocked":
        return SourcePolicyItem(
            field_id=field.field_id,
            selection_status="blocked",
            reconciliation_status=reconciliation_status,
        )
    if field.status in {"present", "derived"} and field.candidates:
        return _resolve_single_source(
            entry,
            field,
            market,
            company_id,
            reconciliation_status,
            hk_yahoo_trust_policy,
            provider_semantics_catalog,
        )
    if field.status == "derived" and not field.candidates:
        # Phase H2.1: derived fields without per-source candidates (e.g.
        # `derivation = "akshare:RAW_A + akshare:RAW_B"` resolves directly
        # against records, bypassing direct-alias matching) carry no provider
        # conflict to resolve. The derivation IS the single source: emit a
        # clean selected_single_source result so export keeps status="present"
        # and the field reaches clean_present.
        return SourcePolicyItem(
            field_id=field.field_id,
            selection_status="selected_single_source",
            reconciliation_status=reconciliation_status,
        )

    classifications = _classifications(entry, field, market=market, fx_like=fx_like)
    candidate = _primary_candidate(entry, field, market)
    market_policy = _market_policy(entry, market)
    if market_policy is not None and candidate is None:
        return SourcePolicyItem(
            field_id=field.field_id,
            selection_status="unresolved_conflict",
            conflict_classifications=("missing_source_candidate",),
            verification_required=True,
            warnings=("market source policy primary candidate missing",),
            reconciliation_status=reconciliation_status,
        )
    metadata_classifications = (
        _metadata_classifications(entry, market, candidate)
        if candidate is not None
        else ()
    )
    if candidate is not None and metadata_classifications:
        if not _can_apply_hk_yahoo_trust_policy(
            field.field_id,
            candidate,
            market=market,
            company_id=company_id,
            hk_yahoo_trust_policy=hk_yahoo_trust_policy,
            provider_semantics_catalog=provider_semantics_catalog,
        ):
            return SourcePolicyItem(
                field_id=field.field_id,
                selection_status="unresolved_conflict",
                conflict_classifications=_dedupe_classifications(
                    classifications + metadata_classifications
                ),
                verification_required=True,
                warnings=(
                    _metadata_warning(market, prefix="selected primary candidate"),
                ),
                reconciliation_status=reconciliation_status,
            )
        return _apply_trust_policies(
            SourcePolicyItem(
                field_id=field.field_id,
                selection_status="unresolved_conflict",
                selected_candidate=candidate,
                conflict_classifications=_dedupe_classifications(
                    classifications + metadata_classifications
                ),
                verification_required=True,
                warnings=(
                    _metadata_warning(market, prefix="selected primary candidate"),
                ),
                reconciliation_status=reconciliation_status,
            ),
            market=market,
            company_id=company_id,
            hk_yahoo_trust_policy=hk_yahoo_trust_policy,
            provider_semantics_catalog=provider_semantics_catalog,
        )
    if reconciliation_status in {"equivalent", "close"}:
        return _apply_trust_policies(
            SourcePolicyItem(
                field_id=field.field_id,
                selection_status="selected_primary",
                selected_candidate=candidate or _deterministic_candidate(field.candidates),
                reconciliation_status=reconciliation_status,
            ),
            market=market,
            company_id=company_id,
            hk_yahoo_trust_policy=hk_yahoo_trust_policy,
            provider_semantics_catalog=provider_semantics_catalog,
        )

    if (
        candidate is not None
        and market_policy is not None
        and market_policy.on_conflict == "select_primary_require_pdf"
    ):
        return _apply_trust_policies(
            SourcePolicyItem(
                field_id=field.field_id,
                selection_status="selected_primary",
                selected_candidate=candidate,
                conflict_classifications=classifications,
                verification_required=True,
                warnings=tuple(
                    f"source policy selected primary candidate despite {classification}"
                    for classification in classifications
                ),
                reconciliation_status=reconciliation_status,
            ),
            market=market,
            company_id=company_id,
            hk_yahoo_trust_policy=hk_yahoo_trust_policy,
            provider_semantics_catalog=provider_semantics_catalog,
        )
    return SourcePolicyItem(
        field_id=field.field_id,
        selection_status="unresolved_conflict",
        conflict_classifications=classifications or ("normalized_value_conflict",),
        verification_required=True,
        reconciliation_status=reconciliation_status,
    )


def _resolve_single_source(
    entry: SourceMappingEntry,
    field: MappedTurtleField,
    market: str | None,
    company_id: str | None,
    reconciliation_status: ReconciliationStatus | None,
    hk_yahoo_trust_policy: HkYahooTrustPolicy | None,
    provider_semantics_catalog: ProviderSemanticsCatalog | None,
) -> SourcePolicyItem:
    candidate = field.candidates[0]
    market_policy = _market_policy(entry, market)
    requires_pdf = bool(
        market_policy is not None and market_policy.single_source_requires_pdf
    )
    metadata_classifications = _metadata_classifications(entry, market, candidate)
    if metadata_classifications:
        if not _can_apply_hk_yahoo_trust_policy(
            field.field_id,
            candidate,
            market=market,
            company_id=company_id,
            hk_yahoo_trust_policy=hk_yahoo_trust_policy,
            provider_semantics_catalog=provider_semantics_catalog,
        ):
            return SourcePolicyItem(
                field_id=field.field_id,
                selection_status="unresolved_conflict",
                conflict_classifications=metadata_classifications,
                verification_required=True,
                warnings=(_metadata_warning(market, prefix="single source candidate"),),
                reconciliation_status=reconciliation_status,
            )
        return _apply_trust_policies(
            SourcePolicyItem(
                field_id=field.field_id,
                selection_status="unresolved_conflict",
                selected_candidate=candidate,
                conflict_classifications=metadata_classifications,
                verification_required=True,
                warnings=(_metadata_warning(market, prefix="single source candidate"),),
                reconciliation_status=reconciliation_status,
            ),
            market=market,
            company_id=company_id,
            hk_yahoo_trust_policy=hk_yahoo_trust_policy,
            provider_semantics_catalog=provider_semantics_catalog,
        )
    classifications: tuple[ConflictClassification, ...] = (
        ("single_source_unverified",) if requires_pdf else ()
    )
    return _apply_trust_policies(
        SourcePolicyItem(
            field_id=field.field_id,
            selection_status="selected_single_source",
            selected_candidate=candidate,
            conflict_classifications=classifications,
            verification_required=requires_pdf,
            warnings=(
                ("single source candidate requires PDF verification",)
                if requires_pdf
                else ()
            ),
            reconciliation_status=reconciliation_status,
        ),
        market=market,
        company_id=company_id,
        hk_yahoo_trust_policy=hk_yahoo_trust_policy,
        provider_semantics_catalog=provider_semantics_catalog,
    )


_HK_YAHOO_TRUSTED_UNCERTAINTIES: tuple[ConflictClassification, ...] = (
    "fx_like_ratio",
    "metadata_currency_suspected",
    "single_source_unverified",
    "currency_as_unit",
    "statement_metadata_unproven",
)


# Phase H2 Task 3: classifications that a provider_semantics_sample_verified
# rule "explains" — they describe why provider raw values diverge (e.g. AKShare
# OPERATE_INCOME vs Yahoo Total Revenue including finance-subsidiary 利息收入).
# When a sample-verified rule applies to the selected primary candidate, these
# classifications are cleared because the divergence is the *expected*
# semantic gap documented in the catalog rule.
_PROVIDER_SEMANTICS_EXPLAINED_CLASSIFICATIONS: tuple[ConflictClassification, ...] = (
    "semantic_mismatch",
    "normalized_value_conflict",
)


def _apply_hk_yahoo_trust_policy(
    item: SourcePolicyItem,
    *,
    market: str | None,
    company_id: str | None = None,
    hk_yahoo_trust_policy: HkYahooTrustPolicy | None,
    provider_semantics_catalog: ProviderSemanticsCatalog | None,
) -> SourcePolicyItem:
    candidate = item.selected_candidate
    if not _can_apply_hk_yahoo_trust_policy(
        item.field_id,
        candidate,
        market=market,
        company_id=company_id,
        hk_yahoo_trust_policy=hk_yahoo_trust_policy,
        provider_semantics_catalog=provider_semantics_catalog,
    ):
        return item
    assert hk_yahoo_trust_policy is not None
    remaining_classifications = tuple(
        classification
        for classification in item.conflict_classifications
        if classification not in _HK_YAHOO_TRUSTED_UNCERTAINTIES
    )
    remaining_warnings = tuple(
        warning
        for warning in item.warnings
        if not _is_hk_yahoo_trusted_uncertainty_warning(warning)
    )
    trust_policy_evidence = hk_yahoo_trust_policy.build_policy_evidence(item.field_id)
    if provider_semantics_catalog is not None and candidate is not None:
        semantics_rule = provider_semantics_catalog.rule_for(
            provider="yahoo",
            market="HK",
            turtle_field_id=item.field_id,
            raw_field_name=candidate.raw_field_name,
        )
        if semantics_rule is not None:
            trust_policy_evidence = {
                **trust_policy_evidence,
                "proof_class": "sampled_pdf_policy_proof",
                "is_final_pdf_evidence": False,
                "provider_semantics_classification": semantics_rule.classification,
                "provider_semantics_proof_origin": semantics_rule.proof_origin,
                "provider_semantics_raw_field": semantics_rule.raw_field_name,
            }
    return SourcePolicyItem(
        field_id=item.field_id,
        selection_status=(
            "selected_primary"
            if item.selection_status == "unresolved_conflict"
            else item.selection_status
        ),
        selected_candidate=candidate,
        conflict_classifications=remaining_classifications,
        verification_required=bool(remaining_classifications or remaining_warnings),
        warnings=remaining_warnings,
        reconciliation_status=item.reconciliation_status,
        trust_policy_evidence=trust_policy_evidence,
    )


def _can_apply_hk_yahoo_trust_policy(
    field_id: str,
    candidate: TurtleMappingCandidate | None,
    *,
    market: str | None,
    company_id: str | None = None,
    hk_yahoo_trust_policy: HkYahooTrustPolicy | None,
    provider_semantics_catalog: ProviderSemanticsCatalog | None,
) -> bool:
    if market != "HK" or hk_yahoo_trust_policy is None or candidate is None:
        return False
    if candidate.source != "yahoo":
        return False
    rule = hk_yahoo_trust_policy.rule_for_field(field_id)
    if rule is None or rule.classification != "yahoo_pdf_verified":
        return False
    accepted_currencies = rule.accepted_currencies()
    if (
        not candidate.raw_field_name
        or candidate.raw_field_name not in rule.allowed_yahoo_raw_fields
        or candidate.currency not in accepted_currencies
        or candidate.unit != rule.trusted_unit
        or candidate.canonical_unit not in accepted_currencies
        or candidate.unit_multiplier != rule.trusted_unit_multiplier
        or not rule.applies_to_company(company_id)
    ):
        return False
    if provider_semantics_catalog is None:
        return False
    semantics_rule = provider_semantics_catalog.rule_for(
        provider="yahoo",
        market="HK",
        turtle_field_id=field_id,
        raw_field_name=candidate.raw_field_name,
    )
    return (
        semantics_rule is not None
        and semantics_rule.allowed_as_primary
        and semantics_rule.classification == "provider_semantics_sample_verified"
    )


def _is_hk_yahoo_trusted_uncertainty_warning(warning: str) -> bool:
    if warning == "single source candidate requires PDF verification":
        return True
    if "lacks proven HK metadata" in warning:
        return True
    return any(
        f"despite {classification}" in warning
        for classification in _HK_YAHOO_TRUSTED_UNCERTAINTIES
    )


def _apply_trust_policies(
    item: SourcePolicyItem,
    *,
    market: str | None,
    company_id: str | None = None,
    hk_yahoo_trust_policy: HkYahooTrustPolicy | None,
    provider_semantics_catalog: ProviderSemanticsCatalog | None,
) -> SourcePolicyItem:
    """Apply HK Yahoo trust policy + market-agnostic provider semantics promotion.

    Both mechanisms can clear classifications/warnings on a selected primary
    candidate; HK trust policy fires first (HK Yahoo specific), provider
    semantics promotion fires second (CN AKShare and any other market with a
    provider_semantics_sample_verified rule).

    `company_id` propagates from `build_source_policy_report` so HK Yahoo
    trust rules with `pdf_verified_company_ids` allowlists can gate promotion
    per issuer (Phase HK-B.5 follow-up — avoids broad promotion when the
    Yahoo HK adapter's hardcoded HKD currency label misrepresents a non-HKD
    issuer's reporting currency).
    """
    item = _apply_hk_yahoo_trust_policy(
        item,
        market=market,
        company_id=company_id,
        hk_yahoo_trust_policy=hk_yahoo_trust_policy,
        provider_semantics_catalog=provider_semantics_catalog,
    )
    item = _apply_provider_semantics_promotion(
        item,
        market=market,
        company_id=company_id,
        provider_semantics_catalog=provider_semantics_catalog,
    )
    return _apply_provider_semantics_unverified_warning(
        item,
        market=market,
        provider_semantics_catalog=provider_semantics_catalog,
    )


# Phase H2.2 Sub-B: when a selected candidate matches a
# provider_semantics_unverified rule (e.g. HK Yahoo SGA per 00001/01113
# spot-check), the rule documents a known scope mismatch with PDF. Surface
# this as verification_required + a warning so the field lands in
# pdf_required → terminal_unverified rather than silently clean_present.
def _apply_provider_semantics_unverified_warning(
    item: SourcePolicyItem,
    *,
    market: str | None,
    provider_semantics_catalog: ProviderSemanticsCatalog | None,
) -> SourcePolicyItem:
    if provider_semantics_catalog is None or market is None:
        return item
    if item.selection_status not in {"selected_primary", "selected_single_source"}:
        return item
    candidate = item.selected_candidate
    if candidate is None or not candidate.raw_field_name:
        return item
    # If trust_policy_evidence already documents a sample_verified rule, the
    # candidate is explained — don't re-add an unverified warning.
    if (
        item.trust_policy_evidence is not None
        and item.trust_policy_evidence.get("provider_semantics_classification")
        == "provider_semantics_sample_verified"
    ):
        return item
    semantics_rule = provider_semantics_catalog.rule_for(
        provider=candidate.source,
        market=market,
        turtle_field_id=item.field_id,
        raw_field_name=candidate.raw_field_name,
    )
    if (
        semantics_rule is None
        or semantics_rule.classification != "provider_semantics_unverified"
    ):
        return item
    # Phase H2.2 Sub-B: only gate when the unverified rule carries fresh PDF
    # spot-check samples documenting the scope mismatch. Older stub-level
    # unverified rules without samples are documentation-only and must not
    # silently regress fields that previously passed clean_present.
    if not semantics_rule.samples:
        return item
    warning = (
        f"provider semantics unverified for {candidate.source} "
        f"{candidate.raw_field_name!r} on {market}: "
        f"{semantics_rule.classification}"
    )
    if warning in item.warnings:
        return item
    new_trust_policy_evidence: dict[str, object] = {
        "proof_class": "sampled_pdf_policy_proof",
        "is_final_pdf_evidence": False,
        "provider_semantics_classification": semantics_rule.classification,
        "provider_semantics_proof_origin": semantics_rule.proof_origin,
        "provider_semantics_raw_field": semantics_rule.raw_field_name,
        "provider_semantics_provider": semantics_rule.provider,
        "provider_semantics_market": semantics_rule.market,
    }
    if item.trust_policy_evidence is not None:
        new_trust_policy_evidence = {
            **item.trust_policy_evidence,
            **new_trust_policy_evidence,
        }
    return SourcePolicyItem(
        field_id=item.field_id,
        selection_status=item.selection_status,
        selected_candidate=candidate,
        conflict_classifications=item.conflict_classifications,
        verification_required=True,
        warnings=item.warnings + (warning,),
        reconciliation_status=item.reconciliation_status,
        trust_policy_evidence=new_trust_policy_evidence,
    )


# Phase H2 Task 3: market-agnostic provider semantics promotion. When a
# selected_primary candidate matches a provider_semantics_sample_verified rule
# (allowed_as_primary=True), the rule documents the per-provider semantic
# divergence. We clear semantic_mismatch / normalized_value_conflict
# classifications because the rule is the proof that the chosen provider value
# is the correct Turtle field, even if cross-source values differ.
def _apply_provider_semantics_promotion(
    item: SourcePolicyItem,
    *,
    market: str | None,
    company_id: str | None = None,
    provider_semantics_catalog: ProviderSemanticsCatalog | None,
) -> SourcePolicyItem:
    if provider_semantics_catalog is None or market is None:
        return item
    if item.selection_status != "selected_primary":
        return item
    candidate = item.selected_candidate
    if candidate is None or not candidate.raw_field_name:
        return item
    semantics_rule = provider_semantics_catalog.rule_for(
        provider=candidate.source,
        market=market,
        turtle_field_id=item.field_id,
        raw_field_name=candidate.raw_field_name,
    )
    if (
        semantics_rule is None
        or not semantics_rule.allowed_as_primary
        or semantics_rule.classification != "provider_semantics_sample_verified"
        or not semantics_rule.applies_to_company(company_id)
    ):
        return item

    remaining_classifications = tuple(
        classification
        for classification in item.conflict_classifications
        if classification not in _PROVIDER_SEMANTICS_EXPLAINED_CLASSIFICATIONS
    )
    remaining_warnings = tuple(
        warning
        for warning in item.warnings
        if not _is_provider_semantics_explained_warning(warning)
    )
    trust_policy_evidence: dict[str, object] = {
        "proof_class": "sampled_pdf_policy_proof",
        "is_final_pdf_evidence": False,
        "provider_semantics_classification": semantics_rule.classification,
        "provider_semantics_proof_origin": semantics_rule.proof_origin,
        "provider_semantics_raw_field": semantics_rule.raw_field_name,
        "provider_semantics_provider": semantics_rule.provider,
        "provider_semantics_market": semantics_rule.market,
    }
    if item.trust_policy_evidence is not None:
        trust_policy_evidence = {**item.trust_policy_evidence, **trust_policy_evidence}
    return SourcePolicyItem(
        field_id=item.field_id,
        selection_status=item.selection_status,
        selected_candidate=candidate,
        conflict_classifications=remaining_classifications,
        verification_required=bool(remaining_classifications or remaining_warnings),
        warnings=remaining_warnings,
        reconciliation_status=item.reconciliation_status,
        trust_policy_evidence=trust_policy_evidence,
    )


def _is_provider_semantics_explained_warning(warning: str) -> bool:
    return any(
        f"despite {classification}" in warning
        for classification in _PROVIDER_SEMANTICS_EXPLAINED_CLASSIFICATIONS
    )


def _classifications(
    entry: SourceMappingEntry,
    field: MappedTurtleField,
    *,
    market: str | None,
    fx_like: bool,
) -> tuple[ConflictClassification, ...]:
    classifications: list[ConflictClassification] = []
    if _semantic_mismatch(entry, field, market):
        classifications.append("semantic_mismatch")
    if fx_like:
        classifications.extend(["fx_like_ratio", "metadata_currency_suspected"])
    if not classifications and _values_differ(field):
        classifications.append("normalized_value_conflict")
    return tuple(classifications)


def _semantic_mismatch(
    entry: SourceMappingEntry,
    field: MappedTurtleField,
    market: str | None,
) -> bool:
    policy = entry.source_policy
    if policy is None:
        return False
    primary_candidate = _primary_candidate(entry, field, market)
    if primary_candidate is None or primary_candidate.normalized_value is None:
        return False
    variants = policy.semantic_variants.get(primary_candidate.source)
    if variants is None:
        return False
    related_candidates = tuple(
        candidate
        for candidate in field.candidates + field.policy_evidence_candidates
        if candidate.source == primary_candidate.source
        and candidate.normalized_value is not None
        and _candidate_label(candidate) in variants.related
    )
    if not related_candidates:
        return False
    cross_check_sources = _cross_check_sources(entry, market)
    cross_check_candidates = tuple(
        candidate
        for candidate in field.candidates
        if candidate.source in cross_check_sources
        and candidate.normalized_value is not None
    )
    for related_candidate in related_candidates:
        for cross_check_candidate in cross_check_candidates:
            if (
                cross_check_candidate.normalized_value
                == related_candidate.normalized_value
                and cross_check_candidate.normalized_value
                != primary_candidate.normalized_value
            ):
                return True
    return False


def _candidate_label(candidate: TurtleMappingCandidate) -> str:
    return candidate.raw_field_code or candidate.raw_field_name


def _cross_check_sources(
    entry: SourceMappingEntry,
    market: str | None,
) -> set[str]:
    market_policy = _market_policy(entry, market)
    if market_policy is None:
        if entry.source_policy is None:
            return set()
        return {
            source
            for source, variants in entry.source_policy.semantic_variants.items()
            if variants.primary
        }
    return {_source_from_route(route) for route in market_policy.cross_check_routes}


def _values_differ(field: MappedTurtleField) -> bool:
    values = {
        candidate.normalized_value
        for candidate in field.candidates
        if candidate.normalized_value is not None
    }
    return len(values) > 1


def _requires_currency_metadata(candidate: TurtleMappingCandidate) -> bool:
    return (
        candidate.currency in {"unknown", "ambiguous"}
        or candidate.unit is None
        or candidate.canonical_unit is None
    )


def _metadata_classifications(
    entry: SourceMappingEntry,
    market: str | None,
    candidate: TurtleMappingCandidate,
) -> tuple[ConflictClassification, ...]:
    classifications: list[ConflictClassification] = []
    if _requires_currency_metadata(candidate):
        classifications.append("currency_metadata_required")
    if market == "HK" and _candidate_uses_currency_as_unit(candidate):
        classifications.append("currency_as_unit")
    if _requires_hk_statement_metadata(entry, market, candidate):
        classifications.append("statement_metadata_unproven")
    return _dedupe_classifications(tuple(classifications))


def _metadata_warning(market: str | None, *, prefix: str) -> str:
    metadata_scope = "HK metadata" if market == "HK" else "source metadata"
    return f"{prefix} lacks proven {metadata_scope}"


def _candidate_uses_currency_as_unit(candidate: TurtleMappingCandidate) -> bool:
    return (
        candidate.currency not in {"unknown", "ambiguous"}
        and candidate.unit is not None
        and candidate.unit.upper() == candidate.currency
    )


def _requires_hk_statement_metadata(
    entry: SourceMappingEntry,
    market: str | None,
    candidate: TurtleMappingCandidate,
) -> bool:
    return (
        market == "HK"
        and entry.value_type == "money"
        and not candidate.statement_metadata_proven
    )


def _dedupe_classifications(
    classifications: tuple[ConflictClassification, ...],
) -> tuple[ConflictClassification, ...]:
    return tuple(dict.fromkeys(classifications))


def _market_policy(
    entry: SourceMappingEntry,
    market: str | None,
) -> MarketSourcePolicy | None:
    if entry.source_policy is None or market is None:
        return None
    return entry.source_policy.market_policies.get(market)


def _primary_candidate(
    entry: SourceMappingEntry,
    field: MappedTurtleField,
    market: str | None,
) -> TurtleMappingCandidate | None:
    market_policy = _market_policy(entry, market)
    if market_policy is None:
        return None
    primary_source = market_policy.primary_route.split("_", 1)[0]
    source_candidates = [
        candidate
        for candidate in field.candidates
        if candidate.source == primary_source
    ]
    if not source_candidates:
        return None
    if entry.source_policy is None:
        return source_candidates[0]
    variants = entry.source_policy.semantic_variants.get(primary_source)
    if variants is None:
        return source_candidates[0]
    for primary_label in variants.primary:
        for candidate in source_candidates:
            if (
                candidate.raw_field_code == primary_label
                or candidate.raw_field_name == primary_label
            ):
                return candidate
    return source_candidates[0]


def _source_from_route(route: str) -> str:
    return route.split("_", 1)[0]


def _deterministic_candidate(
    candidates: tuple[TurtleMappingCandidate, ...],
) -> TurtleMappingCandidate:
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.source,
            candidate.raw_field_name,
            candidate.raw_field_code or "",
        ),
    )[0]


def _fx_like_fields(
    mapping: TurtleMappingResult,
    *,
    relative_tolerance: Decimal = Decimal("0.001"),
) -> set[str]:
    ratios: list[tuple[str, tuple[str, str, str | None, str], Decimal]] = []
    for field_id, mapped_field in mapping.fields.items():
        if len(mapped_field.candidates) != 2:
            continue
        left, right = _ordered_pair(mapped_field.candidates)
        if left.period != right.period:
            continue
        if left.currency != right.currency:
            continue
        base = left.normalized_value
        other = right.normalized_value
        if (
            base is None
            or base == Decimal("0")
            or other is None
            or other == Decimal("0")
        ):
            continue
        ratio = other / base
        if ratio == 1:
            continue
        ratios.append(
            (
                field_id,
                (left.source, right.source, left.period, left.currency),
                ratio,
            )
        )
    for _, grouping_key, ratio in ratios:
        similar = [
            other_field_id
            for other_field_id, other_grouping_key, other_ratio in ratios
            if other_grouping_key == grouping_key
            and _relative_difference(ratio, other_ratio) <= relative_tolerance
        ]
        if len(similar) >= 3:
            return set(similar)
    return set()


def _ordered_pair(
    candidates: tuple[TurtleMappingCandidate, ...],
) -> tuple[TurtleMappingCandidate, TurtleMappingCandidate]:
    assert len(candidates) == 2
    left, right = sorted(
        candidates,
        key=lambda candidate: (
            candidate.source,
            candidate.raw_field_name,
            candidate.raw_field_code or "",
        ),
    )
    return left, right


def _relative_difference(left: Decimal, right: Decimal) -> Decimal:
    denominator = max(abs(left), abs(right))
    if denominator == 0:
        return Decimal("0")
    return abs(left - right) / denominator
