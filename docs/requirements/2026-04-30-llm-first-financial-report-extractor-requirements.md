# LLM-First 财报抽取器需求文档

## 1. 背景

当前 `financial-report-analysis` 采用 deterministic-first 架构，通过表格结构恢复、
指标映射、事实治理、P5 dataset、Turtle export 和 recompute audit 提供高确定性
财报事实。这套架构适合稳定字段、长期回归测试和可治理输出。

但在新增公司、新市场、新财报格式和新增字段时，现有路径经常需要补充结构恢复、
row label mapping、negative controls 和 focused specs。对于“尽快从陌生财报中拿到
Turtle v0.15 所需数据”的目标，这条路线太重。

因此新项目应作为独立应用建设，不复用现有 canonical facts、metric lifecycle、
P5 recompute 或 deterministic registry。

## 2. 目标

建设一个独立的 LLM-first 财报抽取应用，从 PDF 年报中按 Turtle v0.15 字段清单抽取
结构化数据，并为每个结果保留证据。

核心目标：

- 面向新公司、新格式时减少手写规则和 registry 扩展。
- 按字段优先级抽取，而不是一次性尝试理解整份财报。
- 每个 `present` 结果必须有页码、chunk/block id 和原文证据；若可获得 table id、
  row/cell/bbox，也应作为附加 evidence metadata 保存，但 `table_id` 不是必需字段。
- 支持 `missing`、`ambiguous`、`not_applicable` 和 `extraction_failed`，避免
  LLM 为了填空而编造。
- 产出独立 JSON，可用于人工 review、投资分析或与 deterministic 结果对比。

### 2.1 架构护栏

第一阶段必须避免退回旧项目中风险最高的“表格驱动优先”路线。财报表格在不同公司、
不同市场、不同 PDF 生成方式下差异很大，完整恢复表格结构不应成为字段抽取的前置条件。

推荐主路径：

```text
PDF
  -> page text / layout evidence blocks
  -> statement or section logical chunks
  -> field-scoped retrieval
  -> LLM extracts raw candidate values and evidence
  -> deterministic money/unit normalizer
  -> schema/evidence/derivation validator
  -> reviewable JSON
```

硬性约束：

- Evidence-block-first：先保证页文本、布局行、段落、statement line、section window
  可追溯；table row/cell/bbox 是增强信息，不是必需主路径。
- 不要求完整 table stitching 后才能抽取字段。只要证据 block、单位上下文、期间和 scope
  足够清晰，就可以进入检索和 LLM 抽取；置信度和 ambiguity 由 validator/reviewer 管理。
- 不做 whole-document extraction。LLM 调用应按字段或小字段组，并限制在相关 statement/section
  logical chunks 内。
- 不依赖纯向量 RAG。第一阶段 retrieval 必须结合 field alias、statement hint、period、scope、
  unit/currency context 和邻近块。
- Prompt 不是可信边界。schema validation、evidence enforcement、金额归一化、推导字段校验、
  period/scope consistency 必须由代码执行。
- LLM 不负责最终金额归一化。LLM 只抽取 `value_raw`、`unit_context`、`currency_hint`
  和 evidence；最终 `currency`、`unit_multiplier`、`normalized_value` 由 deterministic
  normalizer 计算。
- 不隐式做汇率换算，不静默混合币种，不在多候选值中强行选一个。
- 市场/版式级规则可以存在，例如 A 股中文报表、港股英文双栏、多币种列；第一阶段应避免发行人
  专属 patch。
- 每次运行必须保存 page/chunk/retrieval/raw LLM/parsed response/normalized result/run metadata，
  便于复现和 review。
- 开发期和分析期生成的中间产物默认写入当前项目内 `tmp/`，不要写入系统 `/tmp`。`tmp/`
  下内容应可由源 PDF 和代码重建。

对应的反目标：

