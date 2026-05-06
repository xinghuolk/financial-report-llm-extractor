# Phase M HK Yahoo Trust Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reviewable HK Yahoo trust policy so sampled annual-report PDF proof can make selected Yahoo HK raw-HKD fields clean present without pretending those policy samples are final company-specific PDF evidence.

**Architecture:** Add a small structured policy fixture and loader under the structured source boundary, then pass the policy into source policy, warning classification, and provider baseline replay. Keep ingestion, chunking, retrieval, LLM transport, and final PDF evidence contracts unchanged.

**Tech Stack:** Python 3.11 standard library, frozen dataclasses, existing pytest suite, existing provider baseline replay artifacts.

---

## Task 1: Add HK Yahoo trust policy fixture and loader

**Files:**

- Create `field_catalog/hk_yahoo_trust_policy.json`
- Create `src/financial_report_llm_extractor/structured_sources/hk_yahoo_trust_policy.py`
- Create `tests/test_hk_yahoo_trust_policy.py`

**Steps:**

- [x] Add fixture schema with top-level `version`, `market`, `provider`, and `rules`.
- [x] Add one rule per field with:
  - `policy_id`
  - `field_id`
  - `classification`
  - `trusted_currency`
  - `trusted_unit`
  - `trusted_unit_multiplier`
  - `allowed_yahoo_raw_fields`
  - `samples`
- [x] For each sample include:
  - `company_id`
  - `provider_ticker`
  - `report_ref`
  - `pdf_page`
  - `statement_name`
  - `statement_line`
  - `reported_currency`
  - `reported_unit`
  - `pdf_value`
  - `pdf_unit_multiplier`
  - `expected_yahoo_raw_value`
  - `yahoo_raw_field`
  - `match_basis`
- [x] Fill documented samples from the roadmap:
  - `00001 revenue`: `280036` HKD million -> `280036000000`
  - `00001 total_cur_assets`: `212743` HKD million -> `212743000000`
  - `00001 total_cur_liab`: `135399` HKD million -> `135399000000`
  - `01113 revenue`: `57935` HKD million -> `57935000000`
  - `01113 total_cur_assets`: `174106` HKD million -> `174106000000`
  - `01113 total_cur_liab`: `39072` HKD million -> `39072000000`
  - `01113 total_assets`: `335392 + 174106` HKD million -> `509498000000`
  - `01113 total_liabilities`: `39072 + 61745` HKD million -> `100817000000`
- [x] Populate real `pdf_page` values from existing quick-validation artifacts or by reusing the project PDF text probe. Do not leave page values as `0`.
- [x] Mark `net_profit` and `gross_profit` as `yahoo_definition_unverified` unless exact PDF line semantics and value proof are added to the fixture in this task.
- [x] Add frozen dataclasses:
  - `HkYahooTrustPolicy`
  - `HkYahooTrustRule`
  - `HkYahooTrustSample`
- [x] Add `load_hk_yahoo_trust_policy(path: Path) -> HkYahooTrustPolicy`.
- [x] Add validation that:
  - top-level market is `HK`
  - provider is `yahoo`
  - `trusted_unit_multiplier == 1`
  - every sample `pdf_page` is a positive integer
  - every sample `statement_line` can be found on `pdf_page` in the existing quick-validation artifact or PDF text probe output
  - every verified sample satisfies `Decimal(pdf_value) * Decimal(pdf_unit_multiplier) == Decimal(expected_yahoo_raw_value)`
  - verified rules have at least one sample
  - sample `yahoo_raw_field` is listed in `allowed_yahoo_raw_fields`
- [x] Add lookup helpers:
  - `rule_for_field(field_id: str) -> HkYahooTrustRule | None`
  - `is_pdf_verified(field_id: str) -> bool`
  - `build_policy_evidence(field_id: str) -> dict[str, object]`

**Tests:**

- [x] `test_load_hk_yahoo_trust_policy_validates_samples`
- [x] `test_hk_yahoo_trust_policy_rejects_bad_multiplier_match`
- [x] `test_hk_yahoo_trust_policy_exposes_verified_and_unverified_classifications`

**Commit:**

- [x] Implemented in final Phase M commit.

---

## Task 2: Apply trust policy inside source policy

**Files:**

- Modify `src/financial_report_llm_extractor/structured_sources/source_policy.py`
- Modify `tests/test_source_policy.py`

**Steps:**

- [x] Import the trust policy dataclasses behind optional typing so source policy remains usable without a policy file.
- [x] Extend `SourcePolicyItem` with `trust_policy_evidence: Mapping[str, object] | None`.
- [x] Include `trust_policy_evidence` in `SourcePolicyItem.to_dict()`.
- [x] Add optional parameter to the source policy builder:

```python
def build_source_policy_report(
    ...,
    hk_yahoo_trust_policy: HkYahooTrustPolicy | None = None,
) -> SourcePolicyReport:
```

- [x] When selected primary candidate is HK Yahoo and the rule is `yahoo_pdf_verified`, verify:
  - field id matches the rule
  - candidate source/provider is Yahoo
  - candidate raw field metadata is present
  - candidate raw field name is allowed by the rule
  - candidate currency is `HKD`
  - candidate canonical unit matches HKD currency normalization
  - candidate unit multiplier is `1`
- [x] If candidate raw field metadata is missing, keep the field in `pdf_required` or `yahoo_definition_unverified`; do not apply trust policy from field id alone.
- [x] If verification succeeds:
  - set `verification_required=False`
  - remove warnings whose only cause is HK Yahoo raw-vs-million policy uncertainty
  - keep unrelated warnings intact
  - attach `trust_policy_evidence`
