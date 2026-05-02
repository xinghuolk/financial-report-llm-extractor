# Structured Data Source First 财报抽取设计补充

> 日期：2026-05-01
> 状态：设计补充
> 关联设计：`docs/design/2026-04-30-llm-first-turtle-financial-extraction-design.md`

## 1. 背景

当前项目最初采用 PDF/LLM-first 路线：从年报 PDF 构建 page、block、chunk、retrieval probe，再由 LLM 对 Turtle v0.15 P0/P1 字段做 evidence-grounded extraction。

真实 PDF 验证暴露出关键问题：字段覆盖率和 prompt budget 不足以支撑 broad extraction。当前 Turtle 覆盖预算验证中，港股英文报告 `00001_2025_en` 和 `01113_2025_en` 对 33 个 P0/P1 required fields 的覆盖率约为 27.3% 和 24.2%。这说明 PDF field-first retrieval 可以用于诊断和补证据，但不适合作为第一步的大规模结构化财务数据主路径。

核心原因不是单个 alias 不够，而是 PDF 通用定位层本身难以稳定泛化：

- 定位过宽会把 MD&A、notes、financial summary、outlook 等大量无关内容送入 LLM。
- 定位过窄会漏掉不同公司、不同语言、跨页表格、跨页文字中的关键字段。
- 表格结构、报表标题、字段措辞、单位表达在不同公司之间差异很大，逐家公司调规则不可扩展。
- LLM 能处理跨页上下文，但前提是系统已经把相关上下文送进去；如果 retrieval 没召回，LLM 无法补救。

因此，当前路线应从 PDF-first 调整为 source-first：优先通过 AKShare 和 Yahoo/yfinance 获取三大报表和主要指标，完成 Turtle 字段映射、派生、货币单位归一化和 coverage gate。只有当结构化来源缺失、冲突、歧义，或需要年报页码证据时，才进入 PDF 财报分析和 LLM evidence fallback。

## 2. 设计目标修正

新的第一阶段目标不是“从任意 PDF 中直接抽全量 Turtle 字段”，而是建立 AKShare + Yahoo/yfinance 优先的数据获取和字段覆盖机制：

1. 优先从 AKShare 获取 A 股、港股和可用美股结构化财报数据。
2. 使用 Yahoo/yfinance 作为港股、美股和标准化字段补充来源。
3. 将原始 source fields 映射到 Turtle v0.15 P0/P1 catalog。
4. 对每个字段保留 source、period、currency、unit、raw field、raw value。
5. 用 coverage gate 判断 AKShare/Yahoo 组合是否足够覆盖目标字段。
6. 只对缺失、冲突、歧义、需要 PDF 证据的字段进入 PDF/LLM fallback。

非目标：

- 不让 LLM 作为生产主路径直接调用 MCP 后自由取数。
- 不把 AKShare、Yahoo 或 Tushare 的返回值直接提升为 canonical fact。
- 不复制大型外部项目的 service、worker、database 架构。
- 不取消 PDF evidence；PDF 角色从主抽取源调整为最后阶段的 evidence、fallback 和 review。

## 3. 推荐架构

主路径：

```text
AKShare adapter
-> Yahoo/yfinance adapter
-> raw source artifact store
-> source field inventory
-> Turtle field mapping / derivation
-> currency/unit normalization
-> coverage and conflict gate
-> selected PDF financial report analysis for missing/conflict/evidence fields
-> LLM only for ambiguous mapping/evidence review
-> review/export JSON
```

与旧路线的关系：

```text
Old:
PDF -> retrieval -> LLM extraction -> normalized Turtle JSON

New:
AKShare + Yahoo/yfinance -> deterministic Turtle mapping -> coverage gate
                                                        \-> selected PDF/LLM fallback
```

结构化数据源层必须是 deterministic adapter，而不是 LLM tool call。LLM 可以用于探索、字段解释、歧义判断和 evidence review，但生产数据获取必须可测试、可缓存、可重放。

推荐 source priority：

```text
AKShare
-> Yahoo/yfinance
-> cross-source reconciliation
-> PDF financial report analysis
-> LLM-assisted evidence / ambiguity review
```

PDF 财报分析是最后阶段，不参与第一轮 broad field coverage。它只处理结构化数据源无法稳定解决的问题。

### 3.1 Turtle 字段分类

