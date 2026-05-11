"""OpenAI-compatible LLM transport with raw response artifacts."""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast
from urllib.error import URLError

from financial_report_llm_extractor.extraction import (
    LlmExtractedField,
    LlmResponse,
    PromptRequest,
    run_fake_extraction,
)

ProviderKind = Literal["openai-compatible", "gemini"]


@dataclass(frozen=True)
class ProviderDefaults:
    base_url: str
    api_key_env: str
    kind: ProviderKind
    api_key_required: bool = True


PROVIDER_DEFAULTS: dict[str, ProviderDefaults] = {
    "openai-compatible": ProviderDefaults(
        base_url="",
        api_key_env="OPENAI_API_KEY",
        kind="openai-compatible",
    ),
    "deepseek": ProviderDefaults(
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        kind="openai-compatible",
    ),
    "ollama": ProviderDefaults(
        base_url="http://localhost:11434/v1",
        api_key_env="OLLAMA_API_KEY",
        kind="openai-compatible",
        api_key_required=False,
    ),
    "gemini": ProviderDefaults(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key_env="GEMINI_API_KEY",
        kind="gemini",
    ),
}


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
        provider = _normalize_provider(str(data["provider"]))
        defaults = PROVIDER_DEFAULTS.get(provider)
        return cls(
            provider=provider,
            model=data["model"],
            base_url=data.get("base_url")
            or (defaults.base_url if defaults is not None else ""),
            api_key_env=data.get("api_key_env")
            or (defaults.api_key_env if defaults is not None else "OPENAI_API_KEY"),
            timeout_seconds=float(data.get("timeout_seconds", 30)),
            max_retries=int(data.get("max_retries", 0)),
        )


def resolve_provider_kind(config: LlmTransportConfig) -> ProviderKind:
    provider = _normalize_provider(config.provider)
    defaults = PROVIDER_DEFAULTS.get(provider)
    if defaults is None:
        return "openai-compatible"
    return defaults.kind


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower().replace("_", "-")
    if normalized in {"openai-compatible", "openai"}:
        return "openai-compatible"
    if normalized in {"google-gemini", "google"}:
        return "gemini"
    return normalized


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


