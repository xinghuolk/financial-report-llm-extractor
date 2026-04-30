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

Phase 2 foundation 已完成：
- `src/financial_report_llm_extractor/chunking.py`
- `tests/test_chunking.py`
- 已支持从 `pages.jsonl` 生成稳定 `BlockRecord`。
- 已支持中英文主表标题识别：balance sheet、income statement、cash flow。
- 已支持 page chunks 和 statement chunks，并写出 `chunks.jsonl`。
- CLI 命令：`financial-report-llm-extractor chunk --pages <pages.jsonl> --metadata <run_metadata.json> --out <chunks.jsonl>`。

Phase 3 foundation 已完成：
- `src/financial_report_llm_extractor/retrieval.py`
- `tests/test_retrieval.py`
- 已支持加载字段目录并为核心 P0/P1 字段补充 seed aliases 和 statement hints。
- 已支持从 `chunks.jsonl` 检索候选 chunk/evidence，并写出 `retrieval_probe.json`。
- 缺少候选的字段会显式标记为 `missing`。
- CLI 命令：`financial-report-llm-extractor retrieve --catalog <catalog.json> --chunks <chunks.jsonl> --out <retrieval_probe.json> --priorities P0,P1`。

Phase 4 foundation 已完成：
- `src/financial_report_llm_extractor/money.py`
- `tests/test_money.py`
- 已支持 raw numeric strings、commas、parentheses negatives、minus signs、dash missing values。
- 已支持 CNY/HKD/USD 与常见中英文 scale units，例如 `人民币百万元`、`HKD million`、`US$ thousand`。
- `normalize_money()` 返回并校验现有 `MoneyAmount` 合同。

Phase 5 foundation 已完成：
- `src/financial_report_llm_extractor/extraction.py`
- `tests/test_extraction.py`
- 已支持 PromptRequest、LlmExtractedField、LlmResponse 和 fixture-backed `FakeLlmClient`。
- 已支持 `retrieval_probe.json` -> fake LLM response -> money normalizer -> `ExtractedItem.validate()` -> `extraction_result.json`。
- `present` without evidence 会降级为 `extraction_failed` 并保留 errors。
- CLI 命令：`financial-report-llm-extractor extract-fake --retrieval-probe <retrieval_probe.json> --out <extraction_result.json>`。

Phase 6 foundation 已完成：
- `src/financial_report_llm_extractor/llm_transport.py`
- `tests/test_llm_transport.py`
- 已支持 JSON LLM config、OpenAI-compatible chat-completions transport、timeout、limited retry、raw response artifacts。
- 测试通过 injected transport，不需要真实网络。
- CLI 命令：`financial-report-llm-extractor extract --retrieval-probe <retrieval_probe.json> --config <llm_config.json> --out <extraction_result.json> --raw-response-dir <dir>`。

Phase 7 foundation 已完成：
- `src/financial_report_llm_extractor/evaluation.py`
- `tests/test_evaluation.py`
- 已定义真实报告评估矩阵：`600519_2025`、`00001_2025_en`、`01113_2025_en`。
- 已支持 extraction result review summary：status counts、present without evidence、present money without normalized value。
- CLI 命令：`financial-report-llm-extractor evaluate --root <repo-root> --out <evaluation_summary.json>`。

Phase 8 foundation 已完成：
- `docs/skills/financial-report-extractor/SKILL.md`
- `docs/skills/financial-report-extractor/references/review-checklist.md`
- `tests/test_skill_wrapper.py`
- 已提供 repo-contained optional skill wrapper，指导 Codex/Claude 调用 CLI。
- Skill wrapper 明确不得解析 PDF、归一化金额、验证合同或存储最终事实。

推荐下一步继续 Phase 7/8 follow-up：对三份真实 PDF 跑完整 artifacts，沉淀 hard-case regression fixtures，并决定是否安装 repo skill 到 `$CODEX_HOME/skills`。

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

Phase 2 foundation 已经实现 statement/evidence-block logical chunks：
- 从 `pages.jsonl` 生成稳定 block records。
- 构造 `block_id` 并服务于 `Evidence.block_id`。
- 生成 page chunks 和 statement chunks。
- 每个 chunk 包含 `chunk_id`、`kind`、`page_start`、`page_end`、`block_ids`、text。
- artifact 可追溯到 `source_pdf_hash` 并更新 `run_metadata`。

后续增强优先考虑：
- 更丰富的 layout-line metadata。
- statement continuation/end heuristics。
- HK side-by-side statement splitting。
- candidate row label、period、unit-context 提取。

## Phase 3 Direction

