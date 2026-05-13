import json
from pathlib import Path
from typing import Any
from urllib.error import URLError

from financial_report_llm_extractor.extraction import PromptRequest
from financial_report_llm_extractor.llm_transport import (
    LlmTransportConfig,
    OpenAiCompatibleClient,
    create_llm_client,
    response_json_text,
    resolve_provider_kind,
    run_real_transport_probe,
)


class FakeHttpTransport:
    def __init__(self, responses: list[dict[str, object] | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str], dict[str, object], float]] = []

    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        self.calls.append((url, headers, payload, timeout_seconds))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_load_llm_config_from_json(tmp_path: Path) -> None:
    config_path = tmp_path / "llm_config.json"
    config_path.write_text(
        json.dumps(
            {
                "provider": "openai-compatible",
                "model": "test-model",
                "base_url": "https://llm.example/v1",
                "api_key_env": "TEST_LLM_KEY",
                "timeout_seconds": 12,
                "max_retries": 2,
            }
        ),
        encoding="utf-8",
    )

    config = LlmTransportConfig.from_json(config_path)

    assert config.provider == "openai-compatible"
    assert config.model == "test-model"
    assert config.base_url == "https://llm.example/v1"
    assert config.api_key_env == "TEST_LLM_KEY"
    assert config.timeout_seconds == 12
    assert config.max_retries == 2


def test_load_deepseek_config_uses_provider_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "llm_config.json"
    config_path.write_text(
        json.dumps({"provider": "deepseek", "model": "deepseek-chat"}),
        encoding="utf-8",
    )

    config = LlmTransportConfig.from_json(config_path)

    assert config.provider == "deepseek"
    assert config.base_url == "https://api.deepseek.com/v1"
    assert config.api_key_env == "DEEPSEEK_API_KEY"
    assert resolve_provider_kind(config) == "openai-compatible"


def test_load_ollama_config_uses_provider_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "llm_config.json"
    config_path.write_text(
        json.dumps({"provider": "ollama", "model": "qwen2.5:7b"}),
        encoding="utf-8",
    )

    config = LlmTransportConfig.from_json(config_path)

    assert config.provider == "ollama"
    assert config.base_url == "http://localhost:11434/v1"
    assert config.api_key_env == "OLLAMA_API_KEY"
    assert resolve_provider_kind(config) == "openai-compatible"


def test_load_gemini_config_uses_provider_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "llm_config.json"
    config_path.write_text(
        json.dumps({"provider": "gemini", "model": "gemini-1.5-flash"}),
        encoding="utf-8",
    )

    config = LlmTransportConfig.from_json(config_path)

    assert config.provider == "gemini"
    assert config.base_url == "https://generativelanguage.googleapis.com/v1beta"
    assert config.api_key_env == "GEMINI_API_KEY"
    assert resolve_provider_kind(config) == "gemini"


def test_load_openai_codex_config_uses_subscription_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "llm_config.json"
    config_path.write_text(
        json.dumps({"provider": "openai-codex", "model": "gpt-5.3-codex"}),
        encoding="utf-8",
    )

    config = LlmTransportConfig.from_json(config_path)

    assert config.provider == "openai-codex"
    assert config.base_url == "https://chatgpt.com/backend-api/codex"
    assert config.api_key_env == ""
    assert resolve_provider_kind(config) == "codex-responses"


def test_load_claude_code_config_uses_subscription_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "llm_config.json"
    config_path.write_text(
        json.dumps({"provider": "claude-code", "model": "claude-sonnet-4-6"}),
        encoding="utf-8",
    )

    config = LlmTransportConfig.from_json(config_path)

    assert config.provider == "claude-code"
    assert config.base_url == "https://api.anthropic.com"
    assert config.api_key_env == ""
    assert resolve_provider_kind(config) == "anthropic-messages"


def test_response_json_text_reads_codex_responses_output_text() -> None:
    raw = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": json.dumps({"fields": []})}
                ],
            }
        ]
    }

    assert response_json_text(raw) == json.dumps({"fields": []})


def test_response_json_text_reads_anthropic_messages_text() -> None:
    raw = {"content": [{"type": "text", "text": json.dumps({"fields": []})}]}

    assert response_json_text(raw) == json.dumps({"fields": []})


