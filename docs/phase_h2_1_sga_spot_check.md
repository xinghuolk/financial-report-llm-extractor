# Phase H2.1: 600519/2024 SGA PDF Spot-Check

> Date: 2026-05-09
> PDF: `downloads/cn_stocks/600519/annual/2024_年度报告.pdf`
> Period: 2024-12-31

## PDF values (consolidated income statement notes 43, 44)

| Line | 2024 (CNY) | 2023 (CNY) |
|------|-----------:|-----------:|
| 销售费用 | 5,639,300,059.49 | 4,648,613,585.82 |
| 管理费用 | 9,315,650,060.38 | 9,729,389,252.31 |
| **Sum (销售 + 管理)** | **14,954,950,119.87** | 14,378,002,838.13 |

Extracted via `pdftotext -layout ... | grep -E "销售费用|管理费用"`. The values appear in two locations (notes summary + main income statement detail) — both consistent.

## AKShare values (from fixture, 600519/2024-12-31)

| Raw field | Value (CNY) |
|-----------|------------:|
| `SALE_EXPENSE` | 5,639,300,059.49 |
| `MANAGE_EXPENSE` | 9,315,650,060.38 |
| **AKShare derivation** (MANAGE_EXPENSE + SALE_EXPENSE) | **14,954,950,119.87** |

## Yahoo SGA (single field)

| Raw field | Value (CNY) |
|-----------|------------:|
| `Selling General And Administration` | 10,362,839,420.99 |

## Comparison

| Source | SGA value (CNY) | vs PDF Sum |
|--------|----------------:|------------|
| PDF (销售 + 管理) | 14,954,950,119.87 | — |
| **AKShare derivation** | **14,954,950,119.87** | **EXACT match** ✓ |
| Yahoo SGA | 10,362,839,420.99 | −30.7% (~4.6B short) |

## Decision

**Branch A: PROMOTE.**

AKShare `MANAGE_EXPENSE + SALE_EXPENSE` matches PDF (销售费用 + 管理费用) to the cent for 600519/2024 — same proof gate that H2 used for revenue/operating_profit.

Yahoo SGA differs by ~30%, suggesting Yahoo's SGA scope excludes some items (possibly bundles selling expense differently, or excludes certain management overhead categories common to Chinese P&L convention). Yahoo SGA stays `provider_semantics_unverified` per H2 documentation; not used as primary.

## Catalog actions (Task 4)

- Add `derivation: "akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE"` to `selling_general_administrative` entry
- Update `source_policy.market_policies.CN.on_conflict` to `"select_primary_require_pdf"` (was `preserve_conflict` per H2 Task 4)
- Replace existing `provider_semantics_unverified` rule for `MANAGE_EXPENSE → SGA` (added in H2 Task 4) with a `provider_semantics_sample_verified` rule using a composite raw_field_name (e.g., `"MANAGE_EXPENSE+SALE_EXPENSE"`) OR add the verified rule alongside if that schema fits cleaner
- Update `tests/test_phase_h2_validation.py::test_phase_h2_sga_and_da_have_unverified_rules` to expect ONLY D&A as unverified (SGA now verified)

## Single-sample acknowledgment (per spec Open Questions)

This spot-check verified ONE company (600519). Other CN issuers may have different SGA reporting conventions (e.g., manufacturing companies may include 研发费用 separately; banks have different opex structures). Phase H2.2 candidate: extend sample-verification to ≥3 CN companies before relying on this rule for production-grade coverage claims.
