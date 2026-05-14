"""Bucket → ConfidenceLevel translation + LLM filter behavior."""

from __future__ import annotations


def test_bucket_to_confidence_clean_present_is_verified() -> None:
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        bucket_to_confidence,
    )

    assert bucket_to_confidence("clean_present") == ConfidenceLevel.VERIFIED


def test_bucket_to_confidence_llm_supplement_is_llm() -> None:
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        bucket_to_confidence,
    )

    assert (
        bucket_to_confidence("llm_supplement_present")
        == ConfidenceLevel.LLM_SUPPLEMENT
    )


def test_bucket_to_confidence_unresolved_conflict_is_ambiguous() -> None:
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        bucket_to_confidence,
    )

    assert (
        bucket_to_confidence("unresolved_conflict")
        == ConfidenceLevel.AMBIGUOUS
    )


def test_bucket_to_confidence_terminal_unverified_is_unavailable() -> None:
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        bucket_to_confidence,
    )

    assert (
        bucket_to_confidence("terminal_unverified")
        == ConfidenceLevel.UNAVAILABLE
    )


def test_bucket_to_confidence_source_unavailable_is_unavailable() -> None:
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        bucket_to_confidence,
    )

    assert (
        bucket_to_confidence("source_unavailable")
        == ConfidenceLevel.UNAVAILABLE
    )


def test_bucket_to_confidence_not_in_scope_is_unavailable() -> None:
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        bucket_to_confidence,
    )

    assert (
        bucket_to_confidence("not_in_scope") == ConfidenceLevel.UNAVAILABLE
    )


def test_bucket_to_confidence_unknown_bucket_is_unavailable() -> None:
    """Defensive: unknown bucket name maps to UNAVAILABLE."""
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        bucket_to_confidence,
    )

    assert (
        bucket_to_confidence("some_future_bucket")
        == ConfidenceLevel.UNAVAILABLE
    )


def test_build_field_value_clean_present_with_decimal_value() -> None:
    """build_field_value reads a row dict (from query_extraction) and
    constructs a FieldValue with Decimal-decoded value for money/number fields."""
    from decimal import Decimal
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        build_field_value,
    )

    # Simulate what query_extraction would return for a clean_present money field.
    # NOTE: db_query._decode_field_row already json.loads'd the value column,
    # so `value` here is the inner Python value (str for stringified numbers).
    db_row = {
        "bucket": "clean_present",
        "value": "170899152276.34",
        "currency": "CNY",
        "unit": "yuan",
        "selected_source": "akshare",
        "reason": None,
        "evidence_page": None,
        "llm_confidence": None,
        "llm_reasoning_short": None,
        "priority": "P0",
    }
    field_taxonomy = {"value_type": "money"}

    fv = build_field_value(
        field_id="revenue",
        db_row=db_row,
        field_taxonomy=field_taxonomy,
        include_llm_supplement=True,
    )
    assert fv.field_id == "revenue"
    assert fv.value == Decimal("170899152276.34")
    assert isinstance(fv.value, Decimal)
    assert fv.confidence == ConfidenceLevel.VERIFIED
    assert fv.is_reliable is True
    assert fv.source == "akshare"
    assert fv.raw_bucket == "clean_present"


def test_build_field_value_llm_supplement_kept_when_included() -> None:
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        build_field_value,
    )

    db_row = {
        "bucket": "llm_supplement_present",
        "value": "标准无保留意见",
        "currency": "unknown",
        "unit": None,
        "selected_source": "llm",
        "reason": None,
        "evidence_page": 55,
        "llm_confidence": 0.98,
        "llm_reasoning_short": "审计意见",
        "priority": "P4",
    }
    field_taxonomy = {"value_type": "text"}

    fv = build_field_value(
        field_id="audit_opinion",
        db_row=db_row,
        field_taxonomy=field_taxonomy,
        include_llm_supplement=True,
    )
    assert fv.value == "标准无保留意见"
    assert fv.confidence == ConfidenceLevel.LLM_SUPPLEMENT
    assert fv.is_reliable is False
    assert fv.is_present is True
    assert fv.verification_required is True
    assert fv.evidence_page == 55


def test_build_field_value_llm_supplement_filtered_when_excluded() -> None:
    """When include_llm_supplement=False, LLM_SUPPLEMENT field is returned
    as UNAVAILABLE placeholder (not silently dropped)."""
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        build_field_value,
    )

    db_row = {
        "bucket": "llm_supplement_present",
        "value": "opinion text",
        "currency": None,
        "unit": None,
        "selected_source": "llm",
        "reason": None,
        "evidence_page": 55,
        "llm_confidence": 0.98,
        "llm_reasoning_short": None,
        "priority": "P4",
    }
    field_taxonomy = {"value_type": "text"}

    fv = build_field_value(
        field_id="audit_opinion",
        db_row=db_row,
        field_taxonomy=field_taxonomy,
        include_llm_supplement=False,
    )
    assert fv.confidence == ConfidenceLevel.UNAVAILABLE
    assert fv.value is None
    assert fv.raw_bucket == "llm_supplement_present"
    assert fv.reason == "llm_supplement_filtered"
    assert fv.is_reliable is False
    assert fv.is_present is False


def test_build_field_value_unresolved_conflict_value_is_none() -> None:
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        build_field_value,
    )

    db_row = {
        "bucket": "unresolved_conflict",
        "value": None,
        "currency": "CNY",
        "unit": None,
        "selected_source": None,
        "reason": "missing_source_candidate",
        "evidence_page": None,
        "llm_confidence": None,
        "llm_reasoning_short": None,
        "priority": "P0",
    }
    field_taxonomy = {"value_type": "money"}

    fv = build_field_value(
        field_id="fix_assets",
        db_row=db_row,
        field_taxonomy=field_taxonomy,
        include_llm_supplement=True,
    )
    assert fv.value is None
    assert fv.confidence == ConfidenceLevel.AMBIGUOUS
    assert fv.reason == "missing_source_candidate"


def test_build_field_value_currency_unknown_normalized_to_none() -> None:
    """Spec: 'unknown' currency string is normalized to None."""
    from financial_report_llm_extractor.client import build_field_value

    db_row = {
        "bucket": "llm_supplement_present",
        "value": "x",
        "currency": "unknown",
        "unit": None,
        "selected_source": "llm",
        "reason": None,
        "evidence_page": None,
        "llm_confidence": None,
        "llm_reasoning_short": None,
        "priority": "P4",
    }
    field_taxonomy = {"value_type": "text"}

    fv = build_field_value(
        field_id="audit_opinion",
        db_row=db_row,
        field_taxonomy=field_taxonomy,
        include_llm_supplement=True,
    )
    assert fv.currency is None
