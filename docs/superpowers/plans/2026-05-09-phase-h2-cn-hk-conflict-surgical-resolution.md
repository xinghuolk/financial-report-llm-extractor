# Phase H2 Implementation Plan — CN/HK Conflict Surgical Resolution

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve 7 normalized_value_conflict fields surfaced by Phase EC live run on 600519/2024 — promote where PDF semantics proof allows, terminal_unverified where not. Per drift §177: no silent promotion.

**Architecture:** Module A introduces `sign_normalize: "raw" | "absolute"` market policy + reconciliation abs-comparison branch (closes 2 sign-mirror conflicts). Module B applies H1-style surgical resolution per remaining 5 fields × CN+HK markets — catalog `market_policies` edits + new `provider_raw_semantics_cn.json` (NEW) + HK semantics extension. Module C produces live before/after report on 600519 + 00001 + 01113.

**Tech Stack:** Python 3.11 stdlib, frozen dataclasses, existing reconciliation pipeline, evaluate-company orchestrator (Phase EC), pytest.

**Spec:** `docs/superpowers/specs/2026-05-09-phase-h2-cn-hk-conflict-surgical-resolution.md`

---

## File Structure

| 文件 | 职责 |
|------|------|
| `src/financial_report_llm_extractor/structured_sources/catalog.py` | `MarketSourcePolicy.sign_normalize` 字段 + 解析 |
| `src/financial_report_llm_extractor/structured_sources/reconciliation.py` | `reconcile_mapped_fields(*, sign_normalize_fields)` + abs-比较分支 |
| `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py` | `evaluate_source_first_slice` 构造 sign_normalize_fields 并传入 reconciliation |
| `field_catalog/turtle_v015_source_mapping_minimal.json` | 7 fields × CN/HK market_policies 编辑 |
| `field_catalog/provider_raw_semantics_cn.json` | NEW — CN raw field semantics rules |
| `field_catalog/provider_raw_semantics_hk.json` | 追加 H2 字段 rules |
| `tests/test_source_reconciliation.py` | sign_normalize 单测 + 回归测 |
| `tests/test_catalog_consistency.py` | 加 sign_normalize 字段值校验 |
| `tests/test_provider_baseline_replay.py` | sign_normalize_fields 接线集成测 |
| `tests/test_phase_h2_validation.py` | NEW — Phase H2 字段桶迁移期望测 |
| `docs/phase_h2_validation_report.md` | NEW — Module C 实地验证报告 |
| `docs/roadmap/...roadmap.md` | Phase H2 Implementation Result 段 |

---

## Task 1: Sign normalization 机制

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/catalog.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/reconciliation.py`
- Modify: `tests/test_source_reconciliation.py`

### Step 1: 写 sign_normalize=absolute 的 reconciliation 测

追加到 `tests/test_source_reconciliation.py`：

```python
def test_reconcile_sign_normalize_absolute_treats_mirrored_values_as_match() -> None:
    """Phase H2 Module A: when sign_normalize_fields contains the field,
    reconciliation compares abs() — capital_expenditures akshare:+4.68B vs
    yahoo:-4.68B becomes equivalent, not conflict."""
    result = _result(
        "capital_expenditures",
        _field(
            "capital_expenditures",
            _candidate("akshare", Decimal("4678712053.56")),
            _candidate("yahoo", Decimal("-4678712053.56")),
        ),
    )

    report = reconcile_mapped_fields(
        result, sign_normalize_fields=frozenset({"capital_expenditures"})
    )

    assert report.items["capital_expenditures"].status != "conflict"
    assert report.items["capital_expenditures"].status in {"equivalent", "close"}


def test_reconcile_sign_normalize_default_keeps_mirrored_values_as_conflict() -> None:
    """Regression: default behavior (no sign_normalize_fields) unchanged —
    still flags +X / -X as conflict."""
    result = _result(
        "capital_expenditures",
        _field(
            "capital_expenditures",
            _candidate("akshare", Decimal("4678712053.56")),
            _candidate("yahoo", Decimal("-4678712053.56")),
        ),
    )

    report = reconcile_mapped_fields(result)  # no sign_normalize_fields

    assert report.items["capital_expenditures"].status == "conflict"
