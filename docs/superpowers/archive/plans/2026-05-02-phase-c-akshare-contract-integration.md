# Phase C AKShare Contract Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the existing AKShare adapter to the Phase B source artifact manifest and replay-validation contract.

**Architecture:** Keep provider conversion in the existing adapters. Add provider-neutral artifact tracking and finalization in `structured_sources/artifacts.py`: `SourceArtifactStore` records every artifact it writes, and `finalize_source_artifacts()` writes `source_artifact_manifest.json` then validates `SourceEvidence.artifact_id` references. Wire adapter-backed source validation runs through that helper while keeping captured-inventory runs backward-compatible.

**Tech Stack:** Python 3.11 standard library, pathlib/json/hashlib, frozen dataclasses, pytest, existing structured source artifact and AKShare adapter modules.

---

## Files

- Modify: `src/financial_report_llm_extractor/structured_sources/artifacts.py`
  - Add `SourceArtifactStore.artifacts` tracking and a small `finalize_source_artifacts()` helper that writes and validates manifests.
- Modify: `src/financial_report_llm_extractor/structured_sources/real_source_validation.py`
  - Write manifest from `SourceArtifactStore.artifacts`, replay-validate inventory, and include manifest path in summary.
- Modify: `tests/test_source_artifacts.py`
  - Unit test artifact store tracking and `finalize_source_artifacts()`.
- Modify: `tests/test_akshare_adapter.py`
  - Fixture tests proving AKShare records can be replay-validated through the manifest for `600519`, `00001`, and `01113`.
- Modify: `tests/test_real_source_validation.py`
  - Tests that adapter-backed validation writes the manifest and captured validation remains manifest-optional.
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
  - Mark PC2 as the Phase C follow-up.

## Task 1: Provider-Neutral Artifact Store Tracking And Finalization

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/artifacts.py`
- Modify: `tests/test_source_artifacts.py`

- [ ] **Step 1: Write failing artifact store tracking test**

Add to `tests/test_source_artifacts.py`:

```python
from financial_report_llm_extractor.structured_sources.artifacts import (
    finalize_source_artifacts,
)
```

Add:

```python
def test_source_artifact_store_tracks_written_artifacts(tmp_path: Path) -> None:
    store = SourceArtifactStore(tmp_path)

    artifact = store.write_json(
        source="akshare",
        artifact_id="akshare_cn_600519_balance_sheet",
        payload={"rows": []},
    )

    assert store.artifacts == (artifact,)
```

- [ ] **Step 2: Run failing tracking test**

Run:

```bash
uv run pytest tests/test_source_artifacts.py::test_source_artifact_store_tracks_written_artifacts -v
```

Expected: FAIL because `SourceArtifactStore.artifacts` does not exist.

- [ ] **Step 3: Implement artifact store tracking**

In `SourceArtifactStore.__init__()` add:

```python
        self._artifacts: list[SourceArtifact] = []
```

Add property:

```python
    @property
    def artifacts(self) -> tuple[SourceArtifact, ...]:
        return tuple(self._artifacts)
```

In `SourceArtifactStore.write_json()`, after `artifact.validate()` and before returning:

```python
        self._artifacts.append(artifact)
