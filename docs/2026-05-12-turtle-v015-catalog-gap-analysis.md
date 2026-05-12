# Turtle v0.15 phase3 vs 当前 catalog gap 分析

> Date: 2026-05-12
> Branch: feature/phase-c-unmapped-p3-p4-fields
> Author: Claude session (依据 Stock_Analyze_Prompts/turtle_framework/龟龟投资策略_v0.15/ 4 个 markdown 文件)
> Purpose: 在投入下一个 phase 之前，先对照外部 Turtle v0.15 投资分析框架确定本项目（数据收集层）的真实 catalog gap，区分**我们应该补**和**下游应该做**。

## 0. Scope 澄清（关键！）

**`financial-report-llm-extractor` 只做数据收集层**：
- 从年报 PDF + 结构化 provider 抽取**原始字段**到 structured JSON
- 输出含 `value / unit / currency / period / evidence / confidence`
- **不做**数值计算（Owner Earnings, FCF margin, ROIC, payout ratio, R%/GG%/II%/KK%）
- **不做**定量判断（买入/持有/卖出，安全边际，仓位矩阵）
- **不做**多年合并（time-series merge, YoY 计算）→ 由下游 Turtle Agent 拼接多年快照

因此，agent 之前列的 5 大 "gap"（多年 time-series、EV 口径双轨、Owner Earnings、SOTP、穿透回报）大多是**下游计算层 scope**，不是本项目责任。本文档只保留属于本项目的 **catalog 字段缺失** 部分。

## 1. 当前 catalog 状态

62 个字段（56 mapped + 6 unmapped P4 LLM-review），按 domain × priority：

| Domain | P0 | P1 | P2 | P3 | P4 |
|---|---:|---:|---:|---:|---:|
| **income_statement** | 6 (revenue, net_profit, operating_cost/profit, invest_income, rd_exp) | 5 (gross_profit, SGA, non_oper_income/exp, fv_value_chg_gain) | 0 | 0 | 0 |
| **balance_sheet** | 11 (cash, total_assets/liabs, equity, fix_assets, cip, inventories, accounts_receiv, acct_payable, st_borr/lt_borr, bond_payable, money_cap) | 6 (defer_tax_assets/liab, minority_int, other_cur_assets, total_cur_assets/liab) | 0 | 0 | 0 |
| **cash_flow** | 3 (operating/investing/financing_cash_flow) | 0 | 6 (capex, change_in_受/付/库, receiv_tax_refund, SBC) | 1 (interest_paid_cash) | 0 |
| **shareholder_return** | 0 | 0 | 2 (dividends_paid, repurchase_of_stock) | 3 (dps, dividend_plan, buyback_cancellation_progress) | 0 |
| **notes_and_mda** | 0 | 0 | 0 | 8 (restricted_cash, time_deposits, contingent_liab, lease_liability_maturity, receivables_aging, related_party, segment_revenue_profit, bad_debt_provision) | 6 ✗ (audit_opinion, auditor_change_history, dividend_policy_text, mda_business_review/forward_guidance/risk_factors — 全 llm_review 路径) |
| **accounting_adjustments** | 0 | 0 | 1 (depreciation_amortization) | 2 (capitalized_rd, capitalized_interest) | 0 |
| **合计** | **20** | **11** | **9** | **14** | **6 (✗ unmapped)** |

数据可靠度（基于 HK 9 公司 + CN 4 公司 PDF spot-check）：
- **P0/P1/P2** 大多 PDF-verified 或 deterministic clean（multi-currency trust policy 64 samples）
- **P3** 部分 pdf_only 仍依赖 LLM supplement（~50% hit rate）
- **P4** llm_review 路径**未实现**（6 字段全 `extraction_failed`）

## 2. v0.15 phase3 实际引用字段（按用途分组）

来源：`龟龟投资策略_v0.15/phase3_分析与报告.md` (1906 行) + `coordinator.md` (340 行)。

### 因子1A/1B — 定性筛选与商业模式（LLM-required）

