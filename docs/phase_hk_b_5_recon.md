# Phase HK-B.5: acct_payable PDF Spot-Check + Promotion

> Date: 2026-05-11
> Scope: 6 HK issuers × `acct_payable` field
> Outcome: Yahoo HK `Accounts Payable` confirmed = PDF pure Trade payables
> across all 6 issuers; promotion via market_policy + trust policy lands all
> 6 HK in clean_present. +3 HK clean cells (00001/01113/09987).

## Background

HK-B.1 originally locked `acct_payable` at 3 clean / 3 conflict
(`docs/phase_hk_b_recon.md`). The recon's recommended next step was a
sample-scoped policy after PDF spot-check, but flagged
`provider-provider agreement is not proof of catalog semantics` per drift §177.
This phase performed the PDF spot-check across all 6 HK issuers and found
that the picture is cleaner than the recon assumed.

## PDF Spot-Check Findings

| Company | Reporting | Yahoo `Accounts Payable` | PDF disclosure | Match |
|---|---|---:|---:|---|
| 00001 (HSBC) | HKD | 22,632,000,000 | Note 27 (a) **Trade payables** 22,632 HKDM (page 244) | ✓ |
| 01113 (CK Asset) | HKD | 3,607,000,000 | Note 18 **Creditors** 3,607 HKDM (page 164) — property-co convention | ✓ |
| 01810 (Xiaomi) | RMB | 98,280,585,000 | Note 30 **Trade payables** 98,280,585 K RMB | ✓ |
| 02498 | RMB | 475,825,000 | Note 32 **Trade payables** 475,825 K RMB | ✓ |
| 06862 | RMB | 1,796,362,000 | Note 27 **貿易應付款項** 1,796,362 K RMB (page 227) | ✓ |
| 09987 (Yum China) | USD | 801,000,000 | Notes **Accounts payable** $801M USD (page 175) | ✓ |

**All 6 HK Yahoo Accounts Payable values exactly match the corresponding PDF
pure trade payables line** (using each issuer's preferred terminology:
"Trade payables" / "Creditors" / "Accounts payable"). The scope is consistently
*pure trade* — NOT combined with accruals or other payables.

### Critical discovery: 01113

The HK-B recon had marked 01113 as a likely terminal because the English PDF
text extract didn't surface a "Trade payables" line. The correct line is named
**"Creditors"** (Note 18, page 164) — a property-co accounting convention used
in HK/UK GAAP for non-COGS-driven trade payable cycles. Yahoo's value
3,607,000,000 HKD matches PDF Creditors 3,607 HKDM exactly, with a formal
aging analysis disclosed in the same note.

### AKShare divergence (informational)

AKShare `应付帐款` for the 3 conflict cases:

| Company | AKShare | Yahoo (PDF-confirmed) | AKShare interpretation |
|---|---:|---:|---|
| 00001 | 73.23B HKD | 22.63B HKD (pure) | Different aggregation — banking-issuer specific; not matched to any single PDF line |
| 01113 | 17.08B HKD | 3.61B HKD (pure Creditors) | Close to (3,607 + 14,101) = 17,708 HKDM combined Creditors+Accruals (3.6% short) |
| 09987 | 14.95B *labeled HKD* | 0.80B *labeled HKD* | AKShare appears to return combined "Accounts payable and other current liabilities" ($2,080M USD) in RMB without rebasing currency label |

In all 3 conflict cases, AKShare returns a broader/different scope than PDF
pure trade payables. Yahoo's scope is correct.

## Yahoo HK Currency Label Quirk + Allowlist Mitigation

Yahoo HK adapter hardcodes `currency=HKD` for every HK issuer in the inventory
record (`source_inventory_fetch.py`), regardless of the issuer's actual
reporting currency. Raw values themselves are the issuer's reported figures —
e.g. 98,280,585,000 RMB stays labeled HKD, $801M USD stays labeled HKD.
Cumulative review (2026-05-11) flagged this as a High-severity data-quality
risk: promoting via the trust policy makes the inventory's HKD label the
exported currency, so for the non-HKD issuers a clean_present claim would
emit a wrong-currency value downstream.

For 09987 (Yum China, USD reporter) the wrong-currency claim would be a NEW
regression introduced by HK-B.5 — the field was previously `unresolved_conflict`
(no claim made). For 01810/02498/06862 (RMB issuers), the wrong HKD label
is pre-existing: those records were already clean_present via AKShare with
the same HKD hardcode in `PandasAkshareClient`, so HK-B.5 doesn't worsen
them. For 00001/01113 (HKD issuers), the label is correct.

### Phase HK-B.5.1: adapter-level currency detection (forward-going)

