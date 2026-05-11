# Source Policy Conflict Resolution Spec

> Date: 2026-05-05
> Status: design spec
> Scope: distinguish provider field semantics, source priority, and review requirements so AKShare/Yahoo conflicts do not either hide real disagreements or unnecessarily lower source-first coverage.

## 1. Purpose

Canonical-unit reconciliation removed false conflicts caused only by provider unit labels such as `CNY yuan` vs `CNY raw`. The remaining provider baseline replay conflicts are different. They are not simple unit bugs:

- `600519` `revenue` compares AKShare `营业收入 / OPERATE_INCOME` with Yahoo `Total Revenue`, while AKShare also contains `营业总收入 / TOTAL_OPERATE_INCOME`, which matches Yahoo exactly.
- `600519` `net_profit` compares AKShare `净利润 / NETPROFIT` with Yahoo `Net Income`, while AKShare also contains `归属于母公司股东的净利润 / PARENT_NETPROFIT`, which matches Yahoo exactly.
- HK `00001` and `01113` balance-sheet totals show a near-constant Yahoo/AKShare ratio of about `1.1071499745`, suggesting FX-like conversion or reporting-currency metadata risk rather than random field mismatch.

The current pipeline has only two practical choices after reconciliation: promote equivalent candidates or export conflicts. That is too coarse. It correctly avoids silent acceptance, but it makes combined source coverage worse than the best single reliable route and does not explain why conflicts happened.

This phase adds explicit field semantics and source policy. It must keep true conflicts reviewable while allowing a primary source candidate to be exported with warnings and PDF verification requirements when the catalog defines that source as the intended route.

## 2. Goals

This phase must provide:

- Field semantic metadata for source mappings, including the exact accounting concept intended by each Turtle field.
- Per-field, per-market source policy that defines primary routes and cross-check routes.
- A deterministic conflict classifier that distinguishes:
  - `semantic_mismatch`
  - `fx_like_ratio`
  - `metadata_currency_suspected`
  - `normalized_value_conflict`
  - `missing_source_candidate`
  - `single_source_unverified`
  - `currency_metadata_required`
- A source policy resolver that can select a primary candidate without pretending cross-source conflicts disappeared.
- Export metadata that preserves:
  - selected primary source value,
  - all conflicting/cross-check candidates,
  - conflict classification,
  - warnings,
  - verification requirements.
- Provider baseline replay summaries that report selected source coverage separately from unresolved review obligations.
- Regression coverage for `600519`, `00001`, and `01113` using checked-in fixtures only.

## 3. Non-Goals

This phase does not:

- Call AKShare, Yahoo, yfinance, PDF parsers, or LLM providers.
- Perform automatic FX conversion.
- Promote any provider value to a canonical fact.
- Resolve all Turtle field semantics globally.
- Add broad PDF extraction.
- Change period selection.
- Hide real normalized-value disagreements.
- Require PDF evidence to exist before source policy can identify which fields need PDF verification.

## 4. Field Semantics Decisions

The implementation slice must make these current 15-field catalog decisions explicit.

### 4.1 A-share `revenue`

`revenue` means operating revenue, not total operating revenue.

For A shares:

- Primary source: AKShare `OPERATE_INCOME` / `营业收入`.
- Cross-check source: Yahoo `Total Revenue`, but it may align with AKShare `TOTAL_OPERATE_INCOME` rather than `OPERATE_INCOME`.
- If Yahoo matches `TOTAL_OPERATE_INCOME` and differs from `OPERATE_INCOME`, classify as `semantic_mismatch`.
- Export may select AKShare `OPERATE_INCOME` with warning and PDF verification requirement.

### 4.2 A-share `net_profit`

`net_profit` means profit attributable to parent-company shareholders.

For A shares:

- Primary source: AKShare `PARENT_NETPROFIT` / `归属于母公司股东的净利润`.
- Cross-check source: Yahoo `Net Income` or `Net Income Common Stockholders`.
- AKShare `NETPROFIT` / `净利润` is a related but different semantic variant. It must not be selected for `net_profit` when `PARENT_NETPROFIT` is available.
- If AKShare `NETPROFIT` differs while `PARENT_NETPROFIT` matches Yahoo, classify the previous conflict as catalog semantic mismatch, not provider disagreement.

