"""Period-scoped replay for the provider field baseline fixture."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from financial_report_llm_extractor.models import Currency
from financial_report_llm_extractor.money import (
    MoneyNormalizationError,
    normalize_money,
)
from financial_report_llm_extractor.field_metadata import (
    FieldTaxonomyCatalog,
    load_field_taxonomy,
)
from financial_report_llm_extractor.structured_sources.artifacts import (
    read_source_inventory,
    write_source_inventory,
)
from financial_report_llm_extractor.structured_sources.capture_targets import (
    DEFAULT_PROVIDER_FIELD_CAPTURE_TARGETS,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    load_source_mapping_catalog,
)
from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportItem,
    SourceFirstExportResult,
    build_source_first_export,
    write_source_first_export_artifacts,
)
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    discover_provider_field_candidates,
)
from financial_report_llm_extractor.structured_sources.hk_15_field_closure import (
    build_hk_15_field_closure_report,
    write_hk_15_field_closure_artifacts,
)
from financial_report_llm_extractor.structured_sources.hk_yahoo_trust_policy import (
    HkYahooTrustPolicy,
    load_hk_yahoo_trust_policy,
)
from financial_report_llm_extractor.structured_sources.mapping import (
    map_source_inventory,
    write_turtle_mapping_artifacts,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
    SourceName,
)
from financial_report_llm_extractor.structured_sources.provider_semantics import (
    ProviderSemanticsCatalog,
    load_provider_semantics_catalog,
)
from financial_report_llm_extractor.structured_sources.reconciliation import (
    reconcile_mapped_fields,
    write_reconciliation_report,
)
from financial_report_llm_extractor.structured_sources.source_policy import (
    build_source_policy_report,
    write_source_policy_report,
)
from financial_report_llm_extractor.structured_sources.warning_classification import (
    build_warning_classification,
    write_warning_classification_artifacts,
)


ReplaySliceName = Literal["akshare_only", "yahoo_only", "combined"]
COMBINED_SLICE_NAME = "combined"  # used by _merge_llm_evidence_supplement gate
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_HK_YAHOO_TRUST_POLICY_PATH = (
    REPO_ROOT / "field_catalog" / "hk_yahoo_trust_policy.json"
)
DEFAULT_PROVIDER_RAW_SEMANTICS_PATH = (
    REPO_ROOT / "field_catalog" / "provider_raw_semantics_hk.json"
)
# Phase H2 Task 3: CN provider raw semantics (akshare CN promotion proof).
# Auto-merged with the HK file when present, so per-market rules coexist in a
# single ProviderSemanticsCatalog passed to source_policy resolution.
DEFAULT_PROVIDER_RAW_SEMANTICS_CN_PATH = (
    REPO_ROOT / "field_catalog" / "provider_raw_semantics_cn.json"
)
METADATA_REVIEW_NOTES = {
    "currency_metadata_required",
    "metadata_currency_suspected",
    "currency_as_unit",
    "statement_metadata_unproven",
}


@dataclass(frozen=True)
class _AutoHkYahooTrustPolicyPath:
    pass


AUTO_HK_YAHOO_TRUST_POLICY_PATH = _AutoHkYahooTrustPolicyPath()


@dataclass(frozen=True)
class ProviderBaselineGroup:
    company_id: str
    source: SourceName
    market: str
    provider_ticker: str


@dataclass(frozen=True)
class ProviderBaselineReplayResult:
    summary_path: Path
    markdown_path: Path
    company_count: int


def company_source_groups() -> dict[str, dict[SourceName, ProviderBaselineGroup]]:
    groups: dict[str, dict[SourceName, ProviderBaselineGroup]] = {}
    for target in DEFAULT_PROVIDER_FIELD_CAPTURE_TARGETS:
        company_groups = groups.setdefault(target.company_id, {})
        company_groups[target.provider] = ProviderBaselineGroup(
            company_id=target.company_id,
            source=target.provider,
            market=target.market,
            provider_ticker=target.provider_ticker,
        )
    return groups


def records_for_group(
    records: tuple[SourceInventoryRecord, ...],
    group: ProviderBaselineGroup,
) -> tuple[SourceInventoryRecord, ...]:
    return tuple(
        record
        for record in records
        if record.source == group.source
        and record.market == group.market
        and record.ticker == group.provider_ticker
    )


def _company_market(company_groups: dict[SourceName, ProviderBaselineGroup]) -> str:
    akshare_market = company_groups["akshare"].market
    yahoo_market = company_groups["yahoo"].market
    if akshare_market != yahoo_market:
        company_id = company_groups["akshare"].company_id
        raise ValueError(
            f"provider markets differ for {company_id}: "
            f"akshare={akshare_market}, yahoo={yahoo_market}"
        )
    return akshare_market


def select_latest_annual_records(
    records: tuple[SourceInventoryRecord, ...],
) -> tuple[SourceInventoryRecord, ...]:
    annual_dates = {
        _period_date_part(record.period)
        for record in records
        if record.source_status == "present"
        and record.period is not None
        and _is_annual_period(record.period)
    }
    if not annual_dates:
        return records
    selected_date = sorted(annual_dates)[-1]
    return tuple(
        replace(record, period=_period_date_part(record.period))
        for record in records
        if record.source_status == "present"
        and record.period is not None
        and _period_date_part(record.period) == selected_date
    )


def write_provider_baseline_period_replay(
    *,
    inventory_path: Path,
    inventory_summary_path: Path,
    catalog_path: Path,
    output_dir: Path,
    taxonomy_path: Path = Path("field_catalog/turtle_v015_field_taxonomy.json"),
    output_summary_path: Path | None = None,
    company_ids: tuple[str, ...] | None = None,
    hk_yahoo_trust_policy_path: (
        Path | None | _AutoHkYahooTrustPolicyPath
    ) = AUTO_HK_YAHOO_TRUST_POLICY_PATH,
) -> ProviderBaselineReplayResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    if not inventory_summary_path.exists():
        raise FileNotFoundError(f"inventory summary not found: {inventory_summary_path}")

    records = read_source_inventory(inventory_path)
    catalog = load_source_mapping_catalog(catalog_path, priorities=("P0", "P1", "P2"))
    taxonomy = load_field_taxonomy(taxonomy_path)
    hk_yahoo_trust_policy = _load_replay_hk_yahoo_trust_policy(
        hk_yahoo_trust_policy_path
    )
    provider_semantics_catalog = _load_replay_provider_semantics_catalog()
    groups = company_source_groups()
    selected_company_ids = company_ids or tuple(sorted(groups))
    unknown_company_ids = sorted(set(selected_company_ids) - set(groups))
    if unknown_company_ids:
        valid_company_ids = ", ".join(sorted(groups))
        raise ValueError(
            "unknown company ids: "
            f"{', '.join(unknown_company_ids)}; valid company ids: {valid_company_ids}"
        )

    companies: list[dict[str, object]] = []
    for company_id in selected_company_ids:
        company_groups = groups[company_id]
        akshare_group_records = records_for_group(records, company_groups["akshare"])
        yahoo_group_records = records_for_group(records, company_groups["yahoo"])
        akshare_records = select_latest_annual_records(akshare_group_records)
        yahoo_records = select_latest_annual_records(yahoo_group_records)
        company_market = _company_market(company_groups)

        company_dir = output_dir / company_id
        akshare_report = evaluate_source_first_slice(
            company_dir / "akshare_only",
            catalog=catalog,
            taxonomy=taxonomy,
            records=akshare_records,
            company_id=company_id,
            market=company_groups["akshare"].market,
            hk_yahoo_trust_policy=hk_yahoo_trust_policy,
            provider_semantics_catalog=provider_semantics_catalog,
        )
        yahoo_report = evaluate_source_first_slice(
            company_dir / "yahoo_only",
            catalog=catalog,
            taxonomy=taxonomy,
            records=yahoo_records,
            company_id=company_id,
            market=company_groups["yahoo"].market,
            hk_yahoo_trust_policy=hk_yahoo_trust_policy,
            provider_semantics_catalog=provider_semantics_catalog,
        )
        combined_report = evaluate_source_first_slice(
            company_dir / "combined",
            catalog=catalog,
            taxonomy=taxonomy,
            records=akshare_records + yahoo_records,
            company_id=company_id,
            market=company_market,
            hk_yahoo_trust_policy=hk_yahoo_trust_policy,
            provider_semantics_catalog=provider_semantics_catalog,
        )

        companies.append(
            {
                "company_id": company_id,
                "selected_periods": {
                    "akshare": _selected_period(
                        raw_records=akshare_group_records,
                        selected_records=akshare_records,
                    ),
                    "yahoo": _selected_period(
                        raw_records=yahoo_group_records,
                        selected_records=yahoo_records,
                    ),
                },
                "record_counts": {
                    "akshare_only": len(akshare_records),
                    "yahoo_only": len(yahoo_records),
                    "combined": len(akshare_records) + len(yahoo_records),
                },
                "coverage": {
                    "akshare_only": akshare_report["coverage"],
                    "yahoo_only": yahoo_report["coverage"],
                    "combined": combined_report["coverage"],
                },
                "review": {
                    "akshare_only": akshare_report["review"],
                    "yahoo_only": yahoo_report["review"],
                    "combined": combined_report["review"],
                },
                "artifact_paths": {
                    "akshare_only": akshare_report["artifact_paths"],
                    "yahoo_only": yahoo_report["artifact_paths"],
                    "combined": combined_report["artifact_paths"],
                },
            }
        )

    payload = {
        "report_id": "provider_baseline_period_replay",
        "catalog_id": catalog.catalog_id,
        "catalog_version": catalog.version,
        "inventory_path": str(inventory_path),
        "inventory_summary_path": str(inventory_summary_path),
        "company_count": len(companies),
        "companies": companies,
    }
    json_path = output_summary_path or (
        output_dir / "provider_baseline_period_replay_summary.json"
    )
    markdown_path = output_dir / "provider_baseline_period_replay_summary.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_summary_markdown(payload), encoding="utf-8")
    return ProviderBaselineReplayResult(
        summary_path=json_path,
        markdown_path=markdown_path,
        company_count=len(companies),
    )


def _extract_sign_normalize_fields(catalog: Any, market: str) -> frozenset[str]:
    """Build the set of field_ids whose market policy says sign_normalize='absolute'.

    Phase H2 Module A: reconciliation uses this to trigger abs() comparison
    for sign-convention-divergent fields like capital_expenditures.
    """
    out: set[str] = set()
    for field_id, entry in catalog.entries.items():
        if entry.source_policy is None:
            continue
        mp = entry.source_policy.market_policies.get(market)
        if mp is not None and mp.sign_normalize == "absolute":
            out.add(field_id)
    return frozenset(out)


def evaluate_source_first_slice(
    output_dir: Path,
    *,
    catalog: Any,
    taxonomy: FieldTaxonomyCatalog,
    records: tuple[SourceInventoryRecord, ...],
    company_id: str,
    market: str,
    hk_yahoo_trust_policy: HkYahooTrustPolicy | None,
    provider_semantics_catalog: ProviderSemanticsCatalog | None,
    llm_supplement_path: Path | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    slice_hk_yahoo_trust_policy = (
        hk_yahoo_trust_policy if market.upper() == "HK" else None
    )
    write_source_inventory(output_dir / "source_inventory.jsonl", records)
    mapping = map_source_inventory(catalog, records)
    reconciliation = reconcile_mapped_fields(
        mapping,
        sign_normalize_fields=_extract_sign_normalize_fields(catalog, market),
    )
    policy_report = build_source_policy_report(
        catalog,
        mapping,
        reconciliation,
        market=market,
        company_id=company_id,
        hk_yahoo_trust_policy=slice_hk_yahoo_trust_policy,
        provider_semantics_catalog=provider_semantics_catalog,
    )
    export = build_source_first_export(
        mapping,
        reconciliation,
        profile="source_only",
        source_policy_report=policy_report,
    )
    # Optional LLM evidence merge (Phase I-A integration).
    # Two paths:
    #   1. Explicit llm_supplement_path (orchestrator path, e.g.
    #      run_company_evaluation): merge from the exact path provided,
    #      regardless of output_dir.name.
    #   2. Legacy dir-name gate (provider_baseline_replay slice layout):
    #      restrict to combined slice only — LLM supplement is a cross-source
    #      artifact and would pollute per-source coverage views (akshare_only /
    #      yahoo_only).
    if llm_supplement_path is not None:
        export = _merge_llm_evidence_supplement(export, llm_supplement_path)
    elif output_dir.name == COMBINED_SLICE_NAME:
        supplement_candidate = output_dir.parent / "llm_evidence_supplement.json"
        export = _merge_llm_evidence_supplement(export, supplement_candidate)
    candidate_report = discover_provider_field_candidates(
        taxonomy_entries=taxonomy.fields,
        mapping_entries=catalog.entries,
        records=records,
        priorities=("P0", "P1", "P2"),
        fixture=f"provider_baseline_period_replay:{company_id}:{market}",
        taxonomy_catalog=taxonomy.catalog_id,
        mapping_catalog=catalog.catalog_id,
    )
    warning_classification = build_warning_classification(
        export,
        candidate_entries=candidate_report.fields,
        market=market,
        hk_yahoo_trust_policy=slice_hk_yahoo_trust_policy,
    )
    hk_15_field_closure_artifacts: dict[str, Path] = {}
    if market.upper() == "HK":
        closure_report = build_hk_15_field_closure_report(
            export=export,
            warning_classification=warning_classification,
            candidate_entries=candidate_report.fields,
            policy=slice_hk_yahoo_trust_policy,
            company_id=company_id,
            market=market,
        )
        hk_15_field_closure_artifacts = write_hk_15_field_closure_artifacts(
            closure_report,
            output_dir,
        )

    write_turtle_mapping_artifacts(mapping, output_dir)
    write_reconciliation_report(reconciliation, output_dir / "reconciliation_report.json")
    write_source_policy_report(policy_report, output_dir / "source_policy_report.json")
    write_source_first_export_artifacts(export, output_dir)
    warning_artifacts = write_warning_classification_artifacts(
        warning_classification,
        output_dir,
    )
    hk_yahoo_trust_policy_report_path: Path | None = None
    if slice_hk_yahoo_trust_policy is not None:
        hk_yahoo_trust_policy_report_path = (
            output_dir / "hk_yahoo_trust_policy_report.json"
        )
        _write_hk_yahoo_trust_policy_report(
            hk_yahoo_trust_policy_report_path,
            policy=slice_hk_yahoo_trust_policy,
            export=export,
            warning_classification=warning_classification,
            company_id=company_id,
            market=market,
        )

    review = {
        **_review_lists(export),
        **_hk_yahoo_trust_review_lists(
            warning_classification,
            policy=slice_hk_yahoo_trust_policy,
        ),
        "warning_classification": warning_classification.to_dict(),
    }
    artifact_paths = {
        "source_inventory": str(output_dir / "source_inventory.jsonl"),
        "turtle_mapping": str(output_dir / "turtle_mapping.json"),
        "source_coverage_summary": str(output_dir / "source_coverage_summary.json"),
        "reconciliation_report": str(output_dir / "reconciliation_report.json"),
        "source_policy_report": str(output_dir / "source_policy_report.json"),
        "extraction_result": str(output_dir / "extraction_result.json"),
        "review_summary": str(output_dir / "review_summary.json"),
        "warning_classification": str(warning_artifacts["json"]),
        "warning_classification_markdown": str(warning_artifacts["markdown"]),
    }
    if hk_yahoo_trust_policy_report_path is not None:
        artifact_paths["hk_yahoo_trust_policy_report"] = str(
            hk_yahoo_trust_policy_report_path
        )
    if hk_15_field_closure_artifacts:
        artifact_paths["hk_15_field_closure_report"] = str(
            hk_15_field_closure_artifacts["json"]
        )
        artifact_paths["hk_15_field_closure_markdown"] = str(
            hk_15_field_closure_artifacts["markdown"]
        )

    return {
        "coverage": _export_coverage(export),
        "review": review,
        "artifact_paths": artifact_paths,
        "export_object": export,
        "warning_classification_object": warning_classification,
        # Phase EC Tier 1: expose mapping so company_evaluation can render
        # per-source candidate values for unresolved_conflict rows.
        "mapping_object": mapping,
    }


def _load_replay_hk_yahoo_trust_policy(
    path: Path | None | _AutoHkYahooTrustPolicyPath,
) -> HkYahooTrustPolicy | None:
    if path is None:
        return None
    resolved_path = (
        DEFAULT_HK_YAHOO_TRUST_POLICY_PATH
        if isinstance(path, _AutoHkYahooTrustPolicyPath)
        else path
    )
    if not resolved_path.exists():
        return None
    return load_hk_yahoo_trust_policy(resolved_path)


def _load_replay_provider_semantics_catalog() -> ProviderSemanticsCatalog | None:
    """Load and merge HK + CN provider semantics catalogs into a single tuple.

    Returns None only when neither file is present. When both are present,
    rules are concatenated (HK first, then CN) into one ProviderSemanticsCatalog.

    fail-loud on collision: rule lookup keys on
    `(provider, market, turtle_field_id, raw_field_name)` (provider_semantics.py
    rule_for). If two files declare the same key (which would let `rule_for`
    silently return only the first match), raise ValueError so the
    inconsistency is visible at load time rather than as latent silent-shadowing
    bugs.
    """
    catalogs: list[ProviderSemanticsCatalog] = []
    if DEFAULT_PROVIDER_RAW_SEMANTICS_PATH.exists():
        catalogs.append(load_provider_semantics_catalog(DEFAULT_PROVIDER_RAW_SEMANTICS_PATH))
    if DEFAULT_PROVIDER_RAW_SEMANTICS_CN_PATH.exists():
        catalogs.append(load_provider_semantics_catalog(DEFAULT_PROVIDER_RAW_SEMANTICS_CN_PATH))
    if not catalogs:
        return None
    if len(catalogs) == 1:
        return catalogs[0]
    merged_rules = tuple(rule for c in catalogs for rule in c.rules)
    seen: set[tuple[str, str, str, str]] = set()
    duplicates: list[tuple[str, str, str, str]] = []
    for rule in merged_rules:
        key = (rule.provider, rule.market, rule.turtle_field_id, rule.raw_field_name)
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    if duplicates:
        raise ValueError(
            "duplicate provider semantics rule keys across HK + CN catalogs "
            f"(provider, market, turtle_field_id, raw_field_name): {duplicates}. "
            f"Each lookup key must be unique; rule_for would silently return only "
            f"the first match. Resolve by removing the duplicate or differentiating "
            f"raw_field_name."
        )
    return ProviderSemanticsCatalog(rules=merged_rules)


def _hk_yahoo_trust_review_lists(
    warning_classification: Any,
    *,
    policy: HkYahooTrustPolicy | None = None,
) -> dict[str, list[str]]:
    fields_by_category = warning_classification.fields_by_category
    sampled_policy_proof = list(fields_by_category["yahoo_pdf_verified"])
    definition_unverified = set(fields_by_category["yahoo_definition_unverified"])
    if policy is not None:
        definition_unverified.update(
            rule.field_id
            for rule in policy.rules
            if rule.classification == "yahoo_definition_unverified"
        )
    return {
        "yahoo_pdf_verified_fields": sampled_policy_proof,
        "provider_semantics_verified_fields": sampled_policy_proof,
        "sampled_pdf_policy_proof_fields": sampled_policy_proof,
        "final_pdf_evidence_fields": [],
        "provider_semantics_unverified_fields": sorted(definition_unverified),
        "yahoo_definition_unverified_fields": sorted(definition_unverified),
        "pdf_required_fields": fields_by_category["pdf_required"],
    }


def _write_hk_yahoo_trust_policy_report(
    output_path: Path,
    *,
    policy: HkYahooTrustPolicy,
    export: SourceFirstExportResult,
    warning_classification: Any,
    company_id: str,
    market: str,
) -> Path:
    review_lists = _hk_yahoo_trust_review_lists(warning_classification, policy=policy)
    final_pdf_evidence_fields = sorted(
        field_id
        for field_id, item in export.items.items()
        if item.pdf_evidence
    )
    payload = {
        "report_id": "hk_yahoo_trust_policy_report",
        "policy_version": policy.version,
        "company_id": company_id,
        "market": market,
        "deprecated_field_names": {
            "yahoo_pdf_verified_fields": (
                "Legacy name for sampled provider policy proof; not final "
                "per-export PDF evidence."
            )
        },
        **review_lists,
        "final_pdf_evidence_fields": final_pdf_evidence_fields,
        "items": {
            field_id: {
                "status": item.status,
                "selected_source": item.selected_source,
                "verification_required": item.verification_required,
                "trust_policy_evidence": item.trust_policy_evidence,
                "pdf_evidence_count": len(item.pdf_evidence),
            }
            for field_id, item in sorted(export.items.items())
            if item.trust_policy_evidence is not None
            or field_id
            in (
                set(review_lists["yahoo_pdf_verified_fields"])
                | set(review_lists["yahoo_definition_unverified_fields"])
                | set(review_lists["pdf_required_fields"])
            )
        },
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


# Phase I-A.2 review fix: LLM may report currency as "RMB", "HK$", "$" etc.
# Normalize to the project's Currency Literal (CNY/HKD/USD) or "unknown" /
# "ambiguous". The "$" symbol is intentionally ambiguous (HK$? US$?) and
# returns "ambiguous" rather than coerce silently.
_LLM_CURRENCY_NORMALIZATION: dict[str, Currency] = {
    "CNY": "CNY",
    "RMB": "CNY",
    "RENMINBI": "CNY",
    "人民币": "CNY",
    "人民幣": "CNY",
    "HKD": "HKD",
    "HK$": "HKD",
    "HKD$": "HKD",
    "港币": "HKD",
    "港幣": "HKD",
    "USD": "USD",
    "US$": "USD",
    "USD$": "USD",
    "美元": "USD",
}


def _normalize_llm_currency(raw: object) -> Currency:
    """Map an LLM-reported currency string to the project's Currency Literal.

    Returns "unknown" for None/empty/missing, "ambiguous" for the literal "$"
    (which could mean HK$ or US$), and "unknown" for anything else.
    """
    if raw is None:
        return "unknown"
    text = str(raw).strip()
    if not text:
        return "unknown"
    if text == "$":
        return "ambiguous"
    normalized = _LLM_CURRENCY_NORMALIZATION.get(text.upper())
    if normalized is not None:
        return normalized
    return "unknown"


def _merge_llm_evidence_supplement(
    export: SourceFirstExportResult,
    supplement_path: Path,
) -> SourceFirstExportResult:
    """Merge llm_evidence_supplement.json into export.

    For each item where:
    - export status is NOT 'present' (i.e. missing, ambiguous, blocked, etc.)
    - LLM supplement status is 'present'
    Apply the LLM value with `llm_supplemented` review note.
    Never overrides clean source values.
    """
    if not supplement_path.exists():
        return export
    payload = json.loads(supplement_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "llm-evidence-supplement-v1":
        return export

    llm_items = payload.get("items", {})
    if not isinstance(llm_items, dict):
        return export

    new_items: dict[str, SourceFirstExportItem] = dict(export.items)

    for field_id, llm_item in llm_items.items():
        if not isinstance(llm_item, dict):
            continue
        if llm_item.get("status") != "present":
            continue

        existing = new_items.get(field_id)
        if existing is not None and existing.status == "present":
            # Don't override clean source values
            continue

        # Build a present item from LLM evidence. Prefer the supplement's
        # parsed_numeric_value: run_field_extraction already canonicalized
        # accounting notation there (e.g. "(21)" -> -21), so reparsing only
        # the raw value here would silently drop such amounts (present with
        # value=None — PR-18 review P2).
        raw_value = llm_item.get("value")
        parsed_raw = llm_item.get("parsed_numeric_value")
        value: Decimal | None = None
        try:
            if parsed_raw is not None:
                value = Decimal(str(parsed_raw))
            elif raw_value is not None:
                value = Decimal(str(raw_value).replace(",", ""))
        except (InvalidOperation, ValueError):
            value = None

        currency = _normalize_llm_currency(llm_item.get("currency"))

        # Normalize money units so downstream consumers get a canonical
        # base-unit value (e.g. 10080.83 万元 → normalized_value=100808300.0).
        normalized_value: Decimal | None = None
        canonical_unit: Currency | None = None
        if value is not None:
            try:
                money = normalize_money(
                    str(value),
                    unit_context=str(llm_item.get("unit") or ""),
                    currency_hint=currency if currency in {"CNY", "HKD", "USD"} else None,
                )
                normalized_value = money.normalized_value
                canonical_unit = money.normalized_unit
            except (MoneyNormalizationError, ValueError, InvalidOperation):
                normalized_value = None
                canonical_unit = None

        # selected_source="llm" is intentionally distinct from SourceName
        # ("akshare" | "yahoo" | "fixture"). Downstream consumers should
        # treat it as a non-provider evidence source (cf. review_notes=
        # ("llm_supplemented",) for the audit signal).
        new_items[field_id] = SourceFirstExportItem(
            field_id=field_id,
            status="present",
            value=value,
            normalized_value=normalized_value,
            currency=currency,
            unit=str(llm_item.get("unit")) if llm_item.get("unit") else None,
            canonical_unit=canonical_unit,
            period=str(llm_item.get("period")) if llm_item.get("period") else None,
            review_notes=("llm_supplemented",),
            verification_required=True,
            selected_source="llm",
        )

    return SourceFirstExportResult(
        profile=export.profile,
        catalog_id=export.catalog_id,
        catalog_version=export.catalog_version,
        llm_provider=_optional_text(payload.get("llm_provider")) or export.llm_provider,
        llm_model=_optional_text(payload.get("llm_model")) or export.llm_model,
        items=new_items,
    )


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _export_coverage(export: SourceFirstExportResult) -> dict[str, object]:
    selected = sorted(
        field_id
        for field_id, item in export.items.items()
        if item.status == "present"
    )
    clean_present = sorted(
        field_id
        for field_id, item in export.items.items()
        if item.status == "present"
        and not item.warnings
        and not item.verification_required
        and not item.review_notes
        and not item.conflict_classifications
    )
    total = len(export.items)
    return {
        "covered_fields": selected,
        "covered_count": len(selected),
        "selected_fields": selected,
        "selected_count": len(selected),
        "clean_present_fields": clean_present,
        "clean_present_count": len(clean_present),
        "total_fields": total,
        "coverage_ratio": len(selected) / total if total else 0.0,
    }


def _review_lists(
    export: SourceFirstExportResult,
) -> dict[str, object]:
    field_lists = {
        "present_fields": sorted(
            field_id
            for field_id, item in export.items.items()
            if item.status == "present"
        ),
        "missing_fields": sorted(
            field_id
            for field_id, item in export.items.items()
            if item.status == "missing"
        ),
        "ambiguous_fields": sorted(
            field_id
            for field_id, item in export.items.items()
            if item.status == "ambiguous"
        ),
        "blocked_fields": sorted(
            field_id
            for field_id, item in export.items.items()
            if item.status == "blocked"
        ),
        "conflict_fields": sorted(
            field_id
            for field_id, item in export.items.items()
            if item.status == "conflict"
        ),
        "real_reconciliation_conflict_fields": sorted(
            field_id
            for field_id, item in export.items.items()
            if item.reconciliation_status == "conflict"
        ),
        "policy_unresolved_conflict_fields": sorted(
            field_id
            for field_id, item in export.items.items()
            if item.status == "conflict"
            or item.selection_status == "unresolved_conflict"
        ),
        "selected_with_warnings_fields": sorted(
            field_id
            for field_id, item in export.items.items()
            if item.status == "present" and (item.warnings or item.verification_required)
        ),
        "present_metadata_warning_fields": sorted(
            field_id
            for field_id, item in export.items.items()
            if item.status == "present"
            and (
                any(note in METADATA_REVIEW_NOTES for note in item.review_notes)
                or any("currency metadata" in warning for warning in item.warnings)
                or any("HK metadata" in warning for warning in item.warnings)
            )
        ),
        "metadata_blocker_fields": sorted(
            field_id
            for field_id, item in export.items.items()
            if item.status != "present"
            and any(note in METADATA_REVIEW_NOTES for note in item.review_notes)
        ),
        "fields_requiring_pdf_evidence": sorted(
            field_id
            for field_id, item in export.items.items()
            if item.verification_required or item.status == "needs_pdf_evidence"
        ),
    }
    return {**field_lists, "gap_categories": _gap_categories(field_lists)}


def _gap_categories(review: dict[str, list[str]]) -> dict[str, list[str]]:
    conflict_fields = set(review["conflict_fields"])
    source_availability = review["missing_fields"]
    mapping_ambiguity = sorted(set(review["ambiguous_fields"]) - conflict_fields)
    mapping_blocker = review["blocked_fields"]
    real_reconciliation_conflict = review["real_reconciliation_conflict_fields"]
    policy_unresolved_conflict = review["policy_unresolved_conflict_fields"]
    fields_requiring_pdf_evidence = review["fields_requiring_pdf_evidence"]
    pdf_llm_supplement_candidates = sorted(
        set(source_availability)
        | set(mapping_ambiguity)
        | set(mapping_blocker)
        | set(policy_unresolved_conflict)
        | set(real_reconciliation_conflict)
        | set(fields_requiring_pdf_evidence)
    )
    return {
        "source_availability": source_availability,
        "mapping_ambiguity": mapping_ambiguity,
        "mapping_blocker": mapping_blocker,
        "real_reconciliation_conflict": real_reconciliation_conflict,
        "policy_unresolved_conflict": policy_unresolved_conflict,
        "pdf_llm_supplement_candidates": pdf_llm_supplement_candidates,
    }


def _selected_period(
    *,
    raw_records: tuple[SourceInventoryRecord, ...],
    selected_records: tuple[SourceInventoryRecord, ...],
) -> dict[str, object]:
    selected_periods = sorted(
        {
            record.period
            for record in selected_records
            if record.source_status == "present" and record.period is not None
        }
    )
    if not selected_periods:
        return {"normalized": None, "raw_periods": []}

    normalized = selected_periods[-1]
    raw_periods = sorted(
        {
            record.period
            for record in raw_records
            if record.source_status == "present"
            and record.period is not None
            and _period_date_part(record.period) == normalized
        }
    )
    return {"normalized": normalized, "raw_periods": raw_periods}


def _summary_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Provider Baseline Period Replay",
        "",
        f"- company_count: {payload['company_count']}",
        "",
    ]
    for company in payload["companies"]:
        lines.extend([f"## {company['company_id']}", ""])
        for slice_name in ("akshare_only", "yahoo_only", "combined"):
            coverage = company["coverage"][slice_name]
            review = company["review"][slice_name]
            artifact_paths = company["artifact_paths"][slice_name]
            lines.append(
                f"- {slice_name}: {coverage['covered_count']}/"
                f"{coverage['total_fields']} covered; "
                f"conflicts={len(review['conflict_fields'])}; "
                f"ambiguous={len(review['ambiguous_fields'])}; "
                f"blocked={len(review['blocked_fields'])}"
            )
            lines.extend(
                [
                    f"  - present_fields: {_format_field_list(review['present_fields'])}",
                    f"  - missing_fields: {_format_field_list(review['missing_fields'])}",
                    f"  - ambiguous_fields: {_format_field_list(review['ambiguous_fields'])}",
                    f"  - blocked_fields: {_format_field_list(review['blocked_fields'])}",
                    f"  - conflict_fields: {_format_field_list(review['conflict_fields'])}",
                    "  - selected_with_warnings_fields: "
                    f"{_format_field_list(review['selected_with_warnings_fields'])}",
                    "  - present_metadata_warning_fields: "
                    f"{_format_field_list(review['present_metadata_warning_fields'])}",
                    "  - metadata_blocker_fields: "
                    f"{_format_field_list(review['metadata_blocker_fields'])}",
                    "  - fields_requiring_pdf_evidence: "
                    f"{_format_field_list(review['fields_requiring_pdf_evidence'])}",
                    "  - yahoo_pdf_verified_fields: "
                    f"{_format_field_list(review['yahoo_pdf_verified_fields'])}",
                    "  - yahoo_definition_unverified_fields: "
                    f"{_format_field_list(review['yahoo_definition_unverified_fields'])}",
                    "  - pdf_required_fields: "
                    f"{_format_field_list(review['pdf_required_fields'])}",
                ]
            )
            classification = review["warning_classification"]
            classification_fields = classification["fields_by_category"]
            lines.extend(
                [
                    "  - warning_classification:",
                    "    - source_policy_resolvable: "
                    f"{_format_field_list(classification_fields['source_policy_resolvable'])}",
                    "    - pdf_verification_required: "
                    f"{_format_field_list(classification_fields['pdf_verification_required'])}",
                    "    - mapping_expansion_required: "
                    f"{_format_field_list(classification_fields['mapping_expansion_required'])}",
                    "    - source_unavailable: "
                    f"{_format_field_list(classification_fields['source_unavailable'])}",
                ]
            )
            gap_categories = review["gap_categories"]
            lines.extend(
                [
                    "  - gap_categories:",
                    "    - source_availability: "
                    f"{_format_field_list(gap_categories['source_availability'])}",
                    "    - mapping_ambiguity: "
                    f"{_format_field_list(gap_categories['mapping_ambiguity'])}",
                    "    - mapping_blocker: "
                    f"{_format_field_list(gap_categories['mapping_blocker'])}",
                    "    - real_reconciliation_conflict: "
                    f"{_format_field_list(gap_categories['real_reconciliation_conflict'])}",
                    "    - policy_unresolved_conflict: "
                    f"{_format_field_list(gap_categories['policy_unresolved_conflict'])}",
                    "    - pdf_llm_supplement_candidates: "
                    f"{_format_field_list(gap_categories['pdf_llm_supplement_candidates'])}",
                    "  - artifacts:",
                    f"    - review_summary: {artifact_paths['review_summary']}",
                    f"    - reconciliation_report: {artifact_paths['reconciliation_report']}",
                    f"    - source_policy_report: {artifact_paths['source_policy_report']}",
                    f"    - extraction_result: {artifact_paths['extraction_result']}",
                ]
            )
            if "hk_yahoo_trust_policy_report" in artifact_paths:
                lines.append(
                    "    - hk_yahoo_trust_policy_report: "
                    f"{artifact_paths['hk_yahoo_trust_policy_report']}"
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _format_field_list(fields: object) -> str:
    if not isinstance(fields, list) or not fields:
        return "none"
    return ", ".join(str(field) for field in fields)


def _is_annual_period(period: str) -> bool:
    return _period_date_part(period).endswith("-12-31")


def _period_date_part(period: str) -> str:
    return period.split(" ")[0]