- 不把完整表格恢复作为第一阶段成败标准。
- 不把 `PdfTableStructureAdapter` 式确定性表格分类器作为新系统核心。
- 不让 agent skill 替代 parser、normalizer、validator 或 artifact store。
- 不在抽取阶段生成整篇投资分析报告。

## 3. 产品形态决策：独立应用优先，Skills 作为薄封装

这个项目不应该只写成 Codex 或 Claude Code skill。推荐形态是：

```text
独立应用 / Python package / CLI / API
+ 可选 Codex skill
+ 可选 Claude Code skill
```

### 3.1 为什么核心不应只是 skill

Skill 更适合作为“告诉 LLM 怎么做”的工作流说明，不适合作为长期承载抽取系统的主体。

如果只做 skill，会遇到几个问题：

- 状态难管理：PDF chunks、embedding index、extraction runs、评估结果需要持久化。
- 可重复性弱：同一份财报、同一字段、同一 prompt/schema 版本需要可复现输出。
- 测试边界弱：字段 catalog、检索、schema validation、evidence enforcement 都应由代码测试。
- 供应商耦合：Codex skill 和 Claude Code skill 的格式不同，不应让业务核心绑定某个 agent。
- 批处理困难：后续要支持多 PDF、多公司、多年度、重跑和对比，应用边界更自然。

### 3.2 Skill 适合做什么

Skill 适合做 agent 入口和操作手册，而不是核心抽取引擎。

Codex/Claude Code skill 可以负责：

- 指导 agent 调用本项目 CLI/API。
- 解释 Turtle 字段优先级。
- 约束 agent 不要接受无证据的 `present` 结果。
- 帮用户选择字段范围，例如 P0、P0+P1、或指定字段。
- 帮用户阅读 extraction report，生成 review 总结。
- 在人工确认后生成后续分析 prompt。

Skill 不应该负责：

- 直接解析 PDF。
- 手写一次性 prompt 后把结果当事实。
- 保存最终事实库。
- 管理 embedding index。
- 替代 schema validation。
- 绕过 evidence requirement。
- 替代金额、币种和单位归一化逻辑。

### 3.3 推荐边界

```text
financial-report-llm-extractor
  负责解析、切片、检索、LLM 调用、schema 校验、结果存储、测试。

codex/claude skill
  负责教 agent 如何调用 extractor，以及如何 review extractor 输出。
```

这样保留两个优势：

- 应用提供可测试、可重复、可批处理的工程基础。
- Skill 提供低摩擦的人机协作入口，让 Codex/Claude Code 能自然使用这个工具。

## 4. 用户场景

### 4.1 单份年报抽取

用户提供一个 PDF 路径和字段优先级，例如 `P0+P1`。系统解析 PDF，构建 chunks，
逐字段检索证据并调用 LLM，输出结构化 JSON。

### 4.2 指定字段补抽

用户发现某些字段缺失，例如 `total_cur_assets`、`defer_tax_liab`，可以只针对这些
字段重新检索和抽取。

### 4.3 结果 review

用户或 agent 查看每个字段的 value、unit、period、scope、confidence 和 evidence。
无证据字段不得显示为 `present`。

### 4.4 与 deterministic 系统对比

后续可以把 LLM 抽取结果与现有 deterministic availability 或 Turtle dataset 对比，
发现 deterministic 缺口或 LLM 可疑项。但对比结果不自动写回旧系统。

## 5. 字段范围与优先级

字段来源以 Turtle v0.15 gap analysis 为准，落地到
`field_catalog/turtle_v015_priority_fields.json`。

### P0：Turtle 核心数据包

三大表主表和投资分析反复消费的核心字段。第一阶段即使 deterministic 系统已有，
LLM-first 也应独立抽取一遍，作为替代路径的完整性验证。

### P1：高价值主表增强

利润增强、流动资产/负债、递延税项、少数股东权益等字段。它们是第一版之后最重要的
增强对象。

### P2：现金流增强

现金流附表和补充披露中常见，但格式变化更大的字段。建议在 P0/P1 稳定后推进。

