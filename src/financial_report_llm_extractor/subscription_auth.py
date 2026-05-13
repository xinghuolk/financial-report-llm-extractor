"""Read-only subscription credential helpers for Codex and Claude Code."""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

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
    if provider == "openai-codex":
        status, _ = _read_codex_credentials(home=home, env=env)
        return status
    if provider == "claude-code":
        status, _ = _read_claude_credentials(home=home, env=env)
        return status
    return SubscriptionCredentialStatus(
        provider=provider,
        available=False,
        credential_source=None,
        token_status="invalid",
        error_code=ERROR_PROVIDER_UNSUPPORTED,
        message=f"unsupported subscription provider: {provider}",
        base_url=None,
    )


def resolve_subscription_credentials(
    provider: str,
    *,
    home: Path | None = None,
    env: dict[str, str] | None = None,
) -> SubscriptionRuntimeCredentials:
    status = subscription_auth_status(provider, home=home, env=env)
    if not status.available:
        raise SubscriptionAuthError(
            code=status.error_code or ERROR_CREDENTIALS_INVALID,
            message=status.message
            or f"{provider} subscription credentials are unavailable",
            provider=provider,
        )
    if provider == "openai-codex":
        _status, credentials = _read_codex_credentials(home=home, env=env)
        if credentials is not None:
            return credentials
    if provider == "claude-code":
        _status, credentials = _read_claude_credentials(home=home, env=env)
        if credentials is not None:
            return credentials
    raise SubscriptionAuthError(
        code=ERROR_PROVIDER_UNSUPPORTED,
        message=f"unsupported subscription provider: {provider}",
        provider=provider,
    )