Source-first 映射不应继续把 Turtle 字段只按 `P0`、`P1`、`P2` 平铺。优先级是实现顺序，不是字段语义边界。字段目录必须先按财报语义域分类，再为每个字段叠加 priority、source mode 和 evidence requirement。

推荐主分类：

- 利润表：收入、成本、毛利、费用、经营利润、投资收益、公允价值变动、营业外收支、净利润。
- 资产负债表：资产、负债、权益、现金、借款、应收应付、存货、固定资产、在建工程、流动资产和流动负债。
- 现金流量表：经营、投资、筹资现金流，以及回购、分红、资本开支、折旧摊销和营运资本变化。
- 股东回报和资本动作：每股分红、分红计划、回购注销进度。
- 研发、资本化和会计调整：研发费用、资本化研发、资本化利息、递延税、折旧摊销。
- 附注、风险和经营文字：账龄、坏账、关联方、或有事项、租赁到期、分部、受限资金、理财、MD&A、审计意见。

每个字段至少需要：

- `domain`
- `statement_type`
- `source_mode`: direct、derived、source_optional、pdf_only、llm_review
- `period_type`: duration、point_in_time、annual_text、event
- `evidence_requirement`: source_only_allowed、pdf_required、llm_review_required

详细 taxonomy 见：

- `docs/superpowers/specs/2026-05-02-turtle-field-taxonomy-design.md`

## 4. 数据源对比

### 4.1 Yahoo / yfinance / yahoo-finance-mcp

`../yahoo-finance-mcp/` 已经有 MCP 包装，底层使用 yfinance。它可以获取 income statement、balance sheet、cash flow、stock info 等结构化数据，对港股如 `0001.HK` 有一定覆盖。

适合：

- 港股和美股的标准化财务字段补充。
- 与 AKShare 做 cross-source reconciliation。
- 在 AKShare 字段缺失或接口失败时提供备选结构化来源。

限制：

- Yahoo Finance 没有稳定官方公开 HTTP API；yfinance 使用的是非官方接口。
- 年份可能不足，例如常见只返回约 4 年。
- 字段是 Yahoo 标准化后的字段，不等于年报披露字段。
- 没有 PDF page/block/snippet evidence。

建议：

- 当前项目不要让 LLM 直接调用 yahoo MCP 作为主路径。
- 短期可以用 yfinance adapter 或包装 yahoo-finance-mcp 的 deterministic API。
- Yahoo/yfinance 不作为唯一主数据源；它排在 AKShare 之后，用于补充和交叉验证。
- 输出必须保存 raw JSON 和字段覆盖报告。

### 4.2 AKShare

AKShare 源码在本机 venv 中可见，例如：

- `akshare/stock_feature/stock_three_report_em.py`
- `akshare/stock_fundamental/stock_finance_hk_em.py`
- `akshare/stock_fundamental/stock_finance_sina.py`
- `akshare/stock_fundamental/stock_finance_us_em.py`

这些接口对当前项目有实际参考价值：

- A 股三大表：`stock_balance_sheet_by_report_em()`、`stock_profit_sheet_by_report_em()`、`stock_cash_flow_sheet_by_report_em()`。
- A 股新浪三大表和摘要：`stock_financial_report_sina()`、`stock_financial_abstract()`。
- 港股三大表：`stock_financial_hk_report_em()`。
- 港股主要指标：`stock_financial_hk_analysis_indicator_em()`。
- 美股三大表和指标：`stock_financial_us_report_em()`、`stock_financial_us_analysis_indicator_em()`。

适合：

- A 股、港股、美股结构化财务数据源。
- 直接获得报表项目长表：`REPORT_DATE`、`FISCAL_YEAR`、`STD_ITEM_CODE`、`STD_ITEM_NAME`、`AMOUNT`。
- 作为第一优先级 source inventory。
- 作为 Turtle 字段映射和 coverage gate 的主输入。

限制：

- AKShare 返回结构不是稳定业务合同，需要当前项目自己封装。
- 港股函数先查询了 `CURRENCY`、`ACCOUNT_STANDARD`、`REPORT_TYPE`，但三大表明细返回时没有自动 join 这些元数据。
- 不同接口来源混合 Eastmoney/Sina，字段、单位、币种和审计口径可能不一致。
- 当前本机 `report-collector` venv 中是 `akshare==1.17.26`，`TradingAgents-CN` 锁的是 `akshare==1.17.54`，版本差异可能影响接口。

建议：

