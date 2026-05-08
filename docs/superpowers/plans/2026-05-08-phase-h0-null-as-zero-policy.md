# Phase H0: Null-as-Zero Source Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `null_means_zero` source mapping policy so AKShare's null values for known-zero fields (Maotai's debt fields) promote to clean_present value 0.

**Architecture:** Schema extension in `SourceMappingEntry` + null detection in `_candidate_from_record` + JSON catalog update for 3 fields. Pure deterministic logic; no LLM/PDF involvement.

**Tech Stack:** Python 3.11, frozen dataclass, JSON catalog, pytest.

---

### Task 1: Schema extension and loader

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/catalog.py`
- Test: `tests/test_source_mapping_catalog.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_source_mapping_catalog.py`:

```python
def test_source_mapping_entry_supports_null_means_zero(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps({
            "catalog_id": "test",
            "version": "1",
            "priorities": [{"priority": "P0", "fields": ["fld"]}],
            "source_mappings": {
                "fld": {
                    "value_type": "money",
                    "statement_type": "balance_sheet",
                    "source_aliases": {"akshare": ["FLD"]},
                    "null_means_zero": True,
                }
            },
        }),
        encoding="utf-8",
    )
    catalog = load_source_mapping_catalog(catalog_path, priorities=("P0",))
    entry = catalog.entries["fld"]
    assert entry.null_means_zero is True


def test_source_mapping_entry_null_means_zero_defaults_to_false(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps({
            "catalog_id": "test",
            "version": "1",
            "priorities": [{"priority": "P0", "fields": ["fld"]}],
            "source_mappings": {
                "fld": {
                    "value_type": "money",
                    "statement_type": "balance_sheet",
                    "source_aliases": {"akshare": ["FLD"]},
                }
            },
        }),
        encoding="utf-8",
    )
    catalog = load_source_mapping_catalog(catalog_path, priorities=("P0",))
    assert catalog.entries["fld"].null_means_zero is False
```

- [ ] **Step 2: Run tests, confirm FAIL**

```bash
uv run pytest tests/test_source_mapping_catalog.py::test_source_mapping_entry_supports_null_means_zero -v
```
Expected: FAIL — `null_means_zero` is not a SourceMappingEntry attribute.

- [ ] **Step 3: Add field to SourceMappingEntry**

In `catalog.py`, find `class SourceMappingEntry:` and add:

```python
null_means_zero: bool = False
```

After `source_policy: SourcePolicy | None = None`.

- [ ] **Step 4: Update loader**

In `load_source_mapping_catalog`, find the `entry = SourceMappingEntry(...)` construction. Add:

```python
null_means_zero=bool(mapping.get("null_means_zero", False)),
```

After `source_policy=_parse_source_policy(...)`.

- [ ] **Step 5: Run tests, confirm PASS**

```bash
uv run pytest tests/test_source_mapping_catalog.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ tests/test_source_mapping_catalog.py
git commit -m "feat: add null_means_zero field to SourceMappingEntry"
```

---

### Task 2: Apply null-as-zero in candidate construction

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/mapping.py`
- Test: `tests/test_source_mapping.py` (or `tests/test_mapping.py` if exists)

- [ ] **Step 1: Write failing test**

Find the existing mapping test file (e.g., `tests/test_source_mapping.py`). Add:

