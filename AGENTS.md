# AGENTS.md

本文件是给 Codex、Claude、Gemini 以及其他编程代理的项目级工作说明。进入本仓库后，请优先阅读并遵守本文件；若用户在对话中给出更新指令，以用户最新指令为准。

## Project Context

`financial-report-llm-extractor` 是一个独立的财报抽取器，与 deterministic `financial-report-analysis` 管线完全隔离。项目最早从 LLM/PDF-first 原型开始，但当前主线是 **source-first**：

Provider artifacts（AKShare/Yahoo）→ reconciliation & semantics proof → source policy → PDF/LLM fallback evidence supplement。

核心目标：
- 使用 Turtle v0.15 字段目录、taxonomy、coverage matrix 和 source mapping catalog 定义目标字段语义。
- 保存 AKShare/Yahoo raw artifacts，并生成可 replay 的 source inventory。
- 对 provider raw fields 做 Turtle mapping、reconciliation、unit/currency proof 和 source policy selection。
- 对 provider raw field 语义进行显式证明；PDF samples 只能作为 provider policy proof，不等于最终逐公司 PDF evidence。
- 对 selected fields 复用 PDF ingestion/chunking/retrieval/LLM 作为 fallback 或 final evidence supplement。
- 每个 `present` money 值必须有 source evidence、显式币种/单位/倍率；需要 PDF profile 时再补 page/block/snippet evidence。
- 显式标记 `missing`、`ambiguous`、`not_applicable`、`extraction_failed`、`definition_unverified`、`pdf_required`、`source_unavailable` 等状态。

## Read First

开始实现前先看：
- `docs/2026-05-11-phase-summary.md`：当前分支入口快照，含 7 waves、coverage 表、未决项、onboarding artifact map。
- `docs/new-company-analysis-workflow.md`：新公司 6 阶段标准工作流。关键陷阱：`evaluate-company` 必须带 `PDF_PATH` + `LLM_CONFIG`，否则 P3/P4 `pdf_only` 字段会假性 unresolved。
- `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`：历史 roadmap 与已落地 phases。
- `docs/design/2026-05-07-source-first-architecture-drift-analysis.zh.md`：source-first drift analysis，仍是关键架构参考。
- `docs/requirements/2026-04-30-llm-first-financial-report-extractor-requirements.md`
- `docs/design/2026-04-30-llm-first-turtle-financial-extraction-design.md`
- `docs/design/2026-05-01-structured-data-source-first-financial-extraction-design.md`
- `docs/2026-04-30-codex-claude-handoff-prompt.md`

字段目录与 policy：
- `field_catalog/turtle_v015_priority_fields.json`
- `field_catalog/turtle_v015_source_mapping_minimal.json`
- `field_catalog/provider_raw_semantics_hk.json`
- `field_catalog/provider_raw_semantics_cn.json`
- `field_catalog/hk_yahoo_trust_policy.json`

## Current Architecture

所有源码在 `src/financial_report_llm_extractor/`，测试在 `tests/`，字段定义在 `field_catalog/`。

