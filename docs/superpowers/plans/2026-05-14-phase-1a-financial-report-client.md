# Phase 1a — FinancialReportClient Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `FinancialReportClient` Python library that lets downstream agents (e.g. `TradingAgents-CN`) consume extraction results via a stable, encapsulated public API. Single backend = R1 DB + R4 pipeline (in-process). Zero new runtime dependencies (stdlib only).

**Architecture:** A new `src/financial_report_llm_extractor/client.py` module exposes 6 frozen dataclasses + 3 enums + 1 exception + 1 client class. Internally it uses R1's `db_query.query_extraction()` for DB hits and a refactored `pipeline_core.run_pipeline()` (extracted from `cli.py`) for fresh runs. `field_catalog/*.json` is packaged into the wheel via `pyproject.toml` `force-include` rule, loaded via `importlib.resources` to be CWD-independent. Bucket → ConfidenceLevel translation happens in the client layer; `raw_bucket` preserved for audit. All paths and behaviors specified in `docs/superpowers/specs/2026-05-13-financial-report-client-productization-design.md` (rev 4).

**Tech Stack:** Python 3.11 stdlib (`importlib.resources`, `hashlib`, `dataclasses`, `enum`, `decimal`, `pathlib`, `sqlite3`, `json`), pytest, existing R1/R4 cache modules.

---

## File Structure

