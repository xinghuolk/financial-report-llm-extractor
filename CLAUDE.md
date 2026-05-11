# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作提供指引。

## 项目概述

独立的 LLM-first 财报抽取器，采用 **source-first 架构**：以 AKShare/Yahoo 等结构化 provider artifacts 为主，PDF/LLM 仅作为 evidence supplement 和 fallback。从年报中抽取 Turtle v0.15 字段目录数据，输出带 evidence、金额、单位、期间、置信度的结构化 JSON。与 deterministic `financial-report-analysis` 管线完全隔离。

## 常用命令

```bash
# 运行全部测试
uv run pytest -v

# 运行单个测试文件 / 单个测试
uv run pytest tests/test_models.py -v
uv run pytest tests/test_models.py::test_present_item_requires_evidence -v

# Lint 检查
uv run ruff check .

# 类型检查
uv run mypy src tests

# 完整验证（合并前必须通过）
uv run pytest -v && uv run ruff check . && uv run mypy src tests
```

包管理器为 `uv`。运行时零外部 Python 依赖（仅 stdlib）。开发依赖：pytest、ruff、mypy。外部 CLI 依赖：`pdftotext -layout`（来自 poppler）。

## 架构

### Source-First 管线

Provider artifacts (AKShare/Yahoo) → reconciliation & semantics proof → source policy → PDF/LLM 作为 fallback evidence supplement。Provider semantics sampled proof ≠ 最终逐公司 PDF evidence。

### 分阶段模块

| 阶段 | 模块 | 职责 |
|------|------|------|
| 0 | `models.py` | Frozen dataclass 核心合同：Evidence、MoneyAmount、ExtractedItem |
| 1 | `ingestion.py` | PDF → pages.jsonl + run_metadata.json（通过 pdftotext） |
| 2 | `chunking.py` | pages.jsonl → chunks.jsonl + BlockRecords |
| 3 | `retrieval.py` | Field-first evidence 检索，alias 评分排序 |
| 4 | `money.py` | 确定性金额解析（CNY/HKD/USD） |
| 5 | `extraction.py` | LLM 抽取管线（fake + real） |
| 6 | `llm_transport.py` | OpenAI 兼容 + Gemini transport |
| 7 | `evaluation.py` | 抽取结果审核与汇总 |
| M4 | `structured_sources/` | Provider 语义验证、HK Yahoo trust policy |
| M5 | `field_catalog/*.json` | defer_tax_liab Yahoo 证明 + gross_profit 终态降级 |
| N0 | `tests/test_catalog_consistency.py` | 5 个 JSON catalog 跨文件一致性 gate |
| N1-N3 | `field_catalog/turtle_v015_source_mapping_minimal.json` | 33 P0/P1 字段映射（CN 27/33, HK 20-21/33） |
| N4 | 同上 | P2 (9) + P3 partial (2) 扩展，共 44 字段 |
| I-A | `structured_sources/llm_extraction_runner.py` + `llm_extraction_batch.py` | HK notes-level LLM 抽取（field-scoped、bounded queue） |
| I-C | `llm_field_extraction.py` `_parse_response` | text-mode value_type 门控；catalog +12 P3 pdf_only 字段，total 56 |
| I-C.1 | `llm_extraction_runner.select_chunks` | alias_top_k 空白归一化（修跨 PDF 排版换行的 substring miss） |
| EC | `structured_sources/source_inventory_fetch.py` + `company_evaluation.py` | evaluate-company orchestrator：fetch-source-inventory + evaluate-company 两步 CLI；6-bucket 分类 + markdown；live 600519/2024 验证 conflict 三类（period 漂移 16 / sign 3 / 真语义差 5） |
| H2 | `MarketSourcePolicy.sign_normalize` + `provider_raw_semantics_cn.json` + `_apply_provider_semantics_promotion` (source_policy.py) | CN+HK conflict surgical resolution：sign_normalize=absolute (capex+interest_paid_cash) + PDF semantics promote (CN revenue+operating_profit) + terminal_unverified lock (SGA/D&A/dividends_paid)；600519 clean 34→38 |
| H2.1 | `mapping._derive_field` `+` 操作符 + `provider:RAW` operand + source_policy `derived` 分支 | catalog `derivation` 语法扩展为加法 + raw provider 字段引用；CN SGA = `akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE` PDF EXACT promote；600519 clean 38→39 |
| H2.2 | `SourceMappingEntry.by_market_aliases` + multi-sample provider_raw_semantics_cn + Sub-C clean-row candidate audit | (A) 4 CN companies × 4 fields multi-sample (300750/601919/688008 PDF EXACT) ；(B) HK SGA market-scoped Yahoo alias + 终态 unverified；(C) clean rows 显示双 provider 候选值 |

所有源码在 `src/financial_report_llm_extractor/`，测试在 `tests/` 中按阶段对应，字段定义在 `field_catalog/`。

### 核心合同

所有关键数据使用 **frozen dataclass** 并带显式 `validate()` 方法。关键不变量：
- `Evidence` 必须包含 page、chunk_id、block_id、snippet
- `MoneyAmount.normalized_value` 必须等于 `value * unit_multiplier`
- `ExtractedItem` 状态为 `present` 时必须有 evidence；money 类型还必须有 MoneyAmount
- 状态枚举：present / missing / ambiguous / not_applicable / extraction_failed

### Field-First 检索

