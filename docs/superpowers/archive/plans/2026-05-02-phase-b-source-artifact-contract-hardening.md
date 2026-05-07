# Phase B Source Artifact Contract Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the existing Phase B source artifact and inventory boundary with manifests, stable JSONL validation errors, and offline replay checks.

**Architecture:** Extend `structured_sources/artifacts.py` without changing adapter boundaries. Raw provider payloads stay in deterministic JSON files; a manifest records file metadata and hashes; source inventory JSONL readers validate shape before reconstructing `SourceInventoryRecord`; replay validation checks inventory evidence against the manifest and files on disk.

**Tech Stack:** Python 3.11 standard library, `dataclasses`, `hashlib`, `json`, `pathlib`, `Decimal`, pytest, existing `structured_sources` dataclasses.

---

## Files

- Modify: `src/financial_report_llm_extractor/structured_sources/artifacts.py`
  - Add manifest dataclasses/helpers, inventory JSONL shape validation, and replay validation.
- Modify: `tests/test_source_artifacts.py`
  - Add focused tests for manifest roundtrip, manifest rejection, JSONL malformed input, and replay validation.
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
  - Record PB2 as the Phase B follow-up before provider adapter expansion.

## Task 1: Source Artifact Manifest Roundtrip

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/artifacts.py`
- Modify: `tests/test_source_artifacts.py`

- [ ] **Step 1: Write failing manifest roundtrip test**

Add imports in `tests/test_source_artifacts.py`:

```python
from financial_report_llm_extractor.structured_sources.artifacts import (
    SourceArtifactStore,
    build_artifact_id,
    read_source_artifact_manifest,
    read_source_inventory,
    write_source_artifact_manifest,
    write_source_inventory,
)
```

Add this test:

```python
def test_source_artifact_manifest_roundtrip_includes_hash_and_sorts_entries(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path)
    second = store.write_json(
        source="yahoo",
        artifact_id="yahoo_hk_00001_income_statement",
        payload={"rows": [{"field": "Total Revenue", "value": 10}]},
    )
    first = store.write_json(
        source="akshare",
        artifact_id="akshare_hk_00001_balance_sheet",
        payload={"rows": [{"field": "Total assets", "value": 100}]},
    )
    manifest_path = tmp_path / "source_artifact_manifest.json"

    manifest = write_source_artifact_manifest(
        manifest_path,
        artifact_root=tmp_path,
        artifacts=(second, first),
    )
    loaded = read_source_artifact_manifest(manifest_path)

    assert loaded.manifest_id == manifest.manifest_id
    assert [entry.artifact_id for entry in loaded.artifacts] == [
        "akshare_hk_00001_balance_sheet",
        "yahoo_hk_00001_income_statement",
    ]
    assert all(len(entry.sha256) == 64 for entry in loaded.artifacts)
    assert loaded.artifacts[0].path == "akshare/akshare_hk_00001_balance_sheet.json"
```

- [ ] **Step 2: Run failing test**

Run:

```bash
uv run pytest tests/test_source_artifacts.py::test_source_artifact_manifest_roundtrip_includes_hash_and_sorts_entries -v
```

Expected: FAIL because manifest helpers are not defined.

- [ ] **Step 3: Implement manifest dataclasses and helpers**

Add to `src/financial_report_llm_extractor/structured_sources/artifacts.py`:

```python
import hashlib
from dataclasses import asdict, dataclass
```

Replace the existing dataclass import line with the combined import above.

Add these dataclasses and helpers near `SourceArtifactStore`:

```python
@dataclass(frozen=True)
class SourceArtifactManifestEntry:
    source: SourceName
    artifact_id: str
    path: str
    content_type: str
    sha256: str
    market: str | None = None
    ticker: str | None = None
    statement_type: str | None = None
    function: str | None = None
    schema_version: str | None = None
    created_by: str | None = None

    def validate(self) -> None:
        if not self.source:
            raise ValueError("manifest entry source is required")
        if not self.artifact_id:
            raise ValueError("manifest entry artifact_id is required")
        if not self.path:
            raise ValueError("manifest entry path is required")
        if Path(self.path).is_absolute() or ".." in Path(self.path).parts:
            raise ValueError("manifest entry path must be relative to artifact root")
        if not self.content_type:
            raise ValueError("manifest entry content_type is required")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("manifest entry sha256 must be lowercase hex")