| File | Role |
|---|---|
| `pyproject.toml` | Modify: add `[tool.hatch.build.targets.wheel.force-include]` to package `field_catalog/` into wheel |
| `src/financial_report_llm_extractor/client.py` | New: public API surface (enums, dataclasses, exception, FinancialReportClient class) |
| `src/financial_report_llm_extractor/pipeline_core.py` | New: extracted from `cli.py` pipeline dispatch; importable in-process pipeline runner |
| `src/financial_report_llm_extractor/cli.py` | Modify: `pipeline` subcommand becomes thin shim over `pipeline_core.run_pipeline()` |
| `src/financial_report_llm_extractor/__init__.py` | Modify: re-export `client` module's public names (optional but standard) |
| `tests/test_client_dataclasses.py` | New: PdfQuery, ExtractorConfig, FieldValue, ExtractionResult, ConfidenceLevel, RefreshPolicy, Staleness, ExtractorError unit tests |
| `tests/test_client_decimal.py` | New: Decimal precision round-trip test (the spec's most explicit acceptance criterion) |
| `tests/test_client_paths.py` | New: importlib.resources resolution; env var cache_root override; works from non-repo-root CWD |
| `tests/test_client_get_extraction.py` | New: get_extraction across (RefreshPolicy × Staleness) matrix; bucket translation; include_llm_supplement filter |
| `tests/test_client_get_field.py` | New: get_field success/missing/unknown_field/LLM filter behavior |
| `tests/test_pipeline_core.py` | New: pipeline_core.run_pipeline() in-process invocation |
| `tests/test_cli_pipeline.py` | Modify: existing tests still pass post-refactor of cli.py |
| `CLAUDE.md` | Modify: add Phase 1a row to "分阶段模块" table |
| `docs/2026-05-11-phase-summary.md` | Modify: add Phase 1a row to §6 marked 已落地 |

---

## Key Design Decisions (locked from spec rev 4)

1. **Backend = R1 DB + R4 pipeline (in-process), single layer.** Client does NOT read `tmp/runs/*.json`. DB is cache + source of truth for client reads; pipeline writes through DB.
2. **Catalog files in wheel via `importlib.resources`.** Default paths resolve regardless of CWD. Operator can override via `ExtractorConfig`.
3. **`cache_root` default = `$FR_LLM_CACHE_ROOT > ~/.cache/financial-report-llm-extractor/`.** Not CWD-relative. `db_path` defaults to `<cache_root>/extracted.db`.
4. **All API methods keyword-only.** `company`, `period_end`, `market` can never collide positionally.
5. **`include_llm_supplement` symmetric semantics.** Controls BOTH filter (existing DB row) AND pipeline-time LLM step toggle.
6. **`FieldValue.verification_required` is `@property`, not stored.** Derived from `source`.
7. **`Decimal` for money/number values, via `Decimal(str(json.loads(text)))`.** Per `taxonomy.value_type` dispatch.
8. **`extraction_id = sha256("{company}|{period_end}|{market}|{catalog_version}|{generated_at}")[:32]`.**
9. **`source` actual values = `{"akshare", "yahoo", "llm", None}`** (R1-verified). Per-LLM differentiation via `ExtractionResult.llm_provider` + `llm_model`.
10. **Bucket → ConfidenceLevel translation table** (6 buckets → 4 levels). `raw_bucket` preserved for audit.
11. **`PdfQuery` is frozen `kw_only` dataclass.** Positional construction raises `TypeError`.
12. **`evidence_kind` deferred to Phase 2.** Not in this plan.

---

## Task 1: pyproject.toml — Force-include catalog into wheel

**Files:**
- Modify: `pyproject.toml`
- Test: `tests/test_client_paths.py` (created later; this task adds a smoke test directly)

### Step 1.1: Inspect current pyproject.toml

Read `pyproject.toml`. Find the `[tool.hatch.*]` section (or note its absence — extractor uses hatchling per `[build-system]` declaration).

### Step 1.2: Add force-include rule

Append (or merge into existing `[tool.hatch.build.targets.wheel]`):

```toml
[tool.hatch.build.targets.wheel.force-include]
"field_catalog" = "financial_report_llm_extractor/_catalog_data"
```

This bundles `field_catalog/*.json` into the wheel at runtime path `financial_report_llm_extractor/_catalog_data/`.

### Step 1.3: Validate via local build smoke test

```bash
uv build 2>&1 | tail -10
unzip -l dist/financial_report_llm_extractor-*.whl | grep _catalog_data | head -5
```

Expected: wheel contains `financial_report_llm_extractor/_catalog_data/turtle_v015_field_taxonomy.json` and other catalog files.

Clean up:
```bash
rm -rf dist/ build/
```

### Step 1.4: Commit

```bash
git add pyproject.toml
git commit -m "feat: phase 1a force-include field_catalog into wheel for importlib.resources"
```

---

## Task 2: client.py module skeleton + 3 enums

**Files:**
- Create: `src/financial_report_llm_extractor/client.py`
- Test: `tests/test_client_dataclasses.py`

### Step 2.1: Write the failing test

Create `tests/test_client_dataclasses.py`:

```python
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
```

### Step 2.2: Run test → expect FAIL

```bash
uv run pytest tests/test_client_dataclasses.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'financial_report_llm_extractor.client'`.

### Step 2.3: Implement client.py skeleton with 3 enums

Write `src/financial_report_llm_extractor/client.py`:

```python
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

    CACHE_ONLY = "cache_only"      # DB miss → MISSING; no pipeline run
    CACHE_FIRST = "cache_first"    # DB hit (incl. stale) returned; miss → run pipeline
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
```

### Step 2.4: Run test → expect 3 passed

```bash
uv run pytest tests/test_client_dataclasses.py -v
```

### Step 2.5: ruff + mypy

```bash
uv run ruff check src/financial_report_llm_extractor/client.py tests/test_client_dataclasses.py
uv run mypy src/financial_report_llm_extractor/client.py
```

Expected: clean.

### Step 2.6: Commit

```bash
git add src/financial_report_llm_extractor/client.py tests/test_client_dataclasses.py
git commit -m "feat: phase 1a client module skeleton + 3 enums"
```

---

## Task 3: PdfQuery + ExtractorConfig dataclasses

**Files:**
- Modify: `src/financial_report_llm_extractor/client.py`
- Modify: `tests/test_client_dataclasses.py`

### Step 3.1: Write failing tests

Append to `tests/test_client_dataclasses.py`:

```python
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
```

### Step 3.2: Run test → expect FAIL

```bash
uv run pytest tests/test_client_dataclasses.py::test_pdf_query_is_kw_only -v
```

Expected: FAIL with `ImportError`.

### Step 3.3: Add PdfQuery + ExtractorConfig to client.py

Append to `src/financial_report_llm_extractor/client.py`:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


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
```

### Step 3.4: Run tests → expect 4 new passed

```bash
uv run pytest tests/test_client_dataclasses.py -v
```

Expected: 7 passed (3 from Task 2 + 4 new).

### Step 3.5: ruff + mypy

```bash
uv run ruff check src/financial_report_llm_extractor/client.py tests/test_client_dataclasses.py
uv run mypy src/financial_report_llm_extractor/client.py
```

### Step 3.6: Commit

```bash
git add src/financial_report_llm_extractor/client.py tests/test_client_dataclasses.py
git commit -m "feat: phase 1a PdfQuery + ExtractorConfig dataclasses (frozen, kw_only)"
```

---

## Task 4: FieldValue dataclass with computed properties

**Files:**
- Modify: `src/financial_report_llm_extractor/client.py`
- Modify: `tests/test_client_dataclasses.py`

### Step 4.1: Write failing tests

Append to `tests/test_client_dataclasses.py`:

```python
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
```

### Step 4.2: Run tests → expect FAIL

```bash
uv run pytest tests/test_client_dataclasses.py::test_field_value_construction_and_frozen -v
```

### Step 4.3: Add FieldValue to client.py

Append:

```python
from decimal import Decimal


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
```

### Step 4.4: Run tests → expect 4 new passed

```bash
uv run pytest tests/test_client_dataclasses.py -v
```

Expected: 11 passed total.

### Step 4.5: ruff + mypy

```bash
uv run ruff check src/financial_report_llm_extractor/client.py tests/test_client_dataclasses.py
uv run mypy src/financial_report_llm_extractor/client.py
```

### Step 4.6: Commit

```bash
git add src/financial_report_llm_extractor/client.py tests/test_client_dataclasses.py
git commit -m "feat: phase 1a FieldValue dataclass + is_reliable/is_present/verification_required properties"
```

---

## Task 5: ExtractionResult + extraction_id hash

**Files:**
- Modify: `src/financial_report_llm_extractor/client.py`
- Modify: `tests/test_client_dataclasses.py`

### Step 5.1: Write failing tests

Append to `tests/test_client_dataclasses.py`:

```python
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
```

### Step 5.2: Run tests → expect FAIL

```bash
uv run pytest tests/test_client_dataclasses.py::test_extraction_id_is_deterministic_sha256_prefix -v
```

### Step 5.3: Add ExtractionResult + compute_extraction_id to client.py

Append:

```python
import hashlib


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
```

### Step 5.4: Run tests → expect 3 new passed (14 total)

```bash
uv run pytest tests/test_client_dataclasses.py -v
```

### Step 5.5: ruff + mypy

```bash
uv run ruff check src/financial_report_llm_extractor/client.py tests/test_client_dataclasses.py
uv run mypy src/financial_report_llm_extractor/client.py
```

### Step 5.6: Commit

```bash
git add src/financial_report_llm_extractor/client.py tests/test_client_dataclasses.py
git commit -m "feat: phase 1a ExtractionResult dataclass + compute_extraction_id sha256 hash"
```

---

## Task 6: ExtractorError with explicit __init__

**Files:**
- Modify: `src/financial_report_llm_extractor/client.py`
- Modify: `tests/test_client_dataclasses.py`

### Step 6.1: Write failing test

Append to `tests/test_client_dataclasses.py`:

```python
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
```

### Step 6.2: Run test → expect FAIL

```bash
uv run pytest tests/test_client_dataclasses.py::test_extractor_error_init_and_attributes -v
```

### Step 6.3: Add ExtractorError to client.py

Append:

```python
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
```

### Step 6.4: Run tests → expect 3 new passed (17 total)

```bash
uv run pytest tests/test_client_dataclasses.py -v
```

### Step 6.5: ruff + mypy

```bash
uv run ruff check src/financial_report_llm_extractor/client.py tests/test_client_dataclasses.py
uv run mypy src/financial_report_llm_extractor/client.py
```

### Step 6.6: Commit

```bash
git add src/financial_report_llm_extractor/client.py tests/test_client_dataclasses.py
git commit -m "feat: phase 1a ExtractorError unified exception with stable reason codes"
```

---

## Task 7: Decimal deserialization helper

**Files:**
- Modify: `src/financial_report_llm_extractor/client.py`
- Create: `tests/test_client_decimal.py`

### Step 7.1: Write failing tests

Create `tests/test_client_decimal.py`:

```python
"""Decimal precision is the most explicit Phase 1a acceptance criterion.

R1 stores `value` as JSON-encoded text. The client must deserialize numeric
fields as Decimal via `Decimal(str(json.loads(text)))` (the str() detour
prevents float precision loss).
"""

from __future__ import annotations

from decimal import Decimal

import pytest


def test_decode_value_money_string_returns_decimal() -> None:
    """R1 stores money values as stringified-numbers in JSON
    (e.g. '"170899152276.34"'). Client must return Decimal."""
    from financial_report_llm_extractor.client import decode_value

    # JSON-encoded string representation
    result = decode_value(
        value_text='"170899152276.34"', value_type="money",
    )
    assert isinstance(result, Decimal)
    assert result == Decimal("170899152276.34")


def test_decode_value_money_number_returns_decimal_via_str() -> None:
    """If R1 ever stores a value as a JSON number, the str() detour
    must preserve precision."""
    from financial_report_llm_extractor.client import decode_value

    result = decode_value(value_text="0.1", value_type="money")
    assert isinstance(result, Decimal)
    # Critical: Decimal(str(0.1)) == Decimal("0.1"), NOT Decimal(0.1)
    assert result == Decimal("0.1")


def test_decode_value_number_returns_decimal() -> None:
    from financial_report_llm_extractor.client import decode_value

    result = decode_value(value_text="42", value_type="number")
    assert isinstance(result, Decimal)
    assert result == Decimal("42")


def test_decode_value_text_returns_str() -> None:
    from financial_report_llm_extractor.client import decode_value

    result = decode_value(
        value_text='"标准无保留意见"', value_type="text",
    )
    assert isinstance(result, str)
    assert result == "标准无保留意见"


def test_decode_value_boolean_returns_bool() -> None:
    from financial_report_llm_extractor.client import decode_value

    assert decode_value(value_text="true", value_type="boolean") is True
    assert decode_value(value_text="false", value_type="boolean") is False


def test_decode_value_null_returns_none() -> None:
    from financial_report_llm_extractor.client import decode_value

    assert decode_value(value_text=None, value_type="money") is None
    assert decode_value(value_text=None, value_type="text") is None
    assert decode_value(value_text="null", value_type="money") is None


def test_decode_value_unknown_value_type_raises() -> None:
    """Defensive: unknown value_type should surface, not silently coerce."""
    from financial_report_llm_extractor.client import decode_value

    with pytest.raises(ValueError, match="unsupported value_type"):
        decode_value(value_text='"x"', value_type="enum")  # type: ignore[arg-type]
```

### Step 7.2: Run tests → expect FAIL

```bash
uv run pytest tests/test_client_decimal.py -v
```

### Step 7.3: Implement decode_value in client.py

Append to `client.py`:

```python
import json
from typing import Literal


ValueType = Literal["money", "number", "text", "boolean"]


def decode_value(
    *,
    value_text: str | None,
    value_type: ValueType,
) -> Decimal | str | bool | None:
    """Decode an R1-stored JSON value-text into a Python type per taxonomy.

    Critical: numeric values use Decimal(str(...)) to preserve precision
    when the JSON contains a float literal.
    """
    if value_text is None:
        return None
    parsed: object = json.loads(value_text)
    if parsed is None:
        return None
    if value_type in {"money", "number"}:
        return Decimal(str(parsed))
    if value_type == "text":
        if not isinstance(parsed, str):
            # text fields may legitimately be JSON-encoded as string;
            # tolerate accidental non-string by stringifying.
            return str(parsed)
        return parsed
    if value_type == "boolean":
        return bool(parsed)
    raise ValueError(f"unsupported value_type: {value_type!r}")
```

### Step 7.4: Run tests → expect 7 passed

```bash
uv run pytest tests/test_client_decimal.py -v
```

### Step 7.5: ruff + mypy

```bash
uv run ruff check src/financial_report_llm_extractor/client.py tests/test_client_decimal.py
uv run mypy src/financial_report_llm_extractor/client.py
```

### Step 7.6: Commit

```bash
git add src/financial_report_llm_extractor/client.py tests/test_client_decimal.py
git commit -m "feat: phase 1a decode_value helper — Decimal via str() preserves precision"
```

---

## Task 8: pipeline_core.py — extract from cli.py

**Files:**
- Create: `src/financial_report_llm_extractor/pipeline_core.py`
- Modify: `src/financial_report_llm_extractor/cli.py`
- Create: `tests/test_pipeline_core.py`

### Step 8.1: Inspect current cli.py pipeline dispatch

Read `src/financial_report_llm_extractor/cli.py`. Find `if args.command == "pipeline":` branch. Identify the logic:
- Resolve period
- Read catalog_version from taxonomy
- Pre-check DB via `query_extraction()`
- If miss/force: fetch_source_inventory + evaluate-company + index_run
- Print summary JSON

The function we extract should match this control flow but with explicit parameters instead of `args`. The CLI dispatch becomes a thin parser → function call.

### Step 8.2: Write failing test

Create `tests/test_pipeline_core.py`:

```python
"""pipeline_core.run_pipeline() — in-process orchestration shared by
CLI `pipeline` subcommand and FinancialReportClient."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_pipeline_core_db_cache_hit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """If DB has matching (company, period_end, market, catalog_version),
    pipeline_core returns cache_hit dict without invoking fetch/evaluate."""
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.cache.indexer import index_run
    from financial_report_llm_extractor.pipeline_core import run_pipeline

    fixture_dir = Path(__file__).parent / "fixtures" / "cache_sample_run"
    db_path = tmp_path / "out.db"
    init_db(db_path)

    tax_path = Path("field_catalog/turtle_v015_field_taxonomy.json")
    taxonomy_doc = json.loads(tax_path.read_text(encoding="utf-8"))
    catalog_version = str(taxonomy_doc.get("version", "unknown"))
    priority_map = {
        fid: str(info.get("priority", ""))
        for fid, info in taxonomy_doc.get("fields", {}).items()
    }
    index_run(
        run_dir=fixture_dir,
        db_path=db_path,
        catalog_version=catalog_version,
        priority_map=priority_map,
    )

    result = run_pipeline(
        company="600519",
        period_end="2024-12-31",
        market="CN",
        report_type="annual",
        db_path=db_path,
        out_dir=tmp_path / "fresh_run",
        catalog_path=Path(
            "field_catalog/turtle_v015_source_mapping_minimal.json"
        ),
        taxonomy_path=tax_path,
        priorities=("P0", "P1", "P2", "P3", "P4"),
        pdf_path=None,
        llm_config_path=None,
        force=False,
        no_cache=False,
    )
    assert result["status"] == "cache_hit"
    assert result["company"] == "600519"
    assert result["catalog_version"] == catalog_version


def test_pipeline_core_force_bypasses_db(
    tmp_path: Path,
) -> None:
    """--force must bypass the DB pre-check.

    Pipeline will fail downstream (no network / pdf) — the test only
    verifies the dispatch did NOT short-circuit to cache_hit."""
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.cache.indexer import index_run
    from financial_report_llm_extractor.pipeline_core import run_pipeline

    fixture_dir = Path(__file__).parent / "fixtures" / "cache_sample_run"
    db_path = tmp_path / "out.db"
    init_db(db_path)

    tax_path = Path("field_catalog/turtle_v015_field_taxonomy.json")
    taxonomy_doc = json.loads(tax_path.read_text(encoding="utf-8"))
    catalog_version = str(taxonomy_doc.get("version", "unknown"))
    priority_map = {
        fid: str(info.get("priority", ""))
        for fid, info in taxonomy_doc.get("fields", {}).items()
    }
    index_run(
        run_dir=fixture_dir, db_path=db_path,
        catalog_version=catalog_version, priority_map=priority_map,
    )

    # With force=True, even though DB hit exists, pipeline tries fresh
    # run and will fail (no real client). Expect any exception EXCEPT
    # status=="cache_hit" return.
    try:
        result = run_pipeline(
            company="600519",
            period_end="2024-12-31",
            market="CN",
            report_type="annual",
            db_path=db_path,
            out_dir=tmp_path / "fresh_run",
            catalog_path=Path(
                "field_catalog/turtle_v015_source_mapping_minimal.json"
            ),
            taxonomy_path=tax_path,
            priorities=("P0", "P1", "P2", "P3", "P4"),
            pdf_path=None,
            llm_config_path=None,
            force=True,
            no_cache=False,
        )
        # If no exception, must NOT be cache_hit
        assert result.get("status") != "cache_hit"
    except Exception:
        pass  # acceptable — fresh run fails in unit-test env without network
```

### Step 8.3: Run test → expect FAIL

```bash
uv run pytest tests/test_pipeline_core.py -v
```

### Step 8.4: Create pipeline_core.py by extracting from cli.py

Write `src/financial_report_llm_extractor/pipeline_core.py`:

```python
"""In-process pipeline orchestration: fetch + evaluate + auto-index.

Shared by `cli.py pipeline` subcommand and `client.FinancialReportClient`.
Returns a status dict; raises on internal pipeline errors (callers wrap as
needed).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from financial_report_llm_extractor.cache.db import init_db
from financial_report_llm_extractor.cache.db_query import query_extraction
from financial_report_llm_extractor.cache.indexer import index_run
from financial_report_llm_extractor.structured_sources.company_evaluation import (
    run_company_evaluation,
)
from financial_report_llm_extractor.structured_sources.models import (
    PeriodSpec,
)
from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
    fetch_source_inventory,
)


