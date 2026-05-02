# Phase B Source Artifact Contract Hardening Spec

> Date: 2026-05-02
> Status: design spec
> Scope: harden the already-existing Phase B source artifact and source inventory boundary before expanding AKShare/Yahoo adapters.

## 1. Purpose

The original Phase B created the first `SourceArtifactStore` and `SourceInventoryRecord` JSONL persistence layer. That was enough for fixture-backed source-first prototyping, but it predates the full Turtle taxonomy and coverage matrix introduced in Phase A.

This follow-up keeps Phase B's current shape and makes it reliable as a provider-independent contract. Phase C and Phase D adapters should be able to write raw provider artifacts once, build inventory records from those artifacts, and replay or review the result without calling AKShare or Yahoo again.

## 2. Goals

PB2 must provide:

- A manifest for raw source artifacts with stable IDs, paths, content types, and file hashes.
- Deterministic artifact ID/path behavior that is safe for provider, market, ticker, and artifact-type inputs.
- Stable validation errors for malformed source inventory JSONL.
- A replay check that verifies inventory evidence references real raw artifacts.
- Fixture-only tests that do not call AKShare, Yahoo, yfinance, MCP servers, or any network endpoint.

## 3. Non-Goals

PB2 does not:

- Add real AKShare calls.
- Add real Yahoo/yfinance calls.
- Expand Turtle field mappings.
- Implement reconciliation or derivation.
- Add PDF/LLM fallback behavior.
- Add database, UI, async workflow, or canonical fact promotion.

Provider-specific behavior remains outside this phase. PB2 only defines the offline storage and validation boundary those adapters will use.

## 4. Existing Baseline

Existing code already provides:

- `src/financial_report_llm_extractor/structured_sources/artifacts.py`
  - `build_artifact_id()`
  - `SourceArtifactStore.write_json()`
  - `write_source_inventory()`
  - `read_source_inventory()`
- `src/financial_report_llm_extractor/structured_sources/models.py`
  - `SourceArtifact`
  - `SourceEvidence`
  - `SourceInventoryRecord`
- `tests/test_source_artifacts.py`
  - deterministic raw JSON artifact write coverage
  - inventory JSONL roundtrip coverage

PB2 should extend this baseline. It should not rewrite the structured source model.

## 5. Source Artifact Manifest Contract

Raw artifacts should be collected in a manifest so downstream code can inspect and validate source evidence without scanning arbitrary files.

Recommended artifact:

```text
source_artifact_manifest.json
```

Required top-level fields:

- `manifest_id`
- `version`
- `artifact_root`
- `artifacts`

Required artifact entry fields:

- `source`
- `artifact_id`
- `path`
- `content_type`
- `sha256`

Optional provider context fields:

- `market`
- `ticker`
- `statement_type`
- `function`
- `schema_version`
- `created_by`

Validation rules:

- `artifacts` must be a list of objects.
- Each `artifact_id` must be non-empty and unique.
- Each `path` must be relative and must not escape the artifact root.
- Each `sha256` must be a 64-character lowercase hex digest.
- Manifest entries should be sorted by `(source, artifact_id, path)` when written.
- Loader errors must be stable `ValueError` messages and must not leak raw `KeyError`, `TypeError`, or `AttributeError`.

## 6. Artifact ID And Path Contract

`build_artifact_id()` remains the canonical helper for provider artifact IDs.

Rules:

- IDs are lowercase ASCII slugs joined by `_`.
- Empty input parts are ignored only after slugging has proven there is remaining content in at least one part.
- Fully empty IDs are invalid.
- Slugged IDs must contain only `0-9`, `a-z`, and `_`.
- Colliding artifact IDs in one manifest are invalid.
- Raw artifact writes remain under `<artifact_root>/<source>/<artifact_id>.json`.

The artifact writer should keep using sorted, indented JSON with a trailing newline.

## 7. Source Inventory JSONL Validation Contract

`read_source_inventory()` currently assumes each JSONL line decodes into the exact expected dict shape. PB2 must make this reader safe for real provider fixture files.

Validation rules:

- Blank lines are ignored.
- Each non-blank line must parse as JSON.
- Each decoded line must be a JSON object.
- `source_evidence` may be omitted and defaults to an empty tuple.
- If `source_evidence` is present, it must be a list.
- Each evidence item must be a JSON object.
- `parsed_numeric_value` must be convertible to `Decimal` when present.
- The final reconstructed `SourceInventoryRecord.validate()` remains the business invariant gate.
- Reader errors must include the JSONL line number.
- Reader errors must be stable `ValueError` messages and must not leak raw `KeyError`, `TypeError`, `AttributeError`, `decimal.InvalidOperation`, or `json.JSONDecodeError`.

## 8. Replay Validation Contract

PB2 should add a validation helper that checks inventory evidence against the raw artifact manifest.

Recommended helper:

```python
validate_source_inventory_artifacts(
    manifest: SourceArtifactManifest,
    records: Iterable[SourceInventoryRecord],
    artifact_root: Path,
) -> None
```

Rules:

- Every `SourceEvidence.artifact_id` in every inventory record must exist in the manifest.
- The referenced manifest entry path must exist under `artifact_root`.
- The file hash must match the manifest `sha256`.
- Missing artifact references raise `ValueError`.
- Missing files raise `ValueError`.
- Hash mismatches raise `ValueError`.
- Error messages include the affected `artifact_id`.

## 9. Determinism And Offline Operation

PB2 artifacts must be deterministic:

- JSON output uses sorted keys and a final newline.
- Manifest artifacts are sorted before write.
- Inventory writer preserves the input record order.
- Tests use local `tmp_path` fixtures only.
- No test may require network access or provider credentials.

## 10. Success Criteria

PB2 is complete when:

- A source artifact manifest can be written, read, and validated.
- Manifest validation rejects malformed shapes and duplicate artifact IDs with stable errors.
- Source inventory JSONL reader rejects malformed lines with stable line-numbered errors.
- Inventory evidence can be replay-validated against raw artifact files and hashes.
- Structured source tests pass without provider calls.
- Roadmap Phase B clearly distinguishes the completed baseline from this hardening follow-up.