| 阶段 | 模块 | 状态与职责 |
| --- | --- | --- |
| 0 | `models.py` | Frozen dataclass 核心合同：`Evidence`、`MoneyAmount`、`ExtractedItem`、`Chunk`、`ExtractionRun` |
| 1 | `ingestion.py` | PDF → `pages.jsonl` + `run_metadata.json`，通过 `pdftotext -layout` |
| 2 | `chunking.py` | `pages.jsonl` → `chunks.jsonl` + stable `BlockRecord` |
| 3 | `retrieval.py` | Field-first evidence 检索，alias 评分排序 |
| 4 | `money.py` | 确定性金额解析与单位/币种归一化 |
| 5 | `extraction.py` | LLM 抽取管线，支持 fake + real |
| 6 | `llm_transport.py` | OpenAI-compatible + Gemini transport，测试用注入 transport |
| 7 | `evaluation.py` | 抽取结果审核与汇总 |
| M4 | `structured_sources/` | Provider 语义验证、HK Yahoo trust policy |
| M5 | `field_catalog/*.json` | `defer_tax_liab` Yahoo 证明 + `gross_profit` 终态降级 |
| N0 | `tests/test_catalog_consistency.py` | 5 个 JSON catalog 跨文件一致性 gate |
| N1-N4 | `field_catalog/turtle_v015_source_mapping_minimal.json` | P0/P1/P2/P3 扩展，曾达 44/56 字段阶段 |
| I-A/I-C | `structured_sources/llm_extraction_runner.py`、`llm_extraction_batch.py`、`llm_field_extraction.py` | HK notes-level LLM 抽取、text-mode `value_type` 门控、alias 空白归一化 |
| EC/H2/H2.2 | `company_evaluation.py`、`source_policy.py`、catalogs | `evaluate-company` orchestrator、CN/HK conflict surgical resolution、多公司 sample verification |
| R1-R5 | `cache/`、`cli.py`、`company_evaluation.py` | Two-level extraction cache：SQLite index、provider cache、LLM cache、pipeline orchestration、market-scoped schema v2 |
| 1a | `client.py`、`pipeline_core.py` | Public productization API for downstream consumers，`FinancialReportClient` + in-process fresh-run pipeline |

当前 catalog 覆盖：**68 mapped fields**（P0:22 + P1:11 + P2:12 + P3:21 + P4:2）+ 4 个未映射 P4 字段仍在 taxonomy/coverage_matrix 内但不被 `source_mapping_minimal` 引用。

## Product/API State

Two-level extraction cache 已完成：
- R1：SQLite DB at `data/extracted.db`，由 `tmp/runs/*/{evaluation,llm_evidence_supplement}.json` index；CLI `index` + `query`。
- R2：Provider cache at `tmp/.cache/{akshare,yahoo}/<cid>_<period>.json`，24h default TTL，支持 `--cache-ttl-hours`、`--no-cache`、`--skip-if-cached`。
- R3：LLM cache at `tmp/.cache/llm/<sha256>.json`，hash key = model + system prompt + user payload，支持 `--no-llm-cache`。
- R4：CLI `pipeline` 串联 fetch + evaluate + auto-index；DB pre-check 命中时返回 `cache_hit` JSON；`--force` bypass；`--no-cache` bypass R2+R3。
- R5：`field_values` schema v2，primary key 加入 `market`；`query --market {CN,HK}` 必选。v1 schema 会被 drop + recreate，`tmp/runs` 是 source of truth。

Public client API 已完成：
- `src/financial_report_llm_extractor/client.py`：`FinancialReportClient`、6 个 frozen dataclass、3 个 enum、1 个 exception。
- `src/financial_report_llm_extractor/pipeline_core.py`：从 CLI 抽出的 in-process pipeline。
- Backend = R1 DB query cache + R4 fresh-run pipeline。
- 使用 `importlib.resources` 读取 catalog；`$FR_LLM_CACHE_ROOT` 控制 cache root。
- Bucket → `ConfidenceLevel` translation；`raw_bucket` 保留审计。
- `include_llm_supplement` 同时控制 field filter 与 LLM step toggle。
- Decimal precision 通过 `str()` detour；`extraction_id` 使用 sha256 prefix 方便下游 dedup。
- 设计文档：`docs/superpowers/specs/2026-05-13-financial-report-client-productization-design.md`。

## Current Evaluation Snapshot

G4-C 已落地：
- `audit_opinion` + `dividend_policy_text` 加入 P4 `pdf_only`，进入 text-mode pipeline。
- `mda_business_review`、`mda_forward_guidance`、`mda_risk_factors`、`auditor_change_history` 保持 `source_mode=llm_review`，当前 pipeline 未消费，等价于显式 out-of-project-scope。
- `llm_review.py` 当前用于 conflict adjudication，不是段落抽取模块。

