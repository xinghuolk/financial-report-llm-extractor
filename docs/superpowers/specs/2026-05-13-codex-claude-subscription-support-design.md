# Codex and Claude Subscription Support Spec

> Date: 2026-05-13
> Status: **implemented**. Codex path validated for production via 4-cohort PDF+LLM run;
> Claude HTTP path documented as diagnostic-only due to Anthropic policy block.
> See `docs/2026-05-13-subscription-llm-validation.md` for live findings and the
> 3 open options for a future production Claude path.
> Scope: Add read-only support for existing OpenAI Codex and Claude Code subscription credentials as LLM providers.

## Goal

Add first-class, opt-in LLM transport support for:

- `openai-codex`
- `claude-code`

The first version should let existing extraction commands use already-authenticated
Codex CLI or Claude Code subscription credentials through the current
`llm_config.json` path. It should also provide small diagnostic commands for
credential status and provider smoke testing.

This feature must preserve the extractor's current architecture: a standalone
financial report extraction CLI with thin, auditable provider adapters. It must
not become a general account manager or copy Hermes Agent's credential pool,
fallback router, login UI, or agent runtime.

## User Decisions

- Credential scope: read existing credentials only.
- Config integration: support both production extraction via `--config` /
  `--llm-config` and diagnostic commands.
- Expired tokens: fail explicitly; do not refresh and do not write credential
  files.
- Implementation style: use a narrow local adapter layer informed by
  `/home/like/git/hermes-agent`, not a broad Hermes port.

## Non-Goals

- No login flow.
- No device-code OAuth implementation.
- No token refresh.
- No writes to `~/.codex`, `~/.claude`, or a project-owned auth store.
- No credential pool.
- No automatic provider fallback.
- No subscription cost accounting beyond marking subscription routes as
  included or leaving cost out of artifacts.
- No UI.
- No changes to source-first provider semantics, Turtle mapping, or PDF evidence
  policy.

## Architecture

### Subscription Credential Reader

Add `src/financial_report_llm_extractor/subscription_auth.py`.

Responsibilities:

- Read existing subscription credentials.
- Validate required fields.
- Detect expired tokens where expiry metadata is available.
- Return a redacted status object for diagnostics.
- Return a runtime token to transport clients only when credentials are valid.

It must not:

- Start login flows.
- Refresh tokens.
- Write credentials.
- Persist token values in artifacts.

Credential source behavior:

| Provider | Sources |
| --- | --- |
| `openai-codex` | `$CODEX_HOME/auth.json`, otherwise `~/.codex/auth.json` |
| `claude-code` | `ANTHROPIC_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `~/.claude/.credentials.json` |

For Claude, environment tokens take precedence over the credential file because
they are explicit process-local configuration. For Codex, the default is the
Codex CLI auth file because there is no project-owned auth store in this scope.

Recommended data contracts:

```python
@dataclass(frozen=True)
class SubscriptionCredentialStatus:
    provider: str
    available: bool
    credential_source: str | None
    token_status: Literal["valid", "missing", "expired", "invalid"]
    error_code: str | None = None
    message: str | None = None
    base_url: str | None = None


@dataclass(frozen=True)
class SubscriptionRuntimeCredentials:
    provider: str
    access_token: str
    credential_source: str
    base_url: str
