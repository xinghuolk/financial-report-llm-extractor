# 单位归一化统一收口（Money Unit Normalization Funnel）设计

- 日期：2026-06-17
- 状态：设计已批准 → 经 subagent review 修订（收口点重定位 + 迁移检测修复 + 改动清单补全），待用户复审
- 分支：`feat/money-unit-normalization-funnel`
- 触发：603345/2024 抽取暴露 LLM 路径 money 字段单位未归一化（`stock_based_compensation` 报 `value=10080.83 unit=万元`，下游误读为 10080.83 元，错 10000 倍）

## 修订记录（2026-06-17 subagent review）

初版把收口点定在 `export.py:_build_item`。review 核实发现：**LLM supplement 字段不经过 `_build_item`**——它走 `provider_baseline_replay._merge_llm_evidence_supplement`（在 `build_source_first_export` 之后独立 merge，line 706 单独构造 `SourceFirstExportItem`）。全仓仅 3 个构造点：`export.py:321`（provider）、`provider_baseline_replay.py:706`（LLM）、`company_evaluation.py:257`（missing 占位）。故收口点重定位到 706 行。另修订：DB 迁移检测器（v2→v3 不触发）、改动清单补 `indexer.py` 写入侧与 db_query/client 位置耦合点、补 dps per-share money 边界。

## 1. 问题陈述

项目存在 `normalize_money()` 统一归一化机制（`money.py`），且 `extraction.py` 路径正确调用它。但实际主力的 LLM 抽取路径绕过了它，导致全仓单位混用。全仓扫描确认六处隐患：

1. **三套来源词表并存，无统一 canonical**：akshare=`yuan`（经 `_normalize_source_unit`）、yahoo=`raw`、LLM=`元/万元/thousand/million`（透传 PDF 原词）。
2. **两条 money 路径只接了一条归一化**：`extraction.py:122` 调 `normalize_money()` ✅；`llm_field_extraction.py:264` 纯透传（`unit=_str_or_none(raw.get("unit"))`）❌。后者是 HK notes-level + 当前 CN 抽取的主力路径。
3. **`money.py._resolve_multiplier` 词表不全**：有 `百万/million`、`千/thousand`、`十亿/billion`，**缺中国财报最常用的「万元/万」和「亿元/亿」**。即便接上 `normalize_money`，万元也会落到乘数 1。
4. **schema 完备但输出层丢弃**：`SourceFirstExportItem` 有 `normalized_value` + `canonical_unit` 字段并在 `to_dict` 输出，但 `company_evaluation.py:234` 构造的 evaluation field 只暴露 raw `value`/`unit`，丢弃了归一化值。
5. **MoneyAmount 不变量未在 LLM 路径强制**：`models.py:71-75` 规定 `normalized_value == value × unit_multiplier` 且 `normalized_unit == currency`；`extraction.py` 强校验，LLM 路径不构造 MoneyAmount，绕过不变量。
6. **下游消费 raw unit 做判断**：消费方（含公共 API client）拿 raw `unit` 判定，遇到 `元/万元/raw` 报 "unsupported unit → display-only"。

**根因一句话**：统一归一化机制早已存在，但 LLM 主力路径绕过了它，且其乘数词表漏了中文「万/亿」。

## 2. 目标与非目标

### 目标
- 建立**单一归一化收口**：所有来源（akshare/yahoo/LLM）× 全市场（CNY/HKD/USD）× 全单位（千/万/百万/亿）汇流到一处归一化，物理上杜绝绕过。
- 修复 `money.py` 乘数词表缺口（万/亿）。
- 把 `normalized_value` + `canonical_unit` 贯通到输出三层（evaluation.json field / DB / 公共 API），下游只读 `normalized_value`，永不解析 raw unit。
- raw `value`/`unit` 始终保留作审计可溯源。

### 非目标
- **不做跨币种汇率换算**。`normalized_value` 是同币种内的绝对值，`canonical_unit` 保留货币码。
- **不强制重跑历史 run**。逻辑改动后，旧 run 的归一化值由 operator 决定是否重 index（tmp/runs 是 source of truth，重读无 LLM 成本）。
- **不引入治理/校验 gate**（已批方案 B，非 C）。收口兜底即机制，不额外加"强制所有新字段过归一化"的护栏层。

## 3. 方案（方案 B · 单点收口兜底，收口点经 review 重定位）

money 字段有两条独立构造路径，各自收口（合起来覆盖所有 present money 字段）：

- **provider 路径**：`mapping.py:490` `_candidate_from_record` 已调 `normalize_money` 算好 `normalized_value`/`canonical_unit`，经 reconciliation 流到 `export.py:_build_item`（line 321 构造）。**本就归一化，无需改**（仅作幂等保证）。
- **LLM supplement 路径**：`provider_baseline_replay.py:_merge_llm_evidence_supplement`（line 706）独立构造 `SourceFirstExportItem`，**当前不传 `normalized_value`**。这是漏算的唯一来源，也是真正的收口点。

在 line 706 构造 LLM item 时（此处已持有 `value`(parsed Decimal)、`currency`、`unit`），插入收口兜底：

