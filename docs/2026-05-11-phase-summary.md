# Phase Summary — Source-First Financial Report Extractor

> Date: 2026-05-11
> Branch: `feature/source-first-roadmap-requirements` @ `856a1a7`
> Scope: snapshot of the project at the natural inflection point after
> Phases HK-LLM-2/C + HK-B.1-.4 locked. Intended as a TOC into the
> authoritative roadmap (`docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`),
> not a replacement.

## TL;DR

- **Pivot complete**: PDF-first LLM extractor → source-first
  (AKShare/Yahoo → reconciliation → source policy → PDF/LLM supplement).
- **Catalog**: 15 → **56 fields** (P0:22 + P1:11 + P2:9 + P3:14).
- **Coverage**: CN 600519/2024 **79%** (44/56 with LLM); 6 HK companies
  **57–70%** with LLM, all regression-locked.
- **Discipline**: 587 tests, ruff + mypy clean, drift §177 followed
  (no silent promotions, sample-verified rules require PDF spot-check).
- **§7 branch completion criteria**: 5/5 met. Branch is mergeable.

## 1. Timeline By Wave

The repo went from bootstrap to current state in **12 calendar days** (2026-04-30
→ 2026-05-11, 317 commits, ~26/day average). Phases collapsed into 6 waves:

| Wave | Dates | Phases | Outcome |
|------|-------|--------|---------|
| **1. Foundation** | 04-30 → 05-02 | bootstrap, Phase A (mapping artifacts), Phase B (artifact hardening), Phase C (AKShare contract) | Frozen dataclass core; PDF ingestion/chunking/retrieval; provider artifact store; AKShare/Yahoo adapter skeletons. |
| **2. HK Provider Semantics** | 05-07 → 05-08 | Phase M2–M5 (HK 15-field terminal closure, Yahoo trust policy, defer_tax_liab proof, gross_profit terminal) | HK Yahoo trust scope established via sample-verified rule; gross_profit + defer_tax_liab terminal. Architecturally honest "unverified" buckets accepted over forced promotion. |
| **3. Catalog Expansion** | 05-08 → 05-09 | Phase N0–N4 (consistency gate + 15 → 33 → 44 fields), Phase I-C/I-C.1 (12 P3 text-mode + whitespace fix → 56 fields) | Catalog reached 56 fields; cross-file JSON consistency gate (`test_catalog_consistency.py`); P3 LLM hit rate 33/84 (39%) across 6 HK companies. |
| **4. LLM & PDF Buckets** | 05-08 → 05-09 | Phase H0 (null_means_zero), Phase H1 (surgical conflict, partial revert), Phase I-D/I-A/I-A.2 (HK notes LLM + 6 follow-ups) | LLM framework wired with confidence calibration scaffold; invest_income alias expansion 0/6 → 5/6 (83%); H1 partial revert preserved architectural honesty over a 33/33 mirage. |
| **5. Orchestrator & CN Surgical** | 05-09 → 05-10 | Phase EC (evaluate-company), Phase H2/H2.1/H2.2/H2.3#3/H2.4 (CN/HK conflict resolution, addition derivation, multi-sample verification, fixture persistence, cumulative review fixes) | 6-bucket evaluation taxonomy; period normalization cleared 41% spurious conflicts; 16 EXACT samples across 4 CN issuers × 4 fields back the H2 promotions; 600519 P0+P1 hit **33/33 (100%) clean**. |
| **6. HK Cohort Locks** | 05-10 → 05-11 | Phase HK-coverage discovery (HK-A scope collapse), Phase HK-C (industry_not_applicable), Phase HK-LLM-2/C (6 HK supplement merge), Phase HK-B.1-.4 (4 fields × 6 companies conflict shape locks) | HK-A "alias gap" hypothesis empirically collapsed to ~0 cells (adapters genuinely lack fields). 4 new HK fixtures live-fetched (01810/02498/06862/09987). 24 named shape-lock assertions guard against silent promotion of HK-B candidates. |

