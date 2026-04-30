# LLM-First Financial Report Extractor Roadmap

> Status: published roadmap
> Date: 2026-04-30
> Scope: Build an independent LLM-first extractor that turns annual-report PDFs
> into evidence-grounded Turtle-style JSON, without depending on the existing
> deterministic `financial-report-analysis` canonical fact pipeline.

## 1. Decision Summary

The requirements are mature enough to start implementation planning. The first
product should not be a generic financial-analysis engine. It should be a
reviewable extraction tool:

```text
annual-report PDF
-> page/block/logical chunk store
-> field-scoped retrieval
-> LLM structured extraction
-> deterministic money/unit normalization
-> schema + evidence validation
-> JSON artifacts for review and downstream comparison
```

The first milestone focuses on one PDF at a time and P0/P1 Turtle fields. It
must support Chinese A-share annual reports and Hong Kong English annual
reports enough to validate the architecture on real PDFs.

## 2. Architecture Guardrails

The main implementation risk is accidentally rebuilding the old
table-driven-first extractor. Tables remain useful evidence, but complete table
reconstruction must not become a prerequisite for extracting a field.

Required direction:

- Use an evidence-block-first pipeline:
  `PDF -> page text/layout blocks -> full-PDF local evidence index ->
  field-scoped top-k retrieval -> LLM extraction -> deterministic
  normalization and validation`.
- Treat table rows, cells, and bounding boxes as evidence enrichment, not as
  the only path to a valid result.
- Extract by field or small field group, scoped to bounded top-k evidence and
  optional statement/section context. Do not ask the LLM to extract the whole
  document or the whole P0/P1 catalog in one request.
- The full PDF may enter the local evidence index, but prompt payloads must
  remain bounded to selected top-k evidence windows.
- Statement and section discovery are optional ranking/review signals, not the
  required main gate for field retrieval when field-first validation passes.
  Pure vector retrieval over the whole document is not enough for first-slice
  reliability either; deterministic aliases, layout signals, period/scope/unit
  context, and statement hints should all contribute to ranking.
- Prompt instructions are not a trust boundary. Schema validation, evidence
  checks, currency/unit normalization, and derivation checks must run in code.
- The field catalog must carry extraction semantics: aliases, statement hints,
  scope hints, unit expectations, and simple derivation formulas. A priority
  list alone is not sufficient.
- Every `present` value must cite concrete page/block/snippet evidence, even
  when the LLM was given a cross-page logical chunk.
- Cross-page retrieval should pass the logical chunk plus neighbor blocks that
  preserve the local unit, period, and scope context.
- Market-specific rules are allowed for layout families, such as A-share
  Chinese statements and HK English side-by-side statements. Issuer-specific
  patches should be avoided in the first roadmap.
- Save raw artifacts: page text, chunks, retrieval candidates, raw LLM
  responses, parsed responses, normalized results, and run metadata.
- During development and analysis, write intermediate artifacts under the
  repository-local `tmp/` directory, not the system `/tmp` directory.
- Keep the first product as CLI + JSON artifacts. UI, databases, and batch
  workflows should not enter the first slice.

Explicit non-directions:

- Do not make full table stitching the blocking dependency for extraction.
- Do not trust LLM-provided normalized amounts without deterministic
  recomputation.
- Do not do implicit FX conversion.
- Do not silently select among multiple currencies, periods, scopes, or
  candidate values.
- Do not hide missing or ambiguous fields by forcing a best-effort value.

## 3. Reference From The Existing Worktree

The prior implementation under
`/home/like/mycode/finanice/report-collector/.worktrees/financial-report-analysis`
contains useful implementation ideas, but the new project should not copy its
canonical fact, lifecycle, P5, recompute, or deterministic registry layers.

The real PDF samples from that worktree have been copied into this repository
under `downloads/`. Implementation plans and tests should use the local
`downloads/...` paths instead of depending on the external worktree.

Useful patterns to borrow:

- `PdfTableSource`: uses `pdfplumber` to extract page-local table blocks, cells,
  bounding boxes, page text, and local context. In this project it should be an
  optional evidence enricher, not the main extraction dependency.