> 若 `value is not None` → 尝试
> `normalize_money(str(value), unit_context=unit or "", currency_hint=currency)`，
> 成功则填 `normalized_value = m.normalized_value`、`canonical_unit = m.normalized_unit`；
> 失败（货币/单位无法解析，如 text 字段）则捕获异常、保持 None。
> text 字段（audit_opinion 等）`value` 本就为 None（`Decimal(文本)` raise → value=None），天然不进收口。

### 改动清单（一处定义、全局生效）

| # | 文件 | 改动 | 性质 |
|---|------|------|------|
| 1 | `money.py._resolve_multiplier` | 补「万元/万」→`10000`、「亿元/亿」→`100000000`；保持 if 链顺序防误判 | 修致命词表缺口 |
| 2 | `money.py.normalize_money` / `resolve_money_unit` | 加可选 `currency_hint` 参数：unit 无货币标记时用它（兜底 HK `thousand`） | 增强 |
| 3 | `provider_baseline_replay.py:_merge_llm_evidence_supplement` | line 706 LLM item 构造处插入收口归一化（**经 review 重定位，非 `export._build_item`**） | 核心 |
| 4a | `company_evaluation.py` | evaluation field 输出（line 232-236 区）加 `normalized_value`/`canonical_unit` | 贯通下游 |
| 4b | `cache/db_schema.py` | `field_values` 加 `normalized_value TEXT` + `canonical_unit TEXT`（schema v3）| 贯通下游 |
| 4c | `cache/db.py:_is_legacy_schema` | **增检 `normalized_value not in column_names`**（否则 v2→v3 不触发 drop，新列永不创建）| 修迁移检测 |
| 4d | `cache/indexer.py:_merge_field_row` | 取 `eval_info` 的 `normalized_value`/`canonical_unit` + INSERT 列/占位符 +2（位置耦合，遗漏则写入 NULL）| 贯通下游·写入侧 |
| 4e | `cache/db_query.py` | `_FIELD_COLUMNS` 元组 + `_decode_field_row` 位置解包同步加 2 列 | 贯通下游·读取侧 |
| 4f | `client.py` | `FieldValue` dataclass 加 2 字段（**带 `= None` 默认值**，避免 line 525 兜底构造缺参）+ `_build_field_value`（line 701）从 db_row 映射 | 贯通下游·公共 API |

## 4. 数据流

```
provider 路径：
① akshare ─→ mapping._candidate_from_record 调 normalize_money(yuan,×1) ─┐
② yahoo   ─→ 同上(raw,×1) ───────────────────────────────────────────────┤→ _build_item
            （normalized_value 在 mapping 阶段已非 None）                   │  (export.py:321)
                                                                            │  幂等，无需改
LLM 路径（独立 merge，在 build_source_first_export 之后）：
③ LLM supplement ─→ _merge_llm_evidence_supplement (provider_baseline_replay.py)
                     line 706 构造 SourceFirstExportItem：
                       value    = Decimal(parsed_numeric_value)   # 已有
                       currency = _normalize_llm_currency(...)     # 已有
                       unit     = "万元"                            # 已有
                     ┌─── 收口归一化（新增，构造时）───────────────────┐
                     │ normalized_value = canonical_unit = None        │
                     │ if value is not None:                           │
                     │   try:                                          │
                     │     m = normalize_money(str(value),            │
                     │           unit_context=unit or "",             │
                     │           currency_hint=currency)              │
                     │     normalized_value = m.normalized_value      │
                     │     canonical_unit   = m.normalized_unit       │
                     │   except (MoneyNormalizationError,             │
                     │           ValueError, InvalidOperation):       │
                     │     pass   # text 字段 value 本就 None，不进此块 │
                     └────────────────────────────────────────────────┘
                                                │
        两路汇合：SourceFirstExportItem{value, unit,        ← raw 保留(审计)
                                        normalized_value,    ← 全来源统一有值
                                        canonical_unit}
                                                │
                  evaluation.json field  ─┬─  DB field_values 列  ─┬─  client FieldValue
                  (company_evaluation 4a)    (indexer 4d 写 / db_query 4e 读)   (client 4f)
                  +normalized_value          +normalized_value(v3 列, 4b+4c)    +normalized_value
                  +canonical_unit            +canonical_unit                    +canonical_unit
                                                │
                        下游只读 normalized_value + canonical_unit
                        （"unsupported unit" 消失）
```

`stock_based_compensation` 示例：706 行收口前 `value=10080.83, unit=万元` → 收口后 `normalized_value=100808300, canonical_unit=CNY`。

## 5. 边界 case

收口兜底用 **try/except 而非精确 money 类型判定**，自动豁免非货币字段。