| Phase3 用途 | 引用字段 / 数据点 | 当前 catalog 状态 |
|---|---|---|
| 一票否决：审计意见 | 审计报告文本、意见类型、强调事项 | `audit_opinion` (P4 llm_review) ⚠ catalog 有但未实现抽取 |
| 一票否决：审计师变更 | 5年审计师任期、变更次数 | `auditor_change_history` (P4 llm_review) ⚠ 同上 |
| 商业模式 | 各业务板块收入占比、利润来源 | `segment_revenue_profit` (P3) ✓ |
| 资本消耗强度 | Capex / 折旧、固定资产占比 | `capital_expenditures`, `depreciation_amortization`, `fix_assets`, `cip` ✓ |
| 收款模式 | 应收账款周转、合同负债趋势、应付账款周转 | `accounts_receiv`, `acct_payable`, `receivables_aging` ✓；**合同负债 ✗ 缺** |
| 护城河、周期性、人力资本、管理层、监管风险 | 多数从 MD&A / 公告 / 外部数据 | MD&A 4 字段（P4 llm_review）⚠ catalog 有但未实现 |

### 因子2 — Owner Earnings + 分配能力（Top-Down 计算）

| Phase3 用途 | 引用字段 | 当前 catalog 状态 |
|---|---|---|
| 归母净利润 | 归母净利、少数股东损益、非经常性 | `net_profit`, `minority_int`, `non_oper_income/exp`, `fv_value_chg_gain` ✓ |
| D&A | 折旧摊销 | `depreciation_amortization` ✓ |
| 资本开支总额 | 资本开支 | `capital_expenditures` ✓ |
| 维持性 Capex（行业系数）| 行业 E/D 中位数 | **下游计算**（不需 catalog 改动） |
| 5年 OCF/FCF/CFF | 三大现金流 | `operating/investing/financing_cash_flow` ✓ |
| 派息、回购历史 | DPS, 派息金额, 回购金额, 5年序列 | `dps`, `dividends_paid`, `repurchase_of_stock` ✓ |
| 支付率锚定（近3年中位数）| payout_ratio = dividends/net_profit | **下游计算** |
| 最新派息信号检测 | 最新 DPS vs 年报 DPS | **下游计算**（需要 catalog 提供单次 dps + Phase1 多源） |
| 上市主体现金 vs 集团现金 | 母公司单体现金 | ✗ 缺 (`cash_parent_company`) |

### 因子3 — 真实可支配现金 + 现金质量审计（Bottom-Up 计算）

| Phase3 用途 | 引用字段 | 当前 catalog 状态 |
|---|---|---|
| 真实现金收入还原 | 营收, AR 净变动, 合同负债净变动, 坏账 | `revenue`, `accounts_receiv`, `change_in_receivables`, `bad_debt_provision` ✓；**`contract_liabilities` ✗ 缺** |
| AR 核查 | AR 账龄、关联方占比 | `receivables_aging`, `related_party_receivables_payables` ✓ |
| 非经常性现金流分类（V1-V5）| 资产处置、政府补贴、保险赔款、投资收入 | `invest_income` ✓；**非经常性明细拆解 ✗ 缺**（`non_oper_income/exp` 仅聚合） |
| 经营支出还原 | 营业成本、员工支付、所得税、利息 | `operating_cost`, `interest_paid_cash` ✓；员工成本仅含 SG&A 聚合 |
| 资本开支与投资 | Capex、对外投资、资本化研发/利息 | `capital_expenditures`, `capitalized_rd`, `capitalized_interest` ✓；**对外投资明细 ✗ 缺** |
| HKFRS 16 租赁 / VIE | 租赁负债成熟、表外承诺 | `lease_liability_maturity`, `contingent_liabilities_commitments` ✓ |
| 现金储备质量 | 现金、定期/理财、受限现金、合同负债 | `cash`, `money_cap`, `time_deposits_or_wealth_products`, `restricted_cash` ✓；**`contract_liabilities` ✗ 缺** |

### 因子4 — 安全边际 + 估值决策

完全是下游计算（门槛、价值陷阱、安全边际、仓位矩阵），无 catalog 需求。

