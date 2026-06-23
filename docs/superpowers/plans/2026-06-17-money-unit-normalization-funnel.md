# Money Unit Normalization Funnel 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 LLM supplement 路径的 money 字段在收口点统一归一化（补 `normalized_value` + `canonical_unit`），修复 `money.py` 缺失的「万/亿」乘数，并把归一化值贯通到 evaluation.json / DB / 公共 API 三层。

**Architecture:** money 字段有两条独立构造路径。provider 路径在 `mapping._candidate_from_record` 已归一化，无需改。LLM 路径在 `provider_baseline_replay._merge_llm_evidence_supplement`（line 706）独立构造、不传 `normalized_value` —— 收口点就在这里。配合 `money.py` 词表补全 + `currency_hint` 增强 + 输出三层贯通。

**Tech Stack:** Python 3.11 stdlib only（Decimal）、SQLite、pytest、ruff、mypy、uv。

**Spec:** `docs/superpowers/specs/2026-06-17-money-unit-normalization-funnel-design.md`

---

## 文件结构

| 文件 | 职责 | 改动 |
|------|------|------|
| `src/financial_report_llm_extractor/money.py` | 确定性金额归一化 | `_resolve_multiplier` 补万/亿；`normalize_money`/`resolve_money_unit` 加 `currency_hint` |
| `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py` | LLM supplement merge | `_merge_llm_evidence_supplement` 收口归一化（核心） |
| `src/financial_report_llm_extractor/structured_sources/company_evaluation.py` | evaluation 输出 | `CompanyFieldEvaluation` + 构造 + 序列化加两字段 |
| `src/financial_report_llm_extractor/cache/db_schema.py` | DB schema | `field_values` 加两列（v3） |
| `src/financial_report_llm_extractor/cache/db.py` | DB 迁移 | `_is_legacy_schema` 增检 normalized_value |
| `src/financial_report_llm_extractor/cache/indexer.py` | DB 写入 | INSERT + `_merge_field_row` 加两字段 |
| `src/financial_report_llm_extractor/cache/db_query.py` | DB 读取 | `_FIELD_COLUMNS` + `_decode_field_row` 加两列 |
| `src/financial_report_llm_extractor/client.py` | 公共 API | `FieldValue` + `build_field_value` 加两字段 |

---

## Task 1: money.py 补「万/亿」乘数（修词表缺口）

**Files:**
- Modify: `src/financial_report_llm_extractor/money.py:73-81`
- Test: `tests/test_money.py`

- [ ] **Step 1: Write the failing test**

在 `tests/test_money.py` 末尾追加：

```python
from decimal import Decimal

from financial_report_llm_extractor.money import _resolve_multiplier


def test_resolve_multiplier_wan():
    assert _resolve_multiplier("万元") == Decimal("10000")
    assert _resolve_multiplier("万") == Decimal("10000")


def test_resolve_multiplier_yi():
    assert _resolve_multiplier("亿元") == Decimal("100000000")
    assert _resolve_multiplier("亿") == Decimal("100000000")


def test_resolve_multiplier_baiwan_not_confused_by_wan():
    # 「百万元」含「万」子串，必须仍判 1e6 而非 1e4
    assert _resolve_multiplier("百万元") == Decimal("1000000")


def test_resolve_multiplier_shiyi_not_confused_by_yi():
    # 「十亿」含「亿」子串，必须仍判 1e9；且补「十亿」无元后缀的现有漏判
    assert _resolve_multiplier("十亿") == Decimal("1000000000")
    assert _resolve_multiplier("十亿元") == Decimal("1000000000")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_money.py -k "multiplier_wan or multiplier_yi or baiwan or shiyi" -v`
Expected: FAIL —「万元」返回 1（旧码无万），「十亿」返回 1（旧码只认「十亿元」）。

- [ ] **Step 3: Write minimal implementation**

替换 `money.py:73-81` 的 `_resolve_multiplier`（注意 if 链顺序：子串大者在前，防误判）：

