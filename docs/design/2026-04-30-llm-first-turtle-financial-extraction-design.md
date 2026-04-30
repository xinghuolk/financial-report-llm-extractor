# LLM-First Turtle 财报抽取总设计

> 日期：2026-04-30
> 状态：总设计
> 关联需求：`docs/requirements/2026-04-30-llm-first-financial-report-extractor-requirements.md`

## 1. 设计目标

本项目要构建一个独立的财报抽取系统。它从年报 PDF 中生成 Turtle 风格的结构化 JSON，但不写入 canonical fact store，也不复用 deterministic `financial-report-analysis` 的 metric lifecycle、P5 dataset 或 recompute 机制。

系统要解决的核心问题是：不同公司、不同市场、不同语言的年报表达差异很大。单纯依靠固定字段别名做 retrieval 容易漏召回，也容易把目录、五年摘要、MD&A、notes 中的值误当作正式财务报表值。因此，系统必须先理解文档结构和正式报表区域，再发现报表行项目，最后才映射到 Turtle 字段并执行字段级抽取。

## 2. 总体架构

主路径：

```text
PDF
-> parser capability probe
-> page/block evidence store
-> document map
-> statement map
-> LLM-assisted row discovery
-> catalog mapping
-> field-scoped extraction
-> deterministic money/unit normalization
-> schema/evidence/period/scope/derivation validation
-> review/export JSON
```

这不是“整份 PDF 给 LLM 直接抽字段”的架构。LLM 可以参与 discovery 和局部抽取，但每一步都要有可审计的中间 artifact。

## 3. 核心模块

### 3.1 Parser Capability Probe

职责：

- 检查当前 PDF backend 对样本报告的文本抽取质量。
- 记录 parser name/version、source PDF hash、page count。
- 识别中文 A 股 PDF、港股英文 PDF、扫描/字体编码异常 PDF 的基本可用性。

输出：

- parser metadata。
- page extraction quality signals。
- 可继续处理或需要 fallback 的状态。

设计理由：

本地样本验证显示，某些 backend 对 A 股中文年报无法抽出可搜索中文文本。系统不能假设一个 PDF parser 对所有市场都可靠。

### 3.2 Page/Block Evidence Store

职责：

- 将 PDF 转成 page atoms。
- 将 page text 切成 block atoms。
- 为每个 block 生成稳定 `block_id`。
- 保留 page、text、kind、optional layout/table metadata。

最小 block kinds：

- `layout_line`
- `paragraph`
- `statement_line`
- `table_fragment`
- `table_row`
- `section_heading`

要求：

- evidence store 是事实来源。
- 后续 retrieval、row discovery、field extraction 都必须引用这里的 block。
- chunk 可以跨页，但最终 evidence 必须落到具体 page/block/snippet。

### 3.3 Chunk Builder

职责：

- 从 blocks 构建 logical chunks。
- 支持 page chunks、section windows、statement chunks。
- 保留 chunk 到 block 的映射。

chunk kinds：

- `page_text`
- `section_window`
- `statement_table`
- `statement_window`

chunk 不是最终证据。chunk 只提供上下文；最终 `present` item 必须引用 block。

### 3.4 Document Map

职责：

- 识别报告结构。
- 区分目录、五年摘要、MD&A、审计报告、正式财务报表、notes。
- 找到正式财务报表 page range。

输入：

- page/block store。
- 目录页候选。
- 标题候选。
- 审计报告中对财务报表页码的引用。

可用方法：

- 规则：标题关键词、目录页、页码范围、审计报告引用。
- LLM：对候选页面/标题窗口做语义判断。

输出：

```json
{
  "sections": [
    {
      "kind": "audited_financial_statements",
      "page_start": 132,
      "page_end": 346,
      "confidence": 0.92,
      "evidence": [
        {
          "page": 129,
          "block_id": "p0129_b0003",
          "snippet": "financial statements ... set out on pages 132 to 346"
        }
      ]
    }
  ]
}
```

### 3.5 Statement Map

职责：

- 在 document map 中识别正式 statements。
- 解析 statement kind、scope、period columns、unit/currency context。
- 避免把 financial summary 或 MD&A 表格误当正式报表。

statement kinds：

- `income_statement`
- `balance_sheet`
- `cash_flow`
- `changes_in_equity`
- `notes`

scope：

- `consolidated`
- `parent`
- `company`
- `unknown`

输出：

```json
{
  "statements": [
    {
      "statement_kind": "income_statement",
      "scope": "consolidated",
      "page_start": 70,
      "page_end": 70,
      "title": "CONSOLIDATED INCOME STATEMENT",
      "unit_context": "$ Million",
      "period_columns": ["2025", "2024"],
      "evidence_blocks": ["p0070_b0001", "p0070_b0002"]
    }
  ]
}
```

### 3.6 LLM-Assisted Row Discovery

职责：

