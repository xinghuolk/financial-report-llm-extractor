from financial_report_llm_extractor.subscription_auth import (
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