### P3：附注 / 公告桥接

分红、回购、资本化研发、资本化利息、账龄坏账、关联方应收应付、或有负债、租赁负债
分层、分部收入利润等。它们应作为 reviewable signal，而不是强行变成标准事实。

### P4：文本型 review artifact

MD&A、审计意见、股息政策、风险因素等。用于投资分析素材和 review，不进入数值事实层。

## 6. 输出合同

每个字段输出一个或多个 extracted item：

```json
{
  "field_id": "total_cur_assets",
  "status": "present",
  "value": 123456,
  "value_raw": "123,456",
  "currency": "CNY",
  "unit": "CNY thousand",
  "unit_multiplier": 1000,
  "normalized_value": 123456000,
  "normalized_unit": "CNY",
  "period": "2025 FY",
  "scope": "consolidated",
  "confidence": 0.91,
  "evidence": [
    {
      "page": 88,
      "chunk_id": "p88_table_1",
      "block_id": "p88_table_1_r12",
      "snippet": "流动资产合计 ..."
    }
  ]
}
```

状态枚举：

- `present`
- `missing`
- `ambiguous`
- `not_applicable`
- `extraction_failed`

硬性规则：

- `present` 必须有 evidence。
- `value` 必须能从 evidence 中定位或推导，不能只来自 LLM 总结。
- `unit`、`period`、`scope` 不确定时必须显式标记为 `unknown` 或 `ambiguous`。
- 同一字段存在多个候选值时，不应静默选择，应输出 ambiguity 或候选列表。
- 金额字段必须保留原始展示值、币种、单位倍率和归一化值；不能只保存一个无上下文数字。

### 6.1 货币、单位与倍率

财报里常见多种币种和展示单位，例如人民币、港币、美元，以及 `元`、`千元`、`万元`、
`百万元`、`RMB'000`、`HK$ million`、`US$ million`、`$ Million`、`k`、`m`。
系统必须把“原始展示值”和“归一化值”分开管理。

推荐金额结构：

```json
{
  "value_raw": "280,036",
  "value": 280036,
  "currency": "HKD",
  "unit": "HKD million",
  "unit_multiplier": 1000000,
  "normalized_value": 280036000000,
  "normalized_unit": "HKD"
}
```

规则：

- `value_raw` 保存 evidence 中的原始数字文本。
- `value` 是按原始展示单位解析出的数值，不乘倍率。
- `currency` 使用 ISO 风格代码：`CNY`、`HKD`、`USD`、`unknown` 或 `ambiguous`。
- `unit_multiplier` 表示展示单位相对基础币种单位的倍率，例如 `元=1`、`千元=1000`、
  `万元=10000`、`million=1000000`。
- `normalized_value = value * unit_multiplier`，只做同一币种下的倍率归一化。
- 抽取层不做汇率换算。跨币种比较、换算为人民币或美元，应由后续分析层显式执行并记录汇率来源。
- 如果币种或倍率无法从证据中确定，金额字段应标记 `ambiguous`，或把对应字段设为
  `unknown`，不得默认假设。
- 金额归一化不能只由 LLM 或 agent skill 完成。LLM 可以抽取 `value_raw`、候选单位上下文、
  currency hint 和 evidence；最终 `currency`、`unit_multiplier`、`normalized_value` 必须由
  本项目的确定性 normalizer/validator 计算和校验。

币种和单位解析优先级：

1. 表格标题附近的单位行，例如 `单位：元 币种：人民币`、`HK$ million`。
2. 列标题或表头，例如 `2025 HK$ million`、`US$ million`。
3. 行内标记或脚注。
4. 报告全局 reporting currency metadata。
5. 无法确认时标记 `unknown` 或 `ambiguous`。

多币种列处理：

- 如果同一表同时出现 `US$ million` 和 `HK$ million`，应优先选择报表正式 reporting
  currency 列，并在 metadata 中记录被选择的列。