- `PdfTableStructureAdapter`: classifies income statement, balance sheet, and
  cash-flow tables; handles HK side-by-side statements, dual-currency statement
  blocks, continuation pages, and scope guessing. Borrow the layout and
  continuation heuristics, but do not require complete canonical table recovery
  before retrieval or LLM extraction.
- `table_header_parser`: extracts period, currency, and unit hints from table
  headers and context.
- `table_stitcher`: merges continuation tables while preserving source
  metadata. Use this as a reference for evidence continuity, not as a required
  first-slice output format.
- `UnitPolicy`: provides a small deterministic unit multiplier model.
- Real-PDF tests for `600519`, `601919`, `00001`, `01113`, `02498`, `06862`,
  and `09987` show which formats need regression coverage.

Important differences in this project:

- The chunk store is the durable evidence source; vector indexes are derived.
- LLM extraction is first-class, but the trust boundary remains in code.
- Money normalization is deterministic and happens after LLM extraction.
- Outputs are review artifacts, not canonical promoted facts.
- Table/cell structure is optional evidence metadata. Text/layout evidence
  blocks must remain sufficient to drive the first extraction loop.

## 4. Functional Areas

### 4.1 Contracts

Define the shared data model:

- `Evidence`: page, chunk id, block id, snippet, optional bbox/cell references.
- `MoneyAmount`: `value_raw`, `value`, `currency`, `unit`,
  `unit_multiplier`, `normalized_value`, `normalized_unit`.
- `ExtractedItem`: field id, status, value, period, scope, confidence,
  evidence, optional derivation.
- `Chunk`: page atom, block atom, and logical chunk.
- `ExtractionRun`: source PDF hash, parser/chunker versions, LLM metadata,
  prompt/schema versions, artifacts, and errors.

### 4.2 Field Catalog

Extend `field_catalog/turtle_v015_priority_fields.json` from a priority list
into an extraction catalog:

- Priority layer: P0, P1, P2, P3, P4.
- Field aliases in Chinese and English.
- Statement hints: balance sheet, income statement, cash-flow statement, notes.
- Scope hints: consolidated, parent/company, unknown.
- Unit expectations and value type.
- Simple derivation formulas for fields such as `total_assets` and
  `total_liabilities` when reports expose components but not the total row.

### 4.3 PDF Ingestion And Chunk Store

Build a parser that creates durable, reviewable source artifacts:

- `page_text` atoms from the PDF.
- `block` atoms for headings, paragraphs, statement lines, table fragments, and
  table rows when row structure is available.
- `logical chunks` that may cross pages, especially core financial statements
  and page-break paragraphs.

The first version should use a pragmatic PDF backend:

- Start with `pdftotext -layout` for page text when available.
- Add layout-aware block segmentation for headings, paragraphs, statement
  regions, and line groups.
- Add `pdfplumber` for optional table/cell/bbox extraction when available,
  following the old worktree's `PdfTableSource` pattern as evidence enrichment.
- Keep the parser replaceable by recording parser name/version in metadata.

### 4.4 Statement And Evidence-Block Recovery

Implement the statement/section detector and evidence-block chunker before any
real LLM work:

- Detect Chinese titles such as `合并资产负债表`, `合并利润表`, `合并现金流量表`.
- Detect English titles such as `Consolidated Statement of Financial Position`,
  `Consolidated Income Statement`, `Consolidated Statement of Profit or Loss`,
  and `Consolidated Statement of Cash Flows`.
- Continue statement logical chunks across pages when headers/rows continue.
- Split side-by-side HK English pages by layout column or statement region.
- Preserve concrete evidence blocks with line text, inferred row label when
  available, column/period/unit context when available, and page references.
- Do not block extraction because a statement cannot be reconstructed into a
  perfect table. If text/layout evidence is clear enough, retrieval and LLM
  extraction may proceed with lower confidence.

### 4.5 Retrieval

First build deterministic field-scoped retrieval:

- Query by field aliases and statement hints.
- Score matching blocks by statement type, row-label similarity, period, scope,
  and proximity to unit/currency headers.
- Return candidate logical chunks plus concrete evidence blocks.

Embedding retrieval is a later enhancement. The first milestone should prove
that keyword/scored retrieval can consistently find P0/P1 evidence on real
reports.

### 4.6 Money And Unit Normalization