```

- [ ] **Step 4: Run tracking test**

Run:

```bash
uv run pytest tests/test_source_artifacts.py::test_source_artifact_store_tracks_written_artifacts -v
```

Expected: PASS.

- [ ] **Step 5: Write failing finalization helper test**

Add:

```python
def test_finalize_source_artifacts_writes_manifest_and_replay_validates(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path / "source_artifacts")
    artifact = store.write_json(
        source="akshare",
        artifact_id="akshare_cn_600519_balance_sheet",
        payload={"rows": [{"field": "资产总计", "value": "100"}]},
    )
    evidence = SourceEvidence(
        source="akshare",
        adapter="akshare",
        function="stock_balance_sheet_by_report_em",
        artifact_id=artifact.artifact_id,
        raw_record_id="600519:CN:balance_sheet:2024-12-31:0",
        raw_field_name="资产总计",
    )
    record = SourceInventoryRecord(
        source="akshare",
        market="CN",
        ticker="600519",
        statement_type="balance_sheet",
        period="2024-12-31",
        raw_field_name="资产总计",
        raw_value="100",
        parsed_numeric_value=Decimal("100"),
        currency="CNY",
        unit="yuan",
        source_evidence=(evidence,),
    )

    manifest = finalize_source_artifacts(
        artifact_root=tmp_path / "source_artifacts",
        artifacts=(artifact,),
        records=(record,),
        manifest_path=tmp_path / "source_artifact_manifest.json",
    )

    assert manifest.artifacts[0].artifact_id == artifact.artifact_id
    assert (tmp_path / "source_artifact_manifest.json").exists()
```

- [ ] **Step 6: Run failing helper test**

Run:

```bash
uv run pytest tests/test_source_artifacts.py::test_finalize_source_artifacts_writes_manifest_and_replay_validates -v
```

Expected: FAIL because `finalize_source_artifacts()` is not defined.

- [ ] **Step 7: Implement helper**

Add to `src/financial_report_llm_extractor/structured_sources/artifacts.py`:

```python
def finalize_source_artifacts(
    *,
    artifact_root: Path,
    artifacts: Iterable[SourceArtifact],
    records: Iterable[SourceInventoryRecord],
    manifest_path: Path,
) -> SourceArtifactManifest:
    artifact_tuple = tuple(artifacts)
    record_tuple = tuple(records)
    manifest = write_source_artifact_manifest(
        manifest_path,
        artifact_root=artifact_root,
        artifacts=artifact_tuple,
    )
    validate_source_inventory_artifacts(
        manifest,
        record_tuple,
        artifact_root,
    )
    return manifest
```

- [ ] **Step 8: Run helper test**

Run:

```bash
uv run pytest tests/test_source_artifacts.py::test_finalize_source_artifacts_writes_manifest_and_replay_validates -v
```

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

Run:

```bash
git add src/financial_report_llm_extractor/structured_sources/artifacts.py tests/test_source_artifacts.py
git commit -m "feat: track and finalize source artifacts"
```

## Task 2: AKShare Fixture Replay Validation

**Files:**
- Modify: `tests/test_akshare_adapter.py`

- [ ] **Step 1: Write replay validation fixture tests**

Extend imports:

```python
from financial_report_llm_extractor.structured_sources.artifacts import (
    finalize_source_artifacts,
)
```

Add:

```python
def test_akshare_cn_inventory_replay_validates_against_manifest(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path / "source_artifacts")
    adapter = AkshareAdapter(client=FakeAkshareClient(), artifact_store=store)
    records = adapter.fetch_cn_statement_inventory(
        ticker="600519",
        exchange="SH",
        statement_type="balance_sheet",
        unit="yuan",
    )

    manifest = finalize_source_artifacts(
        artifact_root=tmp_path / "source_artifacts",
        artifacts=store.artifacts,
        records=records,
        manifest_path=tmp_path / "source_artifact_manifest.json",
    )

    assert manifest.artifacts[0].artifact_id == "akshare_cn_600519_balance_sheet"
```

Add a second HK ticker fake:

```python
class FakeAkshareClient01113(FakeAkshareClient):
    def stock_financial_hk_report_em(
        self,
        stock: str,
        symbol: str,
        indicator: str,
    ) -> list[dict[str, object]]:
        assert stock == "01113"
        assert symbol == "资产负债表"
        assert indicator == "年度"
        return [
            {
                "REPORT_DATE": "2024-12-31",
                "FISCAL_YEAR": "2024",
                "STD_ITEM_CODE": "HK_BAL_TOTAL_ASSETS",
                "STD_ITEM_NAME": "Total assets",
                "AMOUNT": "200",
            }
        ]

    def stock_financial_hk_report_metadata(
        self,
        stock: str,
    ) -> list[dict[str, object]]:
        assert stock == "01113"
        return [
            {
                "REPORT_DATE": "2024-12-31",
                "CURRENCY": "HKD",
                "ACCOUNT_STANDARD": "HKFRS",
                "REPORT_TYPE": "年报",
            }
        ]