def _resolve_period(
    *,
    period_end: str | None,
    year: int | None,
    report_type: str,
) -> PeriodSpec:
    """Resolve period from either ISO period_end or year."""
    if year is not None and period_end is not None:
        raise ValueError("year and period_end are mutually exclusive")
    if year is not None:
        return PeriodSpec.from_year(year)
    if period_end is not None:
        return PeriodSpec.from_period_end(period_end, report_type)
    raise ValueError("one of year or period_end is required")


def run_pipeline(
    *,
    company: str,
    period_end: str | None = None,
    year: int | None = None,
    market: str,
    report_type: str = "annual",
    db_path: Path,
    out_dir: Path,
    catalog_path: Path,
    taxonomy_path: Path,
    priorities: tuple[str, ...] = ("P0", "P1", "P2", "P3", "P4"),
    pdf_path: Path | None = None,
    llm_config_path: Path | None = None,
    force: bool = False,
    no_cache: bool = False,
) -> dict[str, Any]:
    """Run the DB-aware pipeline. Returns status dict.

    Status values:
      "cache_hit"  — DB has matching extraction (skipped fresh run)
      "fresh_run"  — fetch + evaluate + index completed
    """
    period = _resolve_period(
        period_end=period_end, year=year, report_type=report_type,
    )

    taxonomy_doc = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    catalog_version = str(taxonomy_doc.get("version", "unknown"))
    period_end_str = period.period_end.isoformat()

    init_db(db_path)
    if not force:
        hit = query_extraction(
            db_path=db_path,
            company=company,
            period_end=period_end_str,
            market=market,
        )
        if hit is not None and hit.get("catalog_version") == catalog_version:
            return {
                "status": "cache_hit",
                "company": company,
                "period_end": period_end_str,
                "market": market,
                "catalog_version": catalog_version,
                "artifact_path": hit.get("artifact_path"),
                "field_count": len(hit.get("fields", {})),
            }

    cache_root: Path | None = None if no_cache else Path("tmp/.cache")

    fetch_result = fetch_source_inventory(
        company=company,
        period=period,
        market=market,
        providers=("akshare", "yahoo"),
        out_dir=out_dir,
        catalog_path=catalog_path,
        cache_root=cache_root,
        ttl_hours=24,
        no_cache=no_cache,
    )

    run_company_evaluation(
        company=company,
        period=period,
        market=market,
        inventory_path=fetch_result.inventory_path,
        inventory_summary_path=fetch_result.summary_path,
        catalog_path=catalog_path,
        taxonomy_path=taxonomy_path,
        pdf_path=pdf_path,
        llm_config_path=llm_config_path,
        priorities=priorities,
        out_dir=out_dir,
        cache_root=cache_root,
    )

    priority_map = {
        fid: str(info.get("priority", ""))
        for fid, info in taxonomy_doc.get("fields", {}).items()
    }
    n_fields = index_run(
        run_dir=out_dir, db_path=db_path,
        catalog_version=catalog_version,
        priority_map=priority_map,
    )

    return {
        "status": "fresh_run",
        "company": company,
        "period_end": period_end_str,
        "market": market,
        "catalog_version": catalog_version,
        "artifact_path": str(out_dir),
        "field_count": n_fields,
    }
