# Source-First Turtle 财报抽取器总需求 SPEC

> 日期：2026-05-01
> 状态：总需求修订
> 范围：构建一个独立的 source-first 财报抽取器，优先从 AKShare 和 Yahoo/yfinance 获取结构化财务数据，映射到 Turtle v0.15 字段，再用 PDF/LLM 做缺失、冲突、歧义和年报证据补充。

## 1. 背景

`financial-report-llm-extractor` 最初定位为 LLM-first PDF 财报抽取器：从年报 PDF 中构建 page/block/chunk evidence，再对 Turtle v0.15 P0/P1 字段做 field-first retrieval 和 LLM extraction。

真实 PDF 验证后，路线需要修订。当前 Turtle coverage budget 在港股英文报告上只覆盖约四分之一 P0/P1 required fields；继续扩大 PDF alias、statement localization 和 row discovery 会重新陷入不同公司、不同语言、不同表格结构的通用定位问题。

新的产品方向是 source-first：

```text
AKShare
-> Yahoo/yfinance
-> source field inventory
-> Turtle source mapping / derivation
-> currency/unit normalization
-> coverage and conflict gate
-> selected PDF financial report analysis
-> LLM-assisted evidence / ambiguity review
-> reviewable JSON artifacts
```

PDF 和 LLM 不再是第一轮全字段抽取主路径。它们保留为最后阶段的 evidence supplement、consistency review 和 hard-case fallback。

## 2. 核心目标

系统应支持：

- 定义 Turtle v0.15 P0/P1 字段的 source mapping contract。
- 通过 AKShare 获取 A 股、港股和可用美股的结构化财报数据。
- 通过 Yahoo/yfinance 获取港股、美股和标准化字段补充数据。
- 保存每次 source call 的 raw artifacts，保证可复跑、可审计、可对比。
- 将 source rows 映射到 Turtle 字段，保留 raw field、raw value、period、scope、currency、unit 和 source evidence。
- 对 AKShare 和 Yahoo/yfinance 输出单源 coverage 和组合 coverage。
- 对同一字段的多 source 结果做 period、scope、currency、unit、value reconciliation。
- 用代码执行货币、单位、倍率、派生字段、缺失和冲突校验。
- 只对 missing、ambiguous、conflict 或需要年报页码证据的字段进入 PDF/LLM fallback。
- 输出 JSON-first artifacts，便于人工 review、回归比较和后续分析。

系统不应：

- 先从 PDF 做 broad P0/P1 extraction，再用结构化数据补漏。
- 让 LLM 作为生产主路径自由调用 MCP 获取财务数据。
- 让 prompt 成为信任边界。
- 信任 source 或 LLM 返回的 normalized money，而不做代码校验。
- 在币种、单位、期间、scope 或 source 冲突时静默选择。
- 把 AKShare、Yahoo 或 Tushare 返回值直接提升为 canonical facts。
- 复制 TradingAgents-CN、report-collector 或旧 `financial-report-analysis` 的数据库、worker、metric lifecycle、P5、recompute 或 governance 架构。

## 3. 第一阶段主路径

第一阶段主路径是结构化数据源优先：

```text
Turtle P0/P1 source mapping contract
-> AKShare raw adapter
-> Yahoo/yfinance raw adapter
-> source inventory artifacts
-> source-to-Turtle mapping
-> deterministic money/unit normalization
-> source coverage gate
-> cross-source reconciliation
-> selected PDF/LLM fallback
-> review/export JSON
```

关键约束：

- AKShare 是第一优先级 source。
- Yahoo/yfinance 是第二优先级 source，用于补充和交叉验证。
- PDF 财报分析不参与第一轮 broad field coverage，只处理结构化来源无法稳定解决的问题。
- LLM 可用于解释字段语义、辅助 ambiguous mapping、补 PDF evidence 和做 consistency review，但不能绕过 adapter、raw artifacts、coverage gate 和 deterministic validation。

## 4. Turtle Source Mapping Contract

字段目录来源为 `field_catalog/turtle_v015_priority_fields.json`，需要扩展为 source mapping catalog。

每个 Turtle entry 应包含：

- `field_id`
- priority：P0、P1、P2、P3、P4
- value type：money、number、percent、text、derived
- statement type：income statement、balance sheet、cash flow、equity、notes、unknown
- period expectation：annual、quarterly、point-in-time、duration
- scope expectation：consolidated、parent/company、unknown
- currency requirement：required、optional、not_applicable
- unit requirement：required、optional、not_applicable
- source aliases：AKShare raw field names/codes、Yahoo/yfinance field names
- PDF aliases：仅用于 fallback 和 evidence supplement
- derivation metadata：公式、输入字段、输入一致性要求
- fallback policy：source_required、pdf_allowed、llm_review_required