不是"整个 PDF → LLM"。对每个字段，用 alias 评分 + statement hints 从 evidence index 中排序检索 top-k 候选 chunk。LLM 只看到 field-scoped bounded evidence。Document map / statement map 仅提供排序加分，不作为硬过滤。

## 关键规则

- **阶段边界严格**：ingestion、chunking、retrieval、extraction 是独立阶段，禁止混合逻辑。
- **每个 `present` 值必须有 source evidence**，并带显式 currency/unit/multiplier。
- **终态必须显式表达**：missing/ambiguous/not_applicable/extraction_failed——禁止静默遗漏。
- **Artifact ID 必须确定性**：基于 hash 或序列，禁止随机 UUID。
- **测试中禁止真实网络调用**：使用 FakeLlmClient + protocol 注入。
- **Provider-first**：未经 provider semantics proof，禁止直接提升 PDF 值。
- **严格类型**：mypy `disallow_untyped_defs = true`，ruff line-length 88，target py311。

## 文档导读

**先看**：`docs/2026-05-11-phase-summary.md` —— 阶段性快照（6 waves、coverage 表、未决项、onboarding artifact map），是进入分支的入口文档。

随后查阅 `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md` —— Bucket 1（H0 null_means_zero）、Bucket 4（terminal taxonomy）、Phase H1（surgical conflict resolution）、Phase I-A/I-A.2（HK LLM 抽取 + 6 follow-ups）、Phase N4（P2+P3 扩展）、Phase I-C（text-mode）、Phase I-C.1（whitespace 归一化）、Phase EC（evaluate-company orchestrator）、Phase H2（CN/HK conflict surgical resolution）、Phase H2.1（catalog 加法 derivation 解锁 CN SGA）、Phase H2.2（多公司 sample-verification + market-scoped source_aliases + clean-row candidate audit）均已落地。catalog 覆盖 56 字段（P0:22 + P1:11 + P2:9 + P3:14）。

**当前覆盖率（live evaluate-company，post-HK-B.6 fix_assets multi-currency verified）**：
- **CN 600519/2024**: source-first 39/56 (70%) clean → **+LLM 44/56 (79%)** ✓ regression-locked
- **HK 00001/2025 (HKD)**: source-first 30/56 (54%) + 1 terminal → **+LLM 35/56 (63%)** ✓
- **HK 01113/2025 (HKD)**: source-first 31/56 (55%) → **+LLM 35/56 (63%)** ✓
- **HK 01810/2024 (CNY)**: source-first 32/56 (57%) → **+LLM 39/56 (70%)** ✓
- **HK 02498/2024 (CNY)**: source-first 32/56 (57%) → **+LLM 37/56 (66%)** ✓
- **HK 06862/2024 (CNY)**: source-first 33/56 (59%) → **+LLM 38/56 (68%)** ✓
- **HK 09987/2024 (USD)**: source-first 31/56 (55%) → **+LLM 34/56 (61%)** ✓ (HK-B.6 fix_assets promoted)
- **Sample-verified breadth**: 4 CN 公司 × 4 promotion 字段 = 16 EXACT match samples
- **HK LLM raw**: 33/84 hits across 6 HK companies (phase_i_c_validation_v2)；merge-into-bucket pinned by `tests/test_phase_hk_llm_2_supplement_merge.py`
- **LLM workflow**: evaluate-company 加 `--pdf <path> --llm-config tmp/llm_configs/deepseek.json` 启用；不传则跳过 LLM 步骤（不是 bug 是 by-design gating）
- **Catalog verification** (Phase MX + Phase HK-B.5, 2026-05-11): coverage_matrix verified 24/62 → **36/62** (+12)；详情见 roadmap Phase MX + HK-B.5 Implementation Result
- **HK issuer financial-currency 闭环** (Phase HK-B.5.1 + .5.2, 2026-05-11): `HK_ISSUER_FINANCIAL_CURRENCY` map（PDF spot-checked 6 HK）+ fixture backfill (1616 records) + `HkYahooTrustRule.additional_trusted_currencies` schema → 全部 HK 字段现在用 issuer reporting currency stamp；09987 acct_payable promote 到 clean。注意：revenue/net_profit/total_assets 等 HKD-only trust rules 未做 multi-currency 扩展，非 HKD reporter 的这些字段现在正确 unresolved（之前是 wrong-label-trust-policy 误触发的 mirage clean）

下一步候选：HK-B.6 fix_assets 已 promote 4 issuers（+3 cells；01810/02498 因 PDF-Yahoo 实质偏差未入 allowlist）。剩余可选：扩展剩余 HKD-only trust rule（total_assets/total_liabilities/inventories/defer_tax_liab/total_cur_assets/total_cur_liab —— 主要是 explicit traceability，0-2 cells gain）；或 HK-B.7/.8（accounts_receiv/gross_profit recon 已建议保守，不 promote）；或合并到 main（branch 已 314+ commits ahead）。

`docs/2026-05-08-roadmap-evaluation.zh.md` 包含覆盖率分析和修复路径（Phase H/I 落地前的视角，部分数字已过期但分析框架仍有效）。

AGENTS.md 仍有效，但部分内容（HK 15-field closure 状态）已被 33-field/56-field 扩展取代。设计文档在 `docs/design/`（2026-05-07 drift analysis 仍是关键参考），历史 specs/plans 在 `docs/superpowers/archive/`。

真实 LLM 使用的 API key 模板在 `env.example`；本地常用 LLM config 在 `tmp/llm_configs/deepseek.json`，HK 6 公司 manifest 在 `tmp/llm_configs/n4b_manifest.json`。