```python
def _resolve_multiplier(unit: str) -> Decimal:
    normalized = unit.lower()
    if "billion" in normalized or "十亿元" in unit or "十亿" in unit:
        return Decimal("1000000000")
    if "亿元" in unit or "亿" in unit:
        return Decimal("100000000")
    if "million" in normalized or "百万元" in unit or "百万" in unit:
        return Decimal("1000000")
    if "万元" in unit or "万" in unit:
        return Decimal("10000")
    if "thousand" in normalized or "千元" in unit or "千" in unit:
        return Decimal("1000")
    return Decimal("1")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_money.py -v`
Expected: PASS（含现有 money 测试不破）。

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/money.py tests/test_money.py
git commit -m "fix: add 万/亿 multipliers to money normalization, fix 十亿 latent miss"
```

---

## Task 2: money.py 加 `currency_hint` 参数

**Files:**
- Modify: `src/financial_report_llm_extractor/money.py:35-60`
- Test: `tests/test_money.py`

- [ ] **Step 1: Write the failing test**

追加到 `tests/test_money.py`：

```python
from financial_report_llm_extractor.money import normalize_money, MoneyNormalizationError
import pytest


def test_normalize_money_currency_hint_fills_when_unit_has_no_currency():
    # unit "thousand" 无货币标记，靠 currency_hint 兜底
    m = normalize_money("100", unit_context="thousand", currency_hint="CNY")
    assert m.currency == "CNY"
    assert m.normalized_value == Decimal("100000")


def test_normalize_money_unit_currency_overrides_hint():
    # unit 自带货币标记时，优先 unit（"元" → CNY），hint 不改变结果
    m = normalize_money("5", unit_context="万元", currency_hint="USD")
    assert m.currency == "CNY"
    assert m.normalized_value == Decimal("50000")


def test_normalize_money_still_raises_without_hint():
    with pytest.raises(MoneyNormalizationError):
        normalize_money("100", unit_context="thousand")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_money.py -k currency_hint -v`
Expected: FAIL —`normalize_money() got an unexpected keyword argument 'currency_hint'`。

- [ ] **Step 3: Write minimal implementation**

在 `money.py` 顶部 import 加 `cast`：

```python
from typing import cast
```

替换 `resolve_money_unit`（line 35-43）与 `normalize_money`（line 46-60）：

```python
def resolve_money_unit(
    unit_context: str,
    *,
    currency_hint: str | None = None,
) -> tuple[Currency, str, Decimal, Currency]:
    unit = unit_context.strip()
    currency = _resolve_currency(unit)
    if currency in {"unknown", "ambiguous"} and currency_hint in {"CNY", "HKD", "USD"}:
        currency = cast(Currency, currency_hint)
    if currency in {"unknown", "ambiguous"}:
        raise MoneyNormalizationError("currency is ambiguous")
    multiplier = _resolve_multiplier(unit)
    return currency, unit, multiplier, currency


def normalize_money(
    raw_value: str,
    *,
    unit_context: str,
    currency_hint: str | None = None,
) -> MoneyAmount:
    value = parse_numeric_value(raw_value)
    currency, unit, multiplier, normalized_unit = resolve_money_unit(
        unit_context, currency_hint=currency_hint
    )
    money = MoneyAmount(
        value_raw=raw_value,
        value=value,
        currency=currency,
        unit=unit,
        unit_multiplier=multiplier,
        normalized_value=value * multiplier,
        normalized_unit=normalized_unit,
    )
    money.validate()
    return money
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_money.py -v && uv run mypy src/financial_report_llm_extractor/money.py`
Expected: PASS + mypy clean。现有 `normalize_money(...)` 调用（extraction.py:122、mapping.py）不传 hint，行为不变。

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/money.py tests/test_money.py
git commit -m "feat: add currency_hint to normalize_money for unit-only contexts"
```

---