- 当前项目显式声明并固定 AKShare 版本。
- 只调用 AKShare 公共函数，不复制 site-packages 源码。
- 保存每次调用的 raw response artifact。
- 对港股实现 metadata join，补回 currency、account standard、report type。
- 对所有 source rows 统一输出 `source_ref`，用于后续 review。
- 第一轮 source-first spike 先以 AKShare 为主，Yahoo/yfinance 为补充。

### 4.3 TradingAgents-CN

`/home/like/mycode/finanice/TradingAgents-CN/` 有真实 AKShare provider。它的价值是证明 AKShare 在业务项目中如何接入，包括：

- 初始化 AKShare。
- 处理 headers、curl_cffi、请求延迟和部分反爬问题。
- 调用三大表、主要指标、行情、新闻等接口。
- 将数据保存到应用自己的 MongoDB 服务。

适合参考：

- AKShare provider 的接口调用清单。
- 请求稳定性处理。
- A 股财务数据获取方式。

不建议复制：

- MongoDB service。
- worker/scheduler。
- 行情、新闻、Web API、业务 UI。
- 该项目自己的字段标准化结果。

原因：

当前项目需要的是独立、轻量、可测试的 extraction adapter。`TradingAgents-CN` 的架构太重，直接迁入会把当前项目带向数据平台，而不是 Turtle extractor。

### 4.4 report-collector

`/home/like/mycode/finanice/report-collector/` 主项目没有正式 AKShare 接入。项目代码只在 formatter 中预留了 `source == "akshare"` 分支，依赖文件没有声明 `akshare`。

它的主要价值在 PDF 侧，因此应放在 AKShare/Yahoo 之后：

- CNInfo PDF 搜索和下载。
- HKEX PDF 下载。
- PDF 文件组织和 SQLite 元数据。
- 已收集的真实财报样本。

适合参考：

- PDF source acquisition。
- report metadata。
- 真实 PDF 样本库。
- 结构化 source coverage gate 之后的 PDF evidence supplement。

不适合作为：

- AKShare 数据源实现参考。
- 结构化财务数据主路径参考。

## 5. 当前项目新增边界

建议新增 `structured_sources` 边界，避免把外部数据源逻辑塞进 PDF ingestion 或 LLM extraction。

建议模块：

```text
src/financial_report_llm_extractor/
  structured_sources/
    __init__.py
    models.py
    akshare_adapter.py
    yahoo_adapter.py
    reconciliation.py
    source_artifacts.py
    turtle_mapping.py
```

核心合同示例：

```json
{
  "source": "akshare",
  "market": "HK",
  "ticker": "00001",
  "statement_type": "balance_sheet",
  "period": "2024-12-31",
  "report_type": "annual",
  "account_standard": "HKFRS",
  "currency": "HKD",
  "unit": "raw",
  "raw_field_code": "STD_ITEM_CODE",
  "raw_field_name": "STD_ITEM_NAME",
  "raw_value": "123456000",
  "normalized_value": 123456000,
  "source_ref": {
    "adapter": "akshare",
    "function": "stock_financial_hk_report_em",
    "artifact_id": "..."
  }
}
```

该合同和现有 PDF evidence contract 不冲突。结构化 source evidence 表达“数据来源和原始字段”，PDF evidence 表达“年报页码和片段”。两者都可以进入最终 review JSON，但含义必须区分。

source evidence 和 PDF evidence 的职责分工：

- `source_evidence`：证明值来自哪个结构化数据源、哪个函数、哪个 raw artifact、哪个原始字段。
- `pdf_evidence`：证明年报原文中哪些 page/block/snippet 支持或反驳该值。
- `present` 的结构化字段可以先由 source evidence 支撑；如果下游要求年报证据，再按字段进入 PDF supplement。
- PDF evidence 不应反向驱动第一轮全字段覆盖，避免回到 PDF-first 的通用定位问题。

## 6. 货币和单位机制

结构化 source-first 后，货币和单位仍然是高风险点，必须统一处理：

- `currency` 必须显式：CNY、HKD、USD 或 unknown。
- `unit_multiplier` 必须显式：1、1_000、10_000、1_000_000、100_000_000 等。
- `normalized_value = raw_numeric_value * unit_multiplier`。
- source adapter 只能声明它能证明的 currency/unit，不能猜。
- 如果 source 没有带 currency/unit，状态必须是 ambiguous 或 unknown_unit，不能静默归一化。
- PDF fallback 发现的 `HK$ million`、`RMB thousand`、`人民币百万元` 等可以作为 unit evidence，但不得覆盖结构化来源，除非经过 conflict policy。