G4-C catalog 实测（DeepSeek baseline 2026-05-12 / Codex `gpt-5.5` validation 2026-05-13）：
- CN `600519`/2024：source-first 42/68 → DS +LLM 54/68；Codex 52/68。Codex 正确拒绝 2 个 DS false positive。
- CN `300750`/2024：source-first 42/68 → DS +LLM 55/68。
- HK `01810`/2024：source-first 35/68 + 2 terminal → DS 49/68；Codex 53/68。
- HK `02498`/2024：source-first 35/68 + 2 terminal → DS 49/68。
- HK `06862`/2024：source-first 35/68 + 1 terminal → DS 48/68。
- HK `00001`/2025：source-first 32/68 + 1 terminal → Codex G4-C 47/68。
- HK `01113`/2025：source-first 33/68 → Codex G4-C 44/68。
- HK `09987`/2024：source-first 34/68 + 1 terminal → Codex G4-C 43/68；Phase Q audit 显示 DS 丢失/差异中的两个是 shallow false positive。

Phase Q（2026-05-13）：
- 5 cohort 共 56 个 DS LLM hits 中，4 个被 Codex 拒绝。
- PDF/reasoning audit 显示 4/4 都是 DS shallow false positive。
- 失败模式：散文当数据、合规声明当 policy、上期值当本期、total 当 current。
- 详情见 `docs/2026-05-13-subscription-llm-validation.md`。

重要认知：
- `scope_expectation` 是纯 metadata 标签；`src/` 内无业务逻辑读它做 filtering。G3 只是给 4 个 `pdf_only` 字段贴 `parent` 标签，不需要 schema 维度扩展。
- G2/G3/G4-C 纯 `pdf_only` 字段走 LLM supplement。
- HK issuer financial currency 已闭环：`HK_ISSUER_FINANCIAL_CURRENCY` + fixture backfill + `HkYahooTrustRule.additional_trusted_currencies`。非 HKD reporter 不应触发 HKD-only trust rules。
- HK `gross_profit` 在 Yahoo/AKShare raw semantics 未证明前不能 clean；不得因为某个 PDF 样本值匹配就 promote。
- HK `net_profit` 可以保留 Yahoo `Net Income Common Stockholders` raw field 判断，但必须表述为 sampled provider semantics proof，不是最终 PDF evidence。

## Core Contracts

所有关键数据使用 frozen dataclass 并带显式 `validate()` 方法。关键不变量：
- `Evidence` 必须包含 `page`、`chunk_id`、`block_id`、`snippet`。
- `MoneyAmount.normalized_value` 必须等于 `value * unit_multiplier`。
- `ExtractedItem.status == "present"` 时必须有 evidence。
- money 类型的 present item 必须有 `MoneyAmount`。
- 状态枚举至少包括 `present`、`missing`、`ambiguous`、`not_applicable`、`extraction_failed`；source-first pipeline 还使用 terminal bucket 表达 `definition_unverified`、`pdf_required`、`source_unavailable` 等。

抽取结果必须表达：
- `field_id`
- `status`
- `value` 或 `money`
- `unit`
- `period`
- `scope`
- `confidence`
- `evidence`

对 `status != "present"`：
- 不要伪造值。
- 用状态和错误/说明表达原因。

## Architecture Guardrails

必须保持：
- 独立应用优先；skills 只作为薄封装。
- ingestion、chunking、retrieval、LLM transport、validation/export、structured source policy 保持边界清晰。
- Source-first 是当前主线：AKShare/Yahoo provider artifacts 先于 PDF/LLM fallback。
- Provider raw field semantics proof 是 source policy 的信任边界；不要用逐公司 PDF 值匹配替代 provider 语义证明。
- PDF samples 只能作为 sampled provider policy proof；它们不等于最终 per-export `pdf_evidence`。
- `source_evidence`、`trust_policy_evidence`、`pdf_evidence` 必须分开建模和报告。
- Replay/report artifacts 应显式区分 `provider_semantics_verified_fields`、`sampled_pdf_policy_proof_fields`、`final_pdf_evidence_fields`、`provider_semantics_unverified_fields`。
- LLM 输出必须 evidence-grounded。
- present 值缺证据时不能静默接受。
- 金额、币种、单位、倍率必须显式建模。
- 缺失、歧义、不可用、抽取失败必须状态化。
- Artifact ID 要稳定、可复现，避免运行时随机数。
- 测试中禁止真实网络调用；使用 fake client 或 protocol 注入。