```python
def test_null_record_with_null_means_zero_produces_zero_candidate() -> None:
    record = SourceInventoryRecord(
        source="akshare",
        ticker="600519",
        market="CN",
        statement_type="balance_sheet",
        period="2025-12-31",
        scope="unknown",
        raw_field_name="SHORT_LOAN",
        raw_field_code="SHORT_LOAN",
        raw_value=None,
        parsed_numeric_value=None,
        currency="CNY",
        unit="yuan",
        value_type="money",
        report_type="annual",
        account_standard=None,
        fiscal_year=None,
        source_status="present",
        source_evidence=(
            SourceEvidence(
                source="akshare",
                adapter="akshare",
                function="stock_balance_sheet_by_report_em",
                artifact_id="akshare_cn_600519_balance_sheet",
                raw_record_id="600519:CN:balance_sheet:2025-12-31:SHORT_LOAN",
                provider_version=None,
                retrieved_at=None,
                raw_field_name="SHORT_LOAN",
                raw_field_code="SHORT_LOAN",
            ),
        ),
    )
    entry = SourceMappingEntry(
        field_id="st_borr",
        priority="P0",
        value_type="money",
        statement_type="balance_sheet",
        currency_requirement="required",
        unit_requirement="required",
        source_aliases={"akshare": ("SHORT_LOAN",)},
        null_means_zero=True,
    )
    candidate = _candidate_from_record(record, entry)
    assert candidate.errors == ()
    assert candidate.value == Decimal("0")
    assert candidate.normalized_value == Decimal("0")
    assert candidate.currency == "CNY"
    assert candidate.unit == "yuan"


def test_null_record_without_null_means_zero_is_blocked() -> None:
    record = SourceInventoryRecord(
        # ... same as above
    )
    entry = SourceMappingEntry(
        field_id="st_borr",
        priority="P0",
        value_type="money",
        statement_type="balance_sheet",
        currency_requirement="required",
        unit_requirement="required",
        source_aliases={"akshare": ("SHORT_LOAN",)},
        null_means_zero=False,
    )
    candidate = _candidate_from_record(record, entry)
    assert candidate.errors != ()
```

If `_candidate_from_record` is private (underscore-prefixed), import it from the module. If the test pattern in the existing file uses public APIs only, write a higher-level test that goes through `_map_direct_field` instead.

- [ ] **Step 2: Run test, confirm FAIL**

- [ ] **Step 3: Modify `_candidate_from_record`**

In `src/financial_report_llm_extractor/structured_sources/mapping.py`, change the signature from:

```python
def _candidate_from_record(record: SourceInventoryRecord) -> TurtleMappingCandidate:
```

to:

```python
def _candidate_from_record(
    record: SourceInventoryRecord,
    entry: SourceMappingEntry,
) -> TurtleMappingCandidate:
```

Inside the function, BEFORE the existing try/except block, add:

```python
if (
    entry.null_means_zero
    and record.source_status == "present"
    and record.parsed_numeric_value is None
    and (record.raw_value is None or str(record.raw_value).strip().lower() in ("", "none", "null"))
):
    try:
        record.validate()
        return TurtleMappingCandidate(
            source=record.source,
            raw_field_name=record.raw_field_name,
            raw_field_code=record.raw_field_code,
            raw_value=record.raw_value,
            value=Decimal("0"),
            normalized_value=Decimal("0"),
            currency=record.currency,
            unit=record.unit,
            period=record.period,
            scope=record.scope,
            source_evidence=record.source_evidence,
            canonical_unit=record.currency if record.currency != "unknown" else None,
            errors=(),
            statement_metadata_proven=_statement_metadata_proven(record),
            unit_multiplier=Decimal("1"),
            currency_proof_source=_currency_proof_source(record),
            unit_proof_source=_unit_proof_source(record),
            reporting_metadata_proof_source=_reporting_metadata_proof_source(record),
            review_notes=("null_interpreted_as_zero",),
        )
    except ValueError as exc:
        # Record is structurally invalid; fall through to normal error path
        pass
```

If `TurtleMappingCandidate` doesn't currently have a `review_notes` field, check the dataclass and add it (or use an existing notes/warnings mechanism). Look at how candidates currently flag review notes — there may be a `notes` or `review_notes` field already.

- [ ] **Step 4: Update caller**

In `_map_direct_field`, change:

```python
matched_candidates = tuple(
    _candidate_from_record(record)
    for record in records
    if _record_matches_entry(record, entry)
)
```

to:

```python
matched_candidates = tuple(
    _candidate_from_record(record, entry)
    for record in records
    if _record_matches_entry(record, entry)
)
```

Search the entire `mapping.py` for any other `_candidate_from_record(` callsite and update similarly.

- [ ] **Step 5: Run test, confirm PASS**

```bash
uv run pytest tests/test_source_mapping.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/mapping.py tests/
git commit -m "feat: apply null_means_zero policy in candidate construction"
```

---

### Task 3: Propagate review note to export item

**Files:**
- Possibly modify: mapping data classes if `review_notes` doesn't exist on candidate
- Verify: review note flows through to `SourceFirstExportItem.review_notes`

- [ ] **Step 1: Inspect data flow**

Run:
```bash
grep -rn "review_notes" src/financial_report_llm_extractor/structured_sources/
```

