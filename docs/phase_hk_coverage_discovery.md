# Phase HK-coverage: Discovery Triage

> Date: 2026-05-10 (post-H2.3)
> Source data: `tmp/runs/h2_2_after/{00001,01113}/evaluation.md` (generated 2026-05-09)
> Goal: enumerate every non-clean cell across HK P0+P1, bucket by root cause, attach effort estimates so we can pick the highest-leverage sub-phase first

## Current state (HK P0+P1 = 33 fields per company)

| Company | clean_present | unresolved_conflict | terminal | source_unavailable | clean ratio |
|---------|---:|---:|---:|---:|---:|
| 00001/2025 | 20 | 12 | 1 (SGA, H2.2) | 0 | 20/33 (61%) |
| 01113/2025 | 21 | 11 | 0 | 1 (SGA) | 21/33 (64%) |

CN baseline 600519 P0+P1 = 33/33 (100%). Gap to close: **~12-13 cells per HK company**.

## Bucket A — `missing_source_candidate` (no provider hit)

Both companies fail the same way for these fields → catalog likely lacks Yahoo and/or AKShare-HK aliases. **No conflict to resolve, just need to expose a candidate.**

| Field | Priority | Both? | Likely root cause | Effort |
|-------|---:|------|-------------------|--------|
| bond_payable | P0 | yes | Yahoo HK exposes "Long Term Debt" / "Long Term Bond"; AKShare HK has 应付债券 — alias missing | XS |
| cip | P0 | yes | Construction-in-progress; Yahoo HK alias likely missing | XS |
| invest_income | P0 | yes | Income from associates/JV; Yahoo HK has "Investment Income Net" | XS |
| rd_exp | P0 | yes (00001 has IT spend, 01113 minimal) | 00001: alias gap; 01113: may be genuinely structural-NA | XS / NA |
| other_cur_assets | P1 | 00001 only (01113 clean) | 00001-specific Yahoo field gap or AKShare-HK alias | XS |
| fv_value_chg_gain | P1 | yes | "Net Fair Value Gains/Losses" — Yahoo HK alias missing | XS |
| non_oper_income | P1 | yes | Yahoo HK "Other Income Net" / similar | XS |
| non_oper_exp | P1 | yes | Yahoo HK "Other Operating Expenses" | XS |

**Bucket A scope**: 8 fields × 2 companies = up to 16 cells closable. Effort: ~XS each (investigate Yahoo/AKShare HK adapters for the right alias, add to catalog `source_aliases.by_market.HK`). Aggregate: **S** (4-6h).

## Bucket B — `normalized_value_conflict` (provider hits exist, values differ)

| Field | Priority | 00001 gap | 01113 gap | Root cause hypothesis | Effort |
|-------|---:|----------:|-----------:|------------------------|--------|
| fix_assets | P0 | akshare 90.39B vs yahoo 159.24B (-43%) | 65.82B vs 72.87B (-10%) | Yahoo PP&E likely includes ROU (right-of-use) lease assets; AKShare reports PP&E excluding leases. HKFRS 16 split. | M |
| accounts_receiv | P0 | akshare 38.21B vs yahoo 14.95B (+155%) | 6.76B vs 2.03B (+233%) | AKShare HK likely combines trade + non-trade + LT receivables; Yahoo is short-term trade only | M |
| acct_payable | P0 | akshare 73.23B vs yahoo 22.63B (+224%) | 17.08B vs 3.61B (+373%) | Same scope drift as accounts_receiv (trade + non-trade + LT) | M |
| gross_profit | P1 | akshare 141.67B vs yahoo 139.20B (+1.8%) | 23.08B vs 25.56B (-9.7%) | Definition: revenue - COGS. Yahoo includes some operating costs; AKShare uses a tighter definition | M |

**Bucket B scope**: 4 fields × 2 companies = 8 cells; resolution requires PDF spot-check + `provider_raw_semantics_hk.json` rules (analogous to H2 CN promotion). Effort: **M-L** (~6-10h: 2 companies × 4 fields = 8 PDF spot-checks + rule writing).