@dataclass(frozen=True)
class SourceArtifactManifest:
    manifest_id: str
    version: str
    artifact_root: str
    artifacts: tuple[SourceArtifactManifestEntry, ...]

    def validate(self) -> None:
        if not self.manifest_id:
            raise ValueError("manifest_id is required")
        if not self.version:
            raise ValueError("manifest version is required")
        seen: set[str] = set()
        for entry in self.artifacts:
            entry.validate()
            if entry.artifact_id in seen:
                raise ValueError(f"duplicate artifact_id: {entry.artifact_id}")
            seen.add(entry.artifact_id)
```

Add writer/reader helpers:

```python
def write_source_artifact_manifest(
    path: Path,
    *,
    artifact_root: Path,
    artifacts: Iterable[SourceArtifact],
    manifest_id: str = "source_artifact_manifest",
    version: str = "1",
) -> SourceArtifactManifest:
    entries = tuple(
        sorted(
            (
                _manifest_entry_from_artifact(artifact_root, artifact)
                for artifact in artifacts
            ),
            key=lambda entry: (entry.source, entry.artifact_id, entry.path),
        )
    )
    manifest = SourceArtifactManifest(
        manifest_id=manifest_id,
        version=version,
        artifact_root=artifact_root.as_posix(),
        artifacts=entries,
    )
    manifest.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_manifest_to_jsonable(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def read_source_artifact_manifest(path: Path) -> SourceArtifactManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid source artifact manifest JSON: {path}") from exc
    manifest = _manifest_from_jsonable(payload)
    manifest.validate()
    return manifest
```

Add private helpers:

```python
def _manifest_entry_from_artifact(
    artifact_root: Path,
    artifact: SourceArtifact,
) -> SourceArtifactManifestEntry:
    artifact.validate()
    full_path = artifact_root / artifact.path
    digest = hashlib.sha256(full_path.read_bytes()).hexdigest()
    return SourceArtifactManifestEntry(
        source=artifact.source,
        artifact_id=artifact.artifact_id,
        path=artifact.path,
        content_type=artifact.content_type,
        sha256=digest,
    )


def _manifest_to_jsonable(manifest: SourceArtifactManifest) -> dict[str, Any]:
    return {
        "manifest_id": manifest.manifest_id,
        "version": manifest.version,
        "artifact_root": manifest.artifact_root,
        "artifacts": [asdict(entry) for entry in manifest.artifacts],
    }


def _manifest_from_jsonable(payload: dict[str, Any]) -> SourceArtifactManifest:
    raw_artifacts = payload.get("artifacts", [])
    entries = tuple(
        SourceArtifactManifestEntry(
            **item
        )
        for item in raw_artifacts
    )
    return SourceArtifactManifest(
        manifest_id=str(payload.get("manifest_id") or ""),
        version=str(payload.get("version") or ""),
        artifact_root=str(payload.get("artifact_root") or ""),
        artifacts=entries,
    )
```

- [ ] **Step 4: Run manifest roundtrip test**

Run:

```bash
uv run pytest tests/test_source_artifacts.py::test_source_artifact_manifest_roundtrip_includes_hash_and_sorts_entries -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add src/financial_report_llm_extractor/structured_sources/artifacts.py tests/test_source_artifacts.py
git commit -m "feat: add source artifact manifest"
```

## Task 2: Manifest Shape And Collision Validation

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/artifacts.py`
- Modify: `tests/test_source_artifacts.py`

- [ ] **Step 1: Write failing malformed manifest tests**

Add:

```python
def test_read_source_artifact_manifest_rejects_non_object_payload(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_artifact_manifest.json"
    path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source artifact manifest must be an object"):
        read_source_artifact_manifest(path)


def test_read_source_artifact_manifest_rejects_duplicate_artifact_id(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_artifact_manifest.json"
    entry = {
        "source": "akshare",
        "artifact_id": "artifact_1",
        "path": "akshare/artifact_1.json",
        "content_type": "application/json",
        "sha256": "a" * 64,
    }
    path.write_text(
        json.dumps(
            {
                "manifest_id": "source_artifact_manifest",
                "version": "1",
                "artifact_root": tmp_path.as_posix(),
                "artifacts": [entry, entry],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate artifact_id: artifact_1"):
        read_source_artifact_manifest(path)


def test_read_source_artifact_manifest_rejects_non_list_artifacts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_artifact_manifest.json"
    path.write_text(
        json.dumps(
            {
                "manifest_id": "source_artifact_manifest",
                "version": "1",
                "artifact_root": tmp_path.as_posix(),
                "artifacts": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source artifact manifest artifacts must be a list"):
        read_source_artifact_manifest(path)
```

Add these imports at the top of `tests/test_source_artifacts.py`:

```python
import json

import pytest
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
uv run pytest tests/test_source_artifacts.py::test_read_source_artifact_manifest_rejects_non_object_payload tests/test_source_artifacts.py::test_read_source_artifact_manifest_rejects_duplicate_artifact_id tests/test_source_artifacts.py::test_read_source_artifact_manifest_rejects_non_list_artifacts -v
```

Expected: FAIL for the malformed-shape cases until shared shape helpers exist or are wired correctly.

- [ ] **Step 3: Add reusable shape helpers**

Add near the private helpers in `artifacts.py`:

```python
def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value
```

Replace the manifest reader line with:

```python
    manifest = _manifest_from_jsonable(_require_object(payload, "source artifact manifest"))
```

Replace the start of `_manifest_from_jsonable()` with:

```python
def _manifest_from_jsonable(payload: dict[str, Any]) -> SourceArtifactManifest:
    raw_artifacts = _require_list(payload.get("artifacts"), "source artifact manifest artifacts")
    entries = tuple(
        SourceArtifactManifestEntry(
            **_require_object(item, f"source artifact manifest artifacts[{index}]")
        )
        for index, item in enumerate(raw_artifacts)
    )
```

- [ ] **Step 4: Run malformed manifest tests**

Run:

```bash
uv run pytest tests/test_source_artifacts.py::test_read_source_artifact_manifest_rejects_non_object_payload tests/test_source_artifacts.py::test_read_source_artifact_manifest_rejects_duplicate_artifact_id tests/test_source_artifacts.py::test_read_source_artifact_manifest_rejects_non_list_artifacts -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add src/financial_report_llm_extractor/structured_sources/artifacts.py tests/test_source_artifacts.py
git commit -m "fix: validate source artifact manifests"
```

## Task 3: Source Inventory JSONL Stable Errors

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/artifacts.py`
- Modify: `tests/test_source_artifacts.py`

- [ ] **Step 1: Write failing JSONL validation tests**

Add:

```python
def test_read_source_inventory_rejects_non_object_line_with_line_number(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source inventory line 1 must be an object"):
        read_source_inventory(path)


def test_read_source_inventory_rejects_non_list_source_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source_inventory.jsonl"
    payload = {
        "source": "akshare",
        "market": "HK",
        "ticker": "00001",
        "statement_type": "balance_sheet",
        "period": "2024-12-31",
        "raw_field_name": "Total assets",
        "raw_value": "100",
        "parsed_numeric_value": "100",
        "currency": "HKD",
        "unit": "HKD",
        "source_evidence": {},
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source inventory line 1 source_evidence must be a list"):
        read_source_inventory(path)
```

- [ ] **Step 2: Run failing JSONL tests**

Run:

```bash
uv run pytest tests/test_source_artifacts.py::test_read_source_inventory_rejects_non_object_line_with_line_number tests/test_source_artifacts.py::test_read_source_inventory_rejects_non_list_source_evidence -v
```

Expected: FAIL because current reader can leak raw Python errors.

- [ ] **Step 3: Harden JSONL reader**

Replace the existing decimal import with:

```python
from decimal import Decimal, InvalidOperation
```

Replace `read_source_inventory()` with:

```python
def read_source_inventory(path: Path) -> tuple[SourceInventoryRecord, ...]:
    records: list[SourceInventoryRecord] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            record = _record_from_jsonable(
                _require_object(payload, f"source inventory line {line_number}"),
                line_number=line_number,
            )
        except json.JSONDecodeError as exc:
            raise ValueError(f"source inventory line {line_number} is invalid JSON") from exc
        except (TypeError, KeyError, ValueError) as exc:
            if str(exc).startswith(f"source inventory line {line_number}"):
                raise
            raise ValueError(f"source inventory line {line_number}: {exc}") from exc
        records.append(record)
    return tuple(records)
```

Replace `_record_from_jsonable()` with:

```python
def _record_from_jsonable(
    payload: dict[str, Any],
    *,
    line_number: int | None = None,
) -> SourceInventoryRecord:
    label = "source inventory"
    if line_number is not None:
        label = f"source inventory line {line_number}"
    payload = dict(payload)
    raw_evidence = payload.pop("source_evidence", [])
    evidence_items = _require_list(raw_evidence, f"{label} source_evidence")
    evidence = tuple(
        SourceEvidence(**_require_object(item, f"{label} source_evidence[{index}]"))
        for index, item in enumerate(evidence_items)
    )
    parsed_numeric_value = payload.get("parsed_numeric_value")
    if parsed_numeric_value is not None:
        try:
            payload["parsed_numeric_value"] = Decimal(str(parsed_numeric_value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"{label} parsed_numeric_value is invalid") from exc
    record = SourceInventoryRecord(
        **payload,
        source_evidence=evidence,
    )
    record.validate()
    return record
```

- [ ] **Step 4: Run JSONL validation tests**

Run:

```bash
uv run pytest tests/test_source_artifacts.py::test_read_source_inventory_rejects_non_object_line_with_line_number tests/test_source_artifacts.py::test_read_source_inventory_rejects_non_list_source_evidence -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```bash
git add src/financial_report_llm_extractor/structured_sources/artifacts.py tests/test_source_artifacts.py
git commit -m "fix: harden source inventory reader"
```

## Task 4: Replay Validate Inventory Evidence Against Artifacts

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/artifacts.py`
- Modify: `tests/test_source_artifacts.py`

- [ ] **Step 1: Write failing replay validation tests**

Extend the existing `financial_report_llm_extractor.structured_sources.artifacts` import with:

```python
    validate_source_inventory_artifacts,
```

Add:

```python
def test_validate_source_inventory_artifacts_accepts_matching_manifest(
    tmp_path: Path,
) -> None:
    store = SourceArtifactStore(tmp_path)
    artifact = store.write_json(
        source="akshare",
        artifact_id="akshare_hk_00001_balance_sheet",
        payload={"rows": [{"field": "Total assets", "value": 100}]},
    )
    manifest = write_source_artifact_manifest(
        tmp_path / "source_artifact_manifest.json",
        artifact_root=tmp_path,
        artifacts=(artifact,),
    )
    evidence = SourceEvidence(
        source="akshare",
        adapter="akshare",
        function="stock_financial_hk_report_em",
        artifact_id=artifact.artifact_id,
        raw_record_id="00001:balance_sheet:2024",
        raw_field_name="Total assets",
    )
    record = SourceInventoryRecord(
        source="akshare",
        market="HK",
        ticker="00001",
        statement_type="balance_sheet",
        period="2024-12-31",
        raw_field_name="Total assets",
        raw_value="100",
        parsed_numeric_value=Decimal("100"),
        currency="HKD",
        unit="HKD",
        source_evidence=(evidence,),
    )

    validate_source_inventory_artifacts(manifest, (record,), tmp_path)


def test_validate_source_inventory_artifacts_rejects_missing_artifact_id(
    tmp_path: Path,
) -> None:
    manifest = write_source_artifact_manifest(
        tmp_path / "source_artifact_manifest.json",
        artifact_root=tmp_path,
        artifacts=(),
    )
    evidence = SourceEvidence(
        source="akshare",
        adapter="akshare",
        function="stock_financial_hk_report_em",
        artifact_id="missing_artifact",
        raw_record_id="00001:balance_sheet:2024",
        raw_field_name="Total assets",
    )
    record = SourceInventoryRecord(
        source="akshare",
        market="HK",
        ticker="00001",
        statement_type="balance_sheet",
        period="2024-12-31",
        raw_field_name="Total assets",
        raw_value="100",
        parsed_numeric_value=Decimal("100"),
        currency="HKD",
        unit="HKD",
        source_evidence=(evidence,),
    )

    with pytest.raises(ValueError, match="missing_artifact"):
        validate_source_inventory_artifacts(manifest, (record,), tmp_path)
```

- [ ] **Step 2: Run failing replay tests**

Run:

```bash
uv run pytest tests/test_source_artifacts.py::test_validate_source_inventory_artifacts_accepts_matching_manifest tests/test_source_artifacts.py::test_validate_source_inventory_artifacts_rejects_missing_artifact_id -v
```

Expected: FAIL because replay validation is not defined.

- [ ] **Step 3: Implement replay validation**

Add:

```python
def validate_source_inventory_artifacts(
    manifest: SourceArtifactManifest,
    records: Iterable[SourceInventoryRecord],
    artifact_root: Path,
) -> None:
    manifest.validate()
    entries = {entry.artifact_id: entry for entry in manifest.artifacts}
    for record in records:
        record.validate()
        for evidence in record.source_evidence:
            entry = entries.get(evidence.artifact_id)
            if entry is None:
                raise ValueError(f"source evidence references missing artifact_id: {evidence.artifact_id}")
            full_path = artifact_root / entry.path
            if not full_path.exists():
                raise ValueError(f"source artifact file is missing: {evidence.artifact_id}")
            actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
            if actual_hash != entry.sha256:
                raise ValueError(f"source artifact hash mismatch: {evidence.artifact_id}")
```

- [ ] **Step 4: Run replay validation tests**

Run:

```bash
uv run pytest tests/test_source_artifacts.py::test_validate_source_inventory_artifacts_accepts_matching_manifest tests/test_source_artifacts.py::test_validate_source_inventory_artifacts_rejects_missing_artifact_id -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

Run:

```bash
git add src/financial_report_llm_extractor/structured_sources/artifacts.py tests/test_source_artifacts.py
git commit -m "feat: validate source evidence artifacts"
```

## Task 5: Roadmap And Verification

**Files:**
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`

- [ ] **Step 1: Update roadmap Phase B note**

In the Phase B section, add:

```markdown
Implementation note:

- Phase B baseline artifact store exists in `structured_sources/artifacts.py`.
- PB2 hardening adds `source_artifact_manifest.json`, stable malformed JSONL errors, and replay validation from `SourceEvidence.artifact_id` to raw artifact files.
- This phase remains fixture-only; Phase C/D adapters may consume it without changing the storage contract.
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
uv run pytest tests/test_source_artifacts.py tests/test_structured_source_models.py tests/test_source_mapping_catalog.py tests/test_source_coverage.py -v
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

- [ ] **Step 4: Commit roadmap and verification updates**

Run:

```bash
git add docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md
git commit -m "docs: update phase b hardening roadmap"
```

## Self-Review

- Spec coverage: Task 1 covers manifest roundtrip and hashes; Task 2 covers manifest shape and duplicate IDs; Task 3 covers source inventory JSONL stable errors; Task 4 covers replay validation; Task 5 covers roadmap and verification.
- Placeholder scan: no task uses placeholder wording; each code-writing step includes concrete code or exact markdown.
- Type consistency: the plan consistently uses `SourceArtifactManifest`, `SourceArtifactManifestEntry`, `write_source_artifact_manifest()`, `read_source_artifact_manifest()`, and `validate_source_inventory_artifacts()`.
