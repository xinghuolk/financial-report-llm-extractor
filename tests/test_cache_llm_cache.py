"""LLM completion cache: deterministic content-addressed storage."""

from pathlib import Path
from typing import Any

from financial_report_llm_extractor.cache.llm_cache import (
    cache_get,
    cache_key,
    cache_put,
)


def test_cache_key_is_deterministic() -> None:
    """Same inputs → same hash."""
    k1 = cache_key(
        model="deepseek-chat",
        system_prompt="Return JSON.",
        user_payload={"field_id": "revenue", "chunks": ["a", "b"]},
    )
    k2 = cache_key(
        model="deepseek-chat",
        system_prompt="Return JSON.",
        user_payload={"field_id": "revenue", "chunks": ["a", "b"]},
    )
    assert k1 == k2
    assert len(k1) == 64  # SHA-256 hex


def test_cache_key_differs_on_model_change() -> None:
    base: dict[str, Any] = dict(
        system_prompt="Return JSON.",
        user_payload={"x": 1},
    )
    k1 = cache_key(model="deepseek-chat", **base)
    k2 = cache_key(model="gpt-5.5", **base)
    assert k1 != k2


def test_cache_key_differs_on_prompt_change() -> None:
    k1 = cache_key(
        model="deepseek-chat", system_prompt="Return JSON.",
        user_payload={"x": 1},
    )
    k2 = cache_key(
        model="deepseek-chat", system_prompt="Return strict JSON.",
        user_payload={"x": 1},
    )
    assert k1 != k2


def test_cache_key_differs_on_payload_change() -> None:
    base: dict[str, Any] = dict(model="deepseek-chat", system_prompt="x")
    k1 = cache_key(**base, user_payload={"x": 1})
    k2 = cache_key(**base, user_payload={"x": 2})
    assert k1 != k2


def test_cache_key_dict_ordering_insensitive() -> None:
    """Payload key order must not affect the hash."""
    k1 = cache_key(
        model="m", system_prompt="p",
        user_payload={"a": 1, "b": 2},
    )
    k2 = cache_key(
        model="m", system_prompt="p",
        user_payload={"b": 2, "a": 1},
    )
    assert k1 == k2


def test_cache_put_then_get_round_trip(tmp_path: Path) -> None:
    key = cache_key(model="m", system_prompt="p", user_payload={"x": 1})
    request = {"model": "m", "messages": [{"role": "user", "content": "..."}]}
    response = {"choices": [{"message": {"content": '{"ok":true}'}}]}
    cache_put(cache_root=tmp_path, key=key, request=request, response=response)
    got = cache_get(cache_root=tmp_path, key=key)
    assert got is not None
    assert got["request"] == request
    assert got["response"] == response


def test_cache_get_miss_returns_none(tmp_path: Path) -> None:
    assert cache_get(
        cache_root=tmp_path, key="a" * 64,
    ) is None


def test_cache_get_malformed_returns_none(tmp_path: Path) -> None:
    """Malformed cache file treated as miss (resilient)."""
    cache_file = tmp_path / "llm" / ("b" * 64 + ".json")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("not valid json {", encoding="utf-8")
    assert cache_get(cache_root=tmp_path, key="b" * 64) is None


def test_cache_put_creates_parent_dir(tmp_path: Path) -> None:
    """cache_put auto-creates the tmp/.cache/llm/ dir."""
    key = "c" * 64
    cache_put(
        cache_root=tmp_path, key=key,
        request={}, response={"ok": True},
    )
    assert (tmp_path / "llm" / f"{key}.json").exists()
