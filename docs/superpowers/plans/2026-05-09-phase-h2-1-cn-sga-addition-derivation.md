# Phase H2.1 Implementation Plan — CN SGA Addition Derivation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Extend catalog `derivation` syntax to support `+` operator + `provider:RAW_FIELD_NAME` operands so CN `selling_general_administrative` can derive from `akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE`. Promotion gate sticks to H2 standard: derivation value = PDF SGA EXACT.

**Architecture:** Tight extension of `mapping._derive_field` (currently `mapping.py:247-321` accepting only `Turtle - Turtle` form). Add `+` operator branch + `provider:` prefix operand resolver that looks up raw values from `SourceInventoryRecord` directly. Catalog SGA gets `derivation` string. PDF spot-check decides whether to add `provider_semantics_sample_verified` rule (promote) or document the gap (terminal continues).

**Tech Stack:** Python 3.11 stdlib, frozen dataclasses, existing `_derive_field` + `_compatibility_error` infrastructure, pytest.

**Spec:** `docs/superpowers/specs/2026-05-09-phase-h2-1-cn-sga-addition-derivation.md`

---

## Task 1: derivation `+` operator support (Turtle field operands)

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/mapping.py`
- Modify: `tests/test_source_mapping.py`

### Step 1: write failing test

Append to `tests/test_source_mapping.py`:

```python
def test_derive_supports_addition_operator() -> None:
    """Phase H2.1: derivation should accept `A + B` (currently only `A - B`)."""
    from decimal import Decimal
    from financial_report_llm_extractor.structured_sources.mapping import (
        map_source_inventory,
    )

    catalog = _build_test_catalog_with_addition()  # NEW helper below
    records = _build_test_records_for_addition()

    result = map_source_inventory(catalog, records)

    sga = result.fields["selling_general_administrative"]
    assert sga.status == "derived"
    # MANAGE_EXPENSE 100 + SALE_EXPENSE 50 = 150 (Turtle field operands form)
    assert sga.value == Decimal("150")
```

Where `_build_test_catalog_with_addition()` is a helper constructing a minimal catalog where `selling_general_administrative.derivation = "manage_expense + sale_expense"` AND two intermediate Turtle field entries `manage_expense` / `sale_expense` (this commit only proves `+` parsing works on Turtle operands; provider:raw form lands in Task 2).

If introducing intermediate fields is too invasive for a unit test, alternative simpler test approach: directly call `_derive_field` with constructed `mapped` dict containing `manage_expense` and `sale_expense` MappedTurtleField objects. (This is preferred — it isolates parser change from catalog schema changes.)

### Step 2: confirm RED

`uv run pytest tests/test_source_mapping.py -v -k addition_operator` → fails (`unsupported derivation` because `parts[1] != "-"`).

### Step 3: implement

In `mapping.py:_derive_field` (line 247):

```python
def _derive_field(...) -> MappedTurtleField:
    ...
    parts = entry.derivation.split()
    if len(parts) != 3 or parts[1] not in {"-", "+"}:  # CHANGED
        return MappedTurtleField(status="blocked", errors=(f"unsupported derivation: {entry.derivation}",))

    op = parts[1]  # NEW: capture operator
    ...
    # In the value compute block (lines 291-307), replace `left.value - right.value`
    # with a generic op:
    sign = 1 if op == "+" else -1
    if left.unit == right.unit:
        value = left.value + sign * right.value
        normalized_value = (
            left.normalized_value + sign * right.normalized_value
            if left.normalized_value is not None and right.normalized_value is not None
            else None
        )
        ...
    else:
        ...
        value = left.normalized_value + sign * right.normalized_value
        ...
```

### Step 4: GREEN + full validation

`uv run pytest -q && uv run ruff check . && uv run mypy src tests` — all green.

### Step 5: commit

```bash
git add src/financial_report_llm_extractor/structured_sources/mapping.py tests/test_source_mapping.py
git commit -m "feat: phase h2.1 - derivation supports + operator (turtle operands)

Extend _derive_field parser to accept 'A + B' in addition to existing
'A - B'. Operator is captured and applied via signed arithmetic; all
existing subtraction tests continue to pass (Phase H1 inventories
derivation, etc.).