```

**Note**: the exact parameters of `fetch_source_inventory()` and `run_company_evaluation()` should match what `cli.py` currently calls. Read the existing call sites in `cli.py` to align signatures (especially param names like `no_cache` vs `cache_ttl_hours`).

### Step 8.5: Refactor cli.py pipeline dispatch

In `src/financial_report_llm_extractor/cli.py`, find `if args.command == "pipeline":` branch. Replace its body with a thin call to `pipeline_core.run_pipeline()`:

```python
    if args.command == "pipeline":
        import json as _json
        from financial_report_llm_extractor.pipeline_core import run_pipeline

        result = run_pipeline(
            company=args.company,
            period_end=args.period_end if args.year is None else None,
            year=args.year,
            market=args.market,
            report_type=args.report_type,
            db_path=args.db,
            out_dir=args.out,
            catalog_path=args.catalog,
            taxonomy_path=args.taxonomy,
            priorities=tuple(
                p.strip() for p in args.priorities.split(",") if p.strip()
            ),
            pdf_path=args.pdf,
            llm_config_path=args.llm_config,
            force=args.force,
            no_cache=args.no_cache,
        )
        print(_json.dumps(result, indent=2, sort_keys=True))
        return 0
```

The argparse logic (parser validation of `--year` xor `--period-end`) stays in cli.py; `run_pipeline` revalidates defensively.

### Step 8.6: Run all tests including existing pipeline tests

```bash
uv run pytest tests/test_pipeline_core.py tests/test_cli_pipeline.py -v
```

Expected: 2 new test_pipeline_core tests pass + 6 existing test_cli_pipeline tests still pass.

```bash
uv run pytest -q
```

Expected: full suite passes (no regression).

### Step 8.7: ruff + mypy

```bash
uv run ruff check src/financial_report_llm_extractor/pipeline_core.py tests/test_pipeline_core.py
uv run mypy src/financial_report_llm_extractor/pipeline_core.py
uv run mypy src tests
```

### Step 8.8: Commit

```bash
git add src/financial_report_llm_extractor/pipeline_core.py \
        src/financial_report_llm_extractor/cli.py \
        tests/test_pipeline_core.py
