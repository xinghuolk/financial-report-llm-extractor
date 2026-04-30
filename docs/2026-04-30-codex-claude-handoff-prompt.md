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
- field_catalog/turtle_v015_priority_fields.json 已包含 P0-P4 字段优先级。
- tests/ 下已有 test_models.py、test_ingestion.py、test_cli.py、test_field_catalog.py。

当前架构护栏：
- 保持独立应用优先，skill 只做薄封装。
- 不引入 canonical fact promotion、metric lifecycle governance、recompute decision engine。
- 不依赖现有 P5/Turtle export pipeline。
- LLM 输出必须 evidence-grounded；present 值无证据应被拒绝或标为 ambiguous/missing。
- 金额、币种、单位倍率要显式建模，不能把 “HKD million” 这类单位丢成裸数字。
- 缺失、歧义、不可用、抽取失败必须显式状态化，不要静默填 0 或 None 当成成功。

推荐下一步：从 roadmap 的 Phase 2 开始。

Phase 2 目标：
- 在现有 page-level artifacts 之上建立 statement/evidence-block logical chunks。
- 识别或构造稳定 block_id，用于 Evidence.block_id。
- 为后续 retrieval 和 LLM 抽取提供 chunk store。

建议实施顺序：
1. 先写测试，再实现。
2. 新增或扩展 ingestion/chunking 相关模块，避免把 retrieval 或 LLM 逻辑提前塞进 ingestion.py。
3. 为 pages.jsonl -> blocks/chunks 的转换设计小合同，例如：
   - BlockRecord: block_id, page, kind, text, optional bbox/table/cell metadata
   - Chunk: chunk_id, kind, page_start, page_end, block_ids, text
4. 生成 artifact 时使用稳定、可复现的 ID，不要依赖运行时随机数。
5. 先支持文本块和主表附近窗口，表格结构恢复可以分阶段增强。
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