### 因子1B 模块九 — SOTP / 控股折价

| Phase3 用途 | 引用字段 | 当前 catalog 状态 |
|---|---|---|
| 母公司单体现金 | parent_company 口径 cash | ✗ 缺 (`cash_parent_company`) |
| 母公司有息负债 | parent_company 口径 st_borr + lt_borr + bond_payable | ✗ 缺 (`interest_bearing_debt_parent_company`) |
| 对子公司长期股权投资 | parent_company 口径 long-term equity investment | ✗ 缺 (`equity_investment_in_subsidiaries`) |
| 母子内部往来 | 应收子公司款项 | ✗ 缺 (`amounts_due_from_subsidiaries`) |

## 3. Gap 分类（filter 过本项目 scope 后）

### ✓ Hit（catalog 已覆盖 + 数据可靠）

所有 P0/P1/P2 字段（共 40 个）+ P3 中已 PDF-verified 的字段（contingent_liab, lease_liability_maturity, receivables_aging, related_party, segment_revenue_profit, bad_debt_provision, restricted_cash, time_deposits, capitalized_rd, capitalized_interest, dps, dividend_plan, buyback_cancellation_progress, interest_paid_cash）。

**评价**：phase3 因子2/3 计算所需的**结构化数值字段 ~85% 已 catalog 内 + PDF-verified**。

### ⚠ Catalog 有但抽取层有问题

**6 P4 llm_review 字段**（audit_opinion, auditor_change_history, dividend_policy_text, mda_business_review, mda_forward_guidance, mda_risk_factors）：
- catalog 已定义（taxonomy + coverage_matrix）
- **未被 source_mapping_minimal.json 覆盖**（unmapped）
- 当前 LLM extraction pipeline (`llm_field_extraction.py`) 为**结构化数值/带 anchor**设计，不适用于段落级定性文本
- phase3 因子1A/1B **明确依赖**这 6 个字段做一票否决 + 商业模式输入

**评价**：本项目 scope 内需要实现（不是 catalog 设计问题）。建实现 = 新建 `llm_review` 抽取路径。

### ✗ Catalog 缺失 + 本项目应补

按字段类别分组（priority 排序在 §4 优先级矩阵）：

**Group A — 与现有 56 fields 同模式的 provider-direct 字段**（最低风险）

| 字段 | priority | domain | value_type | source_mode | provider 验证 | phase3 用途 |
|---|---|---|---|---|---|---|
| **`c_pay_to_staff`** | P2 | cash_flow | money | direct | AKShare CN `PAY_STAFF_CASH` ✓ 验证过；Yahoo HK 待查 | factor3 step4 经营支出还原 — 员工现金支付 |
| **`c_paid_for_taxes`** | P2 | cash_flow | money | direct | AKShare CN `PAY_ALL_TAX` ✓ 验证过；Yahoo HK 待查 | factor3 step4 现金税款 |
| **`lt_eqt_invest`** | P2 | balance_sheet | money | direct | AKShare CN `LONG_EQUITY_INVEST` ✓ 验证过；Yahoo HK 待查 | factor1B 模块九 SOTP 子公司持股价值（**合并口径**，不同于 Group C 的 parent-only） |

来源参考：sister repo `report-collector/financial-report-analysis` 已实现这些字段（per `2026-04-22-turtle-v015-financial-field-gap-analysis.md` §0 "主表核心骨架已完成"列表），但本项目 catalog 未包含。

**Group B — current/non-current scope 分裂的字段**（schema 思考）

| 字段 | priority | domain | value_type | source_mode | provider 验证 | phase3 用途 |
|---|---|---|---|---|---|---|
| **`contract_liabilities`** | P3 | balance_sheet | money | direct | AKShare 02498 `合同负债` = 16.4M（current）；Yahoo `Non Current Deferred Revenue` = 01810 2.07B / 02498 68M / 00001 1M（**仅非流动**） | factor2/3 EV 双轨 + 现金质量审计 — 物业/白酒/SaaS 等先收款业务的"类现金" |

