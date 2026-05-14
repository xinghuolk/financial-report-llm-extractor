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
