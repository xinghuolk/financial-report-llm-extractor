"""LLM transport clients integrate with the llm_cache module."""

from pathlib import Path

from financial_report_llm_extractor.cache.llm_cache import (
    cache_key,
    cache_put,
)
from financial_report_llm_extractor.llm_transport import (
    LlmTransportConfig,
    OpenAiCompatibleClient,
    create_llm_client,
)


class _CountingTransport:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls = 0

    def post_json(
        self,
        url: str,
        headers: dict,
        payload: dict,
        timeout_seconds: float,
    ) -> dict:
        self.calls += 1
        return self.response


def _make_openai_config() -> LlmTransportConfig:
    # Use ollama provider so api_key_required=False — tests need no env var.
    return LlmTransportConfig(
        provider="ollama",
        model="m",
        base_url="https://example.com",
        api_key_env="OLLAMA_API_KEY",
        timeout_seconds=10,
        max_retries=0,
    )


def test_openai_client_skips_http_on_cache_hit(tmp_path: Path) -> None:
    response = {"choices": [{"message": {"content": '{"ok":true}'}}]}
    config = _make_openai_config()

    # Prime the cache
    sys_p = "Return JSON."
    user_p: dict = {"field_id": "revenue"}
    key = cache_key(model="m", system_prompt=sys_p, user_payload=user_p)
    cache_put(
        cache_root=tmp_path,
        key=key,
        request={"model": "m"},
        response=response,
    )

    transport = _CountingTransport(response={"never": "called"})
    client = OpenAiCompatibleClient(
        config=config,
        transport=transport,
        cache_root=tmp_path,
    )
    result = client.complete_json(system_prompt=sys_p, user_payload=user_p)
    assert result == response
    assert transport.calls == 0
    # The raw_exchanges should be populated with the cached request+response
    assert len(client.raw_exchanges) == 1


def test_openai_client_writes_cache_on_miss(tmp_path: Path) -> None:
    live_response = {"choices": [{"message": {"content": '{"x": 1}'}}]}
    config = _make_openai_config()
    transport = _CountingTransport(response=live_response)
    client = OpenAiCompatibleClient(
        config=config,
        transport=transport,
        cache_root=tmp_path,
    )
    sys_p = "Return JSON."
    user_p: dict = {"y": 2}
    r1 = client.complete_json(system_prompt=sys_p, user_payload=user_p)
    assert transport.calls == 1
    assert r1 == live_response

    # Cache file should now exist
    key = cache_key(model="m", system_prompt=sys_p, user_payload=user_p)
    assert (tmp_path / "llm" / f"{key}.json").exists()

    # Second client instance should hit cache
    client2 = OpenAiCompatibleClient(
        config=config,
        transport=transport,
        cache_root=tmp_path,
    )
    r2 = client2.complete_json(system_prompt=sys_p, user_payload=user_p)
    assert r2 == live_response
    assert transport.calls == 1  # unchanged


def test_openai_client_no_cache_when_cache_root_is_none() -> None:
    """Backward compat: cache_root=None means no caching."""
    config = _make_openai_config()
    transport = _CountingTransport(response={"x": 1})
    client = OpenAiCompatibleClient(
        config=config,
        transport=transport,
        cache_root=None,
    )
    client.complete_json(system_prompt="p", user_payload={"q": 1})
    client.complete_json(system_prompt="p", user_payload={"q": 1})
    assert transport.calls == 2


def test_create_llm_client_forwards_cache_root(tmp_path: Path) -> None:
    """The factory must wire cache_root through."""
    config = _make_openai_config()
    client = create_llm_client(config, cache_root=tmp_path)
    assert client.cache_root == tmp_path  # type: ignore[attr-defined]
