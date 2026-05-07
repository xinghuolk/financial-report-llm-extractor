# Source-First 架构偏离审查分析

日期：2026-05-07

## 结论摘要

当前项目没有完全偏离 source-first 方向。主体代码仍然以 AKShare/Yahoo 结构化来源为第一层输入，通过 mapping、reconciliation、source policy、warning classification 和 export 产出可复核结果；PDF/LLM 仍应是 bounded supplement，而不是重新回到“整份 PDF 直接抽全部字段”的主流程。

但最近 HK 15-field closure、HK Yahoo trust policy、`net_profit` PDF proof 相关修改已经出现明显术语漂移：文档和测试容易把“用 PDF 样本证明 provider raw field 语义可信”误读成“每家公司、每个字段都需要在 PDF 里找对应值”。这个方向如果继续扩展到 `gross_profit` 或 Phase N 33 字段，会把系统带回 PDF-first/逐公司对账，偏离当前需求。

最重要的修正不是回滚全部代码，而是重新划清三种证据：

- provider raw field semantics proof：证明某个 provider raw field 在某市场可映射到某个 Turtle 字段。
- sampled PDF policy proof：用少量年报样本辅助证明 provider raw field 的语义、币种、单位、倍率。
- final per-export PDF evidence：最终导出项若要求 PDF 证据，才需要 page/block/snippet。

目前代码层面已经分开了 `source_evidence`、`pdf_evidence`、`trust_policy_evidence`，这是正确基础；风险主要来自命名、测试断言和 catalog 合同表达不够清晰。

## 当前状态更新

Phase M4 已按本分析完成纠偏实现。当前离线 provider baseline replay 状态如下：

- `600519` combined selected：`14/15`，clean present：`13/15`。
- `00001` combined selected：`11/15`，clean present：`10/15`。
- `01113` combined selected：`11/15`，clean present：`10/15`。

HK clean 字段来自 source evidence + provider raw semantics policy proof，不是最终逐公司 PDF evidence。当前 HK `final_pdf_evidence_fields` 为空；`sampled_pdf_policy_proof_fields` 为：

- `net_profit`
- `revenue`
- `total_assets`
- `total_cur_assets`
- `total_cur_liab`
- `total_liabilities`

HK 仍未 clean 的 5 个字段已经稳定分桶：

- `gross_profit`：`yahoo_definition_unverified` / provider semantics unverified。
- `defer_tax_liab`：`mapping_expansion_required`。
- `bond_payable`、`cip`、`invest_income`：`source_unavailable`。

因此路线已纠回 source-first/provider-semantics-first。后续可以进入 Phase N 的准备工作，但必须沿用 provider raw semantics gate，不能把 33-field expansion 变成 broad PDF retrieval 或逐公司 PDF 值匹配。

## 审查范围

本次用三个 subagent 并行审查：

- 整体架构边界：source-first/provider-semantics-first 是否仍成立。
- 最近 M2/M3 修改：HK 15-field closure 与 `net_profit` proof 是否过度外推。
- Provider 语义证据策略：`net_profit`、`gross_profit`、Yahoo/AKShare raw field 应如何建模。

审查对象包括：