Implement a deterministic normalizer:

- Currencies: `CNY`, `HKD`, `USD`, `unknown`, `ambiguous`.
- Units: `元`, `千元`, `万元`, `百万元`, `RMB'000`, `HK$ million`,
  `US$ million`, `$ Million`, `k`, `m`, `mn`.
- `normalized_value = value * unit_multiplier`.
- No FX conversion.
- Multi-currency tables must select a single reporting-currency column or mark
  the item ambiguous.

The LLM may extract `value_raw`, `unit_context`, `currency_hint`, and evidence.
It must not be trusted to produce final normalized values.

### 4.7 LLM Layer

Implement a provider-neutral LLM boundary:

- `LlmConfigResolver`: config file, environment variables, and CLI/API
  overrides.
- `LlmClient`: structured JSON completion interface.
- `OpenAICompatibleTransport`: first provider transport.
- `LlmResponseParser`: raw response, parsed JSON, usage, finish reason, latency.
- `FakeLlmClient`: deterministic tests before real API usage.

Automatic provider fallback should be disabled by default. Provider/model/base
URL changes must be recorded in extraction-run metadata.

### 4.8 Validation And Export

Validation is the trust boundary:

- `present` requires evidence.
- Evidence must point to existing page/block/chunk records.
- Monetary fields require normalizer output or a structured ambiguity.
- Derived fields require all input evidence and matching currency/unit/period.
- Invalid LLM output is rejected, repaired once when appropriate, or downgraded.

Exports should be JSON-first:

- `chunks.jsonl`
- `retrieval_probe.json`
- `extraction_result.json`
- `run_metadata.json`
- optional review summary

Development and analysis artifacts should use this repository-local layout:

```text
tmp/
  runs/
    <run_id>/
      pages.jsonl
      chunks.jsonl
      retrieval_probe.json
      extraction_result.json
      run_metadata.json
```

The root `tmp/` directory is for generated intermediate artifacts and should be
rebuildable from source PDFs plus code. Durable sample PDFs live under
`downloads/`.

## 5. Implementation Phases

### Phase 0: Documentation And Contract Cleanup

Goal: make the planned system internally consistent before implementation.

Deliverables:

- Correct architecture order in the design doc.
- Contract models for evidence, money, chunks, extraction items, and runs.
- Tests for evidence-required and money-required invariants.

Exit criteria:

- Unit tests pass for data contracts.
- The README points to requirements, design, and this roadmap.

### Phase 1: PDF Probe And Page Store

Goal: prove the project can ingest real PDFs and persist page-level evidence.

Deliverables:

- CLI command: `ingest`.
- Page text extraction for local PDFs.
- Source PDF hash and parser metadata.
- `pages.jsonl` artifact.

Validation samples:

- A-share Chinese:
  `downloads/cn_stocks/600519/annual/2025_年度报告.pdf`.
- HK English:
  `downloads/hk_stocks/00001/annual/2025_annual_en.pdf`.
- HK English side-by-side:
  `downloads/hk_stocks/01113/annual/2025_annual_en.pdf`.

Exit criteria:

- The CLI writes page artifacts for all three sample PDFs.
- Page numbers align with PDF page numbers used in evidence.

### Phase 2: Statement And Evidence-Block Logical Chunks

Goal: create cross-page statement chunks and concrete evidence blocks without
requiring full table reconstruction.

Deliverables:

- Statement-title detector for CN and HK reports.
- Logical chunks for balance sheet, income statement, and cash-flow statement.
- Basic continuation handling across pages.
- HK side-by-side statement splitting by layout column or statement region.
- Evidence blocks from page text and layout lines, including candidate row label,
  period, unit context, page, and snippet.
- Optional table/cell/bbox enrichment when the parser can provide it.
- `chunks.jsonl` artifact with page atoms, block atoms, and logical chunks.

Borrowed reference:

- Old `PdfTableSource` and `PdfTableStructureAdapter` are references for
  layout clues, dual-currency headers, continuation pages, and side-by-side
  statement handling. They are not the required architecture for this project.

Exit criteria:

- `600519` exposes CN consolidated statements.
- `00001` exposes HK dual-currency statements.
- `01113` exposes side-by-side income, financial position, and cash-flow
  statements without mixing unrelated columns.
