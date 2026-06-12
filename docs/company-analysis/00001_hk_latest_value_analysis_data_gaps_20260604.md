# 00001.HK 最新价值分析数据缺口审计

审计日期：2026-06-04  
数据来源：Docker MongoDB `analysis_reports` 中最新的 00001.HK 报告

## 最新报告信息

| 项目 | 值 |
| --- | --- |
| 报告 ID | `6a215193ad53fb695764087a` |
| task_id | `854ee099-f6a1-45d1-a687-ffa44f3ee6d4` |
| 创建时间 | `2026-06-04T10:21:07.140Z`，即 `2026-06-04 18:21:07 CST` |
| 股票 | `00001` / `长和` / `港股` |
| 数据报告期 | `2025-12-31` |
| facts 状态 | `degraded` |
| 年报数据状态 | `degraded` |
| 行情数据状态 | `complete` |
| 价值信号状态 | `degraded` |
| 最终操作建议 | `买入` |
| 建议置信度 | `0.7` |
| 风险分数 | `0.5` |
| 当前价格 | `68.7 HKD` |
| 目标价格 | `53 HKD` |

## 数据覆盖情况

| 数据段 | 总数 | reliable | display-only | 说明 |
| --- | ---: | ---: | ---: | --- |
| 2025 年报字段 | 51 | 47 | 4 | 核心三表和有息负债已经基本可用 |
| 2024 年报字段 | 49 | 45 | 4 | 历史覆盖较完整 |
| 2023 年报字段 | 37 | 34 | 3 | 附注类字段缺失较多 |
| 行情字段 | 6 | 6 | 0 | 行情基础数据完整 |
| 价值信号 | 8 | 6 complete | 2 degraded | 已无 non-decisionable 信号 |

相比 2026-06-03 的最新审计，2025 年报 reliable 字段已经从 32 个提升到 47 个。`bond_payable` 当前由 `gpt-5.5` 提取并被策略允许作为 reliable 数据，因此已经可以派生 `interest_bearing_debt`。

## 价值信号状态

| 信号 | 状态 | 值 | 缺失输入或限制 |
| --- | --- | ---: | --- |
| `payout_M` | complete | `0.719365` | 未提取承诺派息率，未应用 commitment cap |
| `owner_earnings` | complete | `417.32` 亿港元 | 无 |
| `R` | degraded | `2.5898%` | 缺少 `buyback_amount_3y_avg`，按 0 计算 |
| `GG` | degraded | `9.1274%` | 缺少 `buyback_amount_3y_avg`，按 0 计算 |
| `HH` | complete | `-6.5376` 个百分点 | 依赖降级后的 `R` 和 `GG` |
| `net_cash_ratio` | complete | `-110.1127%` | 无 |
| `ev_switch` | complete | `0` | 无 |
| `cash_protection` | complete | `30%` | 无 |

已解决的关键阻断项：

| 字段 | 当前状态 | 来源 |
| --- | --- | --- |
| `bond_payable` | reliable | `financial-report-client:llm:gpt-5.5`, `bond_payable p.232` |
| `interest_bearing_debt` | reliable | 从 `st_borr`, `lt_borr`, `bond_payable` 派生 |

## 当前主要缺失数据

### P0：直接影响价值信号和最终结论

| 缺失数据 | 当前状态 | 影响 |
| --- | --- | --- |
| `repurchase_of_stock` | unavailable | 没有可靠的回购金额 |
| `buyback_cancellation_progress` | unavailable | 无法确认回购股份是否注销，不能判断真实股东回报 |
| `buyback_amount` | 未生成 | 无法将回购纳入当年股东回报 |
| `buyback_amount_3y_avg` | 缺失，计算时按 0 处理 | `R` 和 `GG` 只能降级计算 |
| `commitment_ratio` | 未提取 | `payout_M` 未应用承诺派息率上限约束 |

### P1：影响资产负债表安全性判断

| 缺失数据 | 影响 |
| --- | --- |
| `restricted_cash` | 无法确认账面现金中可自由使用的部分 |
| `time_deposits_or_wealth_products` | 定存、理财和准现金资产覆盖不完整 |
| `interest_bearing_debt_parent_company` | 缺少母公司层面的有息债务风险 |
| `lease_liability_maturity` | 缺少租赁负债期限结构 |
| `receivables_aging` | 无法判断应收账款逾期、账龄和坏账风险 |
| `related_party_receivables_payables` | 无法判断关联方资金占用和利益输送风险 |

### P2：影响利润和现金流质量判断

| 缺失数据 | 影响 |
| --- | --- |
| `non_recurring_items_breakdown` | 无法完整拆分经常性与非经常性利润 |
| `fv_value_chg_gain` | 公允价值变动对利润的影响不清楚 |
| `non_oper_exp` | 营业外支出拆分不完整 |
| `c_paid_for_taxes` | 税务现金支出缺失 |
| `receiv_tax_refund` | 税款返还缺失 |
| `c_pay_to_staff` | 员工相关现金支出缺失 |
| `rd_exp` | 研发费用缺失 |
| `capitalized_rd` | 研发资本化情况缺失 |
| `stock_based_compensation` | 股权激励和潜在稀释风险缺失 |
| `contract_liabilities_non_current` | 长期合同负债缺失 |
| `other_cur_assets` | 其他流动资产构成缺失 |

## 已获取但不能作为可靠计算输入

