# Confidence Calibration Workflow

Phase I-A.2 follow-up #4 — framework for setting confidence threshold based
on human-verified accuracy data.

## Status

Framework: implemented. Calibration data: not yet collected.

## Mechanism

Both `extract-llm` and `extract-llm-batch` accept `--confidence-threshold`.
When set, fields whose LLM-reported confidence is below the threshold are
demoted from `present` to `extraction_failed` with a `low_confidence` error.
The original value, currency, page, etc. are preserved in the result for
audit, but the field is no longer counted as `present`.

Default: `None` (no gating). Existing behavior preserved.

## Recommended calibration procedure

To choose a threshold, you need a labeled dataset:

1. **Collect**: Run `extract-llm-batch` against ~10-20 HK companies covering
   different layouts (conglomerate / real estate / tech / restaurant / bank).
2. **Spot-check** each `(company, field)` pair: verify the LLM-cited value
   against the actual PDF page. Record:
   - LLM confidence (from the result)
   - Correct (matches PDF) or Incorrect (different value or hallucinated)
3. **Plot precision/recall vs threshold**:
   - For threshold T ∈ {0.5, 0.6, 0.7, 0.8, 0.9}:
     - Precision = (correct present at confidence ≥ T) / (all present at conf ≥ T)
     - Recall = (correct present at conf ≥ T) / (all correct present)
4. **Pick threshold**:
   - High-precision use case (e.g., feeding factual database): pick threshold
     where precision ≥ 0.95
   - Discovery use case (e.g., flagging candidates for human review): pick
     where recall ≥ 0.9

## Suggested initial threshold (without data)

Based on Phase I-A demo + I-A.2 validation observations:
- LLMs (DeepSeek) report high confidence (≥0.9) for clean income-statement
  matches and lower (<0.8) for aggregations or notes-derived values.
- A conservative starting threshold of `0.85` would likely demote ~10-20%
  of `present` results without major false-negative cost.
- A permissive starting threshold of `0.7` would catch only the most
  uncertain cases.

Choose based on downstream consumer's risk tolerance.

## Calibration data location

Once collected:
- `tests/fixtures/llm_calibration/calibration_dataset.csv` (gitignored if
  contains real values; or committed if anonymized)
- Columns: `company_id, field_id, llm_value, pdf_value, confidence, correct`
- Analysis script: `scripts/phase_i_a_demo/calibrate_confidence.py` (TBD when
  data exists)

## When to revisit

- After 50+ verified `(company, field)` pairs are labeled
- After observing significant precision drop in a real consumer use case
- When upgrading the LLM provider (different confidence scoring distributions)
