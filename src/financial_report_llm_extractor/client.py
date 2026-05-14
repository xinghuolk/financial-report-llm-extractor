"""FinancialReportClient — Phase 1a public API.

This module is the entire public API surface of financial-report-llm-extractor
for downstream consumers (e.g. TradingAgents-CN). Internal modules (cache,
structured_sources, cli) are implementation details and should NOT be imported
by downstream code.

See docs/superpowers/specs/2026-05-13-financial-report-client-productization-design.md
"""

from __future__ import annotations

import hashlib
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


def compute_extraction_id(
    *,
    company: str,
    period_end: str,
    market: str,
    catalog_version: str,
    generated_at: str,
) -> str:
    """Return the 32-char hex prefix of SHA-256(keys joined by '|').

    Downstream consumers use this as a foreign key in their derived-data
    DB; same (company, period_end, market, catalog_version, generated_at)
    always produces the same id.
    """
    canonical = f"{company}|{period_end}|{market}|{catalog_version}|{generated_at}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class ExtractionResult:
    """A single extraction snapshot.

    Callers MUST guard staleness before iterating fields:

        if result.staleness.is_missing:
            skip()
        elif result.staleness.is_stale:
            warn_then_decide()
        else:
            use_fields(result.fields)
    """

    company: str
    period_end: str
    market: str
    catalog_version: str
    generated_at: str
    extraction_id: str
    staleness: Staleness
    fields: dict[str, FieldValue]
    llm_provider: str | None = None
    llm_model: str | None = None


class ExtractorError(Exception):
    """Unified internal exception wrapper.

    All exceptions that escape the client are wrapped as ExtractorError
    with a stable `reason` code. Internal exceptions (sqlite3.OperationalError,
    subprocess.CalledProcessError, urllib.error.URLError, etc.) are caught
    at the client boundary and never leak to downstream.

    Stable reason codes:
      unsupported_market  — market not in {"CN", "HK"}
      invalid_period      — period_end not a valid ISO date
      unknown_field       — field_id not in taxonomy
      pdf_not_found       — pdf_resolver returned None or file missing
      llm_config_missing  — include_llm_supplement requires LLM config
      fetch_failed        — pipeline fetch stage raised
      evaluate_failed     — pipeline evaluate stage raised
      db_not_initialized  — DB not found and refresh_policy=CACHE_ONLY
    """

    def __init__(
        self,
        *,
        reason: str,
        message: str,
        company: str | None = None,
        period_end: str | None = None,
        market: str | None = None,
        cause_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.company = company
        self.period_end = period_end
        self.market = market
        self.cause_type = cause_type
