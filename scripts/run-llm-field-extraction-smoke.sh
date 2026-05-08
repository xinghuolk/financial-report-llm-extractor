#!/usr/bin/env bash
# Run the opt-in real-LLM smoke for 00001 revenue.
#
# Required env:
#   REAL_LLM_SMOKE=1
#   LLM_CONFIG_PATH=path/to/llm_config.json
#
# Example llm_config.json (DeepSeek):
# {
#   "provider": "deepseek",
#   "base_url": "https://api.deepseek.com/v1",
#   "model": "deepseek-v4-flash",
#   "api_key_env": "DEEPSEEK_API_KEY",
#   "max_retries": 2,
#   "timeout_seconds": 60
# }

set -euo pipefail

if [[ "${REAL_LLM_SMOKE:-}" != "1" ]]; then
  echo "REAL_LLM_SMOKE must be set to 1 to run the smoke." >&2
  exit 2
fi

if [[ -z "${LLM_CONFIG_PATH:-}" ]]; then
  echo "LLM_CONFIG_PATH must be set to a llm_config.json path." >&2
  exit 2
fi

uv run pytest tests/test_llm_field_extraction.py::test_real_llm_smoke_extracts_revenue_within_tolerance -v -s
