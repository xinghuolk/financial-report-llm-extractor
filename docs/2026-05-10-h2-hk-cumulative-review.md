# H2/HK Cumulative Review

- Review date: 2026-05-10
- Reviewed range: `0a1e796898b85ddb9d09a04557172d6029e15c07..HEAD`
- Branch at review time: `feature/source-first-roadmap-requirements`
- Review focus: requirement fit, source-first architecture drift, and functional correctness.

## Summary

The change set mostly stays on the current source-first path: provider artifacts remain the primary path, PDF/LLM evidence is still separated, HK `net_profit` is represented as sampled provider semantics proof rather than final per-company PDF evidence, and HK `gross_profit` is not clean-promoted.

However, there are several issues to fix before treating the range as fully aligned:

1. HK `selling_general_administrative` can be blocked by a CN-only derivation path.
2. Provider raw derivation bypasses money normalization and unit multiplier proof.
3. Derived clean-present exports lose `selected_source`, weakening reviewability.

## Findings

### 1. HK SGA is routed through a CN-only derivation

Severity: Medium

Files:

- `field_catalog/turtle_v015_source_mapping_minimal.json`
- `src/financial_report_llm_extractor/structured_sources/mapping.py`

`selling_general_administrative` is globally configured as:

```json
"source_mode": "derived",
"derivation": "akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE"
```

The derivation is valid for CN AKShare records, but `map_source_inventory()` attempts derivation whenever direct mapping is missing, without a market guard. In HK, especially `01113`, this produces mapping `blocked` with:

```text
derivation input not present: akshare:MANAGE_EXPENSE
derivation input not present: akshare:SALE_EXPENSE
```

This is not the intended terminal semantics. For HK `01113`, SGA should remain a stable `source_unavailable` / industry-not-applicable terminal bucket, or use the HK Yahoo market-scoped alias when present and then remain terminal-unverified if provider semantics are unverified. A CN derivation failure should not determine the HK outcome.

Recommended fix:

- Make derivations market-scoped, or add a derivation applicability policy to the mapping catalog.
- For `selling_general_administrative`, apply `akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE` only for CN.
- Ensure HK `01113` reaches `source_unavailable` with the catalog `industry_not_applicable` reason instead of mapping `blocked`.

### 2. Provider raw derivation bypasses deterministic money normalization

Severity: Medium

File:

- `src/financial_report_llm_extractor/structured_sources/mapping.py`

`_resolve_derivation_operand()` turns `provider:RAW` operands into `MappedTurtleField` values using:

```python
value=rec.parsed_numeric_value
normalized_value=rec.parsed_numeric_value
```

This bypasses the normal `normalize_money()` path used by direct candidates. It is correct for the current CN SGA sample only because the records are in raw yuan. If a future provider raw operand uses `million`, `thousand`, `万元`, or another scaled unit, the derived `normalized_value` will be wrong and the unit multiplier proof will be missing.

Recommended fix:

- Reuse `_candidate_from_record()` or the same money normalization path for provider raw operands.
- Preserve `unit_multiplier`, `canonical_unit`, currency proof source, unit proof source, and source evidence in the derived field or its operand audit trail.
- Add a regression test where provider raw derivation uses a scaled unit and verifies normalized output.

### 3. Derived clean-present exports lose selected source

Severity: Low to Medium

Files:

- `src/financial_report_llm_extractor/structured_sources/source_policy.py`
- `src/financial_report_llm_extractor/structured_sources/export.py`

For derived fields without direct candidates, source policy returns `selected_single_source` without a `selected_candidate`. Export only sets `selected_source` when `selected_candidate` exists. As a result, CN derived SGA can export as `status: present` with AKShare source evidence but `selected_source: null`.

This does not change the numeric result, but it weakens source-first reviewability. Review artifacts should be explicit about which provider supplied the operands.

Recommended fix:

- Add provider/source metadata to derived fields, for example `derived_source="akshare"` or structured derivation operand metadata.
- Have export render `selected_source` for single-provider derivations.
- Add a test asserting CN derived SGA exports with `selected_source == "akshare"`.

## Positive Checks

- HK `gross_profit` is not clean-promoted.
- HK `net_profit` keeps `trust_policy_evidence.proof_class == "sampled_pdf_policy_proof"` and `is_final_pdf_evidence == false`.
- `source_evidence`, `trust_policy_evidence`, and `pdf_evidence` remain separated in export artifacts.
- Missing, conflict, PDF-required, and definition-unverified states remain explicit.
- No canonical fact promotion, UI workflow, async workflow, or dependency on the deterministic export pipeline was introduced.

## Verification

Commands run during review:

```bash
uv run pytest tests/test_source_mapping.py tests/test_source_policy.py tests/test_provider_baseline_replay.py tests/test_company_evaluation.py tests/test_phase_hk_c_industry_not_applicable.py -q
uv run pytest -q
uv run ruff check .
uv run mypy src tests
git diff --check 0a1e796898b85ddb9d09a04557172d6029e15c07..HEAD
uv run financial-report-llm-extractor replay-provider-baseline --inventory tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz --inventory-summary tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json --catalog field_catalog/turtle_v015_source_mapping_minimal.json --taxonomy field_catalog/turtle_v015_field_taxonomy.json --out /private/tmp/review_replay_h2
```

Results:

- Focused pytest: `92 passed`
- Full pytest: `548 passed, 1 skipped`
- Ruff: `All checks passed`
- Mypy: `Success: no issues found in 101 source files`
- Diff whitespace check: passed
- Replay: completed for 3 companies

## Overall Assessment

The range is broadly aligned with the source-first roadmap, but not fully clean. The main drift is not a broad architectural detour; it is a catalog/modeling boundary issue: a CN-only derivation is encoded as a global field behavior and leaks into HK. Fixing derivation applicability and making derived operand evidence/selected source explicit should bring this range back into line with the project requirements.
