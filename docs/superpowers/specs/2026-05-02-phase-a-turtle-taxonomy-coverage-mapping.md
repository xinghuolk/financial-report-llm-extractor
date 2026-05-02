# Phase A Turtle Taxonomy, Coverage Matrix, And Minimal Mapping Spec

> Date: 2026-05-02
> Status: design spec
> Scope: define the full Turtle target model, expected coverage routes, and minimal source mapping contract before expanding AKShare/Yahoo coverage.

## 1. Purpose

Phase A establishes the Turtle target model before provider-specific implementation. AKShare and Yahoo/yfinance coverage should be measured against Turtle fields, not used to reshape Turtle semantics around whatever a provider happens to return.

This phase has three sub-phases:

- **A1: Turtle Full Field Taxonomy**: every Turtle field gets domain and semantic metadata.
- **A2: Turtle Coverage Matrix**: every Turtle field gets an expected coverage route and verification status.
- **A3: Minimal Source Mapping Contract**: the current source mapping catalog is linked back to taxonomy and coverage metadata.

## 2. Goals

Phase A must produce:

- A complete metadata catalog for all fields in `field_catalog/turtle_v015_priority_fields.json`.
- A coverage matrix showing expected extraction route for every field.
- A minimal source mapping catalog that is traceable to the full taxonomy and coverage matrix.
- Validation checks that prevent unclassified fields from silently entering mapping or coverage reports.

## 3. Non-Goals

Phase A does not:

- Call real AKShare or Yahoo/yfinance providers.
- Add new source adapters.
- Expand PDF broad retrieval.
- Implement final PDF evidence extraction for notes or MDA fields.
- Guarantee that every Turtle field is source-coverable.

Provider-specific coverage is allowed only as metadata in this phase, using statuses such as `verified`, `expected`, `unknown`, and `unsupported`.

## 4. A1: Turtle Full Field Taxonomy

Every field in `field_catalog/turtle_v015_priority_fields.json` must appear exactly once in a new taxonomy catalog.

Recommended artifact:

```text
field_catalog/turtle_v015_field_taxonomy.json
```

Required top-level metadata:

- `catalog_id`
- `version`
- `source_priority_catalog`
- `fields`

Required field metadata:

- `field_id`
- `priority`
- `domain`
- `statement_type`
- `value_type`
- `source_mode`
- `period_type`
- `scope_expectation`
- `currency_requirement`
- `unit_requirement`
- `evidence_requirement`
- `fallback_policy`
- `description`

Allowed domains:

- `income_statement`
- `balance_sheet`
- `cash_flow`
- `shareholder_return`
- `accounting_adjustments`
- `notes_and_mda`

Allowed source modes:

- `direct`
- `derived`
- `source_optional`
- `pdf_only`
- `llm_review`

Validation rules:

- Every priority field appears in taxonomy.
- No taxonomy field is absent from the priority catalog.
- Every field has exactly one primary `domain`.
- `money` and `derived_money` fields must require currency and unit unless explicitly marked `not_applicable`.
- `pdf_only` and `llm_review` fields must not require source aliases.

## 5. A2: Turtle Coverage Matrix

The coverage matrix describes the expected route for each Turtle field. It is not a provider result artifact. It is the planned coverage model.

Recommended artifact:

```text
field_catalog/turtle_v015_coverage_matrix.json
```

Required top-level metadata:

- `matrix_id`
- `version`
- `taxonomy_catalog`
- `fields`

Required field metadata:

- `field_id`
- `domain`
- `priority`
- `primary_route`
- `routes`
- `verification`: field-level status, one of `verified`, `expected`, `unknown`, or `unsupported`
- `notes`

Allowed primary routes:

- `akshare_direct`
- `yahoo_direct`
- `source_derived`
- `pdf_evidence`
- `llm_review`
- `unsupported_first_stage`

Allowed route entries:

- `source`: `akshare`, `yahoo`, `pdf`, `llm`, or `derived`
- `mode`: `direct`, `derived`, `evidence`, `review`, or `unsupported`
- `status`: `verified`, `expected`, `unknown`, or `unsupported`
- `statement_type`
- `evidence_requirement`

Validation rules:

- Every taxonomy field appears in the coverage matrix.
- Every coverage field exists in taxonomy.
- Every field has one `primary_route`.
- A field may have multiple routes, but at least one route must match `primary_route`.
- Field-level `verification` must be no stronger than route evidence. For example, a `verified` field must have at least one `verified` route matching `primary_route`.
- `pdf_only` taxonomy fields must have `primary_route` of `pdf_evidence` or `llm_review`.
- `direct` taxonomy fields should have at least one provider route unless explicitly marked `unknown`.

## 6. A3: Minimal Source Mapping Contract

The existing minimal source mapping catalog should be treated as an implementation slice, not as the whole Turtle model.

Current artifact:

```text
field_catalog/turtle_v015_source_mapping_minimal.json
```

Required additions:

- `taxonomy_catalog`: reference to `turtle_v015_field_taxonomy`
- `coverage_matrix`: reference to `turtle_v015_coverage_matrix`
- Per mapping entry:
  - `domain`
  - `source_mode`
  - `primary_route`
  - `verification_status`

Validation rules:

- Every minimal mapping field exists in taxonomy.
- Every minimal mapping field exists in coverage matrix.
- Mapping `statement_type` must match taxonomy `statement_type`, unless taxonomy uses `mixed`.
- Mapping `source_mode` must not contradict coverage `primary_route`.
- A mapping field marked `pdf_only` or `llm_review` must not be accepted as source-direct.

## 7. Coverage Reporting

After Phase A, coverage should be reportable without calling providers:

- total Turtle fields
- fields by domain
- fields by priority
- fields by source mode
- fields by primary route
- fields expected from AKShare
- fields expected from Yahoo/yfinance
- fields requiring PDF evidence
- fields requiring LLM review
- fields unsupported in first-stage source-first extraction

This report is a planning and validation artifact. Real coverage from captured source inventories remains Phase C/D/E work.

## 8. Relationship To Current Captured Validation

Current real/captured evidence remains useful:

- AKShare `600519` combined three-statement replay validates 8 of 9 minimal source-mapping fields.
- Yahoo/yfinance `0001.HK` income statement replay validates `revenue`, `net_profit`, and `gross_profit`.

Phase A should record those as `verified` for the relevant fields/routes, but it should not generalize them to all companies or all provider statement families.

## 9. Success Criteria

Phase A is complete when:

- Every Turtle v0.15 field has taxonomy metadata.
- Every Turtle v0.15 field has coverage matrix metadata.
- The minimal source mapping catalog references and agrees with taxonomy and coverage matrix.
- Tests fail on missing, extra, contradictory, or unrouteable fields.
- Source-first coverage reports can distinguish true provider gaps from fields intentionally routed to PDF/LLM.
