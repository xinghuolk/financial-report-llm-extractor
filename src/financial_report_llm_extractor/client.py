"""FinancialReportClient — Phase 1a public API.

This module is the entire public API surface of financial-report-llm-extractor
for downstream consumers (e.g. TradingAgents-CN). Internal modules (cache,
structured_sources, cli) are implementation details and should NOT be imported
by downstream code.

See docs/superpowers/specs/2026-05-13-financial-report-client-productization-design.md
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from importlib.resources import files as _pkg_files
from pathlib import Path
from typing import Any, Callable


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
    subscription_token: str | None = None


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



def resolve_catalog_path(*, override: Path | None) -> Path:
    """Return path to source_mapping_minimal catalog. Override > packaged > editable-tree."""
    if override is not None:
        return override
    # Packaged catalog via importlib.resources (pyproject force-include).
    # This works in wheel install (where _catalog_data/ exists in the
    # installed package directory).
    try:
        resource = _pkg_files("financial_report_llm_extractor").joinpath(
            "_catalog_data", "turtle_v015_source_mapping_minimal.json"
        )
        packaged_path = Path(str(resource))
        if packaged_path.exists():
            return packaged_path
    except (ModuleNotFoundError, FileNotFoundError):
        pass
    # Editable-install fallback: walk up from __file__ to find repo-root
    # field_catalog/ directory. __file__ is src/financial_report_llm_extractor/client.py
    # so parent.parent.parent = repo root.
    editable_root = Path(__file__).resolve().parent.parent.parent
    editable_path = editable_root / "field_catalog" / "turtle_v015_source_mapping_minimal.json"
    if editable_path.exists():
        return editable_path
    # Last-resort: CWD-relative (preserves old behavior for unusual setups).
    return Path("field_catalog/turtle_v015_source_mapping_minimal.json")


def resolve_taxonomy_path(*, override: Path | None) -> Path:
    """Return path to field_taxonomy. Override > packaged > editable-tree."""
    if override is not None:
        return override
    # Packaged catalog via importlib.resources (pyproject force-include).
    try:
        resource = _pkg_files("financial_report_llm_extractor").joinpath(
            "_catalog_data", "turtle_v015_field_taxonomy.json"
        )
        packaged_path = Path(str(resource))
        if packaged_path.exists():
            return packaged_path
    except (ModuleNotFoundError, FileNotFoundError):
        pass
    # Editable-install fallback: walk up from __file__ to find repo-root.
    editable_root = Path(__file__).resolve().parent.parent.parent
    editable_path = editable_root / "field_catalog" / "turtle_v015_field_taxonomy.json"
    if editable_path.exists():
        return editable_path
    # Last-resort: CWD-relative.
    return Path("field_catalog/turtle_v015_field_taxonomy.json")


def resolve_cache_root(*, override: Path | None) -> Path:
    """Return cache_root path. Precedence: override > env var > user home."""
    if override is not None:
        return override
    env = os.environ.get("FR_LLM_CACHE_ROOT")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "financial-report-llm-extractor"


def resolve_db_path(*, override: Path | None, cache_root: Path) -> Path:
    """db_path defaults to <cache_root>/extracted.db."""
    if override is not None:
        return override
    return cache_root / "extracted.db"


class FinancialReportClient:
    """The public API surface of financial-report-llm-extractor.

    Downstream consumers (e.g. TradingAgents-CN) instantiate this client
    once and use it to query extracted financial-report data.

    See docs/superpowers/specs/2026-05-13-financial-report-client-productization-design.md
    """

    def __init__(self, config: ExtractorConfig | None = None) -> None:
        self.config = config or ExtractorConfig()
        # Resolve and cache the taxonomy at init for fast catalog_fields()
        # and catalog_version() lookups.
        self._taxonomy_path = resolve_taxonomy_path(
            override=self.config.taxonomy_path
        )
        self._catalog_path = resolve_catalog_path(
            override=self.config.catalog_path
        )
        self._cache_root = resolve_cache_root(
            override=self.config.cache_root
        )
        self._db_path = resolve_db_path(
            override=self.config.db_path, cache_root=self._cache_root,
        )
        # Load taxonomy once (small file).
        self._taxonomy_doc = json.loads(
            self._taxonomy_path.read_text(encoding="utf-8")
        )

    def catalog_fields(self) -> tuple[str, ...]:
        """Return all field_ids known to the current catalog (taxonomy)."""
        fields = self._taxonomy_doc.get("fields", {})
        return tuple(sorted(fields.keys()))

    def catalog_version(self) -> str:
        """Return current catalog version (= taxonomy.version)."""
        return str(self._taxonomy_doc.get("version", "unknown"))

    def get_status(
        self,
        *,
        company: str,
        period_end: str,
        market: str,
    ) -> Staleness:
        """Lightweight DB lookup. Returns FRESH/STALE/MISSING."""
        from financial_report_llm_extractor.cache.db_query import (
            query_extraction,
        )

        try:
            hit = query_extraction(
                db_path=self._db_path,
                company=company,
                period_end=period_end,
                market=market,
            )
        except Exception:
            return Staleness.MISSING
        if hit is None:
            return Staleness.MISSING
        if hit.get("catalog_version") == self.catalog_version():
            return Staleness.FRESH
        return Staleness.STALE

    def get_extraction(
        self,
        *,
        company: str,
        period_end: str,
        market: str,
        include_llm_supplement: bool = False,
        refresh_policy: RefreshPolicy = RefreshPolicy.CACHE_FIRST,
        subscription_token: str | None = None,
    ) -> ExtractionResult:
        """Return an ExtractionResult for the given (company, period_end, market).

        See spec §Client Methods for full behavior table.
        """
        if market not in {"CN", "HK"}:
            raise ExtractorError(
                reason="unsupported_market",
                message=f"market must be 'CN' or 'HK', got {market!r}",
                company=company, period_end=period_end, market=market,
            )

        from financial_report_llm_extractor.cache.db_query import (
            query_extraction,
        )

        # Step 1: try DB read.
        try:
            hit = query_extraction(
                db_path=self._db_path,
                company=company,
                period_end=period_end,
                market=market,
            )
        except Exception as exc:
            if refresh_policy == RefreshPolicy.CACHE_ONLY:
                raise ExtractorError(
                    reason="db_not_initialized",
                    message=f"DB lookup failed: {exc}",
                    company=company, period_end=period_end, market=market,
                    cause_type=type(exc).__name__,
                ) from exc
            hit = None

        current_version = self.catalog_version()

        # CACHE_ONLY: never trigger pipeline.
        if refresh_policy == RefreshPolicy.CACHE_ONLY:
            return self._materialize_from_hit(
                hit=hit, company=company, period_end=period_end,
                market=market, current_version=current_version,
                include_llm_supplement=include_llm_supplement,
            )

        # CACHE_FIRST: hit wins (even stale).
        if (
            refresh_policy == RefreshPolicy.CACHE_FIRST
            and hit is not None
        ):
            return self._materialize_from_hit(
                hit=hit, company=company, period_end=period_end,
                market=market, current_version=current_version,
                include_llm_supplement=include_llm_supplement,
            )

        # FORCE_REFRESH, or CACHE_FIRST miss: run pipeline, re-query DB.
        # Defensive: ensure required config for LLM step.
        if include_llm_supplement and self.config.llm_config_path is None:
            raise ExtractorError(
                reason="llm_config_missing",
                message="include_llm_supplement=True requires llm_config_path",
                company=company, period_end=period_end, market=market,
            )

        try:
            pdf_path = self._resolve_pdf_path(
                company=company, period_end=period_end, market=market,
                require=include_llm_supplement,
            )
        except ExtractorError:
            raise
        except Exception as exc:
            raise ExtractorError(
                reason="pdf_not_found",
                message=str(exc),
                company=company, period_end=period_end, market=market,
                cause_type=type(exc).__name__,
            ) from exc

        from financial_report_llm_extractor.pipeline_core import run_pipeline

        # Out_dir for the fresh run — under cache_root for cleanliness.
        run_out_dir = (
            self._cache_root / "runs" / f"{company}_{period_end}_{market}"
        )
        try:
            run_pipeline(
                company=company,
                period_end=period_end,
                market=market,
                report_type="annual",  # default for client; CLI exposes override
                db_path=self._db_path,
                out_dir=run_out_dir,
                catalog_path=self._catalog_path,
                taxonomy_path=self._taxonomy_path,
                priorities=("P0", "P1", "P2", "P3", "P4"),
                pdf_path=pdf_path if include_llm_supplement else None,
                llm_config_path=(
                    self.config.llm_config_path
                    if include_llm_supplement else None
                ),
                force=(refresh_policy == RefreshPolicy.FORCE_REFRESH),
                no_cache=False,
                subscription_token=self.config.subscription_token,
            )
        except Exception as exc:
            # Distinguish fetch vs evaluate failures by heuristic on exc type
            # (out of scope for v1 — coarse map to fetch_failed).
            reason = (
                "evaluate_failed"
                if "evaluat" in str(exc).lower()
                else "fetch_failed"
            )
            raise ExtractorError(
                reason=reason,
                message=str(exc),
                company=company, period_end=period_end, market=market,
                cause_type=type(exc).__name__,
            ) from exc

        # Re-query DB after fresh run.
        hit = query_extraction(
            db_path=self._db_path,
            company=company,
            period_end=period_end,
            market=market,
        )
        return self._materialize_from_hit(
            hit=hit, company=company, period_end=period_end,
            market=market, current_version=current_version,
            include_llm_supplement=include_llm_supplement,
        )

    def get_field(
        self,
        *,
        company: str,
        period_end: str,
        market: str,
        field_id: str,
        include_llm_supplement: bool = False,
        refresh_policy: RefreshPolicy = RefreshPolicy.CACHE_FIRST,
    ) -> FieldValue:
        """Return a single FieldValue.

        Raises ExtractorError(reason='unknown_field') if field_id is not in
        the taxonomy. If in taxonomy but no DB data, returns UNAVAILABLE
        placeholder.
        """
        if field_id not in self._taxonomy_doc.get("fields", {}):
            raise ExtractorError(
                reason="unknown_field",
                message=f"field_id {field_id!r} not in taxonomy",
                company=company, period_end=period_end, market=market,
            )

        result = self.get_extraction(
            company=company,
            period_end=period_end,
            market=market,
            include_llm_supplement=include_llm_supplement,
            refresh_policy=refresh_policy,
        )
        if field_id in result.fields:
            return result.fields[field_id]

        # In taxonomy but DB has no row → return UNAVAILABLE placeholder.
        return FieldValue(
            field_id=field_id,
            value=None,
            currency=None,
            unit=None,
            confidence=ConfidenceLevel.UNAVAILABLE,
            source=None,
            evidence_page=None,
            raw_bucket="not_in_extraction",
            reason="no_db_row",
        )

    def _resolve_pdf_path(
        self,
        *,
        company: str,
        period_end: str,
        market: str,
        require: bool,
    ) -> Path | None:
        """Use pdf_resolver if set; return None if not required."""
        if self.config.pdf_resolver is None:
            if require:
                raise ExtractorError(
                    reason="pdf_not_found",
                    message="pdf_resolver not configured",
                    company=company, period_end=period_end, market=market,
                )
            return None
        path = self.config.pdf_resolver(
            PdfQuery(company=company, period_end=period_end, market=market)
        )
        if path is None or not path.exists():
            if require:
                raise ExtractorError(
                    reason="pdf_not_found",
                    message=f"pdf_resolver returned {path!r}; not usable",
                    company=company, period_end=period_end, market=market,
                )
            return None
        return path

    def _materialize_from_hit(
        self,
        *,
        hit: dict[str, Any] | None,
        company: str,
        period_end: str,
        market: str,
        current_version: str,
        include_llm_supplement: bool,
    ) -> ExtractionResult:
        """Build an ExtractionResult from a query_extraction hit (or None)."""
        if hit is None:
            return ExtractionResult(
                company=company,
                period_end=period_end,
                market=market,
                catalog_version=current_version,
                generated_at="",
                extraction_id="",
                staleness=Staleness.MISSING,
                fields={},
            )

        catalog_version = str(hit.get("catalog_version", current_version))
        staleness = (
            Staleness.FRESH
            if catalog_version == current_version
            else Staleness.STALE
        )
        generated_at = str(hit.get("generated_at", ""))
        taxonomy_fields = self._taxonomy_doc.get("fields", {})

        fields: dict[str, FieldValue] = {}
        for field_id, db_row in hit.get("fields", {}).items():
            field_taxonomy = taxonomy_fields.get(field_id, {})
            fv = build_field_value(
                field_id=field_id,
                db_row=db_row,
                field_taxonomy=field_taxonomy,
                include_llm_supplement=include_llm_supplement,
            )
            fields[field_id] = fv

        return ExtractionResult(
            company=company,
            period_end=period_end,
            market=market,
            catalog_version=catalog_version,
            generated_at=generated_at,
            extraction_id=compute_extraction_id(
                company=company,
                period_end=period_end,
                market=market,
                catalog_version=catalog_version,
                generated_at=generated_at,
            ),
            staleness=staleness,
            fields=fields,
            llm_provider=hit.get("llm_provider"),
            llm_model=hit.get("llm_model"),
        )


_BUCKET_TO_CONFIDENCE: dict[str, ConfidenceLevel] = {
    "clean_present": ConfidenceLevel.VERIFIED,
    "llm_supplement_present": ConfidenceLevel.LLM_SUPPLEMENT,
    "unresolved_conflict": ConfidenceLevel.AMBIGUOUS,
    "terminal_unverified": ConfidenceLevel.UNAVAILABLE,
    "source_unavailable": ConfidenceLevel.UNAVAILABLE,
    "not_in_scope": ConfidenceLevel.UNAVAILABLE,
}


def bucket_to_confidence(bucket: str) -> ConfidenceLevel:
    """Translate source-first bucket → runtime ConfidenceLevel.

    Unknown buckets map to UNAVAILABLE (defensive). raw_bucket on the
    returned FieldValue preserves the original name for audit.
    """
    return _BUCKET_TO_CONFIDENCE.get(bucket, ConfidenceLevel.UNAVAILABLE)


def build_field_value(
    *,
    field_id: str,
    db_row: dict[str, Any],
    field_taxonomy: dict[str, Any],
    include_llm_supplement: bool,
) -> FieldValue:
    """Construct a FieldValue from a query_extraction row + taxonomy entry.

    Handles bucket translation, Decimal decoding, LLM filter semantics, and
    'unknown' currency normalization per spec.
    """
    raw_bucket = str(db_row.get("bucket", ""))
    confidence = bucket_to_confidence(raw_bucket)

    # LLM filter: when include_llm_supplement=False, replace LLM_SUPPLEMENT
    # fields with UNAVAILABLE placeholder (still in dict, not silently dropped).
    if (
        confidence == ConfidenceLevel.LLM_SUPPLEMENT
        and not include_llm_supplement
    ):
        return FieldValue(
            field_id=field_id,
            value=None,
            currency=None,
            unit=None,
            confidence=ConfidenceLevel.UNAVAILABLE,
            source=None,
            evidence_page=None,
            raw_bucket=raw_bucket,
            reason="llm_supplement_filtered",
        )

    # Decode value per taxonomy.value_type
    value_type = field_taxonomy.get("value_type", "text")
    raw_value = db_row.get("value")
    value: Decimal | str | bool | None
    if raw_value is None:
        value = None
    elif value_type in {"money", "number"}:
        # Decimal(str(...)) detour preserves precision (Task 7 invariant).
        value = Decimal(str(raw_value))
    elif value_type == "boolean":
        value = bool(raw_value)
    else:  # text
        value = str(raw_value) if not isinstance(raw_value, str) else raw_value

    # Currency: normalize "unknown" sentinel to None
    currency = db_row.get("currency")
    if currency == "unknown":
        currency = None

    return FieldValue(
        field_id=field_id,
        value=value,
        currency=currency,
        unit=db_row.get("unit"),
        confidence=confidence,
        source=db_row.get("selected_source"),
        evidence_page=db_row.get("evidence_page"),
        raw_bucket=raw_bucket,
        reason=db_row.get("reason"),
    )