```

Add:

```python
def test_akshare_hk_00001_inventory_replay_validates_against_manifest(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path / "source_artifacts")
    adapter = AkshareAdapter(client=FakeAkshareClient(), artifact_store=store)
    records = adapter.fetch_hk_statement_inventory(
        ticker="00001",
        statement_type="balance_sheet",
        unit="HKD",
    )

    manifest = finalize_source_artifacts(
        artifact_root=tmp_path / "source_artifacts",
        artifacts=store.artifacts,
        records=records,
        manifest_path=tmp_path / "source_artifact_manifest.json",
    )

    assert manifest.artifacts[0].artifact_id == "akshare_hk_00001_balance_sheet"
    assert records[0].currency == "HKD"
```

Add:

```python
def test_akshare_hk_01113_inventory_replay_validates_against_manifest(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path / "source_artifacts")
    adapter = AkshareAdapter(client=FakeAkshareClient01113(), artifact_store=store)
    records = adapter.fetch_hk_statement_inventory(
        ticker="01113",
        statement_type="balance_sheet",
        unit="HKD",
    )

    manifest = finalize_source_artifacts(
        artifact_root=tmp_path / "source_artifacts",
        artifacts=store.artifacts,
        records=records,
        manifest_path=tmp_path / "source_artifact_manifest.json",
    )

    assert manifest.artifacts[0].artifact_id == "akshare_hk_01113_balance_sheet"
    assert records[0].currency == "HKD"
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
uv run pytest tests/test_akshare_adapter.py::test_akshare_cn_inventory_replay_validates_against_manifest tests/test_akshare_adapter.py::test_akshare_hk_00001_inventory_replay_validates_against_manifest tests/test_akshare_adapter.py::test_akshare_hk_01113_inventory_replay_validates_against_manifest -v
```

Expected: PASS if Task 1 was implemented correctly; FAIL if artifact store tracking or replay integration is incomplete.

- [ ] **Step 3: Fix only if needed**

If tests fail, adjust only `SourceArtifactStore.artifacts` tracking or test fixtures. Do not change Turtle mapping or real network code.

- [ ] **Step 4: Run AKShare tests**

Run:

```bash
uv run pytest tests/test_akshare_adapter.py tests/test_source_artifacts.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add tests/test_akshare_adapter.py
git commit -m "test: replay validate akshare fixtures"
```

## Task 3: Real Source Validation Writes Manifest For Adapter Runs

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/real_source_validation.py`
- Modify: `tests/test_real_source_validation.py`

- [ ] **Step 1: Write failing summary manifest test**

Add to `tests/test_real_source_validation.py` or extend the existing adapter-backed test:

```python
def test_real_source_validation_writes_source_artifact_manifest(
    tmp_path: Path,
) -> None:
    result = run_real_source_validation(
        samples=(
            RealSourceValidationSample(
                provider="akshare",
                market="CN",
                ticker="600519",
                statement_type="income_statement",
                currency="CNY",
                unit="yuan",
                exchange="SH",
            ),
        ),
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path,
        akshare_client=FakeAkshareClient(),
    )

    manifest_path = tmp_path / "source_artifact_manifest.json"
    assert manifest_path.exists()
    assert result.summary["artifact_paths"]["source_artifact_manifest"] == str(manifest_path)
```

Use the local fake client pattern already present in `tests/test_real_source_validation.py`.

- [ ] **Step 2: Run failing test**

