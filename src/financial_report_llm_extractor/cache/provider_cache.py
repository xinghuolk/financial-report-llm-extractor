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
- ttl_hours < 0: cache_get always returns None (bypass)

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