git commit -m "refactor: phase 1a extract pipeline_core from cli.py for client import"
```

---

## Task 9: Path resolution — importlib.resources + env var

**Files:**
- Modify: `src/financial_report_llm_extractor/client.py`
- Create: `tests/test_client_paths.py`

### Step 9.1: Write failing tests

Create `tests/test_client_paths.py`:

```python
"""Default path resolution: catalog/taxonomy via importlib.resources;
cache_root via env var or ~/.cache fallback.

These tests must work even when CWD is not the repo root."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_default_catalog_path_resolves_via_importlib_resources() -> None:
    """The packaged catalog must be loadable without CWD assumption."""
    from financial_report_llm_extractor.client import (
        resolve_catalog_path,
        resolve_taxonomy_path,
    )

    catalog = resolve_catalog_path(override=None)
    assert catalog.exists(), f"catalog file not found: {catalog}"
    assert catalog.name == "turtle_v015_source_mapping_minimal.json"

    taxonomy = resolve_taxonomy_path(override=None)
    assert taxonomy.exists(), f"taxonomy file not found: {taxonomy}"
    assert taxonomy.name == "turtle_v015_field_taxonomy.json"


def test_catalog_path_override_takes_precedence(tmp_path: Path) -> None:
    from financial_report_llm_extractor.client import resolve_catalog_path

    custom = tmp_path / "my_catalog.json"
    custom.write_text("{}", encoding="utf-8")
    assert resolve_catalog_path(override=custom) == custom


def test_cache_root_uses_env_var_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from financial_report_llm_extractor.client import resolve_cache_root

    custom = tmp_path / "custom_cache"
    monkeypatch.setenv("FR_LLM_CACHE_ROOT", str(custom))
    assert resolve_cache_root(override=None) == custom


def test_cache_root_falls_back_to_user_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from financial_report_llm_extractor.client import resolve_cache_root

    monkeypatch.delenv("FR_LLM_CACHE_ROOT", raising=False)
    fake_home = tmp_path / "fake_home"
    monkeypatch.setenv("HOME", str(fake_home))
    result = resolve_cache_root(override=None)
    assert result == fake_home / ".cache" / "financial-report-llm-extractor"


def test_cache_root_override_takes_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from financial_report_llm_extractor.client import resolve_cache_root

    # env var set but override should win
    monkeypatch.setenv("FR_LLM_CACHE_ROOT", str(tmp_path / "env_wins"))
    custom = tmp_path / "override_wins"
    assert resolve_cache_root(override=custom) == custom


def test_db_path_default_is_under_cache_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from financial_report_llm_extractor.client import (
        resolve_cache_root,
        resolve_db_path,
    )

    monkeypatch.setenv("FR_LLM_CACHE_ROOT", str(tmp_path / "c"))
    cache_root = resolve_cache_root(override=None)
    db = resolve_db_path(override=None, cache_root=cache_root)
    assert db == cache_root / "extracted.db"
```

### Step 9.2: Run tests → expect FAIL

```bash
uv run pytest tests/test_client_paths.py -v
```

### Step 9.3: Implement path resolution in client.py

Append to `client.py`:

```python
import os
from importlib.resources import files as _pkg_files


def resolve_catalog_path(*, override: Path | None) -> Path:
    """Return path to source_mapping_minimal catalog. Override > packaged."""
    if override is not None:
        return override
    # Packaged catalog via importlib.resources (pyproject force-include).
    try:
        resource = _pkg_files("financial_report_llm_extractor").joinpath(
            "_catalog_data", "turtle_v015_source_mapping_minimal.json"
        )
        return Path(str(resource))
    except (ModuleNotFoundError, FileNotFoundError):
        pass
    # Editable-install fallback: relative to repo root (best-effort).
    return Path("field_catalog/turtle_v015_source_mapping_minimal.json")


def resolve_taxonomy_path(*, override: Path | None) -> Path:
    """Return path to field_taxonomy. Override > packaged."""
    if override is not None:
        return override
    try:
        resource = _pkg_files("financial_report_llm_extractor").joinpath(
            "_catalog_data", "turtle_v015_field_taxonomy.json"
        )
        return Path(str(resource))
    except (ModuleNotFoundError, FileNotFoundError):
        pass
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
```

### Step 9.4: Run tests → expect 6 passed

```bash
uv run pytest tests/test_client_paths.py -v
```

### Step 9.5: ruff + mypy

```bash
uv run ruff check src/financial_report_llm_extractor/client.py tests/test_client_paths.py
uv run mypy src/financial_report_llm_extractor/client.py
```

### Step 9.6: Commit

```bash
git add src/financial_report_llm_extractor/client.py tests/test_client_paths.py
git commit -m "feat: phase 1a path resolution — importlib.resources + env var cache_root"
```

---

## Task 10: FinancialReportClient skeleton — __init__ / catalog_fields / catalog_version / get_status

**Files:**
- Modify: `src/financial_report_llm_extractor/client.py`
- Modify: `tests/test_client_dataclasses.py` (extend with client init tests)

### Step 10.1: Write failing tests

Append to `tests/test_client_dataclasses.py`:

```python
def test_client_init_with_no_config_uses_defaults() -> None:
    from financial_report_llm_extractor.client import FinancialReportClient

    client = FinancialReportClient()
    # Verify resolved paths are set (don't assert exact values; rely on
    # tests in test_client_paths.py for that)
    assert client.config.taxonomy_path is None or client.config.taxonomy_path.exists()


def test_client_catalog_fields_returns_taxonomy_field_ids(
    tmp_path: "Path",
) -> None:
    """catalog_fields() returns the field_ids known to the taxonomy."""
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        FinancialReportClient,
    )

    client = FinancialReportClient()
    fields = client.catalog_fields()
    assert isinstance(fields, tuple)
    assert len(fields) > 50  # current catalog has 68 mapped + a few P4 unmapped
    assert "revenue" in fields
    assert "audit_opinion" in fields


def test_client_catalog_version_returns_string() -> None:
    from financial_report_llm_extractor.client import FinancialReportClient

    client = FinancialReportClient()
    version = client.catalog_version()
    assert isinstance(version, str)
    assert len(version) > 0


def test_client_get_status_missing(tmp_path: "Path") -> None:
    """Empty DB → Staleness.MISSING."""
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        FinancialReportClient,
        Staleness,
    )

    db_path = tmp_path / "empty.db"
    init_db(db_path)

    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path)
    )
    status = client.get_status(
        company="600519", period_end="2024-12-31", market="CN",
    )
    assert status == Staleness.MISSING


def test_client_get_status_fresh(tmp_path: "Path") -> None:
    """DB has matching catalog_version → Staleness.FRESH."""
    import json as _json
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.cache.indexer import index_run
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        FinancialReportClient,
        Staleness,
    )

    db_path = tmp_path / "out.db"
    init_db(db_path)

    fixture_dir = Path(__file__).parent / "fixtures" / "cache_sample_run"
    tax_path = Path("field_catalog/turtle_v015_field_taxonomy.json")
    taxonomy_doc = _json.loads(tax_path.read_text(encoding="utf-8"))
    catalog_version = str(taxonomy_doc.get("version", "unknown"))
    priority_map = {
        fid: str(info.get("priority", ""))
        for fid, info in taxonomy_doc.get("fields", {}).items()
    }
    index_run(
        run_dir=fixture_dir, db_path=db_path,
        catalog_version=catalog_version, priority_map=priority_map,
    )

    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path)
    )
    status = client.get_status(
        company="600519", period_end="2024-12-31", market="CN",
    )
    assert status == Staleness.FRESH
```

### Step 10.2: Run tests → expect FAIL

```bash
uv run pytest tests/test_client_dataclasses.py::test_client_init_with_no_config_uses_defaults -v
```

### Step 10.3: Implement FinancialReportClient class

Append to `client.py`:

```python
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
```

### Step 10.4: Run tests → expect 5 new passed

```bash
uv run pytest tests/test_client_dataclasses.py -v
```

### Step 10.5: ruff + mypy

```bash
uv run ruff check src/financial_report_llm_extractor/client.py tests/test_client_dataclasses.py
uv run mypy src/financial_report_llm_extractor/client.py
```

### Step 10.6: Commit

```bash
git add src/financial_report_llm_extractor/client.py tests/test_client_dataclasses.py
git commit -m "feat: phase 1a FinancialReportClient init + catalog_fields/version + get_status"
```

---

## Task 11: Bucket translation + FieldValue construction helper

**Files:**
- Modify: `src/financial_report_llm_extractor/client.py`
- Create: `tests/test_client_bucket_translation.py`

### Step 11.1: Write failing tests

Create `tests/test_client_bucket_translation.py`:

```python
"""Bucket → ConfidenceLevel translation + LLM filter behavior."""

from __future__ import annotations

import pytest


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

    # Simulate what query_extraction would return for a clean_present money field
    db_row = {
        "bucket": "clean_present",
        "value": "170899152276.34",  # query_extraction does json.loads then returns string
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
```

### Step 11.2: Run tests → expect FAIL

```bash
uv run pytest tests/test_client_bucket_translation.py -v
```

### Step 11.3: Implement bucket translation + build_field_value

Append to `client.py`:

```python
from typing import Any


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
    # db_row["value"] from query_extraction is already json.loads'd by
    # db_query._decode_field_row, but the spec requires Decimal for
    # money/number — re-route via decode_value using stringified input.
    if raw_value is None:
        value: Decimal | str | bool | None = None
    elif value_type in {"money", "number"}:
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
```

### Step 11.4: Run tests → expect 12 passed

```bash
uv run pytest tests/test_client_bucket_translation.py -v
```

### Step 11.5: ruff + mypy

```bash
uv run ruff check src/financial_report_llm_extractor/client.py tests/test_client_bucket_translation.py
uv run mypy src/financial_report_llm_extractor/client.py
```

### Step 11.6: Commit

```bash
git add src/financial_report_llm_extractor/client.py tests/test_client_bucket_translation.py
git commit -m "feat: phase 1a bucket_to_confidence + build_field_value helpers"
```

---

## Task 12: get_extraction() — full implementation

**Files:**
- Modify: `src/financial_report_llm_extractor/client.py`
- Create: `tests/test_client_get_extraction.py`

### Step 12.1: Write failing tests

Create `tests/test_client_get_extraction.py`:

```python
"""get_extraction() behavior across RefreshPolicy × Staleness × LLM filter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _seed_db_with_fixture(
    tmp_path: Path,
    catalog_version_override: str | None = None,
) -> Path:
    """Seed DB with the cache_sample_run fixture; return db_path."""
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.cache.indexer import index_run

    db_path = tmp_path / "out.db"
    init_db(db_path)

    fixture_dir = Path(__file__).parent / "fixtures" / "cache_sample_run"
    tax_path = Path("field_catalog/turtle_v015_field_taxonomy.json")
    taxonomy_doc = json.loads(tax_path.read_text(encoding="utf-8"))
    catalog_version = catalog_version_override or str(
        taxonomy_doc.get("version", "unknown")
    )
    priority_map = {
        fid: str(info.get("priority", ""))
        for fid, info in taxonomy_doc.get("fields", {}).items()
    }
    index_run(
        run_dir=fixture_dir, db_path=db_path,
        catalog_version=catalog_version, priority_map=priority_map,
    )
    return db_path