⚠ **关键 schema 决策**：Yahoo "Non Current Deferred Revenue" 与 AKShare "合同负债"**不是同一 scope**（Yahoo = 长期；AKShare = 流动/合并）。PDF 一般披露 current + non-current 两行 + total。需选其一：

- **方案 a**：加 1 个聚合字段 `contract_liabilities`（aggregate）+ derivation rule（current + non-current 求和），需新 schema 支持二级字段分组
- **方案 b**：加 2 个字段 `contract_liabilities_current` + `contract_liabilities_non_current`，trust policy 各自独立；下游 sum 时合并
- **方案 c**：加 1 个聚合字段 + 双 provider 都直接匹配 PDF 总和（要求 PDF 现成有 total 行）

推荐方案 b（最简洁，与现有 schema 兼容；下游 sum 比 catalog 内 derivation 更灵活）。

**Group C — 新 scope 维度的字段**（架构扩展）

| 字段 | priority | domain | value_type | source_mode | phase3 用途 |
|---|---|---|---|---|---|
| **`cash_parent_company`** | P3 | balance_sheet | money | pdf_only | factor1B 模块九 SOTP — 母公司单体现金 |
| **`interest_bearing_debt_parent_company`** | P3 | balance_sheet | money | pdf_only | 同上 — st_borr+lt_borr+bond_payable parent-only |
| **`equity_investment_in_subsidiaries`** | P3 | balance_sheet | money | pdf_only | 同上 — 对子公司长期股权投资 |
| **`amounts_due_from_subsidiaries`** | P3 | balance_sheet | money | pdf_only | 同上 — 母子内部往来 |

⚠ **关键 schema 扩展**：4 个字段都需引入新 metadata `scope_expectation: parent_company_only`。当前 catalog 假设所有字段都是合并口径（`scope_expectation: consolidated`）。这是真正的 catalog 维度扩展。

**Group D — 文本明细 / 文本聚合字段**

| 字段 | priority | domain | value_type | source_mode | phase3 用途 |
|---|---|---|---|---|---|
| **`non_recurring_items_breakdown`** | P3 | income_statement | text | pdf_only | factor3 step3 V1-V5 分类的**原始明细行**（金额、性质），分类判断由下游做 |
| (optional) `investment_activity_detail` | P3 | cash_flow | text | pdf_only | factor3 step5 对外投资明细（收购/参股/对外投资清单） |

**Group E — Catalog 已定义但未实现抽取的 P4 字段** (G4-C 实施 2026-05-12)

原始 6 字段评估 vs G4-C 实施决定：

| 字段 | 原 source_mode | G4-C 决定 | 理由 |
|---|---|---|---|
| audit_opinion | llm_review | **→ pdf_only 启用** | factor1A 一票否决核心；输出为审计意见段落 + opinion 类型（不需要 LLM 判断，纯 text 抽取） |
| dividend_policy_text | llm_review | **→ pdf_only 启用** | factor2 派息能力；输出为派息政策段落（纯 text 抽取） |
| mda_business_review | llm_review | 留 llm_review (未启用) | MD&A 业务回顾 2000-5000 字段落级；下游 Turtle Agent 已做定性判断；本项目集中抽取 ROI 低 |
| mda_forward_guidance | llm_review | 留 llm_review (未启用) | 同上 |
| mda_risk_factors | llm_review | 留 llm_review (未启用) | 同上 |
| auditor_change_history | llm_review | 留 llm_review (未启用) | **多期数据**——需 5 年审计师任期合并；本项目明确单期 scope，不可做 |

**关键架构洞察**（G4 实施时验证）：`llm_review.py` 模块用于 conflict adjudication 不是段落抽取；`source_mode=llm_review` 在当前 pipeline **未被消费**。原 gap doc 把 G4 估算为 "6-10h 新 module" 是过度评估——5/6 字段本质同 G2/G3 模式（更长 text + 强 anchor alias），只是被错误的 `source_mode` 标签隐藏。

