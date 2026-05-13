"""Content-addressed cache for LLM JSON completions (R3 layer-2).

Cache key: SHA-256 of canonical-JSON of (model, system_prompt, user_payload).
No TTL — given identical inputs the response should not change. Catalog
changes propagate via chunk content → hash → cache miss → re-fetch.

Cache file layout: tmp/.cache/llm/<sha256>.json
File format:
  {
    "schema_version": "llm_cache_v1",
    "key": "<sha256>",
    "cached_at": "<ISO8601 UTC>",
    "request": {...},
    "response": {...}
  }

Malformed cache files → silent miss (next cache_put overwrites).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "llm_cache_v1"


def cache_key(
    *,
    model: str,
    system_prompt: str,
    user_payload: dict[str, Any],
) -> str:
    """SHA-256 hex digest of the canonical-JSON request triple."""
    canonical = json.dumps(
        {
            "model": model,
            "system_prompt": system_prompt,
            "user_payload": user_payload,
        },
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def cache_path(*, cache_root: Path, key: str) -> Path:
    """Return path cache_root/llm/<key>.json."""
    if len(key) != 64 or not all(c in "0123456789abcdef" for c in key):
        raise ValueError(f"key must be a 64-char hex SHA-256 digest, got {key!r}")
    return cache_root / "llm" / f"{key}.json"


def cache_get(
    *,
    cache_root: Path,
    key: str,
) -> dict[str, Any] | None:
    """Return cached entry dict ({request, response}) or None on miss/malformed."""
    path = cache_path(cache_root=cache_root, key=key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != SCHEMA_VERSION:
        return None
    request = payload.get("request")
    response = payload.get("response")
    if not isinstance(request, dict) or not isinstance(response, dict):
        return None
    return {"request": request, "response": response}


def cache_put(
    *,
    cache_root: Path,
    key: str,
    request: dict[str, Any],
    response: dict[str, Any],
) -> None:
    """Write request+response to the cache."""
    path = cache_path(cache_root=cache_root, key=key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "key": key,
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "request": request,
        "response": response,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
