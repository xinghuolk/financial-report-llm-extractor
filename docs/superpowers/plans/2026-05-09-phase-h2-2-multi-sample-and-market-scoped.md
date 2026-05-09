# Phase H2.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Three independent sub-modules: (Sub-A) multi-company sample-verification on H2/H2.1's 5 promotions; (Sub-B) market-scoped source_aliases schema + HK SGA recovery (terminal-honest); (Sub-C) clean-row candidate-value display in evaluation.md.

**Architecture:**
- Sub-A is data work: PDF spot-check 3 CN companies, append samples to `provider_raw_semantics_cn.json`. No code change.
- Sub-B is small schema extension: `source_aliases.by_market` form recognized at lookup; falls back to provider-level when absent.
- Sub-C is display layer: drop bucket filter in `_collect_candidate_values`; show all candidates (≥ 2) regardless of bucket.

**Tech Stack:** Python 3.11 stdlib + pytest. JSON catalog + provider_raw_semantics. PDF spot-check via `pdftotext -layout`.

**Spec:** `docs/superpowers/specs/2026-05-09-phase-h2-2-multi-sample-and-market-scoped.md`

---

## Task 1: Sub-C — markdown candidate values for clean rows

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/company_evaluation.py`
- Modify: `tests/test_company_evaluation.py`

### Step 1: write failing test

Append to `tests/test_company_evaluation.py`:

```python
def test_render_markdown_shows_candidate_values_for_clean_present_with_multi_source() -> None:
    """Phase H2.2 Sub-C: clean_present rows with 2+ candidates show all
    provider values inline (e.g. 'akshare:170.90B / yahoo:174.14B') for audit
    transparency. Single-candidate rows still render only the selected value."""
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        CompanyEvaluation, CompanyFieldEvaluation, render_evaluation_markdown,
    )
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
    )
    from decimal import Decimal

    evaluation = CompanyEvaluation(
        company="600519",
        period=PeriodSpec.from_year(2024),
        market="CN",
        generated_at="2026-05-09T00:00:00+00:00",
        fields=(
            CompanyFieldEvaluation(
                field_id="revenue",
                bucket="clean_present",
                selected_source="akshare",
                value=Decimal("170899152276.34"),
                currency="CNY",
                unit="yuan",
                reason=None,
                # Multi-source: both akshare + yahoo present, akshare selected
                candidate_values=(
                    ("akshare", "170.90B"),
                    ("yahoo", "174.14B"),
                ),
            ),
        ),
        by_bucket={
            "clean_present": 1, "unresolved_conflict": 0, "llm_supplement_present": 0,
            "terminal_unverified": 0, "not_in_scope": 0, "source_unavailable": 0,
        },
        by_priority={"P0": {
            "clean_present": 1, "unresolved_conflict": 0, "llm_supplement_present": 0,
            "terminal_unverified": 0, "not_in_scope": 0, "source_unavailable": 0,
        }},
    )

    md = render_evaluation_markdown(evaluation)

    # Both provider values appear in the value column for the clean row.
    assert "akshare:170.90B" in md
    assert "yahoo:174.14B" in md
    # Selected source still visible in the Source column (no need for inline marker).
    assert "akshare" in md
```

### Step 2: confirm RED

`uv run pytest tests/test_company_evaluation.py::test_render_markdown_shows_candidate_values_for_clean_present_with_multi_source -v` — fails because `_collect_candidate_values` only emits for non-clean buckets.

### Step 3: fix `_collect_candidate_values`

In `src/financial_report_llm_extractor/structured_sources/company_evaluation.py:235-258`:

Current:
```python
def _collect_candidate_values(
    field_id: str,
    bucket: BucketName,
    mapping: TurtleMappingResult | None,
) -> tuple[tuple[str, str], ...]:
    if mapping is None:
        return ()
    if bucket not in {"unresolved_conflict", "terminal_unverified", "source_unavailable"}:
        return ()
    field = mapping.fields.get(field_id)
    if field is None:
        return ()
    out: list[tuple[str, str]] = []
    for c in field.candidates:
        if c.normalized_value is None:
            continue
        out.append((c.source, _format_money_short(c.normalized_value)))
    return tuple(out)