- 在一个 statement chunk 内发现 row labels、raw values 和上下文。
- 解决不同公司字段叫法不同的问题。
- 生成 row inventory，而不是最终 Turtle items。

输入 prompt 应限制在：

- statement title。
- statement kind。
- scope。
- period columns。
- unit/currency context。
- statement blocks。
- 必要 neighbor blocks。

输出：

```json
{
  "rows": [
    {
      "row_label": "Group revenue",
      "candidate_meaning": "group revenue",
      "values": [{"period": "2025", "value_raw": "57,935"}],
      "unit_context": "$ Million",
      "currency_hint": "HKD",
      "evidence": [
        {
          "page": 70,
          "block_id": "p0070_b0002",
          "snippet": "Group revenue 57,935 45,529"
        }
      ]
    }
  ]
}
```

Row discovery 的输出只能作为中间 artifact。它不能绕过 catalog mapping 和 validator。

### 3.7 Field Catalog And Catalog Mapping

职责：

- 将 discovered rows 映射到 Turtle 字段。
- 结合 row label、statement kind、scope、period、unit/currency context 和 field catalog。
- 给出 mapping confidence 和 reason。

字段目录应从 priority list 扩展为 extraction catalog：

- `field_id`
- priority
- value type
- Chinese aliases
- English aliases
- statement hints
- scope hints
- period expectations
- unit/currency expectations
- derivation metadata

输出：

```json
{
  "field_id": "revenue",
  "source_row_label": "Group revenue",
  "mapping_confidence": 0.86,
  "mapping_reason": "row appears in consolidated income statement and matches revenue aliases",
  "status": "mapped"
}
```

低置信度、多候选、scope 冲突或币种冲突时，返回 `ambiguous`。

### 3.8 Field-Scoped Extraction

职责：

- 对一个字段或小字段组执行最终 LLM extraction。
- 输入只包含已映射 row、对应 evidence blocks、headers、unit/period/scope context。
- 输出 raw candidate，不输出可信 normalized money。

LLM 允许返回：

- `status`
- `value_raw`
- `unit_context`
- `currency_hint`
- `period`
- `scope`
- `confidence`
- evidence refs

LLM 不允许决定：

- final `normalized_value`
- final currency conversion
- derived value validity
- evidence contract validity

### 3.9 Money Normalizer

职责：

- 将 LLM 抽取的 raw value 和上下文转换成 deterministic money。
- 在无法确认币种或单位时返回 structured ambiguity。

支持：

- CNY/RMB、HKD、USD、unknown、ambiguous。
- `元`、`千元`、`万元`、`亿元`。
- `RMB'000`、`RMB in thousands`、`RMB in millions`。
- `HK$'000`、`HK$ million`。
- `US$ million`、`$ million`。
- `k`、`m`、`mn`。
- commas、parentheses negatives、minus signs、dash missing values。

计算规则：

```text
normalized_value = value * unit_multiplier
```

不做 FX conversion。

### 3.10 Validator

职责：

- schema validation。
- evidence existence validation。
- evidence snippet/block consistency validation。
- money normalization validation。
- period/scope/currency/unit consistency validation。
- derived value validation。

硬规则：

- `present` 必须有 evidence。
- evidence 必须指向真实 block。
- matched snippet 应位于 evidence block 或可解释的邻近 block 中。
- monetary `present` 必须有 normalized money 或 structured ambiguity。
- derived value 必须列出所有 input evidence，且 inputs 的 period/scope/currency/unit 一致。

### 3.11 LLM Config And Transport

职责：

- 解析 provider/model/base_url/api_key_env/timeout/retry。
- 按 provider 构造 JSON completion request。
- 保存 prompt payload。
- 保存 raw response。
- 解析 JSON response。
- 记录 usage、latency、finish reason 和 structured errors。

组件：

- `LlmConfigResolver`
- `LlmClient`
- `OpenAICompatibleTransport`
- `GeminiGenerateContentTransport`
- `LlmResponseParser`
- `FakeLlmClient`

首批 provider：

- `deepseek` 和 `ollama` 使用 OpenAI-compatible `/chat/completions`。
- `gemini` 使用 `/models/<model>:generateContent`。
- `ollama` 本地模式允许没有 API key，并在未设置 key 时省略 `Authorization`。
- provider resolver 只选择 adapter，不做自动 provider fallback。

关键要求：

- API key value 不得写入 artifact。
- raw response 即使无法 parse 也必须归档。
- provider fallback 默认关闭。
- fake mode 和 real mode 应尽量共享命令形态。

## 4. Artifact Layout

推荐目录：

```text
tmp/
  runs/
    <run_id>/
      pages.jsonl
      chunks.jsonl
      document_map.json
      statement_map.json
      row_inventory.json
      catalog_mapping.json
      retrieval_probe.json
      prompt_payloads/
      raw_llm_responses/
      parsed_llm_responses/
      extraction_result.json
      run_metadata.json
      review_summary.json
```

所有 artifacts 都应能从 source PDF、代码版本、parser/chunker/prompt/schema/config metadata 重建或解释。

