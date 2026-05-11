# Phase H2.2 Validation Report

> Date: 2026-05-10
> Scope: 3 sub-modules — Sub-A multi-company sample-verification, Sub-B HK SGA market-scoped aliases, Sub-C clean-row candidate audit display
> Catalog: post H2.2 commits (`0faf829` → `8beee8d` → `8cd9857` → `e6ebec1` → `0a578a0`)

## Summary

| Company | Market | Period | clean BEFORE (H2.1) | AFTER (H2.2) | Δ |
|---------|--------|--------|--------------------:|-------------:|---|
| 600519 | CN | 2024-12-31 | 39 | 39 | 0 (Sub-A is documentation-strengthening, no bucket movement) |
| 00001 | HK | 2025-12-31 | 28 (clean_present) + 0 terminal | 28 + **1 terminal_unverified** (SGA) | SGA: source_policy_resolvable → terminal_unverified |
| 01113 | HK | 2025-12-31 | 29 + 0 | 29 + 0 (SGA stays source_unavailable; no Yahoo SGA fixture record) | 0 |

## Sub-A: Multi-company sample-verification

PDF spot-check via live `real_source_validation` against AKShare for 3 new CN companies (`tmp/runs/h2_2_real_validation/`):

| Company | Industry | revenue | operating_profit | capex | SGA derivation | interest_paid_cash |
|---------|----------|--------:|-----------------:|------:|---------------:|-------------------:|
| 300750 (CATL) | battery | ✓ EXACT | ✓ EXACT | ✓ EXACT | ✓ EXACT | N/A (non-financial) |
| 601919 (COSCO) | shipping | ✓ EXACT | ✓ EXACT | ✓ EXACT | ✓ EXACT | N/A |
| 688008 (Hygon) | semiconductor | ✓ EXACT | ✓ EXACT | ✓ EXACT | ✓ EXACT | N/A |

Combined with H2/H2.1 600519 baseline:
- **revenue** / **operating_profit** / **capital_expenditures** / **selling_general_administrative**: 4 sample companies covering food / battery / shipping / semiconductor sectors. `provider_raw_semantics_cn.json` rules each carry 4 samples.
- **interest_paid_cash**: still single-sample (600519 only); non-financial CN issuers don't report PAY_INTEREST_COMMISSION. Phase H2.3 candidate to add a CN bank/finance issuer.

`test_phase_h2_2_promoted_cn_rules_have_multi_company_samples` regression-locks the ≥ 2 sample-companies invariant.

## Sub-B: HK SGA market-scoped aliases (Branch B: terminal-honest)

Catalog SGA gains `source_aliases.by_market.HK.yahoo = ["Selling General And Administration"]`. Yahoo HK SGA records now match the catalog entry again (regression-recovery from H2.1 emptying provider-level yahoo aliases).

PDF spot-check decision (per spec Branch B):
- 00001/2025: PDF "Office and general administrative expenses" 9,466M HKD vs Yahoo SGA 16,491M HKD (composes Selling+Marketing 4,157 + G&A 12,334). Different scope. **NOT EXACT.**
- 01113/2025: no single SGA PDF line (real-estate convention). No comparison possible.

**Outcome**: HK Yahoo SGA rule classification stays `provider_semantics_unverified` with 2 spot-check samples documenting the mismatch. HK 00001 SGA bucket transitioned `source_policy_resolvable` → `terminal_unverified` (architecturally honest classification driven by the unverified rule).

Mechanism additions:
- `SourceMappingEntry.by_market_aliases: dict[market, dict[provider, tuple[alias, ...]]]` (default empty)
- Catalog parser routes `source_aliases.by_market` JSON key to the new field
- `mapping._record_matches_entry` checks by_market lookup first, falls back to provider-level
- `_apply_alias_precedence` extended to honor market-scoped aliases over provider-level
- `source_policy._apply_provider_semantics_unverified_warning` (NEW) — fires only when an unverified rule carries fresh PDF samples; gates `terminal_unverified` classification on the basis of explicit spot-check evidence (not stub-level unverified rules)

## Sub-C: clean-row candidate display

Live 600519/2024 evaluation.md after H2.2 — clean_present rows now show competing provider values inline:

| Field | Before (H2.1) | After (H2.2 Sub-C) |
|-------|---------------|--------------------|
| revenue | `\| revenue \| clean_present \| akshare \| 170899152276.34 \| \|` | `\| revenue \| clean_present \| akshare \| akshare:170.90B / yahoo:174.14B \| \|` |
| capital_expenditures | hidden Yahoo value | `akshare:4.68B / yahoo:-4.68B` (sign-mirror visible to reviewer) |
| operating_profit | hidden Yahoo value | `akshare:119.69B / yahoo:118.28B` (1.18% gap visible) |

Single-source / derivation-only rows (e.g. SGA after H2.1) unchanged — display the selected value directly.

`test_render_markdown_shows_candidate_values_for_clean_present_with_multi_source` locks the audit format.

## Aggregate test count

515 (pre-H2) → 524 (H2) → 533 (H2.1) → 540 (H2.2). 25 H2-stack tests added across the 3 phases.

## Phase H2.3 candidates identified

- **interest_paid_cash multi-sample**: include a CN bank (e.g., 600036 China Merchants Bank) or another financial issuer where PAY_INTEREST_COMMISSION is non-null
- **HK 00001 SGA promote**: would require either AKShare HK derivation (analogous to CN MANAGE+SALE — but akshare_hk has no MANAGE_EXPENSE/SALE_EXPENSE raw fields per H2 fixture) or a different Yahoo SGA mapping that excludes the marketing component
- **HK 01113 SGA**: real-estate developer convention has no single SGA line; H2.3 could revisit this as a structurally non-applicable terminal classification rather than `source_unavailable`
- **300750 / 601919 / 688008 fixture extension**: live AKShare data was captured to `tmp/runs/h2_2_real_validation/` but not added to the persistent fixture under `tests/fixtures/provider_captures/`. Future work: extend the fixture to include these 3 companies for offline regression testing without re-fetching from AKShare.

## Acceptance check

- ✅ `provider_raw_semantics_cn.json`: 3 promoted rules each have ≥ 2 sample companies (revenue/op_profit/SGA → 4 each)
- ✅ `source_aliases.by_market` schema parses + mapping lookup respects it
- ✅ HK 00001 SGA: source_policy_resolvable → terminal_unverified
- ✅ evaluation.md clean_present + llm_supplement_present rows with multi-source candidates show all values
- ✅ 600519 clean_present unchanged at 39
- ✅ All 540 unit tests pass; ruff + mypy clean
