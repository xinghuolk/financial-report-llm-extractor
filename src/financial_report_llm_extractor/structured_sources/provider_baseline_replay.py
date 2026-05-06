"""Period-scoped replay for the provider field baseline fixture."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

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
    SourceFirstExportResult,
    build_source_first_export,
    write_source_first_export_artifacts,
)
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    discover_provider_field_candidates,
)
from financial_report_llm_extractor.structured_sources.mapping import (
    map_source_inventory,
    write_turtle_mapping_artifacts,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
    SourceName,
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
METADATA_REVIEW_NOTES = {
    "currency_metadata_required",
    "metadata_currency_suspected",
    "currency_as_unit",
    "statement_metadata_unproven",
}


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
) -> ProviderBaselineReplayResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    if not inventory_summary_path.exists():
        raise FileNotFoundError(f"inventory summary not found: {inventory_summary_path}")

    records = read_source_inventory(inventory_path)
    catalog = load_source_mapping_catalog(catalog_path, priorities=("P0", "P1"))
    taxonomy = load_field_taxonomy(taxonomy_path)
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
        akshare_report = _write_slice(
            company_dir / "akshare_only",
            catalog=catalog,
            taxonomy=taxonomy,
            records=akshare_records,
            company_id=company_id,
            market=company_groups["akshare"].market,
        )
        yahoo_report = _write_slice(
            company_dir / "yahoo_only",
            catalog=catalog,
            taxonomy=taxonomy,
            records=yahoo_records,
            company_id=company_id,
            market=company_groups["yahoo"].market,
        )
        combined_report = _write_slice(
            company_dir / "combined",
            catalog=catalog,
            taxonomy=taxonomy,
            records=akshare_records + yahoo_records,
            company_id=company_id,
            market=company_market,
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


def _write_slice(
    output_dir: Path,
    *,
    catalog: Any,
    taxonomy: FieldTaxonomyCatalog,
    records: tuple[SourceInventoryRecord, ...],
    company_id: str,
    market: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_source_inventory(output_dir / "source_inventory.jsonl", records)
    mapping = map_source_inventory(catalog, records)
    reconciliation = reconcile_mapped_fields(mapping)
    policy_report = build_source_policy_report(
        catalog,
        mapping,
        reconciliation,
        market=market,
        company_id=company_id,
    )
    export = build_source_first_export(
        mapping,
        reconciliation,
        profile="source_only",
        source_policy_report=policy_report,
    )
    candidate_report = discover_provider_field_candidates(
        taxonomy_entries=taxonomy.fields,
        mapping_entries=catalog.entries,
        records=records,
        priorities=("P0", "P1"),
        fixture=f"provider_baseline_period_replay:{company_id}:{market}",
        taxonomy_catalog=taxonomy.catalog_id,
        mapping_catalog=catalog.catalog_id,
    )
    warning_classification = build_warning_classification(
        export,
        candidate_entries=candidate_report.fields,
    )

    write_turtle_mapping_artifacts(mapping, output_dir)
    write_reconciliation_report(reconciliation, output_dir / "reconciliation_report.json")
    write_source_policy_report(policy_report, output_dir / "source_policy_report.json")
    write_source_first_export_artifacts(export, output_dir)
    warning_artifacts = write_warning_classification_artifacts(
        warning_classification,
        output_dir,
    )

    return {
        "coverage": _export_coverage(export),
        "review": {
            **_review_lists(export),
            "warning_classification": warning_classification.to_dict(),
        },
        "artifact_paths": {
            "source_inventory": str(output_dir / "source_inventory.jsonl"),
            "turtle_mapping": str(output_dir / "turtle_mapping.json"),
            "source_coverage_summary": str(output_dir / "source_coverage_summary.json"),
            "reconciliation_report": str(output_dir / "reconciliation_report.json"),
            "source_policy_report": str(output_dir / "source_policy_report.json"),
            "extraction_result": str(output_dir / "extraction_result.json"),
            "review_summary": str(output_dir / "review_summary.json"),
            "warning_classification": str(warning_artifacts["json"]),
            "warning_classification_markdown": str(warning_artifacts["markdown"]),
        },
    }


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
