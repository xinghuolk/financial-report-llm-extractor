# Source-First Financial Report Extractor Roadmap

> Status: revised roadmap
> Date: 2026-05-01
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
- Field mapping must preserve raw field, raw value, period, scope, currency, unit, source, and evidence.
- Money normalization remains deterministic code.
- Cross-source conflicts must be explicit, not silently resolved.
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

Implementation note:

- `field_catalog/turtle_v015_field_taxonomy.json` contains full Turtle field taxonomy.
- `field_catalog/turtle_v015_coverage_matrix.json` contains expected coverage route by field.
- `field_catalog/turtle_v015_source_mapping_minimal.json` is linked to taxonomy and coverage metadata.

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

Implementation note:

- `field_catalog/turtle_v015_field_taxonomy.json` contains full Turtle field taxonomy.
- `field_catalog/turtle_v015_coverage_matrix.json` contains expected coverage route by field.
- `field_catalog/turtle_v015_source_mapping_minimal.json` is linked to taxonomy and coverage metadata.

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
- Remaining minimal-field gap in the current 600519 AKShare combined replay is `gross_profit`.
- Remaining Yahoo work is balance sheet and cash flow captured validation, plus cross-source reconciliation against AKShare where periods and units are comparable.
- Full source-first viability decision is not complete until captured or real validation covers the required statement families for the target companies and remaining gaps are categorized.

## 6. Validation Commands

Expected commands after implementation begins:

```bash
uv run pytest tests/test_structured_sources.py -v
uv run pytest tests/test_source_mapping.py -v
uv run pytest tests/test_source_coverage.py -v
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
-> PDF evidence supplement
-> LLM ambiguity review
```
