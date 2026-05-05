# Canonical Unit Reconciliation Spec

> Date: 2026-05-05
> Status: design spec
> Scope: remove false AKShare/Yahoo conflicts caused by provider unit labels while keeping real cross-source value and account-scope disagreements explicit.

## 1. Purpose

The provider baseline period replay proves that Yahoo can cover 11 of the current 15 source-mapped P0/P1 fields for all three validation companies, and AKShare covers 11 of 15 for `600519`. However, the combined slice currently under-reports coverage because reconciliation compares provider unit labels before comparing normalized values.

Example from `600519`:

- AKShare `cash`: `currency=CNY`, `unit=yuan`, `normalized_value=51690610946.5`
- Yahoo `cash`: `currency=CNY`, `unit=raw`, `normalized_value=51690610946.5`

These candidates are semantically equivalent after normalization, but current reconciliation marks them as `conflict` with reason `candidate units differ`. This is a code-level normalization and reconciliation problem, not an API coverage problem.

At the same time, some fields have real value disagreements:

- `600519` `revenue` and `net_profit` differ between AKShare and Yahoo.
- HK `00001` and `01113` balance-sheet and gross-profit values differ between AKShare and Yahoo.

Those must remain explicit conflicts until a later provider-scope/accounting-semantics phase proves which source and field definition should win.

## 2. Goals

This phase must provide:

- A deterministic canonical unit concept for source-mapped money candidates.
- Preservation of provider-reported unit labels for review.
- Reconciliation that treats `CNY yuan` and `CNY raw`, or `HKD HKD` and `HKD raw`, as comparable when normalized values are in the same canonical currency major unit.
- No false `candidate units differ` conflict when:
  - periods match,
  - currencies match,
  - canonical units match,
  - normalized values are equal or within configured tolerance.
- Continued conflicts when normalized values differ beyond tolerance.
- Export behavior that promotes reconciled ambiguous candidates with `equivalent` or `close` reconciliation to `present` while carrying correct value, currency, unit, period, scope, source evidence, and warning metadata.
- Provider baseline replay regression showing that `600519` combined coverage increases after false unit conflicts are removed.

## 3. Non-Goals

This phase does not:

- Add new Turtle fields.
- Add new AKShare or Yahoo aliases.
- Call AKShare, Yahoo, yfinance, PDF parsing, or LLM providers.
- Perform FX conversion between CNY, HKD, and USD.
- Decide which provider is authoritative when normalized values differ.
- Resolve account-scope differences such as `Net Income` vs `净利润` or `Total Revenue` vs `营业收入`.
- Change period-scoped replay selection.
- Promote provider data into canonical facts.

## 4. Design

### 4.1 Unit Model

Keep two separate concepts:

- `unit`: the provider-reported unit label already carried by `SourceInventoryRecord`, such as `yuan`, `HKD`, or `raw`.
- `canonical_unit`: the deterministic normalized unit used for comparison and export, derived from `normalize_money(...).normalized_unit`.

For the current money normalizer, `canonical_unit` is the currency major unit:

| Input context | Currency | Provider unit | Canonical unit | Multiplier |
| --- | --- | --- | --- | ---: |
| `CNY yuan` | `CNY` | `yuan` | `CNY` | 1 |
| `CNY raw` | `CNY` | `raw` | `CNY` | 1 |
| `HKD HKD` | `HKD` | `HKD` | `HKD` | 1 |
| `HKD raw` | `HKD` | `raw` | `HKD` | 1 |
| `USD raw` | `USD` | `raw` | `USD` | 1 |
| `CNY million` | `CNY` | `million` | `CNY` | 1,000,000 |

The existing `MoneyAmount.normalized_unit` already provides the canonical unit value. This phase should reuse that rather than creating an unrelated normalization table.

### 4.2 Mapping Output

`TurtleMappingCandidate` should expose both provider and canonical unit metadata:

- `unit`: provider-reported unit label, preserved for review.
- `canonical_unit`: deterministic comparison unit from money normalization.

`MappedTurtleField` should also expose `canonical_unit` for direct and derived fields. For a single direct candidate, it should copy the candidate's canonical unit. For derived fields, inputs must share currency, period, scope, and canonical unit; provider-reported unit labels may differ if canonical units match.

### 4.3 Reconciliation

Reconciliation should compare metadata in this order:

1. Periods must match.
2. Currencies must match.
3. Canonical units must match.
4. Scopes must match if both sides provide non-unknown scopes.
5. Normalized values are compared with the configured tolerance.

Provider-reported `unit` labels must not cause conflict by themselves once canonical units match.

Expected outcomes:

- Equal normalized values: `equivalent`
- Difference within tolerance: `close`
- Difference beyond tolerance: `conflict`, reason `candidate normalized values differ`
- Missing canonical unit: `blocked` or `conflict` with a clear reason, depending on whether a normalized value exists

### 4.4 Export

The source-first export already treats ambiguous mappings with `equivalent` or `close` reconciliation as `present`. This phase must make that promotion complete:

- Pick a deterministic representative candidate for scalar value metadata.
- Include all reconciled source evidence.
- Export `currency`, `unit`, `canonical_unit`, `period`, and `scope` from the representative candidate.
- Convert the original multi-candidate ambiguity into a warning such as `multiple source candidates reconciled as equivalent`; the promoted `present` item must not retain that ambiguity as an error.

The representative candidate should prefer the catalog primary route when available in a later phase. For this phase, use deterministic source order `akshare`, then `yahoo`, then lexical source name, because the values are already equivalent or close.

### 4.5 Provider Baseline Effect

After this phase, `600519` combined replay should no longer mark equal AKShare/Yahoo fields as conflicts only because one source says `yuan` and the other says `raw`.

Expected `600519` combined behavior:

- These formerly false-conflict fields become present or equivalent-present:
  - `cash`
  - `operating_cash_flow`
  - `total_assets`
  - `total_cur_assets`
  - `total_cur_liab`
  - `total_liabilities`
- These remain real conflicts because normalized values differ:
  - `revenue`
  - `net_profit`
- Single-source fields remain present:
  - `cip`
  - `defer_tax_liab`
  - `financing_cash_flow`
  - `gross_profit`
  - `invest_income`
  - `investing_cash_flow`
- `bond_payable` remains blocked until mapping/source availability is improved.

Expected `00001` and `01113` combined behavior:

- False period conflicts should remain absent.
- Unit-label conflicts should become normalized-value conflicts when values really differ.
- Coverage should not be artificially increased by ignoring value differences.

## 5. Artifacts

Existing artifacts should remain JSON-compatible and gain additive metadata:

- `turtle_mapping.json`
  - candidate `canonical_unit`
  - mapped field `canonical_unit`
- `reconciliation_report.json`
  - reasons distinguish `candidate canonical units differ` from `candidate normalized values differ`
- `extraction_result.json`
  - exported item `canonical_unit`
- `review_summary.json`
  - present/conflict counts reflect canonical-unit reconciliation
- `provider_baseline_period_replay_summary.json`
  - improved `600519` combined coverage

Generated `tmp/` artifacts remain uncommitted.

## 6. Testing Contract

Tests must cover:

- `CNY yuan` and `CNY raw` candidates with equal normalized values reconcile as `equivalent`.
- `HKD HKD` and `HKD raw` candidates with equal normalized values reconcile as `equivalent`.
- Provider-reported units are still visible in mapping artifacts.
- Canonical units are present in mapping and export artifacts.
- Different currencies still conflict.
- Different canonical units still conflict.
- Equal canonical units with different normalized values still conflict.
- Derived fields accept inputs with different provider unit labels when canonical units match.
- Derived fields reject incompatible currencies, and same-currency derivation compatibility uses canonical units rather than provider unit labels.
- Export promotion for `equivalent` ambiguous candidates includes correct value/currency/unit/canonical unit/period/scope and all source evidence.
- Export promotion for reconciled ambiguous candidates clears the original ambiguity error and preserves it as a warning.
- Provider baseline period replay shows `600519` combined coverage improves and no longer reports `candidate units differ` for equal-value fields.
- Default tests do not call external providers.

## 7. Success Criteria

This phase is complete when:

- Code distinguishes provider-reported unit from canonical comparison unit.
- Reconciliation no longer produces false conflicts for same-currency, same-period, same-canonical-unit, same-normalized-value candidates.
- Real AKShare/Yahoo value disagreements remain conflicts.
- `600519` combined period replay improves from the current `6/15` present baseline to at least `12/15` present, with `revenue` and `net_profit` still not silently accepted.
- Full verification passes:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
git diff --check
```
