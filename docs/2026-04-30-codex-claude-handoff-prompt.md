# Codex / Claude 接手提示词

把下面这段提示词粘给新的 Codex、Claude 或其他编程代理，让它从当前仓库状态继续工作。

```text
你正在接手仓库：financial-report-llm-extractor。

项目定位：
- 这是一个独立的财报字段抽取器，不依赖 deterministic financial-report-analysis 架构。
- 当前产品方向已经从 broad PDF-first 调整为 source-first：优先 AKShare，其次 Yahoo/yfinance，再用 PDF/LLM 做缺失、冲突、歧义和年报证据补充。
- 目标仍然是输出 Turtle v0.15 风格字段和可 review JSON，但 source evidence 与 PDF evidence 要分开建模。
- PDF/LLM 能力保留为 fallback，不应重新扩大为默认 broad P0/P1 PDF 抽取路径。

请先阅读这些文档：
- README.md
- docs/requirements/2026-04-30-llm-first-financial-report-extractor-requirements.md
- docs/design/2026-04-30-llm-first-turtle-financial-extraction-design.md
- docs/design/2026-05-01-structured-data-source-first-financial-extraction-design.md
- docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md
- docs/superpowers/specs/2026-05-02-turtle-field-taxonomy-design.md
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
- Source-first foundation 已开始并已有可运行代码。
  - `src/financial_report_llm_extractor/structured_sources/` 包含 source contracts、artifact store、AKShare adapter、Yahoo adapter、mapping、coverage、reconciliation、review export、PDF supplement、LLM review、source-first evaluation。
  - `field_catalog/turtle_v015_source_mapping_minimal.json` 是当前 source-first 最小字段映射目录。
  - `docs/superpowers/specs/2026-05-02-turtle-field-taxonomy-design.md` 定义了后续完整 Turtle 字段应按利润表、资产负债表、现金流量表、股东回报、会计调整、附注/MD&A 分类，再叠加 P0-P4 priority。
  - `scripts/run-source-first-e2e-evaluation.sh` 是 synthetic no-network source-first E2E。
  - `scripts/run-real-source-validation.sh` 是 opt-in 真实/捕获来源验证入口。
  - `tests/fixtures/akshare/600519_income_statement_2025_required_fields.jsonl` 是从真实 AKShare 600519 income statement 返回固化出来的 captured source inventory。
  - `tests/fixtures/akshare/600519_combined_statements_2025_required_fields.jsonl` 是从真实 AKShare 600519 income statement、balance sheet、cash flow 一次性验证输出固化出来的 captured source inventory。
  - `tests/fixtures/yahoo/0001_hk_income_statement_2025_required_fields.jsonl` 是从真实 Yahoo/yfinance `0001.HK` income statement 输出固化出来的 captured source inventory。
  - captured replay 已验证 source inventory -> Turtle mapping -> reconciliation -> source-only export；AKShare combined fixture 当前覆盖 8/9 minimal source-mapping fields，Yahoo income fixture 当前覆盖 3/9。
- field_catalog/turtle_v015_priority_fields.json 已包含 P0-P4 字段优先级。
- tests/ 下已有 test_models.py、test_ingestion.py、test_cli.py、test_field_catalog.py。

当前架构护栏：
- 保持独立应用优先，skill 只做薄封装。
- 不引入 canonical fact promotion、metric lifecycle governance、recompute decision engine。
- 不依赖现有 P5/Turtle export pipeline。
- LLM 输出必须 evidence-grounded；present 值无证据应被拒绝或标为 ambiguous/missing。
- 金额、币种、单位倍率要显式建模，不能把 “HKD million” 这类单位丢成裸数字。
- Source-first present money 必须有明确 currency/unit；匹配到字段但单位或归一化失败时应是 blocked，不应伪装成 missing。
- 同一 source 内的多个候选可按 catalog alias 顺序作为确定性优先级；跨 source 分歧必须保留给 reconciliation/review。
- 缺失、歧义、不可用、抽取失败必须显式状态化，不要静默填 0 或 None 当成成功。

如何找到下一步工作：
- 先看 `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md` 的 Phase J 当前验证状态。
- 再看最近的 captured validation 输出，例如 `tmp/runs/captured_source_validation_akshare/review_summary.json` 和 `real_source_validation_summary.json`。
- 根据 missing fields 选择下一个 source/statement family，而不是从头跑 broad PDF 或重复请求 provider。
- 如果要调 AKShare/Yahoo 映射，优先从 captured source inventory 开始；只有需要新增或刷新 captured fixture 时才 opt-in 调真实 provider。

当前推荐方向：
- 用 captured fixture 驱动 source-first 映射完善。
- 优先补 Yahoo/yfinance balance sheet 和 cash flow captured fixtures，验证 `total_assets`、`total_liabilities`、`cash`、`operating_cash_flow` 等字段。
- 再补 `00001`、`01113` 的 AKShare/Yahoo captured fixtures 作为港股英文样本验证。
- 对同字段 AKShare/Yahoo 候选做 period、currency、unit、value reconciliation。
- 最后才对仍缺失、冲突、歧义或需要页码证据的字段进入 PDF/LLM fallback。

Phase 2 已完成的基础能力：
- 在现有 page-level artifacts 之上建立 statement/evidence-block logical chunks。
- 识别或构造稳定 block_id，用于 Evidence.block_id。
- 为后续 retrieval 和 LLM 抽取提供 chunks.jsonl。

建议实施顺序：
1. 先写测试，再实现。
2. 对 source-first 工作，先用 captured fixture 复现当前问题；不要反复请求 AKShare/Yahoo。
3. 新增真实 provider 调用必须 opt-in，并将返回固化为可重复使用的 fixture。
4. 用 source mapping、coverage、reconciliation、review export 的 artifacts 判断下一步。
5. 只有 source-first coverage gate 指向 PDF/LLM fallback 时，才运行 PDF ingestion/chunk/retrieval/extract。
6. 每个新 artifact 都要能追溯到 source artifact、source inventory 或 PDF run_metadata。

测试与验证命令：
- uv run pytest -v
- uv run ruff check .
- uv run mypy src tests
- REAL_SOURCE_VALIDATION=1 INVENTORY_FIXTURE=tests/fixtures/akshare/600519_income_statement_2025_required_fields.jsonl OUT_DIR=tmp/runs/captured_source_validation_akshare scripts/run-real-source-validation.sh
- REAL_SOURCE_VALIDATION=1 INVENTORY_FIXTURE=tests/fixtures/akshare/600519_combined_statements_2025_required_fields.jsonl OUT_DIR=tmp/runs/captured_source_validation_akshare_combined scripts/run-real-source-validation.sh
- REAL_SOURCE_VALIDATION=1 INVENTORY_FIXTURE=tests/fixtures/yahoo/0001_hk_income_statement_2025_required_fields.jsonl OUT_DIR=tmp/runs/captured_source_validation_yahoo_income scripts/run-real-source-validation.sh

如果 uv 不可用，可尝试项目虚拟环境中的 pytest；但最终最好保持上述命令可通过。

开发风格：
- 使用 Python 3.11 标准库优先，暂时不要引入重量级依赖，除非文档或测试明确需要。
- 保持 dataclass 合同简单、可序列化、可验证。
- 修改代码前先看现有 tests 的风格。
- 不要大范围重构已经通过的 Phase 0/1，除非新阶段确实需要。
- 新增行为必须有聚焦测试。

请在开始实现前先用 git status 查看工作区，避免覆盖用户未提交修改。
```
