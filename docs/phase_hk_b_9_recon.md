# Phase HK-B.9: Multi-Currency Rule Generalization Validation

> Date: 2026-05-12
> Scope: 3 newly-added HK issuers (00392 / 02669 / 03320), all CNY reporters,
> different sectors (utilities / property services / pharmaceutical)
> Outcome: Multi-currency trust rule architecture generalizes — 2 of 3 new
> issuers add to existing allowlists (00392 across 4 fields, 03320 across 2);
> 02669 deferred due to systematic Yahoo-PDF discrepancy.

## Why this phase

Phase HK-B.5 → .8 built multi-currency HK trust rules using the same 6 HK
issuer cohort (00001/01113/01810/02498/06862/09987). The schema
(`additional_trusted_currencies` + `pdf_verified_company_ids`) was correct
by construction for the 6 verified issuers, but its generalization to new
HK issuers was untested. Phase HK-B.9 validates by running the standard
new-company workflow (`docs/new-company-analysis-workflow.md`) against 3
fresh HK companies in sectors not previously tested.

## Method

1. Live AKShare + Yahoo fetch via `scripts/run-fetch-source-inventory.sh`
2. Full `evaluate-company` pipeline **with `PDF_PATH` + `LLM_CONFIG`**
   (caveat: workflow doc was authored mid-phase after the LLM step was
   initially missed — see `docs/new-company-analysis-workflow.md`)
3. PDF spot-check per company for: revenue / net_profit / acct_payable
   / accounts_receiv (the 4 most-promoted fields in existing trust rules)
4. Compare PDF disclosed value vs Yahoo provider value
5. Add to allowlist only when match within rounding (drift §177)

## Cohort

| Ticker | Issuer | Sector | Reporting currency | New to cohort |
|---|---|---|---|---|
| 00392 | Beijing Enterprises | utilities / conglomerate | CNY (2024 functional currency change HKD→RMB) | ✓ |
| 02669 | China Overseas Property Services | property services | CNY | ✓ |
| 03320 | China Resources Pharmaceutical | pharmaceutical | CNY | ✓ |

Existing 6 HK cohort sectors: banking (00001), property (01113), tech
(01810/02498), F&B (06862/09987). New 3 expand into utilities, property
services, pharmaceutical.

## Source-first + LLM coverage (full pipeline)

| Company | source-first clean | +LLM supplement | unresolved | terminal | Total (clean + LLM) |
|---|---:|---:|---:|---:|---:|
| 00392 | 31 | 9 | 14 | 2 | **40/56 (71%)** |
| 02669 | 29 | 6 | 19 | 2 | **35/56 (63%)** |
| 03320 | 30 | 8 | 16 | 2 | **38/56 (68%)** |

Numbers are in line with existing 6 HK cohort (post-HK-B.8): 35-40 total.
Multi-currency rules + LLM supplement generalize without modification.

## PDF spot-check results

Method: extract PDF text via `pdftotext -layout`, grep for the field's
line item, compare against Yahoo raw_value in the inventory fixture.

| Company | Field | PDF line | PDF value | Yahoo value | Match |
|---|---|---|---|---:|---|
| 00392 | revenue | Note 5 Revenue | 84,064,089 K RMB | 84,064,089,000 CNY | ✓ EXACT |
| 00392 | net_profit | Profit attributable to shareholders | 5,123,085 K RMB | 5,123,085,000 CNY | ✓ EXACT |
| 00392 | acct_payable | Trade payables | 3,379,844 K RMB | 3,379,844,000 CNY | ✓ EXACT |
| 00392 | accounts_receiv | Trade receivables (Note 26) | 5,134,785 K RMB | 5,134,785,000 CNY | ✓ EXACT |
| 02669 | revenue | REVENUE (Note 5) | 14,023,767 K RMB | 14,112,544,000 CNY | ✗ +88.8M (0.63%) |
| 02669 | net_profit | (see below) | — | 1,514,296,000 CNY | ✗ near-match |
| 02669 | acct_payable | Trade payables (Note 28) | 2,424,928 K RMB | 2,460,897,000 CNY | ✗ +35.9M (1.48%) |
| 02669 | accounts_receiv | Trade receivables (Note 22) | 2,595,032 K RMB | 2,630,264,000 CNY | ✗ +35.2M (1.36%) |
| 03320 | revenue | 收益 Revenue (Note 4) | 257,673,256 K RMB | 257,673,256,000 CNY | ✓ EXACT |
| 03320 | net_profit | Equity shareholders of the Company | 3,350,857 K RMB | 3,350,857,000 CNY | ✓ EXACT |
| 03320 | acct_payable | 貿易應付款項 (Note a) | 40,062,416 K RMB | 58,786,432,000 CNY | ✗ Yahoo broader |
| 03320 | accounts_receiv | 貿易應收款項 | 83,694,249 K RMB | 100,547,852,000 CNY | ✗ Yahoo broader |