```

Only `SubscriptionRuntimeCredentials` carries token material, and it should
remain in memory.

### Transport Integration

Extend `src/financial_report_llm_extractor/llm_transport.py`.

Provider defaults:

```json
{
  "provider": "openai-codex",
  "model": "gpt-5.3-codex",
  "base_url": "https://chatgpt.com/backend-api/codex",
  "timeout_seconds": 60,
  "max_retries": 0
}
```

```json
{
  "provider": "claude-code",
  "model": "claude-sonnet-4-6",
  "base_url": "https://api.anthropic.com",
  "timeout_seconds": 60,
  "max_retries": 0
}
```

Both new clients must implement the existing `LlmJsonClient` protocol:

```python
complete_json(system_prompt: str, user_payload: dict[str, object]) -> dict[str, object]
```

This keeps existing callers working:

- `extract`
- `extract-llm`
- `extract-llm-batch`
- `discover-rows-llm`
- field-first LLM supplements that already call `create_llm_client()`

### Codex Client

`openai-codex` uses the OpenAI Responses-style backend at:

```text
https://chatgpt.com/backend-api/codex
```

The request should be built from the existing prompt contract:

```json
{
  "model": "gpt-5.3-codex",
  "instructions": "<system prompt>",
  "input": [
    {
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": "<JSON-serialized user_payload>"
        }
      ]
    }
  ],
  "text": {
    "format": {
      "type": "json_object"
    }
  },
  "stream": true,
  "store": false
}
```

Codex subscription Responses must be requested as streaming SSE. The transport
is responsible for parsing `text/event-stream` events and returning the
`response.completed.response` object when present, or a compatible
`output[].content[].text` response assembled from output text events. When
`text.format.type=json_object` is used, the instructions must include the
literal lower-case word `json`; callers that omit it should be normalized by
the Codex client before sending the request.

Headers should include:

- `Authorization: Bearer <token>`
- `Content-Type: application/json`
- Codex-compatible identity headers modeled after Hermes' Codex handling:
  - `originator: codex_cli_rs`
  - `User-Agent` with a `codex_cli_rs/` prefix
  - `ChatGPT-Account-ID` if it can be derived from the access token without
    network calls

The account-id header is a best-effort compatibility detail. Failure to derive
it must not expose token content and should not block local status reporting.

### Claude Code Client

`claude-code` uses the Anthropic Messages API:

```text
https://api.anthropic.com/v1/messages
```

The request should be built from the existing prompt contract:

```json
{
  "model": "claude-sonnet-4-6",
  "max_tokens": 4096,
  "system": "<system prompt>",
  "messages": [
    {
      "role": "user",
      "content": "<JSON-serialized user_payload>"
    }
  ]
}
```

Headers should include:

- `Authorization: Bearer <token>`
- `Content-Type: application/json`
- `anthropic-version`
- Claude Code compatible beta/user-agent headers needed for subscription OAuth
  tokens, based on the narrow subset used by Hermes' `anthropic_adapter.py`.

For this project, the client only needs single-turn JSON completion. It should
not port tool use, streaming, adaptive thinking, prompt-cache replay, MCP tool
rewriting, or Hermes agent identity behavior.

### Response Normalization

Provider-specific clients may return provider-native raw responses for archival,
but parsing should normalize JSON content into a shape existing code can consume.

Two acceptable implementation patterns:

1. Extend `_response_json_text()` and `unwrap_llm_content()` to recognize Codex
   Responses and Anthropic Messages raw response shapes.
2. Have provider clients wrap parsed text into the existing OpenAI-compatible
   `choices[0].message.content` shape while preserving the native response under
   a raw artifact key.

The implementation plan should choose the smaller option after inspecting all
current parser call sites. In either case, raw artifacts must include provider,
model, base URL, request payload, and raw response, but never auth headers or
tokens.

## CLI Behavior

Add:

```bash
financial-report-llm-extractor llm-auth-status --provider openai-codex
financial-report-llm-extractor llm-auth-status --provider claude-code
```

The command writes JSON to stdout:

```json
{
  "provider": "openai-codex",
  "available": true,
  "credential_source": "~/.codex/auth.json",
  "token_status": "valid",
  "base_url": "https://chatgpt.com/backend-api/codex"
}
```

Add:

```bash
financial-report-llm-extractor llm-subscription-smoke \
  --config llm_config.json \
  --out tmp/runs/subscription_smoke