Run:

```bash
uv run pytest tests/test_real_source_validation.py::test_real_source_validation_writes_source_artifact_manifest -v
```

Expected: FAIL because adapter-backed validation does not write manifest yet.

- [ ] **Step 3: Wire manifest finalization**

In `real_source_validation.py`, import:

```python
from financial_report_llm_extractor.structured_sources.artifacts import (
    finalize_source_artifacts,
)
```

After writing `source_inventory.jsonl`, call:

```python
    manifest = finalize_source_artifacts(
        artifact_root=output_dir / "source_artifacts",
        artifacts=artifact_store.artifacts,
        records=records,
        manifest_path=output_dir / "source_artifact_manifest.json",
    )
```

Pass `source_artifact_manifest_path=output_dir / "source_artifact_manifest.json"` and `source_artifact_count=len(manifest.artifacts)` into `_write_validation_outputs()`.

Keep `run_captured_source_validation()` passing `None` for the manifest path and count.

- [ ] **Step 4: Update summary writer signature**

Update `_write_validation_outputs()` to accept:

```python
source_artifact_manifest_path: Path | None = None
source_artifact_count: int | None = None
```

When `source_artifact_manifest_path` is not `None`, add:

```python
summary["artifact_paths"]["source_artifact_manifest"] = str(source_artifact_manifest_path)
summary["source_artifact_count"] = source_artifact_count
```

- [ ] **Step 5: Add captured validation compatibility assertion**

Extend `test_captured_source_validation_reuses_saved_inventory_without_clients`:

```python
    assert "source_artifact_manifest" not in result.summary["artifact_paths"]
    assert "source_artifact_count" not in result.summary
    assert not (tmp_path / "source_artifact_manifest.json").exists()
```

This protects captured inventory replay from accidentally requiring raw source artifacts.

- [ ] **Step 6: Run real source validation tests**

Run:

```bash
uv run pytest tests/test_real_source_validation.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

Run:

```bash
git add src/financial_report_llm_extractor/structured_sources/real_source_validation.py tests/test_real_source_validation.py
git commit -m "feat: write source artifact manifest in validation"
```

## Task 4: Roadmap And Verification

**Files:**
- Review: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`

- [ ] **Step 1: Confirm roadmap Phase C note**

Confirm the Phase C section already includes:

```markdown
Implementation note:

- Phase C baseline AKShare fixture adapter exists for HK and CN statements.
- PC2 should integrate AKShare adapter runs with PB2 artifact manifests and replay validation.
- Adapter-backed validation should write `source_artifact_manifest.json`; captured inventory validation remains manifest-optional.
```

Only edit the roadmap if implementation reveals a new Phase C decision that is not already captured.

- [ ] **Step 2: Run focused tests**

Run:

```bash
uv run pytest tests/test_akshare_adapter.py tests/test_real_source_validation.py tests/test_source_artifacts.py -v
```

Expected: PASS.

- [ ] **Step 3: Run full verification**

Run:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
git diff --check
```

Expected: all commands pass.

- [ ] **Step 4: Commit any roadmap update if needed**

If the roadmap changed during implementation, run:

```bash
git add docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md
git commit -m "docs: update phase c akshare contract roadmap"
```

If there is no roadmap diff, skip this commit.

## Self-Review

- Spec coverage: Task 1 covers provider-neutral artifact tracking and finalization; Task 2 covers AKShare replay-validated fixtures for `600519`, `00001`, and `01113`; Task 3 covers validation output manifest writing, summary paths, and captured-run manifest optionality; Task 4 covers roadmap confirmation and verification.
- Placeholder scan: no task uses placeholder wording; each implementation step includes exact code or exact commands.
- Type consistency: the plan consistently uses `SourceArtifact`, `SourceArtifactManifest`, `finalize_source_artifacts()`, and existing `AkshareAdapter`/`RealSourceValidationResult` names.