### Notable per-company findings

**00392 Beijing Enterprises (utilities)**: All 4 spot-checked fields EXACT
match. Eligible for ALL 4 existing trust rule allowlists (revenue /
net_profit / acct_payable / accounts_receiv). Net new clean cells:
+3 (revenue + net_profit move from single_source_unverified to clean;
acct_payable moves from normalized_value_conflict to clean; accounts_receiv
already clean via reconciliation, gains explicit trust policy attribution).

**02669 China Overseas Property Services**: All spot-checked fields have a
**systematic ~0.5-1.5% Yahoo-PDF discrepancy**. PDF Revenue 14,023.8M vs
Yahoo 14,112.5M — Yahoo consistently slightly higher. Possible causes
(not investigated):
- Yahoo data source uses a slightly different fiscal close cut
- Yahoo includes other operating income that PDF Revenue line excludes
- Restated figures pulled by Yahoo but not yet in PDF version we have

Per drift §177, **do NOT add 02669 to any allowlist**. The discrepancy is
not rounding (rounding < 0.1% typically). Coverage stays as-is (LLM
supplement still handles P3 pdf_only fields, source-first clean reflects
non-promoted state).

**03320 China Resources Pharmaceutical**: revenue + net_profit EXACT match;
acct_payable + accounts_receiv have **material Yahoo broader-scope**
discrepancies (47% AP, 20% AR). Yahoo likely aggregates "Trade and other
payables/receivables" while PDF disclosure separates "Trade payables/
receivables" as a Note (a) sub-line within a broader BS aggregate.

Decision: add to revenue + net_profit allowlist only. AP/AR stay excluded;
they fall through to the deterministic-candidate path or PDF-required
terminal.

## Allowlist updates

### Add 00392 to existing trust rules

```diff
revenue:
  pdf_verified_company_ids: [..., "00392"]
  + 00392 sample (PDF Note 5)

net_profit:
  pdf_verified_company_ids: [..., "00392"]
  + 00392 sample (PDF Profit attributable to shareholders)

acct_payable:
  pdf_verified_company_ids: [..., "00392"]
  + 00392 sample (PDF Trade payables)

accounts_receiv:
  pdf_verified_company_ids: [..., "00392"]
  + 00392 sample (PDF Trade receivables Note 26)
```

### Add 03320 to selected trust rules

```diff
revenue:
  pdf_verified_company_ids: [..., "03320"]
  + 03320 sample (PDF 收益 Note 4)

net_profit:
  pdf_verified_company_ids: [..., "03320"]
  + 03320 sample (PDF Equity shareholders of the Company)
```

### Skip 02669 entirely (document why)

No allowlist additions for 02669. Recon doc records the spot-check pattern
so a future iteration can investigate the systematic Yahoo-PDF discrepancy
(possibly an issuer-specific data quality issue, possibly a Yahoo data
source idiosyncrasy).

## Coverage impact (post-HK-B.9 catalog update)

| Company | Pre-HK-B.9 source-first clean | Post-HK-B.9 | Delta |
|---|---:|---:|---:|
| 00392 | 31 | 34 | +3 |
| 02669 | 29 | 29 | 0 (deferred) |
| 03320 | 30 | 32 | +2 |
| **Total** | 90 | 95 | **+5 cells** |

Trust policy verified samples: 58 → 58 + 4 (00392) + 2 (03320) = **64**.

## Cohort expansion summary

| Cohort size before | Cohort size after | Sectors represented |
|---:|---:|---|
| 6 HK | 9 HK | banking, property (residential), tech, F&B, **+ utilities, property services, pharmaceutical** |

Multi-currency trust rule architecture confirmed to generalize across HK
issuer sectors. 2 of 3 new issuers contribute to existing allowlists
without rule changes. 1 of 3 (02669) reveals a Yahoo data quality nuance
worth tracking but not blocking.

## Follow-up

