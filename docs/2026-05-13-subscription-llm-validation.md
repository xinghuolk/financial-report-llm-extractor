# Codex / Claude Subscription Transport — Live Validation & Open Options

> Date: 2026-05-13
> Branch: `feature/codex-claude-subscription-support`
> Status: Codex path validated for production. Claude HTTP path documented as
> diagnostic-only. Future architecture options recorded for follow-up branches.

## TL;DR

- **Codex subscription path is production-ready**. `gpt-5.5` works via Codex
  Responses backend; 4-cohort PDF+LLM validation (1 CN + 3 HK across CNY/HKD/USD
  reporting currencies) shows hit-rate and citation quality on par with or
  better than DeepSeek. Codex actively rejects two known DeepSeek false
  positives, closing G4-C loose end #5 (`dividend_policy_text` precision).
- **Claude Code HTTP direct path is blocked by Anthropic policy**, not a bug.
  Subscription OAuth tokens are accepted by `/v1/messages` (auth + orgId
  resolution succeed) but every request returns `rate_limit_error` with
  vague body `"Error"`. This is Anthropic's intentional limit on programmatic
  use of Claude Code subscription tokens. **The current `ClaudeCodeMessagesClient`
  is therefore diagnostic-only** (token shape, header construction, smoke
  test framework). It is *not* a viable production transport.
- 3 future architecture options for Claude subscription are documented at the
  bottom. None of them are in scope for this branch — they would each warrant
  a separate spec + branch.

## 4-Cohort Codex `gpt-5.5` Validation (2026-05-13)

Reused existing source inventories; only the LLM supplement step differs.
Catalog: post-G4-C (68 mapped fields). DeepSeek baseline runs are the most
recent published evaluate-company artifacts under `tmp/runs/`.

| Cohort | Currency | DeepSeek baseline | Codex `gpt-5.5` | Δ |
|---|---|---|---|---|
| 600519 CN-2024 | CNY | 42 + 12 = **54/68** | 42 + 10 = **52/68** | **-2 (codex correctly declined 2 DS false positives)** |
| 00001 HK-2025 | HKD | 32 + 12 = **44/68** | 32 + 15 = **47/68** | **+3** |
| 01810 HK-2024 | CNY | 35 + 13 = **48/68** | 35 + 18 = **53/68** | **+5** |
| 09987 HK-2024 | USD | 34 + 10 = **44/68** | 34 + 9 = **43/68** | **-1** |
| **Total** | | 143 + 47 = **190/272** | 143 + 52 = **195/272** | **+5** |

`clean_present` count is identical (source-first layer is provider-determined,
not LLM-dependent). All movement is in the LLM supplement layer.

### Quality observations beyond raw count

**Codex correctly rejects DeepSeek false positives on 600519**:

| Field | DeepSeek value | Codex response | Verdict |
|---|---|---|---|
| `dividend_policy_text` (P4) | Returned `"公司利润分配符合《章程》规定"` (compliance acknowledgement, not policy text) | `status: not_found` with reasoning: *"chunks include execution details but NOT the standing long-term policy text such as a target payout ratio, dividend frequency commitment, or other ongoing policy terms"* | **Codex is correct**. Closes G4-C roadmap §6 loose end #5. |
| `receiv_tax_refund` (P2) | Returned `1,500,047.04` (this is the 2023 column value) | `status: not_found` with reasoning: *"2024年度 amount is blank; 2023年度 shows 1,500,047.04. -100% YoY change confirms current period not reported"* | **Codex is correct**. Moutai reports no 2024 tax refund. |

**Codex citation quality is materially higher**: every supplement response
includes `page`, `confidence`, `reasoning`, and `statement_line`. Spot-check of
4 codex-only 01810 hits (none of which DeepSeek captured):

- `c_paid_for_taxes` = 3,467,218 RMB'000, page 237, conf 0.99 — verified
- `dividends_paid` = -23,286 RMB'000 (to NCI), page 238, conf 0.87 — verified
- `non_oper_income` = 1,666,779 RMB'000 (other income line), page 230, conf 0.86 — verified
- `non_recurring_items_breakdown` = SBC 0.9B RMB + smart EV-related items, page 10, conf 0.72 — verified text-mode hit

### Cohort coverage milestones closed by this validation

- G4-C roadmap §6 loose end #3: 00001 and 09987 cohort rows refreshed under
  Codex + post-G4-C catalog (no longer "pre-G4-C baseline 保守估计").
- G4-C roadmap §6 loose end #5: `dividend_policy_text` precision concern
  confirmed (DeepSeek hits were shallow false positives). Future P4 field
  precision audits should use Codex `gpt-5.5` as the reference LLM.

## Claude Code HTTP Direct — Diagnostic Only

### Observed behavior (live, 2026-05-13)

The current `ClaudeCodeMessagesClient` sends a single-turn Messages request to
`https://api.anthropic.com/v1/messages` with subscription OAuth bearer token
plus the published Claude Code beta headers. The auth layer works:

- Token from `~/.claude/.credentials.json` parses correctly
- Anthropic resolves `anthropic-organization-id` (returned in response headers)
- Request reaches the model layer (no auth-related error)

But the response is always:

```
HTTP 429 Too Many Requests
x-should-retry: true
body: {"type":"error","error":{"type":"rate_limit_error","message":"Error"},...}
```

