#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-.}"
cd "${ROOT}"

if [[ -z "${COMPANY:-}" ]]; then
  echo "COMPANY is required" >&2; exit 2
fi
if [[ -z "${MARKET:-}" ]]; then
  echo "MARKET is required (CN or HK)" >&2; exit 2
fi

CATALOG="${CATALOG:-field_catalog/turtle_v015_source_mapping_minimal.json}"
TAXONOMY="${TAXONOMY:-field_catalog/turtle_v015_field_taxonomy.json}"
PRIORITIES="${PRIORITIES:-P0,P1,P2,P3}"

if [[ -n "${YEAR:-}" && -n "${PERIOD_END:-}" ]]; then
  echo "YEAR and PERIOD_END are mutually exclusive" >&2; exit 2
fi
if [[ -n "${YEAR:-}" ]]; then
  PERIOD_FLAG="--year ${YEAR}"
  PERIOD_LABEL="${YEAR}-12-31"
elif [[ -n "${PERIOD_END:-}" ]]; then
  PERIOD_FLAG="--period-end ${PERIOD_END} --report-type ${REPORT_TYPE:-annual}"
  PERIOD_LABEL="${PERIOD_END}"
else
  echo "YEAR or PERIOD_END is required" >&2; exit 2
fi

OUT_DIR="${OUT_DIR:-tmp/runs/${COMPANY}_${PERIOD_LABEL}}"
INVENTORY="${INVENTORY:-${OUT_DIR}/source_inventory.jsonl}"
INVENTORY_SUMMARY="${INVENTORY_SUMMARY:-${OUT_DIR}/source_inventory_summary.json}"

PDF_FLAG=""
if [[ -n "${PDF_PATH:-}" ]]; then
  PDF_FLAG="--pdf ${PDF_PATH}"
fi
LLM_FLAG=""
if [[ -n "${LLM_CONFIG:-}" ]]; then
  LLM_FLAG="--llm-config ${LLM_CONFIG}"
fi

mkdir -p "${OUT_DIR}"

uv run financial-report-llm-extractor evaluate-company \
  --company "${COMPANY}" \
  ${PERIOD_FLAG} \
  --market "${MARKET}" \
  --inventory "${INVENTORY}" \
  --inventory-summary "${INVENTORY_SUMMARY}" \
  --catalog "${CATALOG}" \
  --taxonomy "${TAXONOMY}" \
  ${PDF_FLAG} \
  ${LLM_FLAG} \
  --priorities "${PRIORITIES}" \
  --out "${OUT_DIR}"