```

Replace with:
```python
def _collect_candidate_values(
    field_id: str,
    bucket: BucketName,
    mapping: TurtleMappingResult | None,
) -> tuple[tuple[str, str], ...]:
    """Pull per-source candidate normalized values from mapping for any field
    with multi-source candidates. Phase H2.2 Sub-C: emit for ALL buckets so
    clean_present rows also show competing provider values for audit
    transparency. Single-candidate fields remain empty (Source/Value columns
    already convey the same info)."""
    if mapping is None:
        return ()
    field = mapping.fields.get(field_id)
    if field is None or len(field.candidates) < 2:
        return ()
    out: list[tuple[str, str]] = []
    for c in field.candidates:
        if c.normalized_value is None:
            continue
        out.append((c.source, _format_money_short(c.normalized_value)))
    return tuple(out)
```

Also update markdown render at `company_evaluation.py:309-318`. Currently:
```python
if f.value is not None:
    value_str = _format_decimal_plain(f.value)
elif f.candidate_values:
    value_str = " / ".join(f"{src}:{val}" for src, val in f.candidate_values)
else:
    value_str = ""
```

Need to also show candidate_values when value is set (multi-source clean). Replace with:
```python
if f.candidate_values and len(f.candidate_values) >= 2:
    # Multi-source row: show all candidates for audit. Source column conveys selection.
    value_str = " / ".join(f"{src}:{val}" for src, val in f.candidate_values)
elif f.value is not None:
    value_str = _format_decimal_plain(f.value)
else:
    value_str = ""
```

### Step 4: GREEN + verify existing tests still pass

```bash
uv run pytest tests/test_company_evaluation.py -v
uv run pytest -q && uv run ruff check . && uv run mypy src tests
```

The existing `test_render_markdown_shows_candidate_values_for_conflict_rows` test should still pass (its candidate_values tuple has 2 entries). The clean-present sample evaluation in `_build_sample_evaluation` may need updating if its assertions break — verify and fix.

### Step 5: live re-run for visual verification

```bash
rm -f tmp/runs/600519_2024-12-31/{evaluation.json,evaluation.md,extraction_result.json,reconciliation_report.json,turtle_mapping.json,source_policy_report.json,review_summary.json,source_coverage_summary.*,warning_classification.*}
uv run python -c "
from financial_report_llm_extractor.cli import main
main(['evaluate-company', '--company', '600519', '--year', '2024', '--market', 'CN',
      '--inventory', 'tmp/runs/600519_2024-12-31/source_inventory.jsonl',
      '--catalog', 'field_catalog/turtle_v015_source_mapping_minimal.json',
      '--taxonomy', 'field_catalog/turtle_v015_field_taxonomy.json',
      '--priorities', 'P0,P1,P2,P3', '--out', 'tmp/runs/600519_2024-12-31'])
" 2>&1 | tail -10
grep -E "^\| (revenue|operating_profit|capital_expenditures|interest_paid_cash) \|" tmp/runs/600519_2024-12-31/evaluation.md
```

Expected: revenue/operating_profit etc clean rows now show `akshare:X / yahoo:Y` with both visible. selling_general_administrative is derivation-only (no candidates) — remains as-is showing only 14.95B.

### Step 6: commit

```bash
git add src/financial_report_llm_extractor/structured_sources/company_evaluation.py tests/test_company_evaluation.py
git commit -m "feat: phase h2.2 sub-c - clean rows show candidate values for audit

evaluation.md previously hid Yahoo competing values for clean_present
rows where AKShare won (e.g. revenue: 'akshare:170.90B' shown but
'yahoo:174.14B' invisible). reviewer couldn't spot Yahoo divergence
inline → potential sampling-bias blind spot.

Fix: drop bucket filter in _collect_candidate_values; emit candidate
values for any field with >= 2 candidates regardless of bucket.
Markdown renderer prefers candidate display when multi-source even on
clean rows. Source column already conveys selection — no inline marker
needed.

Single-candidate / derivation-only fields (e.g. SGA after H2.1)
unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Sub-A — PDF spot-check 3 CN companies × 5 fields

**Files:**
- Create: `docs/phase_h2_2_multi_company_spot_check.md`

### Step 1: identify available PDFs

```bash
ls downloads/cn_stocks/{300750,601919,688008}/annual/ 2>/dev/null
```

For each available PDF, extract the 5 promotion fields:

```bash
for COMPANY in 300750 601919 688008; do
  PDF=$(ls downloads/cn_stocks/${COMPANY}/annual/*.pdf 2>/dev/null | grep -E '202[34]' | tail -1)
  [ -z "$PDF" ] && continue
  echo "=== $COMPANY ($PDF) ==="
  echo "--- 营业收入 ---"
  pdftotext -layout "$PDF" - 2>/dev/null | grep -E "^\s*营业收入\s+[0-9]" | head -3
  echo "--- 营业利润 ---"
  pdftotext -layout "$PDF" - 2>/dev/null | grep -E "营业利润" | head -3
  echo "--- 销售/管理 ---"
  pdftotext -layout "$PDF" - 2>/dev/null | grep -E "(销售费用|管理费用)" | head -4
  echo "--- 资本开支 ---"
  pdftotext -layout "$PDF" - 2>/dev/null | grep -iE "购建固定资产|capital expenditures" | head -3
  echo "--- 利息支付 ---"
  pdftotext -layout "$PDF" - 2>/dev/null | grep -E "支付的利息|分配股利" | head -3
done
```

### Step 2: cross-reference with fixture for AKShare values

```bash
gunzip -c tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz | uv run python -c "
import sys, json
companies = ('300750','601919','688008')
fields = {'OPERATE_INCOME','OPERATE_PROFIT','MANAGE_EXPENSE','SALE_EXPENSE','CONSTRUCT_LONG_ASSET','PAY_INTEREST_COMMISSION'}
for line in sys.stdin:
    rec = json.loads(line)
    if not (rec.get('period') or '').startswith('2024-12-31'):
        continue
    if rec.get('source') != 'akshare':
        continue
    rfn = rec.get('raw_field_name') or ''
    rfc = rec.get('raw_field_code') or ''
    if rfn in fields or rfc in fields:
        for ev in rec.get('source_evidence', []):
            rid = ev.get('raw_record_id', '')
            for c in companies:
                if rid.startswith(c):
                    print(f'{c} {rfn or rfc}: {rec.get(\"parsed_numeric_value\")}')
                    break
"
```

If a company isn't in the fixture, note it and skip its samples (work with available data only).

### Step 3: write doc with findings

Create `docs/phase_h2_2_multi_company_spot_check.md`:

```markdown
# Phase H2.2 Sub-A: Multi-Company SGA/Revenue/etc PDF Spot-Check

> Date: 2026-05-09
> Companies: 300750 (CATL), 601919 (COSCO), 688008 (Hygon) — different industries to test sample diversity
> Fields: revenue, operating_profit, capital_expenditures, interest_paid_cash, selling_general_administrative

## Per-company table

### 300750 / 2024-12-31 (CATL — battery manufacturing)

| Field | PDF value (CNY) | AKShare value (CNY) | Match? | Notes |
|-------|-----------------|---------------------|--------|-------|
| revenue (营业收入) | [extract] | [extract] | true/false | |
| operating_profit (营业利润) | [extract] | [extract] | | |
| ... |

### 601919 / 2024-12-31 (COSCO Shipping)

[same table] ...

### 688008 / 2024-12-31 (Hygon — semiconductor)

[same table] ...

## Aggregate finding

Of 15 (3 companies × 5 fields) cells:
- N exact PDF matches → confirms H2/H2.1 promotion holds across industries
- M near-match (< 1% rounding diff) → noted in samples with reason
- K mismatches → require regression review of promotion (rare expected)

## Decision per field

[For each field, summarize whether multi-company evidence supports keeping promotion as-is or warrants downgrading.]
```

### Step 4: commit

```bash
git add docs/phase_h2_2_multi_company_spot_check.md
git commit -m "docs: phase h2.2 sub-a - multi-company SGA/revenue/etc PDF spot-check

PDF-verified the 5 H2/H2.1 promotion fields against 3 additional CN
issuers (300750 CATL battery, 601919 COSCO shipping, 688008 Hygon
semiconductor). Multi-industry coverage hardens the sample-verified
proofs against single-company sampling-bias.

[Summary of N/M/K findings]

Task 3 will append the verified samples into provider_raw_semantics_cn.json.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Sub-A — multi-company samples in provider_raw_semantics_cn.json

**Files:**
- Modify: `field_catalog/provider_raw_semantics_cn.json`
- Modify: `tests/test_phase_h2_validation.py` (existing tests; verify samples > 1)

### Step 1: write test asserting multi-company samples

Append to `tests/test_phase_h2_validation.py`:

```python
def test_phase_h2_2_promoted_rules_have_multi_company_samples() -> None:
    """Phase H2.2 Sub-A: each H2/H2.1 promoted rule should have ≥ 2 sample
    companies — single-sample sample_verified is sampling-bias risk per drift §177."""
    cn_rules = _load_semantics(SEMANTICS_CN)
    promoted = [r for r in cn_rules if r.get("classification") == "provider_semantics_sample_verified"]
    assert promoted, "expected at least one promoted rule"
    for rule in promoted:
        samples = rule.get("samples", [])
        sample_companies = {s.get("company_id") for s in samples}
        assert len(sample_companies) >= 2, (
            f"rule for {rule.get('turtle_field_id')!r} (raw {rule.get('raw_field_name')!r}) "
            f"has only {len(sample_companies)} sample companies: {sample_companies}. "
            f"Phase H2.2 Sub-A requires ≥ 2 to mitigate sampling-bias."
        )
