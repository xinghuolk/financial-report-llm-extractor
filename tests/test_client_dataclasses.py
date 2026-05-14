"""Phase 1a: client.py public API — enums, dataclasses, exception."""

from __future__ import annotations

import pytest

def test_confidence_level_enum_values() -> None:
    from financial_report_llm_extractor.client import ConfidenceLevel

    assert ConfidenceLevel.VERIFIED.value == "verified"
    assert ConfidenceLevel.LLM_SUPPLEMENT.value == "llm_supplement"
    assert ConfidenceLevel.AMBIGUOUS.value == "ambiguous"
    assert ConfidenceLevel.UNAVAILABLE.value == "unavailable"


def test_refresh_policy_enum_values() -> None:
    from financial_report_llm_extractor.client import RefreshPolicy

    assert RefreshPolicy.CACHE_ONLY.value == "cache_only"
    assert RefreshPolicy.CACHE_FIRST.value == "cache_first"
    assert RefreshPolicy.FORCE_REFRESH.value == "force_refresh"


def test_staleness_enum_and_properties() -> None:
    from financial_report_llm_extractor.client import Staleness

    assert Staleness.FRESH.value == "fresh"
    assert Staleness.STALE.value == "stale"
    assert Staleness.MISSING.value == "missing"

    assert Staleness.FRESH.is_fresh is True
    assert Staleness.FRESH.is_stale is False
    assert Staleness.FRESH.is_missing is False

    assert Staleness.STALE.is_fresh is False
    assert Staleness.STALE.is_stale is True
    assert Staleness.STALE.is_missing is False

    assert Staleness.MISSING.is_fresh is False
    assert Staleness.MISSING.is_stale is False
    assert Staleness.MISSING.is_missing is True


def test_pdf_query_is_kw_only() -> None:
    """PdfQuery must reject positional construction (frozen + kw_only)."""
    from financial_report_llm_extractor.client import PdfQuery

    # kwargs work
    q = PdfQuery(company="600519", period_end="2024-12-31", market="CN")
    assert q.company == "600519"
    assert q.period_end == "2024-12-31"
    assert q.market == "CN"

    # positional raises TypeError
    with pytest.raises(TypeError):
        PdfQuery("600519", "2024-12-31", "CN")  # type: ignore[call-arg,misc]


def test_pdf_query_is_frozen() -> None:
    from dataclasses import FrozenInstanceError
    from financial_report_llm_extractor.client import PdfQuery

    q = PdfQuery(company="600519", period_end="2024-12-31", market="CN")
    with pytest.raises(FrozenInstanceError):
        q.company = "300750"  # type: ignore[misc]


def test_extractor_config_defaults_all_none() -> None:
    from financial_report_llm_extractor.client import ExtractorConfig

    cfg = ExtractorConfig()
    assert cfg.llm_config_path is None
    assert cfg.pdf_resolver is None
    assert cfg.cache_root is None
    assert cfg.db_path is None
    assert cfg.catalog_path is None
    assert cfg.taxonomy_path is None


def test_extractor_config_frozen() -> None:
    from dataclasses import FrozenInstanceError
    from financial_report_llm_extractor.client import ExtractorConfig

    cfg = ExtractorConfig()
    with pytest.raises(FrozenInstanceError):
        cfg.llm_config_path = None  # type: ignore[misc]


def test_field_value_construction_and_frozen() -> None:
    from decimal import Decimal
    from dataclasses import FrozenInstanceError
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        FieldValue,
    )

    fv = FieldValue(
        field_id="revenue",
        value=Decimal("170899152276.34"),
        currency="CNY",
        unit="yuan",
        confidence=ConfidenceLevel.VERIFIED,
        source="akshare",
        evidence_page=None,
        raw_bucket="clean_present",
    )
    assert fv.field_id == "revenue"
    assert fv.value == Decimal("170899152276.34")
    assert fv.reason is None  # default

    with pytest.raises(FrozenInstanceError):
        fv.value = Decimal("0")  # type: ignore[misc]


def test_field_value_is_reliable() -> None:
    from financial_report_llm_extractor.client import ConfidenceLevel, FieldValue

    verified = FieldValue(
        field_id="revenue", value="1", currency=None, unit=None,
        confidence=ConfidenceLevel.VERIFIED, source="akshare",
        evidence_page=None, raw_bucket="clean_present",
    )
    assert verified.is_reliable is True

    llm = FieldValue(
        field_id="audit_opinion", value="opinion text", currency=None, unit=None,
        confidence=ConfidenceLevel.LLM_SUPPLEMENT, source="llm",
        evidence_page=55, raw_bucket="llm_supplement_present",
    )
    assert llm.is_reliable is False

    ambiguous = FieldValue(
        field_id="fix_assets", value=None, currency=None, unit=None,
        confidence=ConfidenceLevel.AMBIGUOUS, source=None,
        evidence_page=None, raw_bucket="unresolved_conflict",
    )
    assert ambiguous.is_reliable is False


