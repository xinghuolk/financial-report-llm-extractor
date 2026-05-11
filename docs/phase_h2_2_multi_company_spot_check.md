# Phase H2.2 Sub-A: Multi-Company PDF Spot-Check

> Date: 2026-05-10
> Companies: 300750 (CATL — battery), 601919 (COSCO Shipping — shipping), 688008 (Hygon — semiconductor)
> Period: 2025-12-31 (latest annual; 2025 PDFs locally available)
> Promotion fields: revenue, operating_profit, capital_expenditures, interest_paid_cash, selling_general_administrative
> Method: live `real_source_validation` against AKShare for 3 new tickers, captured to `tmp/runs/h2_2_real_validation/`; PDF values via `pdftotext -layout downloads/cn_stocks/<TICKER>/annual/2025_年度报告.pdf`.

## Per-company × per-field matrix

### 300750 (CATL — battery manufacturing) / 2025-12-31

| Field | AKShare raw_field | AKShare value (CNY) | PDF value (CNY) | Match? |
|-------|-------------------|---------------------|-----------------|--------|
| revenue | OPERATE_INCOME | 423,701,834,000.00 | 423,701,834 千元 = 423,701,834,000 | ✓ EXACT |
| operating_profit | OPERATE_PROFIT | 89,518,636,000.00 | 89,518,636 千元 = 89,518,636,000 | ✓ EXACT |
| capital_expenditures | CONSTRUCT_LONG_ASSET | 42,344,558,000.00 | 42,344,558 千元 = 42,344,558,000 | ✓ EXACT |
| interest_paid_cash | PAY_INTEREST_COMMISSION | (None) | N/A | not applicable (battery mfr; no interest paid line) |
| SGA derivation | MANAGE+SALE | 11,666,741,000 + 3,735,118,000 = 15,401,859,000 | 11,666,741 + 3,735,118 = 15,401,859 千元 = 15,401,859,000 | ✓ EXACT |

### 601919 (COSCO Shipping) / 2025-12-31

| Field | AKShare raw_field | AKShare value (CNY) | PDF value (CNY) | Match? |
|-------|-------------------|---------------------|-----------------|--------|
| revenue | OPERATE_INCOME | 219,503,805,222.70 | 219,503,805,222.70 | ✓ EXACT |
| operating_profit | OPERATE_PROFIT | 42,039,041,074.21 | 42,039,041,074.21 | ✓ EXACT |
| capital_expenditures | CONSTRUCT_LONG_ASSET | 25,015,551,614.56 | 25,015,551,614.56 | ✓ EXACT |
| interest_paid_cash | PAY_INTEREST_COMMISSION | (None) | N/A | shipping company; no interest paid in standard CN cash flow lines |
| SGA derivation | MANAGE+SALE | 8,243,469,490.23 + 825,422,692.68 = 9,068,892,182.91 | same arithmetic from PDF | ✓ EXACT |

### 688008 (Hygon — semiconductor) / 2025-12-31

| Field | AKShare raw_field | AKShare value (CNY) | PDF value (CNY) | Match? |
|-------|-------------------|---------------------|-----------------|--------|
| revenue | OPERATE_INCOME | 5,456,316,783.63 | 5,456,316,783.63 | ✓ EXACT |
| operating_profit | OPERATE_PROFIT | 2,321,777,105.55 | 2,321,777,105.55 | ✓ EXACT |
| capital_expenditures | CONSTRUCT_LONG_ASSET | 265,828,735.88 | 265,828,735.88 | ✓ EXACT |
| interest_paid_cash | PAY_INTEREST_COMMISSION | (None) | N/A | semi co; no interest paid line |
| SGA derivation | MANAGE+SALE | 526,287,844.89 + 120,228,658.51 = 646,516,503.40 | same arithmetic from PDF | ✓ EXACT |

## Aggregate

- **5 fields × 3 companies = 15 cells**: 12 EXACT matches; 3 N/A (PAY_INTEREST_COMMISSION absent for non-financial issuers — architecturally correct, not regression).
- **0 mismatches** — none of the 3 issuers' AKShare values diverged from PDF.
- **Combined with H2/H2.1 600519 baseline**: 4 sample companies × 4 always-applicable fields = 16 EXACT match samples; PAY_INTEREST_COMMISSION still single-sample (600519 only) because non-financial CN issuers don't report it.

## Decision per field (multi-company sample)

| Field | Sample companies | Decision |
|-------|------------------|----------|
| revenue | 600519 + 300750 + 601919 + 688008 | Promote stays — 4-company sample-verified across food, battery, shipping, semi |
| operating_profit | 600519 + 300750 + 601919 + 688008 | Promote stays — same 4-company coverage |
| capital_expenditures | 600519 + 300750 + 601919 + 688008 | Promote stays — same 4-company coverage |
| selling_general_administrative (derivation) | 600519 + 300750 + 601919 + 688008 | Promote stays — same 4-company coverage |
| interest_paid_cash | 600519 only | **Single-sample limitation persists** — non-financial issuers don't report PAY_INTEREST_COMMISSION. Future Phase H2.3 candidate: include a CN bank/finance issuer where this field is non-null. |

## Methodology note

- AKShare 2025 data fetched 2026-05-10 via `real_source_validation` against live AKShare (akshare 1.18.60).
- PDFs are `2025_年度报告.pdf` published Q1 2026 by each issuer. Both AKShare and PDF reflect the same FY2025 annual filing.
- 300750 PDF reports values in 千元 (thousand yuan); AKShare reports raw yuan. Conversion (multiply 千元 by 1000) confirms EXACT equality. Other 2 issuers report PDF in raw yuan; direct comparison.
- All sums (`MANAGE_EXPENSE + SALE_EXPENSE`) computed from per-component AKShare values; PDF reports the components separately (no PDF formal "SGA" single-line on these issuers, consistent with CN P&L convention).

## Next steps (Task 3)

Append per-company samples to `field_catalog/provider_raw_semantics_cn.json` for each H2/H2.1 promoted rule (revenue, operating_profit, capital_expenditures, SGA derivation). Each rule's `samples[]` array goes from 1 entry (600519) to 4 entries (+ 300750, 601919, 688008). PAY_INTEREST_COMMISSION rule unchanged (no new applicable issuers).
