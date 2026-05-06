# Phase M: HK Yahoo Trust Policy And PDF Spot-Check Spec

> Date: 2026-05-06
> Status: Implemented
> Roadmap phase: Phase M

## 背景

Phase K 已经证明 HK provider replay 的 `currency`、`unit`、`unit_multiplier` 和 reporting metadata 可以被审查。Phase L 已经把当前 15 字段样本中的 warning 分成三类：source policy 可解决、需要 PDF 验证、以及 source unavailable。

当前剩下的关键问题是：HK 年报披露通常用 `HK$ million`，Yahoo Finance API 返回的是完整 HKD raw amount。只要能用少量真实 PDF 样本证明“Yahoo raw amount = 年报 HK$ million 数值 * 1,000,000”，某些字段就不应该再因为 HK provider ratio mismatch 被一律挡在 PDF verification 队列里。

Phase M 的目标是沉淀这个 market/field 级 trust policy，并把它接入 source policy/replay：对于已经抽样证明的 HK Yahoo 字段，系统可以把 Yahoo HK raw value 作为可信主来源，同时保留“这是策略证明，不是该公司最终 PDF page evidence”的边界。

## 目标

1. 新增 HK Yahoo trust policy fixture，记录 00001 和 01113 年报抽样证明。
2. 用结构化合同表达每条证明的 PDF 披露值、披露单位、Yahoo raw 字段、Yahoo raw 期望值和匹配状态。
3. 在 source policy 中识别 `yahoo_pdf_verified` 字段，并允许这些 HK Yahoo primary items 成为 clean present。
4. 在 review artifacts 中解释 Yahoo HK `currency=HKD`、`unit=raw`、`unit_multiplier=1` 为什么被信任。
5. 明确区分 policy evidence 和 final export PDF evidence。

## 非目标

Phase M 不做以下事情：

1. 不要求每家公司每个字段都有最终 PDF page/block evidence。
2. 不扩展完整 P0/P1 33 字段 mapping。
3. 不把 `gross_profit` 直接提升为 clean present；它仍需要明确年报行语义证明。
4. 不把 `bond_payable`、`cip`、`invest_income` 伪造成可用字段。
5. 不把 trust policy 写入 ingestion、chunking 或 LLM transport 层。

## Trust Policy Fixture

新增 fixture 建议路径：

```text
field_catalog/hk_yahoo_trust_policy.json
```

fixture 必须是可审查的 JSON artifact，至少包含以下字段。下面是结构示例，不是可直接复制的 fixture；`pdf_page` 必须在实现时从 quick-validation artifact 或重新解析的 PDF text 中填入真实页码。

```json
{
  "version": 1,
  "market": "HK",
  "provider": "yahoo",
  "rules": [
    {
      "policy_id": "hk_yahoo_raw_hkd_pdf_verified:revenue",
      "field_id": "revenue",
      "classification": "yahoo_pdf_verified",
      "trusted_currency": "HKD",
      "trusted_unit": "raw",
      "trusted_unit_multiplier": 1,
      "samples": [
        {
          "company_id": "00001",
          "provider_ticker": "0001.HK",
          "report_ref": "downloads/hk_stocks/00001/annual/2025_annual_en.pdf",
          "pdf_page": "<real_pdf_page_from_artifact>",
          "statement_name": "Consolidated Income Statement",
          "statement_line": "Revenue",
          "reported_currency": "HKD",
          "reported_unit": "million",
          "pdf_value": "280036",
          "pdf_unit_multiplier": 1000000,
          "expected_yahoo_raw_value": "280036000000",
          "yahoo_raw_field": "Total Revenue",
          "match_basis": "pdf_value * pdf_unit_multiplier equals expected_yahoo_raw_value"
        }
      ]
    }
  ]
}
```

实现后的正式 fixture 不允许保留字符串占位。测试必须验证每条 sample 的 `pdf_page` 是正整数，并且该页的 PDF text 或 quick-validation artifact 中可以找到对应 `statement_line`。

## 初始字段分类

Phase M 的初始分类基于路线图中已经记录的抽样事实：

`yahoo_pdf_verified`：