def test_openai_compatible_client_builds_chat_completions_request(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("TEST_LLM_KEY", "secret-key")
    transport = FakeHttpTransport(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "fields": [
                                        {
                                            "field_id": "revenue",
                                            "status": "present",
                                            "value_raw": "100",
                                            "unit_context": "HKD million",
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ]
            }
        ]
    )
    client = OpenAiCompatibleClient(
        LlmTransportConfig(
            provider="openai-compatible",
            model="test-model",
            base_url="https://llm.example/v1",
            api_key_env="TEST_LLM_KEY",
            timeout_seconds=12,
        ),
        transport=transport,
    )

    response = client.extract(PromptRequest(field_id="revenue", candidates=()))

    assert response.fields[0].field_id == "revenue"
    assert transport.calls[0][0] == "https://llm.example/v1/chat/completions"
    assert transport.calls[0][1]["Authorization"] == "Bearer secret-key"
    assert transport.calls[0][2]["model"] == "test-model"
    assert transport.calls[0][3] == 12


def test_deepseek_client_uses_openai_compatible_defaults(monkeypatch: Any) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    transport = FakeHttpTransport(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"fields": [{"field_id": "cash", "status": "missing"}]}
                            )
                        }
                    }
                ]
            }
        ]
    )
    client = create_llm_client(
        LlmTransportConfig(
            provider="deepseek",
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            api_key_env="DEEPSEEK_API_KEY",
        ),
        transport=transport,
    )

    response = client.extract(PromptRequest(field_id="cash", candidates=()))

    assert response.fields[0].status == "missing"
    assert transport.calls[0][0] == "https://api.deepseek.com/v1/chat/completions"
    assert transport.calls[0][1]["Authorization"] == "Bearer deepseek-key"


def test_ollama_client_omits_authorization_when_key_missing(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    transport = FakeHttpTransport(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"fields": [{"field_id": "cash", "status": "missing"}]}
                            )
                        }
                    }
                ]
            }
        ]
    )
    client = create_llm_client(
        LlmTransportConfig(
            provider="ollama",
            model="qwen2.5:7b",
            base_url="http://localhost:11434/v1",
            api_key_env="OLLAMA_API_KEY",
        ),
        transport=transport,
    )

    response = client.extract(PromptRequest(field_id="cash", candidates=()))

    assert response.fields[0].status == "missing"
    assert transport.calls[0][0] == "http://localhost:11434/v1/chat/completions"
    assert "Authorization" not in transport.calls[0][1]


def test_gemini_client_builds_generate_content_request(monkeypatch: Any) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    transport = FakeHttpTransport(
        [
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "fields": [
                                                {
                                                    "field_id": "cash",
                                                    "status": "missing",
                                                }
                                            ]
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    )
    client = create_llm_client(
        LlmTransportConfig(
            provider="gemini",
            model="gemini-1.5-flash",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            api_key_env="GEMINI_API_KEY",
        ),
        transport=transport,
    )

    response = client.extract(PromptRequest(field_id="cash", candidates=()))

    assert response.fields[0].status == "missing"
    assert (
        transport.calls[0][0]
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    )
    assert transport.calls[0][1]["x-goog-api-key"] == "gemini-key"
    assert "gemini-key" not in json.dumps(transport.calls[0][2])
    assert transport.calls[0][2]["generationConfig"] == {
        "responseMimeType": "application/json"
    }


def test_openai_compatible_client_retries_timeout_errors(monkeypatch: Any) -> None:
    monkeypatch.setenv("TEST_LLM_KEY", "secret-key")
    transport = FakeHttpTransport(
        [
            TimeoutError("slow"),
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"fields": [{"field_id": "cash", "status": "missing"}]}
                            )
                        }
                    }
                ]
            },
        ]
    )
    client = OpenAiCompatibleClient(
        LlmTransportConfig(
            provider="openai-compatible",
            model="test-model",
            base_url="https://llm.example/v1",
            api_key_env="TEST_LLM_KEY",
            max_retries=1,
        ),
        transport=transport,
    )

    response = client.extract(PromptRequest(field_id="cash", candidates=()))

    assert response.fields[0].status == "missing"
    assert len(transport.calls) == 2


