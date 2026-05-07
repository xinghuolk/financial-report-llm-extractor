# HK 15-Field Closure Before P0/P1 Expansion

> Date: 2026-05-06
> Status: Ready for review
> Roadmap position: after Phase M, before full Phase N expansion

## Background

Phase M made HK Yahoo raw-HKD trust explicit and reviewable. The current HK
15-field denominator now has 9 clean-present fields:

- `cash`
- `operating_cash_flow`
- `investing_cash_flow`
- `financing_cash_flow`
- `revenue`
- `total_assets`
- `total_cur_assets`
- `total_cur_liab`
- `total_liabilities`

The Yahoo PDF-verified policy added by Phase M covers:

- `revenue`
- `total_assets`
- `total_cur_assets`
- `total_cur_liab`
- `total_liabilities`

The remaining HK work should close or explicitly classify the 15-field gaps
before expanding the source mapping denominator from 15 fields to the full P0/P1
33 fields. Expanding first would copy unresolved HK definition, mapping, and
availability questions into a larger denominator and make coverage reports less
actionable.

## Goals

1. Resolve whether `net_profit` can be upgraded from selected-with-warnings to
   clean present through PDF/definition proof.
2. Keep `gross_profit` blocked until annual-report row semantics and value proof
   justify any trust-policy upgrade.
3. Run deterministic mapping-expansion review for `defer_tax_liab`, then decide
   whether it can be mapped from captured provider inventory or must remain PDF
   required.
4. Preserve explicit unavailable status for `bond_payable`, `cip`, and
   `invest_income` when captured AKShare/Yahoo data has no usable source field.
5. Produce replay/review artifacts that explain every remaining non-clean HK
   15-field outcome before Phase N expands to 33 fields.

## Non-Goals

1. Do not expand `field_catalog/turtle_v015_source_mapping_minimal.json` to all
   P0/P1 33 fields in this slice.
2. Do not refresh real AKShare or Yahoo captures unless existing fixture evidence
   is insufficient and the user explicitly approves an opt-in source refresh.
3. Do not promote Yahoo HK `gross_profit` or `net_profit` from field id alone.
4. Do not fabricate source mappings for `bond_payable`, `cip`, or
   `invest_income` when provider baseline evidence is absent.
5. Do not turn trust-policy sample evidence into final PDF `Evidence` objects.

## Field Decisions

### `net_profit`

Current state: Yahoo has a selected value, but source policy keeps the field in
`yahoo_definition_unverified`.

Required work:

- Inspect existing annual-report text/proof artifacts for `00001` and `01113`.
- Identify the exact formal statement row that matches Turtle `net_profit`
  semantics, preferably profit attributable to ordinary shareholders or owners.
- Compare the PDF value and unit multiplier against the selected Yahoo raw field.
- If the row semantics and value match, add a trust-policy sample and move the
  rule to `yahoo_pdf_verified`.
- If semantics differ or remain unclear, keep `yahoo_definition_unverified` and
  make the reason visible in replay artifacts.

### `gross_profit`

Current state: provider value exists, but Phase M intentionally did not allow
Yahoo automatic clean-present behavior.

Required work:

- Search existing PDF artifacts for a formal gross-profit row or a deterministic
  derivation from statement rows.
- Accept only proof that can explain both field semantics and value equality.
- If no formal row or deterministic derivation exists, keep the field in
  `pdf_required` or `yahoo_definition_unverified`; do not rely on Yahoo naming
  alone.

### `defer_tax_liab`

Current state: mapping-expansion path.

Required work:

- Run the existing provider candidate discovery / mapping-expansion review
  against captured baseline artifacts.
- Promote a source alias only when the candidate is deterministic, has statement
  and period support, and does not collide with an existing field alias.
- If a mapping is promoted, run period-scoped HK replay and apply the normal HK
  source policy gates.
- If no deterministic candidate exists, keep the field as mapping-blocked or PDF
  required rather than source-unavailable.

### `bond_payable`, `cip`, `invest_income`

Current state: source unavailable in captured AKShare/Yahoo data.

Required work:

- Confirm the source-unavailable classification from current provider baseline
  artifacts.
- Keep these fields out of clean-present coverage unless a new provider capture
  or deterministic PDF fallback is explicitly added later.
- Ensure review output distinguishes unavailable source data from an unmapped
  but available candidate.

## Artifacts

The implementation should update or add review outputs that make the closure
state easy to audit:

- `warning_classification.json` and `.md` for HK slices.
- `source_policy_report.json` for selected provider values and trust-policy
  decisions.
- `hk_yahoo_trust_policy_report.json` when `net_profit` or `gross_profit` policy
  samples are added or intentionally left unverified.
- Mapping-expansion review artifacts for `defer_tax_liab`.
- Provider baseline replay summary fields that continue to report clean-present,
  selected-with-warning, PDF-required, mapping-expansion, and source-unavailable
  counts.

## Acceptance Criteria

1. HK 15-field replay for `00001` and `01113` reports all six remaining fields in
   explicit, reviewable buckets.
2. `net_profit` is either upgraded to clean present with PDF/definition proof or
   remains `yahoo_definition_unverified` with a concrete reason.
3. `gross_profit` is not clean present unless formal PDF row semantics or a
   deterministic derivation is proven.
4. `defer_tax_liab` is classified as mapped, mapping-blocked, or PDF-required
   based on captured provider evidence.
5. `bond_payable`, `cip`, and `invest_income` remain explicitly
   source-unavailable unless new evidence is introduced.
6. Phase N full P0/P1 expansion can start from a stable HK 15-field baseline
   where unresolved fields are not confused with unmapped fields.

## Validation Plan

Focused validation should include:

```bash
uv run pytest tests/test_hk_yahoo_trust_policy.py tests/test_source_policy.py tests/test_warning_classification.py tests/test_provider_baseline_replay.py -v
uv run pytest tests/test_source_mapping_expansion.py tests/test_field_candidate_discovery.py -v
uv run ruff check .
uv run mypy src tests
```

Full validation before finishing implementation should include:

```bash
uv run pytest -v
```

The known full-suite caveat from Phase M remains: the existing
`akshare_cn_600519_balance_sheet` fixture hash mismatch is unrelated to HK
closure work unless this phase changes provider artifact fixtures.