- 不能把不同币种列混合用于同一字段。
- 如果字段来自推导计算，参与计算的所有 evidence 必须使用同一币种和倍率；否则输出
  `ambiguous`。

英文缩写处理：

- `k` / `K` 只有在金额上下文明确时才解释为 thousand。
- `m` / `M` / `mn` 只有在金额上下文明确时才解释为 million。
- `$` 不能单独确定币种，必须结合报告市场、表头、单位行或 metadata。

推荐处理流：

```text
LLM extraction
  -> value_raw / unit_context / currency_hint / evidence
money normalizer
  -> value / currency / unit_multiplier / normalized_value / normalized_unit
validator
  -> schema check / evidence check / currency-unit consistency
```

如果 normalizer 无法确定币种或倍率，应返回结构化错误，由 extraction result 标记为
`ambiguous`、`missing` 或 `extraction_failed`，而不是要求 LLM 猜测。

### 6.2 财报字段语义与推导字段

不同市场的报表命名不同。字段 catalog 应支持中英文别名和 statement hints，例如：

- `资产负债表` / `Consolidated Statement of Financial Position`
- `利润表` / `Consolidated Income Statement` / `Consolidated Statement of Profit or Loss`
- `现金流量表` / `Consolidated Statement of Cash Flows`
- `归属于母公司股东的净利润` / `Profit attributable to ordinary shareholders`
- `货币资金` / `Cash and cash equivalents` / `Bank balances and deposits`

部分字段在港股英文报表中可能不是单行展示，例如 `total_assets`、`total_liabilities`。
第一阶段允许 evidence-backed derived value，但必须满足：

- 输出标记 `derivation`，说明计算公式。
- evidence 列出所有参与计算的行。
- 所有参与行的币种、倍率、期间和 scope 必须一致。
- 如果缺少任一参与行，或口径不一致，应输出 `ambiguous` 或 `missing`。

示例：

```json
{
  "field_id": "total_assets",
  "status": "present",
  "value": 1155673,
  "currency": "HKD",
  "unit": "HKD million",
  "unit_multiplier": 1000000,
  "normalized_value": 1155673000000,
  "derivation": {
    "formula": "non_current_assets + current_assets",
    "inputs": ["non_current_assets", "current_assets"]
  },
  "evidence": [
    {"page": 136, "block_id": "p136_row_non_current_assets", "snippet": "Non-current assets ... 942,930"},
    {"page": 136, "block_id": "p136_row_current_assets", "snippet": "Current assets ... 212,743"}
  ]
}
```

## 7. RAG / Chunk Store 合同

财报 PDF 的表格和关键文字经常跨页。系统不应只按单页切片，也不应把相邻页粗暴拼成
不可追溯的大文本。推荐采用“原子证据 + 逻辑切片”两层结构：

- `page atom`：按页保存原始文本，是最小可回放来源。
- `block atom`：页内段落、标题、表格片段或表格行，保留 page、block id、文本和可选 layout metadata。
- `logical chunk`：面向 RAG/LLM 的上下文，可以跨页，例如一张跨页的合并现金流量表或一个跨页段落。

硬性规则：

- RAG chunk 可以跨页，但 evidence atom 必须保持页级和 block 级可追溯。
- `chunk_id` 可以指向跨页 logical chunk；`page`、`block_id`、`snippet` 必须指向具体证据位置。
- chunk store 是 evidence lookup 的来源；embedding/vector index 是可重建派生物，不是事实源。
- 同一 PDF、同一 parser/chunker 版本下，chunk id 应尽量稳定，便于 diff 和重跑。
- parser version、chunker version、embedding model/version、source PDF hash 必须写入 metadata。
- PDF、parser 或 chunker 版本变化时，应重建 chunk store 和 retrieval index。

推荐第一阶段 chunk 类型：

- `page_text`
- `paragraph`
- `section_window`
- `layout_line`
- `statement_line`
- `table_fragment`
- `statement_table`
- `table_row`

