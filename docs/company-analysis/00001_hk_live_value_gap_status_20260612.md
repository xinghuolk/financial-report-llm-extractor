# 00001.HK 价值投资字段缺口 — LIVE 状态基线（2026-06-12）

> **用途**：以最新一次实际运行的输出为准，刷新并**取代**以下快照/规划 doc 中已过时的逐字段状态：
> `00001-ckh-3yr-2023-2025.md`（06-11 抽取快照）、`00001_hk_latest_value_analysis_data_gaps_20260604.md`（06-04）、`00001-missing-fields-source-exploration-20260610.md`（06-10 规划）。
> 那几份的"可靠性=C"是**某次抽取运行的快照**，早于 gap-closure 重跑；本 doc 以 live run 校准。
>
> **数据来源（live run）**：
> - 全字段：`tmp/runs/00001_2025_vgaps2/`（Jun 12）—— `evaluation.json`（supplement 之后的最终分类，权威）+ 各 `*/*_field-extraction-v1.json`。
> - `non_recurring_items_breakdown`：专项重跑 `tmp/runs/nr_00001_2025/`（PR #19），**取代** vgaps2（vgaps2 里该字段仍 not_found）。
> - 公司 00001 · 市场 HK · 期末 2025-12-31 · 币种 HKD · 数值单位百万 HKD（除注明）。
>
> `evaluation.json` 桶计（68 字段）：clean_present 33 / llm_supplement_present 21 / not_in_scope 3 / terminal_unverified 1 / unresolved_conflict 10。

## 1. ✅ 已闭环（present）—— 覆盖快照里的 C

| 字段 | FY2025 | 来源/页 | 说明 |
|---|---|---|---|
| `non_recurring_items_breakdown` | 10,922 = 9,915（处置非现金损失）+ 1,445（CKHGT 交易费）+ 438（公司间抵免） | llm @p19 conf .94 | PR #19；vgaps2 仍 not_found，专项重跑（4,456 chunks）才解出；2024 = 3,740 |
| `c_paid_for_taxes` | -5,571 | llm @p141 | "Tax paid" 现金流行 |
| `capitalized_interest` | -21 | llm @p205 | Note 9 "Less: interest capitalised"；括号负数 parser 修复 |
| `lease_liability_maturity` | ≤1y 15,485 / 1-5y 33,080 / >5y 35,814；undiscounted 84,379；账面 66,496 | llm @p280 conf .95 | 完整到期阶梯 |
| `buyback_cancellation_progress` | "未购买/出售/赎回任何上市证券（含库存股）" | llm @p89 conf .93 | 实质终态"无回购活动" |
| `dps` | 1.602 HK$/股 | llm @p17 | per-share 单位为下游工程项 |
| `bond_payable` | 165,366 | llm @p232 | — |
| `receivables_aging` | <31d 11,433 / 31-60d 1,796 / 61-180d 1,056 / >180d 3,998 / 合计 18,283 | llm @p229 | — |
| `related_party_receivables_payables` | 与联营/合营往来（注 18、19，叙述） | llm @p269 | 仅文本 |
| 核心主干 | `net_profit` 11,841 · `operating_cash_flow` 62,567 · `capital_expenditures` -20,835 · `dividends_paid` -8,518 · `repurchase_of_stock` 0 · `cash` 143,748 · `st_borr` 38,416 · `lt_borr` 229,699 | yahoo | A 级（clean_present） |

## 2. 🟠 仍开放且与价值投资相关

