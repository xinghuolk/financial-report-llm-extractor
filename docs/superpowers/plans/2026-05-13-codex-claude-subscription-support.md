# Codex and Claude Subscription Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-only OpenAI Codex and Claude Code subscription credentials as opt-in LLM providers, with redacted diagnostics and a smoke command.

**Architecture:** Implement a small `subscription_auth.py` module that reads existing CLI credentials without login, refresh, or writes. Extend `llm_transport.py` with two single-turn JSON clients that still satisfy the current `LlmJsonClient.complete_json()` protocol, and add CLI diagnostics that stay below the financial extraction layer.

**Tech Stack:** Python 3.11 standard library, frozen dataclasses, `urllib.request`, `argparse`, `pytest`, existing injected `HttpTransport` tests.

---

## File Structure

- Create `src/financial_report_llm_extractor/subscription_auth.py`
  - Credential status dataclasses.
  - Stable `SubscriptionAuthError`.
  - Codex and Claude credential readers.
  - Token expiry helpers.
  - Redacted status snapshots.

- Modify `src/financial_report_llm_extractor/llm_transport.py`
  - Add provider kinds `codex-responses` and `anthropic-messages`.
  - Add defaults for `openai-codex` and `claude-code`.
  - Add `CodexResponsesClient` and `ClaudeCodeMessagesClient`.
  - Add response text normalization for Codex Responses and Anthropic Messages.
  - Ensure raw exchange archival omits headers and token material.

- Modify `src/financial_report_llm_extractor/llm_field_extraction.py`
  - Reuse the shared response text normalizer, or extend its local unwrap logic for the two new raw response shapes if the shared import would create a cycle.

- Modify `src/financial_report_llm_extractor/llm_row_discovery.py`
  - Reuse the shared response text normalizer, or extend local parsing consistently with field extraction.

- Modify `src/financial_report_llm_extractor/cli.py`
  - Add `llm-auth-status`.
  - Add `llm-subscription-smoke`.
  - Print JSON diagnostics and artifact paths.

- Create `tests/test_subscription_auth.py`
  - Covers credential source parsing, missing/invalid/expired states, and redaction.

- Modify `tests/test_llm_transport.py`
  - Covers provider defaults, request payloads, headers, missing credentials, expired credentials, and new response parsing.

- Modify `tests/test_llm_field_extraction.py`
  - Adds raw-response unwrap coverage for Codex and Claude shapes.

- Modify `tests/test_llm_row_discovery.py`
  - Adds row parser coverage for Codex and Claude shapes.

- Modify `tests/test_cli.py`
  - Adds CLI status and smoke command coverage with monkeypatches and fake transport.

---

### Task 1: Subscription Auth Contracts and Error Model

**Files:**
- Create: `src/financial_report_llm_extractor/subscription_auth.py`
- Create: `tests/test_subscription_auth.py`

- [ ] **Step 1: Write failing contract tests**

Add this to `tests/test_subscription_auth.py`:

```python
import json
from pathlib import Path

import pytest

from financial_report_llm_extractor.subscription_auth import (
    DEFAULT_CLAUDE_CODE_BASE_URL,
    DEFAULT_CODEX_BASE_URL,
    SubscriptionAuthError,
    SubscriptionCredentialStatus,
    subscription_auth_status,
)


def test_status_for_unknown_provider_is_invalid() -> None:
    status = subscription_auth_status("unknown-provider")

    assert status == SubscriptionCredentialStatus(
        provider="unknown-provider",
        available=False,
        credential_source=None,
        token_status="invalid",
        error_code="subscription_provider_unsupported",
        message="unsupported subscription provider: unknown-provider",
        base_url=None,
    )


def test_error_str_includes_stable_code() -> None:
    error = SubscriptionAuthError(
        code="subscription_credentials_missing",
        message="No credentials found",
        provider="openai-codex",
    )

    assert str(error) == "subscription_credentials_missing: No credentials found"
    assert error.provider == "openai-codex"
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
uv run pytest tests/test_subscription_auth.py::test_status_for_unknown_provider_is_invalid tests/test_subscription_auth.py::test_error_str_includes_stable_code -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'financial_report_llm_extractor.subscription_auth'`.

- [ ] **Step 3: Implement the minimal contract module**

Create `src/financial_report_llm_extractor/subscription_auth.py`:

```python
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
```

- [ ] **Step 4: Run the contract tests and verify they pass**

Run:

```bash
uv run pytest tests/test_subscription_auth.py::test_status_for_unknown_provider_is_invalid tests/test_subscription_auth.py::test_error_str_includes_stable_code -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add src/financial_report_llm_extractor/subscription_auth.py tests/test_subscription_auth.py
git commit -m "feat: add subscription auth contracts"
```

---

### Task 2: Codex Credential Reader

**Files:**
- Modify: `src/financial_report_llm_extractor/subscription_auth.py`
- Modify: `tests/test_subscription_auth.py`

- [ ] **Step 1: Write failing Codex credential tests**

Append to `tests/test_subscription_auth.py`:

```python
from datetime import datetime, timedelta, timezone

from financial_report_llm_extractor.subscription_auth import (
    resolve_subscription_credentials,
)


def _jwt_with_exp(exp: int, account_id: str = "acct-test") -> str:
    import base64

    def enc(payload: dict[str, object]) -> str:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{enc({'alg': 'none'})}.{enc({'exp': exp, 'https://api.openai.com/auth': {'chatgpt_account_id': account_id}})}.sig"


def test_codex_status_reads_codex_home_auth_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    token = _jwt_with_exp(int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()))
    (codex_home / "auth.json").write_text(
        json.dumps({"tokens": {"access_token": token, "refresh_token": "refresh"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    status = subscription_auth_status("openai-codex")
    creds = resolve_subscription_credentials("openai-codex")

    assert status.available is True
    assert status.token_status == "valid"
    assert status.credential_source == str(codex_home / "auth.json")
    assert status.base_url == DEFAULT_CODEX_BASE_URL
    assert creds.access_token == token
    assert creds.credential_source == str(codex_home / "auth.json")


def test_codex_status_reports_missing_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    status = subscription_auth_status("openai-codex")

    assert status.available is False
    assert status.token_status == "missing"
    assert status.error_code == "subscription_credentials_missing"
    assert status.credential_source == str(tmp_path / ".codex" / "auth.json")


def test_codex_resolve_raises_for_expired_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    token = _jwt_with_exp(int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()))
    (codex_home / "auth.json").write_text(
        json.dumps({"tokens": {"access_token": token, "refresh_token": "refresh"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    status = subscription_auth_status("openai-codex")
    with pytest.raises(SubscriptionAuthError) as exc_info:
        resolve_subscription_credentials("openai-codex")

    assert status.available is False
    assert status.token_status == "expired"
    assert status.error_code == "subscription_token_expired"
    assert exc_info.value.code == "subscription_token_expired"


def test_codex_status_reports_invalid_shape(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(json.dumps({"tokens": {}}), encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    status = subscription_auth_status("openai-codex")

    assert status.available is False
    assert status.token_status == "invalid"
    assert status.error_code == "subscription_credentials_invalid"
```

- [ ] **Step 2: Run Codex tests and verify they fail**

Run:

```bash
uv run pytest tests/test_subscription_auth.py -v
```

Expected: FAIL because `resolve_subscription_credentials()` and Codex parsing are not implemented.

- [ ] **Step 3: Implement Codex credential parsing**

Add these imports near the top of `subscription_auth.py`:

```python
import base64
import json
import os
import time
```

Add these helpers and functions:

```python
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
            message=status.message or f"{provider} subscription credentials are unavailable",
            provider=provider,
        )
    if provider == "openai-codex":
        return _read_codex_credentials(home=home, env=env)[1]
    if provider == "claude-code":
        return _read_claude_credentials(home=home, env=env)[1]
    raise SubscriptionAuthError(
        code=ERROR_PROVIDER_UNSUPPORTED,
        message=f"unsupported subscription provider: {provider}",
        provider=provider,
    )


def _runtime_env(env: dict[str, str] | None) -> dict[str, str]:
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
                message="Codex credentials not found; run the official Codex CLI login first",
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
                message="Codex access token is expired; run the official Codex CLI login again",
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
    creds = SubscriptionRuntimeCredentials(
        provider="openai-codex",
        access_token=access_token.strip(),
        credential_source=str(path),
        base_url=DEFAULT_CODEX_BASE_URL,
    )
    return status, creds
```

Update `subscription_auth_status()`:

```python
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
```

Add a temporary Claude stub at the end so imports pass until Task 3:

```python
def _read_claude_credentials(
    *,
    home: Path | None,
    env: dict[str, str] | None,
) -> tuple[SubscriptionCredentialStatus, SubscriptionRuntimeCredentials | None]:
    del home, env
    return (
        SubscriptionCredentialStatus(
            provider="claude-code",
            available=False,
            credential_source=None,
            token_status="missing",
            error_code=ERROR_CREDENTIALS_MISSING,
            message="Claude Code credentials not found",
            base_url=DEFAULT_CLAUDE_CODE_BASE_URL,
        ),
        None,
    )
```