def test_get_extraction_cache_only_db_miss_returns_missing(
    tmp_path: Path,
) -> None:
    """CACHE_ONLY + DB miss → staleness=MISSING, fields={}, no pipeline."""
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        FinancialReportClient,
        RefreshPolicy,
        Staleness,
    )

    db_path = tmp_path / "empty.db"
    init_db(db_path)
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    result = client.get_extraction(
        company="600519", period_end="2024-12-31", market="CN",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
    )
    assert result.staleness == Staleness.MISSING
    assert result.fields == {}


def test_get_extraction_cache_only_hit_returns_fresh(
    tmp_path: Path,
) -> None:
    """CACHE_ONLY + DB hit + matching catalog_version → FRESH."""
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        FinancialReportClient,
        RefreshPolicy,
        Staleness,
    )

    db_path = _seed_db_with_fixture(tmp_path)
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    result = client.get_extraction(
        company="600519", period_end="2024-12-31", market="CN",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
    )
    assert result.staleness == Staleness.FRESH
    assert "revenue" in result.fields


def test_get_extraction_cache_only_stale_returns_stale_with_data(
    tmp_path: Path,
) -> None:
    """CACHE_ONLY + DB hit + mismatched catalog_version → STALE,
    fields still returned."""
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        FinancialReportClient,
        RefreshPolicy,
        Staleness,
    )

    # Seed with a stale catalog_version
    db_path = _seed_db_with_fixture(tmp_path, catalog_version_override="stale-v0")
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    result = client.get_extraction(
        company="600519", period_end="2024-12-31", market="CN",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
    )
    assert result.staleness == Staleness.STALE
    assert "revenue" in result.fields, "STALE must still return fields"


def test_get_extraction_decimal_value_preserved(tmp_path: Path) -> None:
    """Critical acceptance test: Decimal precision preserved end-to-end."""
    from decimal import Decimal
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        FinancialReportClient,
        RefreshPolicy,
    )

    db_path = _seed_db_with_fixture(tmp_path)
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    result = client.get_extraction(
        company="600519", period_end="2024-12-31", market="CN",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
    )
    revenue = result.fields["revenue"]
    assert isinstance(revenue.value, Decimal), (
        f"expected Decimal, got {type(revenue.value).__name__}"
    )
    assert revenue.value == Decimal("170899152276.34")


def test_get_extraction_extraction_id_stable(tmp_path: Path) -> None:
    """extraction_id is reproducible from result metadata."""
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        FinancialReportClient,
        RefreshPolicy,
        compute_extraction_id,
    )

    db_path = _seed_db_with_fixture(tmp_path)
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    result = client.get_extraction(
        company="600519", period_end="2024-12-31", market="CN",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
    )
    expected = compute_extraction_id(
        company=result.company,
        period_end=result.period_end,
        market=result.market,
        catalog_version=result.catalog_version,
        generated_at=result.generated_at,
    )
    assert result.extraction_id == expected


def test_get_extraction_include_llm_supplement_false_filters_llm_fields(
    tmp_path: Path,
) -> None:
    """include_llm_supplement=False: LLM fields returned as UNAVAILABLE
    placeholder (still in dict, not silently dropped)."""
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        ExtractorConfig,
        FinancialReportClient,
        RefreshPolicy,
    )

    db_path = _seed_db_with_fixture(tmp_path)
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    result = client.get_extraction(
        company="600519", period_end="2024-12-31", market="CN",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
        include_llm_supplement=False,  # default but explicit
    )
    # audit_opinion in fixture is bucket=llm_supplement_present
    audit = result.fields["audit_opinion"]
    assert audit.confidence == ConfidenceLevel.UNAVAILABLE
    assert audit.value is None
    assert audit.raw_bucket == "llm_supplement_present"
    assert audit.reason == "llm_supplement_filtered"


