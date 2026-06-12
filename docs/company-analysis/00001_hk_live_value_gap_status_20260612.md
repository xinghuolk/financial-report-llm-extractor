# 00001.HK 价值投资字段缺口 — LIVE 状态基线（2026-06-12 晚，5-PR review 合并后刷新）

> **用途**：以最新一次实际运行的输出为准，刷新并**取代**以下快照/规划 doc 中已过时的逐字段状态：
> `00001-ckh-3yr-2023-2025.md`（06-11 抽取快照）、`00001_hk_latest_value_analysis_data_gaps_20260604.md`（06-04）、`00001-missing-fields-source-exploration-20260610.md`（06-10 规划）、以及本文档的当日早间版本。
>
> **数据来源（live run）**：`tmp/runs/00001_2025_postreview/`（Jun 12 晚，main @ 5-PR 统筹 review 全部合并后：#19 trim 返工 / #20 gross_profit standardized + 门控 / #21 parent debt absence-zero + scope guard / #22 调查文档 / #23 AKShare HK CNY）。
> `evaluation.json`（supplement 之后的最终分类，权威）+ `llm_evidence_supplement.json`（Codex relay `gpt-5.5`，P0–P4 全 68 字段）。
> 公司 00001 · 市场 HK · 期末 2025-12-31 · 币种 HKD · 数值单位百万 HKD（除注明）。
>
> `evaluation.json` 桶计（68 字段）：**clean_present 34 / llm_supplement_present 23 / not_in_scope 3 / terminal_unverified 1 / unresolved_conflict 7**。
> （早间版本为 33/21/3/1/10——当日净改善 +3 present、−3 unresolved。）

## 0. 当日（06-12）关闭项 —— 早间版本 §2/§6 的开放项现状

| 早间开放项 | 现状 | 关闭方式 |
|---|---|---|
| `gross_profit` "unresolved_conflict，需口径决策" | ✅ **clean_present** 139,204（yahoo） | PR #20：operator 决策接受 Yahoo standardized 派生（select_primary_standardized + yahoo_standardized_accepted trust rule，带 raw-field/币种/单位门控）；佐证链见 `docs/gates/2026-06-12-gross-profit-divergence-investigation.md`（01810 三方逐位一致；00001 币种修正后残差 ~12.7% 为真口径差，已书面接受） |
| `interest_bearing_debt_parent_company` "支持挂 absence_means_zero 但尚未做" | ✅ **llm_supplement_present = 0** @p271 conf .86 | PR #21：absence_means_zero 落地 + parent scope guard（推零只能从 alias 检索到的母公司 section 触发，合并报表不会误喂）；本次 run 经 alias 路径实际推零 |
| `non_recurring_items_breakdown` "需专项重跑才解出" | ✅ **常规 run 直接命中** @p19 conf .95 | PR #19：alias-window trim 返工（预算重分配 + 头尾均匀选址 + 空白归一化匹配）后，常规全量 run 不再丢页尾 itemization |

## 1. ✅ 已闭环（present，57/68 = clean 34 + LLM 23）

| 字段 | FY2025 | 来源/页 | 说明 |
|---|---|---|---|
| `non_recurring_items_breakdown` | 10,922 = 9,915（处置非现金损失）+ 1,445（CKHGT 交易费）+ 438（公司间抵免） | llm @p19 conf .95 | 2024 对比期 = 3,740 |
| `interest_bearing_debt_parent_company` | **0**（母公司表无借款行，section 完整佐证推零） | llm @p271 conf .86 | absence_means_zero；控股公司债务沉在运营子公司 |
| `gross_profit` | 139,204 | yahoo（standardized accepted） | 带 `standardized_derivation_accepted` 来源标签；与 AKShare 派生的口径差保留在 recon 报告供审计 |
| `audit_opinion` | 无保留意见（"true and fair view"） | llm @p129 conf .95 | P4 |
| `dividend_policy_text` | 董事会股息政策（投资级评级 + 最优资本结构承诺） | llm @p125 conf .98 | P4 |
| `c_paid_for_taxes` | -5,571 | llm @p141 | "Tax paid" 现金流行 |
| `capitalized_interest` | -21 | llm @p205 | Note 9 括号负数 |
| `lease_liability_maturity` | ≤1y 15,485 / 1-5y 33,080 / >5y 35,814；undiscounted 84,379；账面 66,496 | llm @p280 | 完整到期阶梯 |
| `buyback_cancellation_progress` | "未购买/出售/赎回任何上市证券（含库存股）" | llm @p89 | 实质终态"无回购活动" |
| `dps` | 1.602 HK$/股 | llm @p17 | per-share 单位为下游工程项 |
| `receivables_aging` | <31d 11,433 / 31-60d 1,796 / 61-180d 1,056 / >180d 3,998 / 合计 18,283 | llm @p229 | — |
| 母公司 SOTP 组 | `cash_parent_company` 7 · `equity_investment_in_subsidiaries` 368,139 · `amounts_due_from_subsidiaries` 25,731 | llm @p271 | G3 字段全闭环 |
| 利润质量组 | `invest_income` 19,974 · `non_oper_income` 976 · `non_oper_exp` 12,327 · `segment_revenue_profit`（segment rev 507,297 / EBITDA 104,816 @p153） | llm @p134/p153 | — |
| 核心主干 | `net_profit` 11,841 · `operating_cash_flow` 62,567 · `capital_expenditures` -20,835 · `dividends_paid` -8,518 · `repurchase_of_stock` 0 · `cash` 143,748 · `st_borr` 38,416 · `lt_borr` 229,699 · `bond_payable` 165,366（llm @p232） | yahoo/llm | A 级 |

