import json
from decimal import Decimal
from pathlib import Path
from typing import cast

from financial_report_llm_extractor.field_metadata import FieldDomain, FieldTaxonomyEntry
from financial_report_llm_extractor.structured_sources.catalog import SourceMappingEntry
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    ProviderFieldCandidate,
    ProviderRawField,
    build_provider_raw_field_index,
    discover_provider_field_candidates,
    normalize_match_text,
    write_provider_field_candidate_report,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
)


def _record(
    *,
    source: str = "akshare",
    ticker: str = "600519",
    statement_type: str = "income_statement",
    period: str = "2025-12-31",
    raw_field_name: str = "营业收入",
    raw_field_code: str | None = "OPERATE_INCOME",
    value: str = "100",
) -> SourceInventoryRecord:
    evidence = SourceEvidence(
        source=source,  # type: ignore[arg-type]
        adapter=source,
        function="fn",
        artifact_id="artifact_1",
        raw_record_id=f"{source}:{ticker}:{statement_type}:{period}:{raw_field_name}",
        raw_field_name=raw_field_name,
        raw_field_code=raw_field_code,
    )
    return SourceInventoryRecord(
        source=source,  # type: ignore[arg-type]
        market="CN" if ticker == "600519" else "HK",
        ticker=ticker,
        statement_type=statement_type,
        period=period,
        raw_field_name=raw_field_name,
        raw_field_code=raw_field_code,
        raw_value=value,
        parsed_numeric_value=Decimal(value),
        currency="CNY" if ticker == "600519" else "HKD",
        unit="yuan" if ticker == "600519" else "raw",
        source_evidence=(evidence,),
    )


def test_normalize_match_text_handles_english_codes_and_chinese() -> None:
    assert normalize_match_text("TOTAL_OPERATE_INCOME") == "total operate income"
    assert normalize_match_text("Total   Revenue") == "total revenue"
    assert normalize_match_text("营业收入") == "营业收入"


def test_build_provider_raw_field_index_groups_targets_periods_and_counts() -> None:
    records = (
        _record(period="2024-12-31"),
        _record(period="2025-12-31"),
        _record(
            source="yahoo",
            ticker="0001.HK",
            raw_field_name="Total Revenue",
            raw_field_code=None,
            value="200",
        ),
    )

    index = build_provider_raw_field_index(records)

    akshare_key = ("akshare", "income_statement", "营业收入", "OPERATE_INCOME")
    yahoo_key = ("yahoo", "income_statement", "Total Revenue", None)
    assert index[akshare_key] == ProviderRawField(
        source="akshare",
        statement_type="income_statement",
        raw_field_name="营业收入",
        raw_field_code="OPERATE_INCOME",
        normalized_names=("营业收入",),
        normalized_codes=("operate income",),
        tickers=("600519",),
        periods=("2024-12-31", "2025-12-31"),
        record_count=2,
    )
    assert index[yahoo_key].tickers == ("0001.HK",)
    assert index[yahoo_key].periods == ("2025-12-31",)


def _taxonomy_entry(
    field_id: str = "revenue",
    *,
    priority: str = "P0",
    statement_type: str = "income_statement",
    source_mode: str = "direct",
    value_type: str = "money",
    period_type: str = "duration",
    scope_expectation: str = "consolidated",
    currency_requirement: str = "required",
    unit_requirement: str = "required",
    evidence_requirement: str = "source_only_allowed",
    description: str = "Revenue from operations for the reporting period.",
) -> FieldTaxonomyEntry:
    domain: FieldDomain = "notes_and_mda"
    if statement_type in {"income_statement", "balance_sheet", "cash_flow"}:
        domain = cast(FieldDomain, statement_type)
    return FieldTaxonomyEntry(
        field_id=field_id,
        priority=priority,  # type: ignore[arg-type]
        domain=domain,
        statement_type=statement_type,  # type: ignore[arg-type]
        value_type=value_type,  # type: ignore[arg-type]
        source_mode=source_mode,  # type: ignore[arg-type]
        period_type=period_type,  # type: ignore[arg-type]
        scope_expectation=scope_expectation,  # type: ignore[arg-type]
        currency_requirement=currency_requirement,  # type: ignore[arg-type]
        unit_requirement=unit_requirement,  # type: ignore[arg-type]
        evidence_requirement=evidence_requirement,  # type: ignore[arg-type]
        fallback_policy="pdf_allowed",
        description=description,
    )


def _mapping_entry(
    field_id: str = "revenue",
    *,
    priority: str = "P0",
    statement_type: str = "income_statement",
) -> SourceMappingEntry:
    return SourceMappingEntry(
        field_id=field_id,
        priority=priority,
        value_type="money",
        statement_type=statement_type,
        currency_requirement="required",
        unit_requirement="required",
        source_aliases={
            "akshare": ("营业收入", "OPERATE_INCOME"),
            "yahoo": ("Total Revenue",),
        },
        domain=statement_type,
        source_mode="direct",
        primary_route="akshare_direct",
        verification_status="verified",
        fallback_policy="pdf_allowed",
    )


def test_discover_provider_field_candidates_marks_existing_aliases_strong() -> None:
    records = (
        _record(
            period="2024-12-31",
            raw_field_name="营业收入",
            raw_field_code="OPERATE_INCOME",
        ),
        _record(
            period="2025-12-31",
            raw_field_name="营业收入",
            raw_field_code="OPERATE_INCOME",
        ),
        _record(
            source="yahoo",
            ticker="0001.HK",
            raw_field_name="Total Revenue",
            raw_field_code=None,
            value="200",
        ),
    )

    report = discover_provider_field_candidates(
        taxonomy_entries={"revenue": _taxonomy_entry()},
        mapping_entries={"revenue": _mapping_entry()},
        records=records,
        priorities=("P0",),
    )

    field = report.fields["revenue"]
    assert field.status == "has_candidates"
    assert field.providers["akshare"].candidates[0] == ProviderFieldCandidate(
        raw_field_name="营业收入",
        raw_field_code="OPERATE_INCOME",
        score=100,
        strength="strong",
        signals=("existing_alias", "statement_match", "period_support"),
        target_count=1,
        period_count=2,
        record_count=2,
    )
    assert field.providers["yahoo"].candidates[0].strength == "strong"


