"""Phase 1a: client.py public API — enums, dataclasses, exception."""

from __future__ import annotations

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
