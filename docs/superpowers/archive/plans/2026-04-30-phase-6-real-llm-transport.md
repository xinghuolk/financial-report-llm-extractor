# Phase 6 Real LLM Transport Implementation Plan

> **For agentic workers:** Phase 6 has started with an OpenAI-compatible transport boundary. Tests use injected transports and do not require network access.

**Goal:** Add real LLM extraction behind the same extraction interface while keeping transport calls auditable.

**Architecture:** Keep transport code in `src/financial_report_llm_extractor/llm_transport.py`. It loads provider config, builds OpenAI-compatible chat-completions requests, retries limited transient failures, records raw responses, and reuses the Phase 5 extraction pipeline.

**Tech Stack:** Python 3.11 standard library, `urllib`, dataclasses, JSON, pytest.

---

### Task 1: LLM Config

**Files:**
- Create: `src/financial_report_llm_extractor/llm_transport.py`
- Create: `tests/test_llm_transport.py`

- [x] **Step 1: Write failing tests**

Cover loading provider, model, base URL, API-key env var, timeout, and retry settings from JSON.

- [x] **Step 2: Implement minimal code**

Add `LlmTransportConfig.from_json()`.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_llm_transport.py -v`

Expected: config values load deterministically.

### Task 2: OpenAI-Compatible Client

**Files:**
- Modify: `src/financial_report_llm_extractor/llm_transport.py`
- Modify: `tests/test_llm_transport.py`

- [x] **Step 1: Write failing tests**

Cover request URL, auth header, model payload, timeout, JSON response parsing, and retry behavior.

- [x] **Step 2: Implement minimal code**

Add injectable `HttpTransport`, standard-library `UrllibHttpTransport`, and `OpenAiCompatibleClient`.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_llm_transport.py -v`

Expected: tests pass without live network calls.

### Task 3: Raw Response Artifacts

**Files:**
- Modify: `src/financial_report_llm_extractor/llm_transport.py`
- Modify: `tests/test_llm_transport.py`

- [x] **Step 1: Write failing tests**

Cover `run_real_transport_probe()` writing raw provider/model/request/response JSON artifacts.

- [x] **Step 2: Implement minimal code**

Reuse `run_fake_extraction()` with an `OpenAiCompatibleClient` and write raw exchanges after the run.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_llm_transport.py -v`

Expected: extraction result and raw response artifacts are written.

### Task 4: CLI Command

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Write failing tests**

Cover `extract --retrieval-probe ... --config ... --out ... --raw-response-dir ...`.

- [x] **Step 2: Implement minimal code**

Add the `extract` command.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_cli.py -v`

Expected: CLI calls the real transport layer.

### Follow-Up Work

- [ ] Add sample `llm_config.example.json`.
- [ ] Record latency and structured transport errors in run metadata.
- [ ] Add provider fallback config, explicit and disabled by default.
- [ ] Support non-OpenAI-compatible providers behind the same client protocol.
- [ ] Add integration smoke test guarded by opt-in environment variables.

