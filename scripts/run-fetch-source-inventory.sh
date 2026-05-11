#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-.}"
cd "${ROOT}"

if [[ -z "${COMPANY:-}" ]]; then
  echo "COMPANY is required (e.g., COMPANY=600519)" >&2
  exit 2
fi
if [[ -z "${MARKET:-}" ]]; then
  echo "MARKET is required (CN or HK)" >&2
  exit 2
fi

CATALOG="${CATALOG:-field_catalog/turtle_v015_source_mapping_minimal.json}"
PROVIDERS="${PROVIDERS:-akshare,yahoo}"

if [[ -n "${YEAR:-}" && -n "${PERIOD_END:-}" ]]; then
  echo "YEAR and PERIOD_END are mutually exclusive" >&2
  exit 2
fi
if [[ -n "${YEAR:-}" ]]; then
  PERIOD_FLAG="--year ${YEAR}"
  PERIOD_LABEL="${YEAR}-12-31"
elif [[ -n "${PERIOD_END:-}" ]]; then
  PERIOD_FLAG="--period-end ${PERIOD_END} --report-type ${REPORT_TYPE:-annual}"
  PERIOD_LABEL="${PERIOD_END}"
else
  echo "YEAR or PERIOD_END is required" >&2
  exit 2
fi

OUT_DIR="${OUT_DIR:-tmp/runs/${COMPANY}_${PERIOD_LABEL}}"
mkdir -p "${OUT_DIR}"

uv run financial-report-llm-extractor fetch-source-inventory \
  --company "${COMPANY}" \
  ${PERIOD_FLAG} \
  --market "${MARKET}" \
  --providers "${PROVIDERS}" \
  --catalog "${CATALOG}" \
  --out "${OUT_DIR}"