Caveat: same rule must hold across both 00001 (HSBC, banking) AND 01113 (CK Asset, real-estate) — drift §177 sampling-bias risk. May need 3+ HK issuers from different sectors before promotion. Risk: **higher** than CN promotion because HK accounting standards (HKFRS) differ across sector conventions more than CN GAAP.

## Bucket C — terminal / structural

| Field | Company | Bucket | Decision needed |
|-------|---------|--------|-----------------|
| selling_general_administrative | 00001 | terminal_unverified (H2.2 ✓) | Done — no further work in HK-coverage scope |
| selling_general_administrative | 01113 | source_unavailable | **Promote to `not_applicable_terminal`** — real-estate convention has no single SGA line; `source_unavailable` misleadingly implies "we didn't try". Effort: **XS** (catalog flag + 1 test). |

## Bucket D — P3 notes-level (out of HK-coverage scope)

12-13 P3 fields per company are `unresolved_conflict / missing_source_candidate`: bad_debt_provision, buyback_cancellation_progress, capitalized_interest/rd, contingent_liabilities_commitments, dividend_plan, dps, lease_liability_maturity, receivables_aging, related_party_receivables_payables, restricted_cash, segment_revenue_profit, time_deposits_or_wealth_products, stock_based_compensation, repurchase_of_stock, receiv_tax_refund.

These are notes-level fields handled by the Phase I-A HK LLM extraction pipeline, not by source-first. Already validated: 33/84 hits, 0 extraction_failed. **Out of scope** for HK-coverage source-first phase; covered by separate "wire LLM supplement into evaluate-company orchestrator" track.

## Sub-phase candidates

| Sub-phase | Scope | Effort | Coverage delta (P0+P1) | Risk |
|-----------|-------|--------|------------------------:|------|
| **HK-A**: Bucket A alias additions | 8 fields × by_market.HK aliases | S (4-6h) | up to +16 cells (00001: +8, 01113: +7) | LOW (additive, no semantic change) |
| **HK-B**: Bucket B sample-verified promotion | 4 fields × ≥3 HK issuers PDF spot-check + rules | M-L (8-12h) | up to +8 cells | MEDIUM (sample bias if only 2 issuers; HKFRS sector variance) |
| **HK-C**: 01113 SGA structural classification | catalog flag + 1 test | XS (~1h) | +1 cell, but signal-quality improvement only | LOW |
| **LLM-orchestrator**: wire HK LLM runner into evaluate-company | orchestrator integration | M (~6h) | up to +25 P3 cells per company (LLM supplement bucket) | MEDIUM (depends on existing I-A runner reliability) |

## Recommendation

**Start with HK-A** (Bucket A alias additions). Highest leverage-per-hour:
- Closes the most cells (up to 16)
- Lowest risk (additive change, no sample-verification needed since these are missing-source not value-conflict)
- Each field is independent — can land incrementally
- Reveals which fields are genuinely structural-NA (e.g., 01113 R&D) vs alias gaps; informs Bucket B/C scoping later

**Then HK-C** (1h XS) as a quick second win for signal-quality.

**Defer HK-B** until either (a) we have 3+ HK issuer fixtures (current: 2, both single-sector — banking + real-estate), or (b) we observe the same conflict in CN P0 of a non-promoted company that requires the same machinery — building HK-B prematurely on 2 sample companies has a high drift §177 sampling-bias cost.

**Defer LLM-orchestrator** until the source-first ceiling is reached for HK; otherwise we're polishing P3 cells while P0 still has alias gaps.

## Open questions

1. **HK adapter inventory**: do AKShare HK / Yahoo HK actually expose the missing fields? Bucket A's effort estimate assumes "alias missing in catalog, value present in adapter" — needs verification per field. First step of HK-A is `fetch-source-inventory` for both HK tickers and grep for the candidate raw_field codes.
2. **Industry-aware terminal classification**: HK-C's `not_applicable_terminal` semantic doesn't exist yet. Adding it is XS but precedent-setting — should we generalize this? Could resolve other industry-NA cases (e.g., CN financial-issuer-only fields like PAY_INTEREST_COMMISSION for non-financials).

