# 下游迁移说明：money 字段单位归一化（normalized_value / canonical_unit）

- 日期：2026-06-18
- 关联 PR：#25 `feat/money-unit-normalization-funnel`
- 受众：消费 `financial-report-llm-extractor` 输出的下游（TradingAgents-CN 等）
- spec：`docs/superpowers/specs/2026-06-17-money-unit-normalization-funnel-design.md`

## TL;DR（下游必读）

1. **三层输出（evaluation.json / DB / 公共 API `FieldValue`）各新增两个字段：`normalized_value` 和 `canonical_unit`。** 原有 `value`/`unit`/`currency` 全部保留，向后兼容。
2. **下游做金额计算/比较时，改为读 `normalized_value`（已按单位乘数换算成基础货币绝对值）+ `canonical_unit`（标准货币码 CNY/HKD/USD），不要再自己解析 raw `unit`。**
3. 之前 LLM 抽取的 money 字段（如 `stock_based_compensation`）`value=10080.83 unit=万元` 会被下游误读成 10080.83 元（**错 10000 倍**）；现在 `normalized_value=100808300` 是正确的绝对值。
4. **迁移动作**：升级后须 `rm data/extracted.db` 重建（schema v3）；历史 run 须**重跑 pipeline** 才能拿到 normalized_value（仅 re-index 不回填，详见末节）。

---

## 1. 为什么变

LLM 路径抽取的 money 字段直接返回 PDF 原始单位词（`万元`/`元`/`千港元` 等）放进 `unit`，但**没有归一化值**。下游若按 `value` 直接使用、或自己解析 `unit`，会踩两个坑：

- **单位倍数**：`万元`/`千元` 等没被换算，`value=10080.83 unit=万元` 实际是 1.008 亿元。
- **货币误判**：`港元`/`美元` 含「元」字，旧逻辑误判成 CNY。

本次修复在抽取管线收口统一调归一化，并把结果贯通到所有输出层。

---

## 2. 三层输出 Schema 变化

三层都是**新增字段、不删不改原字段**。

### 2.1 `evaluation.json` 的 `fields[<field_id>]`

| 字段 | 变化 | 说明 |
|------|------|------|
| `value` | 不变 | raw 数值（字符串），如 `"10080.83"` |
| `unit` | 不变 | raw 单位词，如 `"万元"` |
| `currency` | 不变 | raw 货币词，可能是 `"人民币"` 等非标准写法 |
| **`normalized_value`** | **新增** | 按单位乘数换算后的绝对值（字符串，定点无科学计数法），如 `"100808300.00"`；text/无值/不可归一化时为 `null` |
| **`canonical_unit`** | **新增** | 标准货币码 `"CNY"`/`"HKD"`/`"USD"`；不可归一化时 `null` |

before（旧）：
```json
"stock_based_compensation": {
  "bucket": "llm_supplement_present",
  "value": "10080.83", "currency": "人民币", "unit": "万元", "reason": null
}
```
after（新）：
```json
"stock_based_compensation": {
  "bucket": "llm_supplement_present",
  "value": "10080.83", "normalized_value": "100808300.00",
  "currency": "人民币", "unit": "万元", "canonical_unit": "CNY", "reason": null
}
```

### 2.2 DB `field_values` 表 / `query` 命令输出

`field_values` 表新增两列 `normalized_value TEXT` + `canonical_unit TEXT`（**schema v3**）。`query` / `query_extraction` 返回的 dict 同步新增这两键。

`query --company 603345 --period 2024-12-31 --market CN --field stock_based_compensation` 输出：
```json
{
  "field_id": "stock_based_compensation",
  "bucket": "llm_supplement_present",
  "value": "10080.83",
  "normalized_value": "100808300.00",
  "currency": "人民币",
  "unit": "万元",
  "canonical_unit": "CNY",
  "selected_source": "llm",
  "evidence_page": 226,
  "llm_confidence": 0.86,
  "priority": "P2",
  ...
}
```

> ⚠️ `query` 命令的参数是 `--period`（不是 `--period-end`）。

### 2.3 公共 API `client.FieldValue`

`FieldValue` dataclass 新增两个字段（带默认值，向后兼容）：

```python
@dataclass(frozen=True)
class FieldValue:
    field_id: str
    value: Decimal | str | bool | None       # 不变：money/number=Decimal, text=str
    currency: str | None                     # 不变：raw 货币（可能是「人民币」）
    unit: str | None                         # 不变：raw 单位（如「万元」）
    confidence: ConfidenceLevel
    source: str | None
    evidence_page: int | None
    raw_bucket: str
    reason: str | None = None
    normalized_value: Decimal | None = None  # 新增：归一化绝对值（Decimal）
    canonical_unit: str | None = None        # 新增：标准货币码 CNY/HKD/USD
```