## Task 3: LLM 收口归一化（核心）

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py:706`（`_merge_llm_evidence_supplement`）
- Test: `tests/test_phase_hk_llm_2_supplement_merge.py`

- [ ] **Step 1: Write the failing test**

追加到 `tests/test_phase_hk_llm_2_supplement_merge.py`（沿用该文件已有的 supplement fixture 风格；下方构造一个最小 supplement 直接驱动 `_merge_llm_evidence_supplement`）：

```python
import json
from pathlib import Path
from decimal import Decimal

from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportItem, SourceFirstExportResult,
)
from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
    _merge_llm_evidence_supplement,
)


def _empty_export() -> SourceFirstExportResult:
    return SourceFirstExportResult(items={}, profile="source_only")


def _write_supplement(tmp_path: Path, items: dict) -> Path:
    p = tmp_path / "llm_evidence_supplement.json"
    p.write_text(json.dumps({
        "schema_version": "llm-evidence-supplement-v1",
        "items": items,
    }), encoding="utf-8")
    return p


def test_llm_merge_normalizes_wan_yuan(tmp_path):
    supp = _write_supplement(tmp_path, {
        "stock_based_compensation": {
            "status": "present",
            "parsed_numeric_value": 10080.83,
            "currency": "人民币",
            "unit": "万元",
        }
    })
    merged = _merge_llm_evidence_supplement(_empty_export(), supp)
    item = merged.items["stock_based_compensation"]
    assert item.value == Decimal("10080.83")
    assert item.normalized_value == Decimal("100808300.0")
    assert item.canonical_unit == "CNY"


def test_llm_merge_text_field_does_not_crash(tmp_path):
    supp = _write_supplement(tmp_path, {
        "audit_opinion": {
            "status": "present",
            "parsed_numeric_value": None,
            "value": "标准无保留意见",
            "currency": None,
            "unit": None,
        }
    })
    merged = _merge_llm_evidence_supplement(_empty_export(), supp)
    item = merged.items["audit_opinion"]
    assert item.value is None
    assert item.normalized_value is None
    assert item.canonical_unit is None


def test_llm_merge_yuan_multiplier_one(tmp_path):
    supp = _write_supplement(tmp_path, {
        "dividends_paid": {
            "status": "present",
            "parsed_numeric_value": 929784589.68,
            "currency": "人民币",
            "unit": "元",
        }
    })
    merged = _merge_llm_evidence_supplement(_empty_export(), supp)
    item = merged.items["dividends_paid"]
    assert item.normalized_value == Decimal("929784589.68")
    assert item.canonical_unit == "CNY"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_phase_hk_llm_2_supplement_merge.py -k "normalizes_wan or text_field or yuan_multiplier" -v`
Expected: FAIL —`item.normalized_value` 为 None（收口未实现）。

- [ ] **Step 3: Write minimal implementation**

在 `provider_baseline_replay.py` import 区加：

```python
from financial_report_llm_extractor.money import (
    MoneyNormalizationError,
    normalize_money,
)
```

（`Decimal`、`InvalidOperation` 该文件已 import。）

把 `_merge_llm_evidence_supplement` 中 line 706 的构造块改为：先算归一化，再构造。即在 `new_items[field_id] = SourceFirstExportItem(...)` 之前插入：

```python
        normalized_value: Decimal | None = None
        canonical_unit: Currency | None = None
        if value is not None:
            try:
                money = normalize_money(
                    str(value),
                    unit_context=str(llm_item.get("unit") or ""),
                    currency_hint=currency if currency in {"CNY", "HKD", "USD"} else None,
                )
                normalized_value = money.normalized_value
                canonical_unit = money.normalized_unit
            except (MoneyNormalizationError, ValueError, InvalidOperation):
                normalized_value = None
                canonical_unit = None

        new_items[field_id] = SourceFirstExportItem(
            field_id=field_id,
            status="present",
            value=value,
            normalized_value=normalized_value,
            currency=currency,
            unit=str(llm_item.get("unit")) if llm_item.get("unit") else None,
            canonical_unit=canonical_unit,
            period=str(llm_item.get("period")) if llm_item.get("period") else None,
            review_notes=("llm_supplemented",),
            verification_required=True,
            selected_source="llm",
        )
