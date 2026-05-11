# Phase H1: Surgical Conflict Resolution Spec

> Date: 2026-05-08
> Status: Draft
> Roadmap phase: Bucket 2 (deterministic resolution; precedes full Phase H pipeline)

## Goal

Resolve 7 (company, field) conflicts identified post-Phase N replay using the existing `source_policy.semantic_variants` infrastructure rather than building a full PDF supplement pipeline. Each conflict has a clear deterministic resolution based on provider semantic differences already documented.

Expected impact:
- 600519: 30/33 → 32/33 (revenue, operating_profit promote to clean; SGA needs derivation or stays non-clean)
- 00001: 20/33 → 21/33 (inventories promotes; fix_assets locked as terminal)
- 01113: 21/33 → 22/33 (fix_assets promotes via Yahoo)

## Background

After Phase N, replay surfaces `verification_required=true` or `status=ambiguous` for 7 (company, field) pairs. Each has a different root cause — not all need PDF retrieval.

### 600519 revenue
- AKShare `营业收入` (OPERATE_INCOME) = 168,838M CNY
- Yahoo `Total Revenue` = 172,054M CNY (this maps to AKShare `TOTAL_OPERATE_INCOME` / `营业总收入`, not `revenue`)
- Architecture currently treats both as primary candidates → `semantic_mismatch` flag → `verification_required`

