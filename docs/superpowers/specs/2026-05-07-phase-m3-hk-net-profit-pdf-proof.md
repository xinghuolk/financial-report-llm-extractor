# Phase M3: HK net_profit PDF Proof Spec

> Date: 2026-05-07
> Status: Implemented
> Roadmap phase: Phase M3

## Goal

Promote HK `net_profit` from `yahoo_definition_unverified` to `yahoo_pdf_verified` only when the Yahoo raw field matches the annual-report row semantics for profit attributable to shareholders.

This phase intentionally does not expand to the full 33-field P0/P1 denominator. It tightens the current HK 15-field baseline first.

## Decision

For HK `net_profit`, the trusted Yahoo raw field is:

```text
Net Income Common Stockholders
```

The broader Yahoo fields remain unsafe as direct proof for Turtle `net_profit`:

```text
Net Income
Net Income From Continuing Operation Net Minority Interest
```

Reason: in the `01113` 2025 fixture, `Net Income` is `11,133,000,000`, while the annual report row `Profit attributable to shareholders` is `10,847` HKD million. The correct match is `Net Income Common Stockholders`, also `10,847,000,000`.

## PDF Proof Samples

### `00001`

- PDF: `downloads/hk_stocks/00001/annual/2025_annual_en.pdf`
- Page: `134`
- Statement: `Consolidated Income Statement`
- Row: `Profit attributable to ordinary shareholders`
- PDF value: `11,841`
- Unit: `HKD million`
- Yahoo raw field: `Net Income Common Stockholders`
- Yahoo raw value: `11,841,000,000`
- Match: `11,841 * 1,000,000 = 11,841,000,000`

### `01113`

- PDF: `downloads/hk_stocks/01113/annual/2025_annual_en.pdf`
- Page: `70`
- Statement: `Consolidated Income Statement`
- Row: `Profit attributable to shareholders`
- PDF value: `10,847`
- Unit: `HKD million`
- Yahoo raw field: `Net Income Common Stockholders`
- Yahoo raw value: `10,847,000,000`
- Match: `10,847 * 1,000,000 = 10,847,000,000`

## Required Behavior

1. `field_catalog/hk_yahoo_trust_policy.json` must classify `net_profit` as `yahoo_pdf_verified`.
2. The HK Yahoo trust policy must include the two PDF proof samples above.
3. `allowed_yahoo_raw_fields` for `net_profit` must be limited to `Net Income Common Stockholders`.
4. `field_catalog/turtle_v015_source_mapping_minimal.json` must select `Net Income Common Stockholders` as the Yahoo primary semantic variant for `net_profit`.
5. `Net Income` and `Net Income From Continuing Operation Net Minority Interest` may remain related context, but must not be primary or trusted raw fields for HK policy promotion.
6. HK combined replay should move from `9/15` clean present to `10/15` clean present.
7. `gross_profit` remains non-clean; this phase must not promote it.

## Acceptance Criteria

1. `load_hk_yahoo_trust_policy()` reports `net_profit` as `yahoo_pdf_verified`.
2. The policy exposes two `net_profit` samples, one for `00001` and one for `01113`.
3. Provider replay puts `net_profit` into HK Yahoo verified fields.
4. HK 15-field closure puts `net_profit` into `clean_present`.
5. HK 15-field closure keeps `gross_profit` in `pdf_required`.
6. Focused tests pass.

## Verification

Focused verification:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_hk_yahoo_trust_policy.py tests/test_hk_15_field_closure.py tests/test_provider_baseline_replay.py tests/test_source_mapping_catalog.py -q
```

Expected:

```text
69 passed
```