def test_discover_provider_field_candidates_marks_pdf_only_not_applicable() -> None:
    report = discover_provider_field_candidates(
        taxonomy_entries={
            "audit_opinion": _taxonomy_entry(
                field_id="audit_opinion",
                priority="P4",
                statement_type="notes",
                source_mode="pdf_only",
                value_type="text",
                period_type="annual_text",
                scope_expectation="not_applicable",
                currency_requirement="not_applicable",
                unit_requirement="not_applicable",
                evidence_requirement="pdf_required",
                description="Audit opinion text.",
            )
        },
        mapping_entries={},
        records=(),
        priorities=("P4",),
    )

    assert report.fields["audit_opinion"].status == "not_applicable"
    assert report.fields["audit_opinion"].providers == {}


def test_discover_provider_field_candidates_marks_cross_provider_support() -> None:
    mapping = SourceMappingEntry(
        field_id="revenue",
        priority="P0",
        value_type="money",
        statement_type="income_statement",
        currency_requirement="required",
        unit_requirement="required",
        source_aliases={
            "akshare": ("Total Revenue",),
            "yahoo": ("Total Revenue",),
        },
        domain="income_statement",
        source_mode="direct",
        primary_route="akshare_direct",
        verification_status="expected",
        fallback_policy="pdf_allowed",
    )
    report = discover_provider_field_candidates(
        taxonomy_entries={"revenue": _taxonomy_entry()},
        mapping_entries={"revenue": mapping},
        records=(
            _record(
                source="akshare",
                raw_field_name="Total Revenue",
                raw_field_code=None,
            ),
            _record(
                source="yahoo",
                ticker="0001.HK",
                raw_field_name="Total Revenue",
                raw_field_code=None,
            ),
        ),
        priorities=("P0",),
    )

    akshare_candidate = report.fields["revenue"].providers["akshare"].candidates[0]
    yahoo_candidate = report.fields["revenue"].providers["yahoo"].candidates[0]
    assert "cross_provider_support" in akshare_candidate.signals
    assert "cross_provider_support" in yahoo_candidate.signals


def test_discover_provider_field_candidates_keeps_catalog_gap_with_candidates() -> None:
    report = discover_provider_field_candidates(
        taxonomy_entries={"revenue": _taxonomy_entry()},
        mapping_entries={},
        records=(
            _record(
                raw_field_name="revenue",
                raw_field_code=None,
            ),
        ),
        priorities=("P0",),
    )

    field = report.fields["revenue"]
    assert field.status == "catalog_gap"
    assert field.providers["akshare"].candidates[0].raw_field_name == "revenue"
    assert report.summary["fields_with_candidates"] == 1
    assert report.summary["fields_without_candidates"] == 0


def test_provider_field_candidate_report_summary_counts_empty_catalog_gaps() -> None:
    report = discover_provider_field_candidates(
        taxonomy_entries={"revenue": _taxonomy_entry()},
        mapping_entries={},
        records=(),
        priorities=("P0",),
    )

    assert report.fields["revenue"].status == "catalog_gap"
    assert report.summary["fields_with_candidates"] == 0
    assert report.summary["fields_without_candidates"] == 1


def test_write_provider_field_candidate_report_writes_json_and_markdown(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "candidate_report"

    result = write_provider_field_candidate_report(
        taxonomy_path=Path("field_catalog/turtle_v015_field_taxonomy.json"),
        mapping_catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        inventory_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz"
        ),
        summary_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/"
            "provider_field_inventory_summary.json"
        ),
        output_dir=output_dir,
        priorities=("P0", "P1"),
    )

    assert result.json_path == output_dir / "provider_field_candidate_report.json"
    assert result.markdown_path == output_dir / "provider_field_candidate_report.md"
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["report_id"] == "provider_field_candidate_report"
    assert payload["summary"]["field_count"] == 33
    assert payload["summary"]["inventory_record_count"] == 6771
    assert payload["fields"]["revenue"]["status"] == "has_candidates"
    assert "akshare" in payload["fields"]["revenue"]["providers"]
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "## P0" in markdown
    assert "`revenue`" in markdown
    assert "akshare" in markdown
    assert "营业收入" in markdown
    assert "OPERATE_INCOME" in markdown
    assert "strength=`strong`" in markdown
    assert "signals=existing_alias,statement_match,period_support" in markdown


def test_provider_field_candidate_report_fixture_summary_is_stable(
    tmp_path: Path,
) -> None:
    result = write_provider_field_candidate_report(
        taxonomy_path=Path("field_catalog/turtle_v015_field_taxonomy.json"),
        mapping_catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        inventory_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz"
        ),
        summary_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/"
            "provider_field_inventory_summary.json"
        ),
        output_dir=tmp_path,
        priorities=("P0", "P1"),
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["field_count"] == 33
    assert payload["summary"]["inventory_record_count"] == 6771
    assert payload["summary"]["fields_with_candidates"] >= 25
    revenue_candidates = payload["fields"]["revenue"]["providers"]["akshare"][
        "candidates"
    ]
    total_assets_candidates = payload["fields"]["total_assets"]["providers"]["yahoo"][
        "candidates"
    ]
    assert revenue_candidates[0]["strength"] == "strong"
    assert total_assets_candidates[0]["strength"] == "strong"