Resolution: move Yahoo `Total Revenue` to `semantic_variants.related` for CN market. Keep AKShare `营业收入` primary for CN. Yahoo `Total Revenue` becomes related-variant (not blocked, but won't trigger semantic_mismatch on revenue).

### 600519 operating_profit
- AKShare `OPERATE_PROFIT` = 114,809M CNY
- Yahoo `Operating Income` = 114,072M CNY (Yahoo's own aggregation, slightly different scope)
- Yahoo Operating Income is a Yahoo-defined metric. For Turtle `operating_profit` (营业利润), AKShare is correct.

Resolution: move Yahoo `Operating Income` to `semantic_variants.related` for CN market.

### 600519 selling_general_administrative
- AKShare `MANAGE_EXPENSE` = 8,320M CNY (admin only)
- Yahoo `Selling General And Administration` = 11,787M CNY (combined SGA, matches Turtle semantics)
- AKShare reports SGA as 2 separate fields: SELLING_EXPENSE + MANAGE_EXPENSE. Single MANAGE_EXPENSE is incomplete.

Resolution options:
- (a) Use Yahoo SGA as primary for CN market (matches Turtle semantics directly)
- (b) Add derivation: AKShare `SELLING_EXPENSE + MANAGE_EXPENSE`

Choose (a) for simplicity. Update market policy: CN `selling_general_administrative.primary_route = yahoo_direct`. Move AKShare to cross-check.

### 00001 inventories
- AKShare HK `存货` = 24,105M HKD (incorrect — doesn't match PDF or Yahoo)
- Yahoo `Inventory` = 26,688M HKD = PDF page 136 "Inventories" 26,688M ✓

Resolution: drop AKShare HK alias for inventories. AKShare HK `存货` consistently reports a different/wrong value for these issuers. Update aliases to keep `INVENTORY` for CN AKShare but remove HK Chinese alias.

Actually a cleaner option: keep AKShare alias but use HK market policy with `yahoo_direct` primary and AKShare cross_check. The architecture should select Yahoo. The `fx_like_ratio`/`metadata_currency_suspected` warnings would still fire though, requiring `verification_required`.

Best option: add HK market policy with `yahoo_direct` primary AND add a provider_semantics rule for Yahoo Inventory HK with PDF samples (M5-style proof). This trusts Yahoo and silences the warnings.

### 00001 fix_assets — TERMINAL
- AKShare HK `固定资产` = 90,394M HKD (incorrect, doesn't match PDF)
- Yahoo `Net PPE` = 159,240M HKD = PDF Fixed assets (100,080) + Right-of-use assets (59,160)
- Yahoo aggregates PPE + ROU; PDF shows them separately

For Turtle `fix_assets` semantics (just Fixed assets, not ROU), neither provider directly matches. Lock as terminal `hk_format_incompatible` (similar to gross_profit).

Resolution: 
- Mark `fix_assets` HK as `provider_semantics_unverified` for both AKShare and Yahoo
- Update HK market policy: don't promote either as primary
- Document in coverage_matrix notes

### 01113 fix_assets
- AKShare HK `固定资产` = 65,816M HKD (slightly off)
- Yahoo `Net PPE` = 72,868M HKD = PDF page 71 "Fixed assets" 72,868M ✓ (01113 has minimal ROU so Yahoo Net PPE matches)

For 01113, Yahoo wins. But 00001 is incompatible. So fix_assets HK is per-issuer dependent.

Resolution: Lock `fix_assets` HK as `provider_semantics_unverified` (same as gross_profit). Don't try to promote per-issuer. Future Phase H/I can handle per-company PDF check.

## Design

### 1. revenue + operating_profit CN cleanup

Update `field_catalog/turtle_v015_source_mapping_minimal.json` for `revenue` and `operating_profit`:
- Add Yahoo aliases to `semantic_variants.yahoo.related` (move from `primary` if there)
- Or: keep current structure, but add provider_semantics rule that authorizes AKShare as proven primary for CN

Actually re-reading the current revenue mapping — `semantic_variants.yahoo.primary = ["Total Revenue", "Operating Revenue"]` already lists them as primary. The conflict comes because `Total Revenue` is yahoo-primary but doesn't semantically equal AKShare's `OPERATE_INCOME`.

Cleanest fix: add provider_semantics rule for AKShare CN `OPERATE_INCOME` saying it's `provider_semantics_sample_verified` for `revenue` Turtle field. Then source_policy can use this as proof and skip the verification_required flag.

Wait — looking at source_policy code, the `select_primary_require_pdf` policy fires when conflict is detected, requiring PDF verification. If we want to avoid this, we need either:
(a) Change CN market policy from `select_primary_require_pdf` to `select_primary` (no PDF requirement)
(b) Add provider_semantics that makes the conflict acceptable

Option (a) is simpler. CN AKShare is the canonical source for CN A-shares; cross-source check with Yahoo is informational, conflict shouldn't require PDF.

For `revenue`, `operating_profit`, `selling_general_administrative`: change CN market policy `on_conflict` from `select_primary_require_pdf` to `select_primary`.

Actually simpler still: the AKShare value IS the correct value for these CN fields. We can mark them as `provider_semantics_sample_verified` for CN AKShare in `provider_raw_semantics_cn.json` (new file, parallel to HK). Then the verification flag won't fire.

But creating a parallel CN provider semantics catalog is significant scope. Let me use option (a): change market policy.

### 2. SGA: CN primary route → yahoo_direct

For `selling_general_administrative`, in CN market policy, set `primary_route: yahoo_direct`. Yahoo correctly aggregates SGA; AKShare splits it.

Add cross_check route to akshare_direct.

### 3. HK inventories: drop AKShare 存货 alias OR add HK market policy

Option A: Remove `存货` from inventories yahoo aliases for HK (or globally)
Option B: Add HK market policy with `yahoo_direct` primary + drop AKShare cross-check for HK

Choose Option B: add explicit HK market policy. Yahoo Inventory matches PDF for both 00001 and 01113.

### 4. HK fix_assets: lock as terminal

Update `fix_assets`:
- HK market policy: `primary_route: yahoo_direct` BUT add note marking this as semantically-incompatible-by-issuer
- Add provider_semantics rule for Yahoo Net PPE HK: `classification: provider_semantics_unverified`, `proof_origin: hk_statement_format_incompatible`, similar to gross_profit
- Mark coverage_matrix as needing PDF verification for HK

This makes HK fix_assets stay non-clean but with explicit terminal classification (similar to gross_profit pattern).

### 5. PDF samples for verified mappings

Where we promote a source via market_policy + provider_semantics, add PDF samples (M5 pattern) to the trust_policy or provider_semantics catalog.

For HK inventories: add Yahoo Inventory provider_semantics rule with samples for 00001/01113.

## Implementation Tasks

1. **revenue/operating_profit CN policy relax** (2 fields): Change CN `on_conflict` to `select_primary`, document why. Or add CN provider semantics proof.
2. **SGA CN switch primary** (1 field): Update market_policies.CN.primary_route to yahoo_direct.
3. **HK inventories Yahoo proof** (1 field): Add HK market policy + provider_semantics + trust_policy with PDF samples.
4. **HK fix_assets terminal lock** (1 field × 2 companies): Add provider_semantics unverified + format_incompatible reason.
5. **Update tests** to reflect new clean coverage.
6. **Verify replay**.

## Expected Coverage After H1

| Company | After H0 | After H1 |
|---------|---------|---------|
| 600519 | 30/33 | 32-33/33 |
| 00001 | 20/33 | 21/33 |
| 01113 | 21/33 | 22/33 |

Remaining non-clean fields fall into:
- HK `fix_assets`, `gross_profit` — terminal (HK format incompatible)
- HK `accounts_receiv`, `acct_payable` — Phase I LLM extraction (notes-level)
- HK `bond_payable`, `cip`, `invest_income`, `rd_exp`, `fv_value_chg_gain` — source_unavailable HK (Phase I LLM or terminal)
- HK `non_oper_income`, `non_oper_exp`, `selling_general_administrative` (01113), `other_cur_assets` (00001) — terminal or Phase I

## Out of Scope

- Building full PDF supplement pipeline (deferred to later Phase H pipeline integration)
- LLM-assisted extraction (Phase I)
- New CN provider semantics catalog (use market_policy adjustments instead)

## Verification

```bash
uv run pytest -v
uv run ruff check .
```

All tests pass. Replay shows expected coverage gains per company.
