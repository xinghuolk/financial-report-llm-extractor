#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-.}"
cd "${ROOT}"

CATALOG="${CATALOG:-field_catalog/turtle_v015_source_mapping_minimal.json}"
OUT_DIR="${OUT_DIR:-tmp/runs/source_first_evaluation}"

uv run python -m financial_report_llm_extractor.structured_sources.source_first_evaluation \
  --catalog "${CATALOG}" \
  --out-dir "${OUT_DIR}"