Task 2 will extend operand syntax to accept provider:RAW form, allowing
CN SGA's MANAGE_EXPENSE + SALE_EXPENSE addition derivation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: derivation operand `provider:RAW` support + records injection

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/mapping.py`
- Modify: `tests/test_source_mapping.py`

### Step 1: write failing tests (4 cases)

Append to `tests/test_source_mapping.py`:

```python
def test_derive_with_provider_raw_operands_sums_correctly() -> None:
    """Phase H2.1: derivation operands like 'akshare:MANAGE_EXPENSE' look up
    raw values directly from source records, bypassing mapped Turtle fields."""
    from decimal import Decimal
    from financial_report_llm_extractor.structured_sources.mapping import (
        map_source_inventory,
    )

    # Catalog: SGA with derivation = "akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE"
    catalog = _build_catalog_with_provider_raw_derivation(
        "selling_general_administrative",
        "akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE",
    )
    records = (
        _build_record(source="akshare", raw_field_name="MANAGE_EXPENSE",
                      value=Decimal("9315650060.38"), period="2024-12-31"),
        _build_record(source="akshare", raw_field_name="SALE_EXPENSE",
                      value=Decimal("7252900000.00"), period="2024-12-31"),
    )

    result = map_source_inventory(catalog, records)

    sga = result.fields["selling_general_administrative"]
    assert sga.status == "derived"
    assert sga.value == Decimal("16568550060.38")  # 9.32B + 7.25B


def test_derive_provider_raw_blocks_when_one_raw_field_missing() -> None:
    """If a provider:RAW operand isn't present in records → blocked + clear reason."""
    catalog = _build_catalog_with_provider_raw_derivation(
        "selling_general_administrative",
        "akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE",
    )
    records = (
        _build_record(source="akshare", raw_field_name="MANAGE_EXPENSE",
                      value=Decimal("100"), period="2024-12-31"),
        # SALE_EXPENSE missing
    )

    result = map_source_inventory(catalog, records)

    sga = result.fields["selling_general_administrative"]
    assert sga.status == "blocked"
    assert any("SALE_EXPENSE" in err for err in sga.errors)


def test_derive_rejects_cross_provider_addition() -> None:
    """`akshare:X + yahoo:Y` is invalid — both operands must be same provider."""
    catalog = _build_catalog_with_provider_raw_derivation(
        "selling_general_administrative",
        "akshare:MANAGE_EXPENSE + yahoo:SALE_EXPENSE",
    )
    records = (
        _build_record(source="akshare", raw_field_name="MANAGE_EXPENSE",
                      value=Decimal("100"), period="2024-12-31"),
        _build_record(source="yahoo", raw_field_name="SALE_EXPENSE",
                      value=Decimal("50"), period="2024-12-31"),
    )

    result = map_source_inventory(catalog, records)

    sga = result.fields["selling_general_administrative"]
    assert sga.status == "blocked"
    assert any("cross-provider" in err.lower() or "different providers" in err.lower()
               for err in sga.errors)


def test_derive_provider_raw_inherits_currency_unit_from_records() -> None:
    """Derived field inherits currency/unit from raw records (for downstream
    reconciliation + sign_normalize compatibility)."""
    catalog = _build_catalog_with_provider_raw_derivation(
        "selling_general_administrative",
        "akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE",
    )
    records = (
        _build_record(source="akshare", raw_field_name="MANAGE_EXPENSE",
                      value=Decimal("100"), currency="CNY", unit="yuan",
                      period="2024-12-31"),
        _build_record(source="akshare", raw_field_name="SALE_EXPENSE",
                      value=Decimal("50"), currency="CNY", unit="yuan",
                      period="2024-12-31"),
    )

    result = map_source_inventory(catalog, records)
    sga = result.fields["selling_general_administrative"]
    assert sga.status == "derived"
    assert sga.currency == "CNY"
    assert sga.unit == "yuan"
```

Helper `_build_catalog_with_provider_raw_derivation` constructs a minimal `SourceMappingCatalog` where the named field has the given derivation string. Re-use existing fixture-building helpers in test_source_mapping.py if present; otherwise add minimal one.

`_build_record` helper constructs a `SourceInventoryRecord` minimal stub. Adapt from `_build_record` in `tests/test_source_inventory_fetch.py`.

### Step 2: confirm RED

`uv run pytest tests/test_source_mapping.py -v -k provider_raw` → 4 fails (operand parsing doesn't recognize `provider:` prefix).

### Step 3: implement

In `mapping.py`:

1. Update `map_source_inventory` to pass `records` to `_derive_field`:

```python
def map_source_inventory(catalog, records) -> TurtleMappingResult:
    catalog.validate()
    mapped: dict[str, MappedTurtleField] = {}
    for field_id, entry in catalog.entries.items():
        mapped[field_id] = _map_direct_field(entry, records)

    for field_id, entry in catalog.entries.items():
        if not entry.derivation or mapped[field_id].status != "missing":
            continue
        mapped[field_id] = _derive_field(entry, mapped, records)  # CHANGED: + records

    return TurtleMappingResult(...)
