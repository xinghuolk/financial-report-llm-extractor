# Phase 14 DeepSeek Gemini Ollama Provider Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit DeepSeek, Gemini, and Ollama provider support for real LLM smoke tests.

**Architecture:** Extend `llm_transport.py` with provider defaults, provider kind resolution, a provider-neutral JSON completion interface, and a Gemini `generateContent` adapter. Keep `deepseek` and `ollama` on the existing OpenAI-compatible path. Update row discovery to call the provider-neutral completion method.

**Tech Stack:** Python 3.11 standard library, JSON, urllib transport abstraction, pytest, ruff, mypy.

---

### Task 1: Provider Defaults And Resolution

**Files:**
- Modify: `src/financial_report_llm_extractor/llm_transport.py`
- Modify: `tests/test_llm_transport.py`

- [x] Write failing tests for `LlmTransportConfig.from_json()` defaults for `deepseek`, `ollama`, and `gemini`.
- [x] Implement provider alias normalization and provider defaults.
- [x] Keep existing OpenAI-compatible config behavior working.
- [x] Run `uv run pytest tests/test_llm_transport.py -v`.

### Task 2: OpenAI-Compatible DeepSeek And Ollama Requests

**Files:**
- Modify: `src/financial_report_llm_extractor/llm_transport.py`
- Modify: `tests/test_llm_transport.py`

- [x] Write failing tests proving `deepseek` builds a chat-completions request using `DEEPSEEK_API_KEY`.
- [x] Write failing tests proving `ollama` builds a chat-completions request and omits `Authorization` when no key is set.
- [x] Implement provider-neutral `create_llm_client(config, transport=...)`.
- [x] Add optional auth header handling for Ollama.
- [x] Run `uv run pytest tests/test_llm_transport.py -v`.

### Task 3: Gemini GenerateContent Adapter

**Files:**
- Modify: `src/financial_report_llm_extractor/llm_transport.py`
- Modify: `tests/test_llm_transport.py`

- [x] Write a failing test proving Gemini sends `generateContent` requests to `/models/<model>:generateContent`.
- [x] Assert Gemini uses `x-goog-api-key` and never puts the key into payload.
- [x] Assert Gemini response text is parsed into existing `LlmResponse`.
- [x] Implement `GeminiGenerateContentClient`.
- [x] Run `uv run pytest tests/test_llm_transport.py -v`.

### Task 4: Row Discovery Provider-Neutral Completion

**Files:**
- Modify: `src/financial_report_llm_extractor/llm_row_discovery.py`
- Modify: `tests/test_llm_row_discovery.py`

- [x] Write a failing injected-transport test showing `write_llm_row_inventory()` works with Gemini config.
- [x] Refactor row discovery to use `create_llm_client(...).complete_json(...)`.
- [x] Keep prompt/raw/parsed artifact behavior unchanged.
- [x] Run `uv run pytest tests/test_llm_row_discovery.py -v`.

### Task 5: Verification

- [x] Run `uv run pytest -v`.
- [x] Run `uv run ruff check .`.
- [x] Run `uv run mypy src tests`.
- [x] Run `git diff --check`.

### Task 6: Commit

- [x] Commit with `feat: add deepseek gemini ollama providers`.
