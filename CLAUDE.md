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

优先阅读 `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md` —— Phase N 已完成，下一步为 Bucket 1 (source policy 修正) → Bucket 4 (终态分类) → Phase H → Phase I。

`docs/2026-05-08-roadmap-evaluation.zh.md` 包含覆盖率分析和修复路径。

AGENTS.md 仍有效，但部分内容（HK 15-field closure 状态）已被 33-field 扩展取代。设计文档在 `docs/design/`（2026-05-07 drift analysis 仍是关键参考），历史 specs/plans 在 `docs/superpowers/archive/`。

真实 LLM 使用的 API key 模板在 `env.example`（Phase I 启动时使用）。