```

2. Update `_derive_field` signature + add operand resolver:

```python
def _derive_field(
    entry: SourceMappingEntry,
    mapped: dict[str, MappedTurtleField],
    records: tuple[SourceInventoryRecord, ...] | list[SourceInventoryRecord] = (),
) -> MappedTurtleField:
    assert entry.derivation is not None
    parts = entry.derivation.split()
    if len(parts) != 3 or parts[1] not in {"-", "+"}:
        return MappedTurtleField(
            field_id=entry.field_id,
            status="blocked",
            errors=(f"unsupported derivation: {entry.derivation}",),
        )

    op = parts[1]

    # Resolve operands: prefer Turtle field lookup; fall back to provider:raw
    left, left_err = _resolve_derivation_operand(parts[0], mapped, records)
    right, right_err = _resolve_derivation_operand(parts[2], mapped, records)
    if left_err or right_err:
        return MappedTurtleField(
            field_id=entry.field_id,
            status="blocked",
            errors=tuple(e for e in (left_err, right_err) if e),
        )

    # Cross-provider check: if both operands are provider:raw form, providers must match
    if (parts[0].startswith("akshare:") or parts[0].startswith("yahoo:")) and \
       (parts[2].startswith("akshare:") or parts[2].startswith("yahoo:")):
        left_provider = parts[0].split(":")[0]
        right_provider = parts[2].split(":")[0]
        if left_provider != right_provider:
            return MappedTurtleField(
                field_id=entry.field_id,
                status="blocked",
                errors=(f"derivation operands use different providers: {entry.derivation}",),
            )

    # Existing compatibility + value compute path (unchanged after Task 1's `op` capture).
    ...


def _resolve_derivation_operand(
    operand: str,
    mapped: dict[str, MappedTurtleField],
    records: tuple[SourceInventoryRecord, ...] | list[SourceInventoryRecord],
) -> tuple[MappedTurtleField | None, str | None]:
    """Return (mapped-field-or-virtual, error-or-None). `provider:RAW` form looks
    up raw value from records; bare names look up mapped Turtle dict."""
    if ":" not in operand:
        # Existing path: Turtle field ID lookup
        m = mapped.get(operand)
        if m is None:
            return None, f"derivation input missing from catalog: {operand}"
        return m, None

    # provider:RAW form
    provider, raw_field_name = operand.split(":", 1)
    matches = [
        r for r in records
        if r.source == provider
        and r.raw_field_name == raw_field_name
        and r.source_status == "present"
    ]
    if not matches:
        return None, f"derivation input not present: {operand}"
    if len(matches) > 1:
        return None, f"derivation input has multiple records: {operand}"

    rec = matches[0]
    # Wrap as virtual MappedTurtleField for downstream compat
    from financial_report_llm_extractor.structured_sources.models import SourceEvidence
    virtual = MappedTurtleField(
        field_id=operand,  # virtual ID for trace
        status="present",
        value=rec.parsed_numeric_value,
        normalized_value=rec.parsed_numeric_value,
        currency=rec.currency,
        unit=rec.unit,
        canonical_unit=rec.currency,  # raw record's currency = its canonical unit
        period=rec.period,
        scope=rec.scope,
        source_evidence=rec.source_evidence,
    )
    return virtual, None
```

Note: the cross-provider check above is one approach. Adapt error message to match the test's `match` pattern.

### Step 4: GREEN + full validation

`uv run pytest tests/test_source_mapping.py -v -k provider_raw` → 4 passed.
`uv run pytest -q && uv run ruff check . && uv run mypy src tests` — all green.

### Step 5: commit

```bash
git add src/financial_report_llm_extractor/structured_sources/mapping.py tests/test_source_mapping.py
git commit -m "feat: phase h2.1 - derivation operands support provider:RAW form

Extend _derive_field operand resolver to recognize 'provider:raw_field_name'
syntax (e.g. 'akshare:MANAGE_EXPENSE'). Such operands resolve directly from
source inventory records, bypassing mapped Turtle field lookup.

Cross-provider sums (e.g. akshare:X + yahoo:Y) are rejected to avoid
semantic confusion. Mixed forms (Turtle + provider:raw) are allowed.

map_source_inventory now passes records to _derive_field for the
provider:raw lookup path.

4 new tests: provider_raw_sums_correctly, blocks_when_missing,
rejects_cross_provider, inherits_currency_unit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: PDF spot-check 600519 SGA + decision

