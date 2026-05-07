# Turtle Field Coverage And Prompt Budget Validation Spec

## Problem

Before continuing with real LLM extraction, the project must prove that the
fields required by the Turtle investment workflow can be found in real financial
report PDFs with a bounded amount of evidence text.

The current field-first validation is useful but too narrow. On
`00001_2025_en`, five selected fields were found, but the same code over the
full P0/P1 catalog found only 9 of 33 fields. This means the next risk is not
LLM extraction quality; it is whether the retrieval layer can cover the required
field set at all.

## Decision Question

For a configured Turtle field set and a configured real-report sample set:

- Which fields have at least one candidate evidence block?
- Which fields are missing before any LLM call?
- How many candidate text characters are needed for `top_k=1`, `3`, `5`, and
  `8`?
- Which fields dominate the prompt budget?
- Should downstream real LLM extraction proceed, or should catalog/retrieval
  work stop the roadmap first?

## Scope

This is a local, deterministic validation layer. It does not call any LLM
provider and does not attempt final field extraction.

Inputs:

- `field_catalog/turtle_v015_priority_fields.json`
- real PDF quick-validation artifacts, especially `chunks.jsonl`
- configured priorities such as `P0`, `P0,P1`, or `P0,P1,P2,P3,P4`
- optional explicit field overrides for smaller experiments
- configured `top_k` values

Outputs:

- `coverage_budget.json`
- `coverage_budget.md`
- console summary suitable for quick triage

Default output location:

```text
tmp/runs/coverage_budget/<report_id>/
```

## Field Set Rules

The validation must distinguish required and optional fields.

- Default required set: `P0,P1`.
- Full catalog audit: `P0,P1,P2,P3,P4`.
- Explicit selected fields may override priorities for small experiments.
- A required field is covered only when it has at least one candidate evidence
  block with page, chunk id, block id, snippet, and candidate text.
- A field that is naturally derived or note-based may later carry derivation or
  note metadata, but in this validation it still appears in the missing or
  covered list. It must not disappear silently.

## Metrics

Per report, field set, and `top_k`, record:

- total field count
- covered field count
- missing field ids
- coverage ratio
- total candidate text chars
- rough token estimate, computed as `ceil(chars / 4)`
- per-field candidate count
- per-field candidate text chars
- top candidate evidence: page, chunk id, block id, snippet
- top candidate score when available

The metric is character-based because the current retrieval layer is provider
neutral. Token estimation is advisory and must not be used as the trust boundary.

## Gate Rules

The validation produces a go/no-go decision for LLM extraction.

Default gate for required fields:

- no missing required field
- `top_k` chosen for extraction has total candidate text chars below
  `max_total_chars`
- no single field exceeds `max_field_chars`
- every covered field has concrete evidence refs

Initial default thresholds:

- `max_total_chars`: `40_000`
- `max_field_chars`: `8_000`
- extraction `top_k`: `3`

These thresholds are intentionally conservative. They are not final product
limits; they are a safety gate to prevent building real LLM extraction on top
of a retrieval path that already fails locally.

If the field set fails coverage, budget numbers are still reported but the
decision is `blocked_by_missing_fields`.

If coverage passes but budget fails, the decision is `blocked_by_prompt_budget`.

If coverage and budget pass, the decision is `ready_for_field_scoped_llm_probe`.

## Required Reports For The First Pass

The first pass should run at least:

- `downloads/hk_stocks/00001/annual/2025_annual_en.pdf`
- `downloads/hk_stocks/01113/annual/2025_annual_en.pdf`

Additional reports can be added through script configuration. The validation
must not hard-code issuer-specific logic.

## Report Format

`coverage_budget.json` should contain machine-readable data:

```json
{
  "report_id": "00001_2025_en",
  "catalog_id": "turtle_v015_priority_fields",
  "priorities": ["P0", "P1"],
  "top_k_values": [1, 3, 5, 8],
  "gate": {
    "status": "blocked_by_missing_fields",
    "required_top_k": 3,
    "max_total_chars": 40000,
    "max_field_chars": 8000,
    "blockers": ["operating_profit", "accounts_receiv"]
  },
  "metrics": [
    {
      "top_k": 3,
      "total_fields": 33,
      "covered_fields": 9,
      "missing_fields": ["operating_profit"],
      "coverage_ratio": 0.2727,
      "total_candidate_text_chars": 36266,
      "rough_token_estimate": 9067,
      "fields": [
        {
          "field_id": "revenue",
          "status": "candidates_found",
          "candidate_count": 3,
          "candidate_text_chars": 1772,
          "top_evidence": {
            "page": 349,
            "chunk_id": "page_p0349",
            "block_id": "p0349_b0003",
            "snippet": "Revenue ..."
          }
        }
      ]
    }
  ]
}
```

`coverage_budget.md` should be optimized for review:

- summary table by `top_k`
- gate result
- missing fields
- largest prompt-budget fields
- per-field evidence summary

## Non-Goals

- No real LLM call.
- No whole-PDF prompting.
- No issuer-specific fixes.
- No final normalized financial values.
- No FX conversion or money normalization changes.
- No requirement to solve every missing field in this plan.

## Acceptance Criteria

- A deterministic test can produce coverage and prompt budget metrics from
  chunk records without LLM calls.
- The report shows all required fields, including missing fields.
- The gate blocks extraction when required fields are missing.
- The gate blocks extraction when prompt budget exceeds configured thresholds.
- A script can run the validation against local real PDF artifacts and write
  `tmp/runs/coverage_budget/<report_id>/coverage_budget.json`.
- Documentation states that this validation must pass before broad real LLM
  extraction continues.
