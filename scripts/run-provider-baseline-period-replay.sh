#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-.}"
cd "${ROOT}"

INVENTORY="${INVENTORY:-tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz}"
INVENTORY_SUMMARY="${INVENTORY_SUMMARY:-tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json}"
CATALOG="${CATALOG:-field_catalog/turtle_v015_source_mapping_minimal.json}"
OUT_DIR="${OUT_DIR:-tmp/runs/provider_baseline_period_replay}"

uv run financial-report-llm-extractor replay-provider-baseline \
  --inventory "${INVENTORY}" \
  --inventory-summary "${INVENTORY_SUMMARY}" \
  --catalog "${CATALOG}" \
  --out "${OUT_DIR}"