不要引入：
- canonical fact promotion。
- metric lifecycle governance。
- recompute decision engine。
- 对现有 P5/Turtle export pipeline 的依赖。
- 第一阶段之外的 UI 或异步 workflow。
- broad PDF retrieval 作为 provider semantics 的默认解决办法。

## Development Rules

默认工作方式：
- 修改前先运行 `git status --short`，避免覆盖用户未提交修改。
- 先看现有测试风格，再改代码。
- 新增行为必须有聚焦测试。
- 尽量使用 Python 3.11 标准库。
- 暂时不要引入重量级依赖，除非文档、测试或用户明确要求。
- 保持 dataclass 合同简单、可序列化、可验证。
- 不要大范围重构已通过的早期阶段，除非新阶段确实需要。
- 不要把 retrieval 或 LLM 逻辑提前塞进 ingestion 层。
- 不要为了提高 clean coverage 而把 `definition_unverified`、`pdf_required`、`source_unavailable` 混成一个 missing/warning bucket。

代码风格：
- Python package 位于 `src/financial_report_llm_extractor/`。
- 测试位于 `tests/`。
- 使用 frozen dataclass 表达稳定合同。
- 使用显式 `validate()` 方法表达业务不变量。
- 保持函数小而可测试。
- mypy `disallow_untyped_defs = true`，ruff line-length 88，target py311。

本地命令环境：
- 当前环境是 macOS/zsh；使用常规 UTF-8 shell 命令即可。
- 若在 Windows + PowerShell 环境工作，优先使用 PowerShell，并显式进入 UTF-8 模式：`[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()`；`Get-Content` / `Set-Content` 显式使用 `-Encoding UTF8`。
- 需要生成无 BOM UTF-8 fixture 或 JSONL 时，Windows 下优先使用 `.NET System.Text.UTF8Encoding($false)` 写入。
- Codex 沙箱内不要默认使用 Git Bash；本机 Git Bash/MSYS2 可能因 Windows 沙箱限制无法创建 signal pipe。

## Common Commands

包管理器为 `uv`。运行时零外部 Python 依赖（仅 stdlib）。开发依赖：pytest、ruff、mypy。外部 CLI 依赖：`pdftotext -layout`（poppler）。

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
```

单文件或单测试：

```bash
uv run pytest tests/test_models.py -v
uv run pytest tests/test_models.py::test_present_item_requires_evidence -v
```

完整验证：

```bash
uv run pytest -v && uv run ruff check . && uv run mypy src tests
```

重要 CLI：
- `financial-report-llm-extractor ingest --pdf <path> --out <dir>`
- `financial-report-llm-extractor chunk --pages <pages.jsonl> --metadata <run_metadata.json> --out <chunks.jsonl>`
- `financial-report-llm-extractor retrieve --catalog <catalog.json> --chunks <chunks.jsonl> --out <retrieval_probe.json> --priorities P0,P1`
- `financial-report-llm-extractor extract-fake --retrieval-probe <retrieval_probe.json> --out <extraction_result.json>`
- `financial-report-llm-extractor extract --retrieval-probe <retrieval_probe.json> --config <llm_config.json> --out <extraction_result.json> --raw-response-dir <dir>`
- `financial-report-llm-extractor evaluate --root <repo-root> --out <evaluation_summary.json>`
- `financial-report-llm-extractor fetch-source-inventory ...`
- `financial-report-llm-extractor evaluate-company ...`
- `financial-report-llm-extractor index --runs tmp/runs ...`
- `financial-report-llm-extractor query --market {CN,HK} ...`
- `financial-report-llm-extractor pipeline ...`

真实 LLM 使用：
- API key 模板在 `env.example`。
- 本地常用 LLM config 在 `tmp/llm_configs/deepseek.json`。
- HK 6 公司 manifest 在 `tmp/llm_configs/n4b_manifest.json`。
- 默认测试不能依赖外网；真实 LLM evaluation 必须显式配置。

## Agent Handoff

如果需要把任务交给另一个代理，请使用：
- `docs/2026-04-30-codex-claude-handoff-prompt.md`

交接时说明：
- 当前 git 状态。
- 已改文件。
- 已运行的验证命令和结果。
- 未完成事项或已知风险。
