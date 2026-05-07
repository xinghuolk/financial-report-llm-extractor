# Phase 11 Statement/Row Discovery To Selected-Field Demo Spec

> Date: 2026-04-30
> Status: ready for implementation
> Scope: Add a no-network statement map, row inventory, and selected-field catalog mapping demo.

## Goal

Phase 11 proves the middle of the revised discovery architecture:

```text
document_map.json + chunks.jsonl
-> statement_map.json
-> row_inventory.json
-> catalog_mapping.json
```

This phase does not implement real LLM row discovery. It creates a fake/rule-first row inventory path that has the same artifact shape later LLM-assisted discovery will use.

## Inputs

- `chunks.jsonl`
- `document_map.json`
- field catalog JSON
- selected field ids

## Outputs

- `statement_map.json`
- `row_inventory.json`
- `catalog_mapping.json`

## Statement Map

`statement_map.json` should identify formal statements inside the audited financial statement range:

- `income_statement`
- `balance_sheet`
- `cash_flow`

Each statement entry includes:

- `statement_id`
- `statement_kind`
- `scope`
- `page_start`
- `page_end`
- `title`
- `unit_context`
- `period_columns`
- `chunk_id`
- `evidence_blocks`

## Row Inventory

`row_inventory.json` lists row labels and raw values found in each statement chunk. This first version may parse simple layout lines with current/prior numeric columns.

Each row includes:

- `statement_id`
- `row_label`
- `values`
- `unit_context`
- `currency_hint`
- `evidence`

## Catalog Mapping

`catalog_mapping.json` maps discovered rows to selected Turtle fields.

Selected demo fields:

- `revenue`
- `net_profit`
- `total_assets`
- `total_liabilities`
- `operating_cash_flow`

Each mapping includes:

- `field_id`
- `status`: `mapped`, `missing`, or `ambiguous`
- `source_row_label`
- `statement_id`
- `mapping_confidence`
- `mapping_reason`
- `evidence`

## Success Criteria

- Synthetic tests prove statement map creation, row inventory extraction, and selected-field mapping.
- CLI exposes thin commands for all three artifacts.
- Every mapped field carries evidence refs.
- Missing selected fields are explicit.
- Full pytest, ruff, and mypy pass.