**实施结果**：catalog 从 56 → 68 mapped 字段（G1-G4-C 合计 +12）。剩余 4 字段留在 taxonomy/coverage_matrix 但不映射 = **显式 out-of-project-scope 信号**——任何 evaluate-company 都不会处理它们，但 catalog 仍然描述了它们的"存在"。下游 Turtle Agent 自己用 PDF + LLM 抽取这 4 字段不会重复本项目工作（本项目根本没做）。

### ⊘ 看似 phase3 需要但实际是下游 scope

| Agent 之前列的 gap | 为什么不属于本项目 |
|---|---|
| 多年 time-series 架构（period_type: time_series, 数组结构）| 本项目只输出**单期 evaluation.json**；下游 `financial-report-analysis` P5 已实现 multi-year 拼接 |
| EV 口径双轨制 / Owner Earnings / 穿透回报率计算 | 下游 Turtle Agent 计算层；本项目只提供原始 component |
| 支付率锚定值（近3年中位数 + 信号检测）| 下游计算；本项目提供 dps + dividends_paid 多期单 evaluation |
| 安全边际 / 仓位矩阵 / 价值陷阱判断 | factor4 完全下游 |
| 维持性 Capex 系数（行业 E/D 中位数）| 下游 + 跨公司参考 |
| 股价分位 / 10 年历史 | Phase1 data_pack_market 提供（不是 PDF 抽取层）|
| 非经常性损益**分类**（V1-V5 保留/扣除标记）| 我们提供明细，下游判断分类 |

## 4. 优先级矩阵

按 (本项目 scope) × (phase3 关键性) × (implementation cost) × (provider 验证状态)：

| 阶段 | 内容 | Effort | 风险 | provider 已验证？ | phase3 影响 | 顺序 |
|---|---|---|---|---|---|---|
| **G1a** | 3 CN-direct fields (c_pay_to_staff, c_paid_for_taxes, lt_eqt_invest) — Group A | S (~1-2h batch) | 低（同 P2 cash_flow/BS 模式） | ✓ AKShare CN | factor3 经营支出 + factor1B SOTP（合并口径） | **1** |
| **G1b** | `contract_liabilities` 处理 current + non_current scope 分裂 — Group B | S-M (~2-4h) | 中（schema 思考：方案 a/b/c）| ⚠ 部分（Yahoo LT-only, AKShare current-only） | factor2/3 EV 双轨核心；先收款模式"类现金" | **2** |
| **G2** | `non_recurring_items_breakdown` (text pdf_only) — Group D | S-M (~2-3h) | 中（拆解 schema 设计：表格 row schema） | ✗ pdf_only | factor3 V1-V5 分类原始明细 | **3** |
| **G3** | parent_company_only scope 扩展 + 4 字段 — Group C | M (~4-6h) | 中-高（新 schema 维度 scope_expectation） | ✗ pdf_only | factor1B 模块九 SOTP；控股公司分析必备 | **4** |
| **G4** | 6 P4 llm_review 字段 + 新 extraction pipeline — Group E | M-L (~6-10h) | 高（新 module，输出 schema 与现有 numerical extraction 不同）| ✗ pdf_only 段落文本 | factor1A 一票否决 + factor1B 定性输入；架构投资大 | **5** |
| **G5 (optional)** | `investment_activity_detail` (text) — Group D 第二项 | S | 低 | ✗ pdf_only | factor3 step5 对外投资明细 | 6 |

**总投入估算（全部 6 阶段）**：~17-27h（小 phase 模式分多次 commit）。

**G1a 应先做的具体理由**：
- 唯一 **provider 数据已验证存在**的批次（AKShare CN `PAY_STAFF_CASH` / `PAY_ALL_TAX` / `LONG_EQUITY_INVEST` 都已在 600519 fixture 中确认）
- 3 字段同 P2 模式，可批量加 catalog + test 一次性搞定
- 低风险验证一遍现有 standard new-company add-field workflow
- 立即让 CN cohort cash flow + BS 完整度 +3 cells；HK 端待 Yahoo 字段查对后扩

## 5. 下一步建议

**严格按优先级 G1a → G1b → G2 → G3 → G4 顺序执行**，每个独立 commit + PR。

