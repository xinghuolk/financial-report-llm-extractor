import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from financial_report_llm_extractor.subscription_auth import (
    DEFAULT_CODEX_BASE_URL,
    SubscriptionAuthError,
    SubscriptionCredentialStatus,
    resolve_subscription_credentials,
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


def test_codex_status_reads_codex_home_auth_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    token = _jwt_with_exp(
        int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    )
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
    token = _jwt_with_exp(
        int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
    )
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