```

### Step 2: confirm RED

`uv run pytest tests/test_source_reconciliation.py -v -k sign_normalize` → 2 fail (kwarg not accepted).

### Step 3: extend `MarketSourcePolicy` with `sign_normalize` field

In `catalog.py:54-85`, add the field with default `"raw"`:

```python
@dataclass(frozen=True)
class MarketSourcePolicy:
    primary_route: str
    cross_check_routes: tuple[str, ...] = field(default_factory=tuple)
    on_conflict: str = "preserve_conflict"
    single_source_requires_pdf: bool = False
    sign_normalize: str = "raw"  # NEW: "raw" | "absolute"

    def validate(self) -> None:
        ...  # existing validation
        if self.sign_normalize not in ("raw", "absolute"):
            raise ValueError(
                f"sign_normalize must be 'raw' or 'absolute' (got {self.sign_normalize!r})"
            )
```

In `_load_market_policy` (the function that parses dict → MarketSourcePolicy, ~line 280-300), add:

```python
sign_normalize = value.get("sign_normalize", "raw")
if not isinstance(sign_normalize, str):
    raise ValueError("sign_normalize must be a string")
market_policies[str(market)] = MarketSourcePolicy(
    primary_route=...,
    cross_check_routes=...,
    on_conflict=...,
    single_source_requires_pdf=single_source_requires_pdf,
    sign_normalize=sign_normalize,  # NEW
)
```

### Step 4: extend `reconcile_mapped_fields` to accept `sign_normalize_fields`

In `reconciliation.py`, find the public `reconcile_mapped_fields(...)` signature. Add a keyword-only param:

```python
def reconcile_mapped_fields(
    result: TurtleMappingResult,
    *,
    sign_normalize_fields: frozenset[str] | None = None,
) -> ReconciliationReport:
    ...
```

Thread it through to `_reconcile_field`:

```python
def _reconcile_field(
    field_id: str,
    candidates: tuple[TurtleMappingCandidate, ...],
    *,
    tolerance: Decimal,
    sign_normalize: bool = False,  # NEW
) -> ReconciliationItem:
    ...
    # at the value-comparison stage (around lines 139-148):
    values = [candidate.normalized_value for candidate in candidates]
    if any(value is None for value in values):
        return ...  # blocked
    normalized_values = [value for value in values if value is not None]
    if sign_normalize:
        normalized_values = [abs(v) for v in normalized_values]
    max_difference = max(normalized_values) - min(normalized_values)
    ...
```

In the public function:

```python
sign_normalize_fields = sign_normalize_fields or frozenset()
for field_id, mapped in result.fields.items():
    item = _reconcile_field(
        field_id, mapped.candidates,
        tolerance=tolerance,
        sign_normalize=field_id in sign_normalize_fields,
    )
    items[field_id] = item
```

### Step 5: confirm GREEN

`uv run pytest tests/test_source_reconciliation.py -v -k sign_normalize` → 2 pass.

### Step 6: full validation

`uv run pytest -q && uv run ruff check . && uv run mypy src tests` — all green.

### Step 7: commit

```bash
git add src/financial_report_llm_extractor/structured_sources/catalog.py src/financial_report_llm_extractor/structured_sources/reconciliation.py tests/test_source_reconciliation.py
git commit -m "feat: phase h2 module a - sign_normalize market policy + reconciliation

Adds MarketSourcePolicy.sign_normalize ('raw' | 'absolute') and a
sign_normalize_fields kwarg to reconcile_mapped_fields. When set,
candidate normalized_values are compared via abs() — closing
+X-vs-(-X) sign-mirror false-positives.

Mechanism only; Task 2 applies it to capital_expenditures and
interest_paid_cash for CN+HK.

Two new unit tests:
- test_reconcile_sign_normalize_absolute_treats_mirrored_values_as_match
- test_reconcile_sign_normalize_default_keeps_mirrored_values_as_conflict

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Apply sign_normalize=absolute to capital_expenditures + interest_paid_cash

**Files:**
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`
- Modify: `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`
- Modify: `tests/test_provider_baseline_replay.py`

### Step 1: write integration test

Append to `tests/test_provider_baseline_replay.py`:

```python
def test_evaluate_source_first_slice_passes_sign_normalize_fields_to_reconciliation(
    tmp_path: Path,
) -> None:
    """Phase H2 Module A integration: capital_expenditures with mirrored signs
    must NOT appear as unresolved_conflict after slice."""
    from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
        evaluate_source_first_slice,
    )

    catalog = _load_minimal_catalog()  # use existing helper
    taxonomy = _load_minimal_taxonomy()
    # Construct records with capital_expenditures akshare:+1000 / yahoo:-1000.
    records = _build_records_with_mirrored_capex()  # NEW helper

    out_dir = tmp_path / "slice"
    result = evaluate_source_first_slice(
        out_dir,
        catalog=catalog,
        taxonomy=taxonomy,
        records=records,
        company_id="600519",
        market="CN",
        hk_yahoo_trust_policy=None,
        provider_semantics_catalog=None,
    )

    export = result["export_object"]
    capex = export.items["capital_expenditures"]
    # After Task 2 catalog edits, sign_normalize=absolute fires; capex is
    # no longer in conflict.
    assert "normalized_value_conflict" not in capex.conflict_classifications
