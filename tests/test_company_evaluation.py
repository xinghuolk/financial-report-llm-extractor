"""Tests for company_evaluation module: bucket cascade + orchestrator."""

from __future__ import annotations

from typing import Any


def _make_export_item(
    field_id: str = "revenue",
    *,
    status: str = "present",
    selected_source: str | None = "akshare",
    conflict_classifications: tuple[str, ...] = (),
    review_notes: tuple[str, ...] = (),
    value_decimal: str = "100",
) -> Any:
    """Construct minimal SourceFirstExportItem for tests.

    Note: SourceFirstExportItem.value is `Decimal | None`, not `str`. Tests use
    Decimal(value_decimal) for present items.
    """
    from decimal import Decimal
    from financial_report_llm_extractor.structured_sources.export import (
        SourceFirstExportItem,
    )
    return SourceFirstExportItem(
        field_id=field_id,
        status=status,  # type: ignore[arg-type]
        selected_source=selected_source,
        value=Decimal(value_decimal) if status == "present" else None,
        currency="CNY",
        unit="raw",
        conflict_classifications=conflict_classifications,
        review_notes=review_notes,
    )


def _make_warning_item(category: str, *, field_id: str = "x") -> Any:
    from financial_report_llm_extractor.structured_sources.warning_classification import (
        WarningClassificationItem,
    )
    return WarningClassificationItem(
        field_id=field_id,
        category=category,  # type: ignore[arg-type]
        status="missing",
        reasons=(),
        review_notes=(),
        warnings=(),
        selected_source=None,
        candidate_sources=(),
        verification_required=False,
    )


def _make_mapping_entry(source_mode: str = "direct") -> Any:
    from financial_report_llm_extractor.structured_sources.catalog import (
        SourceMappingEntry,
    )
    return SourceMappingEntry(
        field_id="revenue",
        priority="P0",
        value_type="money",
        statement_type="income_statement",
        domain="income_statement",
        source_mode=source_mode,
        primary_route="akshare_direct",
        verification_status="expected",
        currency_requirement="required",
        unit_requirement="required",
        fallback_policy="pdf_allowed",
        source_aliases={},
        pdf_aliases=(),
    )


