import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest

from financial_report_llm_extractor.extraction import PromptRequest
from financial_report_llm_extractor.llm_transport import (
    LlmTransportConfig,
    OpenAiCompatibleClient,
    UrllibHttpTransport,
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


def _jwt_with_exp(exp: int, account_id: str = "acct-test") -> str:
    import base64

    def enc(payload: dict[str, object]) -> str:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return (
        f"{enc({'alg': 'none'})}."
        f"{enc({'exp': exp, 'https://api.openai.com/auth': {'chatgpt_account_id': account_id}})}."
        "sig"
    )


def _write_codex_auth(tmp_path: Path, monkeypatch: Any, token: str) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        json.dumps({"tokens": {"access_token": token, "refresh_token": "refresh"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))


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
    raw: dict[str, object] = {
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
    raw: dict[str, object] = {
        "content": [{"type": "text", "text": json.dumps({"fields": []})}]
    }

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


def test_codex_client_builds_responses_request(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    token = _jwt_with_exp(
        int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        account_id="acct-123",
    )
    _write_codex_auth(tmp_path, monkeypatch, token)
    transport = FakeHttpTransport(
        [
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "fields": [
                                            {"field_id": "cash", "status": "missing"}
                                        ]
                                    }
                                ),
                            }
                        ],
                    }
                ]
            }
        ]
    )

    client = create_llm_client(
        LlmTransportConfig(
            provider="openai-codex",
            model="gpt-5.3-codex",
            base_url="https://chatgpt.com/backend-api/codex",
            api_key_env="",
        ),
        transport=transport,
    )
    response = client.extract(PromptRequest(field_id="cash", candidates=()))

    assert response.fields[0].status == "missing"
    url, headers, payload, _timeout = transport.calls[0]
    assert url == "https://chatgpt.com/backend-api/codex/responses"
    assert headers["Authorization"] == f"Bearer {token}"
    assert headers["originator"] == "codex_cli_rs"
    assert headers["ChatGPT-Account-ID"] == "acct-123"
    assert payload["model"] == "gpt-5.3-codex"
    assert payload["instructions"]
    assert "json" in str(payload["instructions"])
    assert payload["stream"] is True
    assert payload["store"] is False
    input_items = payload["input"]
    assert isinstance(input_items, list)
    first_item = input_items[0]
    assert isinstance(first_item, dict)
    content = first_item["content"]
    assert isinstance(content, list)
    first_part = content[0]
    assert isinstance(first_part, dict)
    assert json.loads(first_part["text"])["field_id"] == "cash"


def test_codex_client_adds_json_instruction_when_prompt_omits_keyword(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    token = _jwt_with_exp(
        int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    )
    _write_codex_auth(tmp_path, monkeypatch, token)
    transport = FakeHttpTransport(
        [
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": json.dumps({"ok": True})}
                        ],
                    }
                ]
            }
        ]
    )
    client = create_llm_client(
        LlmTransportConfig(
            provider="openai-codex",
            model="gpt-5.3-codex",
            base_url="https://chatgpt.com/backend-api/codex",
            api_key_env="",
        ),
        transport=transport,
    )

    client.complete_json(system_prompt="Return an object.", user_payload={"ok": True})

    instructions = str(transport.calls[0][2]["instructions"])
    assert "json" in instructions


def test_urllib_transport_parses_responses_sse_completed_event(
    monkeypatch: Any,
) -> None:
    class FakeHeaders:
        def get(self, name: str, default: str = "") -> str:
            if name.lower() == "content-type":
                return "text/event-stream"
            return default

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            completed = {
                "type": "response.completed",
                "response": {
                    "id": "resp_1",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps({"fields": []}),
                                }
                            ],
                        }
                    ],
                },
            }
            return (
                "event: response.completed\n"
                f"data: {json.dumps(completed)}\n\n"
                "data: [DONE]\n\n"
            ).encode("utf-8")

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        assert timeout == 12
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    raw = UrllibHttpTransport().post_json(
        "https://chatgpt.com/backend-api/codex/responses",
        {"Content-Type": "application/json"},
        {"stream": True},
        12,
    )

    assert raw["id"] == "resp_1"
    assert response_json_text(raw) == json.dumps({"fields": []})