```

The smoke command should:

- Load `LlmTransportConfig`.
- Require provider `openai-codex` or `claude-code`.
- Send a minimal JSON-completion request.
- Archive prompt, raw response, and parsed result under `--out`.
- Fail non-zero on missing, invalid, expired, or rejected credentials.
- Avoid any financial-report extraction or source-first replay side effects.

## Error Handling

Use explicit, stable error codes:

| Code | Meaning |
| --- | --- |
| `subscription_credentials_missing` | No supported credential source found. |
| `subscription_credentials_invalid` | Credential file/env exists but does not have the expected shape. |
| `subscription_token_expired` | Token is present but expired. |
| `subscription_request_failed` | Network or provider response failed. |
| `subscription_provider_unsupported` | Subscription-only command was run against another provider. |

Transport failures should preserve current retry semantics where practical:

- Retry only timeout and transient URL errors, matching current behavior.
- Do not retry credential validation errors.
- Do not attempt refresh after 401/403.
- On 401/403, return a message that asks the user to re-authenticate with the
  official Codex or Claude CLI.

Raw response artifacts may include:

- HTTP status code
- provider error body
- provider
- model
- base URL
- redacted credential source

Raw response artifacts must not include:

- access tokens
- refresh tokens
- `Authorization` header
- full credential JSON

## Testing

Default tests must not touch the real home directory and must not require
network access.

### `tests/test_subscription_auth.py`

Cover:

- Codex auth file found.
- Codex auth file missing.
- Codex token expired.
- Codex invalid JSON or missing token fields.
- Claude env token priority.
- Claude `.credentials.json` found.
- Claude credentials missing.
- Claude token expired.
- Claude invalid JSON or missing `claudeAiOauth`.
- Redacted status does not contain token substrings.

Use temporary directories and monkeypatch `HOME`, `CODEX_HOME`, and environment
variables.

### `tests/test_llm_transport.py`

Cover:

- `LlmTransportConfig.from_json()` supports `openai-codex`.
- `LlmTransportConfig.from_json()` supports `claude-code`.
- Codex client builds Responses payload and Codex-compatible headers.
- Claude client builds Messages payload and Claude Code-compatible headers.
- Missing credentials fail before transport call.
- Expired credentials fail before transport call.
- Raw exchange archival omits auth headers and token values.
- Provider responses parse into existing JSON extraction paths.

Use injected fake `HttpTransport` only.

### `tests/test_cli.py`

Cover:

- `llm-auth-status` emits JSON for valid/missing/expired states.
- `llm-subscription-smoke` rejects non-subscription providers.
- `llm-subscription-smoke` succeeds with fake transport.
- CLI output remains redacted.

### Optional Real Smoke

Real subscription smoke is opt-in:

```bash
REAL_SUBSCRIPTION_SMOKE=1 \
uv run pytest tests/test_subscription_smoke.py -v
```

The test should skip unless explicitly enabled and should use the user's already
configured Codex/Claude credentials. It should not run in default CI.

## Acceptance Criteria

- `openai-codex` and `claude-code` can be selected in `llm_config.json`.
- Existing LLM commands can call both providers through `create_llm_client()`.
- Missing, invalid, and expired credentials fail with stable error codes.
- Diagnostic status and smoke commands exist.
- No command writes subscription credentials.
- No raw artifact contains token material.
- Unit and CLI tests use fake credentials and fake transport only.
- Full default verification remains offline-compatible:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
```

## Risks and Mitigations

**Risk:** Codex backend header requirements change.

Mitigation: isolate Codex header construction in one helper and cover it with
tests that mirror the known Hermes-compatible header contract.

**Risk:** Codex subscription backend requires streaming Responses semantics.

Mitigation: send `stream: true`, parse SSE `response.completed` events in the
stdlib transport, and keep the returned raw response compatible with the shared
`response_json_text()` parser.

**Risk:** Codex `json_object` requests are rejected unless the prompt contains
the literal `json` keyword.

Mitigation: normalize Codex instructions to include a lower-case `json`
directive before sending the request.

**Risk:** Claude Code credential file shape changes.

Mitigation: keep credential parsing narrow, fail with
`subscription_credentials_invalid`, and let users fall back to explicit
`ANTHROPIC_TOKEN` or `CLAUDE_CODE_OAUTH_TOKEN`.

**Risk:** Expired tokens block runs because first version does not refresh.

Mitigation: return `subscription_token_expired` with an actionable message to
run the official CLI login again. This preserves the read-only credential scope.

**Risk:** Anthropic policy blocks direct Claude Code subscription OAuth calls
to `/v1/messages`.

Mitigation: treat the direct `claude-code` HTTP client as best-effort only and
do not present it as a verified production path. If direct calls are rejected
with subscription-specific `rate_limit_error` responses, the viable follow-up is
a separate CLI bridge through the official `claude -p` process, not more HTTP
header changes inside this feature.

**Risk:** Provider-native raw response shapes fragment parsing code.

Mitigation: implement a single response-text normalization helper and reuse it
from field extraction, row discovery, and transport tests.

**Risk:** Subscription support is mistaken for final financial evidence.

Mitigation: keep this feature strictly below the LLM transport boundary. It only
changes how JSON completions are obtained; source-first provider semantics,
PDF evidence policy, and Turtle field status rules remain unchanged.

## Implementation Notes from Hermes Reference

Reference files in `/home/like/git/hermes-agent`:

- `hermes_cli/auth.py`: Codex credential source, default base URL, token expiry
  logic, and device-code flow. This project should use only read/validate ideas,
  not login or refresh behavior.
- `agent/anthropic_adapter.py`: Claude Code credential file parsing and
  subscription OAuth headers. This project should use the minimum needed for
  single-turn Messages API JSON completion.
- `agent/transports/codex.py` and `agent/codex_responses_adapter.py`: Responses
  payload structure. This project should implement a tiny single-turn subset.
- `agent/usage_pricing.py`: subscription routes are treated as included. This
  project does not need full cost estimation in the first version.
