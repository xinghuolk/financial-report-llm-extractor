# Phase H0: Null-as-Zero Source Policy Spec

> Date: 2026-05-08
> Status: Draft
> Roadmap phase: Bucket 1 (precedes Phase H/I)

## Goal

Allow source mapping to declare that a provider's null value for a field means "explicit zero" (e.g., the company genuinely has no debt), so the field is promoted to clean_present with value 0 rather than blocked.

Resolves 600519 `bond_payable`, `st_borr`, `lt_borr` from `source_policy_resolvable` to `clean_present`. Expected impact: 600519 27/33 → 30/33.

## Problem

AKShare returns records with `source_status: present`, `raw_value: null` for known-zero items (e.g., Maotai has zero short-term debt, zero long-term debt, zero bonds). Current behavior:

1. `_candidate_from_record` calls `normalize_money(str(None), ...)` → `MoneyNormalizationError`
2. Candidate marked with errors
3. `_map_direct_field` finds no valid candidates → `status="blocked"`
4. `warning_classification` correctly tags as `source_policy_resolvable`, but the field stays non-clean

The architecture is correctly surfacing the issue. The fix is to add an opt-in policy declaration that null-from-provider equals explicit zero for declared fields.

## Design

### 1. Schema extension

Add `null_means_zero: bool` to `SourceMappingEntry` (default `False`). Loaded from the JSON catalog under each source_mapping entry.

When `null_means_zero == True` and a provider record has:
- `source_status == "present"` (not missing or extraction_failed)
- `parsed_numeric_value is None` AND `raw_value` is None / "null" / empty

Then `_candidate_from_record` produces a zero-valued candidate:
- `value = Decimal("0")`
- `normalized_value = Decimal("0")`
- `currency = record.currency` (preserve provider metadata)
- `unit = record.unit`
- `unit_multiplier = Decimal("1")` (any value works since value is 0)
- No errors
- A new review note `null_interpreted_as_zero` so this is auditable downstream

### 2. Apply to 3 fields

Update `field_catalog/turtle_v015_source_mapping_minimal.json` for `bond_payable`, `st_borr`, `lt_borr`:
- Add `"null_means_zero": true`
- Add inline note explaining the rule

### 3. Review note propagation

`null_interpreted_as_zero` should appear in the export item's `review_notes` so future audit can trace which fields were promoted via this policy.

This means the warning_classification still recognizes the policy effect — fields with `null_interpreted_as_zero` should NOT trigger `pdf_verification_required` based on review notes alone. Verify this doesn't regress.

## Out of Scope

- Auto-detecting "this company has no debt" without explicit catalog declaration. (Too risky — null could mean undisclosed for other fields.)
- Applying to assets fields (only liabilities/borrowings get this treatment in this phase).
- Cross-source agreement check (if Yahoo returns a non-zero value and AKShare returns null, the conflict logic still applies; this policy only fires when null is the ONLY value and no contradicting source exists).

## Verification

### New tests

`tests/test_mapping.py` (or new test file):

1. `test_null_record_with_null_means_zero_produces_zero_candidate` — unit test: feed a record with raw_value=None and entry.null_means_zero=True; expect candidate with value=0, no errors, review note `null_interpreted_as_zero`.

2. `test_null_record_without_null_means_zero_is_blocked` — regression: same record, entry.null_means_zero=False (default); expect candidate with errors.

`tests/test_provider_baseline_replay.py`:

3. Update 600519 `expected_clean` to include `bond_payable`, `st_borr`, `lt_borr` (was `source_policy_resolvable`). Update count assertion.

4. Verify `warning_classification` no longer lists these 3 in `source_policy_resolvable` (or, that the bucket is empty for 600519).

### Catalog tests

`tests/test_catalog_consistency.py`: existing invariants should still pass. No new invariant needed for this — `null_means_zero` is internal to source_mapping.

### Full suite

```bash
uv run pytest -v
uv run ruff check .
```

Expected: 445+ tests pass.

## Implementation Steps

1. Add `null_means_zero: bool = False` field to `SourceMappingEntry` dataclass.
2. Update `load_source_mapping_catalog` to read it from JSON (default False).
3. Modify `_candidate_from_record` in `mapping.py` to accept an entry parameter and apply the policy when applicable.
4. Update `_map_direct_field` to pass entry into `_candidate_from_record`.
5. Add `null_interpreted_as_zero` review note to the candidate, then propagate through `MappedTurtleField` → `SourceFirstExportItem`.
6. Update 3 source_mapping JSON entries with `null_means_zero: true`.
7. Add unit tests.
8. Update replay test assertions.
9. Verify warning_classification handles the review note correctly (doesn't flip the field into pdf_verification_required).

## Expected Coverage Result

| Company | Before | After |
|---------|--------|-------|
| 600519 | 27/33 | 30/33 |
| 00001 | 20/33 | 20/33 (no change) |
| 01113 | 21/33 | 21/33 (no change) |

Remaining 600519 non-clean: `revenue`, `operating_profit`, `selling_general_administrative` (Phase H deterministic PDF verification candidates).