```

确认文件顶部已 import `Currency`（若无，加 `from financial_report_llm_extractor.models import Currency`）。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_phase_hk_llm_2_supplement_merge.py -v`
Expected: PASS（含该文件原有 merge-pin 测试不破）。

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py tests/test_phase_hk_llm_2_supplement_merge.py
git commit -m "feat: normalize money units at LLM supplement merge funnel"
```

---

## Task 4: evaluation 输出贯通 normalized_value + canonical_unit

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/company_evaluation.py:147-158`（dataclass）、`229-238`（构造）、`568-577`（序列化）
- Test: `tests/test_company_evaluation.py`

- [ ] **Step 1: Write the failing test**

追加到 `tests/test_company_evaluation.py`（沿用现有 `serialize_company_evaluation` 调用风格，断言序列化 dict 含新字段）：

```python
from financial_report_llm_extractor.structured_sources.company_evaluation import (
    CompanyFieldEvaluation,
)


def test_company_field_evaluation_has_normalized_fields():
    f = CompanyFieldEvaluation(
        field_id="x", bucket="llm_supplement_present", selected_source="llm",
        value=None, currency="CNY", unit="万元", reason=None,
        normalized_value=None, canonical_unit="CNY",
    )
    assert f.canonical_unit == "CNY"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_company_evaluation.py -k normalized_fields -v`
Expected: FAIL —`CompanyFieldEvaluation.__init__() got an unexpected keyword argument 'normalized_value'`。

- [ ] **Step 3: Write minimal implementation**

(a) `company_evaluation.py:147-158` dataclass 加两字段（带默认值，置于 `candidate_values` 之前以保持位置参数兼容）：

```python
@dataclass(frozen=True)
class CompanyFieldEvaluation:
    field_id: str
    bucket: BucketName
    selected_source: str | None
    value: Decimal | None
    currency: str | None
    unit: str | None
    reason: str | None
    normalized_value: Decimal | None = None
    canonical_unit: str | None = None
    candidate_values: tuple[tuple[str, str], ...] = ()
```

(b) 构造处 `company_evaluation.py:229-238` 的 `CompanyFieldEvaluation(...)` 加：

```python
        fields.append(CompanyFieldEvaluation(
            field_id=field_id,
            bucket=bucket,
            selected_source=export_item.selected_source,
            value=export_item.value,
            currency=export_item.currency,
            unit=export_item.unit,
            reason=reason,
            normalized_value=export_item.normalized_value,
            canonical_unit=export_item.canonical_unit,
            candidate_values=candidate_values,
        ))
```

(c) 序列化 `company_evaluation.py:568-577` 的 fields dict 加两键：

```python
        "fields": {
            f.field_id: {
                "bucket": f.bucket,
                "selected_source": f.selected_source,
                "value": _format_decimal_plain(f.value) if f.value is not None else None,
                "normalized_value": (
                    _format_decimal_plain(f.normalized_value)
                    if f.normalized_value is not None else None
                ),
                "currency": f.currency,
                "unit": f.unit,
                "canonical_unit": f.canonical_unit,
                "reason": f.reason,
            }
            for f in ev.fields
        },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_company_evaluation.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/company_evaluation.py tests/test_company_evaluation.py
git commit -m "feat: surface normalized_value + canonical_unit in evaluation output"
```

---

## Task 5: DB schema v3 + 迁移检测修复

**Files:**
- Modify: `src/financial_report_llm_extractor/cache/db_schema.py:45-61`、`src/financial_report_llm_extractor/cache/db.py:37-49`
- Test: `tests/test_cache_db.py`

- [ ] **Step 1: Write the failing test**

追加到 `tests/test_cache_db.py`：

