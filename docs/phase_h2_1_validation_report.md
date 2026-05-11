# Phase H2.1 Validation Report

> Date: 2026-05-09
> Scope: CN `selling_general_administrative` promotion via addition derivation
> Catalog: post H2.1 commits (`762994d` → `5058f16` → `9fc8d4c` → `56f1eda` → `0b6b397`)

## Summary

| Company | Market | clean_present BEFORE (H2 final) | AFTER (H2.1) | Δ |
|---------|--------|---------------------------------:|--------------:|---|
| 600519 | CN | 38 | **39** | **+1** |

### 600519 unresolved_conflict

| Bucket | H2 | H2.1 | Δ |
|--------|----|------|---|
| clean_present | 38 | **39** | **+1** |
| unresolved_conflict | 17 | **16** | **−1** |
| terminal_unverified | 0 | 0 | 0 |
| source_unavailable | 1 | 1 | 0 |

## Per-field migration

| Field | Company | Before (H2) | After (H2.1) | Reason |
|-------|---------|-------------|--------------|--------|
| selling_general_administrative | 600519 (CN) | unresolved_conflict (akshare:9.32B / yahoo:10.36B) | **clean_present** | derivation `akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE` = 14.95B = PDF EXACT |
| selling_general_administrative | 00001 (HK) | clean_present (incidental Yahoo match) | source_policy_resolvable | catalog source_aliases.yahoo emptied to enable CN derivation; HK Yahoo SGA was `provider_semantics_unverified` per H2 anyway — incidental clean_present was not policy-justified |
| selling_general_administrative | 01113 (HK) | source_unavailable | source_policy_resolvable | same root cause as 00001; HK SGA had no clean policy basis |

## Phase H2.1 deliverables

- **Module A**: `mapping._derive_field` parser supports `+` operator (commit `762994d`, T1).
- **Module B**: derivation operands accept `provider:RAW_FIELD_NAME` form; `map_source_inventory` passes records through to `_derive_field`; cross-provider rejection (commit `5058f16`, T2).
- **PDF spot-check**: 600519/2024 销售费用 + 管理费用 = AKShare MANAGE_EXPENSE + SALE_EXPENSE = 14,954,950,119.87 EXACT (commit `9fc8d4c`, T3).
- **Catalog promotion**: SGA source_aliases emptied + `derivation` field added + provider_raw_semantics_cn rule promoted unverified→sample_verified + 12 LoC `source_policy.py` derived-without-candidates branch (commit `56f1eda`, T4).
- **Defensive test**: focused unit for source_policy `derived` branch (commit `0b6b397`, T4 follow-up).

## Architectural addition: derived-without-candidates branch

A subtle issue surfaced during T4 implementation. `_derive_field` returns a `MappedTurtleField` with `status="derived"` but **no per-source candidates** (the operands were resolved directly from records, not from prior `_map_direct_field` results). The existing `source_policy._resolve_field` cascade fell through to "no primary candidate" and would have classified SGA as `unresolved_conflict` despite the derivation succeeding.

Fix: 12 LoC branch in `source_policy.py:181-192` returning `selected_single_source` for derived-without-candidates fields. Direct unit test added in `test_source_policy.py` to lock the contract.

This pattern will recur for any future `provider:RAW` derivation field — the branch handles all of them, not just SGA.

## HK regression note

Emptying `source_aliases.yahoo` to enable CN derivation also dropped Yahoo SGA matching for HK 00001 + 01113. Result:
- 00001 SGA: clean_present → source_policy_resolvable (Δ −1 clean)
- 01113 SGA: source_unavailable → source_policy_resolvable (no Δ on clean count)

This is **architecturally consistent** — HK Yahoo SGA was `provider_semantics_unverified` per H2 (`provider_raw_semantics_hk.json` rule). The previous "clean_present" status for 00001 was incidental, not policy-justified. H2.1 makes the HK SGA classification reflect the actual policy state.

A future Phase H2.2 could:
1. Restore Yahoo HK SGA alias under a new market-scoped source_aliases mechanism (catalog refactor, out-of-H2.1 scope).
2. Or PDF spot-check Yahoo HK SGA values against HK PDF; if EXACT match, promote.

## Acceptance check

- ✅ Addition derivation (`+`) supported, regression test in test_source_mapping.py
- ✅ `provider:RAW` operands resolve from records, 4 unit tests cover happy + missing + cross-provider + currency cases
- ✅ Cross-file invariant (raw_field_name vs CN_WIDE_FIELD_ALIASES) defensive test still passes
- ✅ 600519/2024 SGA promoted: unresolved_conflict → clean_present (akshare 14,954,950,119.87)
- ✅ Existing H2 4 promotions intact (capex, interest_paid_cash, revenue, operating_profit)
- ✅ D&A, dividends_paid still terminal_unverified (test_phase_h2_da_remains_unverified, test_phase_h2_dividends_paid_terminal_for_cn)
- ✅ Single-sample acknowledged; multi-company verification deferred to Phase H2.2 candidate
- ✅ All 5 H2.1 commits independently green (pytest 527 → 533, ruff + mypy throughout)

## Open follow-ups

- **Phase H2.2 candidate**: multi-company sample-verification for the H2 + H2.1 promotions (revenue, operating_profit, capex, interest_paid_cash, SGA). Currently all rely on 600519/2024 alone as the sample-verified evidence. Per drift §177, single-sample sample_verified rules carry sample-bias risk; broadening to ≥3 CN issuers would harden the proofs.
- **HK SGA**: see note above. Either market-scoped source_aliases refactor OR PDF spot-check Yahoo HK SGA per-issuer.
- **derivation_inputs_use_different_periods** check: `_resolve_derivation_operand` doesn't enforce period equality between the two operand records. If a future caller passes multi-period inventory, `_derive_field` could silently sum across periods. Add a period-match assertion in T2's resolver (small follow-up).