```

### Step 2: confirm RED

`uv run pytest tests/test_phase_h2_validation.py -v -k multi_company_samples` → fails (current rules have only 600519).

### Step 3: append samples per Task 2 findings

For each rule in `provider_raw_semantics_cn.json` that's `provider_semantics_sample_verified`, append samples for the 3 new companies based on Task 2 doc:

```jsonc
"samples": [
  {"company_id": "600519", "period_end": "2024-12-31", "pdf_value": "...", "matches_raw_value": true, ...},  // existing
  {"company_id": "300750", "period_end": "2024-12-31", "pdf_value": "...", "matches_raw_value": true, ...},  // NEW
  {"company_id": "601919", "period_end": "2024-12-31", "pdf_value": "...", "matches_raw_value": true_or_false, ...},  // NEW
  {"company_id": "688008", "period_end": "2024-12-31", "pdf_value": "...", "matches_raw_value": true, ...}   // NEW
]
```

If a sample is `matches_raw_value: false`, add `matches_raw_value_reason` per the schema convention. The promotion stays sample_verified IF ≥ 2 of 4 are true (majority); if ≤ 1 true, downgrade to unverified.

If 300750/601919/688008 are missing from the fixture for a particular field (e.g. shipping company has no `MANAGE_EXPENSE` raw record), document the absence in `samples[].notes` and skip that company for that field. The test only requires ≥ 2 sample companies overall.

### Step 4: GREEN + full validation

`uv run pytest -q && uv run ruff check . && uv run mypy src tests` — all green.

### Step 5: commit

```bash
git add field_catalog/provider_raw_semantics_cn.json tests/test_phase_h2_validation.py
git commit -m "feat: phase h2.2 sub-a - multi-company samples for promoted rules

Append PDF-verified samples from 300750 / 601919 / 688008 (per
docs/phase_h2_2_multi_company_spot_check.md) to each
provider_semantics_sample_verified rule in provider_raw_semantics_cn.json.

Each promoted rule now carries ≥ 2 sample companies, mitigating the
single-sample sampling-bias risk (drift §177) flagged in H2 + H2.1
validation reports.

New regression test test_phase_h2_2_promoted_rules_have_multi_company_samples
asserts the invariant.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Sub-B — source_aliases.by_market schema + lookup

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/catalog.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/mapping.py`
- Modify: `tests/test_source_mapping.py` (or new test file)
- Modify: `tests/test_source_mapping_catalog.py` (catalog parsing)

### Step 1: write failing test

Append to `tests/test_source_mapping.py`:

```python
def test_source_aliases_by_market_takes_precedence_over_provider_level() -> None:
    """Phase H2.2 Sub-B: when source_aliases includes by_market.<MARKET>.<provider>,
    that takes precedence over provider-level aliases for records in that market."""
    from decimal import Decimal
    from financial_report_llm_extractor.structured_sources.catalog import (
        SourceMappingCatalog, SourceMappingEntry,
    )
    from financial_report_llm_extractor.structured_sources.mapping import (
        map_source_inventory,
    )

    # CN-side: yahoo provider has no aliases (HK has Yahoo SGA alias)
    catalog = SourceMappingCatalog(
        catalog_id="test", version="v0",
        entries={
            "selling_general_administrative": SourceMappingEntry(
                field_id="selling_general_administrative",
                priority="P1",
                value_type="money",
                statement_type="income_statement",
                currency_requirement="required",
                unit_requirement="required",
                source_aliases={
                    "akshare": (),
                    "yahoo": (),
                    "by_market": {
                        "HK": {"yahoo": ("Selling General And Administration",)},
                    },
                },
            )
        },
    )
    records = (
        _h2_1_record(source="yahoo", raw_field_name="Selling General And Administration",
                     parsed_numeric_value=Decimal("100"), currency="HKD",
                     market="HK"),
    )

    result = map_source_inventory(catalog, records)
    sga = result.fields["selling_general_administrative"]
    assert sga.status == "present"
    assert sga.value == Decimal("100")