This decision follows Turtle investment-analysis usage: the profit measure used for shareholder return and valuation should be attributable profit, not broad consolidated net profit including non-controlling interests.

### 4.3 HK balance-sheet totals

For HK `total_assets`, `total_cur_assets`, `total_cur_liab`, and `total_liabilities`:

- Primary source: AKShare HK raw statement rows.
- Cross-check source: Yahoo standardized balance-sheet fields.
- If Yahoo and AKShare share period and nominal currency but differ by a stable near-constant ratio across multiple fields in the same company/slice, classify as `fx_like_ratio` and `metadata_currency_suspected`.
- Do not convert values.
- Export may select AKShare as the primary candidate only when the selected AKShare candidate has proven statement-level currency/unit metadata, such as AKShare HK metadata join evidence. If the selected primary candidate itself has suspected currency/unit metadata, the field must remain unresolved and require currency metadata or PDF evidence before selection. If the suspicion applies only to the Yahoo cross-check candidate, export may select AKShare with warning and PDF verification requirement.

### 4.4 HK `gross_profit`

For HK `gross_profit`:

- Primary source: AKShare HK `毛利` when present.
- Cross-check source: Yahoo `Gross Profit`.
- If the value difference follows the same company-level FX-like ratio as balance-sheet fields, classify as `fx_like_ratio`.
- If it does not, classify as `semantic_mismatch` or `normalized_value_conflict`.
- Export should require PDF verification in either case.

### 4.5 Yahoo-only HK fields

For HK fields currently covered only by Yahoo, such as revenue, net profit, and cash-flow fields:

- Yahoo may provide a selected source candidate.
- The item must carry a `single_source_unverified` warning unless a source policy marks Yahoo as accepted for that exact field and market.
- The item should require PDF evidence in review/export profiles that need annual-report support.

## 5. Catalog Additions

Each source mapping entry may gain an additive `source_policy` object:

```json
{
  "semantic_concept": "profit attributable to parent-company shareholders",
  "semantic_variants": {
    "akshare": {
      "primary": ["PARENT_NETPROFIT", "归属于母公司股东的净利润"],
      "related": ["NETPROFIT", "净利润"]
    },
    "yahoo": {
      "primary": ["Net Income", "Net Income Common Stockholders"]
    }
  },
  "market_policies": {
    "CN": {
      "primary_route": "akshare_direct",
      "cross_check_routes": ["yahoo_direct"],
      "on_conflict": "select_primary_require_pdf"
    },
    "HK": {
      "primary_route": "akshare_direct",
      "cross_check_routes": ["yahoo_direct"],
      "on_conflict": "select_primary_require_pdf"
    }
  },
  "verification_requirement": "pdf_required_on_conflict"
}
```

The schema is intentionally additive. Existing catalog consumers must continue to load entries that do not define `source_policy`.

## 6. Conflict Classification

The classifier consumes mapped field candidates and reconciliation outcomes. It must not mutate source candidates.

Classification rules:

1. `missing_source_candidate`: field has no candidates.
2. `semantic_mismatch`: candidates correspond to known related semantic variants for the same Turtle field.
3. `metadata_currency_suspected`: candidates claim the same currency, but the source is known to derive currency from ticker/market defaults rather than provider statement metadata.
4. `fx_like_ratio`: at least three same-company same-period fields from the same provider pair have nearly identical ratios beyond tolerance.
5. `normalized_value_conflict`: normalized values differ and no more specific semantic or FX-like explanation is available.
6. `single_source_unverified`: exactly one source candidate exists and the source policy requires additional evidence.
7. `currency_metadata_required`: the candidate that would otherwise be selected lacks proven statement-level currency/unit metadata.

The ratio detector should be conservative:

- It only groups fields in the same `(company_id, period, candidate source pair)`.
- It ignores ratios when either normalized value is missing or zero.
- It only emits `fx_like_ratio` when at least three fields share a ratio within a tight relative tolerance, such as `0.1%`.
- It does not infer a conversion direction or converted value.

## 7. Source Policy Resolution

The resolver runs after mapping and reconciliation and before source-first export.

Inputs:

- `TurtleMappingResult`
- `ReconciliationReport`
- source mapping catalog policies
- optional company/market context from provider baseline replay
- conflict classification report