Phase HK-B.5.1 lands the architectural fix at the adapter layer:
`source_inventory_fetch.HK_ISSUER_FINANCIAL_CURRENCY` maps each known HK
issuer to its financial-statement reporting currency (PDF spot-check is
the source of truth). `_fetch_yahoo_for_company` and `_run_fetch_source_inventory`
(CLI) both consult this map so new live fetches stamp inventory records
with the issuer's actual reporting currency — not the trading-market HKD
default.

The map is intentionally explicit for the 6 spot-checked issuers (PDF
verified); unknown HK issuers fall back to HKD (pre-fix behavior, no
silent regression for cohorts that haven't been audited yet). A future
sub-phase can replace the hardcoded map with live detection via
`yfinance.Ticker.info.financialCurrency` once the live-fetch path is
robustly tested.

This is a forward-going fix only. Existing fixtures still carry the
pre-Phase-HK-B.5.1 HKD labels for 01810/02498/06862/09987; Phase HK-B.5.2
(below) is required to backfill them and re-promote 09987.

### Phase HK-B.5.2: fixture backfill + trust policy multi-currency + 09987 re-promote (implemented 2026-05-11)

Three coordinated changes close the currency-label loop:

1. **Fixture backfill**: 1616 records in the HK 6-extension fixtures
   (`provider_field_baseline_hk_llm_6_extension/{01810,02498,06862,09987}/source_inventory.jsonl.gz`
   plus aggregated) rewritten to stamp the issuer's actual reporting
   currency on every record. Source-of-truth is the same
   `HK_ISSUER_FINANCIAL_CURRENCY` map used by the adapter (Phase HK-B.5.1).

2. **Trust policy multi-currency schema**: `HkYahooTrustRule` gains an
   optional `additional_trusted_currencies: tuple[str, ...] | None`
   (default None preserves single-currency behavior). `accepted_currencies()`
   returns `(trusted_currency, *additional_trusted_currencies)`.
   `_can_apply_hk_yahoo_trust_policy` switches from `==` to `in`
   membership check.

3. **acct_payable rule extended**: `additional_trusted_currencies =
   ["CNY", "USD"]` + 09987 added to `pdf_verified_company_ids` + 09987
   sample restored. All 6 HK issuers now promote acct_payable to
   `clean_present`.

**Honest coverage adjustment**: backfill exposed that pre-Phase-HK-B.5.2
"clean" status for several other fields on non-HKD issuers (revenue,
net_profit, etc.) relied on the wrong-HKD-label accidentally triggering
HKD-scoped trust policies. With currency now correct, those fields
revert to `unresolved_conflict` until separately PDF-verified for CNY/USD
reporters and extended to multi-currency. Net baseline shifts:

  - 01810: 32 → 30 (acct_payable kept clean via multi-currency rule;
    revenue + net_profit lost accidental HKD promotion)
  - 02498: 32 → 30 (same pattern)
  - 06862: 33 → 31 (same pattern)
  - 09987: 29 → 28 (acct_payable gained via promotion; net loss of 1
    accidentally-promoted field via HKD trust policy)
  - 00001 / 01113 / 600519: unchanged (HKD or CN reporters; no
    currency-label mismatch existed)

This is the "coverage mirage" correction — the previous numbers were
inflated by a known adapter bug. Future work to extend revenue,
net_profit, etc. trust rules with PDF-verified multi-currency support
can claw the coverage back honestly per drift §177.

### Phase HK-B.5 short-term mitigation: per-issuer allowlist

Pending Phase HK-B.5.2, the per-issuer allowlist on both the trust
policy rule and the provider semantics rule is the active mitigation:

- `HkYahooTrustRule.pdf_verified_company_ids: tuple[str, ...] | None`
  (`hk_yahoo_trust_policy.py`) — when set, the rule only fires for listed
  issuers.
- `ProviderSemanticsRule.pdf_verified_company_ids: tuple[str, ...] | None`
  (`provider_semantics.py`) — parallel check; both must allow the issuer
  before promotion fires.
- `_can_apply_hk_yahoo_trust_policy` + `_apply_provider_semantics_promotion`
  now thread `company_id` and call `rule.applies_to_company(company_id)`
  before promoting.

The `acct_payable` rule sets
`pdf_verified_company_ids = ("00001", "01113", "01810", "02498", "06862")`,
excluding 09987. The 09987 PDF match is documented in recon (this file)
but doesn't appear in the trust policy `samples` since samples reflect
active promotion scope.

The architectural Yahoo HK adapter fix (detect issuer reporting currency
and stamp inventory accordingly) is recorded as a §7 roadmap follow-up.
Once the adapter is fixed, 09987 can be added to the allowlist and
01810/02498/06862 will have correct RMB labels.

## Implementation

**Three catalog changes** (no source code changes needed):

1. **`field_catalog/provider_raw_semantics_hk.json`** — added Yahoo
   `acct_payable` rule with `classification: provider_semantics_sample_verified`,
   `allowed_as_primary: true`, raw_field_name=`Accounts Payable`.

2. **`field_catalog/hk_yahoo_trust_policy.json`** — added
   `hk_yahoo_raw_hkd_pdf_verified:acct_payable` rule with 6 PDF samples
   (one per HK issuer, citing PDF page + statement_line + pdf_value +
   reported_currency).

3. **`field_catalog/turtle_v015_source_mapping_minimal.json`** — added
   `source_policy` to `acct_payable` with HK market_policy
   (`primary_route: yahoo_direct`, `on_conflict: select_primary_require_pdf`).
   No CN market_policy (CN behavior unchanged — 600519 stays clean via
   AKShare).

The promotion mechanism is the existing source_policy chain:
- `_primary_candidate` picks Yahoo for HK (per new market_policy)
- `_can_apply_hk_yahoo_trust_policy` validates yahoo candidate + trust
  policy rule + provider_semantics rule all align
- `_apply_hk_yahoo_trust_policy` clears the conflict_classifications
- Result: all 6 HK issuers land `clean_present` with `selected_source=yahoo`.

## Test Updates

| Test file | Change |
|---|---|
| `test_phase_hk_b_acct_payable.py` | All 6 HK cases now expect `clean_present` / `selected_source="yahoo"` / yahoo value. Previously 3 clean (selected_source=akshare) + 3 unresolved_conflict. |
| `test_phase_hk_llm_2_supplement_merge.py` | Baseline counts bumped for 3 affected companies: 00001 (28→29), 01113 (29→30), 09987 (29→30). Total counts also +1. |
| `test_provider_baseline_replay.py` | Added `acct_payable` to `EXPECTED_HK_YAHOO_VERIFIED_FIELDS` (8→9) and to `expected_clean_by_company` for 00001 (26→27) and 01113 (28→29). |
| `test_hk_yahoo_trust_policy.py` | Verified samples count 14→20 (+6 from acct_payable). |

## Coverage Impact (after currency-label allowlist mitigation)

- Matrix verification: 35/62 → **36/62** verified (acct_payable promoted).
- HK 00001/2025 source-first: 28/56 → **29/56** clean (50% → 52%). HKD reporter.
- HK 01113/2025 source-first: 29/56 → **30/56** clean (52% → 54%). HKD reporter.
- HK 09987/2024 source-first: 29/56 **unchanged** — acct_payable held in
  `unresolved_conflict` despite PDF match (USD reporter; Yahoo HK adapter
  HKD hardcode would produce wrong-currency claim).
- HK 01810/02498/06862 source-first: unchanged (already clean, just
  selected_source flipped akshare → yahoo; HKD label on RMB raw value
  is pre-existing adapter debt unchanged by HK-B.5).
- CN 600519/2024: unchanged (no CN market_policy — AKShare path preserved).
- Total: **+2 HK clean cells** (down from naive +3 once 09987 was excluded
  via per-issuer allowlist to prevent wrong-currency clean claim).

## What This Replicates

Same methodology as H2.1/H2.2 CN SGA promotion:
- Multi-issuer sample verification (6 HK issuers vs 4 CN issuers for H2.2)
- PDF spot-check per issuer with explicit page + statement_line cite
- Catalog rule with named samples (not silent broad promotion)
- Tests lock the post-promotion shape

The drift §177 standard is met: ≥2 issuer samples + PDF spot-check + named
evidence. The HK Yahoo `Accounts Payable` semantic is now PDF-verified across
the full local validation cohort.

## What's Next

- **HK-B.6 (`fix_assets`)**: similar pattern — 3 clean / 3 conflict per HK-B.2 lock.
  Yahoo Net PPE has known ROU asset / scope ambiguity per HKFRS 16. A
  PDF spot-check across all 6 HK issuers would clarify whether the same
  promotion path applies. Higher cost (each PDF needs careful note-level
  reading of fixed-asset breakdowns).
- **HK-B.7 (`accounts_receiv`) and HK-B.8 (`gross_profit`)**: recon already
  identified these as conservative — `accounts_receiv` all 6 HK conflict,
  `gross_profit` 4 conflict + 2 terminal_unverified. PDF check would need
  to determine if Yahoo Accounts Receivable also matches pure Trade
  receivables consistently.
