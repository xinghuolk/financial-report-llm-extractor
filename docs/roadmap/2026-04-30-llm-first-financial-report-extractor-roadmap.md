# Source-First Financial Report Extractor Roadmap

> Status: revised roadmap
> Date: 2026-05-07
> Scope: Pivot the project from PDF-first LLM extraction to AKShare/Yahoo-first structured financial data extraction, with PDF/LLM retained as the final evidence supplement and ambiguity review layer.

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
