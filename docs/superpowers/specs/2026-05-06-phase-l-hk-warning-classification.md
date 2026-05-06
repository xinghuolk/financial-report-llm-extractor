# Phase L: HK Warning Classification Spec

> Date: 2026-05-06
> Status: draft for implementation
> Roadmap phase: Phase L, Classify HK Warning Fields

## Background

Phase K made HK currency, unit, and reporting metadata proof visible and enforced. After the review fix, HK fields can no longer become clean present when statement metadata is unproven or when `unit == currency`.

The current provider baseline replay for `00001` and `01113` still leaves a useful but flat work queue:

- clean present fields: `cash`, `operating_cash_flow`, `investing_cash_flow`, `financing_cash_flow`
- selected with warning fields: `revenue`, `net_profit`
- policy unresolved / metadata blocker / reconciliation conflict fields: `gross_profit`, `total_assets`, `total_cur_assets`, `total_cur_liab`, `total_liabilities`
- missing fields: `bond_payable`, `cip`, `defer_tax_liab`, `invest_income`

Phase L turns these fields into explicit next-action buckets so Phase M and PDF fallback do not start from a broad or ambiguous list.

## Goal

Classify every non-clean HK field in the current 15-field denominator into an actionable queue, with per-field reasons and source evidence preserved in replay artifacts.

The classification must answer:

- Can deterministic source policy or mapping work resolve this?
- Does this field require annual-report PDF verification?
- Does a raw provider candidate exist but the catalog does not map it yet?
- Is the source unavailable in the current captured HK provider data?

## Non-Goals

- Do not expand the minimal source mapping denominator from 15 to 33 fields. That is Phase M.
- Do not refresh AKShare or Yahoo fixtures.
- Do not run PDF ingestion or LLM extraction.
- Do not decide final canonical facts.
- Do not collapse source evidence and PDF evidence into one evidence model.

## Classification Contract

Phase L introduces a warning classification layer with four primary categories:

- `source_policy_resolvable`: deterministic source policy, alias precedence, metadata proof, or provider priority can resolve the field without PDF evidence.
- `pdf_verification_required`: annual-report evidence is needed because providers disagree, values imply FX-like ratio, source semantics differ, or the selected value is single-source/unverified.
- `mapping_expansion_required`: provider raw fields exist for the company/source slice, but the current catalog aliases or policies are insufficient to map them.
- `source_unavailable`: neither AKShare nor Yahoo captured a usable field candidate in the current company/source slice.

Each classification item must include:

- `field_id`
- `category`
- `status`
- `reasons`
- `review_notes`
- `warnings`
- `selected_source`
- `candidate_sources`
- `verification_required`

## Classification Precedence

The categories are mutually exclusive. Use this precedence:

1. `missing` with provider candidates in the company/source slice -> `mapping_expansion_required`
2. `missing` with no provider candidates in the company/source slice -> `source_unavailable`
3. real source disagreement or PDF-required uncertainty -> `pdf_verification_required`
   - `reconciliation_status == "conflict"`
   - `verification_required == true`
   - review notes include `fx_like_ratio`, `metadata_currency_suspected`, `semantic_mismatch`, `normalized_value_conflict`, or `single_source_unverified`
4. deterministic policy/catalog issue -> `source_policy_resolvable`
   - review notes include `currency_metadata_required`, `currency_as_unit`, or `statement_metadata_unproven`
   - status is `ambiguous` or `blocked` and provider candidates exist

If multiple reasons exist, the primary category follows the precedence above, and all supporting reasons remain in `reasons`.

## Provider Candidate Input

Classification must be company/slice-aware. It must not use the broad all-company candidate report alone, because a field can exist for A-share or another HK company but still be unavailable for the current HK company.

For each provider baseline replay slice:

- Build a provider candidate report from the already selected latest-period records for that slice.
- Use existing `discover_provider_field_candidates()` and the Turtle taxonomy.
- Do not call AKShare or Yahoo.
- Do not persist a full candidate report unless needed for review; the warning classification artifact is the required output.

## Replay Output

Each replay slice must write:

- `warning_classification.json`
- `warning_classification.md`

Each company/slice review summary must include:

- `warning_classification.counts_by_category`
- `warning_classification.fields_by_category`
- `warning_classification.items`

The top-level Markdown replay summary must show category counts and field lists for each company/source slice.

## Expected HK Baseline Shape

For `00001` and `01113` combined slices after Phase K:

- `pdf_verification_required` includes:
  - `gross_profit`
  - `net_profit`
  - `revenue`
  - `total_assets`
  - `total_cur_assets`
  - `total_cur_liab`
  - `total_liabilities`
- `mapping_expansion_required` includes:
  - `defer_tax_liab`
- `source_unavailable` includes:
  - `bond_payable`
  - `cip`
  - `invest_income`

If future fixture data changes these exact lists, tests should fail and force a deliberate update.

## Acceptance Criteria

- Provider baseline replay exposes warning classification for every company/source slice and combined slice.
- `00001` and `01113` no longer expose only flat warning/blocker buckets.
- The PDF fallback queue can be read directly from `pdf_verification_required`.
- The mapping expansion queue can be read directly from `mapping_expansion_required`.
- `source_unavailable` is company/slice-specific, not inferred from the broad all-company candidate report.
- Tests run without network access and use existing captured provider fixtures.
