#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-.}"
cd "${ROOT}"
RUN_ROOT="."
CATALOG="${CATALOG:-field_catalog/turtle_v015_priority_fields.json}"
PRIORITIES="${PRIORITIES:-P0,P1}"
TOP_K_VALUES="${TOP_K_VALUES:-1,3,5,8}"
REQUIRED_TOP_K="${REQUIRED_TOP_K:-3}"
MAX_TOTAL_CHARS="${MAX_TOTAL_CHARS:-40000}"
MAX_FIELD_CHARS="${MAX_FIELD_CHARS:-8000}"
REPORTS="${REPORTS:-00001_2025_en=downloads/hk_stocks/00001/annual/2025_annual_en.pdf,01113_2025_en=downloads/hk_stocks/01113/annual/2025_annual_en.pdf}"

IFS=',' read -r -a report_specs <<< "${REPORTS}"
for report_spec in "${report_specs[@]}"; do
  report_id="${report_spec%%=*}"
  pdf="${report_spec#*=}"
  run_dir="${RUN_ROOT%/}/tmp/runs/quick_validation/${report_id}"
  chunks="${run_dir}/chunks.jsonl"
  out_dir="${RUN_ROOT%/}/tmp/runs/coverage_budget/${report_id}"

  if [[ ! -f "${pdf}" ]]; then
    echo "Missing PDF: ${pdf}" >&2
    exit 1
  fi

  uv run financial-report-llm-extractor quick-validate \
    --pdf "${pdf}" \
    --report-id "${report_id}" \
    --root "${RUN_ROOT}"

  uv run financial-report-llm-extractor coverage-budget \
    --chunks "${chunks}" \
    --catalog "${CATALOG}" \
    --report-id "${report_id}" \
    --priorities "${PRIORITIES}" \
    --top-k-values "${TOP_K_VALUES}" \
    --required-top-k "${REQUIRED_TOP_K}" \
    --max-total-chars "${MAX_TOTAL_CHARS}" \
    --max-field-chars "${MAX_FIELD_CHARS}" \
    --out-dir "${out_dir}"
done
