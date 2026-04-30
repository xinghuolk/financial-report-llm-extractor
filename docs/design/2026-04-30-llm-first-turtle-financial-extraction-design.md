# LLM-First Turtle Financial Extraction Design

## Goal

Build an independent extraction path for Turtle-style financial report inputs.
The system should adapt to new companies and report formats without extending
the deterministic metric registry for every field variant.

The product requirements are documented in
`docs/requirements/2026-04-30-llm-first-financial-report-extractor-requirements.md`.

## Architecture

```text
PDF
-> document parser
-> page text / layout evidence blocks / optional table metadata
-> chunk builder
-> chunk store: page atoms + block atoms + logical chunks
-> retrieval index
-> Turtle field catalog
-> field-scoped retrieval
-> prompt builder
-> LLM config resolver
-> LLM client / transport
-> LLM structured extraction
-> structured response parser
-> money/unit normalizer
-> schema validator + evidence enforcer
-> evidence-grounded extracted items
-> review/export JSON
```

The retrieval index stores source chunks and evidence pointers. It is not the
final fact store. Final outputs are stored as extraction-run items with their
own status, confidence, and evidence.

The primary path is evidence-block-first, not table-driven-first. Page text,
layout lines, statement lines, paragraphs, and section windows must be enough
to drive retrieval and LLM extraction. Table rows, cells, and bounding boxes
are valuable evidence enrichment when a PDF backend can recover them, but a
field should not be blocked solely because the full table could not be
reconstructed.

## Chunking And Cross-Page Context

Annual reports frequently split both tables and important narrative text across
page boundaries. The system should preserve page-level evidence while building
larger logical chunks for retrieval and LLM extraction.

The chunk store has three layers:

- `page atom`: raw extracted text for one PDF page.
- `block atom`: a page-local paragraph, heading, layout line, statement line,
  table fragment, or table row when available.
- `logical chunk`: a retrieval/LLM context that can reference blocks from one
  or more pages.

RAG chunks may cross pages. Evidence must remain page/block specific. For
example, a cash-flow statement logical chunk may span pages 64-66, while the
`operating_cash_flow` evidence points to the exact row on page 65.

Recommended first-slice chunk kinds:

- `page_text`
- `paragraph`
- `section_window`
- `layout_line`
- `statement_line`
- `table_fragment`
- `statement_table`
- `table_row`

Statement and table continuation rules:

- Start a logical `statement_table` when a statement title is detected, such as
  consolidated balance sheet, consolidated income statement, or consolidated
  cash-flow statement.
- Continue the chunk on following pages when there is no new major title and
  the table structure or statement semantics continues.
- Stop when a new statement starts, a parent-company statement starts, or a
  report-signature/footer marker indicates the table ended.
- Preserve row-level blocks when available with page, row label, column labels,
  period, unit, and optional layout metadata.
- When row-level table structure is unavailable, preserve line-level statement
  blocks plus nearby unit, period, scope, and heading context. Extraction may
  proceed from these blocks with lower confidence instead of failing early.
- For Hong Kong English annual reports, split by layout column or statement
  region when pages contain side-by-side statements. A block should not mix
  unrelated rows from the left and right columns.

Narrative continuation rules:

- Build section windows from report headings such as audit report, MD&A, and
  financial statement notes.
- Merge page-break paragraphs only when the previous page ends without a
  natural terminator and the next page does not start with a heading.
- For long sections, retrieve a focused window around the matched block rather
  than sending the whole section to the LLM.

The chunk store is the durable evidence source. Embedding/vector indexes are
derived artifacts and should be rebuildable from the chunk store plus parser,
chunker, embedding model, and source PDF metadata.

## Money And Unit Normalization

Financial reports present numbers with different currencies and scale units:
RMB/CNY, HKD, USD, `元`, `千元`, `万元`, `RMB'000`, `HK$ million`,
`US$ million`, `$ Million`, `k`, and `m`. Extraction must preserve the raw
displayed value and separately compute a same-currency normalized value.

Recommended money fields on numeric extracted items:

- `value_raw`: source text number exactly as shown in evidence.
- `value`: parsed numeric value before applying the scale multiplier.
- `currency`: `CNY`, `HKD`, `USD`, `unknown`, or `ambiguous`.
- `unit`: human-readable combined unit, such as `HKD million`.
- `unit_multiplier`: multiplier to the base currency unit.
- `normalized_value`: `value * unit_multiplier`.
- `normalized_unit`: base currency unit, such as `HKD`.

The extractor must not perform FX conversion. Currency conversion belongs to a
later analysis layer with an explicit exchange-rate source and date.

Money normalization is a deterministic project component, not an LLM or skill
responsibility. The LLM may identify `value_raw`, nearby unit context,
currency hints, and evidence blocks. The normalizer computes `value`,
`currency`, `unit_multiplier`, `normalized_value`, and `normalized_unit`.
The validator then checks schema, evidence, and currency/unit consistency.

```text
LLM extraction
-> value_raw / unit_context / currency_hint / evidence
money normalizer
-> value / currency / unit_multiplier / normalized_value / normalized_unit
validator
-> schema check / evidence check / currency-unit consistency
```

If the normalizer cannot determine currency or multiplier, it should return a
structured error that becomes `ambiguous`, `missing`, or `extraction_failed`.
The system should not ask the LLM to guess a normalized amount.

Unit resolution should use this precedence:

1. Statement/table unit line, for example `单位：元 币种：人民币` or
   `HK$ million`.
2. Column header, for example `2025 HK$ million`.
3. Row label or footnote.
4. Report-level metadata.
5. `unknown` or `ambiguous` when unresolved.