- [ ] **Step 4: Run subscription auth tests**

Run:

```bash
uv run pytest tests/test_subscription_auth.py -v
```

Expected: PASS for current tests.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add src/financial_report_llm_extractor/subscription_auth.py tests/test_subscription_auth.py
git commit -m "feat: read codex subscription credentials"
```

---

### Task 3: Claude Code Credential Reader

**Files:**
- Modify: `src/financial_report_llm_extractor/subscription_auth.py`
- Modify: `tests/test_subscription_auth.py`

- [ ] **Step 1: Write failing Claude credential tests**

Append to `tests/test_subscription_auth.py`:

```python
def test_claude_status_prefers_anthropic_token_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_TOKEN", "env-oauth-token")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "lower-priority-token")

    status = subscription_auth_status("claude-code")
    creds = resolve_subscription_credentials("claude-code")

    assert status.available is True
    assert status.token_status == "valid"
    assert status.credential_source == "ANTHROPIC_TOKEN"
    assert status.base_url == DEFAULT_CLAUDE_CODE_BASE_URL
    assert creds.access_token == "env-oauth-token"


def test_claude_status_reads_credentials_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ANTHROPIC_TOKEN", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    credentials_path = tmp_path / ".claude" / ".credentials.json"
    credentials_path.parent.mkdir()
    credentials_path.write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "file-token",
                    "refreshToken": "refresh-token",
                    "expiresAt": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp() * 1000),
                }
            }
        ),
        encoding="utf-8",
    )

    status = subscription_auth_status("claude-code")
    creds = resolve_subscription_credentials("claude-code")

    assert status.available is True
    assert status.token_status == "valid"
    assert status.credential_source == str(credentials_path)
    assert creds.access_token == "file-token"


def test_claude_status_reports_missing_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ANTHROPIC_TOKEN", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    status = subscription_auth_status("claude-code")

    assert status.available is False
    assert status.token_status == "missing"
    assert status.error_code == "subscription_credentials_missing"
    assert status.credential_source == str(tmp_path / ".claude" / ".credentials.json")


def test_claude_status_reports_expired_credentials_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ANTHROPIC_TOKEN", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    credentials_path = tmp_path / ".claude" / ".credentials.json"
    credentials_path.parent.mkdir()
    credentials_path.write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "expired-token",
                    "refreshToken": "refresh-token",
                    "expiresAt": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp() * 1000),
                }
            }
        ),
        encoding="utf-8",
    )

    status = subscription_auth_status("claude-code")
    with pytest.raises(SubscriptionAuthError) as exc_info:
        resolve_subscription_credentials("claude-code")

    assert status.available is False
    assert status.token_status == "expired"
    assert status.error_code == "subscription_token_expired"
    assert exc_info.value.code == "subscription_token_expired"


def test_claude_status_redacts_token_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_TOKEN", "secret-token-value")

    status = subscription_auth_status("claude-code")

    assert "secret-token-value" not in json.dumps(status.__dict__)
```

- [ ] **Step 2: Run Claude tests and verify they fail**

Run:

```bash
uv run pytest tests/test_subscription_auth.py -v
```

Expected: FAIL because `_read_claude_credentials()` still returns missing.

- [ ] **Step 3: Implement Claude credential parsing**

Replace the Claude stub in `subscription_auth.py` with:

```python
def _claude_credentials_path(*, home: Path | None, env: dict[str, str] | None) -> Path:
    return _runtime_home(home, env) / ".claude" / ".credentials.json"