```

If `_build_records_with_mirrored_capex` helper doesn't exist, write it inline using the existing `_record(...)` helper pattern in that test file.

### Step 2: confirm RED

`uv run pytest tests/test_provider_baseline_replay.py -v -k sign_normalize_fields` → fails (catalog doesn't yet declare sign_normalize for capital_expenditures, OR slice doesn't pass it through).

### Step 3: edit catalog

In `field_catalog/turtle_v015_source_mapping_minimal.json`, find `"capital_expenditures"` and `"interest_paid_cash"` entries. Each has `source_policy.market_policies.{CN,HK}`. Add `"sign_normalize": "absolute"` to all 4 (capital_expenditures CN+HK, interest_paid_cash CN+HK).

Example for capital_expenditures CN:

```jsonc
"capital_expenditures": {
  ...
  "source_policy": {
    "market_policies": {
      "CN": {
        "primary_route": "akshare_direct",
        "cross_check_routes": ["yahoo_direct"],
        "on_conflict": "select_primary_require_pdf",  // or whatever it currently is
        "single_source_requires_pdf": false,
        "sign_normalize": "absolute"  // NEW
      },
      "HK": {
        ...
        "sign_normalize": "absolute"  // NEW
      }
    }
  }
}
```

If `interest_paid_cash` doesn't yet have a market_policies block, add one:

```jsonc
"interest_paid_cash": {
  ...
  "source_policy": {
    "semantic_concept": "cash paid for interest",
    "semantic_variants": {},
    "market_policies": {
      "CN": {
        "primary_route": "akshare_direct",
        "cross_check_routes": ["yahoo_direct"],
        "on_conflict": "select_primary_require_pdf",
        "single_source_requires_pdf": false,
        "sign_normalize": "absolute"
      },
      "HK": {
        "primary_route": "yahoo_direct",
        "cross_check_routes": ["akshare_direct"],
        "on_conflict": "select_primary_require_pdf",
        "single_source_requires_pdf": false,
        "sign_normalize": "absolute"
      }
    },
    "verification_requirement": "none"
  }
}
```

### Step 4: thread sign_normalize_fields in evaluate_source_first_slice

In `provider_baseline_replay.py:323` (where `reconciliation = reconcile_mapped_fields(mapping)`), build the field set and pass it:

```python
reconciliation = reconcile_mapped_fields(
    mapping,
    sign_normalize_fields=_extract_sign_normalize_fields(catalog, market),
)
```

Add helper somewhere logical in the same file:

```python
def _extract_sign_normalize_fields(catalog, market: str) -> frozenset[str]:
    """Build the set of field_ids whose market policy says sign_normalize=absolute.

    Phase H2 Module A: reconciliation uses this to trigger abs() comparison
    for sign-convention-divergent fields like capital_expenditures.
    """
    out: set[str] = set()
    for field_id, entry in catalog.entries.items():
        if entry.source_policy is None:
            continue
        mp = entry.source_policy.market_policies.get(market)
        if mp is not None and mp.sign_normalize == "absolute":
            out.add(field_id)
    return frozenset(out)
```

### Step 5: confirm GREEN + full validation

```bash
uv run pytest -q && uv run ruff check . && uv run mypy src tests
```

### Step 6: live re-run for visual confirmation

```bash
rm -f tmp/runs/600519_2024-12-31/{evaluation.json,evaluation.md,extraction_result.json,reconciliation_report.json,turtle_mapping.json,source_policy_report.json}
set -a && source .env && set +a
uv run python -c "
from financial_report_llm_extractor.cli import main
main([
    'evaluate-company', '--company', '600519', '--year', '2024', '--market', 'CN',
    '--inventory', 'tmp/runs/600519_2024-12-31/source_inventory.jsonl',
    '--catalog', 'field_catalog/turtle_v015_source_mapping_minimal.json',
    '--taxonomy', 'field_catalog/turtle_v015_field_taxonomy.json',
    '--priorities', 'P0,P1,P2,P3', '--out', 'tmp/runs/600519_2024-12-31',
])
"
grep -E "capital_expenditures|interest_paid_cash" tmp/runs/600519_2024-12-31/evaluation.md
```

Expected: `clean_present` (or at least not `unresolved_conflict`) for both fields. Note the result for the eventual Module C report.

### Step 7: commit

```bash
git add field_catalog/turtle_v015_source_mapping_minimal.json src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py tests/test_provider_baseline_replay.py
git commit -m "feat: phase h2 module a applied - sign_normalize=absolute for capex + interest_paid_cash