Phase 3 foundation 已经实现 retrieval probe：
- 读取 Turtle priority field catalog。
- 为部分核心字段提供 seed aliases 和 statement hints。
- 对 `chunks.jsonl` 的 chunk records 做 alias/scoring。
- 输出 `retrieval_probe.json`，包含 field status、candidate chunk、matched aliases 和 evidence。

后续增强优先考虑：
- 把 aliases/hints 移入更丰富的 catalog artifact。
- 补全全部 P0/P1 字段和 HK wording variants。
- 将 block-level evidence scoring 与 chunk-level scoring 分开。
- 对 derived fields 使用显式状态，而不只是 `missing`。
- 用真实 `600519`、`00001`、`01113` 报告评估召回质量。

## Phase 4 Direction

Phase 4 foundation 已经实现 deterministic money normalization：
- `parse_numeric_value()` 解析 commas、minus signs、parentheses negatives。
- dash-like values 被视为 missing numeric value。
- `resolve_money_unit()` 解析 CNY/HKD/USD 和基础 scale multipliers。
- `normalize_money()` 输出 `MoneyAmount` 并复用 `MoneyAmount.validate()`。

后续增强优先考虑：
- 补充 yuan、RMB yuan、HK$'000、RMB'000、万元、亿元等单位。
- 为多币种上下文提供结构化 ambiguity errors。
- 明确 row/header/report metadata 的 currency/unit precedence。
- 增加 derived value engine，并传播所有输入 evidence。
- 在 fake extraction pipeline 中接入 money normalizer。

## Phase 5 Direction

Phase 5 foundation 已经实现 fake extraction pipeline：
- `FakeLlmClient` 可按 field id 返回 fixture response。
- `run_fake_extraction()` 消费 `retrieval_probe.json`。
- present money outputs 会调用 `normalize_money()` 并生成 `MoneyAmount`。
- 每个 item 会经过 `ExtractedItem.validate()`。
- 无 evidence 的 present 输出不会通过，会变成 `extraction_failed`。

后续增强优先考虑：
- 从 JSON fixture 文件加载 fake LLM responses。
- 支持 text/number value types。
- 保存 raw LLM request/response artifacts。
- 加强 fake response schema validation。
- 在 derived value engine 完成后接入 derived fields。

## Phase 6 Direction

Phase 6 foundation 已经实现 real LLM transport boundary：
- `LlmTransportConfig.from_json()` 读取 provider/model/base URL/API key env/timeout/retry。
- `OpenAiCompatibleClient` 构造 `/chat/completions` 请求并解析 JSON object response。
- Transport 可注入，测试不依赖真实网络。
- `run_real_transport_probe()` 复用 extraction pipeline，并写 raw response artifacts。
- `extract` CLI 命令调用 real transport layer。

后续增强优先考虑：
- 添加 `llm_config.example.json`。
- 记录 latency、usage 和 structured transport errors。
- provider fallback 保持显式且默认关闭。
- 支持更多 provider adapter。
- 增加 opt-in integration smoke test。

## Phase 7 Direction

Phase 7 foundation 已经实现 evaluation harness：
- `DEFAULT_EVALUATION_FIXTURES` 包含 roadmap 指定的三份真实报告。
- `build_evaluation_matrix()` 检查 PDF 是否可用。
- `summarize_extraction_result()` 统计 present/missing/ambiguous/extraction_failed 等状态。
- summary 会显式列出 present without evidence 和 present money without normalized value。
- `write_review_summary()` 写出 `evaluation_summary.json`。

后续增强优先考虑：
- 对 `600519`、`00001`、`01113` 跑真实 artifacts。
- 明确真实评估输出目录约定。
- 增加 Markdown review summary。
- 从真实输出中提取 known hard cases 加回归测试。
- 可选真实 LLM evaluation 必须显式配置，默认测试不能依赖外网。

## Phase 8 Direction

Phase 8 foundation 已经实现 thin skill wrapper：
- Skill 文件位于 `docs/skills/financial-report-extractor/SKILL.md`。
- Review checklist 位于 `docs/skills/financial-report-extractor/references/review-checklist.md`。
- Wrapper 只指导调用 CLI，不承载业务逻辑。
- Tests 确认 frontmatter、CLI 命令、guardrails 和 checklist link。

后续增强优先考虑：
- 决定是否安装到 `$CODEX_HOME/skills`。
- 如果要作为一等 Codex skill 安装，再添加 `agents/openai.yaml`。
- CLI 参数变化时同步更新 wrapper。
- 真实 Phase 7 artifacts 存在后补充 example prompts。

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