**Files:**
- Create: `docs/phase_h2_1_sga_spot_check.md`

### Step 1: spot-check

```bash
pdftotext -layout downloads/cn_stocks/600519/annual/2024_年度报告.pdf - | grep -E "销售费用|管理费用" | head -20
```

Expected: PDF lists 销售费用 and 管理费用 separately with numbers. Compare:
- AKShare MANAGE_EXPENSE: 9,315,650,060.38
- AKShare SALE_EXPENSE (look up in fixture for 600519/2024)
- AKShare derivation = MANAGE + SALE
- PDF formal SGA (if reported as a single line) OR PDF (MANAGE + SALE) total

### Step 2: write decision doc

Create `docs/phase_h2_1_sga_spot_check.md`:

```markdown
# Phase H2.1: 600519/2024 SGA PDF Spot-Check

> Date: YYYY-MM-DD

## PDF values

- 销售费用: [extract value from PDF]
- 管理费用: [extract value from PDF]
- Sum: [computed]

## AKShare values (from fixture)

- MANAGE_EXPENSE: 9,315,650,060.38
- SALE_EXPENSE: [extract from fixture]
- Sum: [computed]

## Yahoo SGA

- Selling General And Administration: 10,362,839,420.99

## Decision

[ ] Promote: AKShare MANAGE+SALE = PDF (销售费用+管理费用) EXACT match → add provider_semantics_sample_verified rule + promote derivation
[ ] Terminal: AKShare MANAGE+SALE diverges from PDF → keep terminal_unverified, document reason

[Filled-in result + reasoning]
```

### Step 3: commit

```bash
git add docs/phase_h2_1_sga_spot_check.md
git commit -m "docs: phase h2.1 - 600519 SGA PDF spot-check + decision

Verify whether AKShare MANAGE_EXPENSE + SALE_EXPENSE matches PDF SGA
formal value EXACTLY (per H2 promotion gate; no tolerance). Decision
recorded; informs Task 4 catalog edit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: apply CN SGA derivation OR document terminal continuation

**Files:**
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`
- Modify: `field_catalog/provider_raw_semantics_cn.json`
- Modify: `tests/test_phase_h2_validation.py`

### Branch A: PROMOTE (PDF EXACT match in Task 3)

#### Step 1: edit catalog

In `selling_general_administrative` entry, add:

```jsonc
"derivation": "akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE"
```

In `source_policy.market_policies.CN`, set:
- `"on_conflict": "select_primary_require_pdf"` (was preserve_conflict per H2)

#### Step 2: update provider_raw_semantics_cn.json

Replace SGA's `provider_semantics_unverified` rule (added in H2 Task 4) with two `provider_semantics_sample_verified` rules — one for MANAGE_EXPENSE, one for SALE_EXPENSE — both pointing at `selling_general_administrative` Turtle field. Or add a single composite rule with `raw_field_name="MANAGE_EXPENSE+SALE_EXPENSE"` (composite key form). The composite form is simpler:

```jsonc
{
  "provider": "akshare",
  "market": "CN",
  "raw_field_name": "MANAGE_EXPENSE+SALE_EXPENSE",
  "raw_field_code": null,
  "turtle_field_id": "selling_general_administrative",
  "semantic_claim": "Full SGA = AKShare MANAGE_EXPENSE (管理费用) + SALE_EXPENSE (销售费用) per CN P&L convention. Single addition derivation matches PDF SGA EXACTLY for 600519/2024.",
  "classification": "provider_semantics_sample_verified",
  "trusted_currency": "CNY",
  "trusted_unit": "yuan",
  "trusted_unit_multiplier": 1,
  "allowed_as_primary": true,
  ...
  "samples": [
    {"company_id": "600519", "period_end": "2024-12-31",
     "pdf_value": "[exact PDF value]",
     "matches_raw_value": true, ...}
  ]
}
```

NB: this composite raw_field_name won't match the single-record derivation result either (since the derived field is virtual). The `_apply_provider_semantics_promotion` in source_policy.py looks up by `(provider, market, turtle_field_id, raw_field_name)`. If derivation produces a candidate with `raw_field_name="MANAGE_EXPENSE+SALE_EXPENSE"` (or similar), the rule matches. **Verify this assumption** during implementation: the derived MappedTurtleField's source_evidence/raw_field_name needs to align with the rule lookup key. Adjust in the implementation as needed (may require setting a synthetic raw_field_name in `_derive_field` output).

#### Step 3: update test_phase_h2_validation.py

