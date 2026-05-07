# Phase M2 HK 15-Field Terminal Buckets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every HK 15-field replay item either clean present or assigned to a stable, reviewable closure bucket before expanding to the full 33-field P0/P1 denominator.

**Architecture:** Reuse the implemented `hk_15_field_closure.py` report layer. The closure report consumes source-first export, warning classification, candidate discovery, and HK Yahoo trust policy, then writes HK-specific JSON/Markdown artifacts from provider baseline replay.

**Tech Stack:** Python 3.11 standard library, frozen dataclasses, JSON/Markdown artifacts, existing pytest suite, captured provider fixtures.

---

## Implementation Status

This phase has already been implemented in the current branch through these commits:

1. `feat: add hk 15-field closure report`
2. `feat: write hk 15-field closure replay artifact`
3. `test: lock defer tax liability mapping review`
4. `test: tighten defer tax liability mapping review`
5. `docs: record hk 15-field closure follow-up`

The plan below records what has landed and how to verify it.

---

## Task 1: HK Closure Contract

**Files:**

- Implemented: `src/financial_report_llm_extractor/structured_sources/hk_15_field_closure.py`
- Tested: `tests/test_hk_15_field_closure.py`

**Completed steps:**

- [x] Define `HK_15_FIELD_IDS` with the current 15-field denominator.
- [x] Define closure categories:
  - `clean_present`
  - `selected_with_warnings`
  - `yahoo_pdf_verified`
  - `yahoo_definition_unverified`
  - `pdf_required`
  - `mapping_expansion_required`
  - `source_unavailable`
- [x] Add `Hk15FieldClosureItem`.
- [x] Add `Hk15FieldClosureReport`.
- [x] Add `build_hk_15_field_closure_report(...)`.
- [x] Add `write_hk_15_field_closure_artifacts(...)`.
- [x] Add unit tests for:
  - remaining gap classification
  - not applying Yahoo policy to missing fields
  - not applying Yahoo policy to Akshare-selected fields

---

## Task 2: Provider Replay Integration

**Files:**

- Implemented: `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`
- Tested: `tests/test_provider_baseline_replay.py`

**Completed steps:**

- [x] Build HK 15-field closure report for HK slices.
- [x] Write `hk_15_field_closure_report.json`.
- [x] Write `hk_15_field_closure_report.md`.
- [x] Expose artifact paths:
  - `hk_15_field_closure_report`
  - `hk_15_field_closure_markdown`
- [x] Add replay regression coverage for exact HK closure buckets.

---

## Task 3: Net Profit And Gross Profit Terminal Reasons

**Files:**

- Implemented: `field_catalog/hk_yahoo_trust_policy.json`
- Implemented: `src/financial_report_llm_extractor/structured_sources/hk_yahoo_trust_policy.py`
- Tested: `tests/test_hk_yahoo_trust_policy.py`
- Tested: `tests/test_hk_15_field_closure.py`

**Completed steps:**

- [x] Keep `net_profit` as `yahoo_definition_unverified`.
- [x] Add `definition_status_reason` for `net_profit`.
- [x] Add `required_proof` for `net_profit`.
- [x] Keep `gross_profit` as `pdf_required`.
- [x] Add `definition_status_reason` for `gross_profit`.
- [x] Add `required_proof` for `gross_profit`.
- [x] Ensure neither field is promoted to `yahoo_pdf_verified` without explicit PDF row semantics proof.

---

## Task 4: Defer Tax Liability Mapping Expansion Lock

**Files:**

- Implemented: `tests/test_source_mapping_expansion.py`
- Reflected in: `tests/test_hk_15_field_closure.py`

**Completed steps:**

- [x] Lock `defer_tax_liab` as `mapping_expansion_required`.
- [x] Preserve candidate source visibility for Yahoo.
- [x] Assert AKShare candidate is already mapped.
- [x] Assert Yahoo candidate is not strong enough for direct promotion.

---

## Task 5: Verification

**Focused verification run:**

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_hk_15_field_closure.py tests/test_provider_baseline_replay.py tests/test_hk_yahoo_trust_policy.py tests/test_warning_classification.py -q
```

Result:

```text
36 passed
```

**Recommended final verification before committing future edits:**

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); uv run ruff check .
```

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); uv run mypy src tests
```

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); uv run pytest -v
```

Known caveat from Phase M verification: full pytest may still fail on the pre-existing `akshare_cn_600519_balance_sheet` fixture hash mismatch unless that fixture is repaired separately.

---

## Current HK 15-Field Closure State

`clean_present`:

1. `cash`
2. `financing_cash_flow`
3. `investing_cash_flow`
4. `operating_cash_flow`
5. `revenue`
6. `total_assets`
7. `total_cur_assets`
8. `total_cur_liab`
9. `total_liabilities`

`yahoo_definition_unverified`:

1. `net_profit`

`pdf_required`:

1. `gross_profit`

`mapping_expansion_required`:

1. `defer_tax_liab`

`source_unavailable`:

1. `bond_payable`
2. `cip`
3. `invest_income`

---

## Handoff Notes

- Do not create a second terminal bucket module; use `hk_15_field_closure.py`.
- Do not promote `net_profit` or `gross_profit` without annual-report row semantics proof.
- Do not promote `defer_tax_liab` from weak Yahoo candidate evidence.
- Phase N can now start from a stable 15-field baseline.