## 5. Extraction Output Contract

示例：

```json
{
  "field_id": "revenue",
  "status": "present",
  "value_raw": "57,935",
  "value": 57935,
  "currency": "HKD",
  "unit": "HKD million",
  "unit_multiplier": 1000000,
  "normalized_value": 57935000000,
  "normalized_unit": "HKD",
  "period": "2025 FY",
  "scope": "consolidated",
  "confidence": 0.86,
  "evidence": [
    {
      "page": 70,
      "chunk_id": "stmt_income_statement_p0070_p0070",
      "block_id": "p0070_b0002",
      "snippet": "Group revenue 57,935 45,529"
    }
  ]
}
```

状态：

- `present`
- `missing`
- `ambiguous`
- `not_applicable`
- `extraction_failed`

## 6. CLI/API Shape

第一阶段以 CLI + JSON 为主。推荐命令形态：

```text
financial-report-llm-extractor ingest --pdf <pdf> --out <run_dir>
financial-report-llm-extractor chunk --pages <pages.jsonl> --metadata <run_metadata.json> --out <chunks.jsonl>
financial-report-llm-extractor map-document --chunks <chunks.jsonl> --out <document_map.json>
financial-report-llm-extractor map-statements --chunks <chunks.jsonl> --document-map <document_map.json> --out <statement_map.json>
financial-report-llm-extractor discover-rows --chunks <chunks.jsonl> --statement-map <statement_map.json> --config <llm_config.json> --out <row_inventory.json>
financial-report-llm-extractor map-fields --catalog <catalog.json> --row-inventory <row_inventory.json> --out <catalog_mapping.json>
financial-report-llm-extractor extract --chunks <chunks.jsonl> --mapping <catalog_mapping.json> --config <llm_config.json> --out <extraction_result.json>
financial-report-llm-extractor evaluate --root <repo-root> --out <evaluation_summary.json>
```

实际实现可以分阶段落地，不要求一次完成全部命令。

## 7. 测试策略

优先测试：

- nested artifact output directory creation。
- evidence 指向包含 matched alias/snippet 的 block。
- malformed raw LLM response 仍被归档。
- document map 能区分目录、financial summary、MD&A 和正式报表。
- statement map 能识别不同英文标题变体。
- row discovery fake fixture 输出 row inventory。
- catalog mapping 对多候选返回 ambiguous。
- money normalizer 支持中英文单位和多币种 ambiguity。
- validator 拒绝 present without evidence。

真实样本：

- `600519_2025`：中文 A 股。
- `00001_2025_en`：港股英文大型综合公司。
- `01113_2025_en`：港股英文地产/综合，含多页与多区域结构。

扩展样本：

- `300750`
- `601919`
- `688008`
- `01810`
- `02498`
- `06862`
- `09987`

默认测试不得依赖真实网络。真实 LLM smoke test 必须 opt-in。

## 8. 近期五阶段计划

### Phase 9: Evidence Contract 修复

- 修复 retrieval evidence 指错 block。
- 修复 chunk 输出目录不自动创建。
- 修复 raw LLM response parse 失败时不归档。
- 加 focused tests。

### Phase 10: Parser Capability Probe And Document Map Demo

- 验证 PDF backend 对 A 股和港股样本的文本抽取能力。
- 生成 document map。
- 区分正式报表和摘要/MD&A/notes。

### Phase 11: Statement Map And Row Discovery

- 建立 statement map。
- 用 fake/real LLM 对 statement chunk 生成 row inventory。
- 保留 row-level evidence refs。

### Phase 12: Catalog Mapping And Field-Scoped Extraction

- 扩展 field catalog。
- 将 discovered rows 映射到 Turtle P0/P1。
- 对 selected fields 做小范围 extraction。

### Phase 13: Money/Scope Validation And Evaluation Loop

- 增强 money/unit/scope/period validation。
- 标准化 `tmp/runs/evaluation/<report_id>/`。
- 生成 JSON/Markdown review summary。
- 从真实报告 hard cases 沉淀 regression fixtures。

## 9. 非目标

第一阶段不做：

- UI。
- 数据库产品化。
- 多用户工作流。
- 自动下载财报。
- canonical fact promotion。
- deterministic recompute。
- FX conversion。
- 整篇投资分析报告生成。
- issuer-specific patch。
- full table reconstruction as a hard dependency。

## 10. 设计结论

后续架构应避免两个极端：

- 只靠固定 field aliases 做 retrieval，导致不同公司字段叫法变化时漏召回。
- 让 LLM 整篇读取 PDF 并直接输出最终字段，导致不可审计、不可复跑、难以定位错误。

正确方向是：

```text
先发现文档结构
再发现正式报表行项目
再映射 Turtle 字段
最后做字段级抽取和代码验证
```

这让 LLM 用在它擅长的语义发现上，同时把 evidence、money、period、scope 和 derivation 的信任边界保留在代码里。