def test_claude_code_client_builds_messages_request(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("ANTHROPIC_TOKEN", "sk-ant-oat01-claude-token")
    monkeypatch.setattr(
        "financial_report_llm_extractor.llm_transport._detect_claude_code_version",
        lambda: "2.1.74",
    )
    transport = FakeHttpTransport(
        [
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"fields": [{"field_id": "cash", "status": "missing"}]}
                        ),
                    }
                ]
            }
        ]
    )

    client = create_llm_client(
        LlmTransportConfig(
            provider="claude-code",
            model="claude-sonnet-4-6",
            base_url="https://api.anthropic.com",
            api_key_env="",
        ),
        transport=transport,
    )
    response = client.extract(PromptRequest(field_id="cash", candidates=()))

    assert response.fields[0].status == "missing"
    url, headers, payload, _timeout = transport.calls[0]
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["Authorization"] == "Bearer sk-ant-oat01-claude-token"
    assert headers["anthropic-version"]
    assert headers["user-agent"] == "claude-cli/2.1.74 (external, cli)"
    assert payload["model"] == "claude-sonnet-4-6"
    assert payload["max_tokens"] == 4096
    messages = payload["messages"]
    assert isinstance(messages, list)
    first_message = messages[0]
    assert isinstance(first_message, dict)
    assert json.loads(first_message["content"])["field_id"] == "cash"


def test_claude_code_user_agent_detects_installed_version(
    monkeypatch: Any,
) -> None:
    import subprocess

    class FakeCompleted:
        returncode = 0
        stdout = "2.2.3 (Claude Code)\n"

    def fake_run(
        args: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
    ) -> FakeCompleted:
        assert args == ["claude", "--version"]
        assert capture_output is True
        assert text is True
        assert timeout == 5
        return FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)

    from financial_report_llm_extractor.llm_transport import _claude_code_headers

    headers = _claude_code_headers("sk-ant-oat01-token")

    assert headers["user-agent"] == "claude-cli/2.2.3 (external, cli)"


def test_subscription_client_missing_credentials_fails_before_transport(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    transport = FakeHttpTransport([])
    client = create_llm_client(
        LlmTransportConfig(
            provider="openai-codex",
            model="gpt-5.3-codex",
            base_url="https://chatgpt.com/backend-api/codex",
            api_key_env="",
        ),
        transport=transport,
    )

    with pytest.raises(Exception) as exc_info:
        client.extract(PromptRequest(field_id="cash", candidates=()))

    assert "subscription_credentials_missing" in str(exc_info.value)
    assert transport.calls == []


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


def test_subscription_raw_response_artifact_does_not_include_token(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    token = _jwt_with_exp(
        int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    )
    _write_codex_auth(tmp_path, monkeypatch, token)
    retrieval_probe_path = tmp_path / "retrieval_probe.json"
    config_path = tmp_path / "llm_config.json"
    output_path = tmp_path / "extraction_result.json"
    raw_dir = tmp_path / "raw"
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
        json.dumps({"provider": "openai-codex", "model": "gpt-5.3-codex"}),
        encoding="utf-8",
    )
    transport = FakeHttpTransport(
        [
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "fields": [
                                            {"field_id": "cash", "status": "missing"}
                                        ]
                                    }
                                ),
                            }
                        ],
                    }
                ]
            }
        ]
    )

    run_real_transport_probe(
        retrieval_probe_path,
        config_path=config_path,
        output_path=output_path,
        raw_response_dir=raw_dir,
        transport=transport,
    )

    raw_text = next(raw_dir.glob("*.json")).read_text(encoding="utf-8")
    assert token not in raw_text
    assert "Authorization" not in raw_text


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
