#!/usr/bin/env bash
set -euo pipefail

if [[ "${REAL_SOURCE_VALIDATION:-}" != "1" ]]; then
  echo "Set REAL_SOURCE_VALIDATION=1 to run real AKShare/Yahoo source validation." >&2
  exit 2
fi

ROOT="${ROOT:-.}"
cd "${ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
CATALOG="${CATALOG:-field_catalog/turtle_v015_source_mapping_minimal.json}"
OUT_DIR="${OUT_DIR:-tmp/runs/real_source_validation}"
PROVIDERS="${PROVIDERS:-akshare}"
INVENTORY_FIXTURE="${INVENTORY_FIXTURE:-}"

if [[ -n "${INVENTORY_FIXTURE}" ]]; then
  PYTHONPATH=src "${PYTHON_BIN}" -m financial_report_llm_extractor.structured_sources.real_source_validation \
    --catalog "${CATALOG}" \
    --out-dir "${OUT_DIR}" \
    --inventory-fixture "${INVENTORY_FIXTURE}"
else
  PYTHONPATH=src "${PYTHON_BIN}" -m financial_report_llm_extractor.structured_sources.real_source_validation \
    --catalog "${CATALOG}" \
    --out-dir "${OUT_DIR}" \
    --providers "${PROVIDERS}"
fi
