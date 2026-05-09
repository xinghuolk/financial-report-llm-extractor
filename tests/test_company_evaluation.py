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