- At least one statement can be represented and reviewed from text/layout
  evidence even if table cells are unavailable.

### Phase 3: Field Catalog And Retrieval Probe

Goal: retrieve candidate evidence for P0/P1 without LLM.

Deliverables:

- Enriched field catalog with aliases and statement hints.
- Retrieval scorer.
- CLI command: `retrieve`.
- `retrieval_probe.json` showing candidate chunks/evidence per field.

Exit criteria:

- P0/P1 core fields retrieve plausible evidence on `600519`.
- HK samples retrieve `revenue`, `cash`, `net cash from operating activities`,
  profit attributable to shareholders, and equity/capital rows.
- Missing or derived fields are explicitly marked as such in retrieval output.

### Phase 4: Money Normalizer And Derived Values

Goal: normalize monetary values deterministically.

Deliverables:

- Money parser for raw numeric strings, parentheses, minus signs, commas, and
  dashes.
- Currency/unit resolver using unit lines, headers, row context, and report
  metadata.
- Derived value engine for simple formulas such as:
  `total_assets = non_current_assets + current_assets`.
- Structured ambiguity errors.

Exit criteria:

- CNY, HKD, USD and common Chinese/English scale units normalize correctly.
- Multi-currency tables never mix currencies.
- Derived fields include all input evidence or become ambiguous.

### Phase 5: Fake LLM Extraction Pipeline

Goal: run the complete extraction contract without network dependency.

Deliverables:

- Prompt request/response models.
- `FakeLlmClient`.
- Extraction orchestrator:
  retrieval -> fake LLM output -> normalizer -> validator -> result JSON.
- Validator for schema, evidence, money, and derivation.

Exit criteria:

- Full pipeline works with fixture LLM responses.
- Invalid fake responses are rejected or downgraded predictably.
- `present` without evidence cannot pass.

### Phase 6: Real LLM Transport

Goal: add real LLM extraction behind the same interface.

Deliverables:

- Project config file for LLM settings.
- OpenAI-compatible transport.
- Timeout and limited retry handling.
- Raw response artifacts.
- CLI command: `extract`.

Exit criteria:

- Real extraction works for a small field subset.
- Runs record provider, model, base URL, prompt/schema version, usage, latency,
  and errors.
- Provider fallback remains explicit and off by default.

### Phase 7: Real Report Evaluation

Goal: decide whether the first slice is useful on real PDFs.

Deliverables:

- Evaluation fixture matrix:
  - `downloads/cn_stocks/600519/annual/2025_年度报告.pdf`.
  - `downloads/hk_stocks/00001/annual/2025_annual_en.pdf`.
  - `downloads/hk_stocks/01113/annual/2025_annual_en.pdf`.
- Review summary comparing present/missing/ambiguous fields.
- Regression tests for known hard cases.

Exit criteria:

- P0/P1 extraction is reviewable on all three PDFs.
- Every present monetary item has normalized value and concrete evidence.
- Ambiguities are visible instead of silently guessed.

### Phase 8: Thin Skill Wrapper

Goal: make Codex/Claude usage ergonomic without moving business logic into a
skill.

Deliverables:

- Optional skill instructions that call the CLI/API.
- Review checklist for extraction outputs.
- Guidance for choosing P0/P1 or selected fields.

Exit criteria:

- Skill never parses PDFs, normalizes money, validates evidence, or stores final
  facts.

## 6. Quick Validation Roadmap

> Status: updated after the document-map / row-discovery design review.
> Purpose: validate the revised pipeline quickly before broadening the product
> scope. These phases are intentionally smaller than the full roadmap. The goal
> is to prove that the system can go from a real PDF to document structure, row
> discovery, catalog mapping, and evidence-grounded selected-field extraction.

The quick validation path is:

```text
contract fixes
-> parser/document-map demo
-> field-first retrieval with optional statement/row signals
-> selected-field extraction demo
```

This is not a whole-document LLM extraction plan. The LLM may help with
document/statement/row discovery, but final extracted fields still require
page/chunk/block/snippet evidence and deterministic validation.

### Phase 9: Contract Fixes And Demo Run Skeleton

Goal: remove known evidence/artifact contract bugs so the validation demo does
not stand on unreliable outputs.