Identify whether `TurtleMappingCandidate` has a `review_notes` field and whether `_map_direct_field` propagates it to `MappedTurtleField`, and from there to `SourceFirstExportItem`.

- [ ] **Step 2: Add propagation if missing**

If review_notes is not propagated for present items:
- Add `review_notes` field to `MappedTurtleField` dataclass (if missing)
- In `_map_direct_field`'s present-status return, copy `candidate.review_notes` to the result
- In the export step, copy `MappedTurtleField.review_notes` to `SourceFirstExportItem.review_notes`

If already propagated, this task is a no-op.

- [ ] **Step 3: Run full pytest, ensure no regression**

```bash
uv run pytest -v
```

- [ ] **Step 4: Commit if changes made**

```bash
git add src/
git commit -m "feat: propagate null_interpreted_as_zero review note to export"
```

---

### Task 4: Update source_mapping JSON for 3 fields

**Files:**
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`

- [ ] **Step 1: Add null_means_zero to 3 entries**

In `field_catalog/turtle_v015_source_mapping_minimal.json`, find each of `bond_payable`, `st_borr`, `lt_borr` and add:

```json
"null_means_zero": true,
```

Add it after the `fallback_policy` field for consistency.

- [ ] **Step 2: Run replay**

```bash
uv run financial-report-llm-extractor replay-provider-baseline \
  --inventory tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz \
  --inventory-summary tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json \
  --catalog field_catalog/turtle_v015_source_mapping_minimal.json \
  --out tmp/runs/h0_verification
```

Verify in `tmp/runs/h0_verification/provider_baseline_period_replay_summary.json`:
- 600519 clean_present_count: 30 (was 27)
- 600519 clean_present_fields includes `bond_payable`, `st_borr`, `lt_borr`
- 00001/01113 unchanged (still 20/33, 21/33)

- [ ] **Step 3: Commit**

```bash
git add field_catalog/turtle_v015_source_mapping_minimal.json
git commit -m "feat: enable null_means_zero for bond_payable st_borr lt_borr"
```

---

### Task 5: Update tests and verify

**Files:**
- Modify: `tests/test_provider_baseline_replay.py`

- [ ] **Step 1: Update 600519 expected coverage**

Find the test that asserts 600519 coverage. The test file uses per-company expected_clean sets. Update 600519's expected_clean to include `bond_payable`, `st_borr`, `lt_borr`, and update the count.

If `EXPECTED_HK_*` constants don't apply to 600519, find the CN-specific assertion (might be in a separate test or in `expected_clean_count_by_company`).

- [ ] **Step 2: Verify warning_classification regression**

The `source_policy_resolvable` bucket for 600519 should no longer contain these 3 fields. Update any assertion that listed them.

- [ ] **Step 3: Run full pytest**

```bash
uv run pytest -v
uv run ruff check .
```

All tests must pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_provider_baseline_replay.py
git commit -m "test: update 600519 coverage assertions for null_means_zero promotion"
```

---

### Task 6: Update roadmap and commit

**Files:**
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`

- [ ] **Step 1: Add Phase H0 result section**

Insert after the "Phase H/I: Concrete Trigger Set" section:

```markdown
### Phase H0 Implementation Result

Status: implemented on 2026-05-08. See:
- `docs/superpowers/specs/2026-05-08-phase-h0-null-as-zero-policy.md`
- `docs/superpowers/plans/2026-05-08-phase-h0-null-as-zero-policy.md`

Goal: Resolve Bucket 1 by adding null_means_zero source mapping policy.

Implementation result:

- Added `null_means_zero: bool` field to `SourceMappingEntry`.
- `_candidate_from_record` produces a zero-valued candidate when policy applies and provider returns null with status=present.
- Candidate emits review note `null_interpreted_as_zero` for audit trail.
- Applied to `bond_payable`, `st_borr`, `lt_borr` in source_mapping catalog.
- 600519 clean present: 27/33 → 30/33.
- 00001/01113 unchanged (no null records for these fields in HK data).

Bucket 1 closed. Next: Bucket 4 (locked terminal taxonomy) → Phase H deterministic PDF verification.
```

- [ ] **Step 2: Commit**

```bash
git add docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md
git commit -m "docs: record phase h0 null_means_zero implementation"
```