def test_source_aliases_by_market_does_not_match_other_markets() -> None:
    """Sub-B: HK-scoped Yahoo SGA alias should NOT match a yahoo CN record."""
    from decimal import Decimal
    from financial_report_llm_extractor.structured_sources.catalog import (
        SourceMappingCatalog, SourceMappingEntry,
    )
    from financial_report_llm_extractor.structured_sources.mapping import (
        map_source_inventory,
    )

    catalog = SourceMappingCatalog(
        catalog_id="test", version="v0",
        entries={
            "selling_general_administrative": SourceMappingEntry(
                field_id="selling_general_administrative",
                priority="P1",
                value_type="money",
                statement_type="income_statement",
                currency_requirement="required",
                unit_requirement="required",
                source_aliases={
                    "akshare": (),
                    "yahoo": (),
                    "by_market": {
                        "HK": {"yahoo": ("Selling General And Administration",)},
                    },
                },
            )
        },
    )
    records = (
        _h2_1_record(source="yahoo", raw_field_name="Selling General And Administration",
                     parsed_numeric_value=Decimal("100"), currency="CNY",
                     market="CN"),  # CN market — HK rule should not match
    )

    result = map_source_inventory(catalog, records)
    sga = result.fields["selling_general_administrative"]
    assert sga.status == "missing"
```

May need to extend `_h2_1_record` helper to accept `market` kwarg if it doesn't already.

### Step 2: confirm RED

`uv run pytest tests/test_source_mapping.py -v -k by_market` — fails (catalog doesn't recognize `by_market` key OR mapping doesn't dispatch to it).

### Step 3: schema + lookup

In `catalog.py`:
- Update `source_aliases` parsing to recognize `by_market` key as a special nested form
- Backward compatible: if `by_market` absent, behavior unchanged
- Validate: if present, must be `dict[str (market), dict[str (provider), tuple[str, ...]]]`

The simplest path may be to keep `source_aliases: dict[str, ...]` typed loosely; mapping.py reads `source_aliases.get("by_market", {})` separately. Decide based on existing dataclass shape; keep `validate()` strict about non-empty source_aliases (requires at least one provider key OR by_market non-empty).

In `mapping.py:_record_matches_entry`:

```python
def _record_matches_entry(record: SourceInventoryRecord, entry: SourceMappingEntry) -> bool:
    if record.source_status != "present":
        return False
    aliases: tuple[str, ...] = ()
    by_market = entry.source_aliases.get("by_market") if isinstance(entry.source_aliases.get("by_market"), dict) else {}
    if isinstance(by_market, dict):
        market_entry = by_market.get(record.market, {})
        if isinstance(market_entry, dict):
            aliases = tuple(market_entry.get(record.source, ()))
    if not aliases:
        # fall back to provider-level
        provider_aliases = entry.source_aliases.get(record.source, ())
        if isinstance(provider_aliases, (list, tuple)):
            aliases = tuple(provider_aliases)
    return record.raw_field_name in aliases or (
        record.raw_field_code is not None and record.raw_field_code in aliases
    )
```

Adjust the typing/structure based on `SourceMappingEntry.source_aliases` actual type (currently `dict[str, tuple[str, ...]]`). Either widen the type (allow nested `by_market` dict) or store `by_market` as a separate field on `SourceMappingEntry`. The cleaner option may be a separate field:

```python
@dataclass(frozen=True)
class SourceMappingEntry:
    ...
    source_aliases: dict[str, tuple[str, ...]]
    by_market_aliases: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)  # NEW