```python
import sqlite3
from financial_report_llm_extractor.cache.db import init_db


def test_v2_to_v3_migration_adds_normalized_columns(tmp_path):
    db = tmp_path / "extracted.db"
    # 建一个 v2 schema（有 market，无 normalized_value）
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE field_values ("
        " company TEXT NOT NULL, period_end TEXT NOT NULL, market TEXT NOT NULL,"
        " field_id TEXT NOT NULL, priority TEXT, bucket TEXT NOT NULL,"
        " value TEXT, currency TEXT, unit TEXT, selected_source TEXT, reason TEXT,"
        " evidence_page INTEGER, llm_confidence REAL, llm_reasoning_short TEXT,"
        " PRIMARY KEY (company, period_end, market, field_id));"
    )
    conn.commit()
    conn.close()

    init_db(db)

    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(field_values)")}
    conn.close()
    assert "normalized_value" in cols
    assert "canonical_unit" in cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cache_db.py -k v2_to_v3 -v`
Expected: FAIL —迁移未触发，新列不存在。

- [ ] **Step 3: Write minimal implementation**

(a) `db_schema.py` 的 `CREATE_FIELD_VALUES_TABLE_SQL` 在 `llm_reasoning_short TEXT,` 之后、`PRIMARY KEY` 之前加两列：

```python
  llm_reasoning_short TEXT,
  normalized_value    TEXT,
  canonical_unit      TEXT,
  PRIMARY KEY (company, period_end, market, field_id)
```

(b) `db.py:_is_legacy_schema` 末尾 return 改为：

```python
    column_names = {r[1] for r in rows}  # PRAGMA returns (cid, name, type, ...)
    return "market" not in column_names or "normalized_value" not in column_names
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cache_db.py -v`
Expected: PASS（含现有 v1 迁移测试仍绿）。

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/cache/db_schema.py src/financial_report_llm_extractor/cache/db.py tests/test_cache_db.py
git commit -m "feat: field_values schema v3 (normalized_value, canonical_unit) + migration detect"
```

---

## Task 6: indexer 写入 + db_query 读取往返

**Files:**
- Modify: `src/financial_report_llm_extractor/cache/indexer.py:108-132`（INSERT）、`158-187`（`_merge_field_row` return）、`src/financial_report_llm_extractor/cache/db_query.py:11-15`（`_FIELD_COLUMNS`）、`118-140`（`_decode_field_row`）
- Test: `tests/test_cache_db_query.py`

- [ ] **Step 1: Write the failing test**

追加到 `tests/test_cache_db_query.py`（沿用现有 index→query 往返风格；最小断言 normalized_value 往返）：

```python
def test_normalized_value_roundtrip(tmp_path):
    from financial_report_llm_extractor.cache.db import init_db, connect
    from financial_report_llm_extractor.cache.db_query import query_field

    db = tmp_path / "extracted.db"
    init_db(db)
    conn = connect(db)
    conn.execute(
        "INSERT INTO field_values (company, period_end, market, field_id, priority,"
        " bucket, value, currency, unit, selected_source, reason, evidence_page,"
        " llm_confidence, llm_reasoning_short, normalized_value, canonical_unit)"
        " VALUES ('603345','2024-12-31','CN','sbc','P3','llm_supplement_present',"
        " '\"10080.83\"','CNY','万元','llm',NULL,NULL,NULL,NULL,'100808300','CNY')"
    )
    conn.commit()
    conn.close()

    row = query_field(db_path=db, company="603345", period_end="2024-12-31",
                      market="CN", field_id="sbc")
    assert row["normalized_value"] == "100808300"
    assert row["canonical_unit"] == "CNY"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cache_db_query.py -k normalized_value_roundtrip -v`
Expected: FAIL —`_decode_field_row` 解包列数不匹配 / KeyError。

- [ ] **Step 3: Write minimal implementation**

(a) `indexer.py` INSERT（line ~114-130）列名 + 占位符 + values 元组各加两项（末尾）：

```python
                INSERT INTO field_values (
                  company, period_end, market, field_id, priority, bucket, value,
                  currency, unit, selected_source, reason,
                  evidence_page, llm_confidence, llm_reasoning_short,
                  normalized_value, canonical_unit
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company, period_end, market, field_id,
                    priority_map.get(field_id),
                    bucket,
                    row["value"],
                    row["currency"],
                    row["unit"],
                    row["selected_source"],
                    row["reason"],
                    row["evidence_page"],
                    row["llm_confidence"],
                    row["llm_reasoning_short"],
                    row["normalized_value"],
                    row["canonical_unit"],
                ),