def test_field_value_is_present() -> None:
    from financial_report_llm_extractor.client import ConfidenceLevel, FieldValue

    present = FieldValue(
        field_id="x", value="some_value", currency=None, unit=None,
        confidence=ConfidenceLevel.VERIFIED, source="akshare",
        evidence_page=None, raw_bucket="clean_present",
    )
    assert present.is_present is True

    absent = FieldValue(
        field_id="x", value=None, currency=None, unit=None,
        confidence=ConfidenceLevel.UNAVAILABLE, source=None,
        evidence_page=None, raw_bucket="source_unavailable",
    )
    assert absent.is_present is False


def test_field_value_verification_required_derived_from_source() -> None:
    """verification_required is a @property derived from source ==
    'llm', not a stored field."""
    from financial_report_llm_extractor.client import ConfidenceLevel, FieldValue

    llm_field = FieldValue(
        field_id="audit_opinion", value="opinion", currency=None, unit=None,
        confidence=ConfidenceLevel.LLM_SUPPLEMENT, source="llm",
        evidence_page=55, raw_bucket="llm_supplement_present",
    )
    assert llm_field.verification_required is True

    akshare_field = FieldValue(
        field_id="revenue", value="1", currency=None, unit=None,
        confidence=ConfidenceLevel.VERIFIED, source="akshare",
        evidence_page=None, raw_bucket="clean_present",
    )
    assert akshare_field.verification_required is False

    no_source = FieldValue(
        field_id="x", value=None, currency=None, unit=None,
        confidence=ConfidenceLevel.UNAVAILABLE, source=None,
        evidence_page=None, raw_bucket="source_unavailable",
    )
    assert no_source.verification_required is False


def test_extraction_id_is_deterministic_sha256_prefix() -> None:
    """Same (company, period_end, market, catalog_version, generated_at)
    → same extraction_id; different → different."""
    from financial_report_llm_extractor.client import compute_extraction_id

    a = compute_extraction_id(
        company="600519",
        period_end="2024-12-31",
        market="CN",
        catalog_version="2026-05-02",
        generated_at="2026-05-13T10:00:00",
    )
    b = compute_extraction_id(
        company="600519",
        period_end="2024-12-31",
        market="CN",
        catalog_version="2026-05-02",
        generated_at="2026-05-13T10:00:00",
    )
    assert a == b
    assert len(a) == 32  # 32 hex chars per spec
    assert all(c in "0123456789abcdef" for c in a)


def test_extraction_id_changes_on_any_key_change() -> None:
    from financial_report_llm_extractor.client import compute_extraction_id

    base = dict(
        company="600519", period_end="2024-12-31", market="CN",
        catalog_version="2026-05-02", generated_at="2026-05-13T10:00:00",
    )
    base_id = compute_extraction_id(**base)
    for diff_field in ("company", "period_end", "market", "catalog_version", "generated_at"):
        kwargs = dict(base)
        kwargs[diff_field] = kwargs[diff_field] + "x"
        assert compute_extraction_id(**kwargs) != base_id, (
            f"changing {diff_field} should produce different extraction_id"
        )


def test_extraction_result_construction() -> None:
    from financial_report_llm_extractor.client import (
        ExtractionResult,
        Staleness,
    )

    r = ExtractionResult(
        company="600519",
        period_end="2024-12-31",
        market="CN",
        catalog_version="2026-05-02",
        generated_at="2026-05-13T10:00:00",
        extraction_id="a" * 32,
        staleness=Staleness.FRESH,
        fields={},
    )
    assert r.staleness.is_fresh
    assert r.fields == {}
    assert r.llm_provider is None  # default
    assert r.llm_model is None     # default


def test_extractor_error_init_and_attributes() -> None:
    from financial_report_llm_extractor.client import ExtractorError

    err = ExtractorError(
        reason="fetch_failed",
        message="AKShare returned 500",
        company="600519",
        period_end="2024-12-31",
        market="CN",
        cause_type="urllib.error.HTTPError",
    )
    assert err.reason == "fetch_failed"
    assert err.message == "AKShare returned 500"
    assert err.company == "600519"
    assert err.period_end == "2024-12-31"
    assert err.market == "CN"
    assert err.cause_type == "urllib.error.HTTPError"
    # also catchable as plain Exception
    assert isinstance(err, Exception)
    # __str__ uses message
    assert "AKShare returned 500" in str(err)


def test_extractor_error_optional_fields() -> None:
    from financial_report_llm_extractor.client import ExtractorError

    err = ExtractorError(reason="invalid_period", message="bad date")
    assert err.company is None
    assert err.period_end is None
    assert err.market is None
    assert err.cause_type is None


def test_extractor_error_raise_and_catch() -> None:
    from financial_report_llm_extractor.client import ExtractorError

    with pytest.raises(ExtractorError) as excinfo:
        raise ExtractorError(reason="unknown_field", message="no such field")
    assert excinfo.value.reason == "unknown_field"
