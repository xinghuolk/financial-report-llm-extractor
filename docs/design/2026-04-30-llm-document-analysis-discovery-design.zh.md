# LLM 文档分析与行项目发现设计分析

> 日期：2026-04-30  
> 状态：设计分析  
> 目的：解释为什么系统不能只做固定字段检索，也不能让 LLM 一次性读取整份 PDF 输出最终字段；并给出适合不同公司年报的分阶段文档分析方案。

## 1. 问题背景

当前项目的原始架构是：

```text
PDF
-> page/block/logical chunk store
-> field-scoped retrieval
-> LLM structured extraction
-> deterministic money/unit normalization
-> validation/export
```

这个方向仍然正确，但需要补上一层更靠前的文档理解能力。

原因是不同公司、不同市场、不同语言的年报中，同一个 Turtle 字段可能有完全不同的呈现方式：

- 收入可能叫 `营业收入`、`Revenue`、`Turnover`、`Group revenue`、`Total revenue`。
- 净利润可能叫 `归属于母公司股东的净利润`、`Profit attributable to shareholders`、`Net income attributable to Yum China Holdings, Inc.`。
- 资产负债表可能叫 `合并资产负债表`、`Consolidated Statement of Financial Position`、`Consolidated Balance Sheet`。
- 单位可能是 `元`、`万元`、`亿元`、`RMB'000`、`RMB in thousands`、`HK$ million`、`US$ million`。
- 同一个关键词会出现在目录、五年摘要、管理层讨论、分部分析、正式财务报表和 notes 中。

如果系统只按字段别名做 retrieval，会遇到两个问题：

1. **召回不足**：公司使用了 catalog 没覆盖的叫法，字段直接找不到。
2. **误召回过多**：关键词命中了摘要或叙述区，而不是正式财务报表行。

因此，后续设计需要从“先找字段”调整为“先理解文档结构，再发现报表行，再映射字段”。

## 2. 本地样本验证

`downloads/` 下已有多类真实报告：

- A 股中文年报：`300750`、`600519`、`601919`、`688008`。
- 港股英文/中文年报：`00001`、`01113`、`01810`、`02498`、`06862`、`09987`。
- 同时包含 annual、quarterly、semi_annual 等报告类型。

轻量抽样验证显示：

- 港股英文报告中，`Revenue` 在正式财务报表前就会大量出现，例如目录、五年财务摘要、主席报告、MD&A 和分部分析。
- `01113_2025_en` 第 3 页五年摘要已经有 `Group revenue`，正式 income statement 在后面页面。
- `01810_2024_en` 第 8 页五年摘要和第 28 页现金流摘要都能命中核心字段，但正式审计报表在后面两百多页。
- 不同公司使用的报表标题不同，包括 `Consolidated Income Statement`、`Consolidated Statement of Comprehensive Income`、`Consolidated Statement of Financial Position`、`Consolidated Balance Sheet`、`Consolidated Statements of Operations`。
- A 股中文 PDF 对不同文本抽取 backend 的依赖更强；某些 backend 无法可靠抽出可搜索中文文本。

这些现象说明：单层 field-scoped retrieval 不足以适配真实年报。系统需要先建立 document map 和 statement map。

## 3. 关键边界：不是整篇黑盒抽取

LLM 可以参与文档分析，但不能成为不可审计的整篇抽取黑盒。

禁止的模式：

```text
whole PDF text
-> LLM
-> final P0/P1 Turtle fields
```

这个模式的问题是：

- 很难判断模型取值来自正式报表、摘要、MD&A 还是 notes。
- 很难稳定追踪到 page、chunk、block、snippet。
- 容易混淆本期/上期、合并/母公司、RMB/HKD/USD。
- 出错时无法定位是文档理解错、字段映射错、抽取错，还是金额归一化错。
- 成本高，不适合局部 rerun。

推荐的模式：

```text
PDF
-> page/block store
-> document map
-> statement map
-> LLM-assisted row discovery
-> catalog mapping
-> field-scoped extraction
-> deterministic normalization
-> validation/export
```

这里 LLM 的角色是：

- 帮助识别文档结构。
- 帮助识别正式报表区域。
- 帮助列出某个 statement chunk 中出现的 row labels 和 raw values。
- 帮助把 row label 的语义候选解释出来。

LLM 不能直接决定最终 normalized money，也不能绕过 evidence validation。

## 4. 分阶段数据流

### 4.1 Page And Block Store

输入是 PDF，输出是可追溯的 page/block artifact。

每个 block 至少包含：

- `block_id`
- `page`
- `text`
- `kind`
- optional layout/table metadata

这一层不做字段判断，只负责保留证据。

### 4.2 Document Map

目标是建立整份报告的结构索引，而不是抽取财务字段。

Document map 应识别：

- 目录页。
- 审计报告页。
- 正式财务报表页范围。
- notes 起止范围。
- MD&A / 管理层讨论范围。
- 五年摘要 / financial summary 范围。
- 报告语言、市场、报告期、公司名。

LLM 可以参与这一步，但输入应是：

- page title candidates。
- 每页前若干 block。
- 目录页文本。
- 候选标题附近窗口。

输出是结构化 map，不是最终字段：

```json
{
  "sections": [
    {
      "kind": "audited_financial_statements",
      "page_start": 132,
      "page_end": 346,
      "confidence": 0.92,
      "evidence": [{"page": 129, "block_id": "p0129_b0003", "snippet": "which are set out on pages 132 to 346"}]
    }
  ]
}
```