Update `test_phase_h2_sga_and_da_have_unverified_rules` to expect ONLY D&A as unverified for SGA — SGA now sample-verified. Or add a new test asserting SGA on CN is sample_verified. Refactor as needed.

#### Step 4: full validation + live re-run

```bash
uv run pytest -q && uv run ruff check . && uv run mypy src tests
# Live re-run on 600519/2024
rm -f tmp/runs/600519_2024-12-31/{evaluation.json,evaluation.md,extraction_result.json,reconciliation_report.json,turtle_mapping.json,source_policy_report.json,review_summary.json,source_coverage_summary.*,warning_classification.*}
uv run python -c "
from financial_report_llm_extractor.cli import main
main(['evaluate-company', '--company', '600519', '--year', '2024', '--market', 'CN',
      '--inventory', 'tmp/runs/600519_2024-12-31/source_inventory.jsonl',
      '--catalog', 'field_catalog/turtle_v015_source_mapping_minimal.json',
      '--taxonomy', 'field_catalog/turtle_v015_field_taxonomy.json',
      '--priorities', 'P0,P1,P2,P3', '--out', 'tmp/runs/600519_2024-12-31'])
"
grep -E "^\| selling_general_administrative \|" tmp/runs/600519_2024-12-31/evaluation.md
```

Expected: SGA → clean_present | akshare | [derived value].

### Branch B: TERMINAL CONTINUATION (PDF doesn't match)

Document why in updated `provider_semantics_unverified` rule semantic_claim. Catalog can still gain the `derivation` field (mechanism is in place) but the rule keeps `allowed_as_primary: false`. test_phase_h2_validation continues to assert unverified for SGA.

### Step 5: commit

Branch A:
```bash
git commit -m "feat: phase h2.1 - promote CN SGA via akshare derivation

PDF spot-check (docs/phase_h2_1_sga_spot_check.md) confirmed AKShare
MANAGE_EXPENSE + SALE_EXPENSE = PDF SGA EXACT for 600519/2024.

catalog: derivation = 'akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE'.
provider_raw_semantics_cn.json: provider_semantics_sample_verified rule
added (composite raw_field_name).

Live re-run: 600519/2024 SGA moves from unresolved_conflict to
clean_present. Test expectation updated.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

Branch B:
```bash
git commit -m "docs: phase h2.1 - SGA derivation mechanism in place; sample not verified

PDF spot-check (docs/phase_h2_1_sga_spot_check.md) found AKShare
MANAGE_EXPENSE + SALE_EXPENSE diverges from PDF SGA by [N%], so the
existing provider_semantics_unverified rule remains in force. Catalog
gains the derivation field as infrastructure for future markets/companies
where the sum may match.

SGA stays terminal_unverified for CN.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: validation report + roadmap update

**Files:**
- Create: `docs/phase_h2_1_validation_report.md`
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
- Modify: `CLAUDE.md`

### Step 1: capture before/after

Before: `tmp/runs/h2_after/600519.json` (post-H2 baseline).
After: re-run `tmp/runs/600519_2024-12-31/evaluation.json` (post-H2.1).

### Step 2: write report

Create `docs/phase_h2_1_validation_report.md` with:
- 600519/2024 before/after bucket counts (whether +1 clean or unchanged depending on Branch)
- Per-field migration table (just SGA)
- Decision rationale (link to spot-check doc)
- Phase H2.2 candidate notes if multi-company sample expansion warranted

### Step 3: roadmap + CLAUDE.md

Append "Phase H2.1 Implementation Result" section to roadmap (after Phase H2 section).

CLAUDE.md: phase table H2.1 row + 下一步 pointer update.

### Step 4: commit

```bash
git add docs/phase_h2_1_validation_report.md docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md CLAUDE.md
git commit -m "docs: phase h2.1 implementation result + validation report

[Branch A: 600519/2024 SGA promoted clean_present; CN clean 38→39]
[OR Branch B: derivation infrastructure landed; SGA stays terminal_unverified]

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Acceptance Criteria

- 5 commits, each independently green (pytest + ruff + mypy)
- ≥ 5 new unit tests (1 in Task 1, 4 in Task 2)
- 600519/2024 SGA row has either `clean_present | akshare | [value]` (Branch A) OR `unresolved_conflict | | [candidate values] | normalized_value_conflict` (Branch B unchanged from H2)
- Existing H2 4 promotions unchanged (test_phase_h2_validation continues to enforce)
- Catalog `derivation` parser supports both `+` and `-` operators with operand validation
- Report documents the spot-check decision + acknowledges single-sample limitation (Phase H2.2 candidate)
