# Extraction Review Checklist

Use this checklist after generating `extraction_result.json` or `evaluation_summary.json`.

## Required Checks

- Every `present` item has evidence with `page`, `chunk_id`, `block_id`, and `snippet`.
- All present monetary items include `money.normalized_value`.
- The normalized money value matches the report unit context.
- Missing, ambiguous, not-applicable, and extraction-failed items are explicit.
- Retrieval candidates are statement-relevant and not generic narrative text when a statement row is available.
- Raw LLM response artifacts exist for real-provider runs.

## Review Output

Summarize:

- Total fields reviewed.
- Counts for present, missing, ambiguous, not_applicable, and extraction_failed.
- Fields present without evidence.
- Present monetary items without normalized values.
- Any field whose snippet does not visibly support the extracted value.