**Key reversals along the way**

- **H1 partial revert**: revenue/operating_profit/SGA alias swaps undone before merge
  — they would have moved 600519 to 33/33 via silent semantics change, violating
  source-first principle. Recovered by H2/H2.1/H2.2 with explicit PDF + multi-sample proof.
- **HK-A scope collapse**: pre-recon estimate was "16 cells fixable via alias
  expansion". Empirical recon showed adapters structurally lack the fields
  → revised to ~0 cells. Documented in `docs/phase_hk_coverage_discovery.md`.
- **HK-LLM "wiring missing" misread**: B-recon (`docs/phase_hk_llm_recon.md`)
  found the orchestrator was already wired; the apparent "0 supplement" was
  a UX/process gap (runs invoked without `--pdf --llm-config`), not engineering.

## 2. Architecture State

**Current source-first chain** (every arrow is enforced at the code level):

```
AKShare HK/CN + Yahoo HK/CN
   ↓  (source_inventory_fetch.py — live fetch or fixture replay)
SourceInventoryRecord  (ticker, period, raw_field_code, raw_value, source, currency, unit)
   ↓  (mapping.py — catalog-driven, market-scoped, derivation-aware)
MappedTurtleField  (per turtle field, all candidates with provenance)
   ↓  (reconciliation, source_policy.py — sign_normalize, provider_semantics, period norm)
SourceFirstExportItem  (selected_source + candidates + warnings)
   ↓  (company_evaluation.py classify_field — 6-bucket cascade)
6-bucket: clean_present / llm_supplement_present / unresolved_conflict
        / terminal_unverified / not_in_scope / source_unavailable
   ↓  (optional, gated by --pdf + --llm-config)
LLM evidence supplement merge  (selected_source="llm" for missing-candidate cells)
   ↓
final_export.json + evaluation.md
```

**Original PDF/LLM pipeline retained as fallback infrastructure**:
`ingestion.py` (pdftotext), `chunking.py` (BlockRecords + statement maps),
`retrieval.py` (field-first alias-scored top-k), `extraction.py`
(FakeLlmClient + real transport), `llm_field_extraction.py`,
`llm_extraction_runner.py`, `llm_extraction_batch.py`. The LLM path is now
**bounded, field-scoped, and opt-in** — never broad-PDF retrieval.

**Module boundary discipline**

- `evaluate-company` (orchestrator, per-(company, period), optional LLM)
  vs `replay-provider-baseline` (fixture-only batch)
- `MarketSourcePolicy.sign_normalize` is market-scoped (raw vs absolute)
- `SourceMappingEntry.by_market_aliases` and `derivation_markets` enforce
  CN/HK separation without code duplication
- `IndustryNotApplicableSpec` lets a single field carry per-(market, ticker)
  not_in_scope reasons (e.g., 01113 real-estate SGA convention) without
  global catalog forks

## 3. Coverage Milestones

| Ticker / Period | Source-first clean | +LLM | Locked by |
|-----------------|-------------------:|-----:|-----------|
| CN 600519 / 2024 | 39/56 (70%) | **44/56 (79%)** | `test_phase_hk_llm_2_supplement_merge.py::[600519]` |
| HK 00001 / 2025 | 28/56 (50%) | 33/56 (59%) | `test_phase_hk_llm_2_supplement_merge.py::[00001]` |
| HK 01113 / 2025 | 29/56 (52%) | 33/56 (59%) | `test_phase_hk_llm_2_supplement_merge.py::[01113]` |
| HK 01810 / 2024 | 32/56 (57%) | **39/56 (70%)** | `test_phase_hk_llm_2_supplement_merge.py::[01810]` |
| HK 02498 / 2024 | 32/56 (57%) | 37/56 (66%) | `test_phase_hk_llm_2_supplement_merge.py::[02498]` |
| HK 06862 / 2024 | 33/56 (59%) | 38/56 (68%) | `test_phase_hk_llm_2_supplement_merge.py::[06862]` |
| HK 09987 / 2024 | 29/56 (52%) | 32/56 (57%) | `test_phase_hk_llm_2_supplement_merge.py::[09987]` |