- [x] Do not apply trust policy to `gross_profit`, `net_profit`, source-unavailable fields, or non-HK markets.
- [x] Do not populate final `Evidence(page/chunk/block/snippet)` from `trust_policy_evidence`.

**Tests:**

- [x] `test_source_policy_marks_hk_yahoo_verified_field_clean_with_trust_policy`
- [x] `test_source_policy_keeps_gross_profit_verification_required_without_definition_proof`
- [x] non-HK / missing raw-field guard coverage
- [x] `test_source_policy_report_serializes_trust_policy_evidence_separately`

**Commit:**

- [x] Implemented in final Phase M commit.

---

## Task 3: Extend HK warning classification

**Files:**

- Modify `src/financial_report_llm_extractor/structured_sources/warning_classification.py`
- Modify `tests/test_warning_classification.py`

**Steps:**

- [x] Add classification buckets:
  - `yahoo_pdf_verified`
  - `yahoo_definition_unverified`
  - `pdf_required`
- [x] When trust policy is provided, classify HK Yahoo fields as:
  - `yahoo_pdf_verified` if rule classification is `yahoo_pdf_verified`
  - `yahoo_definition_unverified` if rule classification is `yahoo_definition_unverified`
  - `pdf_required` when provider value exists but no deterministic rule or trust policy proof exists
- [x] Keep existing Phase L buckets for:
  - `source_policy_resolvable`
  - `mapping_expansion_required`
  - `source_unavailable`
- [x] Ensure `bond_payable`, `cip`, and `invest_income` remain source unavailable for the current fixture.
- [x] Ensure `defer_tax_liab` remains mapping-expansion-first.

**Tests:**

- [x] `test_warning_classification_moves_verified_hk_yahoo_fields_to_yahoo_pdf_verified`
- [x] `test_warning_classification_keeps_gross_profit_definition_unverified`
- [x] `test_warning_classification_keeps_unavailable_fields_unavailable`

**Commit:**

- [x] Implemented in final Phase M commit.

---

## Task 4: Wire trust policy into provider baseline replay

**Files:**

- Modify `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`
- Modify `tests/test_provider_baseline_replay.py`

**Steps:**

- [x] Add optional CLI/replay parameter `--hk-yahoo-trust-policy`.
- [x] Default the path to `field_catalog/hk_yahoo_trust_policy.json` when the file exists under repo root.
- [x] Load the trust policy only for HK slices.
- [x] Pass the policy to `build_source_policy_report()`.
- [x] Pass the policy to warning classification.
- [x] Write `hk_yahoo_trust_policy_report.json` next to existing replay review artifacts for each HK slice.
- [x] Include in replay summary:
  - `yahoo_pdf_verified_fields`
  - `yahoo_definition_unverified_fields`
  - `pdf_required_fields`
- [x] Preserve existing behavior when no trust policy path is provided and no default file exists.

**Tests:**

- [x] `test_provider_replay_loads_default_hk_yahoo_trust_policy_for_hk_slice`
- [x] `test_provider_replay_writes_hk_yahoo_trust_policy_report`
- [x] `test_provider_replay_summary_lists_yahoo_pdf_verified_fields`
- [x] `test_provider_replay_without_policy_preserves_previous_behavior`

**Commit:**

- [x] Implemented in final Phase M commit.

---

## Task 5: Add regression coverage for clean-present behavior

**Files:**

- Modify `tests/test_provider_baseline_replay.py`
- Modify `tests/test_source_review_export.py`
- Modify `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`

**Steps:**

- [x] Add a replay fixture/assertion where HK verified fields become clean present:
  - `revenue`
  - `total_cur_assets`
  - `total_cur_liab`
  - `total_assets` when fixture proof exists for that company/field path
  - `total_liabilities` when fixture proof exists for that company/field path
- [x] Assert `gross_profit` is not clean present unless its rule classification is upgraded to `yahoo_pdf_verified`.
- [x] Assert clean-present export items that used trust policy still do not contain PDF `Evidence`.
- [x] Assert the policy evidence remains available through source policy/replay artifact.
- [x] Update roadmap Phase M status from planned to completed with verification caveat.
- [x] Add a short note to roadmap that `net_profit` remains `yahoo_definition_unverified` unless exact PDF sample proof is later added.

**Tests:**

- [x] Phase M related tests: `116 passed`.
- [x] `uv run ruff check .`
- [x] `uv run mypy src tests`

**Commit:**

- [x] Implemented in final Phase M commit.

## Final Verification

- Phase M focused suite: `116 passed`.
- `uv run ruff check .`: passed.
- `uv run mypy src tests`: passed.
- Full `uv run pytest -v`: `411 passed, 1 skipped, 1 failed`.
- Remaining full-suite failure: `tests/test_source_artifacts.py::test_provider_field_baseline_fixture_replays_compressed_inventory`, caused by pre-existing `akshare_cn_600519_balance_sheet` source artifact hash mismatch.

---

## Implementation Notes

- Use `Decimal` for proof arithmetic; do not use float.
- Keep fixture values as strings to avoid JSON integer precision surprises in downstream tooling.
- Treat `trust_policy_evidence` as review metadata, not extraction evidence.
- Keep source policy optional: existing tests and non-HK replay must work without loading the fixture.
- Preserve Phase K metadata proof fields. Trust policy can clear HK Yahoo verification warnings only after currency/unit/unit_multiplier metadata is already proven.
- Preserve Phase L source-unavailable classifications. Trust policy must not manufacture provider values for missing source fields.