def _claude_file_token_is_expired(expires_at: object) -> bool:
    if not isinstance(expires_at, (int, float)):
        return False
    if expires_at <= 0:
        return False
    return int(time.time() * 1000) >= int(expires_at) - 60_000


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
            creds = SubscriptionRuntimeCredentials(
                provider="claude-code",
                access_token=token,
                credential_source=env_name,
                base_url=DEFAULT_CLAUDE_CODE_BASE_URL,
            )
            return status, creds

    path = _claude_credentials_path(home=home, env=env)
    if not path.is_file():
        return (
            SubscriptionCredentialStatus(
                provider="claude-code",
                available=False,
                credential_source=str(path),
                token_status="missing",
                error_code=ERROR_CREDENTIALS_MISSING,
                message="Claude Code credentials not found; run the official Claude Code login first",
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
                message="Claude Code credentials file is missing claudeAiOauth.accessToken",
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
                message="Claude Code access token is expired; run the official Claude Code login again",
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
    creds = SubscriptionRuntimeCredentials(
        provider="claude-code",
        access_token=access_token.strip(),
        credential_source=str(path),
        base_url=DEFAULT_CLAUDE_CODE_BASE_URL,
    )
    return status, creds
```

- [ ] **Step 4: Run subscription auth tests**

Run:

```bash
uv run pytest tests/test_subscription_auth.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```bash
git add src/financial_report_llm_extractor/subscription_auth.py tests/test_subscription_auth.py
git commit -m "feat: read claude code subscription credentials"
```

---

### Task 4: Provider Defaults and Shared Response Text Normalization

**Files:**
- Modify: `src/financial_report_llm_extractor/llm_transport.py`
- Modify: `src/financial_report_llm_extractor/llm_field_extraction.py`
- Modify: `src/financial_report_llm_extractor/llm_row_discovery.py`
- Modify: `tests/test_llm_transport.py`
- Modify: `tests/test_llm_field_extraction.py`
- Modify: `tests/test_llm_row_discovery.py`

- [ ] **Step 1: Write failing provider default tests**

Append to `tests/test_llm_transport.py`:

```python
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
```

- [ ] **Step 2: Write failing response normalization tests**

Append to `tests/test_llm_transport.py`:

```python
from financial_report_llm_extractor.llm_transport import response_json_text


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
    raw = {
        "content": [
            {"type": "text", "text": json.dumps({"fields": []})}
        ]
    }

    assert response_json_text(raw) == json.dumps({"fields": []})
```

Append to `tests/test_llm_field_extraction.py`:

```python
def test_unwrap_llm_content_reads_codex_responses_shape() -> None:
    from financial_report_llm_extractor.llm_field_extraction import unwrap_llm_content

    raw = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps({"field_id": "revenue", "found": False}),
                    }
                ],
            }
        ]
    }

    assert unwrap_llm_content(raw)["found"] is False


def test_unwrap_llm_content_reads_anthropic_messages_shape() -> None:
    from financial_report_llm_extractor.llm_field_extraction import unwrap_llm_content

    raw = {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"field_id": "revenue", "found": False}),
            }
        ]
    }

    assert unwrap_llm_content(raw)["found"] is False
```

Append to `tests/test_llm_row_discovery.py`:

```python
def test_row_response_parser_reads_codex_responses_shape() -> None:
    from financial_report_llm_extractor.llm_row_discovery import _parse_row_response

    raw = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": json.dumps({"rows": []})}
                ],
            }
        ]
    }

    assert _parse_row_response(raw) == {"rows": []}


def test_row_response_parser_reads_anthropic_messages_shape() -> None:
    from financial_report_llm_extractor.llm_row_discovery import _parse_row_response

    raw = {"content": [{"type": "text", "text": json.dumps({"rows": []})}]}

    assert _parse_row_response(raw) == {"rows": []}
```

- [ ] **Step 3: Run targeted tests and verify they fail**

Run:

```bash
uv run pytest tests/test_llm_transport.py::test_load_openai_codex_config_uses_subscription_defaults tests/test_llm_transport.py::test_load_claude_code_config_uses_subscription_defaults tests/test_llm_transport.py::test_response_json_text_reads_codex_responses_output_text tests/test_llm_transport.py::test_response_json_text_reads_anthropic_messages_text tests/test_llm_field_extraction.py::test_unwrap_llm_content_reads_codex_responses_shape tests/test_llm_field_extraction.py::test_unwrap_llm_content_reads_anthropic_messages_shape tests/test_llm_row_discovery.py::test_row_response_parser_reads_codex_responses_shape tests/test_llm_row_discovery.py::test_row_response_parser_reads_anthropic_messages_shape -v
```

Expected: FAIL because new provider kinds and parser shapes are missing.

- [ ] **Step 4: Implement provider defaults and shared normalizer**

In `llm_transport.py`, update provider kind definitions:

```python
ProviderKind = Literal[
    "openai-compatible",
    "gemini",
    "codex-responses",
    "anthropic-messages",
]
```

Add defaults:

```python
    "openai-codex": ProviderDefaults(
        base_url="https://chatgpt.com/backend-api/codex",
        api_key_env="",
        kind="codex-responses",
    ),
    "claude-code": ProviderDefaults(
        base_url="https://api.anthropic.com",
        api_key_env="",
        kind="anthropic-messages",
    ),
```

Update `_normalize_provider()`:

```python
    if normalized in {"codex", "openai-codex"}:
        return "openai-codex"
    if normalized in {"claude", "claude-code", "anthropic-subscription"}:
        return "claude-code"
```

Rename `_response_json_text()` to public helper and keep private alias:

```python
def response_json_text(raw_response: dict[str, object]) -> str:
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

    output = raw_response.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content_list = item.get("content")
            if not isinstance(content_list, list):
                continue
            for part in content_list:
                if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                    text = part.get("text")
                    if isinstance(text, str):
                        return text
        raise ValueError("Codex response missing output text")

    anthropic_content = raw_response.get("content")
    if isinstance(anthropic_content, list):
        for part in anthropic_content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    return text
        raise ValueError("Anthropic response missing text content")

    if choices is not None:
        raise ValueError("LLM response missing choices")
    raise ValueError("LLM response missing candidates")


def _response_json_text(raw_response: dict[str, object]) -> str:
    return response_json_text(raw_response)
```

In `llm_field_extraction.py`, import and use the helper:

```python
from financial_report_llm_extractor.llm_transport import response_json_text
```

Then replace wrapped-shape parsing in `unwrap_llm_content()` with:

```python
    if (
        "choices" in raw
        or "candidates" in raw
        or "output" in raw
        or (
            "content" in raw
            and isinstance(raw.get("content"), list)
        )
    ):
        parsed = json.loads(response_json_text(raw))
        if isinstance(parsed, dict):
            return parsed
        raise ValueError(f"LLM response content must be a JSON object: {raw!r}")
```

In `llm_row_discovery.py`, import:

```python
from financial_report_llm_extractor.llm_transport import response_json_text
```

Then replace its `_response_json_text()` body with:

```python
def _response_json_text(raw_response: dict[str, object]) -> str:
    return response_json_text(raw_response)
```

- [ ] **Step 5: Run targeted tests**

Run:

```bash
uv run pytest tests/test_llm_transport.py::test_load_openai_codex_config_uses_subscription_defaults tests/test_llm_transport.py::test_load_claude_code_config_uses_subscription_defaults tests/test_llm_transport.py::test_response_json_text_reads_codex_responses_output_text tests/test_llm_transport.py::test_response_json_text_reads_anthropic_messages_text tests/test_llm_field_extraction.py::test_unwrap_llm_content_reads_codex_responses_shape tests/test_llm_field_extraction.py::test_unwrap_llm_content_reads_anthropic_messages_shape tests/test_llm_row_discovery.py::test_row_response_parser_reads_codex_responses_shape tests/test_llm_row_discovery.py::test_row_response_parser_reads_anthropic_messages_shape -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

Run:

```bash
git add src/financial_report_llm_extractor/llm_transport.py src/financial_report_llm_extractor/llm_field_extraction.py src/financial_report_llm_extractor/llm_row_discovery.py tests/test_llm_transport.py tests/test_llm_field_extraction.py tests/test_llm_row_discovery.py
git commit -m "feat: normalize subscription llm responses"
```

---

### Task 5: Codex and Claude Transport Clients

**Files:**
- Modify: `src/financial_report_llm_extractor/llm_transport.py`
- Modify: `tests/test_llm_transport.py`

- [ ] **Step 1: Write failing transport client tests**

Append to `tests/test_llm_transport.py`:

```python
def _write_codex_auth(tmp_path: Path, monkeypatch: Any, token: str) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        json.dumps({"tokens": {"access_token": token, "refresh_token": "refresh"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))


def test_codex_client_builds_responses_request(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    from tests.test_subscription_auth import _jwt_with_exp
    from datetime import datetime, timedelta, timezone

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
                            {"type": "output_text", "text": json.dumps({"fields": [{"field_id": "cash", "status": "missing"}]})}
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
    assert payload["store"] is False
    assert json.loads(payload["input"][0]["content"][0]["text"])["field_id"] == "cash"


def test_claude_code_client_builds_messages_request(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("ANTHROPIC_TOKEN", "claude-token")
    transport = FakeHttpTransport(
        [
            {
                "content": [
                    {"type": "text", "text": json.dumps({"fields": [{"field_id": "cash", "status": "missing"}]})}
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
    assert headers["Authorization"] == "Bearer claude-token"
    assert headers["anthropic-version"]
    assert "claude-code" in headers["user-agent"]
    assert payload["model"] == "claude-sonnet-4-6"
    assert payload["max_tokens"] == 4096
    assert json.loads(payload["messages"][0]["content"])["field_id"] == "cash"


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
```

- [ ] **Step 2: Run transport client tests and verify they fail**

Run:

```bash
uv run pytest tests/test_llm_transport.py::test_codex_client_builds_responses_request tests/test_llm_transport.py::test_claude_code_client_builds_messages_request tests/test_llm_transport.py::test_subscription_client_missing_credentials_fails_before_transport -v
```

Expected: FAIL because clients are not implemented or not routed.

- [ ] **Step 3: Implement Codex and Claude clients**

In `llm_transport.py`, import:

```python
from financial_report_llm_extractor.subscription_auth import (
    codex_chatgpt_account_id,
    resolve_subscription_credentials,
)
```

Update `create_llm_client()`:

```python
    if kind == "codex-responses":
        return CodexResponsesClient(config, transport=transport)
    if kind == "anthropic-messages":
        return ClaudeCodeMessagesClient(config, transport=transport)
```

Add:

```python
class CodexResponsesClient:
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
        payload = {
            "model": self.config.model,
            "instructions": system_prompt,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                user_payload,
                                ensure_ascii=False,
                                sort_keys=True,
                            ),
                        }
                    ],
                }
            ],
            "text": {"format": {"type": "json_object"}},
            "store": False,
        }
        raw_response = self._post_with_retries(payload)
        self.raw_exchanges.append(RawExchange(request=payload, raw_response=raw_response))
        return raw_response

    def _post_with_retries(self, payload: dict[str, object]) -> dict[str, object]:
        attempts = self.config.max_retries + 1
        last_error: TimeoutError | URLError | None = None
        for _ in range(attempts):
            try:
                creds = resolve_subscription_credentials("openai-codex")
                return self.transport.post_json(
                    f"{self.config.base_url.rstrip('/')}/responses",
                    _codex_headers(creds.access_token),
                    payload,
                    self.config.timeout_seconds,
                )
            except (TimeoutError, URLError) as error:
                last_error = error
        if last_error is not None:
            raise last_error
        raise RuntimeError("Codex transport failed without an error")


def _codex_headers(access_token: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "originator": "codex_cli_rs",
        "User-Agent": "codex_cli_rs/0.0.0",
    }
    account_id = codex_chatgpt_account_id(access_token)
    if account_id:
        headers["ChatGPT-Account-ID"] = account_id
    return headers
```

Add:

```python
class ClaudeCodeMessagesClient:
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
        payload = {
            "model": self.config.model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(
                        user_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            ],
        }
        raw_response = self._post_with_retries(payload)
        self.raw_exchanges.append(RawExchange(request=payload, raw_response=raw_response))
        return raw_response

    def _post_with_retries(self, payload: dict[str, object]) -> dict[str, object]:
        attempts = self.config.max_retries + 1
        last_error: TimeoutError | URLError | None = None
        for _ in range(attempts):
            try:
                creds = resolve_subscription_credentials("claude-code")
                return self.transport.post_json(
                    f"{self.config.base_url.rstrip('/')}/v1/messages",
                    _claude_code_headers(creds.access_token),
                    payload,
                    self.config.timeout_seconds,
                )
            except (TimeoutError, URLError) as error:
                last_error = error
        if last_error is not None:
            raise last_error
        raise RuntimeError("Claude Code transport failed without an error")


def _claude_code_headers(access_token: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "claude-code-20250219,oauth-2025-04-20",
        "user-agent": "claude-code/0.0.0",
        "x-app": "cli",
    }
```

- [ ] **Step 4: Run transport client tests**

Run:

```bash
uv run pytest tests/test_llm_transport.py::test_codex_client_builds_responses_request tests/test_llm_transport.py::test_claude_code_client_builds_messages_request tests/test_llm_transport.py::test_subscription_client_missing_credentials_fails_before_transport -v
```

Expected: PASS.

- [ ] **Step 5: Run all transport tests**

Run:

```bash
uv run pytest tests/test_llm_transport.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

Run:

```bash
git add src/financial_report_llm_extractor/llm_transport.py tests/test_llm_transport.py
git commit -m "feat: add codex and claude subscription transports"
```

---

### Task 6: CLI Auth Status and Subscription Smoke

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `src/financial_report_llm_extractor/llm_transport.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Append to `tests/test_cli.py`:

```python
import json


def test_llm_auth_status_command_prints_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from financial_report_llm_extractor.subscription_auth import (
        SubscriptionCredentialStatus,
    )

    def fake_status(provider: str) -> SubscriptionCredentialStatus:
        assert provider == "openai-codex"
        return SubscriptionCredentialStatus(
            provider="openai-codex",
            available=True,
            credential_source="test-source",
            token_status="valid",
            base_url="https://chatgpt.com/backend-api/codex",
        )

    monkeypatch.setattr(cli, "subscription_auth_status", fake_status)

    exit_code = cli.main(["llm-auth-status", "--provider", "openai-codex"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider"] == "openai-codex"
    assert payload["available"] is True
    assert payload["credential_source"] == "test-source"


def test_llm_subscription_smoke_rejects_non_subscription_provider(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "llm_config.json"
    config_path.write_text(
        json.dumps({"provider": "ollama", "model": "qwen2.5:7b"}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        cli.main(
            [
                "llm-subscription-smoke",
                "--config",
                str(config_path),
                "--out",
                str(tmp_path / "smoke"),
            ]
        )


def test_llm_subscription_smoke_writes_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "llm_config.json"
    out_dir = tmp_path / "smoke"
    config_path.write_text(
        json.dumps({"provider": "openai-codex", "model": "gpt-5.3-codex"}),
        encoding="utf-8",
    )

    class FakeSmokeClient:
        raw_exchanges: list[object] = []

        def complete_json(
            self,
            *,
            system_prompt: str,
            user_payload: dict[str, object],
        ) -> dict[str, object]:
            assert "Return strict JSON" in system_prompt
            assert user_payload["task"] == "subscription_smoke"
            return {"choices": [{"message": {"content": json.dumps({"ok": True})}}]}

    def fake_create_client(config: object) -> FakeSmokeClient:
        return FakeSmokeClient()

    monkeypatch.setattr(cli, "create_llm_client", fake_create_client)

    exit_code = cli.main(
        [
            "llm-subscription-smoke",
            "--config",
            str(config_path),
            "--out",
            str(out_dir),
        ]
    )

    assert exit_code == 0
    assert (out_dir / "prompt.json").exists()
    assert (out_dir / "raw_response.json").exists()
    assert (out_dir / "parsed_response.json").exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
```

- [ ] **Step 2: Run CLI tests and verify they fail**

Run:

```bash
uv run pytest tests/test_cli.py::test_llm_auth_status_command_prints_json tests/test_cli.py::test_llm_subscription_smoke_rejects_non_subscription_provider tests/test_cli.py::test_llm_subscription_smoke_writes_artifacts -v
```

Expected: FAIL because parser commands and CLI-level imports are missing.

- [ ] **Step 3: Add CLI imports**

At the top of `cli.py`, add:

```python
from dataclasses import asdict

from financial_report_llm_extractor.llm_transport import (
    LlmTransportConfig,
    create_llm_client,
    response_json_text,
    run_real_transport_probe,
)
from financial_report_llm_extractor.subscription_auth import subscription_auth_status
```

Then remove the existing single import:

```python
from financial_report_llm_extractor.llm_transport import run_real_transport_probe
```

- [ ] **Step 4: Add parser commands**

In `build_parser()`, after the existing `extract` parser block, add:

```python
    auth_status_parser = subparsers.add_parser("llm-auth-status")
    auth_status_parser.add_argument(
        "--provider",
        required=True,
        choices=["openai-codex", "claude-code"],
    )

    subscription_smoke_parser = subparsers.add_parser("llm-subscription-smoke")
    subscription_smoke_parser.add_argument("--config", required=True, type=Path)
    subscription_smoke_parser.add_argument("--out", required=True, type=Path)
```

- [ ] **Step 5: Add smoke helper**

Add above `main()`:

```python
def _run_subscription_smoke(config_path: Path, out_dir: Path) -> dict[str, object]:
    config = LlmTransportConfig.from_json(config_path)
    if config.provider not in {"openai-codex", "claude-code"}:
        raise SystemExit(
            "subscription smoke requires provider openai-codex or claude-code"
        )
    client = create_llm_client(config)
    prompt = {
        "task": "subscription_smoke",
        "provider": config.provider,
        "model": config.model,
        "response_schema": {
            "type": "object",
            "required": ["ok"],
            "properties": {"ok": {"type": "boolean"}},
        },
    }
    raw_response = client.complete_json(
        system_prompt="Return strict JSON for the subscription smoke request.",
        user_payload=prompt,
    )
    parsed = json.loads(response_json_text(raw_response))
    if not isinstance(parsed, dict):
        raise ValueError("subscription smoke response must be a JSON object")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prompt.json").write_text(
        json.dumps(prompt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "raw_response.json").write_text(
        json.dumps(raw_response, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "parsed_response.json").write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "ok": bool(parsed.get("ok")),
        "provider": config.provider,
        "model": config.model,
        "out": str(out_dir),
    }
```

- [ ] **Step 6: Add command dispatch**

In `main()`, before the `extract` command branch, add:

```python
    if args.command == "llm-auth-status":
        status = subscription_auth_status(args.provider)
        print(json.dumps(asdict(status), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "llm-subscription-smoke":
        result = _run_subscription_smoke(args.config, args.out)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
```

- [ ] **Step 7: Run CLI tests**

Run:

```bash
uv run pytest tests/test_cli.py::test_llm_auth_status_command_prints_json tests/test_cli.py::test_llm_subscription_smoke_rejects_non_subscription_provider tests/test_cli.py::test_llm_subscription_smoke_writes_artifacts -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 6**

Run:

```bash
git add src/financial_report_llm_extractor/cli.py tests/test_cli.py
git commit -m "feat: add subscription llm diagnostics"
```

---

### Task 7: Redaction, Integration Regression, and Full Verification

**Files:**
- Modify: `src/financial_report_llm_extractor/llm_transport.py`
- Modify: `tests/test_llm_transport.py`
- Modify: `tests/test_subscription_auth.py`

- [ ] **Step 1: Write failing raw artifact redaction test**

Append to `tests/test_llm_transport.py`:

```python
def test_subscription_raw_response_artifact_does_not_include_token(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    from tests.test_subscription_auth import _jwt_with_exp
    from datetime import datetime, timedelta, timezone

    token = _jwt_with_exp(int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()))
    _write_codex_auth(tmp_path, monkeypatch, token)
    retrieval_probe_path = tmp_path / "retrieval_probe.json"
    config_path = tmp_path / "llm_config.json"
    output_path = tmp_path / "extraction_result.json"
    raw_dir = tmp_path / "raw"
    retrieval_probe_path.write_text(
        json.dumps({"source_pdf_hash": "hash123", "fields": [{"field_id": "cash", "candidates": []}]}),
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
                            {"type": "output_text", "text": json.dumps({"fields": [{"field_id": "cash", "status": "missing"}]})}
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
```

- [ ] **Step 2: Run redaction test**

Run:

```bash
uv run pytest tests/test_llm_transport.py::test_subscription_raw_response_artifact_does_not_include_token -v
```

Expected: PASS if `RawExchange.request` only contains payloads. If it fails, remove any archived headers from `RawExchange` or `_write_raw_exchanges()`.

- [ ] **Step 3: Run all changed test files**

Run:

```bash
uv run pytest tests/test_subscription_auth.py tests/test_llm_transport.py tests/test_llm_field_extraction.py tests/test_llm_row_discovery.py tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 4: Run full verification**

Run:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
```

Expected: all commands PASS. If `mypy` reports new type errors, fix the typed signatures in the touched files and rerun `uv run mypy src tests`.

- [ ] **Step 5: Commit verification fixes**

If Step 4 required changes, run:

```bash
git add src/financial_report_llm_extractor tests
git commit -m "test: verify subscription llm support"
```

If Step 4 required no changes, skip this commit.

---

## Self-Review Notes

- Spec coverage: Tasks 1-3 cover read-only credential status and runtime credentials; Tasks 4-5 cover config integration and transports; Task 6 covers diagnostics and smoke; Task 7 covers redaction and verification.
- Scope check: The plan does not implement login, device-code OAuth, refresh, credential pools, automatic fallback, UI, or source-first financial policy changes.
- Type consistency: Provider ids are consistently `openai-codex` and `claude-code`; token status values are `valid`, `missing`, `expired`, and `invalid`; error codes match the spec.
- Parser consistency: `response_json_text()` is the shared parser entry for OpenAI-compatible, Gemini, Codex Responses, and Anthropic Messages response shapes.

## Post-Review Amendments

- Codex subscription Responses require `stream: true`; the stdlib transport must
  parse `text/event-stream` and return the completed Responses object or an
  assembled `output_text` response.
- Codex `text.format.type=json_object` requests must include the literal
  lower-case `json` keyword in instructions.
- Direct Anthropic `/v1/messages` calls with Claude Code subscription OAuth
  tokens are best-effort only. If Anthropic rejects them with subscription
  policy/rate-limit responses, the follow-up architecture is a separate
  `claude -p` CLI bridge, not a change to the current HTTP transport.