理由：
- **G1a 是 3 个 provider-direct 字段批量扩展**，与现有 56-field architecture 完全兼容；不动 schema；最低风险；唯一 provider 数据已验证
- **G1b contract_liabilities scope 分裂**，需要 schema 决策（current/non_current 双字段方案推荐）；中等复杂
- **G2 文本明细字段**，与现有 pdf_only text fields（如 receivables_aging）同模式
- **G3 引入新 schema 维度**（parent_company_only scope），是真正的 architecture 演进；应作为独立 phase 设计 + 测试
- **G4 是新 LLM extraction pipeline**（不同于现有 pdf_evidence numerical extraction）；本质是新 module，最重，最后做

不推荐做的事：
- ❌ 试图在本项目层做多年 time-series 整合 → 下游 scope
- ❌ 试图实现 Owner Earnings / EV 计算 → 下游 scope
- ❌ 把 6 P4 标 `not_in_scope` 删除 → 它们是 catalog 真实缺口，应该实现，不应 deletion
- ❌ 在 G1b 处理 current/non_current 时强行用 derivation 方案 → 增加 catalog 复杂度，下游 sum 更灵活

## 6. 与现有架构的契合

新增字段全部走已建立的标准流程：
- catalog 添加（taxonomy + coverage_matrix + source_mapping_minimal）
- 对应 trust policy + samples（若 provider 有数据；否则 pdf_only 走 LLM）
- `docs/new-company-analysis-workflow.md` 6-step workflow 适用
- regression test `tests/test_phase_*` 模式适用

**G1a 立即可做**（3 字段 batch）：
1. catalog 加 3 字段 (taxonomy + coverage_matrix + source_mapping_minimal) — AKShare alias 已知
2. 跑 4 CN 公司 (600519/300750/601919/688008) evaluate-company 验证 clean_present
3. HK 端：查 Yahoo HK 字段名（Cash Paid for Salaries / Tax Provision Cash Paid / Long Term Investments 等候选）
4. regression test (test_phase_*.py)
5. commit + PR

预期效果：CN cohort 立刻 +3 cells × 4 公司 = +12 cells；HK 端取决于 Yahoo 字段是否存在。

## 7. 验证已做的工作

写本文档时已 grep 验证：

| 检查 | 结果 |
|---|---|
| AKShare CN 600519 cash flow `PAY_STAFF_CASH` | ✓ 存在 |
| AKShare CN 600519 cash flow `PAY_ALL_TAX` | ✓ 存在 |
| AKShare CN 600519 BS `LONG_EQUITY_INVEST` | ✓ 存在 |
| AKShare HK 02498 `合同负债` | ✓ 存在（current only） |
| Yahoo HK `Non Current Deferred Revenue` 多公司 | 部分：**01810/02498/09987 有**；**00001/01113/06862 无**（00001/01113/06862 Yahoo 只有 `Non Current Deferred *Taxes*` Liabilities/Assets，是递延税款不是合同负债/递延收益——本表初版写错为"00001 ✓"已纠正） |
| sister repo `financial-report-analysis` 已实现这些字段 | ✓ 见 `2026-04-22-turtle-v015-financial-field-gap-analysis.md` §0 |

未验证但已知（待 G1a 实施时确认）：
- Yahoo HK 对应 `c_pay_to_staff` / `c_paid_for_taxes` / `lt_eqt_invest` 的字段名（可能用 `Cash Paid for Salaries` / `Cash Paid for Taxes` / `Long Term Investments`）
- HK 9 公司 + CN 4 公司各自 PDF 中是否清晰披露 contract_liabilities 当期 + 非流动数

## 参考

- 来源：`/Users/like/source/Stock_Analyze_Prompts/turtle_framework/龟龟投资策略_v0.15/`
  - `phase3_分析与报告.md` (1906 行) — 因子1-4 分析框架
  - `coordinator.md` (340 行) — 框架协调与产出
- 当前 catalog：`field_catalog/turtle_v015_*.json` 5 files
- 当前 phase summary：`docs/2026-05-11-phase-summary.md`
- 标准 workflow：`docs/new-company-analysis-workflow.md`