Apply Module A mechanism to the 2 sign-mirror fields surfaced by Phase
EC live run on 600519/2024:
- capital_expenditures: AKShare +X / Yahoo -X (CN+HK)
- interest_paid_cash: AKShare +X / Yahoo -X (CN+HK)

evaluate_source_first_slice now extracts sign_normalize_fields per
market from catalog and threads them through reconcile_mapped_fields.

Live re-run on 600519/2024: capital_expenditures + interest_paid_cash
move from unresolved_conflict to clean_present.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: PDF spot-check + revenue/operating_profit semantic resolution

**Files:**
- Create: `field_catalog/provider_raw_semantics_cn.json`
- Modify: `field_catalog/provider_raw_semantics_hk.json`
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`
- Modify: `tests/test_catalog_consistency.py`

### Step 1: PDF spot-check (manual research, no code)

For each (field, company) cell, find the value in the PDF and compare to AKShare/Yahoo:

```bash
# CN: 600519 — search PDF for revenue and operating_profit
pdftotext -layout downloads/cn_stocks/600519/annual/2024_年度报告.pdf - | grep -E "营业收入|营业利润" | head -20
```

Expected (best understanding, to verify):
- **revenue / 600519**: PDF "营业收入" should match AKShare 170,899M; "营业总收入" matches Yahoo 174,144M (含 finance subsidiary 利息收入)
- **operating_profit / 600519**: PDF "营业利润" should match AKShare 119,689M; Yahoo Operating Income 118,276M may exclude or include some item differently

For HK 00001 + 01113:
```bash
pdftotext -layout downloads/hk_stocks/00001/annual/2025_annual_en.pdf - | grep -iE "revenue|operating profit|operating income" | head -30
pdftotext -layout downloads/hk_stocks/01113/annual/2025_annual_en.pdf - | grep -iE "revenue|operating profit|operating income" | head -30
```

For each cell, record in your work notes:
- which provider value matches PDF (if any)
- if neither matches → terminal_unverified
- if AKShare or Yahoo matches → that becomes primary, the other becomes related_only

### Step 2: write provider_raw_semantics rule tests (catalog consistency)

Append to `tests/test_catalog_consistency.py`:

```python
def test_provider_raw_semantics_cn_loads_h2_rules() -> None:
    """Phase H2: provider_raw_semantics_cn.json must include rules for
    H2-resolved fields (revenue, operating_profit) so spec compliance is
    locked at load time."""
    from financial_report_llm_extractor.structured_sources.provider_semantics import (
        load_provider_semantics_catalog,
    )

    catalog = load_provider_semantics_catalog(
        Path("field_catalog/provider_raw_semantics_cn.json")
    )
    rule_field_ids = {rule.turtle_field_id for rule in catalog.rules}
    assert "revenue" in rule_field_ids
    assert "operating_profit" in rule_field_ids