def test_run_real_transport_probe_writes_raw_response_artifact(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TEST_LLM_KEY", "secret-key")
    retrieval_probe_path = tmp_path / "retrieval_probe.json"
    output_path = tmp_path / "extraction_result.json"
    raw_dir = tmp_path / "raw"
    config_path = tmp_path / "llm_config.json"

    retrieval_probe_path.write_text(
        json.dumps(
            {
                "source_pdf_hash": "hash123",
                "fields": [
                    {
                        "field_id": "cash",
                        "candidates": [
                            {
                                "evidence": {
                                    "page": 8,
                                    "chunk_id": "stmt_balance_p0008_p0008",
                                    "block_id": "p0008_b0001",
                                    "snippet": "Cash 50",
                                }
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps(
            {
                "provider": "openai-compatible",
                "model": "test-model",
                "base_url": "https://llm.example/v1",
                "api_key_env": "TEST_LLM_KEY",
            }
        ),
        encoding="utf-8",
    )
    transport = FakeHttpTransport(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "fields": [
                                        {
                                            "field_id": "cash",
                                            "status": "present",
                                            "value_raw": "50",
                                            "unit_context": "HKD million",
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ],
                "usage": {"total_tokens": 42},
            }
        ]
    )

    result = run_real_transport_probe(
        retrieval_probe_path,
        config_path=config_path,
        output_path=output_path,
        raw_response_dir=raw_dir,
        transport=transport,
    )

    assert result.output_path == output_path
    assert result.raw_response_count == 1
    raw_files = list(raw_dir.glob("*.json"))
    assert len(raw_files) == 1
    raw_payload = json.loads(raw_files[0].read_text(encoding="utf-8"))
    assert raw_payload["provider"] == "openai-compatible"
    assert raw_payload["model"] == "test-model"
    assert raw_payload["raw_response"]["usage"]["total_tokens"] == 42

    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert output["items"][0]["status"] == "present"
    assert output["items"][0]["money"]["normalized_value"] == "50000000"


def test_run_real_transport_probe_archives_unparseable_raw_response(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TEST_LLM_KEY", "secret-key")
    retrieval_probe_path = tmp_path / "retrieval_probe.json"
    output_path = tmp_path / "extraction_result.json"
    raw_dir = tmp_path / "raw"
    config_path = tmp_path / "llm_config.json"

    retrieval_probe_path.write_text(
        json.dumps(
            {
                "source_pdf_hash": "hash123",
                "fields": [{"field_id": "cash", "candidates": []}],
            }
        ),
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps(
            {
                "provider": "openai-compatible",
                "model": "test-model",
                "base_url": "https://llm.example/v1",
                "api_key_env": "TEST_LLM_KEY",
            }
        ),
        encoding="utf-8",
    )
    transport = FakeHttpTransport(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": "{not valid json",
                        }
                    }
                ],
                "usage": {"total_tokens": 9},
            }
        ]
    )

    try:
        run_real_transport_probe(
            retrieval_probe_path,
            config_path=config_path,
            output_path=output_path,
            raw_response_dir=raw_dir,
            transport=transport,
        )
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("expected JSONDecodeError")

    raw_files = list(raw_dir.glob("*.json"))
    assert len(raw_files) == 1
    raw_payload = json.loads(raw_files[0].read_text(encoding="utf-8"))
    assert raw_payload["raw_response"]["usage"]["total_tokens"] == 9


def test_openai_compatible_client_raises_after_retries(monkeypatch: Any) -> None:
    monkeypatch.setenv("TEST_LLM_KEY", "secret-key")
    transport = FakeHttpTransport([URLError("offline"), URLError("offline")])
    client = OpenAiCompatibleClient(
        LlmTransportConfig(
            provider="openai-compatible",
            model="test-model",
            base_url="https://llm.example/v1",
            api_key_env="TEST_LLM_KEY",
            max_retries=1,
        ),
        transport=transport,
    )

    try:
        client.extract(PromptRequest(field_id="cash", candidates=()))
    except URLError:
        pass
    else:
        raise AssertionError("expected URLError after retries")

    assert len(transport.calls) == 2
