# 路线图与计划评估

> 日期：2026-05-08
> 评估基线（v1）：Phase M5 完成后（HK 11/15 clean present, 438 tests）
> 更新基线（v2）：Phase N 完成后（33-field denominator, 445 tests）

## 0. 评估更新（v2，Phase N 完成后）

Phase N 已按 N0/N1/N2/N3 拆分执行完成。当前 33-field replay 状态：

| 公司 | 市场 | clean | non-clean |
|------|------|-------|-----------|
| 600519 | CN | 27/33 | 6 |
| 00001 | HK | 20/33 | 13 |
| 01113 | HK | 21/33 | 12 |

非 clean 字段已分为 4 个桶，对应不同的修复路径（详见 `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md` "Phase H/I: Concrete Trigger Set Identified Post-N"）：

1. **Source policy 修正（不需 fallback）**: 3 个字段（600519 bond_payable/st_borr/lt_borr，Maotai 实际无借款，None → 0）
2. **Phase H 确定性 PDF 抽取（不需 LLM）**: 7 个 (公司,字段) 对
3. **Phase I LLM-辅助 notes 抽取（HK only）**: ~10 个 (公司,字段) 对
4. **锁定终态（不再追求 clean）**: 5 个字段（gross_profit, cip, non_oper_income/exp, 部分 other_cur_assets）

下一步推荐顺序：Bucket 1 → Bucket 4（终态分类） → Phase H → Phase I。

预期最终覆盖：CN 30/33, HK 28-30/33。

---

## 1. 原评估（v1，Phase M5 完成后）

## 1. 当前状态快照

### 覆盖率

| 公司 | 市场 | combined selected | clean present | denominator |
|------|------|-------------------|---------------|-------------|
| 600519 | CN | 14/15 | 13/15 | 15 |
| 00001 | HK | 11/15 | 11/15 | 15 |
| 01113 | HK | 11/15 | 11/15 | 15 |

### P0/P1 字段全集（33 fields）vs 当前映射（15 fields）

已映射的 15 个字段：revenue, net_profit, gross_profit, operating_cash_flow, investing_cash_flow, financing_cash_flow, cash, total_assets, total_liabilities, total_cur_assets, total_cur_liab, defer_tax_liab, bond_payable, cip, invest_income

未映射的 18 个字段：

| 字段 | Priority | 预期难度 | Provider 数据可用性 |
|------|----------|---------|-------------------|
| operating_cost | P0 | 中 | AKShare CN 有；HK 年报格式不标准 |
| operating_profit | P0 | 中 | AKShare CN 有；HK 结构复杂 |
| equity_attributable_to_owners | P0 | 中 | Yahoo 有 Stockholders Equity |
| money_cap | P0 | 低 | AKShare CN 有 |
| st_borr | P0 | 低 | AKShare CN 有；Yahoo 有 |
| lt_borr | P0 | 低 | AKShare CN 有；Yahoo 有 |
| accounts_receiv | P0 | 低 | AKShare CN 有；Yahoo 有 |
| acct_payable | P0 | 低 | AKShare CN 有；Yahoo 有 |
| inventories | P0 | 低 | AKShare CN 有；Yahoo 有 |
| fix_assets | P0 | 低 | AKShare CN 有；Yahoo 有 |
| rd_exp | P0 | 高 | AKShare CN 有；HK 可能无专行 |
| selling_general_administrative | P1 | 中 | Yahoo 有 SGA |
| fv_value_chg_gain | P1 | 高 | AKShare CN 有；HK/Yahoo 可能无 |
| non_oper_income | P1 | 高 | AKShare CN 有；HK 结构不同 |
| non_oper_exp | P1 | 高 | AKShare CN 有；HK 结构不同 |
| other_cur_assets | P1 | 中 | Yahoo 有 Other Current Assets |
| defer_tax_assets | P1 | 低 | Yahoo 有 Non Current Deferred Taxes Assets |
| minority_int | P1 | 低 | Yahoo 有 Minority Interest |

### Provider baseline 数据量

| 市场 | AKShare | Yahoo |
|------|---------|-------|
| HK | 142 unique raw fields | 194 unique raw fields |
| CN | 728 unique raw fields | 160 unique raw fields |

---

## 2. Phase N 计划评估

### 当前 Phase N 定义的问题