- `value` 对 money 字段仍是 raw 数值的 Decimal（如 `Decimal("10080.83")`）。
- `normalized_value` 是换算后的绝对值 Decimal（如 `Decimal("100808300.00")`）。
- `canonical_unit` 是标准货币码。
- 守护：当 `value is None` 时，`normalized_value` 与 `canonical_unit` 也对称为 `None`。

---

## 3. 值的变化（升级前后对照）

| 字段 | 升级前（下游所见） | 升级后 |
|------|------|------|
| `stock_based_compensation` | `value=10080.83 unit=万元`，无归一化 → 易误读为 1.008万 | `normalized_value=100808300.00 canonical_unit=CNY`（**1.008 亿，修正 10000 倍**）|
| `dividends_paid` | `value=929784589.68 unit=元` | `normalized_value=929784589.68 canonical_unit=CNY`（乘数 1，值同，但现在有标准字段）|
| HK 公司 money 字段（`unit=港元/美元`）| `canonical_unit` 旧逻辑会错标 CNY | 正确为 `HKD`/`USD` |

**单位乘数表**（`normalized_value = value × 乘数`）：千/千元=1e3、万/万元=1e4、百万/百万元=1e6、亿/亿元=1e8、十亿=1e9、百亿=1e10、千亿=1e11、万亿=1e12。

---

## 4. 下游应如何修改

### 行动项

1. **金额消费切换到 `normalized_value`**：所有需要"实际金额数值"的地方（计算、比较、入库、画图），从 `value` 改读 `normalized_value`。`value`/`unit` 仅作展示/审计。
2. **货币判断切换到 `canonical_unit`**：需要货币码时读 `canonical_unit`（标准 CNY/HKD/USD），不要用 `currency`（可能是「人民币」等 raw 写法），也不要自己解析 `unit`。
3. **处理 `None`**：`normalized_value=None` 表示无法归一化（text 字段、无值、或归一化失败）——这类字段不应参与数值计算。

### 代码示例（伪代码）

before：
```python
# ❌ 旧：直接用 value，自己猜单位 → 漏算万元/误判港元
amount = fv.value
if fv.unit == "万元":
    amount *= 10000   # 容易漏；港元/美元更会错
```

after：
```python
# ✅ 新：直接用归一化字段
if fv.normalized_value is not None:
    amount = fv.normalized_value          # 已是基础货币绝对值
    ccy = fv.canonical_unit               # "CNY" / "HKD" / "USD"
else:
    amount = None                         # text/无值/不可归一化，不参与计算
```

> 注意：`normalized_value` **不做跨币种汇率换算**——它是同币种内的绝对值，币种由 `canonical_unit` 标识。跨币种比较仍需下游自行处理汇率。

---

## 5. 迁移步骤

### 5.1 DB schema v3

`field_values` 加两列 = schema v3。升级后首次访问会自动检测旧 schema → drop + recreate。**operator 须重建并重新索引**：

```bash
rm data/extracted.db
financial-report-llm-extractor index --runs tmp/runs --db data/extracted.db ...
```

### 5.2 历史 run 须重跑（重要）

⚠️ **仅 `rm db && index` 不足以修复历史数据**：本 PR 之前生成的 `evaluation.json` 没有 `normalized_value` 键，indexer 不做归一化兜底（保持归一化单一收口点 + DB 忠实索引 evaluation.json），re-index 旧 run 只会写 `NULL`。

indexer 在检测到 `llm_supplement_present` 行缺 `normalized_value` 时会向 stderr 打 warning 提示。正确做法：**重跑 pipeline 重新生成 `evaluation.json`**（LLM cache 命中近乎免费），再 index：

```bash
financial-report-llm-extractor pipeline --company <id> --market <CN|HK> --year <yyyy> \
  --pdf <path> --llm-config <config> --out tmp/runs/<...> --db data/extracted.db --force
```

---

## 6. 边界与已知限制

- **per-share money（如 dps 每股股利）**：`unit=元/股`，乘数 1，`normalized_value` 即每股绝对值（如 0.5），不会被乘万。
- **归一化失败**：会在该 export item 的 `warnings` 里记 `"normalize_money_failed"`，`normalized_value`/`canonical_unit` 为 None。
- **非 CNY/HKD/USD 外币**（欧元/日元等）：当前不在支持范围，`canonical_unit` 可能为 CNY 或 unknown——这些币种不在数据收集范围内，下游遇到应按 None/不可信处理。
- `value`/`unit`/`currency` 三个 raw 字段**永久保留**用于审计溯源，不会移除。