1. **02669 Yahoo-PDF discrepancy investigation**: 0.6-1.5% systematic
   higher Yahoo values across 4 spot-checked fields. Worth a dedicated
   recon to determine if it's a data-source quirk (Yahoo restated vs PDF
   audited) or an issuer-specific reporting boundary.
2. **03320 Trade payable/receivable broader scope**: pharmaceutical
   distributors often have very high "other receivables" (rebate
   receivables, government subsidy receivables). Yahoo conflates these
   into AP/AR aggregate. A future Phase HK-B.10 could examine if other
   pharma HK issuers show the same pattern.
3. **Add 02669/03320/00392 to HK_ISSUER_FINANCIAL_CURRENCY map**: done in
   the previous commit (Phase HK-B.5.1 follow-up).
4. **Workflow standardization**: `docs/new-company-analysis-workflow.md`
   captures the standard 6-step process; future HK additions follow it.

## Phase HK-B.9 follow-up investigation (2026-05-12)

Timeboxed deep-dive into the 02669 / 03320 discrepancies flagged above.
Outcome: both are **real architectural limits**, not catalog bugs. Drift
§177 enforcement correctly excluded them via allowlist; no catalog change.

### 02669 — Yahoo data quality issuer-level quirk

Cross-checked Yahoo's `Gross Accounts Receivable` (2,878,532 K) vs PDF
Note 22(a) `Trade receivables` gross (2,827,771 K) = +50.8M diff. Net
side: Yahoo 2,630,264 K vs PDF 2,595,032 K = +35.2M (1.4%).

Yahoo's impairment differs from PDF too (Yahoo -248,268 vs implied
PDF -232,739). So both gross AND impairment are slightly broader than
PDF — Yahoo data vendor uses a slightly different methodology for
property-services companies, likely includes some sub-category PDF
Note 22 treats separately. Revenue side: Yahoo +88,777 (0.63%); cost
side: Yahoo +77,351 (0.66%). Pattern consistent: Yahoo is ~0.5-1.5%
broader than PDF reported lines across **all** spot-checked items.

**Not a sector pattern** (other property cos like 01113 match cleanly).
**Not a fiscal-cut issue** (PDF is audited Dec 31, Yahoo likely same).
Most plausible: Yahoo data vendor has a 02669-specific data feed
difference. Without access to Yahoo's source-data contract docs, the
exact cause cannot be pinned. The honest catalog state: **02669
permanently excluded from allowlists** until data source clarified.

### 03320 — Pharma sector AP/AR scope ambiguity

PDF disclosure structure:
- BS line "Trade and other receivables (Note 23)": 93,929,934 K
- Note 23(a) "Trade receivables (pure)": 83,694,249 K
- Yahoo "Accounts Receivable": **100,547,852 K** (larger than BOTH)

Yahoo (100.5B) > PDF Trade+Other (93.9B) > PDF pure Trade (83.7B).
Yahoo is **6.6B larger than even the combined "Trade and other"** —
Yahoo aggregates something beyond what PDF reports under "Trade and
other receivables", possibly:
- Related-party receivables (separate BS line in PDF)
- Other current financial assets
- Bills receivable (subset of trade receivables broken out separately)

For Trade payables side, Yahoo (58.8B) sits **between** PDF pure Trade
(40.1B) and PDF Trade+Other (80.7B): roughly midway. So for AP, Yahoo
includes some "other" but not all "other" — granular scope inside
PDF Note 26's sub-categories that Yahoo selectively aggregates.

**Pharma sector hypothesis**: distributors like 03320 have large
"government subsidy receivables", "rebate receivables", "promotional
discount receivables" — categories specific to pharmaceutical
distribution business model. Yahoo's pharma-specific data feed may
aggregate them differently than the issuer reports.

**Not verifiable without sector cohort**: need ≥2 more pharma HK
issuers to confirm if this is sector-pattern or 03320-specific.
For now: **03320 stays in revenue + net_profit allowlist; excluded
from acct_payable / accounts_receiv allowlist**. Future Phase
HK-B.10 (if pharma cohort expands) can test the sector hypothesis.

### Architectural takeaway

Both edge cases reveal: **the allowlist mechanism does its job**.
Without it, naive broad promotion would silently mis-attribute data
for 02669 and 03320 on AP/AR fields. The PDF spot-check + per-issuer
gating successfully caught both edge cases before catalog corruption.

The investigation itself was an `S` (~30-45 min) effort that produced
2 documented limitations + 1 sector hypothesis for future expansion.
No catalog change; no test changes. Phase HK-B.9 closed as architecturally
sound with documented exceptions.