跨页 statement / 表格处理：

- 遇到“合并资产负债表”“合并利润表”“合并现金流量表”等标题时，开启 statement section。
- 下一页如果没有新的大标题，且列结构或表格语义延续，应并入同一个 `statement_table` logical chunk。
- 遇到“母公司资产负债表”“公司负责人”或新报表标题等结束信号时，关闭当前 logical chunk。
- 表头、单位、期间列和每个字段行都应尽量保留独立 block，可用于 evidence。
- 如果 PDF backend 无法稳定产出 table row/cell，系统仍应从 layout line、statement line 和邻近
  unit/context block 构建可 review 的 evidence。完整表格恢复不是抽取前置条件。
- 港股英文年报常见双栏或多栏页面。chunker 应尽量按 layout column 或 statement region 切分，
  避免把左侧财务状况表和右侧权益变动表交错成一个不可审计 block。

跨页文字处理：

- 按章节标题建立 section，例如审计报告、管理层讨论与分析、财务报表附注。
- 页末段落如果没有自然终止符，下一页开头又不是新标题，应合并为跨页 paragraph logical chunk。
- 长章节不应整体塞给 LLM，应使用 section window 或 sliding window，把命中 block 的相邻上下文一起提供。

LLM 抽取字段时可以读取跨页 logical chunk，但输出证据必须落到具体页和 block：

```json
{
  "field_id": "operating_cash_flow",
  "status": "present",
  "value": 61522204989.35,
  "unit": "CNY",
  "period": "2025 FY",
  "scope": "consolidated",
  "evidence": [
    {
      "page": 65,
      "chunk_id": "stmt_cashflow_consolidated_2025_p64_p66",
      "block_id": "p65_table_cashflow_r_operating_cash_flow",
      "snippet": "经营活动产生的现金流量净额 61,522,204,989.35 92,463,692,168.43"
    }
  ]
}
```

## 8. LLM 配置与通信层

第一阶段必须包含明确的 LLM 配置和通信边界，不能只在抽取逻辑里临时调用某个 SDK。
可以参考 `../hermes-agent` 的成熟做法：配置文件管理 model/provider/base_url，密钥从环境变量读取，
通信层负责 provider 解析、请求参数组装、超时、重试和响应归一化。

但本项目和 agent 类应用的目标不同。财报抽取结果需要可复现、可审计，因此第一阶段不应默认启用
“自动换 provider 继续抽取”。如果发生 provider、model 或 endpoint 变化，必须记录到 extraction run
metadata 中；可选 fallback 也只能显式开启。

### 8.1 配置来源

推荐使用项目级配置文件，例如：

```yaml
llm:
  default:
    provider: openai_compatible
    model: gpt-4.1
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
    temperature: 0
    max_output_tokens: 4096
    timeout_seconds: 120
    retry_count: 2
    retry_backoff_seconds: 2
    structured_output_mode: json_schema
  tasks:
    field_extraction:
      model: gpt-4.1
      temperature: 0
    response_repair:
      model: gpt-4.1-mini
      temperature: 0
```

配置优先级：

1. CLI/API 显式参数。
2. 项目配置文件。
3. 环境变量中的密钥和 endpoint override。
4. 内置默认值。

API key 不应写入 extraction output，只记录 `api_key_env` 名称和 provider/model/base_url。

### 8.2 通信层职责

通信层应提供 provider-neutral 接口：

- `LlmConfigResolver`：解析任务级配置、环境变量和运行时 override。
- `LlmClient`：暴露 `extract_field(request) -> response` 或更通用的 `complete_json(request)`。
- `LlmTransport`：封装具体协议，例如 OpenAI-compatible chat completions。
- `LlmResponseParser`：从 provider response 中提取 JSON、usage、latency、finish reason 和 raw text。
- `FakeLlmClient`：用于测试 schema validation、evidence enforcement 和 error path。

