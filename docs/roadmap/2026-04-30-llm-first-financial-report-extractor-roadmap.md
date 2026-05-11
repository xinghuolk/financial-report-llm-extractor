# Source-First Financial Report Extractor Roadmap

> Status: revised roadmap
> Date: 2026-05-07 (last validation: 2026-05-09 Phase EC live run)
> Scope: Pivot the project from PDF-first LLM extraction to AKShare/Yahoo-first structured financial data extraction, with PDF/LLM retained as the final evidence supplement and ambiguity review layer.
>
> Implementation status (2026-05-11): Phases A1–E (source-first foundation), Phase H0 (null_means_zero), Phase H1 (surgical conflict resolution; partially reverted post-review), Phases I-D/I-A/I-A.2 (LLM-assisted HK notes extraction with 6 follow-ups closed), Phases M2–M5 (HK terminal closure + provider semantics correction), Phases N0–N4 (catalog expansion 15 → 44 fields), Phase I-C (text-mode for 12 P3 pdf_only fields, total 56), Phase I-C.1 (whitespace-normalized retrieval), Phase EC (evaluate-company orchestrator for per-(company, period) regression validation), Phase H2 (CN/HK conflict surgical resolution), Phase H2.1 (CN SGA addition derivation), Phase H2.2 (multi-company sample-verification + market-scoped source_aliases + clean-row candidate audit display), Phase H2.3 #3 (persistent multi-company fixture + sample-vs-fixture regression), Phase HK-C (industry_not_applicable catalog override for 01113 SGA real-estate convention), Phase H2.4 (3 surgical fixes for cumulative review findings: market-scoped derivation + derivation-operand money normalization + selected_source for derived clean_present), Phase HK-LLM-2/C (regression-locked LLM supplement merge expanded to full 6 HK companies with 4 new live AKShare+Yahoo HK fixtures), Phase HK-B recon + HK-B.1-.4 shape locks for `acct_payable` / `fix_assets` / `accounts_receiv` / `gross_profit`, Phase MX (coverage matrix verification audit 24/62 → 36/62), and Phase HK-B.5 (acct_payable PDF spot-check + 5-issuer HK promotion via per-issuer `pdf_verified_company_ids` allowlist — 09987 USD reporter excluded pending Yahoo HK adapter currency-label fix) — complete.
>
> **Coverage milestone (post-H2.4 + HK-LLM-2 verified)**: CN 600519/2024 reaches **P0+P1 = 33/33 (100%) clean_present** after H2.2. Source-first 39/56 (70%) → **+LLM supplement 44/56 (79%)**, regression-locked by `tests/test_phase_hk_llm_2_supplement_merge.py`.
>
> **HK companies (regression-locked, post Phase HK-B.5 + currency-label follow-up)**: 00001/2025 source-first 29/56 (52%) → **+LLM 34/56 (61%)**; 01113/2025 source-first 30/56 (54%) → **+LLM 34/56 (61%)**; 01810/2024 source-first 32/56 (57%) → **+LLM 39/56 (70%)** (acct_payable selected_source flipped akshare → yahoo); 02498/2024 source-first 32/56 (57%) → **+LLM 37/56 (66%)** (same); 06862/2024 source-first 33/56 (59%) → **+LLM 38/56 (68%)** (same); 09987/2024 source-first 29/56 (52%) → **+LLM 32/56 (57%)** (acct_payable stays unresolved — USD reporter currency-label mismatch). HK Bucket-A "alias gap" hypothesis collapsed empirically to ~0 cells per `docs/phase_hk_coverage_discovery.md` reality-check. HK-B fixture prerequisite is satisfied; HK-B.1-.4 shape locks at `tests/test_phase_hk_b_*.py` are now augmented by HK-B.5 promotion of `acct_payable` for 5 PDF-verified HKD/RMB issuers via `pdf_verified_company_ids` allowlist (recon `docs/phase_hk_b_5_recon.md`); 09987 deferred until Yahoo HK adapter detects per-issuer reporting currency (see §7 follow-up). Next implementation slice: HK-B.6 `fix_assets` PDF spot-check + HK Yahoo currency-label adapter fix.
>
> **Sample-verification breadth**: 4 CN companies × 4 fields = 16 EXACT-match samples (revenue / operating_profit / capital_expenditures / SGA derivation) backing the H2/H2.1 promotions. interest_paid_cash still single-sample (non-financial issuers don't report PAY_INTEREST_COMMISSION).
>
> Live LLM batch validation on 6 HK companies × 14 P3 fields: 33/84 (39%) present, 0 extraction_failed.

## 1. Decision Summary

The next product slice should not continue broad PDF field retrieval as the main route. Real PDF coverage-budget validation showed that field-first PDF retrieval can diagnose and supplement evidence, but it is not a scalable first step for broad Turtle P0/P1 extraction across issuers and markets.

The revised main path is:

```text
Turtle full field taxonomy
-> Turtle coverage matrix
-> minimal source mapping contract
-> AKShare raw adapter
-> Yahoo/yfinance raw adapter
-> source field inventory
-> Turtle mapping / derivation
-> money and unit normalization
-> source coverage gate
-> cross-source reconciliation
-> source policy conflict classification and primary-candidate selection
-> selected PDF/LLM fallback
-> reviewable JSON artifacts
```

AKShare is the first source. Yahoo/yfinance is the second source. PDF financial report analysis is the last stage and only handles fields that are missing, ambiguous, conflicting, or require page/block/snippet evidence.

The Turtle target model must be designed first. AKShare and Yahoo/yfinance coverage should then be added in phases against that model, not used to reshape Turtle semantics around provider-specific returned fields.

## 2. Architecture Guardrails

Required direction:

- Source-first, not PDF-first.
- AKShare and Yahoo/yfinance calls must be deterministic adapter calls, not LLM tool calls.
- Raw source artifacts are mandatory and must be replayable in tests.
- Turtle field semantics must be defined before source adapter work is considered useful.
- Provider raw field semantics proof is the trust boundary for source policy. A provider raw field must be proven at provider/market/field level before it can be promoted to clean Turtle output.
- PDF samples may support provider policy proof, but they are not final per-export `pdf_evidence`.
- `source_evidence`, `trust_policy_evidence`, and `pdf_evidence` must remain separate in artifacts and reports.
- Do not solve provider semantics by chasing per-company PDF value matches.
- Field mapping must preserve raw field, raw value, period, scope, currency, unit, source, and evidence.
- Money normalization remains deterministic code.
- Cross-source conflicts must be explicit, not silently resolved.
- Cross-source conflicts must pass through source policy; primary-source selection must preserve warnings and verification requirements.
- PDF/LLM fallback is selected-field only and runs after source coverage/reconciliation.
- LLM is an assistant for ambiguity, source-field semantics, PDF evidence supplement, and consistency review; it is not the production data acquisition path.
- Existing PDF ingestion, chunking, retrieval, LLM transport, and evidence validation work remains useful as fallback infrastructure.

Explicit non-directions:

- Do not broaden PDF alias/statement rules as the next main task.
- Do not ask LLM to call MCP freely for production financial data.
- Do not copy TradingAgents-CN database/worker/API layers.
- Do not copy AKShare site-packages source into this repo.
- Do not use `report-collector` as AKShare reference; use it for PDF acquisition and sample reports.
- Do not promote source data to canonical facts.
- Do not do implicit FX conversion.

## 3. Relationship To Existing Work

Already implemented PDF/LLM foundation remains in the repo:

- Contracts for evidence, money, extracted items, chunks, and runs.
- PDF ingestion with `pages.jsonl`.
- Logical chunks with statement/page chunks.
- Retrieval probe with explicit missing status.
- Money normalization for CNY/HKD/USD and common units.
- Fake and real LLM extraction boundaries.
- LLM transports for OpenAI-compatible providers.
- Evaluation harness.
- Thin skill wrapper.
- Turtle coverage budget validation.

These are not discarded. They move behind the source-first coverage gate:

```text
source coverage/reconciliation
  -> selected fields needing PDF evidence
  -> existing PDF ingestion/chunking/retrieval
  -> existing LLM transport if review is needed
```

The newly added design supplement is:

- `docs/design/2026-05-01-structured-data-source-first-financial-extraction-design.md`
- `docs/superpowers/specs/2026-05-02-turtle-field-taxonomy-design.md`
- `docs/design/2026-05-07-source-first-architecture-drift-analysis.zh.md`

## 4. Functional Areas

### 4.1 Turtle Source Mapping Catalog

Define an extraction catalog that starts from `field_catalog/turtle_v015_priority_fields.json` but adds source semantics.

Before adding aliases broadly, fields must be classified by financial statement domain:

- income statement
- balance sheet
- cash flow
- shareholder return and capital actions
- R&D, capitalization, and accounting adjustments
- notes, risk, and operating text

Required fields per entry:

- `field_id`
- priority
- domain
- value type
- statement type
- period expectation
- scope expectation
- currency/unit requirements
- AKShare aliases and raw field candidates
- Yahoo/yfinance aliases and raw field candidates
- PDF aliases for fallback only
- derivation formula when applicable
- fallback policy
- source mode: direct, derived, source_optional, pdf_only, or llm_review
- evidence requirement: source_only_allowed, pdf_required, or llm_review_required

This catalog work has three layers:

1. Full Turtle field taxonomy: classify every existing Turtle field by financial statement domain and source mode.
2. Turtle coverage matrix: state whether each field is expected to be covered by AKShare, Yahoo/yfinance, PDF evidence, LLM review, derivation, or no first-stage source.
3. Minimal source mapping contract: add concrete aliases and raw field candidates only for the current implementation slice.

The first two layers come before broad AKShare/Yahoo mapping. Without them, adapter work can only chase provider output instead of measuring coverage against a stable Turtle model.

### 4.2 Structured Source Contracts

Define source-first models:

- `StructuredSourceRun`
- `SourceArtifact`
- `SourceInventoryRecord`
- `SourceEvidence`
- `TurtleMappingCandidate`
- `MappedTurtleField`
- `SourceCoverageSummary`
- `ReconciliationReport`

Contracts must be serializable, deterministic, and small enough for fixture tests.

### 4.3 AKShare Adapter

AKShare is the first priority source.

Initial target:

- A-share financial statements and indicators.
- HK financial statements and indicators.
- Raw artifact persistence.
- Source inventory rows.
- HK metadata join for currency, account standard, and report type.

Reference interfaces:

- `stock_balance_sheet_by_report_em`
- `stock_profit_sheet_by_report_em`
- `stock_cash_flow_sheet_by_report_em`
- `stock_financial_report_sina`
- `stock_financial_abstract`
- `stock_financial_hk_report_em`
- `stock_financial_hk_analysis_indicator_em`

Implementation should use injected clients or fixture-backed raw artifacts in unit tests. Real AKShare network calls must be opt-in integration tests.

### 4.4 Yahoo/yfinance Adapter

Yahoo/yfinance is the second priority source.

Initial target:

- income statement
- balance sheet
- cash flow
- stock info / metadata
- raw JSON artifact persistence
- source inventory rows

Yahoo fields are standardized fields and must not be treated as annual-report raw disclosure. They are useful for coverage, reconciliation, and fallback when AKShare is missing or fails.

### 4.5 Turtle Mapping And Derivation

Map source inventory records to Turtle fields.

Required behavior:

- Return all candidate source rows per field.
- Apply mapping rules with `mapping_rule_id`.
- Record confidence and warnings.
- Mark missing, ambiguous, conflict, unsupported, derived.
- Preserve all source evidence.
- For derived fields, preserve input lineage and validate period/scope/currency/unit consistency.

### 4.6 Money And Unit Normalization

Reuse and extend existing deterministic money normalizer.

Required additions:

- Treat source metadata as first-class unit/currency evidence.
- Add source precedence:

```text
AKShare explicit metadata
> Yahoo/yfinance explicit metadata
> source report/statement metadata
> PDF table header / PDF evidence
> market default heuristic
> unknown/ambiguous
```

- Block present money when currency or unit is unproven.
- Do not use market default heuristic to auto-accept final values.

### 4.7 Coverage Gate

Coverage gate must run before PDF/LLM fallback.

It must output:

- AKShare coverage.
- Yahoo/yfinance coverage.
- combined coverage.
- missing fields.
- ambiguous fields.
- conflict fields.
- fields requiring PDF evidence.
- fields requiring LLM review.
- blocker status.

Gate policy:

- Missing required source fields block broad source-first completion.
- Unit/currency ambiguity blocks present money.
- Source conflicts block final present value.
- Derived fields without lineage block final present value.
- PDF evidence gaps only block export profiles that require PDF evidence.

### 4.8 PDF/LLM Fallback

Use existing PDF and LLM foundations only after the source-first gate.

Fallback handles:

- missing fields
- ambiguous mapping
- source conflict
- required PDF page/block/snippet evidence
- notes-only or narrative fields
- consistency review between source value and annual-report snippet

Fallback must remain selected-field and bounded. It must not become broad P0/P1 PDF extraction again.

### 4.9 Artifacts And CLI

Artifacts should be JSON-first:

```text
tmp/
  runs/
    <run_id>/
      source_artifacts/
        akshare/
        yahoo/
      source_inventory.jsonl
      turtle_mapping.json
      source_coverage_summary.json
      reconciliation_report.json
      pdf_evidence_supplement.json
      extraction_result.json
      review_summary.json
      run_metadata.json
```

CLI direction:

- `source-fetch`
- `source-map`
- `source-coverage`
- `source-reconcile`
- existing `ingest/chunk/retrieve/extract` remain for fallback

## 5. Implementation Phases

### Phase A1: Turtle Full Field Taxonomy

Goal: define the full Turtle target model before integrating or expanding external data sources.

Deliverables:

- Turtle field taxonomy for all existing fields, grouped by income statement, balance sheet, cash flow, shareholder return, accounting adjustments, and notes/MDA.
- Primary domain for every field in `field_catalog/turtle_v015_priority_fields.json`.
- Source mode for every field: direct, derived, source_optional, pdf_only, or llm_review.
- Statement type, period type, value type, currency/unit requirement, and evidence requirement metadata.
- Tests or validation checks that every current Turtle field is classified exactly once by primary domain.

Exit criteria:

- Every existing Turtle field has a primary domain and source mode.
- The taxonomy can answer domain-first questions such as all P0 balance sheet fields, all cash-flow fields, and all PDF-only notes fields.
- Provider aliases are not required for this phase.
- The taxonomy loader rejects malformed JSON shape with stable `ValueError` messages, not raw `KeyError`, `TypeError`, or `AttributeError`.

Implementation note:

- `field_catalog/turtle_v015_field_taxonomy.json` contains full Turtle field taxonomy.
- `field_catalog/turtle_v015_coverage_matrix.json` contains expected coverage route by field.
- `field_catalog/turtle_v015_source_mapping_minimal.json` is linked to taxonomy and coverage metadata.
- Review follow-up: align taxonomy loader shape validation with the already hardened coverage matrix loader.

### Phase A2: Turtle Coverage Matrix

Goal: decide expected coverage route for every Turtle field before writing broad provider mappings.

Deliverables:

- Coverage matrix keyed by `field_id`.
- Expected coverage route per field:
  - AKShare direct
  - Yahoo/yfinance direct
  - derived from source fields
  - PDF evidence required
  - LLM review required
  - unsupported in first-stage source-first extraction
- Verification status per provider and field: verified, expected, unknown, unsupported.
- Domain-level and priority-level coverage summaries.
- Tests or validation checks that all fields have a coverage route and verification status.

Exit criteria:

- The project can report total Turtle coverage by domain and priority before calling AKShare/Yahoo.
- `pdf_only` and `llm_review` fields are not counted as missing structured-source failures in the first source-first gate.
- The next provider work can be selected from explicit coverage gaps.

Implementation note:

- `field_catalog/turtle_v015_field_taxonomy.json` contains full Turtle field taxonomy.
- `field_catalog/turtle_v015_coverage_matrix.json` contains expected coverage route by field.
- `field_catalog/turtle_v015_source_mapping_minimal.json` is linked to taxonomy and coverage metadata.

### Phase A3: Minimal Source Mapping Contract

Goal: add concrete source aliases only for the current source-first implementation slice.

Deliverables:

- Source-first dataclasses.
- Source evidence contract.
- Enriched Turtle mapping catalog fixture for P0/P1 minimum fields.
- AKShare/Yahoo raw field aliases for the selected fields.
- Tests for serialization and validation.
- Tests for missing currency/unit blocking.

Exit criteria:

- Catalog can list required P0/P1 fields and their source mapping expectations.
- A coverage gate can run against fixture inventory without AKShare/Yahoo installed.
- Minimal mappings are traceable back to the full taxonomy and coverage matrix.
- Referenced source mapping catalogs fail fast on malformed top-level, priority, mapping, alias, or entry shapes using stable `ValueError` messages.

Implementation note:

- `field_catalog/turtle_v015_field_taxonomy.json` contains full Turtle field taxonomy.
- `field_catalog/turtle_v015_coverage_matrix.json` contains expected coverage route by field.
- `field_catalog/turtle_v015_source_mapping_minimal.json` is linked to taxonomy and coverage metadata.
- Review follow-up: harden `load_source_mapping_catalog()` shape validation so broken catalog JSON cannot surface as raw Python container errors.

### Phase B: Source Inventory And Artifact Store

Goal: create the adapter-independent raw artifact and inventory layer.

Deliverables:

- `SourceArtifactStore`.
- `SourceInventoryRecord` writer/reader.
- Stable artifact IDs.
- Fixture-backed raw source artifacts.
- CLI skeleton for source artifact paths.

Exit criteria:

- Fixture raw artifacts can be converted to `source_inventory.jsonl`.
- Artifacts are deterministic and rebuildable.

Implementation note:

- Phase B baseline artifact store exists in `structured_sources/artifacts.py`.
- PB2 hardening is implemented: `source_artifact_manifest.json` roundtrip, stable malformed manifest and JSONL errors, and replay validation from `SourceEvidence.artifact_id` to raw artifact files.
- Replay validation verifies manifest membership, file existence, SHA-256 match, and resolved path containment under the artifact root.
- This remains fixture-only and offline; Phase C/D provider adapters should consume this storage boundary without changing it.

### Phase C: AKShare Adapter

Goal: make AKShare the first structured financial source, implemented in stages against the Turtle coverage matrix.

Deliverables:

- AKShare config and dependency decision.
- Adapter boundary with injectable AKShare client.
- A-share statement inventory conversion.
- HK statement inventory conversion.
- HK metadata join for currency/account standard/report type.
- Fixture tests for `600519`, `00001`, `01113`.
- Optional opt-in smoke script for real AKShare calls.

Exit criteria:

- AKShare fixtures produce source inventory rows for all three validation companies.
- Currency/unit metadata is explicit or marked unknown/ambiguous.
- Source errors are structured.
- AKShare coverage is reported by Turtle domain and priority, not only by raw provider fields.

Implementation note:

- Phase C baseline AKShare fixture adapter exists for HK and CN statements.
- PC2 should integrate AKShare adapter runs with PB2 artifact manifests and replay validation.
- Adapter-backed validation should write `source_artifact_manifest.json`; captured inventory validation remains manifest-optional.
- PC3/PD0 should capture the target AKShare/Yahoo provider field baseline once, save raw artifacts plus `provider_field_inventory_summary.json`, and drive subsequent mapping work from captured fixtures.

### Phase D: Yahoo/yfinance Adapter

Goal: add the second structured source for fallback and reconciliation, implemented in stages against the Turtle coverage matrix.

Deliverables:

- yfinance adapter or deterministic wrapper around existing yahoo-finance-mcp behavior.
- Raw JSON artifact persistence.
- Statement inventory conversion.
- Fixture tests for HK and US-style ticker formats.
- Explicit unsupported/missing statuses.

Exit criteria:

- Yahoo fixtures produce source inventory rows.
- Yahoo coverage can be compared independently with AKShare coverage.
- Yahoo coverage is reported by Turtle domain and priority, not only by raw provider fields.

### Phase E: Turtle Mapping, Derivation, And Coverage Gate

Goal: decide whether AKShare/Yahoo can cover Turtle fields by domain and priority before PDF/LLM work.

Deliverables:

- Source-to-Turtle mapper.
- Mapping rule IDs.
- Derived field engine for simple formulas.
- Coverage summary writer.
- Blocker policy.
- Markdown review summary.

Exit criteria:

- `600519`, `00001`, `01113` each produce:
  - `source_inventory.jsonl`
  - `turtle_mapping.json`
  - `source_coverage_summary.json`
- Missing, ambiguous, conflict, derived, unsupported statuses are explicit.
- Coverage summaries distinguish structured-source gaps from fields intentionally routed to PDF/LLM by taxonomy.

### Phase F: Cross-Source Reconciliation

Goal: compare AKShare and Yahoo when both produce candidates.

Deliverables:

- Reconciliation rules for period, scope, currency, unit, raw value, normalized value.
- Tolerance policy for numeric differences.
- Conflict report.
- Tests for equal, close, different, different-period, different-currency cases.

Exit criteria:

- Combined coverage does not hide source disagreement.
- Conflicts block final present values until resolved or reviewed.

### Phase G: Source-First Review Export

Goal: produce reviewable JSON without requiring PDF fallback.

Deliverables:

- `extraction_result.json` profile backed by source evidence.
- `review_summary.json`.
- Clear distinction between source evidence and PDF evidence.
- Export profile that can optionally require PDF evidence.

Exit criteria:

- Source-only profile can show what fields are available from AKShare/Yahoo.
- PDF-required profile lists exactly which fields still need evidence supplement.

### Phase H: Selected PDF Evidence Supplement

Goal: reuse existing PDF pipeline only for fields selected by the source-first gate.

Deliverables:

- Input: mapped fields needing PDF evidence or review.
- Selected-field retrieval using existing chunk/retrieval code.
- PDF evidence supplement artifact.
- Consistency checks between source value and PDF snippet.

Exit criteria:

- PDF analysis no longer runs broad P0/P1 by default.
- Evidence supplement can attach page/block/snippet to selected fields.

### Phase I: LLM-Assisted Ambiguity Review

Goal: use LLM only where deterministic source mapping and PDF retrieval need help.

Deliverables:

- Prompt schemas for ambiguous source mapping.
- Prompt schemas for source-vs-PDF consistency review.
- DeepSeek/Gemini/Ollama config reuse.
- Fake LLM tests.
- Optional real LLM smoke test.

Exit criteria:

- LLM output never bypasses source evidence, PDF evidence, or money validation.
- Raw LLM responses are archived.

### Phase J: End-To-End Source-First Evaluation

Goal: decide whether source-first is viable for Turtle fields by domain and priority before broader implementation.

Validation samples:

- `600519`
- `00001`
- `01113`

Deliverables:

- End-to-end source-first script.
- Coverage comparison:
  - AKShare only
  - Yahoo only
  - combined
  - combined + PDF supplement
- Coverage comparison by Turtle domain and priority, using the full taxonomy and coverage matrix.
- Known hard-case fixtures.
- Updated roadmap decision note.

Exit criteria:

- Source-first combined coverage is materially better than the current PDF retrieval coverage.
- Remaining gaps are explicit and assigned to source mapping, source availability, PDF supplement, LLM review, or intentionally unsupported first-stage source coverage.

Implementation note:

- Phase J now includes a fixture-driven no-network evaluation harness and `scripts/run-source-first-e2e-evaluation.sh`.
- The harness writes per-report artifacts and compares AKShare-only, Yahoo-only, combined, and combined-plus-PDF-supplement coverage.
- The default fixtures cover the three validation report IDs: `600519`, `00001`, and `01113`.
- Phase J has been tightened after code review so that source-first validation cannot be considered complete from synthetic fixtures alone.
- A real-source validation path now exists as an opt-in smoke:
  - `scripts/run-real-source-validation.sh`
  - `src/financial_report_llm_extractor/structured_sources/real_source_validation.py`
  - real provider calls are gated by `REAL_SOURCE_VALIDATION=1`
  - captured source inventory can be replayed with `INVENTORY_FIXTURE=<source_inventory.jsonl>` without calling providers again.
- The first captured AKShare fixture is saved at `tests/fixtures/akshare/600519_income_statement_2025_required_fields.jsonl`.
  It was derived from a real AKShare 600519 income statement response and currently validates `revenue` and `net_profit` through source inventory, mapping, reconciliation, and source-only export.
- Real AKShare CN statement responses are wide tables, so the AKShare adapter now expands known wide columns into long `SourceInventoryRecord` rows before mapping.
- The mapper treats catalog alias order as a deterministic same-source precedence rule. This resolves cases such as `营业收入` versus `营业总收入` without hiding cross-source conflicts.

Current validation status:

- Synthetic no-network source-first E2E: implemented.
- Captured AKShare income statement replay for 600519: implemented; covers 2 of 9 minimal source-mapping fields.
- Real AKShare combined validation for 600519 has been run once for income statement, balance sheet, and cash flow, then saved as `tests/fixtures/akshare/600519_combined_statements_2025_required_fields.jsonl`.
  Captured replay covers 8 of 9 minimal fields: `revenue`, `net_profit`, `total_assets`, `total_liabilities`, `cash`, `operating_cash_flow`, `total_cur_assets`, and `total_cur_liab`.
- Real Yahoo/yfinance validation for `0001.HK` income statement has been run once, then saved as `tests/fixtures/yahoo/0001_hk_income_statement_2025_required_fields.jsonl`.
  Captured replay covers 3 of 9 minimal fields: `revenue`, `net_profit`, and `gross_profit`.
- A broader provider field baseline has been captured and compressed under `tests/fixtures/provider_captures/provider_field_baseline/`.
  It contains 6,771 latest-five-annual-period inventory records from AKShare and Yahoo across the current validation matrix.
- Provider field candidate discovery is implemented as a no-network replay step:
  - `src/financial_report_llm_extractor/structured_sources/field_candidate_discovery.py`
  - `financial-report-llm-extractor discover-provider-fields`
  - output: `tmp/runs/provider_field_candidate_discovery/provider_field_candidate_report.json`
- Source mapping catalog expansion has promoted 6 strong deterministic mappings, increasing the minimal source mapping denominator from 9 to 15.
- Whole-baseline replay without period scoping is invalid for coverage because the 5-year baseline creates `candidate periods differ` conflicts for every mapped field.
- Provider baseline period-scoped replay is implemented as the replay prerequisite for source policy work:
  - `scripts/run-provider-baseline-period-replay.sh`
  - output: `tmp/runs/provider_baseline_period_replay/provider_baseline_period_replay_summary.json`
  - it selects the latest annual date part per company/source and normalizes replay periods before mapping.
- Source policy conflict resolution is implemented and reviewed:
  - source policy catalog metadata supports semantic variants, market policies, primary routes, cross-check routes, and PDF verification requirements.
  - `MappedTurtleField` preserves policy evidence candidates filtered out by same-source alias precedence.
  - source policy classifies semantic mismatch, FX-like ratio, metadata-currency suspicion, single-source unverified coverage, and missing currency metadata proof.
  - export preserves `selection_status`, `selected_source`, `verification_required`, `conflict_classifications`, warnings, and review notes.
  - provider baseline replay writes `source_policy_report.json` for every company/source slice.
- Latest no-network source-policy replay:
  - command: `uv run financial-report-llm-extractor replay-provider-baseline --inventory tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz --inventory-summary tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json --catalog field_catalog/turtle_v015_source_mapping_minimal.json --out tmp/runs/source_policy_conflict_resolution`
  - output: `tmp/runs/source_policy_conflict_resolution/provider_baseline_period_replay_summary.json`
  - `600519` combined selected coverage: 14/15, clean present: 13/15, `revenue` selected with warning and PDF verification required.
  - `00001` combined selected coverage: 11/15, clean present: 4/15, HK balance-sheet totals selected with warnings and PDF verification required.
  - `01113` combined selected coverage: 11/15, clean present: 4/15, HK balance-sheet totals selected with warnings and PDF verification required.
- Remaining gaps are now categorized into source availability, mapping ambiguity/blocker, raw reconciliation conflict, policy unresolved conflict, and PDF/LLM supplement candidates.

Current Phase M4 replay status, verified on 2026-05-07:

- command: `financial-report-llm-extractor replay-provider-baseline --inventory tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz --inventory-summary tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json --catalog field_catalog/turtle_v015_source_mapping_minimal.json --out tmp/runs/review_current_coverage`
- `600519` combined selected coverage: 14/15, clean present: 13/15.
- `00001` combined selected coverage: 11/15, clean present: 10/15.
- `01113` combined selected coverage: 11/15, clean present: 10/15.
- HK `sampled_pdf_policy_proof_fields`: `net_profit`, `revenue`, `total_assets`, `total_cur_assets`, `total_cur_liab`, `total_liabilities`.
- HK `final_pdf_evidence_fields`: none in the current source-only replay.
- HK remaining non-clean fields:
  - `gross_profit`: `yahoo_definition_unverified` / provider semantics unverified.
  - `defer_tax_liab`: `mapping_expansion_required`.
  - `bond_payable`, `cip`, `invest_income`: `source_unavailable`.
- The route is now corrected back to source-first/provider-semantics-first: clean HK policy fields are clean because of source evidence plus provider raw semantics policy proof, not because every company has final PDF evidence.

### Phase K: HK Currency, Unit, And Reporting Metadata Proof

Goal: make Hong Kong source candidates trustworthy before expanding field coverage.

Rationale:

- Current HK provider baseline is not primarily a raw field availability problem. `00001` and `01113` each reach 11/15 combined selected coverage, but only 4/15 clean present fields.
- The next blocker is proof quality: currency, unit multiplier, report type, account standard, statement metadata, and provider-specific scale semantics.
- Expanding to 33 P0/P1 fields before this proof layer is stable would copy the same warnings into more fields and make coverage numbers misleading.

Deliverables:

- Audit AKShare HK and Yahoo HK inventory metadata separately for `currency`, `unit`, `canonical_unit`, `report_type`, `account_standard`, `statement_metadata_proven`, and source artifact provenance.
- Fix any HK adapter or replay logic that treats currency as unit. `HKD` is currency evidence, not a unit multiplier by itself.
- Define explicit unit semantics for AKShare HK statement rows and Yahoo/yfinance rows:
  - raw provider value
  - reported currency
  - source unit label
  - deterministic `unit_multiplier`
  - normalized Turtle money value
- Tighten source policy so HK metadata warnings distinguish:
  - missing source metadata
  - unproven statement metadata
  - suspicious FX-like cross-source ratio
  - real semantic conflict
- Add fixture-backed tests for HK metadata proof on `00001` and `01113`.

Exit criteria:

- HK candidates cannot be clean present unless currency and unit multiplier are proven.
- HK metadata proof is visible in `source_policy_report.json` and review export artifacts.
- Replaying the existing provider baseline shows fewer metadata-only warnings, or the remaining warnings clearly explain why PDF verification is still required.

### Phase L: Classify HK 11/15 Warning Fields

Goal: turn the current HK selected-with-warning coverage into an actionable work queue.

Implementation status:

- Warning classification artifacts are written for each provider replay slice.
- HK `00001` and `01113` combined slices expose a PDF verification queue, mapping expansion queue, and source unavailable queue.
- PDF verification queue is now bounded to `pdf_verification_required`.

Deliverables:

- Add a warning classification summary for each company/source slice and combined slice.
- For the current 15-field denominator, classify every non-clean selected HK field into one of:
  - `source_policy_resolvable`: source policy, alias precedence, metadata proof, or provider priority can resolve it deterministically.
  - `pdf_verification_required`: annual-report evidence is needed because providers disagree, values imply FX-like ratio, or source semantics differ.
  - `mapping_expansion_required`: provider raw fields exist but catalog aliases/policies are insufficient.
  - `source_unavailable`: neither AKShare nor Yahoo captured a usable field candidate.
- Preserve per-field reasons and candidate source evidence so the queue is reviewable.
- Update provider baseline replay summary with counts by classification and by field.

Exit criteria:

- `00001` and `01113` warning fields are no longer a flat warning bucket.
- The roadmap can state exactly which HK fields should be fixed in source policy and which must proceed to PDF evidence supplement.
- PDF fallback receives a bounded field list instead of broad P0/P1 retrieval.

### Phase M: HK Yahoo Trust Policy And PDF Spot-Check

Status: implemented on 2026-05-06.

Goal: turn the current HK PDF verification queue into deterministic source policy rules where sampled annual-report evidence proves Yahoo HK raw values and field semantics.

Current evidence:

- `00001` and `01113` annual reports in `downloads/hk_stocks/*/annual/2025_annual_en.pdf` have already been parsed into quick-validation artifacts.
- For `00001`, the annual report discloses `Revenue = 280,036 HK$ million`, `Current assets = 212,743 HK$ million`, and `Current liabilities = 135,399 HK$ million`; Yahoo returns the same values as full HKD raw amounts.
- For `01113`, the annual report discloses `Group revenue = 57,935 $ Million`, `Current assets = 174,106 $ Million`, and `Current liabilities = 39,072 $ Million`; Yahoo returns the same values as full HKD raw amounts.
- `01113` total assets and total liabilities can be proven from annual-report subtotals:
  - `335,392 + 174,106 = 509,498` HK$ million, matching Yahoo `Total Assets`.
  - `39,072 + 61,745 = 100,817` HK$ million, matching Yahoo `Total Liabilities Net Minority Interest`.

Deliverables:

- Add an HK Yahoo trust-policy fixture that records annual-report evidence for `00001` and `01113`, including page, statement line, reported unit, PDF value, expected Yahoo raw value, and matched Yahoo raw field.
- Classify the current HK `pdf_verification_required` queue into:
  - `yahoo_pdf_verified`: legacy name for sampled HK Yahoo provider policy proof; it proves a provider raw field/unit rule, not final per-export PDF evidence.
  - `yahoo_definition_unverified`: Yahoo has a value, but annual-report row semantics are not directly proven.
  - `pdf_required`: no current API path can prove the field.
- Promote HK Yahoo primary policy only for sampled fields whose definition and unit are proven:
  - implemented candidates: `revenue`, `total_assets`, `total_cur_assets`, `total_cur_liab`, `total_liabilities`.
  - `net_profit` remains `yahoo_definition_unverified` until exact annual-report row semantics and value proof are added.
  - keep `gross_profit` in PDF verification until the annual-report row semantics are proven, because the sampled formal income statements do not expose a simple same-name gross-profit row.
- Keep `defer_tax_liab` as mapping-expansion-first with PDF spot-check.
- Keep `bond_payable`, `cip`, and `invest_income` as source-unavailable for the current AKShare/Yahoo captured data unless a new provider/source fixture is added.
- Update provider replay so HK Yahoo-verified fields can become clean present while preserving the sampled PDF verification artifact as policy evidence.

Exit criteria:

- `00001` and `01113` combined slices show improved clean-present coverage for the current 15-field denominator without relying on every-company manual PDF analysis.
- Source policy explains that HK Yahoo `currency=HKD`, `unit=raw`, `unit_multiplier=1` is trusted only for fields covered by the sampled PDF trust policy.
- The project can distinguish "Yahoo raw HKD value is PDF-verified by policy" from "this company has page/block PDF evidence in the final export".

Implementation result:

- Added `field_catalog/hk_yahoo_trust_policy.json` and loader/tests.
- Provider baseline replay now writes `hk_yahoo_trust_policy_report.json` for HK slices and exposes:
  - `yahoo_pdf_verified_fields`
  - `yahoo_definition_unverified_fields`
  - `pdf_required_fields`
- `00001` combined coverage is now `10/15` selected and `9/15` clean present.
- `01113` combined coverage is now `10/15` selected and `9/15` clean present.
- Clean HK fields now include:
  - `cash`
  - `operating_cash_flow`
  - `investing_cash_flow`
  - `financing_cash_flow`
  - `revenue`
  - `total_assets`
  - `total_cur_assets`
  - `total_cur_liab`
  - `total_liabilities`
- Remaining HK 15-field gaps:
  - `net_profit`: present but `yahoo_definition_unverified`, still requires annual-report row semantics proof.
  - `gross_profit`: still requires PDF verification.
  - `defer_tax_liab`: mapping expansion path.
  - `bond_payable`, `cip`, `invest_income`: source unavailable in current AKShare/Yahoo captured data.
- Verification:
  - Phase M focused tests: `116 passed`.
  - `uv run ruff check .`: passed.
  - `uv run mypy src tests`: passed.
  - Full `uv run pytest -v`: `411 passed, 1 skipped, 1 failed`; the remaining failure is an existing `akshare_cn_600519_balance_sheet` fixture hash mismatch, not introduced by Phase M.

### Phase M2: HK 15-Field Terminal Bucket Closure

Status: implemented on 2026-05-07. See:

- `docs/superpowers/specs/2026-05-07-phase-m2-hk-15-field-terminal-buckets.md`
- `docs/superpowers/plans/2026-05-07-phase-m2-hk-15-field-terminal-buckets.md`

Goal: make every HK field in the current 15-field denominator either clean present or assigned to a stable, reviewable terminal bucket before expanding to the full 33-field P0/P1 denominator.

Why this precedes Phase N:

- Phase M improved `00001` and `01113` to `10/15` selected and `9/15` clean present.
- The remaining six fields should not be treated as one generic warning queue.
- The right target is not forced `15/15` clean present; it is explicit terminal status for every field.

Target terminal buckets:

- `clean_present`
- `yahoo_pdf_verified`
- `yahoo_definition_unverified`
- `pdf_required`
- `mapping_expansion_required`
- `source_unavailable`

Field priorities:

1. `net_profit`
   - Highest priority.
   - Yahoo value exists.
   - Needs annual-report row semantics proof before it can move from `yahoo_definition_unverified` to `yahoo_pdf_verified`.
   - If proven, HK clean present can move from `9/15` to `10/15`.
2. `gross_profit`
   - Needs PDF row or derivation proof.
   - It may remain non-clean if sampled HK formal reports do not expose stable same-name row semantics.
   - Current Phase M2 terminal bucket is `pdf_required`.
3. `defer_tax_liab`
   - Remains mapping-expansion-first.
   - Existing Yahoo candidate is not strong enough to promote directly.
4. `bond_payable`, `cip`, `invest_income`
   - Remain `source_unavailable` in current captured AKShare/Yahoo data.
   - Do not force clean values without a new provider fixture or PDF fallback.

Deliverables:

- Added `hk_15_field_closure_report.json` to HK provider replay slices.
- Added `hk_15_field_closure_report.md` for human review.
- Added closure artifacts to replay `artifact_paths` as `hk_15_field_closure_report` and `hk_15_field_closure_markdown`.
- Ensured `00001` and `01113` combined replay reports all 15 fields in either clean present or exactly one terminal bucket.
- Phase M4 provider-semantics correction must run before Phase N 33-field expansion; do not use Phase N to hide unresolved 15-field proof issues.

Exit criteria:

- `00001` and `01113` combined replay has no unclassified HK 15-field item.
- `net_profit`, `gross_profit`, `defer_tax_liab`, `bond_payable`, `cip`, and `invest_income` have explicit terminal explanations.
- Replay distinguishes definition-unverified, PDF-required, mapping-expansion, and source-unavailable cases.
- Focused verification: `tests/test_hk_15_field_closure.py`, `tests/test_provider_baseline_replay.py`, `tests/test_hk_yahoo_trust_policy.py`, and `tests/test_warning_classification.py` pass with `36 passed`.
- Phase N can start only after the stable 15-field baseline and Phase M4 provider-semantics correction are both complete.

### Phase M3: HK net_profit Raw Field Semantics Sample Proof

Status: implemented on 2026-05-07, then reclassified by Phase M4 review as provider-semantics sample proof rather than final PDF evidence. See:

- `docs/superpowers/specs/2026-05-07-phase-m3-hk-net-profit-pdf-proof.md`
- `docs/superpowers/plans/2026-05-07-phase-m3-hk-net-profit-pdf-proof.md`

Goal: prove that the HK Yahoo raw field `Net Income Common Stockholders` is the correct provider raw semantic for Turtle `net_profit`, without expanding the denominator beyond the current 15 fields.

Important interpretation:

- The M3 PDF samples are sampled provider policy proof.
- They are not final per-export `pdf_evidence`.
- They must not be used as a pattern for per-company PDF value matching.
- The safer product wording is `provider_semantics_sample_verified`, not final PDF verified evidence.

Implementation result:

- `net_profit` now trusts only Yahoo raw field `Net Income Common Stockholders`.
- `Net Income` and `Net Income From Continuing Operation Net Minority Interest` remain related context, not trusted HK primary fields.
- `00001` proof: page `134`, row `Profit attributable to ordinary shareholders`, `11,841` HKD million equals Yahoo raw `11,841,000,000`.
- `01113` proof: page `70`, row `Profit attributable to shareholders`, `10,847` HKD million equals Yahoo raw `10,847,000,000`.
- HK combined replay currently moves from `9/15` clean present to `10/15` clean present, but Phase M4 must review whether this should remain a clean-present baseline or be reported as sampled provider-semantics proof.
- `gross_profit` remains non-clean and still requires PDF row or derivation proof.

Verification:

- Phase M3 focused tests: `69 passed`.

### Phase M4: Provider Raw Semantics Correction Before 33-Field Expansion

Status: implemented on 2026-05-07. See:

- `docs/design/2026-05-07-source-first-architecture-drift-analysis.zh.md`
- `docs/superpowers/specs/2026-05-07-phase-m4-provider-semantics-correction.md`
- `docs/superpowers/plans/2026-05-07-phase-m4-provider-semantics-correction.md`

Goal: correct the proof-boundary drift before expanding to the full 33-field P0/P1 denominator.

Why this blocks Phase N:

- `yahoo_pdf_verified` currently conflates provider policy proof with final PDF evidence.
- M3 `net_profit` has useful raw-field selection, but its tests and reports can be misread as per-company PDF proof.
- `gross_profit` has provider candidates, but neither Yahoo `Gross Profit` nor AKShare `毛利` has HK provider raw semantics proof.
- Expanding to 33 fields before fixing this vocabulary would multiply the same ambiguity across more fields.

Deliverables:

- Add a provider raw semantics artifact or equivalent loader contract:
  - `field_catalog/provider_raw_semantics_hk.json`
  - `src/financial_report_llm_extractor/structured_sources/provider_semantics.py`
- Distinguish trusted provider raw fields from related-only and negative context fields.
- Reframe `net_profit` as sampled provider-semantics proof for Yahoo `Net Income Common Stockholders`.
- Keep `gross_profit` non-clean until provider raw semantics are proven.
- Update replay/closure reports to distinguish:
  - `source_evidence`
  - `trust_policy_evidence`
  - `provider_semantics_verified_fields`
  - `sampled_pdf_policy_proof`
  - `provider_semantics_unverified_fields`
  - final per-export `pdf_evidence`
- Add catalog consistency tests so top-level `primary_route` / `verification_status` cannot contradict market policy or provider semantics status.
- Add trust-policy sample tests that validate PDF sample page text or explicitly document why page text is unavailable.

Exit criteria:

- Future agents can no longer infer that PDF samples mean final per-company PDF evidence.
- `gross_profit` remains in a stable non-clean terminal bucket with a clear reason.
- `net_profit` preserves the Yahoo raw-field decision while reporting its proof class accurately.
- Phase N expansion has a clean provider-semantics gate to reuse.

Implementation result:

- Provider raw semantics catalog and loader are implemented.
- Source policy refuses HK Yahoo trust-policy promotion unless provider semantics catalog authorizes the raw field.
- Provider replay and HK closure reports separate:
  - `provider_semantics_verified_fields`
  - `sampled_pdf_policy_proof_fields`
  - `provider_semantics_unverified_fields`
  - `final_pdf_evidence_fields`
- Clean-present coverage excludes review notes and conflict classifications.
- `gross_profit` is downgraded from verified direct to expected/non-clean for HK.
- Focused verification: `108 passed`.
- `uv run ruff check .`: passed.

### Phase M5: defer_tax_liab Yahoo Semantics Proof And gross_profit Terminal Closure

Status: implemented on 2026-05-07. See:

- `docs/superpowers/specs/2026-05-07-phase-m5-defer-tax-liab-gross-profit-closure.md`
- `docs/superpowers/plans/2026-05-07-phase-m5-defer-tax-liab-gross-profit-closure.md`

Goal: resolve the two remaining actionable HK 15-field gaps before Phase N expansion.

Implementation result:

- `defer_tax_liab` promoted to clean present via Yahoo `Non Current Deferred Taxes Liabilities` provider semantics proof.
  - 00001: page 136, Deferred tax liabilities = 17,275 HK$ million, Yahoo raw = 17,275,000,000 HKD.
  - 01113: page 71, Deferred tax liabilities = 14,889 $ Million, Yahoo raw = 14,889,000,000 HKD.
  - `Current Deferred Taxes Liabilities` excluded as negative context.
- `gross_profit` terminal reason updated from "not yet proven" to "HK formal income statements do not contain a gross profit row".
  - 00001 page 134: Revenue → 6 cost line items → EBIT-like subtotal, no gross profit row.
  - 01113 page 70: Group revenue → bundled operating costs → profit before tax, no gross profit row.
  - Derivation unreliable due to non-standard cost structures.
  - Terminal bucket remains `yahoo_definition_unverified` with explicit incompatibility reason.
- HK 15-field clean present: 10/15 → 11/15.
- Remaining HK non-clean fields:
  - `gross_profit`: `yahoo_definition_unverified` (HK statement format incompatible).
  - `bond_payable`, `cip`, `invest_income`: `source_unavailable`.
- Focused verification: `438 passed`.
- `uv run ruff check .`: passed.

### Phase N: Expand Minimal Source Mapping From 15 To Full P0/P1 33 Fields

Goal: expand source-first coverage in three risk-graded layers (N1/N2/N3) only after HK 15-field terminal buckets and Phase M4 provider-semantics correction are stable.

Phase N is blocked until Phase M4 is complete. Do not use Phase N to hide unresolved provider semantics issues from the 15-field denominator.

Rationale for decomposition:

The 18 unmapped P0/P1 fields differ widely in difficulty. A one-shot expansion would produce many "yahoo_definition_unverified" or "mapping_expansion_required" buckets at once, making coverage numbers misleading. Layered expansion lets each layer reach explicit clean/non-clean conclusions before proceeding. See `docs/2026-05-08-roadmap-evaluation.zh.md` for the full analysis.

#### Phase N0: Catalog Consistency Gate (Prerequisite)

Goal: harden cross-catalog consistency before expanding the field denominator.

Deliverables:

- Add `tests/test_catalog_consistency.py` covering:
  - `coverage_matrix.primary_route` ↔ `source_mapping.primary_route`
  - `coverage_matrix.verification` ↔ `source_mapping.verification_status`
  - `provider_semantics.turtle_field_id` membership in `source_mapping` keys
  - `trust_policy.field_id` membership in `source_mapping` keys
  - `trust_policy.allowed_yahoo_raw_fields` ↔ `provider_semantics.raw_field_name`
- Tests must run as part of `uv run pytest -v`.

Exit criteria:

- Cross-catalog inconsistencies raise stable `ValueError` or test failures, not silent drift.
- Maintaining 5 field_catalog JSON files during Phase N1/N2/N3 has automated guardrails.

#### Phase N1: Low-Risk Direct Field Expansion (~10 fields)

Goal: add P0/P1 fields whose provider raw field name and Turtle semantics are direct enough to skip full provider-semantics-proof + trust-policy ceremony.

Target fields (all have provider baseline evidence and direct semantic mapping):

- `st_borr`, `lt_borr`, `accounts_receiv`, `acct_payable`, `inventories`, `fix_assets`, `money_cap`, `defer_tax_assets`, `minority_int`, `other_cur_assets`

Deliverables:

- Add source mapping entries for each field with AKShare and Yahoo aliases.
- For HK fields covered by Yahoo, reuse the M5 pattern: provider semantics rule + trust policy rule + source mapping update.
- For CN-only fields (AKShare direct), no trust policy needed; provider semantics still required.
- Update `provider_baseline_replay` so denominator reports both 15-field (compat) and 25-field views.

Exit criteria:

- 600519/00001/01113 replay covers 25 fields without changing provider fixtures.
- N1 fields are clean-present or explicit terminal bucket; no field stuck in unclassified state.
- Catalog consistency tests still pass.

#### Phase N2: Medium-Risk Format-Sensitive Fields (~4 fields)

Goal: add fields where HK statement format may diverge from CN/Yahoo semantics, requiring per-field investigation.

Target fields:

- `operating_cost`, `operating_profit`, `equity_attributable_to_owners`, `selling_general_administrative`

Deliverables:

- For each field, perform PDF investigation on 00001/01113 to confirm whether HK statement format supports direct row matching.
- Apply M3-M5 pattern: if directly verifiable, add provider semantics + trust policy; if not, assign explicit terminal bucket (e.g., `hk_statement_format_incompatible`, similar to `gross_profit`).
- Document findings in spec/plan for each field decision.

Exit criteria:

- N2 fields are clean-present (where format compatible) or explicit non-clean terminal (where not).
- HK-vs-CN coverage gap is explicit per field, not aggregated as "warnings".

#### Phase N3: High-Risk Market-Specific Fields (~4 fields)

Goal: handle fields that may be CN-A-share-specific or HK-notes-only, with high probability of source_unavailable for HK.

Target fields:

- `rd_exp`, `fv_value_chg_gain`, `non_oper_income`, `non_oper_exp`

Deliverables:

- Provider semantics investigation per field per market.
- Refined `source_unavailable` taxonomy:
  - `source_unavailable_hk_only` (CN has data, HK does not)
  - `source_unavailable_all_markets` (no provider has data)
  - `pdf_only_by_design` (taxonomy says PDF-only from the start)
- Trigger Phase H planning if multiple HK fields require PDF supplement.

Exit criteria:

- N3 fields explicitly assigned to one of: clean_present, source_unavailable variant, or pdf_required.
- 33-field denominator coverage is fully classified.
- Phase H scope can be defined based on actual `pdf_required` field list, not speculation.

### Phase N Implementation Result

Status: implemented on 2026-05-08. Source mapping catalog expanded from 15 to 33 P0/P1 fields in four sub-phases.

Implementation results:

- **Phase N0** (catalog consistency gate): Added `tests/test_catalog_consistency.py` with 6 cross-catalog invariant tests covering source_mapping ↔ coverage_matrix, source_mapping ↔ taxonomy, provider_semantics ↔ source_mapping, trust_policy ↔ source_mapping, trust_policy ↔ provider_semantics, and priority list ↔ source_mapping.
- **Phase N1.A**: Added inventories, money_cap, minority_int (simple `cash`-like pattern, no trust policy).
- **Phase N1.B**: Added defer_tax_assets.
- **Phase N1.C**: Added fix_assets, st_borr, lt_borr, accounts_receiv, acct_payable, other_cur_assets.
- **Phase N2**: Added operating_cost, operating_profit, equity_attributable_to_owners, selling_general_administrative.
- **Phase N3**: Added rd_exp, fv_value_chg_gain, non_oper_income, non_oper_exp (CN-only fields, HK marked source_unavailable or mapping_expansion_required by design).

Final 33-field coverage:

| Company | Market | Clean Present |
|---------|--------|---------------|
| 600519 | CN | 27/33 |
| 00001 | HK | 20/33 |
| 01113 | HK | 21/33 |

Key architectural validation:

- The simple source_mapping pattern (no trust policy) handles direct-match fields cleanly.
- The architecture correctly surfaces conflicts (fix_assets 00001 due to Yahoo Net PPE including ROU; accounts_receiv/acct_payable HK due to PDF combined lines), source_policy_resolvable cases (st_borr/lt_borr 600519 because Maotai has no debt), and mapping_expansion_required (other_cur_assets 00001, non_oper_income/exp HK).
- Phase H/I triggers are now concrete: HK conflict fields (fix_assets, accounts_receiv, acct_payable) need PDF supplement; HK source_unavailable fields (bond_payable, cip, invest_income, rd_exp, fv_value_chg_gain) need either PDF extraction or accepted as out-of-scope.
- All 444 tests pass; ruff clean.

### Phase H/I: Concrete Trigger Set Identified Post-N

Status: triggers concrete after Phase N replay analysis (2026-05-08).

The full 33-field replay surfaced specific non-clean fields per company. They cluster into four buckets, each with a different fix path:

#### Bucket 1: Source Policy Repair (no fallback needed)

3 fields × 1 company. Maotai (600519) genuinely has no borrowings/bond debt; AKShare returns `None` which the current source_policy treats as unresolved instead of zero.

- 600519: `bond_payable`, `st_borr`, `lt_borr`

Fix: extend `source_policy.py` to recognize provider-returned `None` for known-zero balance sheet items as a deterministic zero, not a blocker. No PDF/LLM needed.

Estimated effort: small; new policy rule + tests.

#### Bucket 2: Phase H Deterministic PDF Verification

7 (company, field) pairs. Source value exists but cross-source conflict or single-source warning needs PDF check. Standard Phase H — selected-field PDF retrieval, no LLM.

- 600519: `revenue`, `operating_profit`, `selling_general_administrative` (cross-source conflicts)
- 00001: `inventories`, `fix_assets` (Yahoo Net PPE includes ROU; PDF Fixed assets row separates them)
- 01113: `fix_assets`
- 01113: `selling_general_administrative` (currently source_unavailable but PDF likely has it)

Fix: implement Phase H per existing spec (`docs/superpowers/specs/2026-05-01-phase-h-selected-pdf-evidence-supplement.md`). Reuse existing chunk/retrieval/evidence pipeline.

#### Bucket 3: Phase I LLM-Assisted Notes Extraction (HK only)

~10 (company, field) pairs. PDF main statements either combine lines or omit them entirely; the value is in notes/MD&A and requires LLM-level disambiguation.

- 00001 + 01113: `accounts_receiv` (PDF combines "Trade receivables and other current assets")
- 00001 + 01113: `acct_payable` (PDF combines "Trade payables and other current liabilities")
- 00001 + 01113: `rd_exp` (HK main statement has no R&D row; usually in MD&A)
- 00001 + 01113: `fv_value_chg_gain` (scattered across OCI and notes)
- 00001 + 01113: `bond_payable` (broken out by type in borrowings note)
- 00001 + 01113: `invest_income` (HK = Share of profits of joint ventures + Other income; needs aggregation judgment)

Fix: implement Phase I per existing spec (`docs/superpowers/specs/2026-05-01-phase-i-llm-assisted-ambiguity-review.md`). Use bounded LLM prompts with PDF chunk evidence. Evidence-grounded outputs only.

#### Bucket 4: Locked Terminal States (no fix attempted)

5 fields (mostly HK). Field is either format-incompatible or not applicable to the company/market.

- HK 00001 + 01113: `gross_profit` (`yahoo_definition_unverified` — HK income statement format incompatible, confirmed in M5)
- HK 00001 + 01113: `cip` (HK companies often have no construction-in-progress line)
- HK 00001 + 01113: `non_oper_income`, `non_oper_exp` (CN A-share concepts; HK reports no equivalent)
- HK 00001: `other_cur_assets` (Yahoo doesn't return; PDF doesn't have a discrete row)

Fix: extend the `source_unavailable` taxonomy from Phase N3 plan to distinguish these terminal states explicitly, e.g. `hk_format_incompatible`, `not_applicable_for_market`, `pdf_only_terminal`. Update warning_classification to surface them. No further extraction work.

#### Phase Ordering

Recommended order (smallest-cost first, biggest-coverage-gain first):

1. **Bucket 1 source policy fix**: brings 600519 to 30/33 quickly.
2. **Bucket 4 terminal state taxonomy**: clarifies the 5 fields that cannot be improved, reducing apparent gap.
3. **Phase H (Bucket 2)**: deterministic PDF retrieval for 7 conflict fields. Uses existing infrastructure.
4. **Phase I (Bucket 3)**: LLM-assisted extraction for 10 HK notes-level fields. Highest cost, biggest HK coverage gain.

Expected coverage after each step:

| Step | 600519 | 00001 | 01113 |
|------|--------|-------|-------|
| Current | 27/33 | 20/33 | 21/33 |
| After Bucket 1 | 30/33 | 20/33 | 21/33 |
| After Phase H | 30/33 | 22/33 | 23/33 |
| After Phase I | 30/33 | 28-30/33 | 28-30/33 |
| Locked terminal | 30/33 | ~30/33 | ~30/33 |

The 3 unreachable fields per company become explicit terminal states rather than failures.

### Phase H0 Implementation Result

Status: implemented on 2026-05-08. See:
- `docs/superpowers/specs/2026-05-08-phase-h0-null-as-zero-policy.md`
- `docs/superpowers/plans/2026-05-08-phase-h0-null-as-zero-policy.md`

Goal: Resolve Bucket 1 by adding null_means_zero source mapping policy.

Implementation result:

- Added `null_means_zero: bool` field to `SourceMappingEntry`.
- `_candidate_from_record` produces a zero-valued candidate when policy applies and provider returns null with status=present.
- Candidate emits review note `null_interpreted_as_zero` for audit trail (flows to `MappedTurtleField.review_notes` in JSON artifacts; does not reach `SourceFirstExportItem.review_notes`, preserving clean_present status).
- Applied to `bond_payable`, `st_borr`, `lt_borr` in source_mapping catalog.
- 600519 clean present: 27/33 → 30/33.
- 00001/01113 unchanged (no null records for these fields in HK data).

Bucket 1 closed. Next: Bucket 4 (locked terminal taxonomy) → Phase H deterministic PDF verification.

### Phase H1 Implementation Result

Status: implemented on 2026-05-08, then partially reverted on 2026-05-08 after reviewer identified source-first violations. See:
- `docs/superpowers/plans/2026-05-08-phase-h1-surgical-conflict-resolution.md`

Goal: Resolve 7 (company, field) conflict pairs via JSON catalog adjustments + provider_semantics rules only. No PDF pipeline required.

Changes implemented (surviving, architecturally valid):

1. **CN revenue/operating_profit**: disabled Yahoo cross-check route (`cross_check_routes: []`, `on_conflict: "preserve_conflict"`) in source_mapping CN market_policies. AKShare alias order reverted: `OPERATE_INCOME` (营业收入) is primary; `TOTAL_OPERATE_INCOME` (营业总收入) is related. Both sources have different values so these fields remain `unresolved_conflict` for 600519 — architecturally honest.

2. **HK fix_assets**: added two `provider_semantics_unverified` rules to `provider_raw_semantics_hk.json`:
   - Yahoo `Net PPE`: includes ROU assets for some issuers (00001: Fixed assets 100,080 + ROU 59,160 = Yahoo 159,240) but matches directly for others (01113). Per-issuer divergence prevents primary promotion.
   - AKShare `固定资产`: values do not match PDF Fixed assets for sampled HK issuers (00001: 90,394 vs PDF 100,080; 01113: 65,816 vs PDF 72,868).
   Both providers locked as terminal non-clean for HK fix_assets.

3. **HK inventories**: added `provider_semantics_sample_verified` rule to `provider_raw_semantics_hk.json` and `yahoo_pdf_verified` rule to `hk_yahoo_trust_policy.json`. Yahoo `Inventory` verified against PDF for both 00001 (Inventories 26,688 HKD million) and 01113 (Properties for sale 122,799 HKD million — IAS 2 inventory for real estate developers). Added `source_policy.market_policies.HK` to inventories source_mapping with `yahoo_direct` primary.

Reverted (source-first violations, flagged in review):

- **Revenue alias swap**: Swapping `TOTAL_OPERATE_INCOME` to first alias position silently changed Turtle revenue semantics from 营业收入 (168,838M) to 营业总收入 (172,054M) for 600519. Reverted: `OPERATE_INCOME`/`营业收入` is primary again, `TOTAL_OPERATE_INCOME`/`营业总收入` is related.
- **SGA primary switch to Yahoo**: Switching SGA primary to Yahoo without provider_semantics proof violated source-first. Yahoo SGA (11,787M) ≠ AKShare MANAGE_EXPENSE (8,320M) + SALE_EXPENSE (7,253M = 15,573M). AKShare aliases restored; field stays non-clean for CN.
- **operating_profit Yahoo alias**: `Total Operating Income As Reported` added without provider_semantics proof. Removed.

Implementation result (post-revert):

- 600519: 30/33 → **30/33** clean (revenue/operating_profit/SGA remain unresolved_conflict; no false promotions)
- 00001: 20/33 → **21/33** clean (inventories becomes clean_present)
- 01113: 21/33 → **21/33** clean (no net change; fix_assets was already non-clean, inventories was already clean)

The "33/33 clean for 600519" was reached by silent definition changes, not by source-first proof. After revert, 600519 stands at 30/33 — the architecturally honest state.

All 450 tests pass.

### Phase I-D Implementation Result

Status: implemented on 2026-05-08. See:
- `docs/superpowers/specs/2026-05-08-phase-i-d-smoke-test-llm-field-extraction.md`
- `docs/superpowers/plans/2026-05-08-phase-i-d-smoke-test-llm-field-extraction.md`

Goal: Verify LLM extraction framework end-to-end before notes-level extraction (Phase I-A).

Implementation result:

- New module `src/financial_report_llm_extractor/llm_field_extraction.py` with `FieldExtractionRequest`/`FieldExtractionResult` dataclasses, deterministic JSON-schema prompt builder, `JsonClient` Protocol, `run_field_extraction` runner with raw response archival.
- Prompt builder defensively handles both chunk schemas (`page` single int OR `page_start`/`page_end` pair).
- Chunk fixture committed at `tests/fixtures/pdf_chunks/00001_2025_chunks.jsonl` (12 chunks from page 134 of 00001 annual report; 5.5KB; revenue value 280,036 confirmed present).
- 9 unit/integration tests against FakeJsonClient pass.
- 1 opt-in real-LLM smoke test (`REAL_LLM_SMOKE=1` + `LLM_CONFIG_PATH=...`) extracts 00001 revenue and asserts within ±5% of 280,036,000,000 HKD.
- Smoke runner script at `scripts/run-llm-field-extraction-smoke.sh`.
- 459 tests passing, 1 skipped (real LLM smoke).

Phase I-A (HK notes-level extraction) builds on this module. Field-specific prompt overrides come when notes-pattern failures surface.

### Phase I-A Implementation Result

Status: implemented on 2026-05-08. See:
- `docs/superpowers/specs/2026-05-08-phase-i-a-llm-notes-extraction.md`
- `docs/superpowers/plans/2026-05-08-phase-i-a-llm-notes-extraction.md`
- `scripts/phase_i_a_demo/REPORT.md` (feasibility demo)
- `scripts/phase_i_a_demo/VALIDATION.md` (production validation)

Goal: Generalizable LLM-assisted field extraction for HK fields where source-first replay produces source_unavailable / mapping_expansion_required.

Implementation:

- New module `src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py` with `LlmExtractionTarget`, `derive_targets`, `select_chunks` (alias_top_k or broad_keyword), `extract_for_chunks`, `write_llm_evidence_supplement`.
- New CLI `extract-llm` subcommand: ingests + chunks a PDF, derives targets from catalog metadata, runs LLM per field, writes `llm_evidence_supplement.json`.
- `provider_baseline_replay` half-integration: detects per-company `llm_evidence_supplement.json` and merges `present` values into export for fields source-first didn't cover. Never overrides clean source values.

Validation across 6 HK companies × 6 target fields = 36 (company, field) extractions:

| Field | 00001 | 01113 | 01810 | 02498 | 06862 | 09987 |
|-------|-------|-------|-------|-------|-------|-------|
| accounts_receiv | ✓ 14,952 | ✓ 2,028 | ✓ 12,662,060 | ✓ 410,611 | ✓ 346,347 | ✓ 95 |
| acct_payable | ✓ 22,632 | ✓ 3,607 | ✓ 98,280,585 | ✓ 475,825 | ✓ 1,796,362 | ✓ 793 |
| bond_payable | ✓ 165,366 | ✓ 51,400 | N/A | N/A | ✓ 2,027,867 | N/A |
| fv_value_chg_gain | N/A | N/A | ✓ 1,050,800 | ✓ 2,799 | ✓ 194,297 | N/A |
| invest_income | N/A | N/A | N/A | N/A | N/A | N/A |
| rd_exp | N/A | N/A | ✓ 24,050.5 | ✓ 615,434 | N/A | ✓ 8 |

- Present: 21/36 (58%); Not found: 15/36 (42%); Failed: 0/36
- Most `not_found` are architecturally correct (company doesn't disclose the field).
- Outlier: `invest_income` is `not_found` for all 6 companies — suggests its `pdf_aliases`/description need iteration. Phase I-A.2 candidate.

Cross-company generalization confirmed:
- Zero per-company code or catalog changes
- 4 of 6 companies (01810, 02498, 06862, 09987) had never been used during prior source-first phases
- Same code handled CK Hutchison (telecom conglomerate), CK Asset (real estate), Xiaomi (tech), Haidilao (restaurants), Yum China — vastly different layouts and currencies (HKD/RMB)
- Bilingual Chinese/English labels handled (06862)
- 478 tests passing, ruff clean

Phase I-A.2 follow-ups (status):
1. ~~`invest_income` aliases expansion (HK joint-venture profit-sharing patterns)~~ **DONE 2026-05-08** — expanded pdf_aliases 1 → 7 + HK-specific description + aggregation guidance. 0/6 → 5/6 (83%) present. Catalog-only change; field-scoped maintenance validated. Overall coverage 21/36 → 26/36 (72%).
2. ~~Confidence calibration against human-verified accuracy~~ **FRAMEWORK DONE 2026-05-08** — `--confidence-threshold` added to `extract-llm` and `extract-llm-batch`. Below-threshold `present` results demoted to `extraction_failed` with `low_confidence` error. Calibration workflow documented in `scripts/phase_i_a_demo/CALIBRATION.md`. Actual threshold value deferred until ~50+ labeled (company, field) pairs collected.
3. ~~Concurrent multi-company runner~~ **DONE 2026-05-08** — new `extract-llm-batch` CLI + `structured_sources/llm_extraction_batch.py` module. ThreadPoolExecutor for IO-bound LLM/pdftotext. Per-company failure isolation. Default 3 workers configurable via `--workers`. JSON manifest input.
4. ~~Restrict supplement merge to combined slice~~ **DONE 2026-05-08** — gate added in `_write_slice` + integration test
5. ~~`selected_source="llm"` namespace clarification~~ **DONE 2026-05-08** — inline comment documenting non-provider evidence source
6. ~~CLI extract-llm subprocess → Python API~~ **DONE 2026-05-08** — direct `ingest_pdf` and `build_chunk_store` calls; eliminates subprocess overhead

Phase I-A.2 closed. All identified follow-ups addressed (1, 4, 5, 6 fully; 2 framework + deferred calibration; 3 fully). Next phases: Phase H deterministic PDF supplement (the 7 conflict fields from Bucket 2), or Phase N4 expansion to P2/P3 fields.

### Phase N4 Implementation Result (P2 + P3 expansion)

Status: implemented on 2026-05-09. Source mapping expanded from 33 (P0+P1) to 44 fields (P0+P1+P2+P3 partial).

#### Phase N4.A: P2 source-first (8 fields)

Added 8 P2 cash-flow + utility fields with provider data:
- `change_in_receivables`, `change_in_payables`, `change_in_inventory` — Yahoo direct
- `receiv_tax_refund` — AKShare CN-only
- `repurchase_of_stock` — Yahoo direct
- `dividends_paid` — Yahoo + AKShare
- `capital_expenditures` — Yahoo direct
- `depreciation_amortization` — Yahoo direct

Coverage gain after N4.A:
- 600519: 30/33 (P0+P1) → **33/41** (P0+P1+P2)
- 00001: 21/33 → **26/41**
- 01113: 21/33 → **28/41**

#### Phase N4.B: P2 LLM fallback (1 field) + HK gap validation

Added `stock_based_compensation` (P2) — no provider data, LLM-only via `extract-llm`. Validated 4 P2 fields × 6 HK companies via batch LLM:
- 7/24 present (01810/02498 tech-style companies have R&D, fv_value_chg_gain, SBC)
- 17/24 architecturally correct not_found (CK conglomerate / Haidilao restaurant / etc. don't disclose these)

#### Phase N4.C: P3 selective expansion (2 fields)

Added 2 P3 fields with provider data:
- `interest_paid_cash` — Yahoo `Interest Paid Cfo`
- `bad_debt_provision` — Yahoo `Allowance For Doubtful Accounts Receivable`

Remaining 12 P3 fields are taxonomy-marked `pdf_only` (text values: dividend_plan, receivables_aging, contingent_liabilities, segment_revenue_profit, etc.). Deferred to a future Phase I-C (text-mode LLM extraction).

#### Final coverage

| Company | P0+P1 (M5) | + P2 (N4.A/B) | + P3 partial (N4.C) |
|---------|-----------|---------------|---------------------|
| 600519 | 30/33 | 33/42 | TBD |
| 00001 | 21/33 | 26/42 | TBD |
| 01113 | 21/33 | 28/42 | TBD |

**Total mapped fields: 44** (P0:22 + P1:11 + P2:9 + P3:2). 18 P3/P4 fields remain unmapped (mostly text-mode notes/MDA disclosures requiring future text-extraction phase).

491 tests passing, ruff clean. for batch onboarding

### Phase I-C Implementation Result

Goal: Enable text-mode LLM extraction for the 12 remaining P3 `pdf_only` fields (7 text-typed + 5 money-typed) so the catalog covers all P0–P3 fields.

Changes:
- `llm_field_extraction.py::_parse_response`: gate Decimal parsing to `value_type in {money, number}`. Text fields (e.g., `dividend_plan`, `segment_revenue_profit`) preserve narrative `value` without `extraction_failed` errors.
- `turtle_v015_source_mapping_minimal.json`: added 12 P3 entries with `pdf_aliases` covering EN+ZH variants. 7 text-typed (dividend_plan, buyback_cancellation_progress, receivables_aging, related_party_receivables_payables, contingent_liabilities_commitments, lease_liability_maturity, segment_revenue_profit) + 5 money-typed (capitalized_rd, capitalized_interest, restricted_cash, time_deposits_or_wealth_products, dps).
- P3 priority list expanded from 2 → 14 fields.
- New unit test `test_extract_text_field_skips_decimal_parse` covers text-mode path.

**Total mapped fields: 56** (P0:22 + P1:11 + P2:9 + P3:14). 6 P3/P4 fields remain unmapped (deeper notes-only disclosures with weak retrieval signal).

Live LLM batch validation (2026-05-09): `extract-llm-batch --priorities=P3` against 6 HK companies × 14 P3 fields = 84 (company, field) pairs. DeepSeek `deepseek-chat`, 3 workers.

| Field | 00001 | 01113 | 01810 | 02498 | 06862 | 09987 | Hits |
|-------|-------|-------|-------|-------|-------|-------|-----:|
| bad_debt_provision | P | P | P | P | – | P | 5/6 |
| contingent_liabilities_commitments | P | P | P | P | P | – | 5/6 |
| dividend_plan | P | P | P | P | P | – | 5/6 |
| segment_revenue_profit | P | – | P | – | – | P | 3/6 |
| time_deposits_or_wealth_products | – | – | – | P | P | P | 3/6 |
| dps | P | P | – | – | – | – | 2/6 |
| related_party_receivables_payables | – | – | – | P | P | – | 2/6 |
| restricted_cash | – | – | P | P | – | – | 2/6 |
| buyback_cancellation_progress | – | – | P | – | – | – | 1/6 |
| capitalized_interest | P | – | – | – | – | – | 1/6 |
| lease_liability_maturity | – | – | – | – | – | P | 1/6 |
| capitalized_rd | – | – | – | – | – | – | 0/6 |
| interest_paid_cash | – | – | – | – | – | – | 0/6 |
| receivables_aging | – | – | – | – | – | – | 0/6 |

**Summary**: present 30/84 (36%), not_found 54/84 (64%), failed 0.

- **Text-mode gate verified**: 0 `extraction_failed` across 42 (company, text-field) pairs. Narrative values (e.g., 00001 dividend_plan: "HK$1.602 per share final dividend …", 09987 lease_liability_maturity: "$68 million undiscounted minimum lease payments") preserved as raw `value` without Decimal parsing errors.
- **Money-mode regression intact**: text-typed extractions don't pollute numeric path. 00001 `dps`=2.312, `capitalized_interest`=21, 02498 `restricted_cash`=5198, 06862 `time_deposits_or_wealth_products`=4326614 all parsed correctly.
- **3 fields with 0 hits across all 6 companies**: `capitalized_rd`, `interest_paid_cash`, `receivables_aging`. Likely needs `pdf_aliases` iteration (Phase I-A.2 pattern: invest_income went 0/6 → 5/6 after alias expansion).
- **Most non-zero `not_found` results are architecturally correct**: e.g., 06862 (Haidilao) has no `dps` because it suspended dividends; 01113 (CK Asset) has no `capitalized_interest` because real-estate developers expense interest.

Artifacts: `tmp/runs/phase_i_c_validation/{00001,01113,01810,02498,06862,09987}/llm_evidence_supplement.json`.

493 unit tests + ruff + mypy clean.

#### Phase I-C.1 Follow-Up: Whitespace-Normalized Alias Retrieval

Investigation of the 3 zero-hit fields revealed a **chunk retrieval defect** rather than weak aliases. PDFs (via `pdftotext -layout`) wrap multi-word phrases mid-sentence, so chunks contain `"Aging analysis of trade and notes\nreceivables ..."` with internal newlines. The previous `select_chunks` used `text.lower().count(alias)` substring matching which scored 0 against the catalog's single-spaced alias `"aging analysis of trade and notes receivables"`. Aliases ≥4 words were silently dropped by retrieval before the LLM saw any chunks.

PDF spot-check first established that 4 of 6 zero-hit (company, field) pairs were architecturally correct terminal states (e.g., 01810/02498 explicitly disclose `"no significant development expenses had been capitalized"`; 06862/09987 have no receivables ageing at all). The remaining 2 (01810 receivables_aging, 06862 bad_debt_provision) had legitimate disclosures blocked by the retrieval bug.

Fix:
- `llm_extraction_runner.py::select_chunks`: collapse whitespace (`re.sub(r"\s+", " ", text)`) on both alias and chunk text before substring count, so multi-word aliases survive PDF line-wrap. Code change is contained to the `alias_top_k` branch.
- New unit test `test_select_chunks_alias_top_k_matches_across_pdf_layout_whitespace` covers the regression.
- `receivables_aging.pdf_aliases`: extended from 3 → 9 entries to include US `aging` spelling and the `"... trade and notes receivables"` HK telecom variant observed in 01810.

Re-run on identical 6×14 grid:

| Δ from v1 | 00001 | 01113 | 01810 | 02498 | 06862 | 09987 | New hits |
|-----------|-------|-------|-------|-------|-------|-------|----------|
| bad_debt_provision | – | – | – | – | **+P** | – | 1 (RMB 2,670 thousand) |
| lease_liability_maturity | – | – | **+P** | – | – | – | 1 (RMB 45,990 thousand total) |
| receivables_aging | – | – | **+P** | – | – | – | 1 (RMB Up-to-3-months 12,652,651 thousand etc.) |

**v2 summary**: present 33/84 (39%), not_found 51/84 (61%), failed 0. The 3 remaining 0/6 fields (`capitalized_rd`, `interest_paid_cash`, plus all-not_disclosed cohort) are confirmed terminal — `capitalized_rd` is architecturally not-disclosed by the sampled HK issuers, and `interest_paid_cash` is covered by Yahoo `Interest Paid Cfo/Cff/Direct` source path (LLM 0/6 is orthogonal to source-first coverage).

Artifacts: `tmp/runs/phase_i_c_validation_v2/{00001,01113,01810,02498,06862,09987}/llm_evidence_supplement.json`.

494 unit tests + ruff + mypy clean.

### Phase EC Implementation Result (evaluate-company orchestrator)

Status: implemented on 2026-05-09. See:
- `docs/superpowers/specs/2026-05-09-evaluate-company-orchestrator-design.md`
- `docs/superpowers/plans/2026-05-09-evaluate-company-orchestrator.md`

Goal: per-(company, period) validation orchestrator usable as the regular regression check after catalog / source policy / LLM prompt changes.

Design decisions (locked during brainstorming):
- Two-step CLI: `fetch-source-inventory` (live AKShare/Yahoo, opt-in) + `evaluate-company` (deterministic from cache + optional LLM if PDF set).
- `PERIOD_END=YYYY-MM-DD` canonical; `YEAR=YYYY` shortcut. TTM/interim future-extensible via `report_type`.
- Bucket cascade: `unresolved_conflict → llm_supplement_present → clean_present → terminal_unverified → not_in_scope → source_unavailable`. Buckets derived from per-(company, field, market) `WarningCategory` (no global field lists). CN gross_profit cleanly via akshare → `clean_present` (regression test locks this).
- evaluation.json/.md outputs full 6-bucket distribution per priority — no `% clean` framing per drift §177.

Key implementation steps:
1. Refactor `provider_baseline_replay._write_slice` → public `evaluate_source_first_slice`; extend return dict with `export_object` + `warning_classification_object` so the orchestrator can reuse the slice without re-deriving.
2. New `source_inventory_fetch.py`: `PeriodSpec` dataclass (annual/half_year/quarterly/ttm) + fail-loud `select_records_for_period` filter + `fetch_source_inventory` that wraps existing `AkshareAdapter` / `YahooAdapter` primitives.
3. New `company_evaluation.py`: `classify_field` 6-bucket cascade + `build_company_evaluation` priority×bucket aggregator + `render_evaluation_markdown` (no `% clean`) + `run_company_evaluation` orchestrator.
4. New CLI subcommands `fetch-source-inventory` + `evaluate-company` with env-driven shell wrappers.
5. **Critical fix surfaced by live run**: `evaluate_source_first_slice` had hardcoded `if output_dir.name == "combined"` gate for LLM supplement merge — never fired for orchestrator's out_dir. Fixed by adding explicit `llm_supplement_path` parameter; orchestrator now passes `out_dir / "llm_evidence_supplement.json"` directly.

Live validation on 600519 / 2024 (CN, AKShare+Yahoo fixture replay + DeepSeek LLM on PDF):

| Run | Coverage |
|-----|----------|
| P0–P3, no LLM | 15 clean / 39 unresolved_conflict / 1 terminal_unverified (net_profit pdf_verification_required) / 1 source_unavailable |
| P3 only, with PDF + DeepSeek | 1 clean / 5 llm_supplement_present (capitalized_rd 101,596,919 CNY, dividend_plan, contingent_liabilities_commitments, buyback_cancellation_progress, related_party_receivables_payables) / 8 unresolved_conflict |

CN `gross_profit` lands in `clean_present` (yahoo: 160,354,587,590 CNY) — verified by `test_classify_cn_gross_profit_clean_not_terminal`.

515 unit tests + ruff + mypy clean. 9 commits across the orchestrator branch.

#### Conflict root-cause analysis (600519 / 2024 baseline)

The 25 `normalized_value_conflict` fields decompose into 3 categories:

| Category | Count | Pattern | Fix |
|----------|------:|---------|-----|
| **Period string drift** | 16 | AKShare `"2024-12-31 00:00:00"` vs Yahoo `"2024-12-31"`; identical normalized values; reconciliation reports "candidate periods differ" | reconciliation period normalization (`period.split(" ")[0]`) — ~5 LoC |
| **Sign convention** | 3 | `capital_expenditures`, `interest_paid_cash`, `dividends_paid` — Yahoo cash-flow-outflow=negative vs AKShare = positive; same fact, opposite sign | per-field `provider_sign_conventions` rule in catalog |
| **True semantic gap** | 5 | revenue (营业收入 vs 营业总收入, 1.86% Δ), operating_profit (1.18%), SGA (10.11%), depreciation_amortization (16.64%), dividends_paid (after sign-adjust 2.9%) | Phase H2-style surgical resolution per field (8-10h) |

Plus 14 `missing_source_candidate` fields (P2/P3 with single-source coverage, e.g. `repurchase_of_stock`, `stock_based_compensation`) — architecturally correct, not real conflicts.

**Insight**: 16/39 (41%) of "conflict" reports are spurious false-positives from period string formatting. Tier 1 follow-up (period normalization) is near-free and would drop 600519 from 39 → ~23 conflicts immediately, exposing the real semantic work for Phase H2.

### Phase EC Follow-Ups (post-merge)

Tier 1 — small fixes (~150 LoC, 1-2h, can land in this branch):

- **Period string normalization in reconciliation** to clear 16 false-positive conflicts.
- **Markdown candidate-value rendering**: `unresolved_conflict` rows currently show empty value column; render `akshare:170.9B / yahoo:174.1B (Δ 1.9%)` so reviewers can triage without opening source_policy_report.json.
- **Drop or wire 3 dead parameters**: `inventory_summary_path`, `build_company_evaluation.supplement`, `fetch_source_inventory.catalog_path`.
- **Move `_FakeAkshareClient` to `tests/conftest.py`** to remove the cross-test sys.path hack.
- **`Decimal` JSON formatting**: prevent scientific notation (`format(value, "f")`) in evaluation.json.

Tier 2 — separate phases (out of branch scope):

- ~~**Phase H2 candidate**: surgical resolution of the 3 sign-convention + 5 true-semantic-gap CN fields.~~ **DONE 2026-05-09** — see Phase H2 Implementation Result below.
- **Coverage delta tool** (`evaluate-company-diff`): compare two evaluation.json files, surface bucket migrations.
- **`_run_llm_supplement_step` test with FakeJsonClient + canned chunks** to cover the LLM-merge path end-to-end without real API calls.
- **HK orchestrator coverage**: H2 live runs on 00001/01113 surfaced 0/56 clean. Pre-existing fixture/catalog gap, not H2 regression. Worth a dedicated phase.

### Phase H2 Implementation Result

Status: implemented on 2026-05-09. 5 commits (`1428281` → `568063e` → `769117e` → `ac3660b` → docs).

See:
- Spec: `docs/superpowers/specs/2026-05-09-phase-h2-cn-hk-conflict-surgical-resolution.md`
- Plan: `docs/superpowers/plans/2026-05-09-phase-h2-cn-hk-conflict-surgical-resolution.md`
- Validation report: `docs/phase_h2_validation_report.md`

Goal: surgical resolution of the 7 normalized_value_conflict fields surfaced by Phase EC live run on 600519/2024.

**Module A** — `MarketSourcePolicy.sign_normalize` ("raw" | "absolute") + reconciliation `abs()` comparison branch. Applied to `capital_expenditures` + `interest_paid_cash` (CN+HK). 2 fields move from `unresolved_conflict` → `clean_present`.

**Module B** — per-field PDF semantics proof:

- **Promoted** (CN): `revenue` (akshare OPERATE_INCOME 170,899,152,276.34 = PDF 营业收入 EXACTLY; Yahoo Total Revenue includes finance subsidiary 利息收入), `operating_profit` (akshare OPERATE_PROFIT 119,688,579,453.23 = PDF 营业利润 EXACTLY; Yahoo Operating Income excludes adjustments). New `field_catalog/provider_raw_semantics_cn.json` with `provider_semantics_sample_verified` rules.
- **Locked terminal_unverified** (CN+HK): SGA (catalog derivation only supports `A-B` subtraction; addition for MANAGE+SALE_EXPENSE deferred to Phase H2.1), D&A (FA_IR_DEPR vs D&A semantically unequal), dividends_paid (sign-normalized residual 2.9% gap from 已付/宣告 timing). 6 `provider_semantics_unverified` rules added (3 CN + 3 HK).
- HK side: revenue + operating_profit also marked `provider_semantics_unverified` (AKShare 营运收入 listed-company-only vs HKFRS Total Revenue including share of associates per Note 1).

**Architecture additions**:
- Market-agnostic `_apply_provider_semantics_promotion` in `source_policy.py` — replaces 5 `_apply_hk_yahoo_trust_policy` callsites with a `_apply_trust_policies` chain. Conservative: only clears `semantic_mismatch` + `normalized_value_conflict` from `conflict_classifications` when rule is `provider_semantics_sample_verified` + `allowed_as_primary=True`. Trust evidence dict records `proof_class=sampled_pdf_policy_proof, is_final_pdf_evidence=False`.
- `_load_replay_provider_semantics_catalog` now merges HK + CN catalogs (when both files present). Orchestrator path also wired (Task 3 pivot).

**Live validation (600519/2024-12-31)**:

| Bucket | Phase EC final | Phase H2 final | Δ |
|--------|----------------|----------------|---|
| clean_present | 34 | **38** | **+4** |
| unresolved_conflict | 21 | **17** | **−4** |
| terminal_unverified | 0 | 0 | 0 |
| source_unavailable | 1 | 1 | 0 |

Fields promoted: capital_expenditures, interest_paid_cash, revenue, operating_profit. Other 7 conflict-flagged fields remain non-clean by explicit `provider_semantics_unverified` rule (4 fields × 2 markets including Yahoo HK Operating Income; SGA + D&A + dividends_paid + HK revenue/operating_profit).

**HK live runs on 00001/01113**: both 0 clean / 56 unresolved_conflict. Not a Phase H2 regression — most HK fields land in `unresolved_conflict` with reason `missing_source_candidate` (no AKShare alias matches the fixture rows) or `currency_as_unit` / `statement_metadata_unproven`. H2 specifically targets `normalized_value_conflict`; the HK gap is upstream of H2's scope.

515 → 524 unit tests, ruff + mypy clean throughout. 9 new tests + 2 new files.

Phase H2.1 candidate identified: catalog `derivation` field extension to support addition (`A + B`) — would unlock CN SGA promotion. **DONE 2026-05-09** — see Phase H2.1 Implementation Result below.

### Phase H2.1 Implementation Result

Status: implemented on 2026-05-09. 5 commits + 1 follow-up test commit (`762994d` → `5058f16` → `9fc8d4c` → `56f1eda` → `0b6b397`).

See:
- Spec: `docs/superpowers/specs/2026-05-09-phase-h2-1-cn-sga-addition-derivation.md`
- Plan: `docs/superpowers/plans/2026-05-09-phase-h2-1-cn-sga-addition-derivation.md`
- PDF spot-check: `docs/phase_h2_1_sga_spot_check.md`
- Validation report: `docs/phase_h2_1_validation_report.md`

Goal: unlock CN SGA promotion via addition derivation `akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE`. Promotion gate sticks to H2 standard (AKShare derivation = PDF EXACT; no tolerance).

**Mechanism additions**:
- `mapping._derive_field` parser supports `+` operator (was: `-` only).
- New `_resolve_derivation_operand` helper handles `provider:RAW_FIELD_NAME` operand syntax — resolves directly from `SourceInventoryRecord` records, bypassing mapped Turtle field lookup. Cross-provider sums rejected (akshare:X + yahoo:Y).
- `source_policy._resolve_field` gained a `derived && not field.candidates` branch returning `selected_single_source` — necessary because derived fields don't carry per-source candidates.
- Catalog SGA: source_aliases emptied (akshare + yahoo) so `_map_direct_field` returns `status="missing"`, gating derivation to fire. New `derivation` field with the addition expression. `provider_raw_semantics_cn.json` SGA rule promoted unverified → sample_verified citing 600519/2024 PDF spot-check (销售费用 + 管理费用 = 14,954,950,119.87 EXACT).

**Live validation (600519/2024-12-31)**:

| Bucket | Phase H2 final | Phase H2.1 final | Δ |
|--------|----------------|------------------|---|
| clean_present | 38 | **39** | **+1** |
| unresolved_conflict | 17 | **16** | **−1** |

CN SGA → `clean_present | (derived) | 14954950119.87`.

**HK SGA classification change**: 00001 SGA went from clean_present (incidental Yahoo match) → source_policy_resolvable (catalog-driven). HK Yahoo SGA was `provider_semantics_unverified` per H2; the previous clean_present was not policy-justified. H2.1 makes the HK classification consistent with policy state. Future Phase H2.2 candidate for HK: PDF spot-check Yahoo HK SGA per-issuer + decide to promote or stay terminal.

**524 → 533 unit tests** (T1: +1, T2: +4, T4: +new SGA test + HK regression updates, T4-followup: +1 source_policy unit). Ruff + mypy clean throughout.

**Phase H2.2 candidates** identified:
- ~~Multi-company sample-verification~~ **DONE 2026-05-10** — see Phase H2.2 Implementation Result.
- ~~HK SGA via market-scoped source_aliases refactor~~ **DONE 2026-05-10** — see Phase H2.2 Implementation Result.
- `_resolve_derivation_operand` period-equality assertion (currently could silently sum across periods if multi-period inventory passed).

### Phase H2.2 Implementation Result

Status: implemented on 2026-05-10. 6 commits + 1 fetch fixture (`0faf829` → `8beee8d` → `8cd9857` → `e6ebec1` → `0a578a0` + spec/plan).

See:
- Spec: `docs/superpowers/specs/2026-05-09-phase-h2-2-multi-sample-and-market-scoped.md`
- Plan: `docs/superpowers/plans/2026-05-09-phase-h2-2-multi-sample-and-market-scoped.md`
- Multi-company spot-check: `docs/phase_h2_2_multi_company_spot_check.md`
- Validation report: `docs/phase_h2_2_validation_report.md`

Three independent sub-modules:

**Sub-A** — multi-company sample-verification: live `real_source_validation` (akshare 1.18.60) against 300750 (CATL battery) + 601919 (COSCO shipping) + 688008 (Hygon semiconductor) for FY2025 annual reports. PDF spot-check confirmed 12/12 applicable cells EXACT (5 fields × 3 companies, minus 3 PAY_INTEREST_COMMISSION cells N/A for non-financial issuers). `provider_raw_semantics_cn.json` revenue / operating_profit / SGA rules each gain 3 new sample companies (1 → 4 total). Drift §177 single-sample concern mitigated.

**Sub-B** — `SourceMappingEntry.by_market_aliases` schema + `mapping._record_matches_entry` market-scoped lookup precedence + `source_policy._apply_provider_semantics_unverified_warning` for unverified-rule-with-samples classification. Applied to HK SGA: catalog `source_aliases.by_market.HK.yahoo = ["Selling General And Administration"]` restored; PDF spot-check (00001 PDF "Office and general administrative expenses" 9,466M HKD vs Yahoo SGA 16,491M HKD) confirmed scope mismatch → rule stays `provider_semantics_unverified` with 2 samples documenting the divergence; HK 00001 SGA bucket transitioned `source_policy_resolvable` → `terminal_unverified` (architecturally honest).

**Sub-C** — `_collect_candidate_values` drops bucket filter; clean_present + llm_supplement_present rows with ≥ 2 candidates now display all provider values inline (e.g. `revenue: akshare:170.90B / yahoo:174.14B`). Audit transparency for sample-bias spot-checking.

**Live counts**:
- 600519/2024-12-31: clean_present 39 unchanged (Sub-A is documentation strengthening, no bucket movement).
- 00001/2025-12-31: 28 clean_present + **1 terminal_unverified** (SGA, was source_policy_resolvable).
- 01113/2025-12-31: 29 clean_present (SGA stays source_unavailable; no Yahoo SGA fixture record for 1113.HK).

**533 → 540 unit tests**, ruff + mypy clean. New regression tests: `test_phase_h2_2_promoted_cn_rules_have_multi_company_samples`, `test_phase_h2_2_hk_sga_yahoo_unverified_rule_exists`, `test_phase_h2_2_sga_catalog_has_by_market_hk_yahoo_alias`, plus 3 by_market mapping tests + Sub-C clean-row test.

**Phase H2.3 candidates** identified:
- ~~`interest_paid_cash` multi-sample: include a CN bank (e.g., 600036) where PAY_INTEREST_COMMISSION is non-null.~~ **Deferred — single-sample limitation persists; non-financial issuers structurally don't report PAY_INTEREST_COMMISSION. Low ROI without parallel financial-issuer onboarding.**
- ~~HK 01113 SGA: real-estate developer convention has no single SGA line; revisit as structurally non-applicable terminal vs `source_unavailable`.~~ **DONE 2026-05-10 as Phase HK-C** — see Phase HK-C Implementation Result below.
- ~~Persist 300750 / 601919 / 688008 records to `tests/fixtures/provider_captures/` for offline regression testing.~~ **DONE 2026-05-10 as Phase H2.3 #3** — see Phase H2.3 #3 Implementation Result below.
- `_resolve_derivation_operand` period-equality assertion (carried over from Phase H2.1) — still open.

### Phase H2.3 #3 Implementation Result

Status: implemented on 2026-05-10. Commit `ea5bd7d`.

Compressed `tmp/runs/h2_2_real_validation/source_inventory.jsonl` (2,238 records, 3 CN tickers: 300750/601919/688008) into `tests/fixtures/provider_captures/provider_field_baseline_h2_2_extension/source_inventory.jsonl.gz` (62KB). Backfilled `expected_provider_raw_value` + `period_end` on every CN sample-verified rule sample (4 companies × 3 fields = 12 cells across revenue/operating_profit/SGA). Added `derivation_legs: ["MANAGE_EXPENSE", "SALE_EXPENSE"]` marker to SGA rule so the regression test sums the right legs (`related_only_fields` carries negative examples like `TOTAL_OPERATE_INCOME` and must NOT be summed automatically).

Regression test (`tests/test_phase_h2_3_fixture_persistence.py`, 3 cases): walks every CN AKShare sample with `expected_provider_raw_value`, looks up the corresponding fixture record by (ticker, period, raw_field_code), asserts exact match. SGA derivation sums MANAGE+SALE legs from fixture and compares. **543 tests** (was 540).

H2.2 sample-verified evidence is now reproducible offline AND change-detectable.

### Phase HK-C Implementation Result

Status: implemented on 2026-05-10. Commit `087251e`. (Bucket impact: signal-quality only; no count change.)

01113/HK SGA (CK Asset, real-estate) was landing in `source_unavailable` with reason `source_policy_resolvable` — misleading because the real cause is industry convention (real-estate reports operating expenses by function without an aggregated SGA row), not "we didn't try hard enough".

Catalog mechanism: per-(field, market, ticker) `industry_not_applicable: [{market, ticker, reason}]` array. `IndustryNotApplicableSpec` frozen dataclass + JSON loader (fail-loud on malformed entries). `classify_field` gains optional `market` + `company_id` kwargs (non-breaking); after arriving at `source_unavailable`, walks the array for a (market, ticker) match and replaces the default reason with the catalog string. Reason override gated on `source_unavailable` bucket only — clean_present, llm_supplement_present, terminal_unverified are unaffected (otherwise we'd silently corrupt good data).

Tests (5 new, 548 total): catalog presence, loader surfaces tuple, override fires for matching (market, ticker), no override for non-matching, no override for non-source_unavailable buckets.

Deferred to a future phase (when ≥ 2 use cases accumulate): introduce a proper `not_applicable_terminal` bucket. Current XS approach reuses `source_unavailable` so we don't pay the bucket-expansion cost for one cell. Next likely use case: CN PAY_INTEREST_COMMISSION for non-financial issuers (would generalize the same mechanism).

### Phase H2.4 Implementation Result

Status: implemented on 2026-05-10. Commit `f760b31`. Cumulative review (`docs/2026-05-10-h2-hk-cumulative-review.md`) flagged 3 real issues, all empirically verified before fixing.

**Finding 1 (Medium) — derivation must be market-scoped**. Pre-fix: catalog `derivation: "akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE"` was global; `map_source_inventory` attempted it for every market when no direct candidate matched. For HK 01113, AKShare HK lacks MANAGE_EXPENSE/SALE_EXPENSE → SGA returned `status=blocked` with derivation-input errors. HK-C only patched the user-facing reason; the underlying mapping audit trail still showed spurious "blocked".

Fix: `derivation_markets: tuple[str, ...]` field on `SourceMappingEntry` (default empty = applies to all markets, back-compat). `map_source_inventory` derives current market from `records[0].market` and skips derivation when `entry.derivation_markets` is non-empty and current market not in it. SGA catalog gets `derivation_markets: ["CN"]`. HK 01113 SGA now `status=missing` cleanly → warning_classification → `source_unavailable` (the honest bucket, with HK-C real-estate reason still applied).

**Finding 2 (Medium) — derivation operands respect unit_multiplier**. Pre-fix: `_resolve_derivation_operand` set `value=rec.parsed_numeric_value` AND `normalized_value=rec.parsed_numeric_value` (silently same). Worked for current CN AKShare (unit_multiplier=1) by coincidence; any future provider raw operand in 千元/million scales would emit a wrong normalized_value with no audit trail.

Fix: route through `normalize_money(raw_value, unit_context)` like `_candidate_from_record` does. Now value, normalized_value, and canonical_unit derive correctly from the record's currency+unit. Regression test: synthetic 千元 records sum to 3000 千元 = 3,000,000 yuan normalized.

**Finding 3 (Low-Medium) — derived clean_present surfaces selected_source**. Pre-fix: `source_policy` derived branch returns `selection_status=selected_single_source` without `selected_candidate`; `export.py` only sets `selected_source` from `candidate.source`. Result: CN 600519 SGA exported as `status=present + value=14,954,950,119.87 + selected_source=null`. Source-first reviewability gap.

Fix: in `export.py _build_item`, after the selected-from-candidate block, fall back to deriving `selected_source` from `field.source_evidence` when (a) `selected_source` still None, (b) status==present, (c) all evidence shares a single provider. Multi-provider derivations are already rejected at `mapping.py:271-279`, so this stays deterministic. CN derived SGA now exports `selected_source="akshare"`.

Tests: `tests/test_phase_h2_4_review_fixes.py` (4 cases: 3 findings + CN regression guard). `tests/test_provider_baseline_replay.py` updated 01113 SGA expectation `source_policy_resolvable → source_unavailable`. **552 tests** (was 548).

### Phase HK-LLM-2 Implementation Result

Status: implemented on 2026-05-10. Commits `bbd6668` (recon) + `a2fe9c2` (regression lock).

**Recon finding** (`docs/phase_hk_llm_recon.md`): the LLM-orchestrator is **already wired** — `_run_llm_supplement_step` in `company_evaluation.py:448` runs Phase I-A's LLM runner when `--pdf` + `--llm-config` are passed; `provider_baseline_replay._merge_llm_evidence_supplement` merges results into export with `selected_source="llm"`; bucket cascade routes them to `llm_supplement_present`. The earlier "0 hits" observation was a misread of a single-field smoke test (`phase_i_c_alias_iter_1/01113/`, only attempting `receivables_aging`). Real HK runs under `phase_i_c_validation_v2/` show 33/84 = 39% present rate across 6 HK companies, matching the figure cited in CLAUDE.md.

Why H2.2 evals showed `llm_supplement_present=0`: those runs were invoked without `--pdf` + `--llm-config`. The orchestrator gate is intentional (LLM is opt-in to avoid burning API credits on baseline runs).

**Regression lock** (`tests/test_phase_hk_llm_2_supplement_merge.py`) replays existing supplement files against the current catalog and pins the per-company supplement delta. Initial HK-LLM-2 covered 3 companies; Phase C extended it to the full 6-HK cohort after live-fetching and persisting 4 new AKShare+Yahoo HK fixtures.

| Company | Source-first | +LLM | LLM-supplemented fields |
|---------|---:|---:|---|
| 600519/CN | 39/56 (70%) | **44/56 (79%)** | buyback_cancellation_progress, capitalized_rd, contingent_liabilities_commitments, dividend_plan, related_party_receivables_payables |
| 00001/HK | 28/56 (50%) | **33/56 (59%)** | capitalized_interest, contingent_liabilities_commitments, dividend_plan, dps, segment_revenue_profit |
| 01113/HK | 29/56 (52%) | **33/56 (59%)** | bad_debt_provision, contingent_liabilities_commitments, dividend_plan, dps |
| 01810/HK | 32/56 (57%) | **39/56 (70%)** | bad_debt_provision, buyback_cancellation_progress, contingent_liabilities_commitments, dividend_plan, lease_liability_maturity, receivables_aging, segment_revenue_profit |
| 02498/HK | 32/56 (57%) | **37/56 (66%)** | bad_debt_provision, contingent_liabilities_commitments, dividend_plan, related_party_receivables_payables, time_deposits_or_wealth_products |
| 06862/HK | 33/56 (59%) | **38/56 (68%)** | bad_debt_provision, contingent_liabilities_commitments, dividend_plan, related_party_receivables_payables, time_deposits_or_wealth_products |
| 09987/HK | 29/56 (52%) | **32/56 (57%)** | lease_liability_maturity, segment_revenue_profit, time_deposits_or_wealth_products |

Test mechanism: monkey-patches `_run_llm_supplement_step` to a no-op so no live LLM calls happen; pre-places existing supplement file in `out_dir`; calls `run_company_evaluation` with non-None dummy `pdf_path` + `llm_config_path` so the supplement-merge gate fires. Asserts exact baseline clean count, exact with-LLM total, AND exact field set in `llm_supplement_present` bucket so a regression surfaces named (not just count drift).

Guards against silent regressions in `_merge_llm_evidence_supplement`, the bucket cascade, and catalog changes that re-classify a previously-LLM-merged field as source-first clean. **563 tests** after the 6-HK extension.

**Phase HK-coverage** outcome: HK Bucket-A ("alias gap" closure) collapsed empirically to ~0 cells (`docs/phase_hk_coverage_discovery.md` reality-check). Most missing-candidate HK fields are genuinely absent from adapter outputs, not from catalog aliases. The honest path forward is **Phase HK-B** (sample-verified conflict resolution for `fix_assets`, `accounts_receiv`, `acct_payable`, `gross_profit`). The fixture prerequisite landed via `tests/fixtures/provider_captures/provider_field_baseline_hk_llm_6_extension/`; HK-B recon is in `docs/phase_hk_b_recon.md`. HK-B.1-.4 lock the 6-HK conflict shapes; HK-B.5 PDF spot-check then promoted `acct_payable` for 5 of 6 HK issuers (recon `docs/phase_hk_b_5_recon.md`).

### Phase MX Implementation Result

Status: implemented 2026-05-11. Documentation-hygiene audit triggered by the observation that the `coverage_matrix.json` `verification` field had drifted from runtime evidence — 38 of 62 fields were still flagged `expected` despite many having accumulated multi-issuer regression locks or `provider_raw_semantics` sample proofs.

Audit cross-referenced each `expected` field against: `provider_raw_semantics_cn.json` (CN sample rules), `provider_raw_semantics_hk.json` (HK terminal/unverified rules), `tests/test_provider_baseline_replay.py` clean-set expectations, `tests/test_phase_hk_llm_2_supplement_merge.py` LLM supplement field sets, and `tests/test_phase_hk_b_*.py` shape locks. Promotion threshold: ≥2 multi-issuer samples for source-first routes or ≥3 companies for LLM supplement evidence.

**11 fields promoted to `verified`** (matches drift §177 standard):

- P0 (6): `operating_profit`, `operating_cost`, `financing_cash_flow`, `investing_cash_flow`, `lt_borr`, `st_borr` — all backed by multi-company `clean_present` in `test_provider_baseline_replay.py` or by Phase H0 / Phase H2 promotions with audit trails.
- P3 (5): `contingent_liabilities_commitments`, `dividend_plan` (6 of 7 companies in HK-LLM-2 lock), `time_deposits_or_wealth_products`, `segment_revenue_profit`, `related_party_receivables_payables` (3 companies each, cross-market).

**Catalog invariant enforcement**: `field_metadata.py:215` requires a `verified` field's primary_route to also be `verified`. `bad_debt_provision` has 4 HK companies in HK-LLM-2 lock but its primary_route is `yahoo_direct` (Yahoo has no direct data; LLM is the actual evidence path) — kept `expected` with documented reason. A future MX iteration could restructure its primary_route to `pdf_evidence`.

**3 HK-B locked fields kept `expected` with enriched notes** documenting the lock state for future readers: `accounts_receiv` (HK-B.3), `acct_payable` (HK-B.1), `gross_profit` (HK-B.4).

**Result**: coverage matrix verification 24/62 → **35/62** (+11). Both `turtle_v015_coverage_matrix.json` and `turtle_v015_source_mapping_minimal.json` updated to keep `test_catalog_consistency.py::test_source_mapping_aligns_with_coverage_matrix` aligned. All 587 tests still pass.

### Phase HK-B.5 Implementation Result

Status: implemented 2026-05-11. Recon doc: `docs/phase_hk_b_5_recon.md`.

PDF spot-check across all 6 HK issuers confirmed Yahoo HK `Accounts Payable` = PDF pure trade payables (using each issuer's preferred terminology: `Trade payables` for Xiaomi/Anta/06862/HSBC, `Creditors` for CK Asset property co, `Accounts payable` for Yum China USD reporter). All 6 PDF values exactly match the corresponding Yahoo raw candidate.

**Critical discovery**: HK-B recon had assumed 01113 (CK Asset) was a likely terminal because the PDF didn't surface a "Trade payables" line in text extraction. The correct line is **"Creditors"** (Note 18, page 164) — a property-co HK/UK GAAP convention. Yahoo's value 3,607,000,000 HKD matches PDF Creditors 3,607 HKDM exactly, with formal aging analysis disclosed.

**Three catalog changes** wire the promotion:
1. `provider_raw_semantics_hk.json` — added Yahoo `acct_payable` `provider_semantics_sample_verified` rule.
2. `hk_yahoo_trust_policy.json` — added `acct_payable` rule with 6 PDF samples.
3. `turtle_v015_source_mapping_minimal.json` — added `source_policy.market_policies.HK` (`primary_route: yahoo_direct`, `on_conflict: select_primary_require_pdf`). CN behavior unchanged (no CN market_policy entry).

The existing source_policy chain handles the promotion:
- `_primary_candidate` picks Yahoo for HK
- `_can_apply_hk_yahoo_trust_policy` validates the trust policy + provider_semantics rule alignment
- `_apply_hk_yahoo_trust_policy` clears the conflict_classifications
- All 6 HK issuers → `clean_present` with `selected_source=yahoo`.

**Coverage impact** (after currency-label follow-up): +2 HK clean cells (00001/01113 acct_payable moved from `unresolved_conflict` → `clean_present`). 09987 stayed `unresolved_conflict` after the currency-label review (the Yahoo HK adapter hardcodes `currency=HKD` on every HK record; Yum China reports in USD so promoting 09987 would emit a wrong-currency clean claim — `pdf_verified_company_ids` allowlist excludes 09987 until the adapter is fixed). 01810/02498/06862 stay clean — `selected_source` flipped akshare → yahoo (same value, more correct source). Matrix verification: 35/62 → 36/62 (+1, acct_payable now `verified`).

**Test updates** (5 files):
- `test_phase_hk_b_acct_payable.py`: locks new post-promotion shape (6 clean / 0 conflict, selected_source=yahoo).
- `test_phase_hk_llm_2_supplement_merge.py`: baseline counts bumped for 00001 (28→29), 01113 (29→30), 09987 (29→30); total counts also +1.
- `test_provider_baseline_replay.py`: `acct_payable` added to `EXPECTED_HK_YAHOO_VERIFIED_FIELDS` + per-company clean sets + counts 26→27 / 28→29.
- `test_hk_yahoo_trust_policy.py`: verified samples count 14→20.

Same methodology as H2.1/H2.2 CN promotions: multi-issuer (6 HK + CN baseline) sample verification, PDF spot-check per issuer with explicit page + statement_line cite, catalog rule with named samples (not silent broad promotion). Drift §177 satisfied. All 587 tests pass.

## 6. Validation Commands

Expected commands after implementation begins:

```bash
uv run pytest tests/test_structured_sources.py -v
uv run pytest tests/test_source_mapping.py -v
uv run pytest tests/test_source_coverage.py -v
uv run pytest tests/test_source_policy.py tests/test_source_review_export.py tests/test_provider_baseline_replay.py -v
uv run pytest -v
uv run ruff check .
uv run mypy src tests
```

Real AKShare/Yahoo/LLM tests must be opt-in and skipped by default when network credentials or external services are unavailable.

Captured source fixtures should be preferred for iterative development after a provider has been called once. The workflow is:

```bash
REAL_SOURCE_VALIDATION=1 \
INVENTORY_FIXTURE=tests/fixtures/akshare/600519_income_statement_2025_required_fields.jsonl \
OUT_DIR=tmp/runs/captured_source_validation_akshare \
scripts/run-real-source-validation.sh

REAL_SOURCE_VALIDATION=1 \
INVENTORY_FIXTURE=tests/fixtures/akshare/600519_combined_statements_2025_required_fields.jsonl \
OUT_DIR=tmp/runs/captured_source_validation_akshare_combined \
scripts/run-real-source-validation.sh

REAL_SOURCE_VALIDATION=1 \
INVENTORY_FIXTURE=tests/fixtures/yahoo/0001_hk_income_statement_2025_required_fields.jsonl \
OUT_DIR=tmp/runs/captured_source_validation_yahoo_income \
scripts/run-real-source-validation.sh

REAL_SOURCE_VALIDATION=1 \
SAMPLE_SET=provider_field_baseline \
PROVIDERS=akshare,yahoo \
OUT_DIR=tmp/runs/provider_field_capture_baseline \
scripts/run-real-source-validation.sh
```

Use real provider calls only to create or refresh captured fixtures, then drive mapping and reconciliation fixes from those saved artifacts.

### Per-(company, period) end-to-end validation

```bash
# Step 1: live fetch (env-driven shell wrapper)
COMPANY=600519 YEAR=2024 MARKET=CN PROVIDERS=akshare \
  scripts/run-fetch-source-inventory.sh

# Step 2: evaluate (deterministic from cache; auto-runs LLM if PDF given)
COMPANY=600519 YEAR=2024 MARKET=CN \
  PDF_PATH=downloads/cn_stocks/600519/annual/2024_年度报告.pdf \
  LLM_CONFIG=tmp/llm_configs/deepseek.json \
  scripts/run-evaluate-company.sh
```

Outputs land in `tmp/runs/${COMPANY}_${PERIOD_END}/`:
`source_inventory.jsonl`, `source_inventory_summary.json`,
`extraction_result.json`, `llm_evidence_supplement.json` (if PDF set),
`evaluation.json`, `evaluation.md`.

`evaluate-company` 与 `replay-provider-baseline` 的边界：

- `evaluate-company`：单 (公司, 期末)，可选 live (via `fetch-source-inventory`) 或 fixture，含 LLM supplement，输出 bucket-classified evaluation。
- `replay-provider-baseline`：多公司 batch，仅从已有 fixture replay，输出 multi-slice export。

## 7. Branch Completion Criteria

This branch is complete when:

- Requirements document describes source-first as the main product direction.
- Roadmap phases begin with Turtle full field taxonomy, Turtle coverage matrix, minimal source mapping, then staged AKShare and Yahoo/yfinance coverage.
- PDF/LLM work is clearly moved to selected-field fallback.
- Existing completed PDF/LLM phases are preserved as reusable fallback assets, not deleted conceptually.
- The design supplement, requirements, and roadmap agree on source priority:

```text
AKShare
-> Yahoo/yfinance
-> reconciliation
-> source policy conflict classification and primary-candidate selection
-> PDF evidence supplement
-> LLM ambiguity review
```

### Status (2026-05-09)

All 5 criteria met:

1. ✅ Source-first as main direction — codified in `docs/design/2026-05-01-structured-data-source-first-financial-extraction-design.md` and `docs/2026-05-07-source-first-architecture-drift-analysis.zh.md`.
2. ✅ Phase ordering Taxonomy → Coverage Matrix → Minimal Mapping → Adapters — sections 4.1, 4.2, A1–A3, C, D above.
3. ✅ PDF/LLM as bounded selected-field fallback — Phase H0/H1 (deterministic surgical fixes), Phase I-A/I-C (LLM with field-scoped chunk selection, never broad PDF retrieval).
4. ✅ Prior PDF/LLM phases preserved as fallback infrastructure — `extraction.py`, `retrieval.py`, `chunking.py`, `ingestion.py` all reused by Phase I-A's `llm_extraction_runner.py`.
5. ✅ Source priority chain expressed consistently across design supplement / requirements / roadmap — `provider_baseline_replay` → `source_policy` → `llm_evidence_supplement` merge gate respects this order at the code level.

Remaining post-branch follow-ups (out of branch scope):

- 6 P3/P4 fields with no source provider data and no current `pdf_aliases` (deeper notes-only disclosures with weak retrieval signal). Either land via a future Phase I-D iteration with curated alias sets per disclosure pattern, or accept as locked terminal `not_in_scope`.
- Confidence threshold value calibration (Phase I-A.2 follow-up #2) deferred until ~50+ labeled (company, field) pairs collected. Framework already in place.
- Bulk re-validation across more HK and CN issuers when batch extract budget allows (current validation set is 6 HK companies; CN P3 LLM coverage not validated).
- HK-B.5 closed `acct_payable` for 5 of 6 HK issuers via per-issuer `pdf_verified_company_ids` allowlist. `fix_assets` remains under HK-B.2 shape lock — same recipe (PDF spot-check + allowlist) is the next candidate.
- **Yahoo HK + AKShare HK adapter currency-label fix** — *Phase HK-B.5.1 partially landed 2026-05-11*: `source_inventory_fetch.HK_ISSUER_FINANCIAL_CURRENCY` map now stamps known HK issuers (00001/01113→HKD, 01810/02498/06862→CNY, 09987→USD) with their actual reporting currency for new live fetches. Used by both `_fetch_yahoo_for_company` and the CLI's AKShare `hk_default_currency` arg. Unknown HK issuers still fall back to HKD (pre-fix behavior, no silent regression).
- **Phase HK-B.5.2 (deferred)**: existing fixtures still have the pre-HK-B.5.1 HKD labels. Backfill + trust policy multi-currency schema + 09987 re-promote are needed to close the loop. Currently 01810/02498/06862 acct_payable stay clean via the legacy fixture labels; 09987 stays in unresolved via the `pdf_verified_company_ids` allowlist. The pragmatic path is: ship HK-B.5.1 architecturally clean for forward-going fetches, then schedule HK-B.5.2 when there's budget to update many fixture-dependent tests.
- `_resolve_derivation_operand` period-equality assertion (Phase H2.1 carryover): low immediate risk but worth a fail-loud check before summing multi-period operands.

## 8. Phase Summary Index

A point-in-time snapshot of waves, milestones, and open decisions lives at
`docs/2026-05-11-phase-summary.md` (post Phase HK-LLM-2/C + HK-B.1-.4 locks).
Use that doc as the TOC when onboarding into this branch; this roadmap remains
the authoritative per-phase implementation record.