When a statement contains multiple currency columns, such as US dollars and
Hong Kong dollars in the same table, the field extractor should select the
reporting-currency column and record the selected column metadata. It must not
mix currencies inside one extracted value or derived calculation.

Short scale suffixes require context:

- `k` means thousand only in an explicit monetary context.
- `m`, `M`, or `mn` means million only in an explicit monetary context.
- `$` alone does not determine currency.

## Field Semantics And Derived Values

The field catalog should support aliases and statement hints across Chinese and
English reports. Examples:

- Balance sheet: `资产负债表`, `Consolidated Statement of Financial Position`.
- Income statement: `利润表`, `Consolidated Income Statement`,
  `Consolidated Statement of Profit or Loss`.
- Cash-flow statement: `现金流量表`, `Consolidated Statement of Cash Flows`.
- Net profit attributable to owners: `归属于母公司股东的净利润`,
  `Profit attributable to ordinary shareholders`.
- Cash: `货币资金`, `Cash and cash equivalents`, `Bank balances and deposits`.

Some reports do not expose every Turtle field as a single line. The first slice
may support evidence-backed derived values for simple statement totals such as
`total_assets` or `total_liabilities`.

Derived value rules:

- Store a `derivation` object with formula and input field names.
- Cite evidence for every input row.
- Require matching currency, unit multiplier, period, and scope across inputs.
- Return `ambiguous` or `missing` when any input is absent or mismatched.

## LLM Configuration And Communication

The LLM layer should follow the same broad separation used by mature agent
projects such as `../hermes-agent`: configuration resolution, provider/client
construction, request building, response normalization, timeout/retry handling,
and test doubles should be separate from business extraction logic.

This project should not copy Hermes Agent's full runtime. Hermes optimizes for
interactive agent availability and can fall back across providers. Financial
report extraction optimizes for reproducibility and auditability, so automatic
provider fallback must be disabled by default. The resolved provider, model,
base URL, prompt version, schema version, latency, usage, finish reason, and
error metadata should be recorded with each extraction run.

Recommended first-slice components:

- `LlmConfigResolver`: resolves CLI/API overrides, project config, and
  environment variables into an effective task config.
- `LlmClient`: provider-neutral interface for structured JSON completion.
- `LlmTransport`: protocol adapter, with OpenAI-compatible chat completions as
  the first implementation.
- `LlmResponseParser`: extracts raw text, parsed JSON, usage, latency, and
  provider metadata.
- `FakeLlmClient`: deterministic test double for validation and error-path
  tests.

Recommended minimal config shape:

```yaml
llm:
  default:
    provider: openai_compatible
    model: gpt-4.1
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
    temperature: 0
    max_output_tokens: 4096
    timeout_seconds: 120
    retry_count: 2
    structured_output_mode: json_schema
  tasks:
    field_extraction:
      model: gpt-4.1
      temperature: 0
    response_repair:
      model: gpt-4.1-mini
      temperature: 0
```

The API key value should never be written to extraction artifacts. Store the
environment variable name and the resolved non-secret runtime metadata instead.

The trust boundary remains inside this project. Even when a provider supports
JSON schema or structured outputs, the repository must still validate the
parsed response and enforce that every `present` item has page/chunk/snippet
evidence.

LLM calls may receive cross-page logical chunks. The model must still return
specific evidence pointers. A valid field extraction can cite a cross-page
`chunk_id`, but it must also include the concrete `page`, `block_id`, and
`snippet` where the value appears.

## Field Priority

The first implementation should use the field catalog in
`field_catalog/turtle_v015_priority_fields.json`.

- P0: Turtle core statement fields.
- P1: high-value statement enhancement fields.
- P2: cash-flow enhancement fields.
- P3: note and announcement bridge signals.
- P4: text review artifacts.

The first slice should extract P0 and P1 for one annual-report PDF.

## Extraction Contract

Each extracted item should include:

- `field_id`
- `status`: `present`, `missing`, `ambiguous`, `not_applicable`, or
  `extraction_failed`
- `value`, when applicable
- `value_raw`, `currency`, `unit_multiplier`, `normalized_value`, and
  `normalized_unit` for monetary values
- `unit`, when applicable
- `period`
- `scope`: for example `consolidated`, `parent`, or `unknown`
- `confidence`
- `evidence`: page, chunk id, block id, and source snippet
- `derivation`, when the value is calculated from multiple evidence rows

Every `present` item must have evidence. An item without evidence must be
`missing`, `ambiguous`, or `extraction_failed`.

## Independence From Existing System

This project does not write canonical facts, lifecycle decisions, P5 datasets,
or deterministic recompute artifacts. A later export adapter may produce a
Turtle-like JSON file for comparison, but that adapter must remain optional.

The core should be a standalone application/package with CLI/API boundaries.
Codex or Claude Code skills may be added later as thin workflow wrappers that
call this project, but the extraction engine, persistence, validation, and tests
should live in this repository.

## First Milestone

1. Define field catalog and result schema.
2. Implement PDF-to-chunk ingestion.
3. Implement page/block atoms and first-slice cross-page logical chunks for the
   three core financial statements.
4. Implement field-scoped retrieval that returns logical chunks plus concrete
   evidence blocks.
5. Implement money/unit normalization for CNY, HKD, USD and common Chinese /
   English scale units.
6. Implement field aliases and simple evidence-backed derived values for
   statement totals.
7. Implement LLM config resolution and an OpenAI-compatible transport behind a
   provider-neutral client interface.
8. Implement prompt building, structured response parsing, schema validation,
   and evidence enforcement.
9. Add fixture-based tests for cross-page statement chunks, multi-column HK
   English statements, money/unit normalization, derived values, config
   resolution, FakeLlmClient extraction, malformed LLM responses, and
   evidence-required JSON output.