class LlmJsonClient(Protocol):
    raw_exchanges: list[RawExchange]

    def extract(self, request: PromptRequest) -> LlmResponse:
        pass

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, object],
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
        raw_response = self.complete_json(
            system_prompt=(
                "Return strict JSON with a fields array. Each field must "
                "include field_id, status, and optional value_raw/unit_context."
            ),
            user_payload={
                "field_id": request.field_id,
                "candidates": list(request.candidates),
            },
        )
        return _parse_openai_response(raw_response)

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        payload = self._build_payload(system_prompt, user_payload)
        raw_response = self._post_with_retries(payload)
        self.raw_exchanges.append(RawExchange(request=payload, raw_response=raw_response))
        return raw_response

    def _build_payload(
        self,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        return {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        user_payload,
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
                    _auth_headers(self.config),
                    payload,
                    self.config.timeout_seconds,
                )
            except (TimeoutError, URLError) as error:
                last_error = error
        if last_error is not None:
            raise last_error
        raise RuntimeError("LLM transport failed without an error")


def create_llm_client(
    config: LlmTransportConfig,
    *,
    transport: HttpTransport | None = None,
) -> LlmJsonClient:
    kind = resolve_provider_kind(config)
    if kind == "openai-compatible":
        return OpenAiCompatibleClient(config, transport=transport)
    if kind == "gemini":
        return GeminiGenerateContentClient(config, transport=transport)
    raise ValueError(f"unsupported provider kind: {kind}")


class GeminiGenerateContentClient:
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
        raw_response = self.complete_json(
            system_prompt=(
                "Return strict JSON with a fields array. Each field must "
                "include field_id, status, and optional value_raw/unit_context."
            ),
            user_payload={
                "field_id": request.field_id,
                "candidates": list(request.candidates),
            },
        )
        return _parse_response_json_content(raw_response)

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "systemInstruction": {
                "parts": [{"text": system_prompt}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(
                                user_payload,
                                ensure_ascii=False,
                                sort_keys=True,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        raw_response = self._post_with_retries(payload)
        self.raw_exchanges.append(RawExchange(request=payload, raw_response=raw_response))
        return raw_response

    def _post_with_retries(self, payload: dict[str, object]) -> dict[str, object]:
        attempts = self.config.max_retries + 1
        last_error: TimeoutError | URLError | None = None
        for _ in range(attempts):
            try:
                return self.transport.post_json(
                    f"{self.config.base_url.rstrip('/')}/models/{self.config.model}:generateContent",
                    {
                        "Content-Type": "application/json",
                        "x-goog-api-key": _read_api_key(self.config.api_key_env),
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
    client = create_llm_client(config, transport=transport)
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
    if not value and env_name == "GEMINI_API_KEY":
        value = os.environ.get("GOOGLE_API_KEY")
    if not value:
        raise ValueError(f"missing API key environment variable: {env_name}")
    return value


def _auth_headers(config: LlmTransportConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    provider = _normalize_provider(config.provider)
    defaults = PROVIDER_DEFAULTS.get(provider)
    api_key_required = True if defaults is None else defaults.api_key_required
    api_key = os.environ.get(config.api_key_env)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif api_key_required:
        raise ValueError(f"missing API key environment variable: {config.api_key_env}")
    return headers


def _parse_openai_response(raw_response: dict[str, object]) -> LlmResponse:
    return _parse_response_json_content(raw_response)


def _parse_response_json_content(raw_response: dict[str, object]) -> LlmResponse:
    content = _response_json_text(raw_response)
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


def _response_json_text(raw_response: dict[str, object]) -> str:
    choices = raw_response.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ValueError("LLM response choice must be an object")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise ValueError("LLM response missing message")
        content = message.get("content")
        if not isinstance(content, str):
            raise ValueError("LLM response message content must be a string")
        return content

    candidates = raw_response.get("candidates")
    if isinstance(candidates, list) and candidates:
        first_candidate = candidates[0]
        if not isinstance(first_candidate, dict):
            raise ValueError("Gemini response candidate must be an object")
        content_obj = first_candidate.get("content")
        if not isinstance(content_obj, dict):
            raise ValueError("Gemini response missing content")
        parts = content_obj.get("parts")
        if not isinstance(parts, list) or not parts:
            raise ValueError("Gemini response missing parts")
        first_part = parts[0]
        if not isinstance(first_part, dict):
            raise ValueError("Gemini response part must be an object")
        text = first_part.get("text")
        if not isinstance(text, str):
            raise ValueError("Gemini response part text must be a string")
        return text

    if choices is not None:
        raise ValueError("LLM response missing choices")
    raise ValueError("LLM response missing candidates")


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


def _extract_openai_json_content(raw_response: dict[str, object]) -> dict[str, object]:
    """Extract JSON content from OpenAI-compatible chat.completion response.

    OpenAI returns the LLM's JSON output as a string in choices[0].message.content
    when response_format=json_object. We parse and return that JSON dict so callers
    don't need to handle transport-level structure.
    """
    choices = raw_response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError(
            f"openai response missing 'choices' array: {raw_response!r}"
        )
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError(f"openai response choice is not an object: {first!r}")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError(f"openai response message is not an object: {message!r}")
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError(f"openai response message.content is not a string: {content!r}")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"openai response message.content is not valid JSON: {content!r}"
        ) from exc
    if not isinstance(parsed, dict):
        raise ValueError(
            f"openai response content parses to non-object: {parsed!r}"
        )
    return cast(dict[str, object], parsed)


def _extract_gemini_json_content(raw_response: dict[str, object]) -> dict[str, object]:
    """Extract JSON content from Gemini generateContent response.

    Gemini returns the LLM's JSON output as a string in
    candidates[0].content.parts[0].text when responseMimeType=application/json.
    """
    candidates = raw_response.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError(
            f"gemini response missing 'candidates' array: {raw_response!r}"
        )
    first = candidates[0]
    if not isinstance(first, dict):
        raise ValueError(f"gemini response candidate is not an object: {first!r}")
    content = first.get("content")
    if not isinstance(content, dict):
        raise ValueError(f"gemini response candidate.content is not an object: {content!r}")
    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError(f"gemini response content.parts is empty or invalid: {parts!r}")
    text_part = parts[0]
    if not isinstance(text_part, dict):
        raise ValueError(f"gemini response part is not an object: {text_part!r}")
    text = text_part.get("text")
    if not isinstance(text, str):
        raise ValueError(f"gemini response part.text is not a string: {text!r}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"gemini response part.text is not valid JSON: {text!r}"
        ) from exc
    if not isinstance(parsed, dict):
        raise ValueError(
            f"gemini response text parses to non-object: {parsed!r}"
        )
    return cast(dict[str, object], parsed)
