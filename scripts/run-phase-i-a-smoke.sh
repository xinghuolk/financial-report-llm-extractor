#!/usr/bin/env bash
# Phase I-A real-LLM smoke runner.
#
# Required env:
#   REAL_LLM_SMOKE=1        gate flag
#   LLM_CONFIG_PATH=path/to/llm_config.json
#
# Runs extract-llm against 00001 HK annual report for the 6 target fields.
# Asserts the artifact is produced and at least one field came back present.

set -euo pipefail

if [[ "${REAL_LLM_SMOKE:-}" != "1" ]]; then
  echo "REAL_LLM_SMOKE must be 1" >&2
  exit 2
fi

: "${LLM_CONFIG_PATH:?LLM_CONFIG_PATH required}"

OUT="${OUT:-tmp/runs/phase_i_a_smoke}"
mkdir -p "$OUT"

uv run financial-report-llm-extractor extract-llm \
  --pdf downloads/hk_stocks/00001/annual/2025_annual_en.pdf \
  --company-id 00001 \
  --catalog field_catalog/turtle_v015_source_mapping_minimal.json \
  --taxonomy field_catalog/turtle_v015_field_taxonomy.json \
  --llm-config "$LLM_CONFIG_PATH" \
  --out "$OUT" \
  --fields accounts_receiv,acct_payable,rd_exp,fv_value_chg_gain,bond_payable,invest_income

ART="$OUT/llm_evidence_supplement.json"
test -f "$ART" || { echo "artifact not produced: $ART" >&2; exit 1; }

uv run python3 -c "
import json
import sys
data = json.loads(open('$ART').read())
present = data.get('summary', {}).get('fields_present', [])
print(f'present={present}')
if not present:
    sys.exit('no present fields - smoke failed')
"

echo "smoke passed: $ART"
