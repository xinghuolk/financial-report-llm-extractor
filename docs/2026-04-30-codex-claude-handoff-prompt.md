# Codex / Claude 接手提示词

把下面这段提示词粘给新的 Codex、Claude 或其他编程代理，让它从当前仓库状态继续工作。

```text
你正在接手仓库：financial-report-llm-extractor。

项目定位：
- 这是一个独立的 LLM-first 财报抽取器，不依赖 deterministic financial-report-analysis 架构。
- 目标是从年报 PDF 中抽取 Turtle v0.15 风格财务字段，输出带证据、可 review 的 JSON。
- 第一可用切片：单份年报 PDF -> 文档页/块索引 -> P0/P1 字段抽取 -> 每个 present 值必须带 page/chunk/block/snippet 证据。

请先阅读这些文档：
- README.md
- docs/requirements/2026-04-30-llm-first-financial-report-extractor-requirements.md
- docs/design/2026-04-30-llm-first-turtle-financial-extraction-design.md
- docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md
- docs/superpowers/plans/2026-04-30-phase-0-contracts.md
- docs/superpowers/plans/2026-04-30-phase-1-pdf-probe-page-store.md

当前已完成：
- Phase 0 contracts 已完成。
  - src/financial_report_llm_extractor/models.py 包含 Evidence、MoneyAmount、ExtractedItem、Chunk、ExtractionRun 等 frozen dataclass 合同。
  - Evidence 要求 page、chunk_id、block_id、snippet。
  - present money item 必须包含 MoneyAmount，并校验 normalized_value = value * unit_multiplier。
- Phase 1 PDF probe/page store 已完成。
  - src/financial_report_llm_extractor/ingestion.py 包含 pdftotext 文本分页、PDF SHA-256、pages.jsonl 和 run_metadata.json 写入。
  - src/financial_report_llm_extractor/cli.py 提供 ingest 命令。
  - pyproject.toml 注册脚本 financial-report-llm-extractor。
- Phase 2 logical chunks foundation 已完成。
  - src/financial_report_llm_extractor/chunking.py 包含 BlockRecord、LogicalChunkRecord、ChunkStore、build_chunk_store()。
  - tests/test_chunking.py 覆盖稳定 block_id、CN/HK statement title detection、page/statement chunks、chunks.jsonl artifact。
  - src/financial_report_llm_extractor/cli.py 提供 chunk 命令。
  - chunker_version 为 phase2-logical-chunks-v1。
- Phase 3 retrieval probe foundation 已完成。
  - src/financial_report_llm_extractor/retrieval.py 包含 FieldSpec、RetrievalCandidate、load_field_specs()、retrieve_candidates()、write_retrieval_probe()。
  - tests/test_retrieval.py 覆盖 P0/P1 catalog loading、seed aliases、statement hints、candidate scoring、missing status、retrieval_probe.json。
  - src/financial_report_llm_extractor/cli.py 提供 retrieve 命令。
- Phase 4 money normalizer foundation 已完成。
  - src/financial_report_llm_extractor/money.py 包含 MoneyNormalizationError、parse_numeric_value()、resolve_money_unit()、normalize_money()。
  - tests/test_money.py 覆盖 commas、parentheses negatives、minus signs、dash missing values、CNY/HKD/USD 和基础 scale units。
  - normalize_money() 返回现有 MoneyAmount 合同并调用 validate()。
- Phase 5 fake extraction pipeline foundation 已完成。
  - src/financial_report_llm_extractor/extraction.py 包含 PromptRequest、LlmExtractedField、LlmResponse、FakeLlmClient、run_fake_extraction()。
  - tests/test_extraction.py 覆盖 fake client、retrieval_probe -> extraction_result、money normalization、present without evidence 降级。
  - src/financial_report_llm_extractor/cli.py 提供 extract-fake 命令。
- Phase 6 real LLM transport foundation 已完成。
  - src/financial_report_llm_extractor/llm_transport.py 包含 LlmTransportConfig、OpenAiCompatibleClient、run_real_transport_probe()。
  - tests/test_llm_transport.py 覆盖 config loading、OpenAI-compatible request、timeout/retry、raw response artifacts。
  - src/financial_report_llm_extractor/cli.py 提供 extract 命令。
  - 测试使用 injected transport，不需要真实网络。
- Phase 7 real report evaluation foundation 已完成。
  - src/financial_report_llm_extractor/evaluation.py 包含 EvaluationFixture、build_evaluation_matrix()、summarize_extraction_result()、write_review_summary()。
  - tests/test_evaluation.py 覆盖 roadmap 三份真实报告矩阵、PDF availability、status summary、evidence/normalized money review checks。
  - src/financial_report_llm_extractor/cli.py 提供 evaluate 命令。
- Phase 8 thin skill wrapper foundation 已完成。
  - docs/skills/financial-report-extractor/SKILL.md 提供 repo-contained optional skill wrapper。
  - docs/skills/financial-report-extractor/references/review-checklist.md 提供 extraction output review checklist。
  - tests/test_skill_wrapper.py 覆盖 frontmatter、CLI command usage、guardrails、checklist link。
- field_catalog/turtle_v015_priority_fields.json 已包含 P0-P4 字段优先级。
- tests/ 下已有 test_models.py、test_ingestion.py、test_cli.py、test_field_catalog.py。

当前架构护栏：
- 保持独立应用优先，skill 只做薄封装。
- 不引入 canonical fact promotion、metric lifecycle governance、recompute decision engine。
- 不依赖现有 P5/Turtle export pipeline。
- LLM 输出必须 evidence-grounded；present 值无证据应被拒绝或标为 ambiguous/missing。
- 金额、币种、单位倍率要显式建模，不能把 “HKD million” 这类单位丢成裸数字。
- 缺失、歧义、不可用、抽取失败必须显式状态化，不要静默填 0 或 None 当成成功。

推荐下一步：继续 Phase 7/8 follow-up，对三份真实 PDF 跑 artifacts，并决定是否把 repo-contained skill 安装到 $CODEX_HOME/skills。

Phase 2 已完成的基础能力：
- 在现有 page-level artifacts 之上建立 statement/evidence-block logical chunks。
- 识别或构造稳定 block_id，用于 Evidence.block_id。
- 为后续 retrieval 和 LLM 抽取提供 chunks.jsonl。

建议实施顺序：
1. 先写测试，再实现。
2. 明确真实评估输出目录，例如 runs/evaluation/<report_id>/。
3. 对 600519、00001、01113 运行 ingest/chunk/retrieve/extract。
4. 用 evaluate 汇总 extraction_result.json，生成 JSON 和后续 Markdown review summary。
5. 如需安装 skill，再把 docs/skills/financial-report-extractor 复制/安装到 $CODEX_HOME/skills 并补 agents/openai.yaml。
6. 每个新 artifact 都要带 source_pdf_hash 或可追溯到 run_metadata。

测试与验证命令：
- uv run pytest -v
- uv run ruff check .
- uv run mypy src tests

如果 uv 不可用，可尝试项目虚拟环境中的 pytest；但最终最好保持上述命令可通过。

开发风格：
- 使用 Python 3.11 标准库优先，暂时不要引入重量级依赖，除非文档或测试明确需要。
- 保持 dataclass 合同简单、可序列化、可验证。
- 修改代码前先看现有 tests 的风格。
- 不要大范围重构已经通过的 Phase 0/1，除非新阶段确实需要。
- 新增行为必须有聚焦测试。

请在开始实现前先用 git status 查看工作区，避免覆盖用户未提交修改。
```
