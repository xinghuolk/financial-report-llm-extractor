"""Read-only subscription credential helpers for Codex and Claude Code."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DEFAULT_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
DEFAULT_CLAUDE_CODE_BASE_URL = "https://api.anthropic.com"

SubscriptionProvider = Literal["openai-codex", "claude-code"]
TokenStatus = Literal["valid", "missing", "expired", "invalid"]

ERROR_CREDENTIALS_MISSING = "subscription_credentials_missing"
ERROR_CREDENTIALS_INVALID = "subscription_credentials_invalid"
ERROR_TOKEN_EXPIRED = "subscription_token_expired"
ERROR_REQUEST_FAILED = "subscription_request_failed"
ERROR_PROVIDER_UNSUPPORTED = "subscription_provider_unsupported"


@dataclass(frozen=True)
class SubscriptionCredentialStatus:
    provider: str
    available: bool
    credential_source: str | None
    token_status: TokenStatus
    error_code: str | None = None
    message: str | None = None
    base_url: str | None = None


@dataclass(frozen=True)
class SubscriptionRuntimeCredentials:
    provider: SubscriptionProvider
    access_token: str
    credential_source: str
    base_url: str


class SubscriptionAuthError(RuntimeError):
    def __init__(self, *, code: str, message: str, provider: str) -> None:
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def subscription_auth_status(
    provider: str,
    *,
    home: Path | None = None,
    env: dict[str, str] | None = None,
) -> SubscriptionCredentialStatus:
    del home, env
    if provider not in {"openai-codex", "claude-code"}:
        return SubscriptionCredentialStatus(
            provider=provider,
            available=False,
            credential_source=None,
            token_status="invalid",
            error_code=ERROR_PROVIDER_UNSUPPORTED,
            message=f"unsupported subscription provider: {provider}",
            base_url=None,
        )
    raise NotImplementedError(provider)