def _runtime_env(env: dict[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def _runtime_home(home: Path | None, env: dict[str, str] | None) -> Path:
    if home is not None:
        return home
    env_map = _runtime_env(env)
    return Path(env_map.get("HOME") or str(Path.home()))


def _codex_auth_path(*, home: Path | None, env: dict[str, str] | None) -> Path:
    env_map = _runtime_env(env)
    codex_home = env_map.get("CODEX_HOME", "").strip()
    if codex_home:
        return Path(codex_home).expanduser() / "auth.json"
    return _runtime_home(home, env) / ".codex" / "auth.json"


def _jwt_payload(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    segment = parts[1]
    padded = segment + "=" * (-len(segment) % 4)
    try:
        payload = base64.urlsafe_b64decode(padded.encode("ascii"))
        data = json.loads(payload.decode("utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def token_is_expired(token: str, *, skew_seconds: int = 0) -> bool:
    payload = _jwt_payload(token)
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return False
    return time.time() >= float(exp) - skew_seconds


def codex_chatgpt_account_id(token: str) -> str | None:
    payload = _jwt_payload(token)
    auth = payload.get("https://api.openai.com/auth")
    if isinstance(auth, dict):
        account_id = auth.get("chatgpt_account_id")
        if isinstance(account_id, str) and account_id.strip():
            return account_id.strip()
    return None


def _read_codex_credentials(
    *,
    home: Path | None,
    env: dict[str, str] | None,
) -> tuple[SubscriptionCredentialStatus, SubscriptionRuntimeCredentials | None]:
    path = _codex_auth_path(home=home, env=env)
    if not path.is_file():
        return (
            SubscriptionCredentialStatus(
                provider="openai-codex",
                available=False,
                credential_source=str(path),
                token_status="missing",
                error_code=ERROR_CREDENTIALS_MISSING,
                message=(
                    "Codex credentials not found; run the official "
                    "Codex CLI login first"
                ),
                base_url=DEFAULT_CODEX_BASE_URL,
            ),
            None,
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return (
            SubscriptionCredentialStatus(
                provider="openai-codex",
                available=False,
                credential_source=str(path),
                token_status="invalid",
                error_code=ERROR_CREDENTIALS_INVALID,
                message="Codex auth file is not valid JSON",
                base_url=DEFAULT_CODEX_BASE_URL,
            ),
            None,
        )
    tokens = payload.get("tokens")
    access_token = tokens.get("access_token") if isinstance(tokens, dict) else None
    if not isinstance(access_token, str) or not access_token.strip():
        return (
            SubscriptionCredentialStatus(
                provider="openai-codex",
                available=False,
                credential_source=str(path),
                token_status="invalid",
                error_code=ERROR_CREDENTIALS_INVALID,
                message="Codex auth file is missing tokens.access_token",
                base_url=DEFAULT_CODEX_BASE_URL,
            ),
            None,
        )
    if token_is_expired(access_token):
        return (
            SubscriptionCredentialStatus(
                provider="openai-codex",
                available=False,
                credential_source=str(path),
                token_status="expired",
                error_code=ERROR_TOKEN_EXPIRED,
                message=(
                    "Codex access token is expired; run the official "
                    "Codex CLI login again"
                ),
                base_url=DEFAULT_CODEX_BASE_URL,
            ),
            None,
        )
    status = SubscriptionCredentialStatus(
        provider="openai-codex",
        available=True,
        credential_source=str(path),
        token_status="valid",
        base_url=DEFAULT_CODEX_BASE_URL,
    )
    credentials = SubscriptionRuntimeCredentials(
        provider="openai-codex",
        access_token=access_token.strip(),
        credential_source=str(path),
        base_url=DEFAULT_CODEX_BASE_URL,
    )
    return status, credentials


def _read_claude_credentials(
    *,
    home: Path | None,
    env: dict[str, str] | None,
) -> tuple[SubscriptionCredentialStatus, SubscriptionRuntimeCredentials | None]:
    env_map = _runtime_env(env)
    for env_name in ("ANTHROPIC_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
        token = env_map.get(env_name, "").strip()
        if token:
            status = SubscriptionCredentialStatus(
                provider="claude-code",
                available=True,
                credential_source=env_name,
                token_status="valid",
                base_url=DEFAULT_CLAUDE_CODE_BASE_URL,
            )
            credentials = SubscriptionRuntimeCredentials(
                provider="claude-code",
                access_token=token,
                credential_source=env_name,
                base_url=DEFAULT_CLAUDE_CODE_BASE_URL,
            )
            return status, credentials

    path = _claude_credentials_path(home=home, env=env)
    if not path.is_file():
        return (
            SubscriptionCredentialStatus(
                provider="claude-code",
                available=False,
                credential_source=str(path),
                token_status="missing",
                error_code=ERROR_CREDENTIALS_MISSING,
                message=(
                    "Claude Code credentials not found; run the official "
                    "Claude Code login first"
                ),
                base_url=DEFAULT_CLAUDE_CODE_BASE_URL,
            ),
            None,
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return (
            SubscriptionCredentialStatus(
                provider="claude-code",
                available=False,
                credential_source=str(path),
                token_status="invalid",
                error_code=ERROR_CREDENTIALS_INVALID,
                message="Claude Code credentials file is not valid JSON",
                base_url=DEFAULT_CLAUDE_CODE_BASE_URL,
            ),
            None,
        )
    oauth = payload.get("claudeAiOauth")
    access_token = oauth.get("accessToken") if isinstance(oauth, dict) else None
    expires_at = oauth.get("expiresAt") if isinstance(oauth, dict) else None
    if not isinstance(access_token, str) or not access_token.strip():
        return (
            SubscriptionCredentialStatus(
                provider="claude-code",
                available=False,
                credential_source=str(path),
                token_status="invalid",
                error_code=ERROR_CREDENTIALS_INVALID,
                message=(
                    "Claude Code credentials file is missing "
                    "claudeAiOauth.accessToken"
                ),
                base_url=DEFAULT_CLAUDE_CODE_BASE_URL,
            ),
            None,
        )
    if _claude_file_token_is_expired(expires_at):
        return (
            SubscriptionCredentialStatus(
                provider="claude-code",
                available=False,
                credential_source=str(path),
                token_status="expired",
                error_code=ERROR_TOKEN_EXPIRED,
                message=(
                    "Claude Code access token is expired; run the official "
                    "Claude Code login again"
                ),
                base_url=DEFAULT_CLAUDE_CODE_BASE_URL,
            ),
            None,
        )
    status = SubscriptionCredentialStatus(
        provider="claude-code",
        available=True,
        credential_source=str(path),
        token_status="valid",
        base_url=DEFAULT_CLAUDE_CODE_BASE_URL,
    )
    credentials = SubscriptionRuntimeCredentials(
        provider="claude-code",
        access_token=access_token.strip(),
        credential_source=str(path),
        base_url=DEFAULT_CLAUDE_CODE_BASE_URL,
    )
    return status, credentials


def _claude_credentials_path(*, home: Path | None, env: dict[str, str] | None) -> Path:
    return _runtime_home(home, env) / ".claude" / ".credentials.json"


def _claude_file_token_is_expired(expires_at: object) -> bool:
    if not isinstance(expires_at, (int, float)):
        return False
    if expires_at <= 0:
        return False
    return int(time.time() * 1000) >= int(expires_at) - 60_000
