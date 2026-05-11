#!/usr/bin/env bash
set -euo pipefail

PROVIDER="${PROVIDER:-deepseek}"
PDF="${PDF:-downloads/hk_stocks/00001/annual/2025_annual_en.pdf}"
REPORT_ID="${REPORT_ID:-00001_2025_en}"
ROOT="${ROOT:-.}"
SMOKE_STATEMENT_LIMIT="${SMOKE_STATEMENT_LIMIT:-1}"

RUN_DIR="${ROOT%/}/tmp/runs/quick_validation/${REPORT_ID}"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . ".env"
  set +a
fi

if [[ ! -f "${PDF}" ]]; then
  echo "Missing PDF: ${PDF}" >&2
  echo "Set PDF=/path/to/report.pdf or copy the report into downloads/." >&2
  exit 1
fi

case "${PROVIDER}" in
  deepseek)
    MODEL="${DEEPSEEK_MODEL:-deepseek-v4-flash}"
    BASE_URL="${DEEPSEEK_BASE_URL:-https://api.deepseek.com/v1}"
    API_KEY_ENV="DEEPSEEK_API_KEY"
    if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
      echo "Missing DEEPSEEK_API_KEY for provider=deepseek" >&2
      exit 1
    fi
    ;;
  ollama)
    MODEL="${OLLAMA_MODEL:-qwen2.5:7b}"
    BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434/v1}"
    API_KEY_ENV="OLLAMA_API_KEY"
    ;;
  gemini)
    MODEL="${GEMINI_MODEL:-gemini-1.5-flash}"
    BASE_URL="${GEMINI_BASE_URL:-https://generativelanguage.googleapis.com/v1beta}"
    API_KEY_ENV="GEMINI_API_KEY"
    if [[ -z "${GEMINI_API_KEY:-}" && -z "${GOOGLE_API_KEY:-}" ]]; then
      echo "Missing GEMINI_API_KEY or GOOGLE_API_KEY for provider=gemini" >&2
      exit 1
    fi
    ;;
  *)
    echo "Unsupported PROVIDER=${PROVIDER}. Use deepseek, ollama, or gemini." >&2
    exit 1
    ;;
esac

uv run financial-report-llm-extractor quick-validate \
  --pdf "${PDF}" \
  --report-id "${REPORT_ID}" \
  --root "${ROOT}"

CONFIG_PATH="${RUN_DIR}/llm_config_${PROVIDER}.json"
python -c "import json; from pathlib import Path; Path('${CONFIG_PATH}').write_text(json.dumps({'provider': '${PROVIDER}', 'model': '${MODEL}', 'base_url': '${BASE_URL}', 'api_key_env': '${API_KEY_ENV}', 'timeout_seconds': 60, 'max_retries': 1}, indent=2, sort_keys=True) + '\n', encoding='utf-8')"

SMOKE_STATEMENT_MAP="${RUN_DIR}/statement_map_smoke_${PROVIDER}.json"
python -c "import json; from pathlib import Path; source = Path('${RUN_DIR}/statement_map.json'); limit = int('${SMOKE_STATEMENT_LIMIT}'); payload = json.loads(source.read_text(encoding='utf-8')); statements = payload.get('statements', []); preferred_titles = ('consolidated income statement', 'consolidated statement of financial position', 'consolidated statement of cash flows'); preferred = [s for s in statements if str(s.get('title', '')).strip().lower().startswith(preferred_titles)]; payload['statements'] = (preferred or statements)[:limit]; Path('${SMOKE_STATEMENT_MAP}').write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')"

uv run financial-report-llm-extractor discover-rows-llm \
  --chunks "${RUN_DIR}/chunks.jsonl" \
  --statement-map "${SMOKE_STATEMENT_MAP}" \
  --config "${CONFIG_PATH}" \
  --out "${RUN_DIR}/row_inventory_llm_${PROVIDER}.json" \
  --prompt-dir "${RUN_DIR}/prompt_payloads_${PROVIDER}" \
  --raw-response-dir "${RUN_DIR}/raw_llm_responses_${PROVIDER}" \
  --parsed-response-dir "${RUN_DIR}/parsed_llm_responses_${PROVIDER}"

echo "real_llm_smoke=ok"
echo "provider=${PROVIDER}"
echo "model=${MODEL}"
echo "statement_limit=${SMOKE_STATEMENT_LIMIT}"
echo "run_dir=${RUN_DIR}"