| 边界 | 处理 |
|------|------|
| money 类型判定 | 不靠 value_type；对 `normalized_value is None & value is not None` 尝试 `normalize_money`，货币无法解析则 raise → 捕获跳过保持 None。text/ratio/shares（unit 无货币标记）自然豁免 |
| `百万` 被 `万` 误判 | `_resolve_multiplier` if 链顺序：`十亿/billion` → `亿` → `百万/million` → `万` → `千/thousand`。"百万元" 在 `万` 之前命中 1e6；"十亿" 在 `亿` 之前命中 1e9 |
| HK LLM 报纯 `thousand`（无货币词） | `currency_hint=candidate.currency` 兜底；unit 有货币标记时仍优先 unit |
| yahoo `raw` / provider 已算 | `normalized_value` 非 None → 收口幂等跳过，绝不覆盖 |
| 负值（回购/分红现金流出） | `value × multiplier` 保号，`MoneyAmount.validate` 允许负 |
| 不变量保证 | 走 `normalize_money` → 内部 `MoneyAmount.validate()`：`normalized_value==value×multiplier` 且 `normalized_unit∈{CNY,HKD,USD}==currency` |
| 异常捕获范围 | `(MoneyNormalizationError, ValueError, InvalidOperation)` → 跳过 + 记 warning，绝不让收口炸掉整个 export |
| **dps（per-share money）** | `dps.value_type=money`，是每股小数额（如「0.5 元/股」）。收口对它 `normalize_money("0.5", unit_context="元...")` → CNY、×1 → `normalized_value=0.5`，**正确**。风险：若 LLM 误把整表「万元」语境标到 per-share unit，收口会忠实放大 1e4——这是 LLM 抽取错误被放大，非收口缺陷。预期行为：per-share 字段 unit 应只含「元/股」不含「万元」；测试覆盖 `0.5 元` → 0.5 不被乘万 |

### `_resolve_multiplier` 目标实现（if 链顺序）

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

注意：`十亿` 必须在 `亿` 之前、`百万` 必须在 `万` 之前判断（子串包含关系）。

## 6. DB schema 迁移（v3）

`field_values` 表加 `normalized_value TEXT` + `canonical_unit TEXT` 两列 = schema v3。

**关键修复（review 阻断项 2）**：现有 `db.py:_is_legacy_schema` 只检 `"market" not in column_names`，对已有 market 列的 v2 库**不会触发** drop，而 `CREATE TABLE IF NOT EXISTS` 对已存在表是 no-op → 新列永不创建，后续 indexer INSERT 会因列不存在 `OperationalError`。必须把检测改为：

```python
def _is_legacy_schema(db_path: Path) -> bool:
    ...
    column_names = {r[1] for r in rows}
    # v1 缺 market；v3 之前缺 normalized_value —— 任一缺失都视为旧 schema
    return "market" not in column_names or "normalized_value" not in column_names
```

沿用 R5 先例：检测到旧 schema → drop + recreate。operator 须 `rm data/extracted.db && financial-report-llm-extractor index --runs tmp/runs ...` 全量重 index。重读 tmp/runs 无 LLM 成本。

## 7. 测试策略（TDD）

| 层 | 测试 |
|----|------|
| `money.py` 单元 | 「万元/万」→1e4、「亿元/亿」→1e8、**「百万元」仍→1e6**、**「十亿」→1e9（含现有漏判：旧码只认「十亿元」不认「十亿」）**、`currency_hint` 兜底 `thousand`、`unknown` 仍 raise、负值保号、`0.5 元`→0.5（dps 不被乘万） |
| `_merge_llm_evidence_supplement` 收口 | LLM item(`unit=万元,value=10080.83`)→ 构造后 `normalized_value=100808300,canonical_unit=CNY`；text 字段(value=None)→ 不进收口、保持 None 不炸；provider 路径不受影响（不经此函数） |
| 输出三层 | evaluation.json field 含 `normalized_value`/`canonical_unit`；indexer 写入 + db_query 读取往返一致；client `FieldValue` 含字段且 line 525 兜底构造不破 |
| DB 迁移 | **v2 schema（有 market、无 normalized_value）→ init_db → 断言 normalized_value 列出现**（防阻断项 2 复发）；v1→v3 仍触发 drop |
| 回归 | 全量 `uv run pytest -v` + `ruff check .` + `mypy src tests` 不破；`test_catalog_consistency`、`test_cache_*` 等 gate 绿 |
| 端到端 | 重跑 603345/2024：确认 `stock_based_compensation` normalized_value=100808300、`dividends_paid`/`acct_payable`/`repurchase_of_stock` 等 LLM 字段都有 normalized_value + canonical_unit |

## 8. 验收标准

1. `money.py` 支持万/亿，且不误判百万/十亿。
2. LLM 路径 money 字段（经 `_merge_llm_evidence_supplement:706` 收口）在 evaluation 输出有正确 `normalized_value` + `canonical_unit`。
3. provider 路径归一化值不被改变（provider 不经 706 收口，天然幂等）。
4. text/ratio/shares 字段不被错误归一化、收口不抛异常。
5. 输出三层（evaluation.json / DB / 公共 API）均暴露两字段；indexer 写入侧已同步。
6. DB v2→v3 迁移可触发（`_is_legacy_schema` 增检 normalized_value 列）。
7. 全量 pytest/ruff/mypy 通过。
8. 603345/2024 重跑端到端验证通过。
