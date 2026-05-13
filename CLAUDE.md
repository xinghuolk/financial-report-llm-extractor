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
| R1 | `cache/db_schema.py` + `db.py` + `indexer.py` + `db_query.py` | Two-level extraction cache layer-1: SQLite DB at `data/extracted.db` indexed from `tmp/runs/*/{evaluation,llm_evidence_supplement}.json` joined by field_id. New CLI `index` + `query` commands. Zero pipeline behavior change. Schema: `extractions` (company, period_end, market, catalog_version PK) + `field_values` (company, period_end, field_id PK; priority + reason + bucket + JSON-encoded value + LLM page/confidence/reasoning). Exit codes for `query`: 0=hit, 1=miss, 2=db not initialized. See `docs/superpowers/plans/2026-05-13-extraction-cache-db-overview.md`. |
| R2 | `cache/provider_cache.py` + `source_inventory_fetch.py` integration | Two-level extraction cache layer-2 (provider tier): `tmp/.cache/{akshare,yahoo}/<cid>_<period>.json` content-addressed cache with embedded artifact blobs + 24h default TTL. New `fetch-source-inventory` flags: `--cache-ttl-hours`, `--no-cache`, `--skip-if-cached`. Eliminates redundant AKShare/Yahoo network calls across CLI invocations sharing same (company, period). Cache hit replays artifacts into SourceArtifactStore so `finalize_source_artifacts` validation passes. Schema-drift (provider_cache_v2) treated as silent miss. |
| R3 | `cache/llm_cache.py` + `llm_transport.py` integration | Two-level extraction cache layer-2 (LLM tier): `tmp/.cache/llm/<sha256>.json` content-addressed. Hash key = (model, system_prompt, user_payload). Deterministic — no TTL; catalog/model change naturally invalidates. New `--no-llm-cache` flag on `extract-llm` / `extract-llm-batch` / `evaluate-company`. Eliminates redundant LLM completions across re-runs (same chunks + same prompt + same model → cache hit, zero $ + zero latency). |
| R4 | `cli.py` pipeline subcommand + `company_evaluation.py` catalog_version embed | Two-level extraction cache layer-2 (orchestration): new `pipeline` CLI command runs fetch + evaluate + auto-index end-to-end with DB pre-check. If (company, period, catalog_version) already indexed → return cache_hit JSON, skip work. `--force` to bypass; `--no-cache` to bypass R2+R3 caches. `evaluation.json` now embeds `catalog_version` field (closes R1 indexer's stderr warning for fresh runs). **Phase R complete: 4 stages, two-level extraction cache shipped.** |

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

**先看**：`docs/2026-05-11-phase-summary.md` —— 阶段性快照（7 waves、coverage 表、未决项、onboarding artifact map），是进入分支的入口文档。

**分析新公司**：必看 `docs/new-company-analysis-workflow.md` —— 6 阶段标准工作流（currency 确认 → fetch → evaluate-with-LLM → 读 evaluation.md → 按 reason 分类决策 → PDF spot-check → catalog 更新）。**关键陷阱**：`evaluate-company` 必须带 `PDF_PATH` + `LLM_CONFIG`，否则 P3 pdf_only 字段（dividend_plan/dps 等 14 个）假性 unresolved。

随后查阅 `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md` —— Bucket 1（H0 null_means_zero）、Bucket 4（terminal taxonomy）、Phase H1（surgical conflict resolution）、Phase I-A/I-A.2（HK LLM 抽取 + 6 follow-ups）、Phase N4（P2+P3 扩展）、Phase I-C（text-mode）、Phase I-C.1（whitespace 归一化）、Phase EC（evaluate-company orchestrator）、Phase H2（CN/HK conflict surgical resolution）、Phase H2.1（catalog 加法 derivation 解锁 CN SGA）、Phase H2.2（多公司 sample-verification + market-scoped source_aliases + clean-row candidate audit）、Phase G1a（3 CN-direct P2 fields）、Phase G1b（contract_liabilities current+non_current split）、Phase G2（non_recurring_items_breakdown text/pdf_only）、Phase G3（parent-company-only SOTP 4 字段）、Phase G4-C（混合方案：audit_opinion + dividend_policy_text 加入 P4 pdf_only；mda_business_review/mda_forward_guidance/mda_risk_factors/auditor_change_history 留在 source_mode=llm_review 未启用 = 显式 out-of-project-scope）均已落地。catalog 覆盖 **68 字段** mapped（P0:22 + P1:11 + P2:12 + P3:21 + P4:2）+ 4 未映射 P4（仍在 taxonomy/coverage_matrix 内但 source_mapping_minimal 不引用）。**关键认知**：`scope_expectation` 是纯 metadata 标签（`field_metadata.py:32-38` Literal `consolidated/parent/attributable_to_owners/unknown/not_applicable`），`src/` 内无业务逻辑读它做 filtering——G3 只是给 4 个 pdf_only 字段贴 `parent` 标签，不需要 schema 维度扩展或代码改动。**G4-C 关键洞察**：现有 `llm_review.py` 模块用于 conflict adjudication 不是段落抽取；`source_mode=llm_review` 在当前 pipeline 里**未被消费**，等价于"defined but inert"。G4-C 把 2 个真正 PDF-可抽字段 (audit_opinion + dividend_policy_text) 转为 `pdf_only` 进入 text-mode pipeline；剩 4 字段 (MD&A 段落 + 多期 auditor_change_history) 显式留在 unused `llm_review` 模式 = catalog 边界即下游 Turtle Agent scope。

**当前覆盖率（live evaluate-company PDF+LLM，catalog 68 mapped 字段）**：

G4-C catalog 实测 (DeepSeek baseline 2026-05-12 / Codex `gpt-5.5` validation 2026-05-13)：
- **CN 600519/2024**: source-first 42/68 → DS +LLM **54/68 (79%)**；Codex **52/68 (76%)** — Codex 正确拒绝 2 个 DS false positive (`dividend_policy_text` 浅命中 + `receiv_tax_refund` 把 2023 值映到 2024)
- **CN 300750/2024 (CATL)**: source-first 42/68 → DS +LLM **55/68 (81%)** (Codex 未跑)
- **HK 01810/2024 (CNY)**: source-first 35/68 + 2 terminal → DS **49/68 (72%)**；Codex **53/68 (78%, +5)** — c_paid_for_taxes p237 / dividends_paid -23.3M p238 / non_oper_income 1.67B p230 / non_recurring SBC p10
- **HK 02498/2024 (CNY)**: source-first 35/68 + 2 terminal → DS **49/68 (72%)** (Codex 未跑)
- **HK 06862/2024 (CNY)**: source-first 35/68 + 1 terminal → DS **48/68 (71%)**；G3 interest_bearing_debt 2.07M 千 RMB 唯一正向
- **HK 00001/2025 (HKD)**: source-first 32/68 + 1 terminal → DS pre-G4-C 44/68；Codex G4-C **47/68 (69%, +3)**
- **HK 01113/2025 (HKD)**: source-first 33/68 → DS pre-G4-C 41/68；Codex G4-C **44/68 (65%, +3)**
- **HK 09987/2024 (USD)**: source-first 34/68 + 1 terminal → DS pre-G4-C 44/68；Codex G4-C **43/68 (63%, -1)** — codex 命中 audit_opinion，丢 contract_liab_current/segment（**Phase Q audit 显示丢的两个全是 DS shallow FP**：contract_liab DS 把 total 当 current；segment DS 把 Note 16 intro 散文当 segment 数据）

**Phase Q (Codex 二次审计, 2026-05-13)**：5 cohort 共 56 DS LLM hits 中 4 个被 Codex 拒绝；PDF/reasoning audit 显示 **4/4 全是 DS shallow false positive**（DS FP 率 ~7.1%）。失败模式：DS over-eager match（散文当数据 / 合规声明当 policy / 上期值当本期 / total 当 current）。Codex `gpt-5.5` 不犯此错。详情 `docs/2026-05-13-subscription-llm-validation.md` Phase Q 章节。
- **Sample-verified breadth**: 4 CN 公司 × 4 promotion 字段 = 16 EXACT match samples
- **HK LLM raw**: 33/84 hits across 6 HK companies (phase_i_c_validation_v2)；merge-into-bucket pinned by `tests/test_phase_hk_llm_2_supplement_merge.py`
- **LLM workflow**: evaluate-company 加 `--pdf <path> --llm-config tmp/llm_configs/deepseek.json` 启用；不传则跳过 LLM 步骤（不是 bug 是 by-design gating）
- **Catalog verification** (Phase MX + Phase HK-B.5, 2026-05-11): coverage_matrix verified 24/66 → **36/66** (+12)；详情见 roadmap Phase MX + HK-B.5 Implementation Result
- **HK issuer financial-currency 闭环** (Phase HK-B.5.1 + .5.2, 2026-05-11): `HK_ISSUER_FINANCIAL_CURRENCY` map（PDF spot-checked 6 HK）+ fixture backfill (1616 records) + `HkYahooTrustRule.additional_trusted_currencies` schema → 全部 HK 字段现在用 issuer reporting currency stamp；09987 acct_payable promote 到 clean。注意：revenue/net_profit/total_assets 等 HKD-only trust rules 未做 multi-currency 扩展，非 HKD reporter 的这些字段现在正确 unresolved（之前是 wrong-label-trust-policy 误触发的 mirage clean）

下一步候选：G1a/G1b/G2/G3/G4-C 已落地（+12 mapped catalog 字段，+13 source-first cells；G2/G3/G4-C 纯 pdf_only 走 LLM）。原 gap doc 估算 G3 "需新 schema 维度" + G4 "需新抽取模块" 都被实测证伪——G3 是纯标签级，G4-C 是 source_mode 转换 (llm_review→pdf_only) + 模板复用，5/6 P4 字段实质同 G2/G3 模式。**G4-C validation (5 公司 PDF+LLM, 2 CN + 3 HK, 2026-05-12)**：audit_opinion **5/5 ⭐** + dividend_policy_text **5/5 ⭐**（HK 增 "our opinion / in our opinion / what we have audited" anchor aliases 修 retrieval ranking）。剩余 4 P4 未映射字段 (MD&A 3 + auditor_change_history) **显式留在下游 scope**——MD&A 段落级 + 多期 audit history 在本项目数据收集层 ROI 太低。或合并到 main 完成 catalog gap closure 阶段。

**G3 LLM validation (full 7-cohort, PDF+LLM, 2026-05-12)**：catalog 落地后首跑命中率低 (01810 全 miss)，原因是 HK 报告用 "Financial position of the Company" / "Investment in subsidiaries (singular)" 等措辞与 v1 aliases 不匹配。补 HK-specific PDF aliases (`financial position of the company` / `balance sheet of the company` / 单数 `investment in subsidiaries` / `amount due from a subsidiary` 等) 后跑全 7 cohort 实测：

| 字段 | 600519 | 00001 | 01113 | 01810 | 02498 | 06862 | 09987 | Hit |
|---|---|---|---|---|---|---|---|---|
| cash_parent_company | ✓ 77B | ✓ 7M HK$ | ✓ 19,545$ | ✓ 1.52M千 | ✓ 1.85M千 | ✓ 1.91M千 | ✓ 16 USD | **7/7 ⭐** |
| equity_investment_in_subsidiaries | ✓ 1.61B | ✓ 368B HK$ | ✓ 252M千 | ✓ 42.9M千 | ✓ 4.4M千 | ✓ 1.7M千 | ✓ 4.9M USD | **7/7 ⭐** |
| amounts_due_from_subsidiaries | ✗ | ✓ 25.7B HK$ | ✗ | ✗ | ✓ 3.21M千 | ✓ 0 RMB | ✓ 41$ | 4/7 |
| interest_bearing_debt_parent_company | ✗ | ✗ | ✗ | ✗ | ✗ | **✓ 2.07M千 RMB** | ✗ | 1/7 (06862 海底捞 positive hit — alias 工作；6 issuer 母公司真零债务) |
| non_recurring_items_breakdown (G2) | ✓ 文本 | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ 文本 | 2/7 (CN 一票否决 + 部分 HKD-CN-style) |

**全 4/4 alias 组都有正向命中证据**。cash/equity_invest 已 7/7 全 cohort 通过。amounts_due 4/7 (3 家 issuer 真未单独披露)。interest_bearing_debt 1/7 但 06862 海底捞 案例已证明 alias 工作 — 0 hit on 其他 6 家是 issuer parent 真零债务（控股集团 + 消费品 issuer 把 debt 沉到 operating subsidiaries）。Catalog 闭环；剩余低命中率全部是 issuer-level 数据稀疏，不是 catalog 缺陷。

**G1b 跟进 note**：00001/01113/06862 contract_liabilities current/non_current 在 unresolved_conflict 是 provider 真稀疏（Yahoo 只有 `Non Current Deferred *Taxes*` 不是 `Deferred Revenue`；AKShare HK 仅 06862 有 `合同负债` 但 `statement_metadata_unproven`）。**By-design 走 LLM supplement**，不扩 HK-AKShare trust policy（P3 ROI 太低且 PDF 大概率根本不披露）。

`docs/2026-05-08-roadmap-evaluation.zh.md` 包含覆盖率分析和修复路径（Phase H/I 落地前的视角，部分数字已过期但分析框架仍有效）。

AGENTS.md 仍有效，但部分内容（HK 15-field closure 状态）已被 33-field/56-field 扩展取代。设计文档在 `docs/design/`（2026-05-07 drift analysis 仍是关键参考），历史 specs/plans 在 `docs/superpowers/archive/`。

真实 LLM 使用的 API key 模板在 `env.example`；本地常用 LLM config 在 `tmp/llm_configs/deepseek.json`，HK 6 公司 manifest 在 `tmp/llm_configs/n4b_manifest.json`。