### 4.3 Statement Map

目标是从 document map 中进一步识别正式 statements。

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

这一步可以混合规则和 LLM：

- 规则负责标题关键词、页码连续性、审计报告引用页码。
- LLM 负责处理标题变体、目录引用、复杂页面中的语义判断。

### 4.4 Row Discovery

目标是在某个 statement chunk 中发现报表行项目。

LLM 输入不是整份 PDF，而是一个 statement chunk 或其局部窗口：

```text
Statement: CONSOLIDATED INCOME STATEMENT
Scope: consolidated
Period columns: 2025, 2024
Unit: $ Million
Blocks:
- p0070_b0001: ...
- p0070_b0002: Group revenue 57,935 45,529
- p0070_b0003: Share of revenue of joint ventures 27,913 26,056
```

LLM 输出 row inventory：

```json
{
  "rows": [
    {
      "row_label": "Group revenue",
      "candidate_meaning": "group revenue",
      "values": [{"period": "2025", "value_raw": "57,935"}],
      "unit_context": "$ Million",
      "currency_hint": "HKD",
      "evidence": [{"page": 70, "block_id": "p0070_b0002", "snippet": "Group revenue 57,935 45,529"}]
    }
  ]
}
```

注意：row inventory 不是最终 extracted item。它只是“这份年报里有哪些可映射的行”。

### 4.5 Catalog Mapping

目标是把 discovered rows 映射到 Turtle 字段。

输入：

- row label。
- statement kind。
- scope。
- period。
- unit/currency context。
- field catalog aliases。
- field catalog value type。
- derivation metadata。

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

映射可以由规则和 LLM 协作，但最终必须保留解释和置信度。低置信度、多候选或口径冲突时，应返回 `ambiguous`，不能硬选。

### 4.6 Field-Scoped Extraction

完成 row discovery 和 mapping 后，再进入字段级抽取。

此时 prompt 只包含：

- 一个字段或小字段组。
- 已映射 row。
- 对应 evidence blocks。
- 邻近 header/unit/period/scope context。

LLM 只允许返回：

- `value_raw`
- `unit_context`
- `currency_hint`
- `period`
- `scope`
- `status`
- `confidence`
- evidence refs

LLM 不允许返回最终可信的 `normalized_value`。金额归一化必须由代码完成。

### 4.7 Validation And Export

最终输出必须通过代码验证：

- `present` 必须有 page/chunk/block/snippet evidence。
- evidence 必须指向真实存在的 page/block/chunk。
- monetary item 必须有 deterministic normalized money，或者结构化 ambiguity。
- 不允许隐式 FX conversion。
- 不允许混合不同币种、期间、scope。
- derived value 必须带所有输入 evidence。

## 5. 推荐的后续五个阶段

### Phase 9: Evidence Contract 修复

先修复当前 review 中发现的 evidence/chunk 输出合同问题：

- retrieval evidence 必须指向包含 matched alias/snippet 的 block。
- `chunk --out nested/chunks.jsonl` 必须自动创建输出目录。
- fake extraction 的 evidence 必须可被后续 LLM demo 信任。

### Phase 10: Parser Capability Probe And Document Map Demo

目标是验证不同 PDF backend 对 A 股和港股样本文本抽取的可用性，并生成 document map。

重点：

- 记录每个 backend 的文本抽取质量。
- 识别目录、正式财报页、notes、MD&A、financial summary。
- 不抽取最终字段。

### Phase 11: Statement Map And LLM-Assisted Row Discovery

目标是在正式 statement 区域内发现 row labels 和 raw values。

重点：

- income statement、balance sheet、cash flow statement 的 statement map。
- LLM row inventory prompt。
- row-level evidence refs。
- 不直接输出最终 Turtle 字段。

### Phase 12: Catalog Mapping And Field-Scoped Extraction

目标是把 discovered rows 映射到 Turtle P0/P1 字段，并进行小范围字段抽取。

重点：

- structured field catalog。
- aliases + statement kind + scope + unit/period context mapping。
- ambiguous mapping 显式化。
- selected-field rerun。

### Phase 13: Money/Scope Validation And Real Evaluation Loop

目标是在真实年报上形成可复现评估闭环。

重点：

- unit/currency/period/scope validation。
- HK 多币种/多列 ambiguity。
- A 股中文单位。
- `tmp/runs/evaluation/<report_id>/` 标准 run layout。
- JSON/Markdown review summary。

## 6. 设计原则

后续实现应遵守以下原则：

- LLM 可以参与 discovery，但每一步都必须有中间 artifact。
- LLM 不做整篇 PDF 到最终 P0/P1 的黑盒抽取。
- 文档结构发现、行项目发现、字段映射、字段抽取、金额归一化、验证应分层。
- 每层都应能单独 review、单独测试、单独 rerun。
- 真实报告差异应通过 document map 和 row discovery 吸收，而不是靠不断堆字段 alias。
- 表格结构是证据增强，不是唯一入口。
- 当 parser、layout、币种、期间或 scope 不可靠时，输出 ambiguity，而不是伪造确定性。

## 7. 结论

后续方案不应回到“整份 PDF 直接给 LLM 抽字段”，也不应停留在“固定 catalog alias 检索字段”。

正确方向是：

```text
先发现这份年报的结构
再发现正式报表里的行项目
再把行项目映射到 Turtle 字段
最后做字段级抽取和代码验证
```

这条路径既允许 LLM 处理不同公司年报的表达差异，也保留了 evidence、money、period、scope 的可审计边界。