| 字段 | 当前值 | 原因 |
| --- | ---: | --- |
| `dps` | `1.602` | 来源为 `gpt-5.5`，但单位 `per share` 当前不受结构化单位系统支持 |
| `gross_profit` | `139,204,000,000 HKD` | `unresolved_conflict` |
| `selling_general_administrative` | `16,491,000,000 HKD` | `terminal_unverified` |
| `dividend_payout_ratio_proxy_single_year` | `0.719365` | 只是单年代理值，不是三年平均 |

## 行情侧缺失

行情基础字段 `market_cap`, `close_price`, `tax_rate`, `holding_channel`, `rf_rate`, `industry` 均为 reliable，但仍有：

- `dividend data missing`
- `buyback data missing`

年报侧和行情侧都没有可靠回购数据，因此回购是当前最大的数据缺口。

## 最终结论一致性风险

最新报告的最终建议为买入，但存在两项明显的数据和结论不一致：

| 风险 | 具体表现 |
| --- | --- |
| 目标价与买入建议矛盾 | 当前价为 `68.7 HKD`，目标价为 `53 HKD`，目标价比当前价低约 `22.9%`，但最终建议仍为买入 |
| 回购理由缺乏结构化数据支持 | 买入理由称“回购提供正期望收益”，但 `repurchase_of_stock`, `buyback_amount`, `buyback_amount_3y_avg` 和注销进度均无可靠数据 |

因此，当前结构化数据已经能够支持大部分价值信号计算，但不能充分支持最终报告中的回购判断和买入结论。

## 改进优先级

| 优先级 | 改进项 | 建议验收标准 |
| --- | --- | --- |
| P0 | 回购金额与注销进度抽取 | `buyback_amount_3y_avg` 可可靠计算，`R` 和 `GG` 从 degraded 变为 complete |
| P0 | 最终建议一致性校验 | 目标价低于当前价时，不允许输出无解释的买入建议 |
| P0 | 叙述证据约束 | 报告不能把 unavailable 或 display-only 字段作为确定性买卖理由 |
| P1 | 承诺派息率抽取 | `payout_M` 应用 commitment cap，并说明来源页码 |
| P1 | 现金可用性和债务期限 | 补齐受限现金、理财定存、母公司债务和租赁负债期限 |
| P1 | 应收及关联方质量 | 补齐账龄、坏账和关联方往来 |
| P2 | 利润质量字段 | 补齐非经常性损益、公允价值变动、研发和股权激励字段 |
| P2 | display-only 字段验证 | 解决 `gross_profit` 冲突、SG&A 终端验证和 DPS 单位支持 |

## 总体判断

最新数据层已经从“核心指标不可决策”提升到“核心价值信号基本可计算”：

- 51 个当前年报字段中，47 个 reliable。
- 8 个价值信号中，6 个 complete。
- 有息债务和净现金相关信号已经恢复。

剩余最关键的问题不是基础三表，而是回购、承诺派息率、受限现金、应收质量等价值投资附注数据，以及最终自然语言结论与结构化数据之间的一致性控制。

---

## 2026-06-11 更新：extractor 侧进展（alias lifecycle 落地后）

> 本节为 extractor 侧补记；上文为 2026-06-04 下游快照，保留原貌。下游升级
> extractor（含 alias-lifecycle 三件套 + 转正 batch 1/2）并重跑后，下列缺口
> 状态将改变。00001 三年重评估（`gpt-5.5` relay 通道）：FY2025 覆盖
> **50/68**（snapshot 时代 DS 基线 47）。

| 上文缺口 | 现状 | 说明 |
|---|---|---|
| `repurchase_of_stock`（P0） | **已解决** | `absence_means_zero` 合成零（2024/2025 = 0，provider 历史跟踪 + 本期省略） |
| `receivables_aging`（P1） | **已解决** | 别名转正 batch 2（`ageing analysis of the trade receivables`）→ 完整账龄表 @p229 |
| `related_party_receivables_payables`（P1） | **已解决** | p269 关联方注释文本进入 present |
| `non_oper_exp`（P2） | **已解决** | gpt-5.5 抽出 12,327 @利润表 |
| `dps` 跨抽取器冲突 | **已裁决** | gpt-5.5 = 1.602 @p17（与历史 Codex 一致；DS 2.312 为误） |
| `buyback_cancellation_progress`（P0） | **已解决** | `treasury shares` 别名已入 catalog → "no treasury shares" 文本 @p89 进入 present |
| `c_paid_for_taxes`（P2） | **已解决** | `tax paid` 别名已入 → (5,571) @p141（含括号负数解析修复） |
| `lease_liability_maturity`（P1） | **已解决** | `undiscounted` 别名已入 → 完整到期表 @p280 |
| `restricted_cash`（P1） | **判定为非缺口** | p59 实为质押资产非受限现金，"pledged as security" 别名经 review 撤销（语义错配）；00001 大概率无受限现金披露 |
| `non_recurring_items_breakdown`（P2） | 检索已修，抽取待调 | `one-time`/`one-off` 别名已入（chunks 到位），gpt-5.5 判 highlights 页不构成结构化 breakdown → 仍 not_found；owner_earnings 正常化的剩余阻碍 |
| `c_pay_to_staff` / `capitalized_rd` / `receiv_tax_refund`（P2） | **已终态化** | HK market-wide 结构性 NA（not_in_scope），停止假性缺口与 LLM 空转 |
| `time_deposits_or_wealth_products`（P1） | 真不披露 | 维持缺失（00001 不披露） |
| `gross_profit` 冲突 / SGA 终态 | 未变 | 口径仲裁/PDF 佐证仍待决 |