| 字段 | live 状态 | 影响 / 处置建议 |
|---|---|---|
| `gross_profit` | unresolved_conflict（yahoo 139,204 被选，但 akshare↔yahoo 口径冲突、HK 口径未验证） | 毛利率 / 盈利质量。**需口径决策**（采哪种 cost 口径），非加别名可解 |
| `interest_bearing_debt_parent_company` | **仍 missing**（LLM found=false；p271 母公司表无借款行）。运行**未**标 `absence_means_zero` | 仅影响母公司/控股层 SOTP 杠杆，非核心 net_cash_ratio。数据支持挂 `absence_means_zero`（LLM 已确认 section 完整无该行）——**低成本可闭环，但尚未做** |
| `fv_value_chg_gain` | missing（利润表 chunk p132 未进上下文）——**检索缺口**，非 issuer 缺失 | 利润质量；扩检索窗口/别名可解 |
| `stock_based_compensation` | missing（披露"不重大"、无数字） | 稀释质量；可挂 flag 记 N/A 闭环 |
| `other_cur_assets` | missing（无独立"其他流动资产"行） | 需派生（合并行 − trade receivables）或语义映射决策 |
| `selling_general_administrative` | terminal_unverified（yahoo 16,491，pdf_required 未达成） | note 8 组分可拼 PDF 佐证完成验证 |
| `time_deposits_or_wealth_products` / `contract_liabilities_non_current` | missing | HK 报表本就不单列；后者仅流动有值（current = -5,321） |
| `rd_exp` | missing（source_unavailable，**未**标 not_in_scope） | 与已终态的 `capitalized_rd` 不一致；应一并终态化（HK 综合企业不单列研发） |

## 3. ⚪ 终态 / 非缺口（not_in_scope，停止当缺口看）

`c_pay_to_staff`、`receiv_tax_refund`、`capitalized_rd` —— IFRS/HK 报表无对应行，ledger 7 家 HK issuer 全 no_hit。

## 4. 需要点名的两个校正（运行态 vs 人工裁决态）

1. **`restricted_cash`**：live 运行里它只是 **"no chunks matched aliases"（检索未命中）**，字段目录为空；本次运行输出**不包含**"1,571M 是 Note 36 质押资产、非现金"那段推理（那是规划 doc 的人工核查结论）。
   - **下游结论一致**：无受限现金 → 净现金不扣减（00001 现金质量结论反而更干净）。
   - **但裁决未固化进 pipeline**：运行态仍是"未命中"。
   - **结论**：不再重加别名（任何命中 p59 那句的别名都会重现"质押资产→受限现金"误归因）；若要"抵押资产"信号，应另立**新字段 `pledged_assets`**，与现金质量分开。建议把该裁决写进 catalog（标 not_applicable + reason）以消除运行态与裁决态的差异。

2. **数据分层**：`warning_classification.json` 是早期 source-policy 阶段（会把 LLM 补充字段标 missing）；`evaluation.json` 是 supplement 之后的最终分类（标 `llm_supplement_present`）。本 doc 以 **`evaluation.json` + per-field 抽取 JSON** 为权威，避免把早期阶段或快照状态当现状。

## 5. 对价值投资分析的净结论

经 live 刷新，**核心价值信号已基本不被卡住**：

| 信号 | 依赖 | 状态 |
|---|---|---|
| `owner_earnings` / 正常化盈利 | OCF − capex；`non_recurring` 正常化 | ✅ non_recurring 现已 present（上轮误判的头号限制项，实际已解，且更深两个根因也修了） |
| R / GG 的 buyback 项 | `repurchase_of_stock` + 注销链 | ✅ repurchase=0 + 注销确认 → 合法置 0 |
| `payout_M` | dividends_paid / net_profit / commitment | ✅ 数据 present；commitment 已在下游派生（TradingAgents-CN PR #31） |
| `net_cash_ratio` | cash + 有息债务(st+lt+bond) | ✅ present；restricted_cash 无 → 不扣减 |

**真正仍限制"分析深度"的收敛为三项**：① `gross_profit` 口径决策；② `interest_bearing_debt_parent_company` 挂 absence_means_zero（低成本，未做）；③ 少量利润质量/BS 颗粒度字段（部分检索缺口如 `fv_value_chg_gain`，部分应终态化如 `rd_exp`）。**核心买卖结论级别的缺口已基本清掉。**

## 6. 建议下一步（按 ROI）

1. `interest_bearing_debt_parent_company` 挂 `absence_means_zero`（p271 已实证 section 完整无借款行）——最低成本闭环。
2. `restricted_cash` 在 catalog 标 not_applicable（00001 HK，reason=Note 36 质押资产≠受限现金），固化人工裁决；如需抵押资产信号另立 `pledged_assets`。
3. `rd_exp` 终态化（与 `capitalized_rd` 一致，HK market NA）。
4. `fv_value_chg_gain` 扩检索（P&L 页进上下文）；`stock_based_compensation` 挂 flag 记 N/A。
5. `gross_profit` 单独立项做口径仲裁（三方口径定义决策）。
