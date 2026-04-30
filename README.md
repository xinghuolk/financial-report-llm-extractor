# Financial Report LLM Extractor

Independent LLM-first financial report extraction project.

This project is intentionally separate from the deterministic
`financial-report-analysis` architecture. Its job is to extract Turtle-style
financial report inputs from annual-report PDFs with evidence-grounded,
reviewable JSON output.

## Scope

- Parse PDFs into page text, table blocks, layout metadata, and chunks.
- Store chunks for retrieval and evidence lookup.
- Use a Turtle v0.15 field catalog with extraction priority.
- Retrieve candidate evidence per field.
- Ask an LLM to produce structured extracted items.
- Require page/chunk evidence for every `present` value.
- Export JSON for review, comparison, or optional downstream adapters.

## Planning Docs

- Requirements:
  `docs/requirements/2026-04-30-llm-first-financial-report-extractor-requirements.md`
- Design:
  `docs/design/2026-04-30-llm-first-turtle-financial-extraction-design.md`
- Roadmap:
  `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`

## Non-Goals

- No canonical fact promotion.
- No metric lifecycle governance.
- No recompute decision engine.
- No dependency on the existing P5/Turtle export pipeline.
- No UI or async workflow in the first slice.

## First Slice

The first usable slice should handle one annual-report PDF at a time:

1. Build a document chunk index.
2. Extract P0 and P1 Turtle fields.
3. Return structured JSON with value, unit, period, scope, confidence, and
   evidence.
4. Mark missing or ambiguous fields explicitly.
