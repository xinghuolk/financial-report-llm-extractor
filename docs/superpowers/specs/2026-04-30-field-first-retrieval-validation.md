# Field-First Retrieval Validation Spec

## Question

Can this project move away from a statement-first extraction gate and still keep LLM prompts small, auditable, and evidence-grounded?

## Hypothesis

Yes, if the main extraction path is changed from:

```text
find formal statements -> discover rows -> map rows to catalog fields
```

to:

```text
build full-PDF evidence index -> retrieve top-k field evidence -> LLM judge/extract -> evidence validation
```

The validation must prove that formal statement discovery can fail without blocking field evidence retrieval.

## What This Validates

This is an experiment, not a full production migration. It should answer:

- Can full-PDF field retrieval find core fields when statement localization is noisy or wrong?
- Can the prompt stay bounded by top-k evidence blocks instead of whole-PDF context?
- Can each returned candidate still point to `page`, `chunk_id`, `block_id`, and `snippet`?
- Can statement discovery become an optional ranking signal rather than a required gate?

## What This Does Not Validate

- It does not prove final extraction quality across all companies.
- It does not require real LLM calls in default tests.
- It does not remove existing statement discovery code.
- It does not send whole PDFs to the LLM.

## Validation Fixture

Add a synthetic adversarial E2E fixture where statement-first behavior is intentionally unreliable:

- MD&A pages contain repeated words like `cash flow`, `profit`, and `financial position`.
- The formal statement heading is missing, abbreviated, or appears after noisy explanatory text.
- Core field rows still exist in evidence blocks:
  - `Revenue 100 90`
  - `Profit attributable to shareholders 20 18`
  - `Total assets 500 450`
  - `Total liabilities 300 280`
  - `Net cash from operating activities 60 55`

The test should assert that statement discovery produces either noisy candidates or misses at least one formal statement, while field-first retrieval still returns candidates for the selected fields.

## Proposed Components

### Evidence Index

Create a small evidence index from existing `chunks.jsonl`:

- `block_id`
- `page`
- `chunk_id`
- `chunk_kind`
- `statement_kind` when available
- `text`
- lightweight features:
  - year count
  - numeric token count
  - currency/unit tokens
  - statement title hints

This index is still deterministic and local.

### Field-First Retriever

For each selected field, retrieve from the evidence index using multiple weak signals:

- existing field aliases
- numeric/table density
- period/year co-occurrence
- currency/unit co-occurrence
- optional statement kind bonus

Statement kind can increase score but must not be required.

### Prompt Budget Check

The validation should compute the total text sent for top-k candidates and assert that it stays under a fixed budget, for example:

- default top-k: `8`
- max candidate text chars per field: `12_000`

This proves the design does not degrade into whole-PDF prompting.

## Acceptance Criteria

- A default pytest test demonstrates a fixture where statement-first is not sufficient but field-first retrieval finds all selected core fields.
- Retrieved candidates include evidence references for every returned candidate.
- Prompt budget is bounded and asserted in tests.
- Existing tests still pass.
- A separate optional script can run the same validation against the local 00001 PDF and print recall/prompt-size metrics without calling an LLM.

## Decision Rule

If the synthetic validation passes and the 00001 metrics show reasonable top-k prompt sizes, the next roadmap step should be a field-first extraction prototype.

If the validation fails, do not proceed to LLM extraction changes; improve indexing/retrieval first.