Outputs:

- selected candidate per field when policy allows selection,
- `selection_status`, such as:
  - `selected_primary`
  - `selected_single_source`
  - `unresolved_conflict`
  - `missing`
  - `blocked`
- warnings and review flags,
- source candidates retained for audit.

Rules:

- Equivalent or close reconciled fields remain present as before.
- If a conflict matches a field policy with `on_conflict = "select_primary_require_pdf"`, select the primary route candidate and attach conflict warnings.
- If no primary candidate exists, do not select a cross-check candidate unless policy explicitly allows it.
- If selected from a single Yahoo-only HK route, attach `single_source_unverified` unless policy explicitly says source-only is allowed.
- If policy is absent, preserve existing conservative conflict behavior.

## 8. Export And Coverage Semantics

Existing `status == "present"` alone is not enough to describe source-policy results. This phase must keep the current export status vocabulary compatible and add metadata fields instead of adding a new status.

Required additive fields:

- `selection_status`
- `verification_required`
- `conflict_classifications`
- `selected_source`
- `review_notes`

Review summaries must distinguish:

- `present_fields`: accepted source values with no unresolved blocker.
- `selected_with_warnings_fields`: selected primary values that still need review/PDF evidence.
- `unresolved_conflict_fields`: no policy-safe selection.
- `fields_requiring_pdf_evidence`: selected or unresolved fields that need PDF support.

Top-level provider baseline coverage must report both:

- `selected_count`: fields with a policy-selected or reconciled value.
- `clean_present_count`: fields present without warnings or verification requirements.

This avoids overstating quality while also avoiding the current problem where cross-check conflicts erase useful primary-source coverage.

## 9. Expected Provider Baseline Effect

Using the checked-in provider baseline fixture:

- `600519`:
  - `revenue` selected from AKShare `OPERATE_INCOME`, warning `semantic_mismatch`, PDF verification required.
  - `net_profit` selected from AKShare `PARENT_NETPROFIT`, expected to reconcile with Yahoo `Net Income` once catalog alias priority is corrected.
  - `bond_payable` remains blocked/missing unless a valid source candidate exists.
- `00001` and `01113`:
  - HK balance-sheet totals selected from AKShare with `fx_like_ratio` or `metadata_currency_suspected` warnings only when AKShare statement metadata proves the selected value's currency/unit; otherwise those fields remain unresolved and require currency metadata or PDF evidence.
  - HK Yahoo-only fields remain selected candidates with `single_source_unverified` warnings unless covered by improved AKShare aliases.
  - `gross_profit` requires PDF verification; automatic acceptance is not allowed.

The exact selected counts may change as aliases are corrected, but the replay must make the reason for every remaining warning or conflict explicit.

## 10. Testing Contract

Tests must cover:

- `600519 revenue` classifies `OPERATE_INCOME` vs Yahoo `Total Revenue` as `semantic_mismatch` when `TOTAL_OPERATE_INCOME` matches Yahoo.
- `600519 net_profit` maps `PARENT_NETPROFIT` before `NETPROFIT` for the Turtle `net_profit` field.
- HK stable ratios across at least three fields classify as `fx_like_ratio`.
- HK ratio classification does not run on one-off differences.
- A policy-selected conflict keeps all source candidates and warnings.
- Fields with no policy preserve existing conservative conflict behavior.
- Yahoo-only HK fields can be selected with `single_source_unverified` and PDF evidence required.
- Provider baseline replay exposes selected counts separately from clean present counts.
- Default tests use local fixtures only and make no provider, PDF, or LLM calls.

## 11. Success Criteria

This phase is complete when:

- Source mapping catalog entries can express field semantics and market-specific source policy.
- `600519` `revenue` is explained by semantic policy rather than raw normalized-value conflict.
- `600519` `net_profit` uses the `PARENT_NETPROFIT` primary semantic and reconciles with Yahoo `Net Income` when both sources provide matching values.
- HK balance-sheet conflicts are classified as FX-like or metadata-currency suspected where the stable-ratio evidence exists.
- Combined replay no longer lowers useful primary-source coverage solely because a cross-check source disagrees.
- Review artifacts still preserve every disagreement and verification requirement.
- Full verification passes:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
git diff --check
```