**Catalog growth**

| When | Field count | Driver |
|------|-------------|--------|
| Wave 1 baseline | 15 | legacy Turtle minimum |
| Post-N1–N3 (05-08) | 33 | P0:22 + P1:11 expansion |
| Post-N4.A–.C (05-09) | 44 | + 8 P2 source-first + 1 P2 LLM + 2 P3 |
| Post-I-C (05-09) | **56** | + 12 P3 text-mode pdf_only |

6 P3/P4 fields remain unmapped (terminal or weak retrieval; see §6).

**Sample-verification breadth**

- 4 CN companies × 4 promoted fields = **16 EXACT samples**
  (`provider_raw_semantics_cn.json` + `provider_field_baseline_h2_2_extension/`)
- 6 HK companies × 14 P3 fields = **84 LLM attempts, 33 present (39%)**
  (`tmp/runs/phase_i_c_validation_v2/`)
- 6 HK companies × 4 HK-B fields = **24 named shape-lock assertions**
  (`tests/test_phase_hk_b_*.py`)
- HK fixtures: 2 (baseline) + 4 (HK 6 extension) = **6 HK issuers persisted**

**Test count progression**: ~50 (bootstrap) → 450 (H0) → 524 (H2) → 552
(HK-LLM-2 initial 3-co) → **587 (post HK-B.1-.4 + HK-LLM-2/C)**.

## 4. Methodology Snapshot

These patterns are now the operating norm — both written into specs and
enforced by tests:

- **Drift §177 sample verification**: a `provider_raw_semantics` rule
  promoting a candidate needs ≥2 issuers + PDF spot-check before catalog
  promotion. H2.2 backed 4 CN promotions with 4-issuer × 4-field matrix.
  HK-B recon explicitly invokes this rule to reject provider-provider
  agreement as sufficient proof for `gross_profit`.
- **TDD RED → GREEN → commit cadence**: every phase has a spec doc + plan
  doc + implementation commits + validation report + roadmap update.
  Recent examples in `git log --oneline`.
- **Regression-lock pattern**: shape locks (e.g., HK-B `3 clean / 3 conflict`)
  are preferred over count thresholds (`≥2 clean`). HK-LLM-2 locks the
  exact `llm_supplement_present` field set so a catalog change that
  silently re-classifies surfaces named.
- **"Honest path" over tolerance gating**: H1 revert, HK-A collapse,
  HK SGA → terminal_unverified are all examples where architectural
  truth beat numeric coverage.
- **Fail-loud parsing**: `IndustryNotApplicableSpec` JSON loader rejects
  malformed entries with `ValueError`; `provider_semantics` catalog merge
  fails on alias collisions; `MoneyNormalizationError` is never silently
  swallowed.
- **Field-first retrieval** (never broad-PDF LLM): alias scoring +
  statement-map hints feed top-k bounded evidence; whitespace normalization
  (I-C.1) fixed a quiet 30 → 33 hit-rate bump caused by PDF-layout newlines.
- **Subagent-driven research / single-prompt synthesis**: complex audits
  (HK-B recon, this summary, cumulative review) delegated to Explore agents
  for data gathering; main agent synthesizes.

**Notable violation-and-correction moments**

- H0 review: `null_means_zero` lacked audit trail → added `review_notes` field.
- H2 review: derivation not market-scoped → H2.4 added `derivation_markets`.
- H2.4 Finding #2: derivation operand skipped `unit_multiplier` → fixed to
  route through `normalize_money()`.
- EC Tier 1: 41% spurious conflicts from period-string mismatches → period
  normalization before reconciliation.

## 5. Current State

**§7 branch completion criteria** (verified 2026-05-11):

