"""FinancialReportClient — Phase 1a public API.

This module is the entire public API surface of financial-report-llm-extractor
for downstream consumers (e.g. TradingAgents-CN). Internal modules (cache,
structured_sources, cli) are implementation details and should NOT be imported
by downstream code.

See docs/superpowers/specs/2026-05-13-financial-report-client-productization-design.md
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Callable


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


@dataclass(frozen=True, kw_only=True)
class PdfQuery:
    """Keyword-only dataclass for pdf_resolver to prevent positional misuse."""

    company: str
    period_end: str
    market: str


@dataclass(frozen=True)
class ExtractorConfig:
    """Caller-supplied configuration. All fields optional; None = use default.

    Default resolution (see Task 9):
      - catalog_path / taxonomy_path: importlib.resources packaged data
      - cache_root: $FR_LLM_CACHE_ROOT or ~/.cache/financial-report-llm-extractor/
      - db_path: <cache_root>/extracted.db
    """

    llm_config_path: Path | None = None
    pdf_resolver: Callable[[PdfQuery], Path | None] | None = None
    cache_root: Path | None = None
    db_path: Path | None = None
    catalog_path: Path | None = None
    taxonomy_path: Path | None = None


@dataclass(frozen=True)
class FieldValue:
    """A single field's extraction result with reliability metadata.

    `value` is typed `Decimal | str | bool | None`:
      money/number  → Decimal
      text          → str
      boolean       → bool
      None when value is absent or filtered

    `raw_bucket` preserves the source-first bucket name for audit; business
    logic should branch on `confidence` (ConfidenceLevel) instead.
    """

    field_id: str
    value: Decimal | str | bool | None
    currency: str | None
    unit: str | None
    confidence: ConfidenceLevel
    source: str | None
    evidence_page: int | None
    raw_bucket: str
    reason: str | None = None

    @property
    def is_reliable(self) -> bool:
        return self.confidence == ConfidenceLevel.VERIFIED

    @property
    def is_present(self) -> bool:
        return self.value is not None

    @property
    def verification_required(self) -> bool:
        """True for LLM-sourced values (downstream should apply confidence
        threshold / consensus check before relying on them)."""
        return self.source == "llm"