最小 P0/P1 source-first spike 必须覆盖这些字段类别：

- revenue / operating revenue
- net income / profit attributable to shareholders
- total assets
- total liabilities
- total equity / shareholders equity
- cash and cash equivalents
- operating cash flow
- capital expenditure or capex candidate
- debt / borrowings candidate
- per-share 或 ratio 字段，如果 P0/P1 catalog 中要求

## 5. Source Evidence Contract

结构化来源的 evidence 和 PDF evidence 必须区分。

`source_evidence` 至少包含：

- `source`：akshare、yahoo
- `adapter`
- `function` 或 endpoint/tool name
- `artifact_id`
- `raw_record_id`
- `raw_field_name`
- `raw_field_code` when available
- `retrieved_at`
- `provider_version` when available

示例：

```json
{
  "source": "akshare",
  "adapter": "akshare",
  "function": "stock_financial_hk_report_em",
  "artifact_id": "akshare_00001_hk_balance_20240501.json",
  "raw_record_id": "00001:balance_sheet:2024-12-31:STD_ITEM_CODE",
  "raw_field_name": "STD_ITEM_NAME",
  "raw_field_code": "STD_ITEM_CODE"
}
```

`pdf_evidence` 沿用现有合同：

- `page`
- `chunk_id`
- `block_id`
- `snippet`

规则：

- source-first coverage 可由 `source_evidence` 支撑。
- 需要年报页码证据的 final export/profile 才要求补 `pdf_evidence`。
- `present` 字段必须至少有一种 evidence；若字段 profile 要求 PDF evidence，则缺 PDF evidence 时不得通过该 profile。

## 6. AKShare Requirements

AKShare adapter 必须：

- 显式声明并固定 AKShare 版本。
- 调用 AKShare 公共函数，不复制 site-packages 源码。
- 支持 A 股三大表和摘要指标。
- 支持港股三大表和主要指标。
- 保存 raw response artifact。
- 输出 source inventory rows。
- 对港股补 metadata join，保留 `CURRENCY`、`ACCOUNT_STANDARD`、`REPORT_TYPE`。
- 记录 source function、symbol、market、statement type、report type、period、raw columns。
- 对接口异常输出结构化错误，不静默返回空成功。

第一批参考接口：

- `stock_balance_sheet_by_report_em`
- `stock_profit_sheet_by_report_em`
- `stock_cash_flow_sheet_by_report_em`
- `stock_financial_report_sina`
- `stock_financial_abstract`
- `stock_financial_hk_report_em`
- `stock_financial_hk_analysis_indicator_em`

## 7. Yahoo/yfinance Requirements

Yahoo/yfinance adapter 必须：

- 作为第二优先级结构化 source。
- 支持 income statement、balance sheet、cash flow 和 stock info。
- 保存 raw JSON artifact。
- 输出 source inventory rows。
- 记录 ticker、market suffix、period、statement type、raw field name、raw value。
- 明确标记 Yahoo 字段为标准化字段，不等同于年报原始披露字段。
- 对年份不足、字段缺失、接口失败输出结构化状态。

Yahoo Finance 没有稳定官方公开 HTTP API；实现上可以直接使用 yfinance，也可以包装 `../yahoo-finance-mcp/` 中的确定性接口。但生产主路径不应让 LLM 自由调用 MCP。

## 8. Source Inventory

source inventory 是 raw source 到 Turtle mapping 的中间 artifact。

每条记录至少包含：

- source
- market
- ticker
- company identifier when available
- statement type
- report type
- period
- fiscal year when available
- scope when available
- account standard when available
- currency
- unit
- raw field name
- raw field code when available
- raw value
- parsed numeric value when applicable
- source evidence
- source status：present、missing、ambiguous、source_error、unsupported

inventory 不做最终 Turtle 判断。它只表达 source 中存在什么。

## 9. Turtle Mapping And Reconciliation

mapping 输出应表达：

- `field_id`
- source candidate list
- selected source candidate when unambiguous
- mapping rule id
- mapping confidence
- mapping status：present、missing、ambiguous、conflict、derived、unsupported
- period/scope/currency/unit decision
- source evidence list
- errors/warnings

规则：

- AKShare 和 Yahoo 均有候选时，必须比较 period、currency、unit 和 normalized value。
- source 值一致或差异在明确 tolerance 内，才可自动选择。
- source 语义不一致或差异无法解释时，输出 `conflict`。
- derived fields 必须保留所有输入字段 lineage。
- 低置信度、多候选、口径冲突时输出 `ambiguous`，不能硬选。

## 10. Money And Unit Normalization

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

优先级：