```

(If `provider_semantics` module doesn't have `load_provider_semantics_catalog` exported as a top-level public, replace with the actual loader. Verify with `grep -n "def load" src/financial_report_llm_extractor/structured_sources/provider_semantics*.py`.)

### Step 3: confirm RED

`uv run pytest tests/test_catalog_consistency.py -v -k provider_raw_semantics_cn` → fails (file doesn't exist).

### Step 4: create `field_catalog/provider_raw_semantics_cn.json`

Use the same schema as `provider_raw_semantics_hk.json`. Initial content (subject to PDF spot-check refinements from Step 1):

```json
{
  "rules": [
    {
      "provider": "akshare",
      "market": "CN",
      "raw_field_name": "OPERATE_INCOME",
      "raw_field_code": null,
      "turtle_field_id": "revenue",
      "semantic_claim": "营业收入 = 主营业务收入 + 其他业务收入；不含非经营性收入",
      "classification": "provider_semantics_sample_verified",
      "trusted_currency": "CNY",
      "trusted_unit": "yuan",
      "trusted_unit_multiplier": 1,
      "allowed_as_primary": true,
      "related_only_fields": ["TOTAL_OPERATE_INCOME"],
      "negative_examples": [],
      "proof_origin": "sampled_pdf_policy_proof",
      "samples": [
        {
          "company_id": "600519",
          "period_end": "2024-12-31",
          "pdf_page": "TBD-fill-after-spot-check",
          "pdf_value": "170,899,152,276.34",
          "currency": "CNY",
          "matches_raw_value": true
        }
      ],
      "required_proof": []
    },
    {
      "provider": "akshare",
      "market": "CN",
      "raw_field_name": "OPERATE_PROFIT",
      "raw_field_code": null,
      "turtle_field_id": "operating_profit",
      "semantic_claim": "营业利润 = 营业总收入 - 营业总成本 + 各项调整 (per CN P&L convention)",
      "classification": "TBD-after-spot-check",
      "...": "..."
    }
  ]
}
```

The `TBD-after-spot-check` placeholders for operating_profit need to become either `provider_semantics_sample_verified` (if 600519 PDF "营业利润" matches AKShare 119.69B exactly) or `provider_semantics_unverified` (if PDF doesn't match). Update the JSON inline based on Step 1's spot-check.

### Step 5: edit catalog `revenue` + `operating_profit` market_policies for CN

In `turtle_v015_source_mapping_minimal.json`:

For `revenue.source_policy.market_policies.CN`, ensure `primary_route="akshare_direct"` and `on_conflict="select_primary_require_pdf"` (or `"select_primary"` if the existing semantics-proven outcome warrants no further verification).

If H1 reverts left `cross_check_routes: []`, restore `["yahoo_direct"]` so reconciliation actually compares (and the new sample-verified rule allows AKShare to win cleanly).

### Step 6: HK fields — add to `provider_raw_semantics_hk.json`

For revenue + operating_profit on HK companies (00001, 01113), spot-check first. Likely outcomes:
- 00001: Total Revenue (Yahoo) = "Total revenue" in HKFRS PDF (broadly inclusive); H2 likely keeps HK revenue terminal_unverified or promotes Yahoo if PDF matches.
- 01113: similar.

Add 1-2 rules to `provider_raw_semantics_hk.json`:

```json
{
  "provider": "yahoo",
  "market": "HK",
  "raw_field_name": "Total Revenue",
  "turtle_field_id": "revenue",
  "classification": "TBD-after-spot-check",
  ...
}
```

### Step 7: full validation

`uv run pytest -q && uv run ruff check . && uv run mypy src tests` — all green.

### Step 8: commit

```bash
git add field_catalog/provider_raw_semantics_cn.json field_catalog/provider_raw_semantics_hk.json field_catalog/turtle_v015_source_mapping_minimal.json tests/test_catalog_consistency.py
git commit -m "feat: phase h2 module b - revenue + operating_profit semantic resolution

PDF spot-check on 600519/2024-12-31 + 00001/2025-12-31 + 01113/2025-12-31.

CN:
- revenue: promote AKShare OPERATE_INCOME (营业收入) as primary; Yahoo
  Total Revenue includes finance-subsidiary 利息收入 — related_only.
  provider_raw_semantics_cn.json (NEW) records the proof.
- operating_profit: [promote/terminal — fill after spot-check]

HK:
- revenue + operating_profit semantics rules added to
  provider_raw_semantics_hk.json (one rule per market). Promotion vs
  terminal contingent on per-company PDF spot-check captured in samples.

catalog_consistency test locks the new file's expected rule set.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: SGA + D&A + dividends_paid → terminal_unverified

