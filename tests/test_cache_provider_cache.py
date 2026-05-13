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
        ttl_hours=24,
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


def test_cache_path_rejects_path_traversal(tmp_path: Path) -> None:
    """Reject any segment containing /, \\, .., or NUL to prevent escape."""
    with pytest.raises(ValueError, match="forbidden substring"):
        cache_path(
            cache_root=tmp_path, provider="../escape",
            company="600519", period_end="2024-12-31",
        )
    with pytest.raises(ValueError, match="forbidden substring"):
        cache_path(
            cache_root=tmp_path, provider="akshare",
            company="600519/../etc", period_end="2024-12-31",
        )
    with pytest.raises(ValueError, match="must be non-empty"):
        cache_path(
            cache_root=tmp_path, provider="",
            company="600519", period_end="2024-12-31",
        )
