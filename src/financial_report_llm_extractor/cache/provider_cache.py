"""Content-addressed cache for AKShare/Yahoo provider responses (R2 layer-2).

Cache key: (provider, company, period_end). One file per cohort per provider.
File format (v2):
  {
    "schema_version": "provider_cache_v2",
    "provider": "akshare",
    "company": "600519",
    "period_end": "2024-12-31",
    "fetched_at": "2026-05-13T10:00:00+00:00",
    "records": [...],
    "artifacts": [
      {"source": "akshare", "artifact_id": "aid-1", "payload": {...}}
    ]
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

SCHEMA_VERSION = "provider_cache_v2"

_INVALID_SEGMENT_CHARS = ("/", "\\", "..", "\x00")


def _validate_segment(name: str, value: str) -> None:
    if not value:
        raise ValueError(f"{name} must be non-empty")
    for bad in _INVALID_SEGMENT_CHARS:
        if bad in value:
            raise ValueError(
                f"{name}={value!r} contains forbidden substring {bad!r}; "
                f"cache key segments must be plain identifiers"
            )


def cache_path(
    *,
    cache_root: Path,
    provider: str,
    company: str,
    period_end: str,
) -> Path:
    """Return the cache file path for a (provider, company, period_end) key."""
    _validate_segment("provider", provider)
    _validate_segment("company", company)
    _validate_segment("period_end", period_end)
    return cache_root / provider / f"{company}_{period_end}.json"


def cache_get_with_artifacts(
    *,
    cache_root: Path,
    provider: str,
    company: str,
    period_end: str,
    ttl_hours: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    """Return (records, artifacts) tuple if cache hit fresh; None otherwise.

    Treats schema_version mismatch as miss (graceful schema-drift handling).
    Treats malformed JSON, missing fields, expired TTL all as miss.
    """
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
    # Schema version check (graceful drift handling)
    if payload.get("schema_version") != SCHEMA_VERSION:
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
    artifacts = payload.get("artifacts")
    if not isinstance(records, list) or not isinstance(artifacts, list):
        return None
    return (
        [r for r in records if isinstance(r, dict)],
        [a for a in artifacts if isinstance(a, dict)],
    )


def cache_put_with_artifacts(
    *,
    cache_root: Path,
    provider: str,
    company: str,
    period_end: str,
    records: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
) -> None:
    """Write records + artifacts to cache, overwriting any prior entry."""
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
        "artifacts": artifacts,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def cache_get(
    *,
    cache_root: Path,
    provider: str,
    company: str,
    period_end: str,
    ttl_hours: int,
) -> list[dict[str, Any]] | None:
    """Return cached records if present and fresh; None on miss/expired/malformed.

    Delegates to cache_get_with_artifacts; returns only the records list.
    """
    result = cache_get_with_artifacts(
        cache_root=cache_root, provider=provider,
        company=company, period_end=period_end,
        ttl_hours=ttl_hours,
    )
    if result is None:
        return None
    records, _artifacts = result
    return records


def cache_put(
    *,
    cache_root: Path,
    provider: str,
    company: str,
    period_end: str,
    records: list[dict[str, Any]],
) -> None:
    """Write records to the cache, overwriting any prior entry.

    Delegates to cache_put_with_artifacts with an empty artifacts list.
    """
    cache_put_with_artifacts(
        cache_root=cache_root, provider=provider,
        company=company, period_end=period_end,
        records=records,
        artifacts=[],
    )
