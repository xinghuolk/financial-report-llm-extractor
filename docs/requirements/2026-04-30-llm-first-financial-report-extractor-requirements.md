# LLM-First 财报抽取器总需求 SPEC

> 日期：2026-04-30
> 状态：总需求
> 范围：构建一个独立的 LLM-first 财报抽取器，从年报 PDF 中生成带证据、可审计、可复跑的 Turtle 风格 JSON。

## 1. 背景

`financial-report-llm-extractor` 是一个独立项目，不依赖现有 deterministic
`financial-report-analysis` 的 canonical facts、metric lifecycle、P5 dataset、
recompute audit 或 registry 治理流程。

现有 deterministic-first 路径适合长期稳定字段和严格回归，但在新增公司、新市场、新报告格式、新字段时，通常需要补充大量结构恢复、row label mapping、negative controls 和 focused specs。这个项目的目标不同：它要更快地从陌生年报中生成可 review 的候选财务字段，并把证据、歧义和失败原因显式暴露出来。

## 2. 核心目标

系统应支持：

- 从单份年报 PDF 建立 page/block/chunk 证据存储。
- 建立 document map 和 statement map，识别正式财务报表区域，而不是只按字段关键词搜索全文。
- 使用 LLM 辅助发现 statement row labels 和候选 raw values。
- 将发现到的行项目映射到 Turtle v0.15 P0/P1 字段。
- 对字段或小字段组执行小范围 LLM 抽取。
- 使用代码执行金额、币种、单位、期间、scope、evidence 和派生值校验。
- 输出 JSON-first artifacts，便于人工 review、回归比较和后续分析。

系统不应：

- 让 LLM 一次性读取整份 PDF 并直接输出最终 P0/P1 字段。
- 让 prompt 成为信任边界。
- 信任 LLM 返回的 normalized money。
- 在币种、期间、scope 或候选值不明确时静默选择一个值。
- 把完整表格重建作为字段抽取的前置硬依赖。
- 把 Codex/Claude skill 当成业务核心。skill 只能是薄封装。

## 3. 总体主路径

