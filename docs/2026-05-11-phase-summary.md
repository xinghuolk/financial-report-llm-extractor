# 阶段性总结 — Source-First 财报抽取器

> 日期: 2026-05-11（首发）；2026-05-12 增补 Wave 8 catalog gap closure (G1-G4-C)。
> 当前快照: G4-C feature branch `feature/g4-phase-c-audit-opinion-and-dividend-policy`
> @ `3e89f7f`（待 PR），main 含 G1-G3 (PR #3 `3fbcdfd`)。
> 作为 `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
> 的 TOC 入口，不替代它。

## TL;DR

- **架构转向已完成**: PDF-first LLM 抽取器 → source-first
  （AKShare/Yahoo → reconciliation → source policy → PDF/LLM supplement）。
- **Catalog**: 15 → **68 mapped 字段** (P0:22 + P1:11 + P2:12 + P3:21 + P4:2)；
  另 4 P4 字段在 taxonomy/coverage_matrix 但不映射 = 显式 out-of-project-scope。
  Wave 8 G1-G4-C 闭合 Turtle v0.15 phase3 catalog gap (Group A-D + 部分 E)。
- **覆盖率**（post-G4-C, /68）: CN 600519/2024 **79%** (54/68 含 LLM)；CN
  300750/2024 **81%** (55/68)；HK 01810/02498 **72%** (49/68)；HK 06862
  **71%** (48/68)；HK 00001/01113/09987 见 §3 表（pre-G4-C 基线值）。
- **HK trust policy 多币种闭环**: trust 验证 sample 数 14 → **58**（4x 增长）；
  9 HK 字段全 PDF-verified per-issuer（HKD/CNY/USD）。
- **G3/G4-C alias retrieval ranking fix 模式**: HK 报告用与 CN 完全不同的措辞
  ("Financial position of the Company" / "in our opinion" 等)。首版 G3/G4-C
  aliases 全是合并/CN 措辞，HK retrieval 召回错误章节；补 9-12 个 HK-specific
  anchor aliases 后 hit rate ~0% → 7/7 (G3) / 5/5 (G4-C)。
- **纪律**: **594 tests** 通过，ruff + mypy clean，drift §177 严格执行
  （无 silent promotion，sample-verified 规则强制 PDF spot-check）。
- **§7 5 项 branch completion criteria**: 5/5 ✅ 满足。G1-G3 PR #3 已合并到 main；
  G4-C 待 PR。

## 1. 阶段时间线（按 wave 分组）

仓库从 bootstrap 到当前状态共 **12 个日历日**（2026-04-30 → 2026-05-11，
328 commits，日均 ~27 个）。30+ phases 收敛为 7 个 wave：

| Wave | 日期 | Phases | 产出 |
|------|------|--------|------|
| **1. 基础设施** | 04-30 → 05-02 | bootstrap, Phase A (mapping artifacts), Phase B (artifact hardening), Phase C (AKShare contract) | Frozen dataclass 核心；PDF ingestion/chunking/retrieval；provider artifact store；AKShare/Yahoo adapter 骨架。 |
| **2. HK Provider 语义** | 05-07 → 05-08 | Phase M2–M5 (HK 15-field terminal closure, Yahoo trust policy, defer_tax_liab proof, gross_profit terminal) | HK Yahoo trust scope 通过 sample-verified 规则确立；gross_profit + defer_tax_liab 终态化。架构上诚实的"unverified"桶优先于强行 promotion。 |
| **3. Catalog 扩展** | 05-08 → 05-09 | Phase N0–N4 (consistency gate + 15 → 33 → 44 字段), Phase I-C/I-C.1 (12 P3 text-mode + whitespace fix → 56 字段) | Catalog 达到 56 字段；跨文件 JSON 一致性 gate (`test_catalog_consistency.py`)；6 家 HK 公司 P3 LLM 命中率 33/84 (39%)。 |
| **4. LLM 与 PDF 桶** | 05-08 → 05-09 | Phase H0 (null_means_zero), Phase H1 (surgical conflict, 部分回滚), Phase I-D/I-A/I-A.2 (HK notes LLM + 6 follow-ups) | LLM 框架接入并支持 confidence 校准；invest_income alias 扩展 0/6 → 5/6 (83%)；H1 部分回滚保留架构诚实性，拒绝伪 33/33 覆盖率。 |
| **5. Orchestrator 与 CN 精修** | 05-09 → 05-10 | Phase EC (evaluate-company), Phase H2/H2.1/H2.2/H2.3#3/H2.4 (CN/HK conflict 解决, 加法 derivation, 多公司验证, fixture 持久化, 累计 review 修复) | 6-bucket 评估分类；period 归一化清除 41% 假冲突；4 家 CN 公司 × 4 字段 = 16 EXACT samples 背书 H2 promotions；600519 P0+P1 达到 **33/33 (100%) clean**。 |
| **6. HK 集群锁** | 05-10 → 05-11 | Phase HK-coverage discovery (HK-A scope 崩塌), Phase HK-C (industry_not_applicable), Phase HK-LLM-2/C (6 HK supplement merge), Phase HK-B.1-.4 (4 字段 × 6 公司 conflict shape 锁) | HK-A "alias gap"假说经实证崩塌为 ~0 cells（adapter 实际缺字段）。4 家新 HK fixture 实时拉取（01810/02498/06862/09987）。24 条 named shape-lock 断言防止 HK-B 候选字段被静默提升。 |
| **7. Catalog Verification + HK Trust Policy 多币种闭环** | 05-11 | Phase MX (matrix audit 24/62→35/62), Phase HK-B.5 (acct_payable 6 HK) + .5 review fix (per-issuer allowlist 机制), Phase HK-B.5.1/.5.2/.5.3 (adapter currency map → fixture backfill + multi-currency schema → revenue/net_profit recovery), Phase HK-B.6 (fix_assets), Phase HK-B.7 (5 BS 字段 traceability), Phase HK-B.8 (accounts_receiv) | HK 6 公司 currency-label 由 hardcoded HKD 修复为 issuer reporting currency（CNY/USD）。Trust 规则架构升级支持 `additional_trusted_currencies` + `pdf_verified_company_ids` allowlist。**9 HK 字段** (acct_payable / revenue / net_profit / fix_assets / accounts_receiv / total_assets / total_liabilities / total_cur_assets / total_cur_liab / inventories) 全 PDF-verified per-issuer。Trust samples 14 → 58。HK-B.4 `gross_profit` 保持 terminal_unverified（无 PDF anchor）；HK-B.6 `fix_assets` 01810/02498 仍 single-source clean（非 allowlist 内，避免 wrong-currency claim）。 |

**过程中的关键反转**

- **H1 部分回滚**：revenue/operating_profit/SGA 的 alias 替换在合并前撤销
  —— 那本会通过静默的语义改动让 600519 看起来达到 33/33，违反 source-first
  原则。由 H2/H2.1/H2.2 通过显式 PDF + 多样本证明重新建立。
- **HK-A scope 崩塌**：recon 前预估"alias 扩展能修 16 cells"。实证 recon
  发现 adapter 结构性缺失这些字段 → 修正为 ~0 cells。记录在
  `docs/phase_hk_coverage_discovery.md`。
- **"LLM wiring 缺失"误读**：B-recon (`docs/phase_hk_llm_recon.md`) 发现
  orchestrator 已经接好；表面上的"0 supplement"是 UX/流程问题
  （未传 `--pdf --llm-config`），不是工程缺陷。
- **HK currency-label "mirage" 修正（Phase HK-B.5.2）**：Yahoo HK adapter
  把所有 HK 公司 currency hardcode 为 HKD，掩盖了非 HKD reporter (Xiaomi/Anta/
  Yum 等) 的实际报告币种。HK-B.5 PDF spot-check 引出 currency-label review，
  揭示之前部分 baseline clean cells 是 wrong-HKD-label 误触发 HKD trust policy
  造成的"mirage"。HK-B.5.2 backfill 修正诚实状态（-8 cells），HK-B.5.3 用
  PDF-verified multi-currency support 恢复（+8 cells，但 provenance 更
  honest）。最终架构：trust 规则多币种 + per-issuer allowlist，drift §177 严格。
- **HK-B 实际 promotion 范围**：recon 原本建议 acct_payable/fix_assets 谨慎、
  accounts_receiv/gross_profit 保守。后续 PDF spot-check 实证发现 5 of 6
  HK 字段全可 promote（acct_payable 6, revenue 6, net_profit 6, fix_assets
  4, accounts_receiv 6）；只有 gross_profit 经 recon 确认保守（HK 利润表无
  GP 行）。01113 "Creditors" / "Debtors" 是物业公司 HK/UK GAAP 命名约定，
  并非数据缺失。 |

## 2. 架构现状

**当前 source-first 链路**（每一步箭头都在代码层强制执行）：

```
AKShare HK/CN + Yahoo HK/CN
   ↓  (source_inventory_fetch.py — 实时拉取或 fixture replay)
SourceInventoryRecord  (ticker, period, raw_field_code, raw_value, source, currency, unit)
   ↓  (mapping.py — catalog 驱动、market-scoped、derivation-aware)
MappedTurtleField  (每个 turtle 字段，全部候选带 provenance)
   ↓  (reconciliation, source_policy.py — sign_normalize, provider_semantics, period norm)
SourceFirstExportItem  (selected_source + candidates + warnings)
   ↓  (company_evaluation.py classify_field — 6-bucket cascade)
6-bucket: clean_present / llm_supplement_present / unresolved_conflict
        / terminal_unverified / not_in_scope / source_unavailable
   ↓  (可选，由 --pdf + --llm-config 启用)
LLM evidence supplement 合并  (selected_source="llm" 用于 missing-candidate 单元)
   ↓
final_export.json + evaluation.md
```

**原 PDF/LLM 管线保留为 fallback 基础设施**：`ingestion.py` (pdftotext)、
`chunking.py` (BlockRecords + statement maps)、`retrieval.py` (field-first
alias-scored top-k)、`extraction.py` (FakeLlmClient + real transport)、
`llm_field_extraction.py`、`llm_extraction_runner.py`、
`llm_extraction_batch.py`。LLM 路径现在是**有界、field-scoped、opt-in**——
不再是宽泛的 PDF 检索。

**模块边界纪律**

- `evaluate-company`（orchestrator，per-(company, period)，可选 LLM）
  对比 `replay-provider-baseline`（fixture-only 批量）
- `MarketSourcePolicy.sign_normalize` 是 market-scoped 的（raw vs absolute）
- `SourceMappingEntry.by_market_aliases` 和 `derivation_markets` 在不重复
  代码的前提下强制 CN/HK 分离
- `IndustryNotApplicableSpec` 让单一字段携带 per-(market, ticker) 的
  not_in_scope 原因（如 01113 地产 SGA 习惯），无需在 catalog 中分叉

## 3. 覆盖率里程碑

**Post-G4-C 实测 (2026-05-12, 5 公司)**：

| 公司 / 期间 | Reporter | source-first clean | +LLM | 备注 |
|------------|----------|------------------:|-----:|------|
| CN 600519 / 2024 | CNY | 42/68 (62%) | **54/68 (79%)** | G4-C 命中 audit_opinion + dividend_policy_text |
| CN 300750 / 2024 | CNY | 42/68 (62%) | **55/68 (81%)** | CATL，新增 cohort |
| HK 01810 / 2024 | CNY | 35/68 (51%) | **49/68 (72%)** | G3 cash/equity_invest + G4-C 全命中 |
| HK 02498 / 2024 | CNY | 35/68 (51%) | **49/68 (72%)** | 同上 + amounts_due 命中 |
| HK 06862 / 2024 | CNY | 35/68 (51%) | **48/68 (71%)** | G3 interest_bearing_debt 唯一命中 + G4-C 命中 |

**Pre-G4-C baseline (未在 G4-C catalog 下重测，值为保守估计)**：

| 公司 / 期间 | Reporter | source-first clean | +LLM (pre-G4-C) | 注 |
|------------|----------|------------------:|-----:|----|
| HK 00001 / 2025 | HKD | 32/68 (47%) | 44/68 (65%) | G3 4/4 命中已锁；G4-C 待重测 |
| HK 01113 / 2025 | HKD | 33/68 (49%) | 41/68 (60%) | G3 命中已锁；G4-C 待重测 |
| HK 09987 / 2024 | USD | 34/68 (50%) | 44/68 (65%) | G3 命中已锁；G4-C 待重测 |

`test_phase_hk_llm_2_supplement_merge.py` 锁定 G1-G3 catalog 下的 baseline 计数。
G4-C 测试未补 (loose end #2)。

**HK Yahoo Trust Policy 多币种规则覆盖（post-HK-B.8）**：

| 字段 | Allowlist | Samples | 备注 |
|---|---|---:|---|
| revenue | 6 HK | 6 | HKD/CNY/USD reporter 全 PDF-verified |
| net_profit | 6 HK | 6 | 用"attributable to owners"行，正确排除 NCI |
| acct_payable | 6 HK | 6 | 01113 "Creditors" / Yum "Accounts payable" 均匹配 |
| accounts_receiv | 6 HK | 6 | 09987 用 Yahoo "Accounts Receivable" $79M, 非 "Receivables" $316M |
| fix_assets | 4 HK | 4 | 01810/02498 因 PDF-Yahoo 实质偏差排除，仍 single-source clean |
| total_assets | 6 HK | 5 | BS aggregate，traceability |
| total_liabilities | 6 HK | 5 | 同上 |
| total_cur_assets | 6 HK | 6 | 同上 |
| total_cur_liab | 6 HK | 6 | 同上 |
| inventories | 6 HK | 6 | 同上 |
| **合计** | — | **58 PDF-verified samples** | 14 → 58 = 4x 增长 vs Phase H1 baseline |

**Catalog 增长**

| 时点 | 字段数 | 驱动 |
|------|-------|------|
| Wave 1 baseline | 15 | 传统 Turtle 最小集 |
| Post-N1–N3 (05-08) | 33 | P0:22 + P1:11 扩展 |
| Post-N4.A–.C (05-09) | 44 | + 8 P2 source-first + 1 P2 LLM + 2 P3 |
| Post-I-C (05-09) | 56 | + 12 P3 text-mode pdf_only |
| Post-G1a/G1b (05-12, PR #3) | 61 | +3 CN-direct P2 + 2 contract_liabilities P3 split |
| Post-G2 (05-12, PR #3) | 62 | +1 P3 non_recurring_items_breakdown text |
| Post-G3 (05-12, PR #3) | 66 | +4 P3 parent-company-only SOTP fields |
| **Post-G4-C (05-12, 待 PR)** | **68** | +2 P4 pdf_only (audit_opinion + dividend_policy_text) |

剩 4 P4 字段在 taxonomy/coverage_matrix 但 source_mapping_minimal 不引用 = 显式
out-of-project-scope (mda_business_review / mda_forward_guidance / mda_risk_factors
段落级文本下游做；auditor_change_history 多期 inherently 下游)。详见 §6。

**Sample-verification 广度**

- 4 家 CN 公司 × 4 个被提升字段 = **16 EXACT samples**
  （`provider_raw_semantics_cn.json` + `provider_field_baseline_h2_2_extension/`）
- 6 家 HK 公司 × 10 个 trust-promoted 字段 = **58 PDF-verified Yahoo HK samples**
  （`hk_yahoo_trust_policy.json`，post-HK-B.8）
- 6 家 HK 公司 × 14 个 P3 字段 = **84 次 LLM 尝试，33 present (39%)**
  （`tmp/runs/phase_i_c_validation_v2/`）
- 6 家 HK 公司 × 4 个 HK-B 字段 = **24 条 named shape-lock 断言**
  （`tests/test_phase_hk_b_*.py`；post-HK-B.6/.8 部分形态已变 promoted）
- HK fixtures: 2 (baseline) + 4 (HK 6 extension) = **6 家 HK 公司持久化**
- **G3 validation breadth (Wave 8)**: 7 家公司 × 4 G3 fields = **28 G3 hit/miss
  evidence**，全 PDF-validated（`docs/roadmap/...md` §G3 Implementation Result）。
  Hit matrix: cash 7/7, equity_invest 7/7, amounts_due 4/7, interest_bearing_debt
  1/7（06862 海底捞 唯一正向）。低命中率全是 issuer-level 数据稀疏。
- **G4-C validation breadth (Wave 8)**: 5 家公司 × 2 G4-C fields = **10 G4-C
  hit evidence**, 5/5 + 5/5 完美命中。HK opinion-paragraph anchor aliases
  补完后 retrieval 100% 准确指向正确章节。

**测试数增长**：~50 (bootstrap) → 450 (H0) → 524 (H2) → 552
(HK-LLM-2 initial 3-co) → 587 (post HK-B.1-.4 + HK-LLM-2/C) → **594
(post HK-B.5 → .8 multi-currency closure)**。Wave 8 G1-G4-C 落地未引入新 test
（catalog 改动复用既有 test_field_metadata + test_catalog_consistency framework；
test_phase_hk_llm_2_supplement_merge baseline counts 已 updated）；G4-C
"intentionally unmapped P4 4 fields" regression test 未补（loose end）。

## 4. 方法论快照

以下模式已成为项目运作的标准——既写入 spec 文档，也由测试强制执行：

- **Drift §177 sample verification**：要提升一个候选值的
  `provider_raw_semantics` 规则，必须有 ≥2 家公司 + PDF spot-check 才能
  写入 catalog。H2.2 用 4 公司 × 4 字段的矩阵背书 4 条 CN 提升规则。
  HK-B recon 显式引用该规则，拒绝把 provider-provider 一致性当作
  `gross_profit` 的充分证据。
- **TDD RED → GREEN → commit 节奏**：每个 phase 都有 spec doc + plan doc
  + 实现 commits + 验证报告 + roadmap 更新。`git log --oneline` 可查最近示例。
- **Regression-lock 模式**：偏好形态锁（如 HK-B `3 clean / 3 conflict`），
  避免计数阈值（如 `≥2 clean`）。HK-LLM-2 锁定确切的
  `llm_supplement_present` 字段集，确保 catalog 改动若静默重分类会以
  named 形式暴露。
- **"诚实路径"优于宽容门控**：H1 revert、HK-A 崩塌、HK SGA → terminal_unverified
  都是架构真相优先于数字覆盖率的例子。
- **Fail-loud 解析**：`IndustryNotApplicableSpec` JSON loader 对畸形条目
  抛 `ValueError`；`provider_semantics` catalog 合并在 alias 冲突时失败；
  `MoneyNormalizationError` 绝不静默吞噬。
- **Field-first 检索**（不做宽泛 PDF LLM）：alias 评分 + statement-map 提示
  给出 top-k 有界 evidence；whitespace 归一化（I-C.1）通过解决 PDF 排版换行
  问题悄然提升命中率 30 → 33。
- **Subagent 驱动研究 / 单 prompt 综合**：复杂审计（HK-B recon、本总结、累计
  review）委托给 Explore agent 收集数据；主 agent 负责综合。

**违反-纠正的典型时刻**

- H0 review：`null_means_zero` 缺审计 trail → 添加 `review_notes` 字段。
- H2 review：derivation 未做 market 分离 → H2.4 添加 `derivation_markets`。
- H2.4 Finding #2：derivation operand 跳过 `unit_multiplier` → 修复为经过
  `normalize_money()`。
- EC Tier 1：period 字符串不匹配导致 41% 假冲突 → reconciliation 前先做
  period 归一化。
- **HK-B.5 review (currency-label)**：HK trust policy 在 Yahoo HK adapter
  hardcoded HKD label 下广播 promote，对 RMB/USD reporter 产出 wrong-currency
  clean claim。修复链：HK-B.5 加 `pdf_verified_company_ids` 排除 09987 →
  HK-B.5.1 加 `HK_ISSUER_FINANCIAL_CURRENCY` map → HK-B.5.2 fixture backfill
  + `additional_trusted_currencies` schema → HK-B.5.3/.6/.8 用 PDF-verified
  per-issuer samples 覆盖 9 字段。
- **HK-B.6 fix_assets ROU semantic ambiguity**：Yahoo Net PPE conflate
  PP&E + Right-of-use assets per HKFRS 16。4 of 6 HK 公司 PDF 显示
  Yahoo = PP&E + ROU within rounding；01810/02498 实质偏差不入 allowlist。
  保留 single-source clean，避免引入未 verified 的语义。
- **Phase MX coverage matrix audit**：发现 catalog `verification` 字段
  漂移（24/62 verified vs 实际 PDF-evidenced 多），36/62 提升至 verified
  无 runtime 改动，仅 catalog hygiene。期间 `bad_debt_provision` 因
  primary_route invariant 卡住（仅 LLM 证据但 route 标 yahoo_direct），
  保留 expected 状态等待后续修正。

## 5. 当前状态

**§7 branch completion criteria**（2026-05-11 验证）：

1. ✅ Source-first 作为主方向（codified in design docs）
2. ✅ Phase ordering: Taxonomy → Coverage Matrix → Minimal Mapping → Adapters
3. ✅ PDF/LLM 作为有界 selected-field fallback
4. ✅ 既有 PDF/LLM phases 保留为 fallback 基础设施
5. ✅ Source priority chain 在 design / requirements / roadmap 之间表述一致

**分支状态**
- `feature/source-first-roadmap-requirements` @ `d05bf7f`
- 自 bootstrap（`c4fcbd6`，2026-04-30）共 **328 commits**
- **比 `main` 领先 320 commits**（main 仍在 bootstrap 附近）
- 本地领先 origin/feature ~9 commits（自 Phase MX 起未 push）
- **594 tests passing，1 skipped (real-LLM smoke)，0 failing**
- `uv run ruff check .` clean（line-length 88，py311）
- `uv run mypy src tests` clean（`disallow_untyped_defs = true`）
- coverage matrix verified: **36/62**（Phase MX +11，HK-B.5 +1；其余 expected 多为 P3/P4 LLM/notes-only 字段）

**56 字段 catalog 分布**
- P0: 22（利润表 + 资产负债表核心）
- P1: 11（现金流、股息、D&A、利息、税、SBC）
- P2: 9（应收应付存货变动、capex、回购、税返）
- P3: 14（5 money 型：cap_rd/interest、restricted_cash、time_deposits、dps；
  9 text 型：dividend_plan、receivables_aging、related_party、
  contingent_liabilities、lease_liability_maturity、segment_revenue_profit、
  buyback_cancellation_progress、bad_debt_provision、…）

**6-bucket 评估分类**（`company_evaluation.classify_field`）：
`clean_present`、`llm_supplement_present`、`unresolved_conflict`、
`terminal_unverified`、`not_in_scope`、`source_unavailable`。

## 6. 未决项

roadmap 或 recon 文档中明确标记为 deferred / requires-decision 的事项
（已更新反映 Phase HK-B.5 → .8 完成后状态）：

| 项目 | 状态 | 来源 | 下一步动作 |
|------|------|------|-----------|
| HK-B `acct_payable` | **HK-B.5 已 promote 6 HK** ✓ | `docs/phase_hk_b_5_recon.md` | 完成（multi-currency trust rule + per-issuer allowlist）。 |
| HK-B `fix_assets` | **HK-B.6 已 promote 4 HK**；01810/02498 仍 single-source | `docs/phase_hk_b_5_recon.md` Phase HK-B.6 section | 01810/02498 PDF-Yahoo Net PPE 实质偏差（-22% / 2.9%）— 需要更深入 issuer-specific 分析才能判断是否扩展 allowlist。 |
| HK-B `accounts_receiv` | **HK-B.8 已 promote 6 HK** ✓ | 同上 | 完成。注意 Yum China 用 Yahoo "Accounts Receivable"（$79M）而非 "Receivables"（$316M broader）—— source mapping alias 选对了。 |
| HK-B `gross_profit` | 仍 terminal_unverified（HK-B.4 锁） | `docs/phase_hk_b_recon.md` | recon 明确不 promote：HK 利润表无 GP 行，provider-provider agreement alone 按 drift §177 不够。 |
| `defer_tax_liab` Yahoo HK 多币种 | HKD 1 sample，非 HKD issuer 无 Yahoo 数据 | HK-B.7 中标记 | Yahoo Deferred Tax Liabilities Non Current 在 4 非 HKD issuer 全无数据；无法多币种扩展。 |
| `bad_debt_provision` matrix verified | HK-LLM-2 lock 中 4 HK 命中，但 primary_route=yahoo_direct invariant 阻碍 promote 到 verified | Phase MX section | 需要把 primary_route 重构为 pdf_evidence 以反映实际 LLM 路径。 |
| Yahoo HK adapter live-detect financialCurrency | Phase HK-B.5.1 用 hardcoded map (6 公司)；未知 HK 公司仍 fallback HKD | HK-B.5.1 section | 用 `yfinance.Ticker.info.financialCurrency` 替代 hardcoded map，扩展到任意 HK ticker。 |
| ~~6 个检索信号弱的 P3/P4 字段~~ | **Wave 8 G1-G3 闭合** | roadmap G1-G3 sections | G1a/G1b/G2/G3 落地共 +10 字段（5 P3 + 4 P3-parent + 1 P2-split）。G3 4/4 alias 组 PDF-validated 跨 7 cohort。 |
| ~~**G4-C 4 字段 out-of-scope 信号 catalog 层缺机器可读 marker**~~ | **已关闭 (2026-05-13)** | G4-C 收尾 | 4 P4 字段 (3 MD&A + auditor_change_history) taxonomy description 加 `[Intentionally unmapped — out of project scope]` 前缀；coverage_matrix notes 同步；机器可读 marker 落地。 |
| ~~**G4-C regression test 未锁 4 字段不映射**~~ | **已关闭 (2026-05-13)** | G4-C 收尾 | `tests/test_catalog_consistency.py::test_p4_intentionally_unmapped_fields_stay_unmapped` 锁定 4 字段在 taxonomy + coverage_matrix 但不在 source_mapping_minimal，且 description 必须含 marker。 |
| ~~**CLAUDE.md cohort table 3 行 (00001/01113/09987) 未在 G4-C catalog 下重测**~~ | **已关闭 (2026-05-13)** | G4-C 收尾 | 全部 3 行已用 Codex `gpt-5.5` + G4-C catalog 重测：00001 +3 / 01113 +3 / 09987 -1。详情见 `docs/2026-05-13-subscription-llm-validation.md`。 |
| ~~**G4-C dividend_policy_text 精度未深 audit**~~ | **已关闭 (2026-05-13)** | Codex validation | Codex `gpt-5.5` 在 600519 上正确返回 `not_found`，reasoning 明确指出 DS 命中 "公司利润分配符合《章程》规定" 是合规声明非真 policy；DS 是 shallow false positive。 |
| Confidence threshold 校准值 | 框架已就位、值待定 | Phase I-A.2 follow-up #2 | 收集 ~50+ 人工标注的 (company, field) 对后定阈值。 |
| 跨更多 issuer 批量重验证 | 当前 6 HK + 4 CN (G3 7-cohort + G4-C 5-cohort 增量验证) | roadmap §7 follow-up | 在金融 / 能源等行业扩展。 |
| `_resolve_derivation_operand` period 等值断言 | deferred | H2.1 carryover | 添加显式 period-end 等值检查，防多期 operand 被静默累加。 |
| **R1 SQLite indexer (`data/extracted.db`)** | **已落地 (2026-05-13)** | R1 plan | New `cache/` module + `index` / `query` CLI commands. Indexes existing `tmp/runs/*/{evaluation,llm_evidence_supplement}.json` joined by field_id. `field_values` is latest-catalog-version only; `extractions` keeps history. Exit codes: 0=hit, 1=miss, 2=db not initialized. R2 (provider fetch cache) + R3 (LLM cache) + R4 (DB-aware `pipeline` command) follow in separate PRs. |
| **R2 Provider fetch cache** | **已落地 (2026-05-13)** | R2 plan | `tmp/.cache/{akshare,yahoo}/<cid>_<period>.json` content-addressed + 24h default TTL + embedded artifact blobs (cache hit replays into SourceArtifactStore). `--skip-if-cached` / `--no-cache` flags. Deduplicates AKShare/Yahoo network calls across CLI invocations. R3 (LLM cache) + R4 (DB-aware `pipeline` command) follow in separate tasks. |
| **R3 LLM call cache** | **已落地 (2026-05-13)** | R3 plan | `tmp/.cache/llm/<sha256>.json` content-addressed (SHA-256 of model + system_prompt + user_payload). No TTL — deterministic; catalog/model change → different hash → automatic miss. `--no-llm-cache` bypass. 4 transport clients (OpenAI/Gemini/Codex/Claude) all wired. R4 (DB-aware `pipeline` command) follows. |
| ~~合并分支到 `main`~~ | **G1-G3 PR #3 已合并** ✓ | — | G4-C feature branch 待 PR。 |

## 7. Onboarding 文档地图

未来 Claude / 人类读者应知晓的路径：

**权威文档**
- `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
  （1657 行，§1–§7，Phase Implementation Results 见 §5）
- `CLAUDE.md`（项目说明、覆盖率表、phase 索引）
- `AGENTS.md`（部分内容已被 33/56-field 扩展取代）
- `docs/2026-05-11-phase-summary.md`（本文件）

**设计 + drift 分析**
- `docs/design/2026-05-01-structured-data-source-first-financial-extraction-design.md`
- `docs/design/2026-05-07-source-first-architecture-drift-analysis.zh.md`
  （drift §177、sampling bias、terminal states——仍是关键参考）

**Phase 专属 recon / reality-check 文档**
- `docs/phase_hk_b_recon.md`（HK-B 4 字段在 6 公司的 conflict 形态；初版）
- `docs/phase_hk_b_5_recon.md`（HK-B.5/.5.1/.5.2/.5.3/.6 串联的 PDF spot-check
  + currency-label fix + multi-currency 扩展全程，是 Wave 7 的主 reality-check）
- `docs/phase_hk_coverage_discovery.md`（HK-A → ~0 cells 的实证）
- `docs/phase_hk_llm_recon.md`（LLM orchestrator 已 wired）
- `docs/2026-05-10-h2-hk-cumulative-review.md`（H2.4 已闭 3 项 H2 findings）
- `docs/2026-05-08-roadmap-evaluation.zh.md`（pre-H2 框架，数字已过期但分析仍有效）

**字段 catalog JSON**
- `field_catalog/turtle_v015_source_mapping_minimal.json`（56 字段，by_market，derivation）
- `field_catalog/turtle_v015_field_taxonomy.json`（完整 taxonomy，value_type，statement_type）
- `field_catalog/turtle_v015_coverage_matrix.json`（预期覆盖路径）
- `field_catalog/provider_raw_semantics_cn.json`（5 CN 提升 + 3 CN unverified 规则；多公司背书）
- `field_catalog/provider_raw_semantics_hk.json`（HK 终态规则 + HK SGA unverified）
- `field_catalog/hk_yahoo_trust_policy.json`（Yahoo HK 信任范围）
- 跨文件 gate: `tests/test_catalog_consistency.py`

**Regression-lock 测试**（谁守护谁）
- HK-B 形态锁（post-promotion）: `tests/test_phase_hk_b_{acct_payable,fix_assets,accounts_receiv,gross_profit}.py`
  （前 3 已从 conflict 形态升级为 multi-currency clean 形态；gross_profit 保留 conflict + terminal lock）
- 多公司 sample 回归: `tests/test_phase_h2_3_fixture_persistence.py`
- H2.4 累计 review 修复: `tests/test_phase_h2_4_review_fixes.py`
- HK LLM supplement 合并（7 公司）: `tests/test_phase_hk_llm_2_supplement_merge.py`
  （baseline counts 反映 HK-B.5 → .8 promotions）
- Catalog 一致性: `tests/test_catalog_consistency.py`
  （Phase MX 用 36/62 verification 状态过 gate）
- HK-C industry not-applicable: `tests/test_phase_hk_c_industry_not_applicable.py`
- HK Yahoo trust policy schema + 58 sample 数: `tests/test_hk_yahoo_trust_policy.py`
- HK issuer financial-currency map: `tests/test_source_inventory_fetch.py::test_hk_issuer_financial_currency_maps_known_reporters`
  + `tests/test_cli.py::test_fetch_source_inventory_hk_akshare_stamps_issuer_financial_currency`（parametrized 7 cases）

**Fixture 目录**
- `tests/fixtures/provider_captures/provider_field_baseline/`（00001、01113、600519 baseline）
- `tests/fixtures/provider_captures/provider_field_baseline_h2_2_extension/`（300750、601919、688008 CN 多公司）
- `tests/fixtures/provider_captures/provider_field_baseline_hk_llm_6_extension/`（01810、02498、06862、09987 HK）
- `tmp/runs/phase_i_c_validation_v2/{00001,01113,01810,02498,06862,09987}/llm_evidence_supplement.json`（LLM baseline，已为回归测试预放）
- `tmp/llm_configs/deepseek.json`（本地 LLM config）、`n4b_manifest.json`（HK 6 公司批量 manifest）

**CLI 入口**（`python -m financial_report_llm_extractor` 子命令）
- `fetch-source-inventory` — 实时拉取 AKShare + Yahoo 并持久化
- `evaluate-company` — per-(company, period) orchestrator（`--pdf --llm-config` 启用 LLM）
- `extract-llm` / `extract-llm-batch` — field-scoped LLM 抽取
- `replay-provider-baseline` — fixture-only 批量复演

**验证命令**

```bash
uv run pytest -v && uv run ruff check . && uv run mypy src tests
```

Per-(company, period) 实时工作流：

```bash
COMPANY=600519 YEAR=2024 MARKET=CN PROVIDERS=akshare \
  scripts/run-fetch-source-inventory.sh

COMPANY=600519 YEAR=2024 MARKET=CN \
  PDF_PATH=downloads/cn_stocks/600519/annual/2024_年度报告.pdf \
  LLM_CONFIG=tmp/llm_configs/deepseek.json \
  scripts/run-evaluate-company.sh
```
