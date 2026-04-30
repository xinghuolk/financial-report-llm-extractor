# Phase 14 DeepSeek Gemini Ollama Provider Support Spec

> Date: 2026-04-30
> Status: approved for implementation
> Scope: Add explicit provider support for DeepSeek, Gemini, and Ollama while preserving auditability and opt-in network usage.

## Goal

Support three practical provider targets for real LLM smoke tests:

- `deepseek`
- `gemini`
- `ollama`

This should follow the same broad separation used in `../hermes-agent`: provider resolution is separate from request construction, transport, response parsing, and extraction logic. This project must not copy Hermes Agent's automatic fallback, OAuth, credential pools, or broad runtime resolver.

## Provider Behavior

### DeepSeek

DeepSeek uses the OpenAI-compatible chat completions protocol.

Default config:

```json
{
  "provider": "deepseek",
  "model": "deepseek-chat",
  "base_url": "https://api.deepseek.com/v1",
  "api_key_env": "DEEPSEEK_API_KEY"
}
```

### Ollama

Ollama uses the OpenAI-compatible local chat completions protocol.

Default config:

```json
{
  "provider": "ollama",
  "model": "qwen2.5:7b",
  "base_url": "http://localhost:11434/v1",
  "api_key_env": "OLLAMA_API_KEY"
}
```

Ollama should not require an API key. If `OLLAMA_API_KEY` is unset, requests should omit `Authorization`.

### Gemini

Gemini uses the Google `generateContent` protocol, not OpenAI chat completions.

Default config:

```json
{
  "provider": "gemini",
  "model": "gemini-1.5-flash",
  "base_url": "https://generativelanguage.googleapis.com/v1beta",
  "api_key_env": "GEMINI_API_KEY"
}
```

The Gemini adapter may also fall back from `GEMINI_API_KEY` to `GOOGLE_API_KEY` when the default env var is not set. API key values must never be written to artifacts.

## Architecture

Add a small provider resolver in `llm_transport.py`:

```text
JSON config
-> LlmTransportConfig.from_json()
-> provider defaults and protocol kind
-> create_llm_client(config)
-> provider-specific request builder
-> shared JSON response parsing into existing LlmResponse or row inventory JSON
```

The resolver should normalize aliases:

- `openai_compatible` and `openai-compatible`
- `deepseek`
- `ollama`
- `gemini`

`deepseek` and `ollama` should use the OpenAI-compatible client. `gemini` should use a separate Gemini client.

## Row Discovery Integration

`discover-rows-llm` must reuse the same provider resolver. It should not know provider-specific URL formats. It should call a provider-neutral JSON completion method and then parse the returned JSON content into `row_inventory_llm.json`.

## Non-Goals

- No automatic fallback among providers.
- No credential pool rotation.
- No OAuth.
- No model catalog.
- No real network calls in tests.
- No implicit provider switching if a provider fails.

## Success Criteria

- Configs for `deepseek`, `gemini`, and `ollama` can be loaded with sensible defaults.
- DeepSeek and Ollama produce OpenAI-compatible chat-completions requests.
- Ollama works without an API key.
- Gemini produces `generateContent` requests and parses Gemini responses.
- `discover-rows-llm` works with the provider-neutral JSON completion interface.
- Tests use injected transports only.
