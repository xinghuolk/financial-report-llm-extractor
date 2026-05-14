"""FinancialReportClient — Phase 1a public API.

This module is the entire public API surface of financial-report-llm-extractor
for downstream consumers (e.g. TradingAgents-CN). Internal modules (cache,
structured_sources, cli) are implementation details and should NOT be imported
by downstream code.

See docs/superpowers/specs/2026-05-13-financial-report-client-productization-design.md
"""

from __future__ import annotations

from enum import Enum


class ConfidenceLevel(Enum):
    """Bucket → runtime reliability translation.

    VERIFIED: clean_present — safe for structured computation
    LLM_SUPPLEMENT: llm_supplement_present — opt-in with caveat
    AMBIGUOUS: unresolved_conflict — display only, do not compute
    UNAVAILABLE: terminal_unverified / source_unavailable / not_in_scope
    """

    VERIFIED = "verified"
    LLM_SUPPLEMENT = "llm_supplement"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"


class RefreshPolicy(Enum):
    """Caller control over cache vs fresh-fetch behavior."""

    CACHE_ONLY = "cache_only"        # DB miss → MISSING; no pipeline run
    CACHE_FIRST = "cache_first"      # DB hit (incl. stale) returned; miss → run pipeline
    FORCE_REFRESH = "force_refresh"  # Always run pipeline


class Staleness(Enum):
    """Result freshness state. Callers MUST check before iterating fields."""

    FRESH = "fresh"
    STALE = "stale"
    MISSING = "missing"

    @property
    def is_fresh(self) -> bool:
        return self == Staleness.FRESH

    @property
    def is_stale(self) -> bool:
        return self == Staleness.STALE

    @property
    def is_missing(self) -> bool:
        return self == Staleness.MISSING
