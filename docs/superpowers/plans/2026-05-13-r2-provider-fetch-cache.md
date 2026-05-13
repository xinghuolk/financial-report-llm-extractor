# R2 Provider Fetch Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `tmp/.cache/{akshare,yahoo}/<cid>_<period>.json` content-addressed cache layer to `fetch-source-inventory`, eliminating redundant AKShare/Yahoo network calls across CLI invocations sharing the same (company, period_end). Configurable TTL (default 24h), `--skip-if-cached` flag, `--no-cache` bypass.

**Architecture:** New `cache/provider_cache.py` with read-through/write-through helpers. `source_inventory_fetch._fetch_akshare_for_company` and `_fetch_yahoo_for_company` consult the cache before hitting the network. Cache files store `{"fetched_at": ISO8601, "records": [SourceInventoryRecord-as-dict, ...]}`. TTL compared against `fetched_at`; expiry triggers re-fetch. Zero new deps (stdlib `json` + `datetime`).

**Tech Stack:** Python 3.11 stdlib, pytest, project's existing `SourceInventoryRecord` dataclass.

---

## File Structure

| File | Role |
|---|---|
| `src/financial_report_llm_extractor/cache/provider_cache.py` | `read_or_fetch()` + `cache_path()` + serializers |
| `src/financial_report_llm_extractor/structured_sources/source_inventory_fetch.py` | Modified: wrap fetch helpers with cache |
| `src/financial_report_llm_extractor/cli.py` | Modified: add `--cache-ttl-hours` / `--skip-if-cached` / `--no-cache` flags to `fetch-source-inventory` |
| `tests/test_cache_provider_cache.py` | Unit tests for cache module |
| `tests/test_source_inventory_fetch.py` (or analogous) | Integration tests for cache-wrapped fetching |
| `tests/fixtures/cache_provider/` | Optional fixture cache files for round-trip tests |

---

## Key Design Decisions

1. **Cache key is `(provider, company, period_end)`** — period_end string like `"2024-12-31"`. One file per cohort per provider.
2. **Cache file format**: `{"fetched_at": "<ISO8601 UTC>", "records": [<record_dict>, ...]}`. Record dict matches `SourceInventoryRecord.to_dict()` for round-trip via `from_dict`.
3. **TTL semantics**:
   - `ttl_hours > 0`: cache valid if `now - fetched_at < ttl_hours`
   - `ttl_hours == 0`: cache always expired (force refresh)
   - `ttl_hours < 0` (or `--no-cache`): cache bypassed entirely (no read, no write)
4. **Cache miss/expired**: caller invokes fetch closure, then `cache_put()` writes the result. Errors during fetch propagate normally (cache is not written on failure).
5. **No automatic invalidation by data fingerprint** — TTL is the only freshness mechanism. Adequate for daily-update providers; manual `rm -rf tmp/.cache/` always works.
6. **`--skip-if-cached`** is a CLI affordance, not a cache-layer concept. When set on `fetch-source-inventory`, if all (provider, company, period_end) cache files are fresh, the CLI exits successfully without re-fetching anything; otherwise it falls through to the normal flow.

---

## Cache File Schema

```json
{
  "schema_version": "provider_cache_v1",
  "provider": "akshare",
  "company": "600519",
  "period_end": "2024-12-31",
  "fetched_at": "2026-05-13T10:00:00+00:00",
  "records": [
    {
      "company_id": "600519",
      "provider": "akshare",
      "statement_type": "income_statement",
      ...
    }
  ]
}
```

---

## Task 1: `cache_path()` + `cache_get()` + `cache_put()` foundation

**Files:**
- Create: `src/financial_report_llm_extractor/cache/provider_cache.py`
- Test: `tests/test_cache_provider_cache.py`

- [ ] **Step 1.1: Write the failing test**

Write `tests/test_cache_provider_cache.py`:

