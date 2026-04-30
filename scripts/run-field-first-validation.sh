#!/usr/bin/env bash
set -euo pipefail

PDF="${PDF:-downloads/hk_stocks/00001/annual/2025_annual_en.pdf}"
REPORT_ID="${REPORT_ID:-00001_2025_en}"
ROOT="${ROOT:-.}"
SELECTED_FIELDS="${SELECTED_FIELDS:-revenue,net_profit,total_assets,total_liabilities,operating_cash_flow}"

RUN_DIR="${ROOT%/}/tmp/runs/quick_validation/${REPORT_ID}"
CHUNKS_PATH="${RUN_DIR}/chunks.jsonl"

if [[ ! -f "${PDF}" ]]; then
  echo "Missing PDF: ${PDF}" >&2
  echo "Set PDF=/path/to/report.pdf or copy the report into downloads/." >&2
  exit 1
fi

uv run financial-report-llm-extractor quick-validate \
  --pdf "${PDF}" \
  --report-id "${REPORT_ID}" \
  --root "${ROOT}"

if [[ ! -f "${CHUNKS_PATH}" ]]; then
  echo "Missing chunks artifact after quick-validate: ${CHUNKS_PATH}" >&2
  exit 1
fi

uv run python - "${CHUNKS_PATH}" "${SELECTED_FIELDS}" <<'PY'
import json
import sys
from pathlib import Path

from financial_report_llm_extractor.evidence_index import build_evidence_index
from financial_report_llm_extractor.field_first_retrieval import (
    estimate_prompt_budget,
    retrieve_field_first,
)

chunks_path = Path(sys.argv[1])
selected_fields = tuple(
    field.strip() for field in sys.argv[2].split(",") if field.strip()
)
records = [
    json.loads(line)
    for line in chunks_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

index = build_evidence_index(records)
result = retrieve_field_first(index, selected_fields=selected_fields)
budget = estimate_prompt_budget(result)
budget_by_field = {
    field["field_id"]: field["candidate_text_chars"] for field in budget["fields"]
}

print("field-first validation")
print(f"chunks={chunks_path}")
print(f"selected_fields={','.join(selected_fields)}")
for field in result["fields"]:
    candidates = field.get("candidates", [])
    top_candidate = candidates[0] if candidates else {}
    evidence = top_candidate.get("evidence", {})
    page = evidence.get("page", "-")
    block_id = evidence.get("block_id", "-")
    field_id = field["field_id"]
    prompt_chars = budget_by_field.get(field_id, 0)
    print(
        "field="
        f"{field_id} status={field['status']} top_page={page} "
        f"top_block={block_id} prompt_chars={prompt_chars}"
    )
print(f"total_prompt_chars={budget['total_candidate_text_chars']}")
PY