```

Then mapping uses `entry.by_market_aliases.get(record.market, {}).get(record.source, ())` for the lookup, falling back to `entry.source_aliases.get(record.source, ())`.

This separates concerns cleaner. Use this approach.

### Step 4: extend `catalog.py` parser

Recognize a `by_market` key in source_aliases JSON form, populate `by_market_aliases` field on the dataclass, leave `source_aliases` with only the provider-level keys.

```python
# In _parse_source_aliases or equivalent:
provider_aliases = {}
by_market_aliases = {}
for k, v in raw_aliases.items():
    if k == "by_market" and isinstance(v, dict):
        for market, market_dict in v.items():
            if isinstance(market_dict, dict):
                by_market_aliases[market] = {
                    p: tuple(aliases)
                    for p, aliases in market_dict.items()
                    if isinstance(aliases, (list, tuple))
                }
    elif isinstance(v, (list, tuple)):
        provider_aliases[k] = tuple(v)
```

### Step 5: GREEN + validation

`uv run pytest -q && uv run ruff check . && uv run mypy src tests` — all green. Existing tests continue to pass since `by_market_aliases` defaults to empty.

### Step 6: commit

```bash
git add src/financial_report_llm_extractor/structured_sources/catalog.py src/financial_report_llm_extractor/structured_sources/mapping.py tests/test_source_mapping.py
git commit -m "feat: phase h2.2 sub-b - source_aliases.by_market schema + lookup

SourceMappingEntry gains by_market_aliases: dict[market, dict[provider, tuple]].
Catalog parser recognizes 'by_market' key in source_aliases JSON.
mapping._record_matches_entry checks by_market lookup first, falls back
to provider-level aliases.

Mechanism only — Task 5 applies it to HK SGA (terminal-honest per
spot-check decision).

Two new tests cover: by_market match for HK / by_market does not match
other markets.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Sub-B — HK SGA market-scoped Yahoo alias + spot-check + rule

**Files:**
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`
- Modify: `field_catalog/provider_raw_semantics_hk.json`
- Modify: `tests/test_phase_h2_validation.py`

### Step 1: PDF spot-check 00001 + 01113 SGA

```bash
echo "=== 00001 SGA ==="
pdftotext -layout downloads/hk_stocks/00001/annual/2025_annual_en.pdf - 2>/dev/null | grep -iE "selling.*general|administrative|S\.G\.&A" | head -10
echo "=== 01113 SGA ==="
pdftotext -layout downloads/hk_stocks/01113/annual/2025_annual_en.pdf - 2>/dev/null | grep -iE "selling.*general|administrative|S\.G\.&A" | head -10
```

Compare to fixture Yahoo `Selling General And Administration` value for each. Decide:
- EXACT match → rule classification = `provider_semantics_sample_verified`, allowed_as_primary=true
- Otherwise → rule stays `provider_semantics_unverified`, allowed_as_primary=false (just ensure rule exists, schema infra is what's landing)

### Step 2: catalog edit — add HK Yahoo SGA via by_market

In `field_catalog/turtle_v015_source_mapping_minimal.json` find `selling_general_administrative` entry. Add `by_market`:

```jsonc
"source_aliases": {
  "akshare": [],
  "yahoo": [],
  "by_market": {
    "HK": {
      "yahoo": ["Selling General And Administration"]
    }
  }
}
```

### Step 3: provider_raw_semantics_hk.json rule

Append a rule for HK Yahoo SGA based on spot-check decision. Default conservative (terminal):

```jsonc
{
  "provider": "yahoo",
  "market": "HK",
  "raw_field_name": "Selling General And Administration",
  "raw_field_code": null,
  "turtle_field_id": "selling_general_administrative",
  "semantic_claim": "Yahoo HK Selling General And Administration scope unverified for HK issuers — spot-check on 00001/2025 + 01113/2025 shows [exact-match-or-not per spot-check].",
  "classification": "provider_semantics_unverified" or "provider_semantics_sample_verified",
  "trusted_currency": "HKD",
  "trusted_unit": "raw",
  "trusted_unit_multiplier": 1,
  "allowed_as_primary": false or true,
  "related_only_fields": [],
  "negative_examples": [],
  "proof_origin": "sampled_pdf_policy_proof",
  "samples": [
    {"company_id": "00001", "period_end": "2025-12-31", "pdf_value": "...", "matches_raw_value": true_or_false, ...},
    {"company_id": "01113", "period_end": "2025-12-31", "pdf_value": "...", "matches_raw_value": true_or_false, ...}
  ],
  "required_proof": []
}
```

### Step 4: test expectation

Update `tests/test_phase_h2_validation.py`. If terminal: rule exists with `provider_semantics_unverified` for HK SGA. If promoted: rule exists with `provider_semantics_sample_verified`. Match the spot-check decision.

### Step 5: live re-run + verify

```bash
mkdir -p tmp/runs/h2_2_after/{00001,01113}
gunzip -c tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz | uv run python -c "
import sys, json, pathlib
out = {'00001': [], '01113': []}
for line in sys.stdin:
    rec = json.loads(line)
    if not (rec.get('period') or '').startswith('2025-12-31'):
        continue
    for ev in rec.get('source_evidence', []):
        rid = ev.get('raw_record_id', '')
        for ticker in ('00001', '01113'):
            if rid.startswith(ticker):
                out[ticker].append(line.rstrip())
                break
        else:
            continue
        break