Deliverables:

- Fix retrieval evidence selection so the evidence `block_id` points to the
  block containing the matched alias/snippet when a statement chunk spans
  multiple blocks.
- Ensure custom chunk output paths create parent directories, matching the
  behavior of ingestion and retrieval artifacts.
- Ensure raw LLM responses are archived even when parsing fails or provider
  schemas are unexpected.
- Add focused tests for the three review findings.
- Define a conventional quick-demo run layout under
  `tmp/runs/quick_validation/<report_id>/`.
- Add or document a no-network fake/demo path that can exercise artifacts
  without a real API key.

Exit criteria:

- Known evidence and raw-artifact review findings are fixed.
- `pages.jsonl`, `chunks.jsonl`, retrieval/demo artifacts, raw responses,
  parsed responses, final result, and metadata can all be written under a
  nested quick-validation run directory.
- Fake mode can run the skeleton without network.

### Phase 10: Parser Capability Probe And Document Map Demo

Goal: verify that the pipeline can identify useful document structure on
different real reports before attempting final field extraction.

Validation samples:

- A-share Chinese: `downloads/cn_stocks/600519/annual/2025_年度报告.pdf`.
- HK English with large report structure:
  `downloads/hk_stocks/00001/annual/2025_annual_en.pdf`.
- HK English with compact statement pages:
  `downloads/hk_stocks/01113/annual/2025_annual_en.pdf`.

Deliverables:

- Parser capability probe artifact that records parser backend, page count,
  extraction quality signals, and any text extraction warnings.
- `document_map.json` that distinguishes at least:
  - contents / table of contents
  - financial summary
  - MD&A / management discussion
  - independent auditor report
  - audited financial statements
  - notes to financial statements
- Rule-first detection using page titles, contents pages, and auditor-report
  page references.
- Optional LLM-assisted document-map judgement for ambiguous candidate pages,
  saving prompt payloads, raw responses, parsed responses, and errors.
- Tests using synthetic page/block fixtures so CI does not depend on external
  PDF tools or network.

Exit criteria:

- The demo can produce a reviewable `document_map.json` for at least one real
  HK English PDF with the formal financial statement range separated from
  financial summary and MD&A.
- A-share parser limitations are recorded explicitly instead of silently
  producing empty maps.
- Document-map artifacts include evidence blocks for section decisions.

### Phase 11: Field-First Retrieval To Selected-Field Extraction Demo

Goal: prove the revised pipeline can find and extract a small selected field
set through field-first top-k retrieval, while using statement and row discovery
only as optional ranking/review signals. The LLM must not process the whole PDF
as a final extractor.

Selected fields for the demo:

- `revenue`
- `net_profit` or profit attributable to owners/shareholders
- `total_assets`
- `total_liabilities`
- `operating_cash_flow`

Deliverables:

- `retrieval_probe.json` showing selected-field candidates from the full-PDF
  local evidence index, bounded to top-k evidence windows for prompt use.
- Optional `statement_map.json` for formal income statement, balance sheet /
  statement of financial position, and cash-flow statement. It is a
  ranking/review artifact, not a required extraction gate.
- Optional LLM-assisted or fake-LLM `row_inventory.json` for trusted, small
  statement chunks, including row labels, raw values by period, unit/currency
  context, and row-level evidence refs.
- `catalog_mapping.json` mapping discovered rows to selected Turtle fields with
  confidence, reason, and ambiguity status when row discovery is available.
- Selected-field extraction that feeds only top-k field candidates, optional
  mapped rows, neighbor headers, and unit/period/scope context to the LLM.
- Deterministic money normalization for the selected monetary fields.
- `quick_validation_summary.json` and optional Markdown summary reporting:
  present/missing/ambiguous/extraction_failed, evidence gaps, normalization
  gaps, and raw LLM parse errors.

Exit criteria:

- For one HK English sample, the demo can move from PDF artifacts to
  selected-field `retrieval_probe.json` and `extraction_result.json`, with
  optional `row_inventory.json` / `catalog_mapping.json` when statement windows
  are reliable and small enough.
- Every `present` selected field has page/chunk/block/snippet evidence.
- Values from financial summary or MD&A are not silently accepted as formal
  statement values unless explicitly marked as non-formal evidence.