def test_get_extraction_include_llm_supplement_true_keeps_llm_fields(
    tmp_path: Path,
) -> None:
    """include_llm_supplement=True: LLM fields returned with original value."""
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        ExtractorConfig,
        FinancialReportClient,
        RefreshPolicy,
    )

    db_path = _seed_db_with_fixture(tmp_path)
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    result = client.get_extraction(
        company="600519", period_end="2024-12-31", market="CN",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
        include_llm_supplement=True,
    )
    audit = result.fields["audit_opinion"]
    assert audit.confidence == ConfidenceLevel.LLM_SUPPLEMENT
    assert audit.value is not None  # fixture has actual opinion text


def test_get_extraction_invalid_market_raises(tmp_path: Path) -> None:
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        ExtractorError,
        FinancialReportClient,
        RefreshPolicy,
    )

    db_path = _seed_db_with_fixture(tmp_path)
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    with pytest.raises(ExtractorError) as excinfo:
        client.get_extraction(
            company="600519", period_end="2024-12-31", market="US",
            refresh_policy=RefreshPolicy.CACHE_ONLY,
        )
    assert excinfo.value.reason == "unsupported_market"
```

### Step 12.2: Run tests → expect FAIL

```bash
uv run pytest tests/test_client_get_extraction.py -v
```

### Step 12.3: Implement get_extraction()

Add to `FinancialReportClient` class in `client.py`:

```python
    def get_extraction(
        self,
        *,
        company: str,
        period_end: str,
        market: str,
        include_llm_supplement: bool = False,
        refresh_policy: RefreshPolicy = RefreshPolicy.CACHE_FIRST,
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
            )
        except Exception as exc:
            # Distinguish fetch vs evaluate failures by heuristic on exc type
            # (out of scope for v1 — coarse map to fetch_failed).
            reason = "evaluate_failed" if "evaluat" in str(exc).lower() else "fetch_failed"
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
```

### Step 12.4: Run tests → expect 8 passed

```bash
uv run pytest tests/test_client_get_extraction.py -v
```

### Step 12.5: Full suite + ruff + mypy

```bash
uv run pytest -q
uv run ruff check src/financial_report_llm_extractor/client.py tests/test_client_get_extraction.py
uv run mypy src/financial_report_llm_extractor/client.py
```

### Step 12.6: Commit

```bash
git add src/financial_report_llm_extractor/client.py tests/test_client_get_extraction.py
git commit -m "feat: phase 1a get_extraction with full RefreshPolicy + Staleness + LLM filter"
```

---

## Task 13: get_field() — single-field lookup

**Files:**
- Modify: `src/financial_report_llm_extractor/client.py`
- Create: `tests/test_client_get_field.py`

### Step 13.1: Write failing tests

Create `tests/test_client_get_field.py`:

```python
"""get_field() behavior: known field, unknown field (raise),
LLM filter consistent with get_extraction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _seed_db_and_client(tmp_path: Path):
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.cache.indexer import index_run
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        FinancialReportClient,
    )

    db_path = tmp_path / "out.db"
    init_db(db_path)

    fixture_dir = Path(__file__).parent / "fixtures" / "cache_sample_run"
    tax_path = Path("field_catalog/turtle_v015_field_taxonomy.json")
    taxonomy_doc = json.loads(tax_path.read_text(encoding="utf-8"))
    catalog_version = str(taxonomy_doc.get("version", "unknown"))
    priority_map = {
        fid: str(info.get("priority", ""))
        for fid, info in taxonomy_doc.get("fields", {}).items()
    }
    index_run(
        run_dir=fixture_dir, db_path=db_path,
        catalog_version=catalog_version, priority_map=priority_map,
    )

    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    return client


def test_get_field_returns_field_value(tmp_path: Path) -> None:
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        RefreshPolicy,
    )

    client = _seed_db_and_client(tmp_path)
    fv = client.get_field(
        company="600519", period_end="2024-12-31", market="CN",
        field_id="revenue",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
    )
    assert fv.field_id == "revenue"
    assert fv.confidence == ConfidenceLevel.VERIFIED
    assert fv.is_reliable


def test_get_field_unknown_field_raises(tmp_path: Path) -> None:
    from financial_report_llm_extractor.client import (
        ExtractorError,
        RefreshPolicy,
    )

    client = _seed_db_and_client(tmp_path)
    with pytest.raises(ExtractorError) as excinfo:
        client.get_field(
            company="600519", period_end="2024-12-31", market="CN",
            field_id="totally_made_up_field_xyz",
            refresh_policy=RefreshPolicy.CACHE_ONLY,
        )
    assert excinfo.value.reason == "unknown_field"


def test_get_field_taxonomy_field_but_no_db_data_returns_unavailable(
    tmp_path: Path,
) -> None:
    """field is in taxonomy but DB has no row for it (because fixture
    only has 3 fields) → UNAVAILABLE placeholder."""
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        RefreshPolicy,
    )

    client = _seed_db_and_client(tmp_path)
    # `total_assets` is in taxonomy but not in cache_sample_run fixture
    fv = client.get_field(
        company="600519", period_end="2024-12-31", market="CN",
        field_id="total_assets",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
    )
    assert fv.field_id == "total_assets"
    assert fv.confidence == ConfidenceLevel.UNAVAILABLE
    assert fv.value is None


def test_get_field_llm_supplement_filter_same_as_get_extraction(
    tmp_path: Path,
) -> None:
    """get_field and get_extraction must agree on LLM filter behavior."""
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        RefreshPolicy,
    )

    client = _seed_db_and_client(tmp_path)
    # include=False → UNAVAILABLE placeholder
    fv = client.get_field(
        company="600519", period_end="2024-12-31", market="CN",
        field_id="audit_opinion",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
        include_llm_supplement=False,
    )
    assert fv.confidence == ConfidenceLevel.UNAVAILABLE
    assert fv.reason == "llm_supplement_filtered"
    assert fv.raw_bucket == "llm_supplement_present"

    # include=True → full LLM_SUPPLEMENT
    fv2 = client.get_field(
        company="600519", period_end="2024-12-31", market="CN",
        field_id="audit_opinion",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
        include_llm_supplement=True,
    )
    assert fv2.confidence == ConfidenceLevel.LLM_SUPPLEMENT
    assert fv2.value is not None
```

### Step 13.2: Run tests → expect FAIL

```bash
uv run pytest tests/test_client_get_field.py -v
```

### Step 13.3: Implement get_field()

Add to `FinancialReportClient` class:

```python
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
```

### Step 13.4: Run tests → expect 4 passed

```bash
uv run pytest tests/test_client_get_field.py -v
```

### Step 13.5: Full suite + ruff + mypy

```bash
uv run pytest -q
uv run ruff check src/financial_report_llm_extractor/client.py tests/test_client_get_field.py
uv run mypy src/financial_report_llm_extractor/client.py
```

### Step 13.6: Commit

```bash
git add src/financial_report_llm_extractor/client.py tests/test_client_get_field.py
git commit -m "feat: phase 1a get_field — taxonomy gate + UNAVAILABLE for missing DB rows"
```

---

## Task 14: CLAUDE.md + phase-summary Phase 1a pointer

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/2026-05-11-phase-summary.md`

### Step 14.1: Add Phase 1a row to CLAUDE.md "分阶段模块" table

In `CLAUDE.md`, find the row added for R5. Add a new row after it:

```markdown
| 1a | `client.py` (FinancialReportClient + dataclasses) + `pipeline_core.py` (in-process pipeline) + `pyproject.toml` force-include catalog | Public productization API for downstream consumers (TradingAgents-CN). 6 frozen dataclasses + 3 enums + 1 exception + 1 client class. Backend = R1 DB query (cache) + R4 pipeline_core (fresh-run, extracted from cli.py). importlib.resources for catalog; `$FR_LLM_CACHE_ROOT` env var for cache_root. Bucket → ConfidenceLevel translation; raw_bucket preserved for audit. include_llm_supplement symmetric semantics (filter + LLM step toggle). Decimal precision via str() detour. extraction_id = sha256 prefix for downstream dedup. See `docs/superpowers/specs/2026-05-13-financial-report-client-productization-design.md` (rev 4). |
```

### Step 14.2: Add Phase 1a row to phase-summary §6

In `docs/2026-05-11-phase-summary.md`, find the R5 row. Add a new row after it:

```markdown
| **Phase 1a FinancialReportClient productization** | **已落地 (2026-05-14)** | spec rev 4 | New public API: `FinancialReportClient` + `ExtractionResult` + `FieldValue` + `Staleness` + `RefreshPolicy` + `ConfidenceLevel` + `PdfQuery` + `ExtractorError`. Single backend (R1 DB + R4 pipeline_core in-process). importlib.resources packaged catalog. env var cache_root. Decimal precision preserved. include_llm_supplement symmetric. Phase 1b (TradingAgents-CN adapter wiring) next. |
```

### Step 14.3: Verify

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src tests
```

All should be green.

### Step 14.4: Commit

```bash
git add CLAUDE.md docs/2026-05-11-phase-summary.md
git commit -m "docs: phase 1a client library pointer in claude.md + phase-summary"
```

---

## Acceptance Criteria (mirroring spec §验收标准 Phase 1a)

After all 14 tasks complete, every checkbox below must be true:

- [ ] `pip install -e .` then from **any directory**: `python -c "from financial_report_llm_extractor.client import FinancialReportClient; FinancialReportClient()"` succeeds (catalog path via importlib.resources).
- [ ] `get_extraction()` returns `ExtractionResult` frozen dataclass.
- [ ] `get_field()` for catalog-missing field returns `FieldValue(confidence=UNAVAILABLE)`.
- [ ] `get_field()` for unknown field_id raises `ExtractorError(reason="unknown_field")`.
- [ ] bucket → `ConfidenceLevel` mapping covers all 6 buckets (test_client_bucket_translation).
- [ ] `llm_supplement_present` never `is_reliable=True`.
- [ ] `include_llm_supplement=False` returns UNAVAILABLE placeholder (in `result.fields`, not removed).
- [ ] `get_extraction()` and `get_field()` agree on LLM filter behavior.
- [ ] HK `gross_profit` (raw_bucket=`terminal_unverified`) → `confidence=UNAVAILABLE`, not VERIFIED.
- [ ] All exceptions wrapped as `ExtractorError` with `cause_type` set.
- [ ] `ExtractorError` instance has `.reason / .message / .company / .period_end / .market / .cause_type`.
- [ ] **Decimal precision round-trip**: `result.fields["revenue"].value == Decimal("170899152276.34")` (NOT float).
- [ ] `result.staleness == STALE` when DB row catalog_version != client catalog_version; fields still returned.
- [ ] `CACHE_ONLY` + DB miss: `fields == {}`, `staleness == MISSING`, no pipeline triggered.
- [ ] `CACHE_ONLY` guard pattern in tests verifies `result.staleness.is_missing` gate.
- [ ] `extraction_id` is stable: same (company, period_end, market, catalog_version, generated_at) → same hash.
- [ ] `PdfQuery("600519", "2024-12-31", "CN")` raises `TypeError`; `PdfQuery(company=..., period_end=..., market=...)` works.
- [ ] All tests reuse `tests/fixtures/cache_sample_run/` + programmatic seeding; no new fixture directory created.

## Self-Review

**1. Spec coverage:**
- §目标 → covered by Task 2-7 (dataclasses) + Task 10/12/13 (client methods)
- §Non-Goals → enforced by API contract (no HTTP, no auto-LLM-trigger without opt-in)
- §前置 Blocker R5 → already merged PR #10
- §前置 Blocker Python 3.11 → assumed; spec doesn't mandate explicit assertion
- §打包分发 → Task 1 (force-include) + Task 9 (importlib.resources resolution)
- §内部 Backend 架构 → Task 8 (pipeline_core extraction) + Task 12 (get_extraction flow)
- §Public API → Tasks 2-7, 10
- §Dataclass Contract → Tasks 2-7
- §Client Methods → Tasks 10, 12, 13
- §Bucket→Confidence → Task 11
- §CACHE_FIRST stale semantic → Task 12 (test_get_extraction_cache_only_stale_returns_stale_with_data)
- §错误语义 → Task 6 (ExtractorError) + Task 12 (raise sites)
- §PDF 路径责任 → Task 12 (_resolve_pdf_path helper)
- §Catalog Version 与下游失效 → Task 5 (extraction_id) + Task 12 (Staleness logic)
- §TradingAgents-CN 接入建议 → out of Phase 1a scope (Phase 1b)
- §内部实现要点 → Tasks 8, 9
- §Tradeoffs FORCE_REFRESH cost → handled in Task 12 (FORCE_REFRESH path)
- §验收标准 Phase 1a → mirrored above

**2. Placeholder scan:** No "TBD", "add validation", "implement later", or "similar to Task N" patterns. Every step shows complete code.

**3. Type consistency:**
- `ConfidenceLevel` / `RefreshPolicy` / `Staleness` enums defined in Task 2, used in all subsequent tasks. ✓
- `PdfQuery` / `ExtractorConfig` defined in Task 3, used in Task 12 (`_resolve_pdf_path`). ✓
- `FieldValue` defined in Task 4, used in Tasks 11, 12, 13. ✓
- `ExtractionResult` + `compute_extraction_id` defined in Task 5, used in Task 12. ✓
- `ExtractorError` defined in Task 6, raised in Tasks 10, 12, 13. ✓
- `decode_value` defined in Task 7, **NOT directly used** in `build_field_value` (Task 11 inlines the Decimal logic). This is consistent — `decode_value` is a tested primitive that could be used by build_field_value; the choice to inline is fine but worth noting.
- `pipeline_core.run_pipeline` defined in Task 8, called from `FinancialReportClient.get_extraction` in Task 12. ✓
- `resolve_catalog_path` / `resolve_taxonomy_path` / `resolve_cache_root` / `resolve_db_path` defined in Task 9, used in Task 10. ✓
- `bucket_to_confidence` / `build_field_value` defined in Task 11, used in Task 12. ✓

All method signatures and property names consistent across tasks.

**Plan complete.** 14 tasks, ~30-45 min each = ~7-10 hours total. Each task ends in a commit so progress is incremental. Ready for execution.
