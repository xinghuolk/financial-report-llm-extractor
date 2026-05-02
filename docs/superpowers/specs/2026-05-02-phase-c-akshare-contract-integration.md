# Phase C AKShare Contract Integration Spec

> Date: 2026-05-02
> Status: design spec
> Scope: integrate the existing AKShare adapter with the Phase B artifact manifest and replay-validation contract.

## 1. Purpose

The baseline Phase C AKShare adapter already converts injected AKShare-like fixture clients into `SourceInventoryRecord` rows and raw JSON artifacts. PB2 then hardened the artifact layer with `source_artifact_manifest.json`, stable manifest/JSONL validation, and replay validation from `SourceEvidence.artifact_id` back to raw artifact files.

PC2 connects those pieces. AKShare validation runs should be able to fetch or replay fixture records, write a raw artifact manifest, write source inventory JSONL, and prove every present source evidence item points to a valid raw artifact without making another provider request.

## 2. Goals

PC2 must provide:

- A small artifact finalization helper for AKShare validation outputs.
- `source_artifact_manifest.json` generation for AKShare raw artifacts.
- Replay validation of AKShare `SourceInventoryRecord.source_evidence` against the manifest and raw artifact files.
- Provider-neutral tracking of artifacts written through `SourceArtifactStore`, so mixed AKShare/Yahoo validation runs do not lose non-AKShare artifacts.
- Fixture-backed tests for CN `600519` and HK `00001` / `01113` AKShare-like responses.
- Structured summary paths for source inventory and source artifact manifest.
- No default real AKShare calls in unit tests.

## 3. Non-Goals

PC2 does not:

- Expand Turtle source mapping coverage.
- Add new AKShare API endpoints beyond the existing statement adapter shape.
- Change Yahoo/yfinance behavior.
- Promote canonical facts.
- Add PDF/LLM fallback.
- Depend on live AKShare network calls in normal tests.

Real AKShare smoke remains opt-in and should be run sparingly because the API may rate-limit or change shape.

## 4. Existing Baseline

Existing AKShare code:

- `src/financial_report_llm_extractor/structured_sources/akshare_adapter.py`
  - `AkshareAdapter.fetch_hk_statement_inventory()`
  - `AkshareAdapter.fetch_cn_statement_inventory()`
  - injected `AkshareClient` protocol
  - raw artifact writes through `SourceArtifactStore`
- `tests/test_akshare_adapter.py`
  - HK balance sheet fixture path
  - CN balance sheet fixture path
  - unsupported statement status
  - empty CN rows as `missing`
- `src/financial_report_llm_extractor/structured_sources/real_source_validation.py`
  - opt-in real/captured validation entrypoints
  - source inventory JSONL output
  - mapping/reconciliation/export artifacts

Existing PB2 artifact code:

- `write_source_artifact_manifest()`
- `read_source_artifact_manifest()`
- `validate_source_inventory_artifacts()`
- hardened `read_source_inventory()`

PC2 should reuse those functions directly.

## 5. Artifact Finalization Contract

Recommended helper:

```python
finalize_source_artifacts(
    *,
    artifact_root: Path,
    artifacts: Iterable[SourceArtifact],
    records: Iterable[SourceInventoryRecord],
    manifest_path: Path,
) -> SourceArtifactManifest
```

Rules:

- The helper writes `source_artifact_manifest.json` using PB2 `write_source_artifact_manifest()`.
- It immediately calls `validate_source_inventory_artifacts()` with the written manifest, records, and artifact root.
- It returns the manifest for summary/reporting.
- It does not call AKShare, Yahoo, yfinance, or any network source.
- It should be provider-neutral, but PC2 only needs to wire it through AKShare validation paths.

The helper may live in `structured_sources/artifacts.py` if it remains provider-neutral, or in `real_source_validation.py` if implementation should stay local to validation runs. Prefer the provider-neutral location if the code is less than a few focused functions.

`SourceArtifactStore` should also expose the artifacts written during a run:

```python
SourceArtifactStore.artifacts -> tuple[SourceArtifact, ...]
```

This is the preferred artifact collection point. It avoids making each provider adapter maintain separate artifact lists and allows mixed AKShare/Yahoo/source-error validation runs to write one complete manifest.

## 6. Validation Output Contract

For real or fixture-backed source validation, output directories should include:

```text
source_artifacts/
  akshare/
    <artifact_id>.json
source_artifact_manifest.json
source_inventory.jsonl
real_source_validation_summary.json
```

The summary should include paths for:

- `source_artifact_manifest`
- `source_inventory`
- existing mapping/reconciliation/export paths

The summary may include a manifest artifact count. The count should reflect raw source artifact entries, not inventory rows.

## 7. AKShare Fixture Coverage Contract

PC2 should add or strengthen fixture-backed coverage for:

- `600519` CN A-share statement inventory.
- `00001` HK statement inventory with HKD metadata.
- `01113` HK statement inventory with a second HK ticker shape.

The tests should prove:

- AKShare adapter writes raw JSON artifacts.
- Source inventory rows point to those artifacts through `SourceEvidence.artifact_id`.
- The manifest can be written and replay-validated without re-calling the client.
- The artifacts used for replay validation come from the shared `SourceArtifactStore`.
- Currency/unit metadata is explicit for present money rows or represented as `unknown` where metadata is not available.

These tests should use fake injected clients only.

## 8. Captured Inventory Contract

Captured source validation currently starts from an existing `source_inventory.jsonl`, so it may not have raw artifacts available. PC2 should not require replay validation for captured-only runs unless a source artifact manifest and artifact root are supplied.

Rules:

- Real/fake adapter runs that create raw artifacts in the same output directory must write and validate a manifest.
- Captured inventory replay remains allowed without raw artifacts.
- If captured replay is later desired, it should be a separate option requiring `--source-artifact-manifest` and `--source-artifact-root`.

## 9. Error Handling

PC2 errors should follow PB2 behavior:

- Missing artifact ID: stable `ValueError` containing the artifact ID.
- Missing artifact file: stable `ValueError` containing the artifact ID.
- Hash mismatch: stable `ValueError` containing the artifact ID.
- Root escape: stable `ValueError` containing the artifact ID.

`run_real_source_validation()` already captures provider failures as source-error records. Manifest/replay validation failures are local consistency failures and should fail the run rather than becoming provider source-error records.

## 10. Success Criteria

PC2 is complete when:

- AKShare adapter fixture tests can write raw artifacts, write a manifest, and replay-validate inventory evidence.
- `run_real_source_validation()` writes `source_artifact_manifest.json` for adapter-backed runs.
- Validation summary includes the manifest path.
- Captured inventory validation remains backward-compatible without raw artifacts.
- Focused structured source tests and full project validation pass.