```

(b) `indexer.py:_merge_field_row` 的 return dict 加两键（取 eval_info；normalized_value 在 evaluation.json field 里已是字符串或 None）：

```python
        "llm_reasoning_short": _truncate(reasoning, 500),
        "normalized_value": eval_info.get("normalized_value"),
        "canonical_unit": eval_info.get("canonical_unit"),
    }
```

(c) `db_query.py:_FIELD_COLUMNS`（line 11-15）末尾加两列：

```python
_FIELD_COLUMNS = (
    "bucket", "value", "currency", "unit", "selected_source",
    "reason", "evidence_page", "llm_confidence", "llm_reasoning_short",
    "priority", "normalized_value", "canonical_unit",
)
```

(d) `db_query.py:_decode_field_row`（line 126-140）解包 + dict 同步：

```python
    (bucket, value_text, currency, unit, selected_source, reason,
     evidence_page, llm_confidence, llm_reasoning_short, priority,
     normalized_value, canonical_unit) = row
    return {
        "company": company,
        "period_end": period_end,
        "market": market,
        "field_id": field_id,
        "priority": priority,
        "bucket": bucket,
        "value": json.loads(value_text) if value_text is not None else None,
        "currency": currency,
        "unit": unit,
        "selected_source": selected_source,
        "reason": reason,
        "evidence_page": evidence_page,
        "llm_confidence": llm_confidence,
        "llm_reasoning_short": llm_reasoning_short,
        "normalized_value": normalized_value,
        "canonical_unit": canonical_unit,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cache_db_query.py tests/test_cache_indexer.py -v`
Expected: PASS（indexer 与 query 往返一致）。

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/cache/indexer.py src/financial_report_llm_extractor/cache/db_query.py tests/test_cache_db_query.py
git commit -m "feat: persist + read normalized_value/canonical_unit through DB"
```

---

## Task 7: 公共 API FieldValue 暴露归一化字段

**Files:**
- Modify: `src/financial_report_llm_extractor/client.py:115-117`（dataclass）、`701-711`（`build_field_value` 主路径）
- Test: `tests/test_client.py`

- [ ] **Step 1: Write the failing test**

追加到 `tests/test_client.py`（沿用现有 `build_field_value` 直测风格；若无则构造最小 db_row + taxonomy）：

```python
from decimal import Decimal
from financial_report_llm_extractor.client import build_field_value


def testbuild_field_value_carries_normalized():
    db_row = {
        "bucket": "llm_supplement_present", "value": "10080.83",
        "currency": "CNY", "unit": "万元", "selected_source": "llm",
        "evidence_page": None, "reason": None,
        "normalized_value": "100808300", "canonical_unit": "CNY",
    }
    fv = build_field_value(
        field_id="sbc", db_row=db_row,
        field_taxonomy={"value_type": "money"},
        include_llm_supplement=True,
    )
    assert fv.normalized_value == Decimal("100808300")
    assert fv.canonical_unit == "CNY"
```

（注：若 `build_field_value` 签名不同，按实际签名调用；核心断言不变。）

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_client.py -k carries_normalized -v`
Expected: FAIL —`FieldValue` 无 `normalized_value` 属性。

- [ ] **Step 3: Write minimal implementation**

(a) `client.py` `FieldValue` dataclass（line 115-117 区，`reason` 之后）加两字段（带默认值，使 line 524、670 两个兜底构造无需改）：

```python
    raw_bucket: str
    reason: str | None = None
    normalized_value: Decimal | None = None
    canonical_unit: str | None = None
```

(b) `client.py:build_field_value` 主路径 return（line 704-711）加两字段（normalized_value 用 Decimal 解码保精度）：

```python
    normalized_raw = db_row.get("normalized_value")
    normalized_value = (
        Decimal(str(normalized_raw)) if normalized_raw is not None else None
    )

    return FieldValue(
        field_id=field_id,
        value=value,
        currency=currency,
        unit=db_row.get("unit"),
        confidence=confidence,
        source=db_row.get("selected_source"),
        evidence_page=db_row.get("evidence_page"),
        raw_bucket=raw_bucket,
        reason=db_row.get("reason"),
        normalized_value=normalized_value,
        canonical_unit=db_row.get("canonical_unit"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_client.py -v`
Expected: PASS（line 524、670 兜底构造因默认值不破）。

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/client.py tests/test_client.py
git commit -m "feat: expose normalized_value + canonical_unit on public FieldValue"
```

---

## Task 8: 全量回归 + 603345/2024 端到端验证

**Files:**
- 无源码改动（验证 task）

- [ ] **Step 1: 全量门禁**

Run: `uv run pytest -v && uv run ruff check . && uv run mypy src tests`
Expected: 全 PASS。若 mypy 报 `currency_hint`/`cast` 类型问题，按报错修至 clean 再继续。

- [ ] **Step 2: 重建 DB（schema v3 全量重 index）**

```bash
rm -f data/extracted.db
set -a && source .env && set +a
uv run financial-report-llm-extractor index --runs tmp/runs --db data/extracted.db
```

Expected: index 成功，无 stderr schema 警告。

- [ ] **Step 3: 端到端断言关键字段归一化值**

Run:
```bash
uv run financial-report-llm-extractor query --company 603345 --period-end 2024-12-31 --market CN --field stock_based_compensation --db data/extracted.db
```
Expected: 输出 JSON 含 `"normalized_value": "100808300..."`、`"canonical_unit": "CNY"`（不再是 raw `10080.83 万元`）。

- [ ] **Step 4: 抽查 evaluation.json**

Run:
```bash
python3 -c "import json; d=json.load(open('tmp/runs/603345_2024/evaluation.json')); f=d['fields']['stock_based_compensation']; print(f.get('normalized_value'), f.get('canonical_unit'))"
```
注：现有 `tmp/runs/603345_2024/evaluation.json` 是旧 run（无新字段）。如需刷新，重跑：
```bash
set -a && source .env && set +a
uv run financial-report-llm-extractor pipeline --company 603345 --market CN --year 2024 \
  --pdf downloads/cn_stocks/603345/annual/2024_年度报告.pdf \
  --llm-config tmp/llm_configs/openai_gateway.json --out tmp/runs/603345_2024 --db data/extracted.db --force
```
Expected: `100808300... CNY`。

- [ ] **Step 5: Commit（验证记录，可选）**

```bash
git commit --allow-empty -m "test: e2e verify money normalization on 603345/2024"
```

---

## 自审记录

- **Spec 覆盖**：六处隐患 → Task1(词表)、Task2(currency_hint)、Task3(收口/隐患2)、Task4-7(输出三层/隐患4)、Task5(迁移)。隐患5(不变量) 由 Task3 走 `normalize_money` 内部 `validate()` 保证；隐患6(下游 raw unit) 由 Task4-7 贯通解决。
- **改动清单 8 落点**：1→T1/T2，3a→T3，4a→T4，4b/4c→T5，4d→T6(写)，4e→T6(读)，4f→T7。全覆盖。
- **类型一致**：`normalized_value: Decimal|None`、`canonical_unit: str|None` 跨 Task4/6/7 一致；DB 存 TEXT、client 用 `Decimal(str(...))` 解码保精度。
- **边界**：dps(T1 测 `0.5 元`→0.5)、十亿漏判(T1)、text 字段不炸(T3)、v2→v3 迁移(T5)、兜底构造默认值(T7)。