1. ✅ Source-first as main direction (codified in design docs)
2. ✅ Phase ordering Taxonomy → Coverage Matrix → Minimal Mapping → Adapters
3. ✅ PDF/LLM as bounded selected-field fallback
4. ✅ Prior PDF/LLM phases preserved as fallback infrastructure
5. ✅ Source priority chain expressed consistently across design / requirements / roadmap

**Branch state**
- `feature/source-first-roadmap-requirements` @ `856a1a7`
- 317 commits since bootstrap (`c4fcbd6`, 2026-04-30)
- **309 commits ahead of `main`** (main remains near bootstrap)
- 0 commits behind origin/feature-branch (all local work pushed)
- **587 passing tests, 1 skipped (real-LLM smoke), 0 failing**
- `uv run ruff check .` clean (line-length 88, py311)
- `uv run mypy src tests` clean (`disallow_untyped_defs = true`)

**56-field catalog distribution**
- P0: 22 (income statement + balance sheet core)
- P1: 11 (cash flow, dividends, D&A, interest, tax, SBC)
- P2: 9 (Δ receiv/payable/inventory, capex, repurchase, tax refund)
- P3: 14 (5 money: cap_rd/interest, restricted_cash, time_deposits, dps;
  9 text: dividend_plan, receivables_aging, related_party, contingent_liabilities,
  lease_liability_maturity, segment_revenue_profit, buyback_cancellation_progress,
  bad_debt_provision, …)

**6-bucket evaluation taxonomy** (`company_evaluation.classify_field`):
`clean_present`, `llm_supplement_present`, `unresolved_conflict`,
`terminal_unverified`, `not_in_scope`, `source_unavailable`.

## 6. Open Decisions

Items flagged in the roadmap or recon docs as deferred / requires-decision:

| Item | Status | Source | Next required action |
|------|--------|--------|----------------------|
| HK-B `acct_payable` promotion | shape-locked (3 clean / 3 conflict) | `docs/phase_hk_b_recon.md` | PDF spot-check 01810/02498/06862 to validate AKShare 应付帐款 = Yahoo Accounts Payable = PDF Trade payables. If yes → sample-scoped HK rule; if no → terminal. |
| HK-B `fix_assets` promotion | shape-locked (3 clean / 3 conflict) | same | Yahoo Net PPE scope verification (ROU asset inclusion) per HKFRS 16. |
| HK-B `accounts_receiv` | shape-locked (6 conflict) | same | Keep conservative; AKShare 应收帐款 vs Yahoo Accounts Receivable scope mismatch needs ≥3-issuer proof. |
| HK-B `gross_profit` | shape-locked (4 conflict + 2 terminal) | same | Keep non-clean; provider-provider agreement alone insufficient per drift §177. |
| 6 P3/P4 fields with weak retrieval | unmapped | roadmap §7 follow-up | Either Phase I-D iteration with curated aliases per disclosure pattern, or accept terminal `not_in_scope`. |
| Confidence threshold calibration value | framework deployed, value deferred | Phase I-A.2 follow-up #2 | Collect ~50+ labeled (company, field) pairs; set threshold. |
| Bulk re-validation breadth | 6 HK + 4 CN issuers currently | roadmap §7 follow-up | Sector diversification (financials / tech / energy) before any HK-B promotion. |
| `_resolve_derivation_operand` period-equality assertion | deferred | H2.1 carryover | Add explicit period-end equality check on operand sums; low immediate risk. |
| Merge branch to `main` | not yet | — | 309 commits ahead; coherent shippable state. |

## 7. Onboarding Artifact Map

Future Claude / human readers should know these paths:

**Authoritative docs**
- `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
  (1657 lines, §1–§7, Phase Implementation Results indexed in §5)
- `CLAUDE.md` (project instructions, coverage table, phase index)
- `AGENTS.md` (partial — superseded by 33/56-field expansion in places)
- `docs/2026-05-11-phase-summary.md` (this file)

**Design + drift analysis**
- `docs/design/2026-05-01-structured-data-source-first-financial-extraction-design.md`
- `docs/design/2026-05-07-source-first-architecture-drift-analysis.zh.md`
  (drift §177, sampling bias, terminal states — still the load-bearing reference)

**Phase-specific recon / reality-check docs**
- `docs/phase_hk_b_recon.md` (HK-B 4-field conflict shape across 6 issuers)
- `docs/phase_hk_coverage_discovery.md` (HK-A → ~0 cells evidence)
- `docs/phase_hk_llm_recon.md` (LLM orchestrator wiring already complete)
- `docs/2026-05-10-h2-hk-cumulative-review.md` (3 H2 findings closed in H2.4)
- `docs/2026-05-08-roadmap-evaluation.zh.md` (pre-H2 framework, dated numbers)

**Field catalog JSONs**
- `field_catalog/turtle_v015_source_mapping_minimal.json` (56 fields, by_market, derivation)
- `field_catalog/turtle_v015_field_taxonomy.json` (full taxonomy, value_type, statement_type)
- `field_catalog/turtle_v015_coverage_matrix.json` (expected coverage routes)
- `field_catalog/provider_raw_semantics_cn.json` (5 CN promotion + 3 CN unverified rules; multi-sample backed)
- `field_catalog/provider_raw_semantics_hk.json` (HK terminal rules + HK SGA unverified)
- `field_catalog/hk_yahoo_trust_policy.json` (Yahoo HK trust scope)
- Cross-file gate: `tests/test_catalog_consistency.py`

**Regression-lock tests** (what guards what)
- HK-B shape locks: `tests/test_phase_hk_b_{acct_payable,fix_assets,accounts_receiv,gross_profit}.py`
- Multi-company sample regression: `tests/test_phase_h2_3_fixture_persistence.py`
- H2.4 cumulative review fixes: `tests/test_phase_h2_4_review_fixes.py`
- HK LLM supplement merge (7 companies): `tests/test_phase_hk_llm_2_supplement_merge.py`
- Catalog consistency: `tests/test_catalog_consistency.py`
- HK-C industry not-applicable: `tests/test_phase_hk_c_industry_not_applicable.py`

**Fixture directories**
- `tests/fixtures/provider_captures/provider_field_baseline/` (00001, 01113, 600519 base)
- `tests/fixtures/provider_captures/provider_field_baseline_h2_2_extension/` (300750, 601919, 688008 CN multi-sample)
- `tests/fixtures/provider_captures/provider_field_baseline_hk_llm_6_extension/` (01810, 02498, 06862, 09987 HK)
- `tmp/runs/phase_i_c_validation_v2/{00001,01113,01810,02498,06862,09987}/llm_evidence_supplement.json` (LLM baselines, pre-placed for regression)
- `tmp/llm_configs/deepseek.json` (local LLM config), `n4b_manifest.json` (HK 6-company batch manifest)

**CLI entry points** (subcommands of `python -m financial_report_llm_extractor`)
- `fetch-source-inventory` — live AKShare + Yahoo fetch + persist
- `evaluate-company` — per-(company, period) orchestrator (optional LLM via `--pdf --llm-config`)
- `extract-llm` / `extract-llm-batch` — field-scoped LLM extraction
- `replay-provider-baseline` — fixture-only batch replay

**Validation commands**

```bash
uv run pytest -v && uv run ruff check . && uv run mypy src tests
```

Per-(company, period) live workflow:

```bash
COMPANY=600519 YEAR=2024 MARKET=CN PROVIDERS=akshare \
  scripts/run-fetch-source-inventory.sh

COMPANY=600519 YEAR=2024 MARKET=CN \
  PDF_PATH=downloads/cn_stocks/600519/annual/2024_年度报告.pdf \
  LLM_CONFIG=tmp/llm_configs/deepseek.json \
  scripts/run-evaluate-company.sh
```