**Files:**
- Modify: `field_catalog/provider_raw_semantics_cn.json`
- Modify: `field_catalog/provider_raw_semantics_hk.json`
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`
- Create: `tests/test_phase_h2_validation.py`

### Step 1: write Phase H2 expectation tests

Create `tests/test_phase_h2_validation.py`:

```python
"""Phase H2: locked-in field-bucket expectations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


CATALOG_PATH = Path("field_catalog/turtle_v015_source_mapping_minimal.json")
SEMANTICS_CN = Path("field_catalog/provider_raw_semantics_cn.json")
SEMANTICS_HK = Path("field_catalog/provider_raw_semantics_hk.json")


def _load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _load_semantics(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("rules", [])


def test_phase_h2_sga_and_da_are_terminal_unverified_in_both_markets() -> None:
    """SGA: catalog derivation only supports A-B; addition is out of scope.
    D&A: AKShare FA_IR_DEPR is fixed-asset-only, semantically unequal to
    Yahoo D&A (which includes intangibles amortization).
    Both stay terminal_unverified across CN+HK in H2."""
    cn_rules = _load_semantics(SEMANTICS_CN)
    hk_rules = _load_semantics(SEMANTICS_HK)

    for field_id in ("selling_general_administrative", "depreciation_amortization"):
        cn_match = [
            r for r in cn_rules
            if r.get("turtle_field_id") == field_id
        ]
        hk_match = [
            r for r in hk_rules
            if r.get("turtle_field_id") == field_id
        ]
        assert any(
            r.get("classification") == "provider_semantics_unverified"
            for r in cn_match + hk_match
        ), f"{field_id} must have at least one provider_semantics_unverified rule"


def test_phase_h2_dividends_paid_terminal_for_cn() -> None:
    """dividends_paid: even after sign-normalize, AKShare 70.95B vs Yahoo 68.79B
    has 2.9% residual gap (timing: 已付 vs 宣告)."""
    cn_rules = _load_semantics(SEMANTICS_CN)
    matches = [
        r for r in cn_rules if r.get("turtle_field_id") == "dividends_paid"
    ]
    assert any(
        r.get("classification") == "provider_semantics_unverified"
        for r in matches
    )
```

### Step 2: confirm RED (rules don't yet exist)

### Step 3: append rules to provider_raw_semantics_cn.json

For each field, add a rule with `classification: "provider_semantics_unverified"`. Example:

```json
{
  "provider": "akshare",
  "market": "CN",
  "raw_field_name": "MANAGE_EXPENSE",
  "turtle_field_id": "selling_general_administrative",
  "semantic_claim": "管理费用 alone, missing 销售费用 (SALE_EXPENSE) — single AKShare alias is incomplete; full SGA requires MANAGE_EXPENSE + SALE_EXPENSE addition derivation, not yet supported by catalog (mapping.py:251-258 only supports subtraction).",
  "classification": "provider_semantics_unverified",
  "trusted_currency": "CNY",
  "trusted_unit": "yuan",
  "trusted_unit_multiplier": 1,
  "allowed_as_primary": false,
  "related_only_fields": ["SALE_EXPENSE"],
  "negative_examples": [],
  "proof_origin": "sampled_pdf_policy_proof",
  "samples": [
    {
      "company_id": "600519",
      "period_end": "2024-12-31",
      "pdf_value": "[MANAGE+SALE sum-from-PDF-tbd]",
      "matches_raw_value": false,
      "matches_raw_value_reason": "akshare manage_expense alone is partial sga"
    }
  ],
  "required_proof": ["catalog addition derivation support (Phase H2.1)"]
}
```

Similar rules for `depreciation_amortization`, `dividends_paid`, plus HK equivalents in `provider_raw_semantics_hk.json` if applicable.

### Step 4: edit catalog market_policies for these 3 fields

Set `on_conflict="preserve_conflict"` for SGA, D&A, dividends_paid in CN+HK markets so the orchestrator knows these are intentionally non-clean.

### Step 5: full validation

`uv run pytest -q && uv run ruff check . && uv run mypy src tests` — all green.

### Step 6: commit

```bash
git add field_catalog/provider_raw_semantics_cn.json field_catalog/provider_raw_semantics_hk.json field_catalog/turtle_v015_source_mapping_minimal.json tests/test_phase_h2_validation.py
git commit -m "feat: phase h2 module b - lock SGA + D&A + dividends_paid as terminal_unverified

Three fields where neither AKShare nor Yahoo's raw value semantically
matches the Turtle field definition without provider_semantics proof:

- selling_general_administrative: AKShare MANAGE_EXPENSE alone is partial
  (excludes SALE_EXPENSE); addition derivation not yet supported (Phase
  H2.1 candidate). Catalog stays preserve_conflict.
- depreciation_amortization: AKShare FA_IR_DEPR is fixed-asset only;
  Yahoo D&A includes intangibles amortization. Not equivalent.
- dividends_paid: after sign-normalize residual 2.9% gap (timing: 已付
  vs 宣告). Locked terminal.

Provider semantics rules + on_conflict=preserve_conflict in market
policies. New tests/test_phase_h2_validation.py locks these decisions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Live before/after report + roadmap update

**Files:**
- Create: `docs/phase_h2_validation_report.md`
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
- Modify: `CLAUDE.md`

### Step 1: capture before-state (or use prior captures)

Before any Task 1 commit, the existing `tmp/runs/600519_2024-12-31/evaluation.json` already represents the baseline (after Phase EC Tier 1, before H2). Save copies:

```bash
mkdir -p tmp/runs/h2_before
cp tmp/runs/600519_2024-12-31/evaluation.json tmp/runs/h2_before/600519.json
```

If Tasks 1-4 have already run by this point (committed), the `evaluation.json` reflects the H2 state. Use git history or re-derive baseline from `git stash apply` of pre-H2 state. Practical: keep a `tmp/runs/h2_before/` snapshot taken immediately before Task 1's commit lands.

### Step 2: run after-state on all 3 companies

Live runs:

```bash
mkdir -p tmp/runs/h2_after
set -a && source .env && set +a

# 600519 CN already has source_inventory.jsonl from Phase EC; reuse
uv run python -c "
from financial_report_llm_extractor.cli import main
main(['evaluate-company', '--company', '600519', '--year', '2024', '--market', 'CN',
      '--inventory', 'tmp/runs/600519_2024-12-31/source_inventory.jsonl',
      '--catalog', 'field_catalog/turtle_v015_source_mapping_minimal.json',
      '--taxonomy', 'field_catalog/turtle_v015_field_taxonomy.json',
      '--priorities', 'P0,P1,P2,P3', '--out', 'tmp/runs/h2_after/600519'])
"
cp tmp/runs/h2_after/600519/evaluation.json tmp/runs/h2_after/600519.json

# Same for 00001 + 01113 — extract their fixture inventory if not already present.
```

For HK companies, extract inventory from fixture (mirror the 600519 procedure):

```bash
gunzip -c tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz | uv run python -c "
import sys, json, pathlib
out = {'00001': [], '01113': []}
for line in sys.stdin:
    rec = json.loads(line)
    period = (rec.get('period') or '')
    if not period.startswith('2025-12-31'):
        continue
    for ev in rec.get('source_evidence', []):
        rid = ev.get('raw_record_id', '')
        for ticker in ('00001', '01113'):
            if rid.startswith(ticker):
                out[ticker].append(line.rstrip())
                break
for ticker, lines in out.items():
    p = pathlib.Path(f'tmp/runs/h2_after/{ticker}')
    p.mkdir(parents=True, exist_ok=True)
    (p / 'source_inventory.jsonl').write_text('\\n'.join(lines) + '\\n')
    (p / 'source_inventory_summary.json').write_text('{}')
"

for ticker in 00001 01113; do
    uv run python -c "
from financial_report_llm_extractor.cli import main
main(['evaluate-company', '--company', '$ticker', '--year', '2025', '--market', 'HK',
      '--inventory', 'tmp/runs/h2_after/$ticker/source_inventory.jsonl',
      '--catalog', 'field_catalog/turtle_v015_source_mapping_minimal.json',
      '--taxonomy', 'field_catalog/turtle_v015_field_taxonomy.json',
      '--priorities', 'P0,P1,P2,P3', '--out', 'tmp/runs/h2_after/$ticker'])
"
done
```

### Step 3: write phase_h2_validation_report.md

Manually compose `docs/phase_h2_validation_report.md` from the diff of `tmp/runs/h2_before/*.json` vs `tmp/runs/h2_after/*.json`:

```markdown
# Phase H2 Validation Report

> Date: 2026-05-09
> Companies: 600519/2024-12-31 (CN), 00001/2025-12-31 (HK), 01113/2025-12-31 (HK)
> Catalog: H2 final state (post Tasks 1-4)

## Summary

| Company | Market | clean_present BEFORE | AFTER | Δ | unresolved_conflict BEFORE | AFTER | Δ |
|---------|--------|----------------------|-------|---|----------------------------|-------|---|
| 600519 | CN | 34 | [N] | [+M] | 21 | [N] | [-M] |
| 00001 | HK | [N] | [N] | [-M] | [N] | [N] | [-M] |
| 01113 | HK | [N] | [N] | [-M] | [N] | [N] | [-M] |

## Per-field bucket migrations

| Field | Company | Before | After | Reason |
|-------|---------|--------|-------|--------|
| capital_expenditures | 600519 | unresolved_conflict | clean_present | sign_normalize=absolute (Module A) |
| capital_expenditures | 00001 | ... | ... | ... |
| interest_paid_cash | 600519 | unresolved_conflict | clean_present | sign_normalize=absolute |
| revenue | 600519 | unresolved_conflict | clean_present (akshare) | provider_semantics_sample_verified (Module B) |
| operating_profit | 600519 | unresolved_conflict | [bucket] | [PDF spot-check outcome] |
| selling_general_administrative | 600519 | unresolved_conflict | [terminal_unverified or unresolved] | provider_semantics_unverified |
| depreciation_amortization | 600519 | unresolved_conflict | terminal_unverified | provider_semantics_unverified |
| dividends_paid | 600519 | unresolved_conflict | terminal_unverified | provider_semantics_unverified |
| ... (HK companies)

## Phase H2 deliverables produced

- Sign normalize mechanism (`MarketSourcePolicy.sign_normalize`)
- 4 catalog edits (capex/interest_paid_cash CN+HK)
- New `provider_raw_semantics_cn.json` with N rules
- HK semantics rules appended to `provider_raw_semantics_hk.json`
- 3 explicitly-locked terminals: SGA, D&A, dividends_paid

## Acceptance check

- [✓] ≥ 2 fields promote (capex + interest_paid_cash sign convention)
- [?] revenue/operating_profit promote count = N (PDF-verified)
- [✓] SGA/D&A/dividends_paid ∈ terminal_unverified per Spec
```

Fill in actual numbers from the live runs.

### Step 4: roadmap implementation result

Append to `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md` (after Phase EC follow-ups section):

```markdown
### Phase H2 Implementation Result

Status: implemented on 2026-05-09. See:
- `docs/superpowers/specs/2026-05-09-phase-h2-cn-hk-conflict-surgical-resolution.md`
- `docs/superpowers/plans/2026-05-09-phase-h2-cn-hk-conflict-surgical-resolution.md`
- `docs/phase_h2_validation_report.md`

Goal: surgical resolution of the 7 normalized_value_conflict fields surfaced
by Phase EC live run on 600519/2024.

Module A: `MarketSourcePolicy.sign_normalize` ("raw" | "absolute") —
reconciliation compares abs(normalized_value) when set. Applied to
`capital_expenditures` + `interest_paid_cash` (CN+HK). Both move from
unresolved_conflict → clean_present.

Module B: per-field PDF semantics proof (600519 CN + 00001/01113 HK):
- revenue: ... [TBD per spot-check outcome]
- operating_profit: ... [TBD]
- selling_general_administrative: terminal_unverified (catalog derivation
  only supports subtraction; addition deferred to Phase H2.1).
- depreciation_amortization: terminal_unverified (FA_IR_DEPR vs D&A not
  semantically equivalent).
- dividends_paid: terminal_unverified (sign-normalized residual 2.9%
  timing-mismatch).

Module C validation: phase_h2_validation_report.md tracks before/after
buckets across the 3 sample companies. 600519 unresolved_conflict
21 → [N]. P0 clean coverage [9 → 11+] (target). HK companies similarly
trace through.

H2 leaves Phase H2.1 as next candidate: addition derivation in catalog
to enable SGA's MANAGE_EXPENSE+SALE_EXPENSE composite.
```

### Step 5: CLAUDE.md update

Update phase table + 下一步 pointer:

```markdown
| H2 | sign_normalize policy + provider_raw_semantics_cn.json | 7 conflict fields surgical resolution: 2 promote via sign_normalize, 5 routed by PDF semantics proof to clean_present or terminal_unverified per market |
```

下一步 pointer: 加 "Phase H2.1（SGA 加法 derivation）" 候选；记录 H2 完成。

### Step 6: validation + commit

`uv run pytest -q && uv run ruff check . && uv run mypy src tests` — all green.

```bash
git add docs/phase_h2_validation_report.md docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md CLAUDE.md
git commit -m "docs: phase h2 validation report + roadmap implementation result

3-company live before/after captures:
- 600519/2024 (CN): unresolved_conflict 21 → N (Δ -M)
- 00001/2025 (HK): ...
- 01113/2025 (HK): ...

H2 closes the 2 sign-mirror fields (capex, interest_paid_cash) via
Module A mechanism. The 5 true semantic gaps split between
provider_semantics_sample_verified promotions (revenue/operating_profit
where PDF allows) and provider_semantics_unverified terminals
(SGA/D&A/dividends_paid).

Phase H2.1 candidate identified: addition derivation for SGA.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Acceptance Criteria

- 5 commits, each independently green (pytest + ruff + mypy)
- ≥ 4 new unit tests across reconciliation, catalog consistency, phase_h2 validation
- 600519/2024 evaluation: ≥ 2 fields move from unresolved_conflict to clean_present (capex + interest_paid_cash guaranteed via Module A)
- Revenue + operating_profit on CN: PDF-verified outcome documented in provider_raw_semantics_cn.json samples
- SGA + D&A + dividends_paid: 3 explicit `provider_semantics_unverified` rules in CN/HK
- Phase H2 validation report enumerates before/after for all 3 sample companies
- roadmap + CLAUDE.md reflect H2 completion
- No silent semantic promotion (every primary swap or terminal has corresponding rule)