推荐主路径：

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
-> reviewable JSON artifacts
```

这条路径比单纯 field-scoped retrieval 多了三层：

- `document map`：识别目录、审计报告、正式财务报表、notes、MD&A、financial summary 等区域。
- `statement map`：识别 income statement、balance sheet、cash flow statement 及其 page range、unit、currency、period columns、scope。
- `row discovery`：在 statement chunk 内发现行项目，而不是假设所有公司都使用 catalog 里的固定别名。

## 4. LLM 使用边界

LLM 可以参与：

- 判断候选页面是否属于正式财务报表区域。
- 从目录、审计报告引用和标题上下文中辅助建立 document map。
- 对 statement chunk 做 row inventory。
- 给 discovered row 提供候选语义解释。
- 在字段级 prompt 中抽取 `value_raw`、`unit_context`、`currency_hint`、period、scope、confidence 和 evidence refs。

LLM 不可以：

- 直接从整篇 PDF 输出最终 Turtle P0/P1。
- 绕过 page/chunk/block/snippet evidence。
- 决定最终 `normalized_value`。
- 做隐式 FX conversion。
- 在多个币种、期间、scope 或候选行之间无证据地强行选择。

禁止模式：

```text
whole PDF text
-> LLM
-> final P0/P1 extracted fields
```

允许模式：

```text
statement chunk + headers + neighbor blocks
-> LLM row discovery or field extraction
-> deterministic validator
```

## 5. Evidence Contract

每个 `present` item 必须有证据：

- `page`
- `chunk_id`
- `block_id`
- `snippet`

证据必须指向真实存在的 page/block/chunk。若 logical chunk 跨页，最终 evidence 仍必须落到具体 page 和 block。

review 中已暴露出的合同风险必须优先修复：

- retrieval evidence 不能总是使用 candidate chunk 的第一个 `block_id`。当 matched alias 或 snippet 出现在 chunk 后续 block 时，evidence 必须指向包含该文本的 block。
- raw LLM response 即使无法 parse，也必须归档到 artifacts，不能因为 JSON malformed 或 provider schema 异常而丢失原始响应。
- chunk 输出路径若是嵌套目录，CLI 必须自动创建父目录。

## 6. Page/Block/Chunk Store

证据存储至少包含三层：

- `page atom`：PDF 单页文本和页码。
- `block atom`：页内段落、标题、layout line、statement line、table fragment 或 table row。
- `logical chunk`：面向 document map、retrieval 和 LLM 的上下文窗口，可跨页。

第一阶段推荐 chunk kinds：

- `page_text`
- `paragraph`
- `section_window`
- `layout_line`
- `statement_line`
- `table_fragment`
- `statement_table`
- `table_row`

要求：

- chunk store 是 durable evidence source。
- embedding/vector index 只能是可重建派生产物。
- parser version、chunker version、source PDF hash 必须进入 metadata。
- table/cell/bbox 是 evidence enrichment，不是主路径硬依赖。

## 7. Document Map

Document map 应识别：

- 目录页。
- 审计报告页。
- 正式财务报表 page range。
- notes page range。
- MD&A / 管理层讨论范围。
- 五年摘要 / financial summary 范围。
- 报告语言、市场、报告期、公司名。

Document map 输出应是结构化 artifact，并带 evidence：

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

## 8. Statement Map

Statement map 应识别：

- income statement / statement of comprehensive income。
- balance sheet / statement of financial position。
- cash flow statement。
- statement of changes in equity。
- consolidated vs parent/company。
- current year and prior year columns。
- unit and currency context。

输出示例：

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

## 9. Row Discovery

Row discovery 的目标是在 statement chunk 中列出可映射的财务行项目。

LLM 输入应包含：

- statement title。
- scope。
- period columns。
- unit/currency context。
- statement blocks。
- 必要 neighbor blocks。

LLM 输出 row inventory，而不是最终 extracted items：

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

Row inventory 只是中间 artifact。最终字段仍需 catalog mapping、field-scoped extraction 和 validator。

## 10. Field Catalog And Mapping

字段目录来源为 `field_catalog/turtle_v015_priority_fields.json`，后续应扩展为 extraction catalog。

每个 catalog entry 应包含：

- `field_id`
- priority：P0/P1/P2/P3/P4
- value type：money、number、percent、text、derived
- Chinese aliases
- English aliases
- statement hints
- scope hints
- period expectations
- unit/currency expectations
- derivation metadata when applicable

Catalog mapping 输入：

- discovered row label。
- statement kind。
- scope。
- period。
- unit/currency context。
- field catalog aliases and hints。

低置信度、多候选、口径冲突时，输出 `ambiguous`，不能硬选。

## 11. Money And Unit Normalization

LLM 只可提供：

- `value_raw`
- `unit_context`
- `currency_hint`
- evidence refs

代码必须计算：

- `value`
- `currency`
- `unit`
- `unit_multiplier`
- `normalized_value`
- `normalized_unit`

需支持：

- CNY/RMB、HKD、USD、unknown、ambiguous。
- `元`、`千元`、`万元`、`亿元`、`RMB'000`、`RMB in thousands`、`RMB in millions`、`HK$'000`、`HK$ million`、`US$ million`、`$ million`、`k`、`m`、`mn`。
- parentheses negatives、minus signs、commas、dash missing values。

规则：

- `normalized_value = value * unit_multiplier`。
- 不做 FX conversion。
- `$` 不能单独决定币种。
- 多币种列必须选择明确 reporting-currency column，无法确定则 `ambiguous`。
- derived value 的所有输入必须 period、scope、currency、unit 一致。

## 12. LLM Config And Transport

系统必须有 provider-neutral LLM boundary：

- `LlmConfigResolver`
- `LlmClient`
- `OpenAICompatibleTransport`
- `GeminiGenerateContentTransport`
- `LlmResponseParser`
- `FakeLlmClient`

首批必须支持的 provider：

- `openai-compatible`：显式 `base_url`，使用 `OPENAI_API_KEY` 或配置中的 `api_key_env`。
- `deepseek`：默认 `base_url=https://api.deepseek.com/v1`，默认 `api_key_env=DEEPSEEK_API_KEY`，走 OpenAI-compatible `/chat/completions`。
- `ollama`：默认 `base_url=http://localhost:11434/v1`，默认 `api_key_env=OLLAMA_API_KEY`，走 OpenAI-compatible `/chat/completions`；本地无 key 时必须省略 `Authorization`。
- `gemini`：默认 `base_url=https://generativelanguage.googleapis.com/v1beta`，默认 `api_key_env=GEMINI_API_KEY`，走 `/models/<model>:generateContent`；默认 env 缺失时可 fallback 到 `GOOGLE_API_KEY`。

每次 run 必须记录：

- provider
- model
- base_url
- prompt version
- schema version
- latency when available
- usage when available
- finish reason when available
- structured transport/parse errors

API key 只能从环境变量读取，不得写入 artifacts。可记录 `api_key_env` 名称。

provider fallback 默认关闭。若后续支持 fallback，必须显式开启，并记录每次 provider/model/base_url 的变化。

## 13. Output Artifacts

默认使用仓库内 `tmp/`，而不是系统 `/tmp`。

推荐 run layout：

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

## 14. First Slice Scope

第一可用切片：

- 单份 annual PDF。
- P0 + P1 核心字段。
- CLI + JSON artifacts。
- fake LLM mode 必须可离线跑。
- real LLM mode 必须通过显式 config 启用。
- 默认不需要 UI、数据库、批处理队列或自动下载。

优先验证样本：

- `downloads/cn_stocks/600519/annual/2025_年度报告.pdf`
- `downloads/hk_stocks/00001/annual/2025_annual_en.pdf`
- `downloads/hk_stocks/01113/annual/2025_annual_en.pdf`

扩展验证样本：

- `300750`
- `601919`
- `688008`
- `01810`
- `02498`
- `06862`
- `09987`

## 15. Success Criteria

第一阶段成功标准：

- 可以对陌生 annual PDF 生成 document map、statement map、row inventory 和 selected P0/P1 extraction result。
- 每个 `present` 字段都有可读 evidence。
- 正式报表与目录、五年摘要、MD&A、notes 能被区分。
- 跨页 statement 或跨页文字中的字段可以追溯到具体 page/block。
- CNY/HKD/USD 和常见中英文单位能 deterministic normalize。
- HK English 年报中的 reporting currency、双列/多列、derived fields 能处理或显式标记 ambiguous。
- 缺失字段明确标记，不编造。
- 同一字段抽取过程可复跑、可比较。
- 每次 run 记录 provider/model/base_url/prompt/schema/errors。