```python
"""Provider fetch cache: cache_path, cache_get, cache_put round-trip."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from financial_report_llm_extractor.cache.provider_cache import (
    cache_get,
    cache_path,
    cache_put,
)


def test_cache_path_layout(tmp_path: Path) -> None:
    p = cache_path(
        cache_root=tmp_path,
        provider="akshare",
        company="600519",
        period_end="2024-12-31",
    )
    assert p == tmp_path / "akshare" / "600519_2024-12-31.json"


def test_cache_put_then_get_returns_records(tmp_path: Path) -> None:
    records = [
        {"company_id": "600519", "provider": "akshare", "kind": "bs"},
        {"company_id": "600519", "provider": "akshare", "kind": "is"},
    ]
    cache_put(
        cache_root=tmp_path, provider="akshare",
        company="600519", period_end="2024-12-31",
        records=records,
    )
    got = cache_get(
        cache_root=tmp_path, provider="akshare",
        company="600519", period_end="2024-12-31",
        ttl_hours=24,
    )
    assert got == records


def test_cache_get_miss_returns_none(tmp_path: Path) -> None:
    assert cache_get(
        cache_root=tmp_path, provider="akshare",
        company="nope", period_end="2024-12-31",
        ttl_hours=24,
    ) is None


def test_cache_get_expired_returns_none(tmp_path: Path) -> None:
    cache_put(
        cache_root=tmp_path, provider="yahoo",
        company="01810", period_end="2024-12-31",
        records=[{"x": 1}],
    )
    # Forge an old fetched_at by rewriting the file
    cache_file = cache_path(
        cache_root=tmp_path, provider="yahoo",
        company="01810", period_end="2024-12-31",
    )
    import json
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    payload["fetched_at"] = old
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    assert cache_get(
        cache_root=tmp_path, provider="yahoo",
        company="01810", period_end="2024-12-31",
        ttl_hours=24,  # 48h old -> expired
    ) is None


def test_cache_get_ttl_zero_always_expired(tmp_path: Path) -> None:
    cache_put(
        cache_root=tmp_path, provider="akshare",
        company="600519", period_end="2024-12-31",
        records=[{"x": 1}],
    )
    assert cache_get(
        cache_root=tmp_path, provider="akshare",
        company="600519", period_end="2024-12-31",
        ttl_hours=0,
    ) is None


def test_cache_put_overwrites_existing(tmp_path: Path) -> None:
    cache_put(
        cache_root=tmp_path, provider="akshare",
        company="600519", period_end="2024-12-31",
        records=[{"old": True}],
    )
    cache_put(
        cache_root=tmp_path, provider="akshare",
        company="600519", period_end="2024-12-31",
        records=[{"new": True}],
    )
    got = cache_get(
        cache_root=tmp_path, provider="akshare",
        company="600519", period_end="2024-12-31",
        ttl_hours=24,
    )
    assert got == [{"new": True}]


def test_cache_get_malformed_file_returns_none(tmp_path: Path) -> None:
    """If cache file exists but is malformed JSON, treat as miss."""
    cache_file = cache_path(
        cache_root=tmp_path, provider="akshare",
        company="600519", period_end="2024-12-31",
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("not valid json {", encoding="utf-8")
    assert cache_get(
        cache_root=tmp_path, provider="akshare",
        company="600519", period_end="2024-12-31",
        ttl_hours=24,
    ) is None
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
uv run pytest tests/test_cache_provider_cache.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 1.3: Implement `provider_cache.py`**

```python
"""Content-addressed cache for AKShare/Yahoo provider responses (R2 layer-2).

Cache key: (provider, company, period_end). One file per cohort per provider.
File format:
  {
    "schema_version": "provider_cache_v1",
    "provider": "akshare",
    "company": "600519",
    "period_end": "2024-12-31",
    "fetched_at": "2026-05-13T10:00:00+00:00",
    "records": [...]
  }

TTL semantics:
- ttl_hours > 0: fresh if now - fetched_at < ttl_hours
- ttl_hours == 0: always expired (force refresh)
- ttl_hours < 0: callers should bypass entirely; the helpers still return None
  on cache_get for negative ttl_hours for safety.

Malformed cache files are treated as miss (silently) so a corrupt file never
blocks a re-fetch; the next cache_put overwrites it.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "provider_cache_v1"


def cache_path(
    *,
    cache_root: Path,
    provider: str,
    company: str,
    period_end: str,
) -> Path:
    """Return the cache file path for a (provider, company, period_end) key."""
    return cache_root / provider / f"{company}_{period_end}.json"


def cache_get(
    *,
    cache_root: Path,
    provider: str,
    company: str,
    period_end: str,
    ttl_hours: int,
) -> list[dict[str, Any]] | None:
    """Return cached records if present and fresh; None on miss/expired/malformed."""
    if ttl_hours < 0:
        return None
    path = cache_path(
        cache_root=cache_root, provider=provider,
        company=company, period_end=period_end,
    )
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    fetched_at_raw = payload.get("fetched_at")
    if not isinstance(fetched_at_raw, str):
        return None
    try:
        fetched_at = datetime.fromisoformat(fetched_at_raw)
    except ValueError:
        return None
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - fetched_at
    if age >= timedelta(hours=ttl_hours):
        return None
    records = payload.get("records")
    if not isinstance(records, list):
        return None
    return [r for r in records if isinstance(r, dict)]


def cache_put(
    *,
    cache_root: Path,
    provider: str,
    company: str,
    period_end: str,
    records: list[dict[str, Any]],
) -> None:
    """Write records to the cache, overwriting any prior entry."""
    path = cache_path(
        cache_root=cache_root, provider=provider,
        company=company, period_end=period_end,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "company": company,
        "period_end": period_end,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "records": records,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
```

- [ ] **Step 1.4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cache_provider_cache.py -v
```

Expected: 7 passed.

- [ ] **Step 1.5: Run ruff + mypy**

```bash
uv run ruff check src/financial_report_llm_extractor/cache tests/test_cache_provider_cache.py
uv run mypy src/financial_report_llm_extractor/cache
```

Expected: clean.

- [ ] **Step 1.6: Commit**

```bash
git add src/financial_report_llm_extractor/cache/provider_cache.py \
        tests/test_cache_provider_cache.py
git commit -m "feat: r2 provider_cache.py — content-addressed cache with TTL"
```

---

## Task 2: Integrate cache into `source_inventory_fetch.py`

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/source_inventory_fetch.py`
- Test: `tests/test_source_inventory_fetch_cache.py` (new — keeps cache-specific tests isolated)

Before editing: read `source_inventory_fetch.py` to find:
- `_fetch_akshare_for_company` signature and return type
- `_fetch_yahoo_for_company` signature and return type
- `fetch_source_inventory` orchestrator

The integration wraps each fetch helper with a check: cache_get first, on miss call the provider client, on success cache_put.

### Step 2.1: Read existing `source_inventory_fetch.py`

Find the line range of `_fetch_akshare_for_company` and `_fetch_yahoo_for_company`. They likely take `company`, `market`, `client`, `store` and return `list[SourceInventoryRecord]`.

### Step 2.2: Write integration test

Write `tests/test_source_inventory_fetch_cache.py`:

```python
"""Verify _fetch_*_for_company helpers honor the provider cache."""

from pathlib import Path
from unittest.mock import MagicMock

from financial_report_llm_extractor.cache.provider_cache import cache_put
from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
    _fetch_akshare_for_company,
)


def test_fetch_akshare_uses_cache_when_fresh(
    monkeypatch: "pytest.MonkeyPatch", tmp_path: Path
) -> None:
    """If cache has fresh records, _fetch_akshare_for_company must NOT call the client."""
    # Seed cache
    fake_record_dict = {
        "company_id": "600519",
        "provider": "akshare",
        "statement_type": "income_statement",
        # ... minimal subset
    }
    cache_put(
        cache_root=tmp_path, provider="akshare",
        company="600519", period_end="2024-12-31",
        records=[fake_record_dict],
    )

    client = MagicMock()
    # ... call _fetch_akshare_for_company with cache_root=tmp_path,
    #     ttl_hours=24, and verify client.fetch_balance_sheet etc. NOT called
    # (exact assertion depends on the function signature — see Step 2.1)
```

(This test will be refined in Step 2.4 once we know the actual signatures.)

### Step 2.3: Modify `_fetch_akshare_for_company` and `_fetch_yahoo_for_company`

Add new parameters to each:
- `cache_root: Path | None = None` — if None, no caching
- `ttl_hours: int = 24` — TTL in hours

Before invoking the client:
```python
if cache_root is not None:
    cached = cache_get(
        cache_root=cache_root, provider="akshare",
        company=company, period_end=period_end,
        ttl_hours=ttl_hours,
    )
    if cached is not None:
        return [SourceInventoryRecord.from_dict(r) for r in cached]
```

After successful fetch:
```python
if cache_root is not None:
    cache_put(
        cache_root=cache_root, provider="akshare",
        company=company, period_end=period_end,
        records=[r.to_dict() for r in records],
    )
```

**Note**: `SourceInventoryRecord.from_dict` and `to_dict` may not exist yet. Check `src/financial_report_llm_extractor/structured_sources/artifacts.py` (or wherever the dataclass lives). If missing, add them as part of Task 2.

### Step 2.4: Plumb `cache_root` + `ttl_hours` through `fetch_source_inventory()`

The orchestrator should accept the same two parameters and pass them down to the per-provider helpers. Default `cache_root=Path("tmp/.cache")` and `ttl_hours=24`.

### Step 2.5: Run tests + ruff + mypy
### Step 2.6: Commit

```bash
git commit -m "feat: r2 wrap akshare/yahoo fetchers with provider_cache"
```

**Implementation notes for the subagent:**
- The exact signatures of `_fetch_akshare_for_company` / `_fetch_yahoo_for_company` will inform the test fixtures. Read those functions first before writing the cache-integration test.
- If `SourceInventoryRecord` lacks `from_dict` / `to_dict`, add them as part of this task. They should be straightforward dataclass round-trip helpers.
- Period end is derived from `PeriodSpec` (likely has a `period_end_str` property or similar). Use whatever the existing code uses to render the period for filenames.

---

## Task 3: CLI flags `--cache-ttl-hours`, `--skip-if-cached`, `--no-cache`

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Test: `tests/test_cli.py` (extend)

### Step 3.1: Locate the `fetch-source-inventory` subparser

Search `cli.py` for `subparsers.add_parser("fetch-source-inventory"` and the dispatch branch `if args.command == "fetch-source-inventory":` / `_run_fetch_source_inventory(...)`.

### Step 3.2: Add 3 new flags to the subparser

```python
fetch_source_parser.add_argument(
    "--cache-ttl-hours", type=int, default=24,
    help="Cache TTL in hours (default 24; 0 = always re-fetch).",
)
fetch_source_parser.add_argument(
    "--no-cache", action="store_true",
    help="Bypass the provider cache entirely (no read, no write).",
)
fetch_source_parser.add_argument(
    "--skip-if-cached", action="store_true",
    help="Exit successfully without fetching if all keys are cache-fresh.",
)
```

### Step 3.3: Update dispatch / `_run_fetch_source_inventory()`

If `--no-cache` set: pass `cache_root=None` to `fetch_source_inventory`.
Else: pass `cache_root=Path("tmp/.cache")` and `ttl_hours=args.cache_ttl_hours`.

If `--skip-if-cached` set: before invoking the orchestrator, manually check `cache_get` for each (provider, company, period_end). If all hits, print JSON `{"skipped": True, "providers": [...]}` and return 0.

### Step 3.4: Tests

Add 3 new tests to `tests/test_cli.py`:

```python
def test_cli_fetch_source_inventory_no_cache_flag_disables_cache(
    tmp_path: Path, monkeypatch: "pytest.MonkeyPatch",
) -> None:
    """--no-cache: ensure no cache read/write happens (mock provider client)."""
    # ... assertion: cache_get/cache_put NOT called, or cache_root=None
    # passed to fetch_source_inventory


def test_cli_fetch_source_inventory_skip_if_cached_returns_early(
    tmp_path: Path, monkeypatch: "pytest.MonkeyPatch",
) -> None:
    """--skip-if-cached: with pre-warmed cache, exit 0 without invoking provider."""
    # ... seed cache via cache_put, run main(["fetch-source-inventory", ..., "--skip-if-cached"])
    # assert exit 0 and provider client never invoked


def test_cli_fetch_source_inventory_default_cache_ttl_is_24h(
    tmp_path: Path,
) -> None:
    """Smoke: default args set ttl_hours=24 in the call."""
    # Inspect the parser's default
```

### Step 3.5: Run tests + ruff + mypy
### Step 3.6: Commit

```bash
git commit -m "feat: r2 cli flags --cache-ttl-hours / --no-cache / --skip-if-cached"
```

---

## Task 4: CLAUDE.md + phase-summary R2 pointer

Add a row to CLAUDE.md "分阶段模块" table:

```markdown
| R2 | `cache/provider_cache.py` + `source_inventory_fetch.py` integration | Two-level extraction cache layer-2 (provider tier): `tmp/.cache/{akshare,yahoo}/<cid>_<period>.json` content-addressed cache + 24h default TTL. New `fetch-source-inventory` flags: `--cache-ttl-hours`, `--no-cache`, `--skip-if-cached`. Eliminates redundant network calls across CLI invocations sharing same (company, period). |
```

Add a row to phase-summary §6:

```markdown
| **R2 Provider fetch cache** | **已落地 (2026-05-13)** | R2 plan | `tmp/.cache/{akshare,yahoo}/` content-addressed; 24h default TTL; `--skip-if-cached` / `--no-cache` flags. Deduplicates AKShare/Yahoo network calls across CLI invocations. |
```

```bash
git commit -m "docs: r2 provider fetch cache pointer in claude.md + phase-summary"
```

---

## Acceptance Criteria

- 13+ new tests passing (7 unit + 3 integration + 3 CLI), no regressions
- `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src tests` all clean
- `uv run financial-report-llm-extractor fetch-source-inventory --company 600519 --year 2024 --market CN --out /tmp/r2_test` — first run hits network, second run (within 24h) reads from cache; verify by inspecting `tmp/.cache/akshare/600519_2024-12-31.json`
- `--skip-if-cached` exits 0 without calling provider when cache fresh
- No new entries in `pyproject.toml` `dependencies`

## Self-Review

- [x] No new dependencies
- [x] Cache key includes provider so akshare/yahoo don't collide
- [x] TTL semantics explicit (0 = always expired; negative = bypass)
- [x] Malformed cache files treated as miss (resilient)
- [x] `--no-cache` bypass works at CLI layer (no test pollution of real cache dir)
- [x] Integration test uses MagicMock client to verify cache hit avoids provider call