def test_classify_clean_present() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, reason = classify_field(
        export_item=_make_export_item(),
        warning_item=None,
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "clean_present"
    assert reason is None


def test_classify_unresolved_conflict() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, reason = classify_field(
        export_item=_make_export_item(conflict_classifications=("provider_value_mismatch",)),
        warning_item=None,
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "unresolved_conflict"
    assert "provider_value_mismatch" in (reason or "")


def test_classify_llm_supplement_present() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, _ = classify_field(
        export_item=_make_export_item(selected_source="llm"),
        warning_item=None,
        mapping_entry=_make_mapping_entry(source_mode="pdf_only"),
        pdf_provided=True,
    )

    assert bucket == "llm_supplement_present"


def test_classify_terminal_unverified_for_yahoo_definition_unverified() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, reason = classify_field(
        export_item=_make_export_item(status="missing", selected_source=None),
        warning_item=_make_warning_item("yahoo_definition_unverified"),
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "terminal_unverified"
    assert reason == "yahoo_definition_unverified"


def test_classify_not_in_scope_pdf_only_without_pdf() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, _ = classify_field(
        export_item=_make_export_item(status="missing", selected_source=None),
        warning_item=None,
        mapping_entry=_make_mapping_entry(source_mode="pdf_only"),
        pdf_provided=False,
    )

    assert bucket == "not_in_scope"


def test_classify_source_unavailable_default() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, reason = classify_field(
        export_item=_make_export_item(status="missing", selected_source=None),
        warning_item=_make_warning_item("source_unavailable"),
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "source_unavailable"
    assert reason == "source_unavailable"


def test_classify_cn_gross_profit_clean_not_terminal() -> None:
    """Review §"全局列表会错杀 CN clean": gross_profit clean via akshare_direct
    must land in clean_present, not terminal_unverified — even though it
    appears in the roadmap "Locked Terminal States" cohort that the original
    spec hardcoded."""
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, _ = classify_field(
        export_item=_make_export_item(field_id="gross_profit", selected_source="akshare"),
        warning_item=None,  # 关键：CN clean 时无 warning
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "clean_present"


def test_classify_clean_present_with_yahoo_pdf_verified_warning() -> None:
    """A field with status='present' AND a benign warning (yahoo_pdf_verified
    or source_policy_resolvable) must land in clean_present, NOT source_unavailable.

    Regression for review §"clean-with-warning" cascade gap.
    """
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, reason = classify_field(
        export_item=_make_export_item(selected_source="yahoo"),
        warning_item=_make_warning_item("yahoo_pdf_verified"),
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "clean_present"
    assert reason is None


def _build_minimal_catalog() -> Any:
    """3-field SourceMappingCatalog: P0=revenue, P1=gross_profit, P3=dividend_plan."""
    from financial_report_llm_extractor.structured_sources.catalog import (
        SourceMappingCatalog,
    )
    return SourceMappingCatalog(
        catalog_id="test-catalog",
        version="v0",
        entries={
            "revenue": _make_mapping_entry(source_mode="direct"),  # priority defaults P0
            "gross_profit": _replace(_make_mapping_entry(source_mode="direct"),
                                     field_id="gross_profit", priority="P1"),
            "dividend_plan": _replace(_make_mapping_entry(source_mode="pdf_only"),
                                      field_id="dividend_plan", priority="P3"),
        },
    )


def _build_minimal_taxonomy() -> Any:
    """Minimal FieldTaxonomyCatalog stub."""
    from financial_report_llm_extractor.field_metadata import FieldTaxonomyCatalog
    return FieldTaxonomyCatalog(
        catalog_id="test-taxonomy",
        version="v0",
        source_priority_catalog="test-priorities",
        fields={},
    )


def _replace(entry: Any, **kwargs: Any) -> Any:
    """Frozen-dataclass shallow replace helper for test fixtures."""
    import dataclasses
    return dataclasses.replace(entry, **kwargs)


def test_build_company_evaluation_counts_buckets_and_priorities() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        build_company_evaluation,
    )
    from financial_report_llm_extractor.structured_sources.export import (
        SourceFirstExportResult,
    )
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
    )
    from financial_report_llm_extractor.structured_sources.warning_classification import (
        WarningClassificationResult,
    )

    catalog = _build_minimal_catalog()
    taxonomy = _build_minimal_taxonomy()

    # Note: SourceFirstExportResult requires profile + catalog_id + catalog_version
    # + items: dict (NOT tuple).
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test-catalog",
        catalog_version="v0",
        items={
            "revenue": _make_export_item(field_id="revenue", status="present", selected_source="akshare"),
            "gross_profit": _make_export_item(field_id="gross_profit", status="missing", selected_source=None),
            "dividend_plan": _make_export_item(field_id="dividend_plan", status="missing", selected_source=None),
        },
    )
    warning = WarningClassificationResult(items={
        "gross_profit": _make_warning_item("yahoo_definition_unverified", field_id="gross_profit"),
    })

    evaluation = build_company_evaluation(
        company="01113",
        period=PeriodSpec.from_year(2024),
        market="HK",
        export=export,
        warning_classification=warning,
        supplement=None,
        catalog=catalog,
        taxonomy=taxonomy,
        pdf_provided=False,
    )

    assert evaluation.by_bucket["clean_present"] == 1
    assert evaluation.by_bucket["terminal_unverified"] == 1
    assert evaluation.by_bucket["not_in_scope"] == 1  # dividend_plan pdf_only

    assert evaluation.by_priority["P0"]["clean_present"] == 1
    assert evaluation.by_priority["P1"]["terminal_unverified"] == 1
    assert evaluation.by_priority["P3"]["not_in_scope"] == 1


def _build_sample_evaluation() -> Any:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        build_company_evaluation,
    )
    from financial_report_llm_extractor.structured_sources.export import (
        SourceFirstExportResult,
    )
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
    )
    from financial_report_llm_extractor.structured_sources.warning_classification import (
        WarningClassificationResult,
    )

    catalog = _build_minimal_catalog()
    taxonomy = _build_minimal_taxonomy()
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test-catalog",
        catalog_version="v0",
        items={
            "revenue": _make_export_item(field_id="revenue", status="present", selected_source="akshare"),
            "gross_profit": _make_export_item(field_id="gross_profit", status="missing", selected_source=None),
            "dividend_plan": _make_export_item(field_id="dividend_plan", status="missing", selected_source=None),
        },
    )
    warning = WarningClassificationResult(items={
        "gross_profit": _make_warning_item("yahoo_definition_unverified", field_id="gross_profit"),
    })

    return build_company_evaluation(
        company="01113",
        period=PeriodSpec.from_year(2024),
        market="HK",
        export=export,
        warning_classification=warning,
        supplement=None,
        catalog=catalog,
        taxonomy=taxonomy,
        pdf_provided=False,
    )


def test_render_evaluation_markdown_lists_priority_bucket_grid() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        render_evaluation_markdown,
    )

    evaluation = _build_sample_evaluation()
    md = render_evaluation_markdown(evaluation)

    assert "01113" in md  # company
    assert "2024-12-31" in md  # period
    assert "clean_present" in md
    assert "P0" in md and "P3" in md
    # 不出现 "% clean" 字面 —— 与 drift §177 一致
    assert "% clean" not in md.lower()
    assert "/ total" not in md.lower()