- Ambiguous field mapping or money context is visible in the output.
- Current real-PDF field-first validation on `00001_2025_en` found all five
  selected fields locally, but the combined top-k candidate text was about 54k
  prompt characters. Before production LLM extraction, ranking and evidence
  windowing must reduce prompt budget further.

### Phase 12: Turtle Field Coverage Budget Gate

Goal: prevent broad field-scoped extraction from depending on retrieval output
that already fails deterministic local coverage or prompt-budget checks.

Deliverables:

- Before field-scoped LLM extraction, run
  `scripts/run-turtle-field-coverage-budget.sh` for the required Turtle field
  set.
- Treat missing required fields or prompt-budget overflow as a roadmap blocker.
  Extend catalog aliases, evidence ranking, or window reduction before adding
  more real LLM extraction paths.

## 7. Non-Goals For The First Roadmap

These remain intentionally out of scope:

- Canonical fact promotion.
- Metric lifecycle governance.
- P5 dataset generation.
- Deterministic recompute.
- UI and multi-user workflows.
- Automatic report downloading.
- FX conversion.
- Whole-document investment report generation.
- Full-fidelity table reconstruction as a hard dependency.
- Prompt-only extraction without code-level validation.
- Issuer-specific one-off extraction patches.

## 8. Risk Register

| Risk | Guardrail |
| --- | --- |
| Table-driven-first implementation fails on heterogeneous report layouts. | Use evidence-block-first extraction; table/cell/bbox metadata is enrichment only. |
| Whole-document RAG retrieves plausible but wrong context. | Put the full PDF in the local evidence index, but use field-scoped top-k retrieval with concrete evidence blocks and optional statement ranking signals. |
| LLM returns normalized values that look valid but use the wrong unit or currency. | Let LLM extract raw value/context only; deterministic normalizer computes final money fields. |
| Prompt instructions are treated as validation. | Enforce schema, evidence, money, derivation, period, and scope checks in code. |
| Field catalog remains a priority list and cannot guide retrieval. | Extend it into an extraction catalog with aliases, hints, units, and derivations. |
| Derived fields are silently calculated from mismatched rows. | Require derivation objects and matching currency, unit, period, scope, and evidence for every input. |
| Cross-page context is lost or evidence becomes too coarse. | Store logical chunks for context but require page/block/snippet evidence for each value. |
| HK English dual-currency or side-by-side layouts mix columns. | Split by layout region, record selected currency column, and mark ambiguity when unclear. |
| Real-PDF problems appear too late. | Use `600519`, `00001`, and `01113` from Phase 1 onward as validation samples. |
| Cost and latency grow quickly. | Batch only small field groups by bounded top-k evidence windows; record token usage and support selected-field reruns. |
| Raw artifacts are not reproducible. | Persist page/chunk/retrieval/LLM/raw/normalized/run metadata artifacts for every run. |
| Product scope expands before extraction is proven. | Keep first slice to CLI + JSON, one PDF, P0/P1, and reviewable artifacts. |

## 9. Recommended Next Implementation Plan

The next detailed implementation plan should cover Phases 9 through 11 only:

```text
contract fixes and demo run layout
-> parser capability probe and document map
-> field-first retrieval, optional statement/row signals, selected-field extraction
```

Do not broaden immediately into all P0/P1 fields, full table reconstruction, a
batch system, or a UI. The highest-risk assumption now is whether full-PDF local
evidence indexing plus field-first top-k retrieval can produce reviewable
selected-field extraction on real reports without using statement discovery as a
hard gate. Prove that first with a small selected field set, explicit evidence,
and measured prompt budgets.

## 10. Open Decisions

These decisions can be made during implementation planning:

- Whether `pdftotext -layout` remains a required system dependency or only a
  fallback backend.
- Whether `pdfplumber` is included in the first slice as optional enrichment or
  delayed until text/layout evidence blocks are stable.
- Exact CLI names and output directory conventions.
- Whether field aliases live in the existing catalog file or a companion file.
- Whether Phase 10 document-map LLM judgement should be opt-in only or enabled
  by the same real-LLM demo config used in Phase 11.
- Whether quick-validation summaries should include Markdown output in Phase 11
  or wait until the evaluation loop is expanded.