优先级建议：

```text
AKShare explicit metadata
> Yahoo/yfinance explicit metadata
> source report/statement metadata
> PDF table header / PDF evidence
> market default heuristic
> unknown/ambiguous
```

市场默认 heuristic 只能用于 review 提示，不能用于自动 present value。

## 7. LLM 和 MCP 的角色

生产主路径不建议让 LLM 调 MCP 获取财务数据。

原因：

- LLM tool call 不稳定，难以保证同一输入得到同一组数据源调用。
- 难以做 raw artifact、cache、coverage gate 和 regression test。
- 出错时很难区分是数据源失败、tool call 失败、字段映射失败还是 LLM 判断失败。

LLM 合适的角色：

- 解释 source field 与 Turtle field 的语义关系。
- 对 ambiguous mapping 给出候选和理由。
- 在 source coverage gate 之后，从 PDF 中补充字段 evidence。
- 对结构化结果和 PDF snippet 做 consistency review。

MCP 合适的角色：

- 交互式探索。
- 人工诊断。
- 临时查询。

生产实现应使用 deterministic adapter/API。

## 8. 风险和规避

### 当前验证基线

已经完成的真实/捕获验证提供了一个更稳的开发基线：

- AKShare `600519` 三张表真实请求已保存为 captured inventory，回放覆盖 8/9 个 minimal source-mapping 字段。
- Yahoo/yfinance `0001.HK` income statement 真实请求已保存为 captured inventory，回放覆盖 `revenue`、`net_profit`、`gross_profit`。
- 真实 provider 调用只用于创建或刷新 captured artifacts；日常 mapping、coverage、reconciliation 迭代应使用 captured replay，避免重复请求和接口波动。

这说明 source-first 路线对核心三大表字段是可行的，但还不能替代完整评估：`00001`、`01113`、Yahoo balance sheet/cash flow 和 cross-source reconciliation 仍需补齐。

### 风险：结构化来源覆盖不足

规避：

- 对每个 source 跑 Turtle coverage gate。
- 输出 missing fields 和 source coverage matrix。
- 不通过 coverage gate 时不进入 broad LLM extraction。

### 风险：不同 source 字段语义不一致

规避：

- Turtle mapping 需要显式 `mapping_confidence` 和 `mapping_rule_id`。
- 高风险字段需要人工 review 或 PDF evidence support。
- derived fields 必须保留输入 lineage。

### 风险：货币和单位丢失

规避：

- adapter 输出 currency/unit confidence。
- 港股 AKShare 要补 metadata join。
- 无法证明单位时阻断 present money item。

### 风险：AKShare 接口变化

规避：

- 固定版本。
- 保存 raw artifact。
- 用 fixture 做 adapter contract tests。
- integration smoke test 显式 opt-in，不作为默认单元测试。

### 风险：没有 PDF page evidence

规避：

- 结构化 source result 和 PDF evidence 分层表达。
- 对需要年报证据的字段再跑 selected PDF retrieval。
- 最终 export 可区分 `source_evidence` 和 `pdf_evidence`。
- 不因为缺少 PDF evidence 阻塞 source-first coverage spike；只阻塞需要年报证据的最终 export/profile。

## 9. 推荐下一步

第一步不应继续扩大 PDF alias/statement 规则，而应先做 AKShare + Yahoo/yfinance source-first spike：

1. 定义 `StructuredFinancialRecord` 和 `StructuredSourceRun` 合同。
2. 实现 AKShare adapter 的 fixture-backed tests，并将 AKShare 设为第一优先级 source。
3. 实现 Yahoo/yfinance adapter 或 deterministic wrapper，并将其设为第二优先级 source。
4. 对 `00001`、`01113`、`600519` 生成 raw source inventory。
5. 实现最小 Turtle mapping：revenue、net income、total assets、total liabilities、cash flow from operations。
6. 实现 cross-source reconciliation：period、currency、unit、raw value、normalized value。
7. 跑 source-first coverage gate，比较 AKShare、Yahoo 和组合覆盖率。
8. 只对 missing、ambiguous、conflict、需要年报证据的字段进入 PDF fallback。

如果第一轮 AKShare/Yahoo 组合 coverage 明显高于当前 PDF retrieval，后续路线图应正式调整为 source-first；PDF/LLM 保留为最后阶段的 evidence supplement、consistency review 和 hard-case fallback。