```text
AKShare explicit metadata
> Yahoo/yfinance explicit metadata
> source report/statement metadata
> PDF table header / PDF evidence
> market default heuristic
> unknown/ambiguous
```

规则：

- `normalized_value = value * unit_multiplier`。
- 不做 FX conversion。
- `$` 不能单独决定币种。
- market default heuristic 只能用于 review 提示，不能自动生成 present money。
- 多币种或单位不明时输出 `ambiguous` 或 `unknown_unit`。

## 11. Coverage Gate

coverage gate 必须能回答：

- AKShare 单独覆盖多少 Turtle P0/P1 fields。
- Yahoo/yfinance 单独覆盖多少 Turtle P0/P1 fields。
- AKShare + Yahoo/yfinance 组合覆盖多少 fields。
- 哪些字段 missing。
- 哪些字段 ambiguous。
- 哪些字段 conflict。
- 哪些字段需要 PDF evidence supplement。
- 哪些字段需要 LLM review。

第一阶段 gate 阻断条件：

- required source field missing。
- present money 缺 currency 或 unit。
- source conflict 未解决。
- derived field 缺输入 lineage。
- output profile 要求 PDF evidence 但没有对应 PDF evidence。

## 12. PDF/LLM Fallback Boundary

PDF/LLM fallback 只处理：

- source missing。
- source ambiguous。
- source conflict。
- source 有值但需要年报 page/block/snippet evidence。
- source 字段语义无法自动映射到 Turtle 字段。
- 需要从 notes 或管理层文字中解释的非标准字段。

PDF/LLM fallback 不应：

- 重新作为全字段主抽取路径。
- 对所有 Turtle P0/P1 字段 broad scan。
- 代替 source adapter 或 source coverage gate。
- 直接产出 normalized money。

LLM 合适角色：

- 解释 source field 与 Turtle field 的语义关系。
- 对 ambiguous mapping 给候选和理由。
- 从 selected PDF evidence 中补 page/block/snippet。
- 对 source result 和 PDF snippet 做 consistency review。

## 13. LLM Config And Transport

系统保留 provider-neutral LLM boundary：

- `LlmConfigResolver`
- `LlmClient`
- `OpenAICompatibleTransport`
- `GeminiGenerateContentTransport`
- `LlmResponseParser`
- `FakeLlmClient`

首批 provider：

- `deepseek`
- `gemini`
- `ollama`
- generic `openai-compatible`

provider fallback 默认关闭。LLM 只在 fallback/review 阶段调用；source-first adapter 和 coverage gate 不依赖 LLM。

每次 LLM run 必须记录 provider、model、base URL、prompt/schema version、latency、usage、finish reason 和 structured errors。API key 只能从环境变量读取，不得写入 artifacts。

## 14. Output Artifacts

默认使用仓库内 `tmp/`。

推荐 run layout：

```text
tmp/
  runs/
    <run_id>/
      source_artifacts/
        akshare/
        yahoo/
      source_inventory.jsonl
      turtle_mapping.json
      source_coverage_summary.json
      reconciliation_report.json
      pages.jsonl
      chunks.jsonl
      retrieval_probe.json
      pdf_evidence_supplement.json
      prompt_payloads/
      raw_llm_responses/
      parsed_llm_responses/
      extraction_result.json
      review_summary.json
      run_metadata.json
```

PDF artifacts 只在 fallback/supplement 阶段生成。source artifacts 是第一阶段默认产物。

## 15. First Slice Scope

第一可用切片：

- Turtle P0/P1 source mapping contract。
- AKShare raw adapter。
- Yahoo/yfinance raw adapter。
- source inventory artifacts。
- 最小 Turtle mapping。
- money/unit normalization。
- source coverage gate。
- conflict/reconciliation report。
- selected PDF/LLM fallback 设计和 fake path。

优先验证样本：

- `600519` / A 股 / AKShare。
- `00001` / 港股 / AKShare + Yahoo/yfinance。
- `01113` / 港股 / AKShare + Yahoo/yfinance。

## 16. Success Criteria

第一阶段成功标准：

- 能对 `600519`、`00001`、`01113` 生成 AKShare/Yahoo raw source artifacts。
- 能生成 source inventory，并可审查每个 raw field 和 raw value。
- 能将最小 Turtle P0/P1 字段映射到 source candidates。
- 能输出 AKShare、Yahoo 和组合 coverage summary。
- 能识别 missing、ambiguous、conflict、unsupported。
- 能 deterministic normalize CNY/HKD/USD 和常见单位。
- 能阻断单位/币种不明的 present money。
- 能明确列出哪些字段需要 PDF/LLM fallback。
- 不依赖 PDF broad extraction 即可判断结构化 source route 是否可行。
