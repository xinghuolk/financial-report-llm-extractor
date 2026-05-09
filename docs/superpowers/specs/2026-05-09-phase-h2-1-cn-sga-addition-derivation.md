# Phase H2.1: CN SGA Addition Derivation Spec

> 日期：2026-05-09
> 状态：Draft
> 前置：Phase H2 已完成（commits 1428281 → 7ede65e → 4847998）。CN SGA 当前 terminal_unverified 因 catalog `derivation` 字段只支持 `A - B` 减法。
> 触发：Phase H2 留下的明确 follow-up — 解锁 CN SGA promotion via `MANAGE_EXPENSE + SALE_EXPENSE`。

## 目标

扩展 catalog `derivation` 语法支持加法 + raw provider 字段引用，使 CN `selling_general_administrative` 能从 AKShare 两个 raw 字段求和得到。Promotion gate 沿用 H2 标准：**AKShare derivation 值 = PDF SGA 实际值 EXACT**。

## Non-Goals

- 不引入 tolerance-based promotion gate（drift §177 sampled-PDF-not-final-evidence 警告 + 用户明确 push back）。
- 不动 HK SGA（H2 已锁 terminal_unverified；Yahoo SGA scope ambiguity 不归 H2.1 解决）。
- 不重写 mapping 整体架构 —— 仅扩展 `_derive_field` parser。
- 不引入多公司 sample-verified（单样本起步，与 H2 一致；多公司扩展归 Phase H2.2 候选）。

## 机制（最小改动）

### `derivation` 语法扩展

当前（mapping.py:251-258）：
```python
parts = entry.derivation.split()
if len(parts) != 3 or parts[1] != "-":
    return MappedTurtleField(status="blocked", errors=("unsupported derivation",))
left = mapped.get(parts[0])
right = mapped.get(parts[2])
```

扩展后：
- `parts[1]` ∈ `{"-", "+"}` —— 加法 + 减法都接受
- 操作数：除了 Turtle field ID（lookup `mapped[parts[0]]`），还接受 `provider:RAW_FIELD_NAME` 形式（lookup raw value 直接从 source records）

示例 derivation：
- `"gross_profit - operating_cost"` —— 现有 Turtle - Turtle 减法（不变）
- `"akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE"` —— **NEW** raw provider 加法
- 不支持混搭：左右两侧若为 raw provider 引用，**必须同 provider**（避免 cross-provider sum 的语义混乱）

### Raw provider operand 解析

当 operand 形如 `provider:RAW`，`_derive_field` 需要：
1. 从 records（`SourceInventoryRecord` tuple）中找出 `(source==provider) AND (raw_field_name==RAW)` 且 `source_status=="present"` 的记录
2. 取其 `parsed_numeric_value`，currency, unit, source_evidence
3. 与另一 operand 同样处理后做求和/减
4. 输出 derived `MappedTurtleField` with `status="derived"`

如果 raw 字段不存在或多于一条 → `status="blocked"` with 明确错误。
如果两 operand currency / unit 不一致 → 沿用现有 `derivation inputs use different currencies` 检查。

### 接线
`_derive_field` 当前签名是 `(entry, mapped) -> MappedTurtleField`。需扩展为 `(entry, mapped, records) -> MappedTurtleField` 以便访问 raw inventory。`map_source_inventory` 已经有 `records` 在作用域中，传入即可。

## 适用范围（H2.1 阶段）

仅 `selling_general_administrative` 在 CN：
```jsonc
"selling_general_administrative": {
  ...
  "derivation": "akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE"
}
```

注意：`derivation` 是 catalog 顶层字段（不在 `source_policy.market_policies.<MARKET>` 里）。当前 catalog 是 market-agnostic 的 derivation。这意味着：
- 解锁 derivation 后，HK SGA 也会尝试同样的 derivation
- 但 HK AKShare 没有 SALE_EXPENSE / MANAGE_EXPENSE raw 字段（H2 已确认 HK fixture）→ derivation `blocked` → fallback 到现有 unresolved
- 实际 effect: 仅 CN 受益

## PDF spot-check 决策树

实施 commit 3 时：
```
spot-check 600519/2024 PDF 中 SGA 实际值
    │
    ├─ AKShare MANAGE+SALE EXACT match PDF SGA?
    │   ├─ Yes → commit 4: provider_semantics_sample_verified rule + market_policies promote → clean_present ✓
    │   └─ No  → commit 4: 保留 derivation 实现，仍 terminal_unverified；rule 记录"derivation 实现完毕但 sample 未 verified"
    │
    └─ 都不匹配 → 维持 H2 现状；新机制只是基础设施
```

## 5 commits 拆分

| Commit | 主题 | LoC | 关键测试 |
|--------|------|----:|----------|
| 1 | feat: derivation `+` 运算符支持（仍 Turtle field operands） | ~30 | `test_derive_supports_addition` |
| 2 | feat: derivation 操作数支持 `provider:RAW` 形式 + records 注入 | ~80 | `test_derive_with_provider_raw_operands_sums_correctly` + edge cases (missing raw, cross-provider rejection, currency mismatch) |
| 3 | docs: 600519 PDF SGA spot-check + decision note | ~30 | 仅文档 |
| 4 | feat OR docs: apply CN SGA derivation OR record terminal continuation | ~50-100 | 取决于 commit 3 决策 |
| 5 | docs: H2.1 validation report + roadmap update | ~50 | 仅文档 |

每 commit 独立 pytest + ruff + mypy 绿。

## 验收标准

- 加法 derivation + raw provider operand 的单测通过
- 600519/2024 SGA 行有可读 value（无论 promote 还是 terminal）
- 若 promote：catalog `provider_semantics_sample_verified` rule 已加，sample = 600519 1 家（单样本起步，明确文档说明）
- 若 terminal：rule 更新为"derivation 实现，sample 未 verified"，semantic_claim 解释为何 PDF 不匹配
- 现有 H2 4 个 promotion 不回归（test_phase_h2_validation 全过）
- catalog_consistency 全过
- 526 → ~530 tests，全绿

## Open Questions / 风险

- **单样本风险**：与 H2 现有 promotion 一致 —— 600519 是 sample-verified；其他 CN 公司未 verified。文档 acknowledged，留 Phase H2.2 多公司扩 sample 候选。
- **HK accidentally invoked**：catalog `derivation` market-agnostic；HK 调用时若 raw 字段不存在应 cleanly blocked，不 leak 错误值。需 commit 2 测试覆盖。
- **`mapped` lookup vs records lookup 冲突**：如有 Turtle 字段名碰巧叫 `MANAGE_EXPENSE`（不太可能），mixing 时优先级未定。建议：`provider:` 前缀强制走 records lookup；无前缀走 mapped lookup。
- **commit 3 PDF spot-check 结果未知**：commit 4 内容形态依赖此结果。Plan 需对两种分支都准备代码模板。