## Reality-check (post-discovery, 2026-05-10)

Inventory scan of `tmp/runs/h2_2_after/{00001,01113}/source_inventory.jsonl` reveals that **most Bucket A fields are genuinely missing from the adapters, not from the catalog**. Per-field empirical findings:

| Field | Yahoo HK 00001 | Yahoo HK 01113 | AKShare HK 00001 | AKShare HK 01113 | Catalog already has? | Truly fixable? |
|-------|---|---|---|---|---|---|
| bond_payable | "Long Term Debt" only (broader scope) | "Long Term Debt" only | none | none | `akshare:["BOND_PAYABLE"]` (CN code, miss) | NO — Yahoo LT Debt ≠ bonds payable; AKShare HK doesn't break out bonds. Needs PDF spot-check + scope decision. |
| cip | none | none | none | none | none | NO — adapters don't expose CIP separately for HK |
| invest_income | none (only "Investmentsin Associates at Cost" — BS line) | same | "减:投资收益" | "减:投资收益" | `akshare:["INVEST_INCOME"]` (CN code, miss) | **YES — add `by_market.HK.akshare:["减:投资收益"]`. 2 cells.** |
| rd_exp | none | none | none | none | none | NO — adapters don't expose R&D for HK |
| other_cur_assets | none | "Other Current Assets" (already matched) | none | none | `yahoo:["Other Current Assets"]` (already matches 01113) | NO additional fix possible — 00001 Yahoo doesn't expose this line at all (HSBC bank Yahoo schema gap) |
| fv_value_chg_gain | "Financial Assets Designatedas Fair Value Through Profitor Loss Total" (BS, both) | same | none | none | `akshare:["FAIRVALUE_CHANGE_INCOME", "公允价值变动收益"]` | NO — Yahoo exposes BS line not P&L gain; semantic mismatch |
| non_oper_income | "Other Non Operating Income Expenses" (combined) | none | none | "其他收益" | unknown — needs check | MAYBE — inconsistent: 00001 Yahoo combined income+expense; 01113 AKShare 其他收益. Different scope per company. |
| non_oper_exp | none | "Other Operating Expenses" (note: OPERATING not NON-operating) | none | none | unknown | MAYBE — Yahoo "Other Operating Expenses" naming conflicts with non_oper_exp semantic |

### Revised HK-A scope

| Field | Cells closable | Effort | Confidence |
|-------|---------------:|--------|------------|
| invest_income (add `by_market.HK.akshare`) | 2 (both companies) | XS (~30 min) | HIGH — clean AKShare HK alias match |
| Everything else | 0 cells via clean alias | — | structural / semantic mismatch |

**Total realistic HK-A delta: 2 cells**, not 16. The discovery doc's pre-empirical estimate was overoptimistic by ~8x.

### What this means for sub-phase ranking

- **HK-A is no longer the highest-leverage move** — it's now an XS 2-cell win, not a S 16-cell win.
- **LLM-orchestrator wire-in jumps to top priority** — most "missing-candidate" fields are genuinely missing from adapters, so the LLM-supplement path is the only way to close them. CN already proved this works (600519 jumps from 39/56 → 44/56 with LLM supplement). HK 00001/01113 with 13-14 missing-candidate cells per company would benefit even more.
- **HK-B (sample-verified conflict resolution) becomes more attractive in relative terms** — it can close 8 cells (4 fields × 2 companies) which is now the largest source-first-only delta available.
- **HK-C (01113 SGA structural) still XS, still worth doing as a quick signal-quality win.**

### Revised recommendation

1. **HK-A-mini**: invest_income alias (XS, 2 cells, +1 hour to also do as a tiny standalone commit)
2. **LLM-orchestrator wire-in**: highest source of new clean cells (up to +25 P3 per company); requires integrating the existing Phase I-A HK LLM runner into evaluate-company so its hits land in `llm_supplement_present` bucket like CN does
3. **HK-C**: 01113 SGA → not_applicable_terminal (XS, signal quality)
4. **HK-B**: defer until ≥3 HK issuer fixtures (already deferred per original recommendation; reasoning unchanged)