- `docs/design/2026-05-01-structured-data-source-first-financial-extraction-design.md`
- `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
- `field_catalog/turtle_v015_source_mapping_minimal.json`
- `field_catalog/hk_yahoo_trust_policy.json`
- `src/financial_report_llm_extractor/structured_sources/`
- 近期 Phase M2/M3 specs、plans 和 replay tests

## 当前仍然正确的部分

结构化来源主路径仍然成立：

- `provider_baseline_replay` 从 captured provider inventory 重放 AKShare/Yahoo 数据，而不是运行时先解析 PDF。
- mapping 层把 Turtle 字段映射到 provider candidates。
- reconciliation/source policy 层处理 provider 冲突、单位、币种、metadata、trust policy。
- warning classification 把不能 clean 的字段归入 `pdf_required`、`yahoo_definition_unverified`、`mapping_expansion_required`、`source_unavailable` 等终态原因。
- export 层区分 `source_evidence`、`pdf_evidence`、`trust_policy_evidence`。

这说明当前代码没有把生产路径改成 per-company PDF extraction。最近的 `net_profit` 逻辑也不是运行时逐公司 PDF 对账；它更像是“用两个 HK 年报样本证明 Yahoo raw field `Net Income Common Stockholders` 的语义，然后允许该 raw field 作为 HK `net_profit` 的可信来源”。

## 已经出现的偏离风险

### 1. `yahoo_pdf_verified` 命名过强

`yahoo_pdf_verified` 容易被理解为“该字段最终 PDF evidence 已齐”。但当前实际含义更接近：

> Yahoo 某 raw field 的 HK 市场语义经过 PDF 样本 proof，可作为 source policy trust rule 使用。

这不是 final per-export PDF evidence。它不等于每个公司导出结果都有 page/block/snippet，也不等于之后所有公司都经过 PDF 值匹配。

建议改名或新增更准确状态：

- `provider_semantics_sample_verified`
- `sampled_pdf_policy_verified`
- `provider_raw_field_semantics_verified`

如果短期不改枚举，也必须在总设计、路线图、policy report 中明确 `yahoo_pdf_verified` 只是 trust-policy 级别，不是最终 PDF 证据级别。

### 2. M3 `net_profit` proof 的核心判断可保留，但测试基线过度外推

应保留的部分：

- HK Yahoo `net_profit` 只信 `Net Income Common Stockholders`。
- `Net Income`、`Net Income From Continuing Operation Net Minority Interest` 只能作为 related context 或反例线索。
- 两个样本说明 broader `Net Income` 语义过宽，不能直接映射 Turtle `net_profit`。

需要修正的部分：

- 不应把 “sampled policy proof” 直接表述成 “10/15 clean present” 的核心成功目标。
- replay tests 不应只断言 `net_profit` 从 unverified bucket 消失并进入 clean baseline；更应断言 raw field selection、trust policy evidence、related fields 不被提升。
- 当前 policy sample 默认只校验数值换算，没有强制校验 PDF page text 中确实存在 statement line、单位和值。

因此 M3 不需要整体回滚，但需要降噪和重命名：它应该叫 “HK Yahoo `net_profit` raw field semantics sampled proof”，不是“逐公司 PDF proof”。

### 3. `gross_profit` 暴露了架构混淆

`gross_profit` 当前不应该 clean，也不应该直接转 AKShare primary 或 Yahoo primary。

原因：

- Yahoo `Gross Profit` 在 HK 年报语境下还没有 provider raw semantics proof。
- AKShare 的 `毛利/gross_profit` 虽然能抓到值，但也没有 HK provider raw semantics proof。
- 某些公司 PDF 可以推导出类似 Yahoo Gross Profit 的值，但这只能作为 provider semantics sample，不应变成“每家公司都去 PDF 找/算 gross profit”。
- minimal catalog 中 `gross_profit` 顶层 `primary_route`、`verification_status` 与 HK market policy / trust policy 存在表达张力，容易让后续代理误以为它已经 verified direct。

正确终态应是：

- `gross_profit = yahoo_definition_unverified` 或 `pdf_required`
- AKShare/Yahoo 都可保留为 candidate source
- 不能进入 clean present
- 不能因为某个 PDF 样本值相等就全局 promote

### 4. Trust policy proof 缺少真实 PDF 文本校验

`HkYahooTrustSample.validate()` 支持 page text resolver，但默认 loader 没有绑定真实 page text。也就是说，目前样本 proof 至少能验证：

- PDF value 到 expected provider raw value 的乘法关系。
- currency/unit/multiplier 等结构字段。

但还不能强制验证：

- 页码是否正确。
- statement line 是否真的出现在该页。
- PDF 页面是否包含相关单位和数值。
- sample 是否来自实际 artifact 而不是手写复制。

这使得当前 proof 更像人工 curated sample，而不是可复放的 PDF evidence proof。作为 provider policy sample 可以接受；作为 `pdf_verified` 字面含义则证据不足。

### 5. `source_aliases` 同时承担 direct mapping 和 related context

目前为了保留 broader Yahoo rows，`source_aliases.yahoo` 会包含 direct raw field 和 related rows。mapping precedence 可以避免 related rows 被选为 primary，但 `source_aliases` 这个字段名本身容易误导下游：看起来所有 alias 都是可直接映射字段。

建议拆分合同：

- `trusted_source_fields`：可以作为 primary candidate 的 raw fields。
- `related_source_fields`：只进入 policy evidence / review context，不能 promote。
- `negative_source_fields`：名字相近但语义错误的 raw fields。

`net_profit` 中 `Net Income` 就应该是 related 或 negative context，不应该和 `Net Income Common Stockholders` 在同一 direct alias 语义层。

## 是否需要回滚

不建议大范围回滚。

建议保留：

- source-first structured source replay 架构。
- HK 15-field terminal bucket closure 思路。
- `net_profit` 选择 `Net Income Common Stockholders` 的判断。
- related Yahoo rows 留作 policy evidence candidates。
- source/export 中区分 source evidence、PDF evidence、trust policy evidence 的边界。

建议修正：

- 文档和路线图中 `PDF proof`、`yahoo_pdf_verified`、`clean present` 的表述。
- `gross_profit` catalog/policy 状态不一致。
- replay tests 对 `net_profit` clean baseline 的过强断言。
- trust policy sample 缺少 PDF page text resolver 的测试。
- alias 合同中 direct alias 与 related context 混用。

建议暂停：

- 暂停把 `gross_profit` promote 为 clean。
- 暂停直接进入 Phase N 33-field broad expansion。
- 暂停继续用“15/15 clean”作为阶段目标；应改为“字段都有 clean 或稳定 terminal bucket，且 proof class 可 review”。

## 正确的证据模型

后续应显式建立 provider raw semantics artifact。它应按 provider/market/raw field 建模，而不是只按 Turtle field 混在 source mapping 中。

建议最小字段：

```json
{
  "provider": "yahoo",
  "market": "HK",
  "raw_field_name": "Net Income Common Stockholders",
  "raw_field_code": null,
  "turtle_field_id": "net_profit",
  "semantic_claim": "profit attributable to ordinary/common shareholders",
  "classification": "provider_semantics_sample_verified",
  "trusted_currency": "HKD",
  "trusted_unit": "raw",
  "trusted_unit_multiplier": 1,
  "allowed_as_primary": true,
  "related_only_fields": [
    "Net Income",
    "Net Income From Continuing Operation Net Minority Interest"
  ],
  "negative_examples": [],
  "proof_origin": "sampled_pdf_policy_proof",
  "samples": [],
  "required_proof": []
}
```

这样可以清楚表达：

- provider raw field 是否可 direct trust。
- PDF sample 是 policy proof，不是 final export evidence。
- related fields 为什么不能提升。
- 未证明字段为什么必须保持 `pdf_required` 或 `definition_unverified`。

## 下一步建议

以下 1-7 项已经由 Phase M4 落地，后续文档保留为设计背景：

1. 先更新总 design/roadmap 的术语表，明确三类 evidence/proof 的边界：
   `source_evidence`、`trust_policy_evidence`、`pdf_evidence`。

2. 新增或重构 provider raw semantics artifact：
   先覆盖 HK Yahoo `net_profit` 和 `gross_profit`，不要急着扩 33 字段。

3. 把 `yahoo_pdf_verified` 降级或重命名：
   若为了兼容暂时保留枚举，应在 report 中显示为 sampled policy proof，而不是 final PDF evidence。

4. 修正 `gross_profit`：
   保持 unresolved / `yahoo_definition_unverified` / `pdf_required`，同时保留 Yahoo/AKShare candidates；不要 promote。

5. 增加 catalog consistency tests：
   顶层 `primary_route`、`verification_status`、market policy、trust policy classification 不得互相矛盾。

6. 增加 trust policy PDF sample resolver tests：
   至少验证 sample page text 中存在 statement line、reported unit、reported value，避免只有 arithmetic proof。

7. 重写 M3 replay expectations：
   重点断言 raw field selection 和 related field 不提升；不要把 `10/15 clean` 当成唯一成功标准。

## 对后续 Phase 的判断

Phase M4 provider semantics contract cleanup 已完成。下一阶段可以准备 full P0/P1 33-field expansion，但应把 Phase M4 的边界作为硬前置：

- 先扩 source mapping denominator，不直接提升 clean。
- 对每个新增 provider raw field 标注 trusted、related-only、negative 或 unverified。
- `gross_profit` 继续保持 non-clean，直到 Yahoo/AKShare raw semantics proof 成立。
- PDF/LLM fallback 只能消费 bounded queue，不能恢复 broad P0/P1 PDF retrieval。

这样再扩展完整 P0/P1 33 字段会更安全。否则每增加一个字段，都会重复遇到“Yahoo/AKShare 有字段名，但语义是否等价、单位是否可信、是否需要 PDF”的混乱。