第一阶段可以只实现 OpenAI-compatible endpoint，但接口必须允许后续增加 Anthropic、OpenRouter、
本地 vLLM/Ollama 或其他 provider。

### 8.3 错误处理

LLM 通信层至少要区分：

- 配置错误：缺少 API key、base_url 无效、model 为空。
- 网络错误：timeout、connection error。
- provider 错误：401/403、429、5xx、content filter、输出截断。
- 响应错误：非 JSON、schema validation failed、缺少 required fields。

网络和 429/5xx 可以有限重试。认证错误、schema 长期不匹配、无证据 `present` 不应无限重试；
它们应进入 `extraction_failed` 或触发一次可记录的 repair pass。

### 8.4 结构化输出与证据校验边界

LLM 可以被要求按 JSON schema 输出，但最终可信边界在本项目代码中：

- schema validation 由本项目执行。
- `present` evidence enforcement 由本项目执行。
- value 是否可从 evidence snippet 定位或推导，由 validator/reviewer 标记。
- 原始 LLM 响应和 parsed JSON 应保存到 run artifact，便于审计和复现。

## 9. 第一阶段范围

第一阶段只做最小可用闭环：

- 单份年度 PDF。
- P0 + P1 字段。
- PDF text + layout evidence blocks + optional table/cell metadata。
- 本地 JSON chunk store，包含 page atoms、block atoms 和可跨页 logical chunks。
- 本项目内 `tmp/runs/<run_id>/...` 作为默认中间产物目录，保存 pages、chunks、retrieval、
  LLM raw/parsed response、extraction result 和 run metadata。
- 三大表跨页 statement chunk 识别，以及 P0/P1 字段的 concrete evidence blocks。
- 金额字段的币种、单位倍率、归一化值和多币种列选择。
- 中英文 statement/field aliases，以及少量 evidence-backed derived value。
- statement-aware、field-scoped 关键词/规则检索；embedding 或混合检索可以作为后续增强。
- LLM 配置解析、provider-neutral 通信接口和 OpenAI-compatible transport。
- JSON 输出。
- 基础测试：field catalog、schema validation、evidence enforcement、LLM config resolver、FakeLlmClient。

暂不做：

- UI。
- 多用户。
- async job workflow。
- 数据库产品化。
- 自动下载财报。
- 写回 deterministic 系统。
- 技术指标、行情、WebSearch 行业信息。

## 10. 后续演进

第二阶段可以增加：

- 多 PDF / 多年度 batch。
- extraction run 持久化。
- prompt/schema versioning。
- review feedback 数据集。
- 对比 deterministic 输出的 diff report。
- Codex skill / Claude Code skill。
- 可选 HTTP API。
- 多 provider transport 和显式 fallback policy。
- 更强的跨页表格结构恢复、bbox/cell-level evidence 和复杂附注合并；这些仍应作为 evidence
  enrichment，不应替代 evidence-block-first 主路径。

第三阶段再考虑：

- Agentic extraction planning。
- 表格跨页恢复增强。
- 复杂附注检索。
- 投资分析报告生成。
- export adapter。

## 11. 成功标准

第一阶段成功标准：

- 能对一份陌生年报抽取 P0+P1 字段。
- 每个 `present` 字段都有可读证据。
- 跨页表格或跨页文字中的字段可以被抽取，并能回指到具体页和 block。
- 人民币、港币、美元以及 `元`、`千元`、`万元`、`HK$ million`、`US$ million`
  等单位能被统一解析，且不做隐式汇率换算。
- 港股英文年报中的 reporting currency 列、双栏表格和派生字段能被明确处理或标记为 ambiguous。
- 缺失字段能明确标记，不编造。
- 同一字段的抽取过程可重跑、可比较。
- 每次 extraction run 记录实际使用的 provider、model、base_url、prompt/schema 版本和 LLM error metadata。
- 用户可以根据 JSON 结果判断是否值得继续扩展 P2/P3/P4。