## 2. 🟠 仍开放（7 unresolved + 1 terminal）

| 字段 | live 状态 | 影响 / 处置建议 |
|---|---|---|
| `restricted_cash` | unresolved（missing_source_candidate，检索未命中——**by design**，见 §3.1） | 下游结论不受影响（无受限现金 → 净现金不扣减）；待办是把裁决固化进 catalog |
| `fv_value_chg_gain` | unresolved（利润表 p132/134 有行但未被该字段检索命中） | 利润质量；检索缺口，加 P&L 行别名可解 |
| `rd_exp` | unresolved | 应与 `capitalized_rd` 一致终态化（HK 综合企业不单列研发，market-wide NA） |
| `stock_based_compensation` | unresolved（披露"不重大"、无数字） | 可挂 flag 记 N/A 闭环 |
| `other_cur_assets` | unresolved（无独立"其他流动资产"行） | 需派生（合并行 − trade receivables）或语义映射决策 |
| `time_deposits_or_wealth_products` | unresolved | HK 报表本就不单列；低优先级 |
| `contract_liabilities_non_current` | unresolved（仅流动有值 current = 5,321 已 present） | provider 真稀疏（G1b 已核），by-design 留 LLM/缺失 |
| `selling_general_administrative` | terminal_unverified（yahoo 16,491） | note 8 组分可拼 PDF 佐证完成验证；非阻塞 |

## 3. 需要点名的裁决记录（运行态 vs 人工裁决态）

1. **`restricted_cash`**：运行态是"检索未命中"——这是**刻意的**。曾有别名命中 p59/p269 Note 36，但那是**质押资产（pledged assets）非受限现金**，外部 review 判定为误归因后已撤别名（含 fixture canary 锁 no_hit）。
   - **下游结论一致**：无受限现金 → 净现金不扣减。
   - **待办**：在 catalog 标 not_applicable + reason 固化裁决，消除运行态与裁决态差异；如需"抵押资产"信号应另立 `pledged_assets` 字段，与现金质量分开。
2. **数据分层**：`warning_classification.json` 是 source-policy 阶段产物（LLM 补充字段在其中仍标 missing）；`evaluation.json` 是 supplement 之后的最终分类。本 doc 以 **`evaluation.json` + `llm_evidence_supplement.json`** 为权威。
3. **AKShare HK 币种**（PR #23，本 doc 范围外但影响 00001 的 recon 读数）：EastMoney feed 对所有 issuer 输出 CNY 折算值，已统一改标 CNY。00001 此前 5 个 A- 分歧簇（total_assets / total_liabilities / total_cur_assets / total_cur_liab / inventories，比率恰为 CNY/HKD 0.9032）实为同值异币，现 recon 给出诚实的 "candidate currencies differ" 分类而非伪数值冲突。

## 4. 对价值投资分析的净结论

| 信号 | 依赖 | 状态 |
|---|---|---|
| `owner_earnings` / 正常化盈利 | OCF − capex；`non_recurring` 正常化 | ✅ 全 present（non_recurring 常规 run 稳定命中） |
| 毛利率 / 盈利质量 | `gross_profit` | ✅ standardized accepted（带来源标签，divergence 留审计） |
| R / GG 的 buyback 项 | `repurchase_of_stock` + 注销链 | ✅ repurchase=0 + 注销确认 → 合法置 0 |
| `payout_M` | dividends_paid / net_profit / commitment | ✅ present；commitment 已在下游派生（TradingAgents-CN PR #31） |
| `net_cash_ratio` | cash + 有息债务(st+lt+bond) | ✅ present；restricted_cash 无 → 不扣减 |
| 母公司 SOTP 杠杆 | parent cash/equity_invest/amounts_due/debt | ✅ 全 present（parent debt = 0 经 absence-zero） |

**核心买卖结论级别的缺口已清零。** 剩余 7 个 unresolved 全部属于"利润/BS 颗粒度"或"应终态化"层级，无一阻塞核心估值信号。

## 5. 建议下一步（按 ROI）

1. `restricted_cash` 在 catalog 标 not_applicable（00001 HK，reason=Note 36 质押资产≠受限现金），固化人工裁决；如需抵押资产信号另立 `pledged_assets`。
2. `rd_exp` 终态化（与 `capitalized_rd` 一致，HK market-wide NA）。
3. `fv_value_chg_gain` 加 P&L 行别名（p134 已在其他字段上下文中命中，纯检索缺口）。
4. `stock_based_compensation` 挂 flag 记 N/A；`other_cur_assets` 派生决策。
5. `selling_general_administrative` note-8 组分 PDF 佐证（低优先级，terminal 带值可用）。
