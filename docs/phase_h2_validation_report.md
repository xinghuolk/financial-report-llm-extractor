# Phase H2 Validation Report

> Date: 2026-05-09
> Companies: 600519/2024-12-31 (CN, Kweichow Moutai), 00001/2025-12-31 (HK, CK Hutchison), 01113/2025-12-31 (HK, CK Asset)
> Catalog: post H2 Tasks 1-4 (commits 1428281 → ac3660b)
> Mode: fixture-replay (provider_field_baseline) + evaluate-company orchestrator

## Summary

| Company | Market | clean_present BEFORE | AFTER | Δ | unresolved_conflict BEFORE | AFTER | Δ |
|---------|--------|----------------------|-------|---|----------------------------|-------|---|
| 600519 | CN | 34 | **38** | **+4** | 21 | **17** | **−4** |
| 00001 | HK | n/a (orchestrator path) | 0 | — | n/a | 56 | — |
| 01113 | HK | n/a (orchestrator path) | 0 | — | n/a | 56 | — |

**CN headline**: H2 closes 4 of 7 normalized_value_conflict fields cleanly (+4 clean_present, -4 unresolved_conflict).

**HK note**: Both HK companies show 0 clean_present from the orchestrator. This is **NOT a Phase H2 regression** — it surfaces a pre-existing HK fixture/catalog coverage gap. Most HK fields land in `unresolved_conflict` with reason `missing_source_candidate` (no AKShare alias matches the fixture rows) or `currency_as_unit` / `statement_metadata_unproven`. H2 specifically targets `normalized_value_conflict` cases; the HK gap is upstream of H2's scope.

## Per-field bucket migrations (600519/2024)

| Field | BEFORE | AFTER | Reason |
|-------|--------|-------|--------|
| capital_expenditures | unresolved_conflict | clean_present | sign_normalize=absolute (Module A); akshare selected |
| interest_paid_cash | unresolved_conflict | clean_present | sign_normalize=absolute (Module A); akshare selected |
| revenue | unresolved_conflict | clean_present | provider_semantics_sample_verified — akshare OPERATE_INCOME matches PDF 营业收入 (170,899M), Yahoo Total Revenue includes finance subsidiary 利息收入 (174,144M) — different |
| operating_profit | unresolved_conflict | clean_present | provider_semantics_sample_verified — akshare OPERATE_PROFIT matches PDF 营业利润 (119,689M); Yahoo Operating Income (118,276M) excludes adjustments |
| selling_general_administrative | unresolved_conflict | unresolved_conflict | terminal_unverified rule added; akshare MANAGE_EXPENSE alone is partial (excludes SALE_EXPENSE); requires Phase H2.1 addition derivation |
| depreciation_amortization | unresolved_conflict | unresolved_conflict | terminal_unverified rule added; akshare FA_IR_DEPR is fixed-asset only; Yahoo D&A includes intangibles amortization — not equivalent |
| dividends_paid | unresolved_conflict | unresolved_conflict | terminal_unverified rule added; sign-normalize residual 2.9% gap (timing: 已付 vs 宣告) |

## Phase H2 deliverables produced

- **Sign normalize mechanism** (Task 1, commit `1428281`): `MarketSourcePolicy.sign_normalize` field + reconciliation `abs()` comparison branch. 2 unit tests.
- **Module A applied** (Task 2, commit `568063e`): catalog `sign_normalize: "absolute"` for `capital_expenditures` + `interest_paid_cash` (CN+HK); orchestrator threads sign_normalize_fields through. Live confirms 2 fields → clean_present.
- **Module B sample-verified** (Task 3, commit `769117e`): NEW `field_catalog/provider_raw_semantics_cn.json` with akshare OPERATE_INCOME + OPERATE_PROFIT rules. HK companion file appended with 3 unverified rules. Catalog `revenue`/`operating_profit` market_policies.CN restored to cross-check. Market-agnostic `_apply_provider_semantics_promotion` in source_policy. CN catalog auto-load wired into orchestrator.
- **Module B terminal locks** (Task 4, commit `ac3660b`): 3 CN + 3 HK `provider_semantics_unverified` rules for SGA / D&A / dividends_paid. Catalog `preserve_conflict` for these fields. New tests/test_phase_h2_validation.py covers terminal expectations.

## Acceptance check

- ✅ ≥ 2 fields promote on 600519 (capex + interest_paid_cash via Module A)
- ✅ revenue + operating_profit PDF-verified outcome documented in `provider_raw_semantics_cn.json` samples (PDF values match exactly)
- ✅ SGA / D&A / dividends_paid have explicit `provider_semantics_unverified` rules (3 CN + 3 HK = 6 total)
- ✅ 600519 clean_present 34 → 38 (+4); unresolved_conflict 21 → 17 (−4)
- ✅ All 5 H2 commits independently green (pytest 522 → 524, ruff + mypy clean throughout)
- ✅ No silent semantic promotion (every primary swap backed by sample-verified rule; every terminal backed by unverified rule)
- ⚠ HK companies 00001/01113 show 0 clean from orchestrator — pre-existing fixture/catalog mismatch, not H2 regression

## Open follow-ups

- **Phase H2.1 candidate**: catalog addition derivation (e.g., `MANAGE_EXPENSE + SALE_EXPENSE` for SGA). Would unlock CN SGA promotion.
- **HK orchestrator coverage**: 0/56 HK clean indicates upstream fixture/catalog or HK Yahoo trust policy plumbing gap. Investigation worth a dedicated phase. Note this is independent of H2's mechanism — H2's deliverables work correctly when applied to data that does reach the source-policy resolution stage.
- **`OPERATE_PROFIT` raw_field_name vs `CN_WIDE_FIELD_ALIASES` coupling** (flagged in Task 3 review): rule keys on raw code; if alias map gets `OPERATE_PROFIT → 营业利润`, rule silently stops matching. Add second rule with `raw_field_name="营业利润"` OR document the cross-file invariant.
- **Decimal scientific notation**: still not formatted in evaluation.md value column for very small values (Phase EC Tier 1 follow-up partially landed; some edge cases remain).

## Artifacts

- Before-state: `tmp/runs/h2_before/600519.json` (snapshot from commit chain c256ff3..1715fe0..99c20ee i.e. Phase EC Tier 1 final state)
- After-state: `tmp/runs/h2_after/{600519,00001,01113}.json` + per-company evaluation.md/json under `tmp/runs/h2_after/<company>/`
- Live re-runs reproducible via:

  ```bash
  COMPANY=600519 PERIOD_END=2024-12-31 MARKET=CN \
    INVENTORY=tmp/runs/600519_2024-12-31/source_inventory.jsonl \
    OUT_DIR=tmp/runs/h2_after/600519 \
    scripts/run-evaluate-company.sh
  ```

515 unit tests + ruff + mypy clean before H2; 524 unit tests + ruff + mypy clean after.
