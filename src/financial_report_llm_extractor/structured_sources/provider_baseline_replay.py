"""Period-scoped replay for the provider field baseline fixture."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

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
    build_source_first_export,
    write_source_first_export_artifacts,
)
from financial_report_llm_extractor.structured_sources.mapping import (
    TurtleMappingResult,
    map_source_inventory,
    write_turtle_mapping_artifacts,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
    SourceName,
)
from financial_report_llm_extractor.structured_sources.reconciliation import (
    ReconciliationReport,
    reconcile_mapped_fields,
    write_reconciliation_report,
)


ReplaySliceName = Literal["akshare_only", "yahoo_only", "combined"]


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
    output_summary_path: Path | None = None,
    company_ids: tuple[str, ...] | None = None,
) -> ProviderBaselineReplayResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    if not inventory_summary_path.exists():
        raise FileNotFoundError(f"inventory summary not found: {inventory_summary_path}")

    records = read_source_inventory(inventory_path)
    catalog = load_source_mapping_catalog(catalog_path, priorities=("P0", "P1"))
    groups = company_source_groups()
    selected_company_ids = company_ids or tuple(sorted(groups))

    companies: list[dict[str, object]] = []
    for company_id in selected_company_ids:
        company_groups = groups[company_id]
        akshare_group_records = records_for_group(records, company_groups["akshare"])
        yahoo_group_records = records_for_group(records, company_groups["yahoo"])
        akshare_records = select_latest_annual_records(akshare_group_records)
        yahoo_records = select_latest_annual_records(yahoo_group_records)

        company_dir = output_dir / company_id
        akshare_report = _write_slice(
            company_dir / "akshare_only",
            catalog=catalog,
            records=akshare_records,
        )
        yahoo_report = _write_slice(
            company_dir / "yahoo_only",
            catalog=catalog,
            records=yahoo_records,
        )
        combined_report = _write_slice(
            company_dir / "combined",
            catalog=catalog,
            records=akshare_records + yahoo_records,
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
    records: tuple[SourceInventoryRecord, ...],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_source_inventory(output_dir / "source_inventory.jsonl", records)
    mapping = map_source_inventory(catalog, records)
    reconciliation = reconcile_mapped_fields(mapping)
    export = build_source_first_export(mapping, reconciliation, profile="source_only")

    write_turtle_mapping_artifacts(mapping, output_dir)
    write_reconciliation_report(reconciliation, output_dir / "reconciliation_report.json")
    write_source_first_export_artifacts(export, output_dir)

    return {
        "coverage": _mapping_coverage(mapping),
        "review": _review_lists(mapping, reconciliation),
        "artifact_paths": {
            "source_inventory": str(output_dir / "source_inventory.jsonl"),
            "turtle_mapping": str(output_dir / "turtle_mapping.json"),
            "source_coverage_summary": str(output_dir / "source_coverage_summary.json"),
            "reconciliation_report": str(output_dir / "reconciliation_report.json"),
            "extraction_result": str(output_dir / "extraction_result.json"),
            "review_summary": str(output_dir / "review_summary.json"),
        },
    }


def _mapping_coverage(mapping: TurtleMappingResult) -> dict[str, object]:
    covered = sorted(
        field_id
        for field_id, field in mapping.fields.items()
        if field.status in {"present", "derived"}
    )
    total = len(mapping.fields)
    return {
        "covered_fields": covered,
        "covered_count": len(covered),
        "total_fields": total,
        "coverage_ratio": len(covered) / total if total else 0.0,
    }


def _review_lists(
    mapping: TurtleMappingResult,
    reconciliation: ReconciliationReport,
) -> dict[str, list[str]]:
    return {
        "present_fields": sorted(
            field_id
            for field_id, field in mapping.fields.items()
            if field.status in {"present", "derived"}
        ),
        "missing_fields": sorted(
            field_id
            for field_id, field in mapping.fields.items()
            if field.status == "missing"
        ),
        "ambiguous_fields": sorted(
            field_id
            for field_id, field in mapping.fields.items()
            if field.status == "ambiguous"
        ),
        "blocked_fields": sorted(
            field_id
            for field_id, field in mapping.fields.items()
            if field.status == "blocked"
        ),
        "conflict_fields": list(reconciliation.conflict_fields),
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
            lines.append(
                f"- {slice_name}: {coverage['covered_count']}/"
                f"{coverage['total_fields']} covered; "
                f"conflicts={len(review['conflict_fields'])}; "
                f"ambiguous={len(review['ambiguous_fields'])}; "
                f"blocked={len(review['blocked_fields'])}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _is_annual_period(period: str) -> bool:
    return _period_date_part(period).endswith("-12-31")


def _period_date_part(period: str) -> str:
    return period.split(" ")[0]
