# AGENTS.md

本文件是给 Codex、Claude、Gemini 以及其他编程代理的项目级工作说明。进入本仓库后，请优先阅读并遵守本文件；若用户在对话中给出更新指令，以用户最新指令为准。

## Project Context

`financial-report-llm-extractor` 是一个独立的 LLM-first 财报抽取器。它与 deterministic `financial-report-analysis` 架构保持隔离，目标是从年报 PDF 中抽取 Turtle v0.15 风格财务字段，并输出带证据、可 review 的结构化 JSON。

核心目标：
- 将 PDF 解析为 page text、table blocks、layout metadata、chunks。
- 存储 chunks，用于 retrieval 和 evidence lookup。
- 使用 Turtle v0.15 字段目录和优先级。
- 对每个字段检索候选证据。
- 调用 LLM 产出结构化 extracted items。
- 每个 `present` 值必须带 page、chunk、block、snippet 证据。
- 显式标记 missing、ambiguous、not_applicable、extraction_failed。

第一可用切片：
- 单份年报 PDF 输入。
- 构建文档 chunk index。
- 抽取 P0/P1 Turtle 字段。
- 输出 value、unit、period、scope、confidence、evidence。
- 缺失或歧义字段必须显式表达。

## Read First

开始实现前先阅读：
- `README.md`
- `docs/requirements/2026-04-30-llm-first-financial-report-extractor-requirements.md`
- `docs/design/2026-04-30-llm-first-turtle-financial-extraction-design.md`
- `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
- `docs/2026-04-30-codex-claude-handoff-prompt.md`

已完成计划可参考：
- `docs/superpowers/plans/2026-04-30-phase-0-contracts.md`
- `docs/superpowers/plans/2026-04-30-phase-1-pdf-probe-page-store.md`

字段目录：
- `field_catalog/turtle_v015_priority_fields.json`

## Current State

Phase 0 已完成：
- `src/financial_report_llm_extractor/models.py`
- `tests/test_models.py`
- 核心合同包括 `Evidence`、`MoneyAmount`、`ExtractedItem`、`Chunk`、`ExtractionRun`。
- `Evidence` 必须包含 `page`、`chunk_id`、`block_id`、`snippet`。
- `present` money item 必须包含 `MoneyAmount`。
- `MoneyAmount.normalized_value` 必须等于 `value * unit_multiplier`。

Phase 1 已完成：
- `src/financial_report_llm_extractor/ingestion.py`
- `src/financial_report_llm_extractor/cli.py`
- `tests/test_ingestion.py`
- `tests/test_cli.py`
- 已支持 `pdftotext -layout` 文本分页、PDF SHA-256、`pages.jsonl`、`run_metadata.json`。
- CLI 命令：`financial-report-llm-extractor ingest --pdf <path> --out <dir>`。

推荐下一步从 roadmap 的 Phase 2 开始：statement/evidence-block logical chunks。

## Architecture Guardrails

必须保持：
- 独立应用优先；skills 只作为薄封装。
- ingestion、chunking、retrieval、LLM transport、validation/export 保持边界清晰。
- LLM 输出必须 evidence-grounded。
- present 值缺证据时不能静默接受。
- 金额、币种、单位、倍率必须显式建模。
- 缺失、歧义、不可用、抽取失败必须状态化。
- artifact ID 要稳定、可复现，避免运行时随机数。

不要引入：
- canonical fact promotion。
- metric lifecycle governance。
- recompute decision engine。
- 对现有 P5/Turtle export pipeline 的依赖。
- 第一阶段之外的 UI 或异步 workflow。

## Development Rules

默认工作方式：
- 修改前先运行 `git status --short`，避免覆盖用户未提交修改。
- 先看现有测试风格，再改代码。
- 新增行为必须有聚焦测试。
- 尽量使用 Python 3.11 标准库。
- 暂时不要引入重量级依赖，除非文档、测试或用户明确要求。
- 保持 dataclass 合同简单、可序列化、可验证。
- 不要大范围重构已通过的 Phase 0/1，除非新阶段确实需要。
- 不要把 retrieval 或 LLM 逻辑提前塞进 ingestion 层。

代码风格：
- Python package 位于 `src/financial_report_llm_extractor/`。
- 测试位于 `tests/`。
- 使用 frozen dataclass 表达稳定合同。
- 使用显式 `validate()` 方法表达业务不变量。
- 保持函数小而可测试。

## Verification

常用验证命令：

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
```

如果只改某一阶段，可先运行相关测试，例如：

```bash
uv run pytest tests/test_models.py -v
uv run pytest tests/test_ingestion.py tests/test_cli.py -v
```

最终完成实现型任务前，尽量运行完整验证。若本地缺少 `uv` 或外部工具不可用，请在最终回复中说明。

## Phase 2 Direction

推荐下一步实现 statement/evidence-block logical chunks：
- 从 `pages.jsonl` 生成稳定 block records。
- 构造 `block_id` 并服务于 `Evidence.block_id`。
- 生成 statement 或 section-level chunks。
- 每个 chunk 包含 `chunk_id`、`kind`、`page_start`、`page_end`、`block_ids`、text。
- artifact 要能追溯到 `source_pdf_hash` 或 `run_metadata`。
- 先支持文本块和主表附近窗口，表格结构恢复后续增强。

建议新增模块时优先考虑：
- `src/financial_report_llm_extractor/chunking.py`
- `tests/test_chunking.py`

## Output Contract Reminders

抽取结果必须表达：
- `field_id`
- `status`
- `value` 或 `money`
- `unit`
- `period`
- `scope`
- `confidence`
- `evidence`

对 `status == "present"`：
- 必须有 evidence。
- money 字段必须有 `MoneyAmount`。
- evidence snippet 应能支持抽取值。

对 `status != "present"`：
- 不要伪造值。
- 用状态和错误/说明表达原因。

## Agent Handoff

如果需要把任务交给另一个代理，请使用：
- `docs/2026-04-30-codex-claude-handoff-prompt.md`

交接时说明：
- 当前 git 状态。
- 已改文件。
- 已运行的验证命令和结果。
- 未完成事项或已知风险。

