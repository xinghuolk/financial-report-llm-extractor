# Phase M3 HK net_profit Raw Field Semantics Sample Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that Yahoo HK `Net Income Common Stockholders` is the correct provider raw semantic for Turtle `net_profit`.

**Architecture:** Reuse the existing HK Yahoo trust policy path. Keep sampled policy proof in `field_catalog/hk_yahoo_trust_policy.json`, keep source selection in `field_catalog/turtle_v015_source_mapping_minimal.json`, and validate behavior through policy, closure, and provider replay tests. The PDF samples prove provider raw field semantics; they are not final per-export PDF evidence.

**Tech Stack:** Python 3.11 standard library, JSON catalogs, existing pytest suite, captured provider/PDF fixtures.

---

## Task 1: Lock The Trusted Yahoo Raw Field

**Files:**

- Modify: `tests/test_source_mapping_catalog.py`
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`

**Completed steps:**

- [x] Add a regression assertion that `net_profit` Yahoo aliases are limited to `Net Income Common Stockholders`.
- [x] Add a regression assertion that Yahoo semantic primary is `Net Income Common Stockholders`.
- [x] Keep broader Yahoo rows as related context only:
  - `Net Income`
  - `Net Income From Continuing Operation Net Minority Interest`
- [x] Update the minimal mapping catalog accordingly.

## Task 2: Promote net_profit In HK Yahoo Trust Policy

**Files:**

- Modify: `tests/test_hk_yahoo_trust_policy.py`
- Modify: `field_catalog/hk_yahoo_trust_policy.json`

**Completed steps:**

- [x] Update policy tests to expect `net_profit` as `yahoo_pdf_verified`.
- [x] Require `allowed_yahoo_raw_fields == ("Net Income Common Stockholders",)`.
- [x] Add the `00001` proof sample:
  - page `134`
  - row `Profit attributable to ordinary shareholders`
  - PDF value `11841`
  - unit multiplier `1000000`
  - Yahoo raw value `11841000000`
- [x] Add the `01113` proof sample:
  - page `70`
  - row `Profit attributable to shareholders`
  - PDF value `10847`
  - unit multiplier `1000000`
  - Yahoo raw value `10847000000`
- [x] Keep definition-unverified schema tests on `gross_profit`, which still owns that bucket.

## Task 3: Update HK Closure And Replay Expectations

**Files:**

- Modify: `tests/test_hk_15_field_closure.py`
- Modify: `tests/test_provider_baseline_replay.py`

**Completed steps:**

- [x] Update HK closure fixture policy so `net_profit` is `yahoo_pdf_verified`.
- [x] Assert closure categorizes `net_profit` as `yahoo_pdf_verified` in direct closure tests.
- [x] Add `net_profit` to `EXPECTED_HK_YAHOO_VERIFIED_FIELDS`.
- [x] Remove `net_profit` from `EXPECTED_HK_YAHOO_DEFINITION_UNVERIFIED_FIELDS`.
- [x] Update exact HK 15-field closure expectation to `10/15` clean present.
- [x] Keep `gross_profit` in the non-clean path.

## Task 4: Verification

**Completed focused run:**

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_hk_yahoo_trust_policy.py tests/test_hk_15_field_closure.py tests/test_provider_baseline_replay.py tests/test_source_mapping_catalog.py -q
```

Result:

```text
69 passed
```

**Recommended before commit:**

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_hk_yahoo_trust_policy.py tests/test_hk_15_field_closure.py tests/test_provider_baseline_replay.py tests/test_source_mapping_catalog.py tests/test_warning_classification.py tests/test_source_policy.py -q
```

## Handoff Notes

- Do not add `Net Income` back to HK `net_profit` trusted raw fields.
- The `01113` sample proves why `Net Income` is too broad: it maps to `11,133,000,000`, while the shareholder-attributable annual-report row is `10,847,000,000`.
- Do not promote `gross_profit` in this phase.
- After this phase, HK baseline may show `10/15 clean_present`, but Phase M4 must make the proof class explicit as sampled provider semantics proof.
- Do not use this plan as a pattern for per-company PDF value matching.