Roadmap 中 Phase N 的描述过于宽泛：**"一次性从 15 扩到 33"**，没有分层策略。实际上这 18 个字段难度差异极大：

- **简单层（~10 fields）**：st_borr, lt_borr, accounts_receiv, acct_payable, inventories, fix_assets, money_cap, defer_tax_assets, minority_int, other_cur_assets —— provider baseline 有明确数据，语义直接，跟已有字段的证明模式一致
- **中等层（~4 fields）**：operating_cost, operating_profit, equity_attributable_to_owners, selling_general_administrative —— 有 provider 数据但 HK 年报格式可能不直接支持验证
- **困难层（~4 fields）**：rd_exp, fv_value_chg_gain, non_oper_income, non_oper_exp —— HK 可能无对应行项，CN-specific 概念，需要更多市场分析

### 建议：Phase N 应拆为 N1/N2/N3

**Phase N1（低风险扩展，~10 fields）**：
- 只添加 provider baseline 明确可映射、语义直接的字段
- 预期大部分 CN 可 clean present，HK 视 Yahoo 数据而定
- 不需要新增 trust policy 或 provider semantics proof——这些字段的 Yahoo raw field name 和 Turtle 语义足够直接（如 `Accounts Payable` → `acct_payable`）
- 工作量：主要是 JSON catalog 扩展 + 测试

**Phase N2（中等风险，~4 fields）**：
- operating_cost/operating_profit 在 HK 可能是 `gross_profit` 同类问题——年报格式不标准
- equity_attributable_to_owners 需要确认 Yahoo `Stockholders Equity` vs `Total Equity Gross Minority Interest` 的语义差异
- 可能需要新增 provider semantics proof 或 terminal bucket

**Phase N3（高风险/可延后，~4 fields）**：
- fv_value_chg_gain, non_oper_income, non_oper_exp 是 CN A-股概念，HK/Yahoo 体系没有直接对应
- rd_exp 在 HK 年报可能只在 notes 中披露
- 这些字段可能最终落入 `pdf_only` 或 `source_unavailable` for HK

### 为什么不应一次全做

1. **gross_profit 的教训**：如果 M5 之前就盲目扩展到 33 field，会产生 18 个 "yahoo_definition_unverified" 或 "mapping_expansion_required" 的模糊状态，让覆盖率数字失去意义
2. **review 负担**：每个新字段需要确认 raw field 语义、写 provider semantics rule、可能做 PDF spot-check
3. **测试回归风险**：一次大批量改动 JSON catalog 容易引入字段间交叉影响

---

## 3. Phase H/I 时机评估

### Phase H（Selected PDF Evidence Supplement）

**当前状态**：Spec 已写，计划已写，代码未实现。

**问题**：Phase H 的 trigger 是 source-first gate 产出 `needs_pdf_evidence` 字段。当前 15-field 中只有 `gross_profit`（已确认不可验证）和 3 个 source_unavailable 字段需要 PDF。Phase N 扩展后，HK 困难字段才会真正触发 Phase H。

**建议**：Phase H 应在 Phase N2 之后启动，而非 Phase N1 之后。N1 扩展的简单字段不太需要 PDF supplement。

### Phase I（LLM Ambiguity Review）

**当前状态**：Spec 已写，代码未实现。

**问题**：Phase I 是对 ambiguous/conflict 字段的 LLM 辅助判断。当前管线的 conflict 主要来自跨 source 值冲突。如果 Phase N 增加更多 CN+HK 字段，cross-source conflict 概率上升，Phase I 的价值才会体现。

**建议**：Phase I 应在 Phase N2/N3 的 conflict 字段积累后启动，或在需要 LLM 辅助 source semantics 判断时启动。

---

## 4. 架构层面的隐患

### 4.1 JSON catalog 维护复杂度

当前 5 个 JSON catalog 之间有隐式一致性约束：

```
coverage_matrix.primary_route ↔ source_mapping.primary_route
coverage_matrix.verification ↔ source_mapping.verification_status
provider_semantics.turtle_field_id ↔ source_mapping keys
trust_policy.field_id ↔ source_mapping keys
trust_policy.allowed_yahoo_raw_fields ↔ provider_semantics.raw_field_name
```