1. `revenue`
2. `total_cur_assets`
3. `total_cur_liab`
4. `total_assets`，当样本可用直接披露行或可审查 subtotal 证明时
5. `total_liabilities`，当样本可用直接披露行或可审查 subtotal 证明时

`yahoo_definition_unverified`：

1. `net_profit`，直到 fixture 中记录明确 PDF 行语义和值匹配证明
2. `gross_profit`

`pdf_required`：

1. provider 有数值但 policy fixture 没有证明，且无法由 deterministic source policy 解释的字段

`source_unavailable` 或 mapping expansion：

1. `bond_payable`
2. `cip`
3. `invest_income`
4. `defer_tax_liab`，先作为 mapping expansion，再通过 PDF spot-check 验证

## Source Policy 行为

当一个 selected primary candidate 满足以下条件时，source policy 可以应用 HK Yahoo trust policy：

1. market 是 `HK`。
2. provider/source 是 Yahoo。
3. field_id 在 trust policy 中是 `yahoo_pdf_verified`。
4. candidate 的 raw provider field 与 policy rule 允许的 Yahoo raw field 匹配。
5. candidate 的 currency/unit metadata 是 `HKD/raw/unit_multiplier=1`。
6. policy 至少有两个不同公司的 PDF samples，或者该字段在 spec 中被明确列为可由 subtotal 证明。

应用后：

1. selected item 的 `verification_required` 可以变为 `false`。
2. 与 HK Yahoo raw-vs-million 单位差异相关的 warning 可以移除。
3. item 必须保留 `trust_policy_evidence`，说明 policy id、sample companies、sample PDF refs 和匹配基准。
4. final export 不得把 `trust_policy_evidence` 伪装成该公司当前值的 `Evidence(page/chunk/block/snippet)`。

## Replay/Review Artifact

Provider baseline replay 必须输出可审查信息：

1. `source_policy_report.json` 中每个应用 trust policy 的 item 带 `trust_policy_evidence`。
2. warning classification 中把相关字段从 `pdf_verification_required` 移到 `yahoo_pdf_verified`。
3. review summary 中能区分：
   - clean present because source policy trust applies
   - still requires company-specific PDF verification
   - source unavailable

## 验收标准

1. HK trust policy fixture 可以被 loader 校验，所有 sample 的 `pdf_value * pdf_unit_multiplier == expected_yahoo_raw_value`。
2. `00001` 和 `01113` 的 replay artifacts 显示已证明字段进入 `yahoo_pdf_verified`。
3. `gross_profit` 不会因为同属 Yahoo HK 而被误提升为 clean present。
4. `bond_payable`、`cip`、`invest_income` 仍保持 source unavailable 或 missing，不伪造值。
5. source policy report 明确解释 HK Yahoo `currency=HKD`、`unit=raw`、`unit_multiplier=1` 的信任来源。
6. 测试覆盖 trust policy loader、source policy 应用、warning classification 和 provider replay summary。

## 实现结果

Phase M 已实现并接入 provider baseline replay。

当前 HK combined replay 结果：

| 公司 | selected/covered | clean present |
|---|---:|---:|
| `00001` | `10/15` | `9/15` |
| `01113` | `10/15` | `9/15` |

`yahoo_pdf_verified` 字段：

1. `revenue`
2. `total_assets`
3. `total_cur_assets`
4. `total_cur_liab`
5. `total_liabilities`

仍未补足的 HK 15-field 缺口：

1. `net_profit`：有 Yahoo 值，但仍是 `yahoo_definition_unverified`，需要 PDF row semantics proof。
2. `gross_profit`：仍需 PDF verification。
3. `defer_tax_liab`：仍是 mapping expansion path。
4. `bond_payable`、`cip`、`invest_income`：当前 AKShare/Yahoo captured data 中仍是 source unavailable。

验证记录：

1. Phase M 相关测试 `116 passed`。
2. `uv run ruff check .` 通过。
3. `uv run mypy src tests` 通过。
4. 完整 `uv run pytest -v` 当前为 `411 passed, 1 skipped, 1 failed`，唯一失败是既有 `akshare_cn_600519_balance_sheet` fixture hash mismatch，与 Phase M 变更无关。