This is *not* a transient rate limit. It reproduces immediately on the first
call against a freshly authenticated CLI session. The vague `"Error"` body and
the `x-should-retry: true` lie are consistent with Anthropic's known practice
of policy-blocking programmatic use of Claude Code subscription tokens: the
tokens are intentionally scoped to the `claude` CLI process.

### Implication for this branch

- The transport class, header constructor, smoke command, and tests remain
  useful for credential diagnostics (`llm-auth-status`, header shape
  verification, future Hermes-compat work).
- They are **not** a production LLM path. Any extraction run that selects
  `provider: claude-code` will fail at the first network call.
- The smoke command and auth-status command intentionally still ship — they
  let users inspect that their credential file is well-formed and that token
  expiry detection is working, even when end-to-end transport is blocked.

### What was tried before drawing this conclusion

- Confirmed `~/.claude/.credentials.json` is parsed correctly and token is
  unexpired.
- Confirmed `anthropic-beta: claude-code-20250219,oauth-2025-04-20`,
  `user-agent: claude-cli/...`, and `x-app: cli` are sent.
- Retried after 30+ seconds — same 429 with same vague body.
- Same token works in `claude` CLI itself (subscription functioning normally).

## Open Options for Claude Subscription Support (Future Branches)

Three distinct architectural directions, each with its own trade-offs. None of
these are in scope for the `feature/codex-claude-subscription-support` branch.

### Option A — `claude-cli` subprocess adapter (recommended if Claude is needed)

Shell out to the official `claude -p` binary. Implement `LlmJsonClient`
protocol in a `ClaudeCodeCliClient` so callers do not change.

Trade-offs:

- ✓ Most compliant with Anthropic's intended subscription usage model
- ✓ No header construction, token storage, or refresh logic
- ✓ Auto-refresh handled by the CLI itself
- ✓ Future-proof against Anthropic OAuth protocol changes
- ✗ Latency: ~3-5s process spawn + 5-15s model thinking per call. 68 fields
  per company = 10-20 minutes (current Codex is ~6 min, DeepSeek ~5 min).
  Acceptable but ~2-3× slower.
- ✗ Requires `claude` binary in PATH
- ✗ Sequential within a company (no batch protocol)

Implementation gotchas the spec must nail down before coding:

1. **Output format**: `claude -p` default output is markdown/prose. Use
   `--output-format json` if supported in installed version, otherwise prompt
   must force `Return ONLY a JSON object` and adapter must strip any markdown
   fences before `json.loads()`. Spec must be written after spike-testing the
   actual installed CLI behavior.
2. **cwd isolation**: `claude -p` picks up `CLAUDE.md`, `.claude/settings.json`,
   and MCP servers from its working directory. Running it inside this repo
   would pollute prompts with turtle/akshare context. **MVP must spawn from a
   clean temp directory** (e.g., `tempfile.TemporaryDirectory()`).
3. **Latency budget**: spike with one real company before committing — measure
   per-call wall time and total per-company runtime. If > 20 min per company
   the path may not be worth it.
4. **Artifact schema**: raw exchange archive cannot include token (CLI does
   not expose it). Schema differs from HTTP path: stdin prompt + stdout +
   stderr + exit_code + `claude --version`. The existing transport-level
   archival should accept both shapes.

### Option B — `anthropic-api` provider (API key path)

Add a thin provider for users with an Anthropic API key (`sk-ant-api...`).

This may **not need a new transport class**. The existing
`OpenAiCompatibleClient` already accepts arbitrary `base_url`. The first
question to answer before writing any code: does Anthropic's OAI-compat
endpoint accept the request shape this client produces? If yes, this becomes a
config preset only. If no, add an `AnthropicMessagesClient` that shares header
construction with `ClaudeCodeMessagesClient` but with `x-api-key` instead of
`Authorization: Bearer` and without the Claude Code beta header.

Trade-offs:

- ✓ Fast and parallelizable (HTTP, no process overhead)
- ✓ Standard API rate limits and error semantics
- ✓ Already what most automation environments use
- ✗ Costs per-token (not included in any subscription)
- ✗ Users without an API key cannot use Claude at all via this path

### Option C — Keep `claude-code` HTTP transport as diagnostic only

The simplest option: do not extend Claude transport at all. The current
transport remains useful for credential file diagnostics and is documented as
not a production path.

Trade-offs:

- ✓ Zero additional engineering
- ✓ No new code path to maintain
- ✗ Subscription users without API key have no Claude option in this project
- ✗ Footgun: a user with valid credentials may try to use it and hit the 429
  policy block

The footgun is mitigated by clear documentation (this file) and a docstring
on the transport class pointing here.

## Recommended Sequencing

1. **This branch (now)**: ship Codex `gpt-5.5` as a fully validated
   production transport. Document Claude HTTP as diagnostic-only. **No new
   Claude work**.
2. **If demand for Claude subscription support emerges**: spike Option A
   (`claude-cli` subprocess) for ~30 minutes — actually invoke `claude -p`
   with `--output-format json` and a clean temp cwd, measure latency, decide
   whether to commit to a full adapter. If yes, write Option A spec + branch
   it.
3. **If automation/CI requires Claude**: skip Option A entirely, add Option B
   API-key preset (likely ~1-hour change if `OpenAiCompatibleClient` already
   works against Anthropic OAI-compat).

The 4-cohort validation above shows Codex `gpt-5.5` quality is at least
comparable to DeepSeek, often higher. **Adding a second LLM transport is
optional, not blocking** for the data-collection mission of this project.
