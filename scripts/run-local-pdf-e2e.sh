#!/usr/bin/env bash
set -euo pipefail

PDF="${PDF:-downloads/hk_stocks/00001/annual/2025_annual_en.pdf}"
REPORT_ID="${REPORT_ID:-00001_2025_en}"
ROOT="${ROOT:-.}"
PRIORITIES="${PRIORITIES:-P0,P1}"
CATALOG="${CATALOG:-field_catalog/turtle_v015_priority_fields.json}"

RUN_DIR="${ROOT%/}/tmp/runs/quick_validation/${REPORT_ID}"

if [[ ! -f "${PDF}" ]]; then
  echo "Missing PDF: ${PDF}" >&2
  echo "Set PDF=/path/to/report.pdf or copy the report into downloads/." >&2
  exit 1
fi

uv run financial-report-llm-extractor quick-validate \
  --pdf "${PDF}" \
  --report-id "${REPORT_ID}" \
  --root "${ROOT}"

uv run financial-report-llm-extractor retrieve \
  --catalog "${CATALOG}" \
  --chunks "${RUN_DIR}/chunks.jsonl" \
  --out "${RUN_DIR}/retrieval_probe.json" \
  --priorities "${PRIORITIES}"

uv run financial-report-llm-extractor extract-fake \
  --retrieval-probe "${RUN_DIR}/retrieval_probe.json" \
  --out "${RUN_DIR}/extraction_result.json"

uv run financial-report-llm-extractor evaluate \
  --root "${ROOT}" \
  --out "${RUN_DIR}/evaluation_summary.json"

echo "local_pdf_e2e=ok"
echo "run_dir=${RUN_DIR}"
