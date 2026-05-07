# Source Mapping Catalog Expansion Spec

> Date: 2026-05-04
> Status: design spec
> Scope: expand the Turtle P0/P1 source mapping catalog from the offline provider field candidate report without making provider API calls.

## 1. Purpose

PC4 made provider raw-field candidates reviewable from the checked-in AKShare/Yahoo baseline fixture. The next step is to turn the safest candidates into source mapping catalog entries so source-first extraction can cover more Turtle P0/P1 fields.

This phase must not treat the candidate report as an authority. It should promote only deterministic, high-confidence candidates and keep weaker candidates in review artifacts.

## 2. Goals

This phase must provide:

- A review-gated expansion of `field_catalog/turtle_v015_source_mapping_minimal.json`.
- Promotion of strong deterministic candidates from `provider_field_candidate_report.json`.
- No promotion of medium or weak candidates.
- A generated review report that lists promoted candidates, deferred candidates, and fields still without candidates.
- Tests proving the expanded catalog loads, references taxonomy/coverage metadata, and improves candidate-discovery status.
- No AKShare, Yahoo, yfinance, PDF, or LLM calls.

## 3. Non-Goals

This phase does not:

- Automatically promote every candidate.
- Add new provider fixtures.
- Change the Turtle taxonomy or coverage matrix semantics.
- Resolve cross-source value conflicts.
- Run PDF evidence supplement or LLM ambiguity review.
- Expand P2/P3/P4 mappings.

## 4. Inputs

Required local inputs:

- `field_catalog/turtle_v015_field_taxonomy.json`
- `field_catalog/turtle_v015_coverage_matrix.json`
- `field_catalog/turtle_v015_source_mapping_minimal.json`
- `tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz`
- `tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json`

The candidate report is generated from checked-in fixtures with:

```bash
uv run financial-report-llm-extractor discover-provider-fields \
  --taxonomy field_catalog/turtle_v015_field_taxonomy.json \
  --mapping-catalog field_catalog/turtle_v015_source_mapping_minimal.json \
  --inventory tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz \
  --summary tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json \
  --out tmp/runs/provider_field_candidate_discovery \
  --priorities P0,P1
```

## 5. Promotion Policy

Promote a candidate only when all of these are true:

- Field priority is `P0` or `P1`.
- Field status is `catalog_gap` or provider mapping is missing for that source.
- Candidate strength is `strong`.
- Candidate signals include `statement_match` and `period_support`.
- Candidate signals include either `existing_alias` or `exact_text`.
- Candidate source is `akshare` or `yahoo`.
- Candidate raw field name/code does not conflict with an existing alias for a different field in the same source.
- Candidate aliases are not already mapped to the same field in the same source.

Do not promote:

- `medium` or `weak` candidates.
- Candidates with only `keyword_overlap`.
- Candidates for fields whose taxonomy source mode is `pdf_only` or `llm_review`.
- Candidates whose statement type differs from taxonomy.
- Candidates already present in the production mapping catalog.

## 6. Initial Promotion Set

The current candidate report supports this first promotion set:

| field_id | source | aliases |
| --- | --- | --- |
| `bond_payable` | `akshare` | `BOND_PAYABLE` |
| `cip` | `akshare` | `CIP` |
| `defer_tax_liab` | `akshare` | `DEFER_TAX_LIAB` |
| `financing_cash_flow` | `yahoo` | `Financing Cash Flow` |
| `invest_income` | `akshare` | `INVEST_INCOME` |
| `investing_cash_flow` | `yahoo` | `Investing Cash Flow` |

Medium candidates such as receivables, payables, deferred tax assets, borrowing fields, SG&A, R&D, and other current assets remain deferred for manual review or later provider/PDF validation.

## 7. Catalog Update Rules

For each promoted field:

- Add the field id to the matching taxonomy priority list if absent.
- Add a `source_mappings` entry with metadata copied from taxonomy and coverage matrix.
- Preserve existing mappings and alias order.
- Add only promoted source aliases.
- Set `verification_status` to `expected`, not `verified`, unless an existing test already validates the final Turtle field from captured inventory.
- Set `primary_route` to the promoted source route when only one source is promoted.
- Keep `fallback_policy` from taxonomy/coverage conventions.

The production catalog file must remain valid under `load_source_mapping_catalog()`.

## 8. Review Artifact

Create a local generated artifact under `tmp/runs/source_mapping_catalog_expansion/`:

- `source_mapping_expansion_review.json`
- `source_mapping_expansion_review.md`

The review artifact should include:

- promoted fields and aliases,
- deferred medium/weak candidates,
- candidate fields still blocked by missing or conflicting evidence,
- fields with no provider candidates,
- candidate report summary counts before manual promotion.

Generated `tmp/` artifacts are not committed.

## 9. Testing Contract

Tests must cover:

- Strong candidates are selected for promotion.
- Medium/weak candidates are deferred.
- Alias conflicts block promotion.
- Expanded mapping catalog loads and validates.
- Candidate discovery against the expanded catalog reduces `catalog_gap_fields`.
- The review artifact records promoted and deferred candidates.
- No test calls provider APIs or network.

## 10. Success Criteria

This phase is complete when:

- `field_catalog/turtle_v015_source_mapping_minimal.json` includes the first strong candidate promotion set.
- Candidate discovery can be rerun locally and shows fewer catalog gaps than PC4.
- Review artifacts make remaining medium/weak candidates explicit.
- Full verification passes:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
git diff --check
```