for ticker, lines in out.items():
    p = pathlib.Path(f'tmp/runs/h2_2_after/{ticker}')
    p.mkdir(parents=True, exist_ok=True)
    (p / 'source_inventory.jsonl').write_text('\\n'.join(lines) + '\\n')
"

for t in 00001 01113; do
  uv run python -c "
from financial_report_llm_extractor.cli import main
main(['evaluate-company', '--company', '$t', '--year', '2025', '--market', 'HK',
      '--inventory', 'tmp/runs/h2_2_after/$t/source_inventory.jsonl',
      '--catalog', 'field_catalog/turtle_v015_source_mapping_minimal.json',
      '--taxonomy', 'field_catalog/turtle_v015_field_taxonomy.json',
      '--priorities', 'P0,P1,P2,P3', '--out', 'tmp/runs/h2_2_after/$t'])
"
  grep -E "^\| selling_general_administrative \|" tmp/runs/h2_2_after/$t/evaluation.md
done
```

Expected:
- Terminal: HK 00001/01113 SGA → `terminal_unverified` (Yahoo alias matches but rule says unverified) — improvement vs H2.1's source_policy_resolvable
- Promoted: SGA → `clean_present` (yahoo)

### Step 6: commit

```bash
git add field_catalog/turtle_v015_source_mapping_minimal.json field_catalog/provider_raw_semantics_hk.json tests/test_phase_h2_validation.py
git commit -m "feat: phase h2.2 sub-b - HK SGA market-scoped yahoo alias + rule

Catalog: SGA gets by_market.HK.yahoo = ['Selling General And Administration']
so HK Yahoo SGA records match the catalog entry again (regression
recovery after H2.1 emptied yahoo provider-level alias to enable CN
derivation).

provider_raw_semantics_hk.json: add Yahoo HK SGA rule with
classification = [provider_semantics_(un)verified per spot-check]
+ samples for 00001/2025 + 01113/2025.

Live HK re-run: SGA → [terminal_unverified or clean_present per
spot-check].

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: validation report + roadmap

**Files:**
- Create: `docs/phase_h2_2_validation_report.md`
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
- Modify: `CLAUDE.md`

### Step 1: write report

Create `docs/phase_h2_2_validation_report.md` covering:
- Sub-A: per-company × per-field sample matrix; aggregate "N exact / M close / K mismatch"
- Sub-B: HK SGA outcome (terminal_unverified or clean_present) with spot-check evidence link
- Sub-C: evaluation.md before/after snippet showing clean rows now display candidates
- 600519/2024 final clean_present count (still 39, no regression)
- HK 00001/01113 SGA bucket transition: source_policy_resolvable → terminal_unverified (or clean_present)

### Step 2: roadmap + CLAUDE.md

Append `### Phase H2.2 Implementation Result` to roadmap. Update CLAUDE.md phase table + 下一步 pointer.

### Step 3: commit

```bash
git add docs/phase_h2_2_validation_report.md docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md CLAUDE.md
git commit -m "docs: phase h2.2 validation report + roadmap update

[Three-sub-module summary]

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Acceptance Criteria

- 6 commits, each pytest + ruff + mypy green
- ≥ 5 new unit tests (T1: 1, T3: 1, T4: 2, T5: 0-1)
- Provider_raw_semantics_cn rules each have ≥ 2 sample companies
- catalog `source_aliases.by_market` schema parses + lookup respected
- HK SGA bucket changed from source_policy_resolvable → terminal_unverified or clean_present
- evaluation.md clean_present rows with multi-source candidates show all values
- 600519/2024 clean_present unchanged at 39
