"""OpenAI-compatible LLM transport with raw response artifacts."""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from urllib.error import URLError

from financial_report_llm_extractor.extraction import (
    LlmExtractedField,
    LlmResponse,
    PromptRequest,
    run_fake_extraction,
)


@dataclass(frozen=True)
class LlmTransportConfig:
    provider: str
    model: str
    base_url: str
    api_key_env: str
    timeout_seconds: float = 30
    max_retries: int = 0

    @classmethod
    def from_json(cls, path: Path) -> LlmTransportConfig:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            provider=data["provider"],
            model=data["model"],
            base_url=data["base_url"],
            api_key_env=data["api_key_env"],
            timeout_seconds=float(data.get("timeout_seconds", 30)),
            max_retries=int(data.get("max_retries", 0)),
        )


@dataclass(frozen=True)
class RealTransportResult:
    output_path: Path
    item_count: int
    raw_response_count: int


class HttpTransport(Protocol):
    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        pass


@dataclass(frozen=True)
class UrllibHttpTransport:
    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
            return cast(dict[str, object], data)


@dataclass(frozen=True)
class RawExchange:
    request: dict[str, object]
    raw_response: dict[str, object]


class OpenAiCompatibleClient:
    def __init__(
        self,
        config: LlmTransportConfig,
        *,
        transport: HttpTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or UrllibHttpTransport()
        self.raw_exchanges: list[RawExchange] = []

    def extract(self, request: PromptRequest) -> LlmResponse:
        payload = self._build_payload(request)
        raw_response = self._post_with_retries(payload)
        self.raw_exchanges.append(RawExchange(request=payload, raw_response=raw_response))
        return _parse_openai_response(raw_response)

    def _build_payload(self, request: PromptRequest) -> dict[str, object]:
        return {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return strict JSON with a fields array. Each field must "
                        "include field_id, status, and optional value_raw/unit_context."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "field_id": request.field_id,
                            "candidates": list(request.candidates),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

    def _post_with_retries(self, payload: dict[str, object]) -> dict[str, object]:
        attempts = self.config.max_retries + 1
        last_error: TimeoutError | URLError | None = None
        for _ in range(attempts):
            try:
                return self.transport.post_json(
                    f"{self.config.base_url.rstrip('/')}/chat/completions",
                    {
                        "Authorization": f"Bearer {_read_api_key(self.config.api_key_env)}",
                        "Content-Type": "application/json",
                    },
                    payload,
                    self.config.timeout_seconds,
                )
            except (TimeoutError, URLError) as error:
                last_error = error
        if last_error is not None:
            raise last_error
        raise RuntimeError("LLM transport failed without an error")


def run_real_transport_probe(
    retrieval_probe_path: Path,
    *,
    config_path: Path,
    output_path: Path | None = None,
    raw_response_dir: Path | None = None,
    transport: HttpTransport | None = None,
) -> RealTransportResult:
    config = LlmTransportConfig.from_json(config_path)
    client = OpenAiCompatibleClient(config, transport=transport)
    raw_dir = raw_response_dir or retrieval_probe_path.parent / "raw_llm_responses"
    try:
        extraction_result = run_fake_extraction(
            retrieval_probe_path,
            output_path=output_path,
            llm_client=client,
        )
    except Exception:
        _write_raw_exchanges(raw_dir, config, client.raw_exchanges)
        raise
    _write_raw_exchanges(raw_dir, config, client.raw_exchanges)
    return RealTransportResult(
        output_path=extraction_result.output_path,
        item_count=extraction_result.item_count,
        raw_response_count=len(client.raw_exchanges),
    )


def _read_api_key(env_name: str) -> str:
    value = os.environ.get(env_name)
    if not value:
        raise ValueError(f"missing API key environment variable: {env_name}")
    return value


def _parse_openai_response(raw_response: dict[str, object]) -> LlmResponse:
    choices = raw_response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("LLM response missing choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("LLM response choice must be an object")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("LLM response missing message")
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("LLM response message content must be a string")
    parsed = json.loads(content)
    fields = parsed.get("fields")
    if not isinstance(fields, list):
        raise ValueError("LLM JSON content missing fields")
    return LlmResponse(
        fields=tuple(
            LlmExtractedField(
                field_id=str(field["field_id"]),
                status=field["status"],
                value_raw=field.get("value_raw"),
                unit_context=field.get("unit_context"),
                confidence=field.get("confidence"),
            )
            for field in fields
            if isinstance(field, dict)
        )
    )


def _write_raw_exchanges(
    raw_dir: Path,
    config: LlmTransportConfig,
    exchanges: list[RawExchange],
) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for index, exchange in enumerate(exchanges, start=1):
        path = raw_dir / f"raw_response_{index:04d}.json"
        path.write_text(
            json.dumps(
                {
                    "provider": config.provider,
                    "model": config.model,
                    "base_url": config.base_url,
                    "request": exchange.request,
                    "raw_response": exchange.raw_response,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
