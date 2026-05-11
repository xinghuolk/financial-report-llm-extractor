# Phase H2.2 Spec — Multi-Sample Verification + Market-Scoped Aliases + Candidate Audit

> 日期：2026-05-09
> 状态：Draft
> 前置：Phase H2 + H2.1 完成。CN 600519/2024 上有 5 fields（revenue / operating_profit / capital_expenditures / interest_paid_cash / selling_general_administrative）已 sample_verified，但每个仅 1 公司样本（drift §177 sampling-bias 风险）。HK SGA 因 H2.1 emptied yahoo aliases 落入 source_policy_resolvable。clean_present 行不显示其他 provider 候选值。

## 三个独立 sub-modules

### Sub-A: 多公司 sample-verification

新增 PDF spot-check：300750 (CATL 电池) + 601919 (中远海控 航运) + 688008 (海光信息 半导体)，3 家不同行业。对每家 × 5 promotion fields 做 PDF 实地核对，结果写入 `provider_raw_semantics_cn.json` 各 rule 的 `samples[]`（每条 1 → 4 samples）。

**Promotion 不动**：rule 仍 sample_verified；新增样本是"多家验证"信号，不为撤销原 promotion 提供路径（除非任何一样本严重偏离 PDF — 那就要重审）。

**判断标准（每样本）**：
- AKShare 值 = PDF 实际值 EXACT → `matches_raw_value: true`
- 偏离 < 1% 的舍入差异 → `matches_raw_value: true` + `notes` 解释
- 严重偏离 → `matches_raw_value: false` + `matches_raw_value_reason` 解释 + 升级为 `provider_semantics_unverified`（如 ≥1/4 不 EXACT）

**Acceptance**: 5 fields × 4 companies = 20 sample 记录已写入；任何 false 都有解释；所有 H2 + H2.1 promotions 仍 clean_present 在 600519。

### Sub-B: market-scoped source_aliases

扩展 `SourceMappingEntry.source_aliases` schema 支持 market-scoped form：

```jsonc
"source_aliases": {
  "akshare": ["MANAGE_EXPENSE", "SALE_EXPENSE"],
  "yahoo": [],
  "by_market": {
    "HK": {
      "yahoo": ["Selling General And Administration"]
    }
  }
}
```

**Lookup 改动** (`mapping._record_matches_entry` at `mapping.py:401`):
- 当前：`entry.source_aliases.get(record.source, ())` 全市场共享
- 新逻辑：先尝试 `entry.source_aliases.by_market.get(record.market, {}).get(record.source, ())`；fall back 到 `entry.source_aliases.get(record.source, ())`

**适用**：H2.2 内只 SGA 用 by_market。Schema 完整支持任意 entry。

**HK SGA spot-check**:
- 00001 + 01113 PDF：spot-check Yahoo `Selling General And Administration` 是否 EXACT 匹配 PDF SGA 值
- 若 EXACT → 加 `provider_semantics_sample_verified` rule 到 hk catalog → HK SGA promote
- 若不 EXACT → 仅 land schema infra，HK SGA Yahoo alias 还原但 rule 仍 `provider_semantics_unverified`，HK 状态从 `source_policy_resolvable` 恢复到 `terminal_unverified`（架构诚实，per 用户决策）

**Acceptance**: schema + lookup 通过；HK 00001/01113 SGA 行根据 spot-check 结果分类；catalog_consistency 全过；CN 行为不变（`by_market` 不影响 CN-only 字段）。

### Sub-C: candidate audit display for clean rows

修 `_collect_candidate_values` (company_evaluation.py:235) 移除桶 filter，改条件 `mapping.fields[fid].candidates >= 2 → emit all`。markdown 渲染保持 `src1:val / src2:val` format。

**判别 clean rows 的 selected**：clean_present 时通过 Source 列已能看出选了谁；不需在 Value 列额外加 `(selected)` 标记（避免冗余）。

**Edge case**：derived 字段无 candidates → 行为不变（fall through 到 selected value 显示）。

**Acceptance**: clean_present 行（如有 2+ candidates）现在显示 `akshare:170.90B / yahoo:174.14B`；llm_supplement_present 同；新增单测；现有 markdown 测试更新。

## Non-Goals

- 不引入 tolerance gate（per drift §177 + 用户先前 push back）
- Sub-A 不扩展到其他字段（仅 5 个 H2/H2.1 promotion）
- Sub-B 不动其他 catalog entry（仅 SGA）
- Sub-C 不改 evaluation.json schema（仅 markdown 渲染）

## 实现拆分（6 commits）

| Commit | 主题 | LoC | 依赖 |
|--------|------|----:|------|
| 1 | feat: phase h2.2 sub-c — markdown candidate values for clean rows | ~50 | 无 |
| 2 | docs: phase h2.2 sub-a — PDF spot-check 3 CN companies × 5 fields | ~150 | 无 |
| 3 | docs: phase h2.2 sub-a — multi-company samples in provider_raw_semantics_cn.json | ~200 (data) | C2 |
| 4 | feat: phase h2.2 sub-b — source_aliases.by_market schema + lookup | ~80 | 无 |
| 5 | feat: phase h2.2 sub-b — HK SGA market-scoped + spot-check + rule | ~100 | C4 |
| 6 | docs: phase h2.2 validation report + roadmap | ~80 | C1-C5 |

每 commit 独立 pytest + ruff + mypy 绿。Sub-C / Sub-A / Sub-B 互不依赖；可任意顺序。

## 验收标准

- 5 fields × 4 companies = 20 sample 记录在 `provider_raw_semantics_cn.json`
- catalog `source_aliases.by_market` schema 加载 + lookup 通过
- HK SGA 行为符合 spot-check 决策（infra-only 或 promote）
- evaluation.md clean_present + llm_supplement_present 行（>= 2 candidates）显示候选值
- 600519 / 2024-12-31 clean_present 不下降（保 39/56）
- 533 → ~540 unit tests，全绿

## Open Questions / 风险

- **多公司 fixture 缺失**：300750/601919/688008 fixture 在 `provider_field_baseline` 里可能无完整数据 → spot-check 时只查 PDF，记入 sample；fixture 数据若不齐，infra-only land 不阻止后续扩展
- **HK Yahoo SGA EXACT match 概率**：基于 H2 经验（Yahoo HK Total Revenue 含 associates per HKFRS Note 1），SGA 估计 likely **不 EXACT** → 走 infra-only branch
- **Sub-C 渲染冲突**：candidate values 显示对所有 row → markdown 表格变长。可接受（reviewer 价值 > 视觉清爽）