Phase N 扩展 18 个字段时，要同时维护 5 个文件的一致性。当前靠 `test_source_mapping_catalog.py` 的 cross-validation 测试守护，但测试覆盖的约束不完整。

**建议**：在 Phase N1 开始前，加一个 `test_catalog_consistency.py` 专门做全量交叉校验。

### 4.2 HK vs CN 的非对称设计

CN（600519）走 AKShare direct，没有 trust policy 层，不需要 PDF spot-check。HK（00001/01113）走 Yahoo direct + trust policy + provider semantics proof。

Phase N 扩展时，新字段对 CN 可能很简单（AKShare 直接有），对 HK 可能需要重走 M3-M5 的 proof 流程。这意味着 **Phase N 的实际工作量取决于 HK 字段的复杂度，而非字段总数**。

**建议**：Phase N1 的范围定义应基于"HK 也能走通"的字段，而非"CN provider 有数据"的字段。

### 4.3 Provider baseline fixture 的时效性

当前 provider baseline（6,771 records）是某一时刻的 snapshot。如果 AKShare/Yahoo API 返回结构变化，fixture 不会自动更新。

**风险**：Phase N 扩展基于现有 baseline 做 raw field candidate discovery，如果 baseline 过时，可能遗漏新出现的 raw field。

**建议**：Phase N 开始前，可选择性刷新 provider baseline（opt-in real provider 调用），但不是强制要求。

### 4.4 `source_unavailable` 字段的出路

bond_payable, cip, invest_income 当前标记 `source_unavailable`。Phase N 会新增更多可能 HK source_unavailable 的字段（rd_exp, fv_value_chg_gain 等）。

如果 source_unavailable 字段持续积累但没有 Phase H/I 来处理，项目会出现"source-first 覆盖率看起来很低，但其实是字段本身在 source 层面不可得"的表象问题。

**建议**：Phase N 应把 source_unavailable 字段明确分为：
- `source_unavailable_hk_only`（CN 有数据，HK 无）
- `source_unavailable_all_markets`（所有 provider 都没有）
- `pdf_only_by_design`（按 taxonomy 本身就是 PDF-only）

---

## 5. 推荐路线图修订

```
当前 → Phase N1（简单 10 fields 扩展）
     → catalog consistency 测试加固
     → Phase N2（中等 4 fields，需 HK 验证）
     → Phase H（PDF supplement for N2 非 clean 字段）
     → Phase N3（困难 4 fields，可能大量 terminal bucket）
     → Phase I（LLM review for conflict/ambiguous）
```

### 与当前 roadmap 的差异

| 维度 | 当前 roadmap | 建议修订 |
|------|-------------|---------|
| Phase N 范围 | 一次 15→33 | 拆为 N1/N2/N3 |
| Phase H 触发 | Phase N 之后 | Phase N2 之后 |
| Phase I 触发 | Phase H 之后 | Phase N2/N3 conflict 积累后 |
| 新增 | 无 | catalog consistency test gate |
| 字段分类 | "source_unavailable" 一刀切 | 区分 HK-only / all-market / pdf-by-design |

### 预期产出指标

| 里程碑 | 33-field clean present 预期 |
|--------|--------------------------|
| Phase N1 完成 | CN: ~23/33, HK: ~18/33 |
| Phase N2 完成 | CN: ~27/33, HK: ~20/33 |
| Phase H 完成 | HK: ~22/33（PDF supplement 字段上升） |
| Phase N3 + I | CN: ~30/33, HK: ~24/33（剩余为 source_unavailable/pdf_only） |

---

## 6. 总结判断

**当前计划的核心方向（source-first → provider semantics proof → selected PDF/LLM fallback）完全正确。**

主要建议：

1. **Phase N 需要拆分**——一次扩 18 field 风险太大，应按难度分 3 层
2. **Phase H/I 应推迟到有实际需求时**——不要提前实现没有 trigger 的能力
3. **加 catalog consistency gate**——5 个 JSON 文件的交叉一致性应有专门测试守护
4. **source_unavailable 需要细化分类**——避免覆盖率数字失真

风险不在架构本身，而在 **Phase N 执行节奏**：如果一次性做完 33 field，大量字段会停留在模糊 terminal bucket，覆盖率数字会误导判断。分层推进可以在每一层都得到明确的 clean/non-clean 结论，再决定下一步。
