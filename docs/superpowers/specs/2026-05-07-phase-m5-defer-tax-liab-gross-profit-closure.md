# Phase M5: defer_tax_liab Yahoo 语义证明 + gross_profit HK 终态降级

> Date: 2026-05-07
> Status: Draft
> Roadmap phase: Phase M5
> Predecessor: Phase M4 (provider semantics correction)

## Goal

在 Phase N 33-field 扩展之前，解决 HK 15-field denominator 中剩余两个可推进字段的终态：

1. `defer_tax_liab`: 补全 Yahoo provider raw semantics proof，推到 clean present。
2. `gross_profit`: 基于 PDF 实际调查结果，给出明确不可验证原因，锁定终态。

预期结果：HK clean present 从 10/15 → 11/15。

## Background

### defer_tax_liab

当前状态：`mapping_expansion_required`。

- Source mapping catalog 只有 AKShare alias `DEFER_TAX_LIAB`，没有 Yahoo alias。
- Yahoo provider baseline 中 HK 有 `Non Current Deferred Taxes Liabilities`（HKD raw, unit_multiplier=1）。
- PDF 验证结果：
  - 00001 page 136: `Deferred tax liabilities = 17,275 HK$ million` → Yahoo raw `17,275,000,000` ✅
  - 01113 page 71: `Deferred tax liabilities = 14,889 $ Million` → Yahoo raw `14,889,000,000` ✅
- Yahoo 还返回 `Current Deferred Taxes Liabilities`（01113: 1,189M），这是 Provision for taxation，不是递延税项负债，必须作为 negative context 排除。

### gross_profit

当前状态：`yahoo_definition_unverified`。

- Yahoo provider baseline 有 `Gross Profit`（HKD raw）。
- AKShare HK 有 `毛利`（GROSS_PROFIT）。
- PDF 实际调查结果（2026-05-07）：
  - 00001 page 134: 利润表结构为 Revenue → 6 项成本明细（Cost of inventories sold, Staff costs, Expensed customer acquisition, Depreciation, Other expenses, Other income） → EBIT-like subtotal (38,934)。**没有 Gross profit 行。**
  - 01113 page 70: 利润表结构为 Group revenue → 合并 Operating costs (包含 Property costs, Pub operation costs, Salaries, Interest, Depreciation, Other expenses) → Profit before taxation。**没有 Gross profit 行。**
- Derivation 不可靠：00001 的成本拆分包含非 COGS 项（staff costs, depreciation 等），01113 的 operating costs 是合并金额无法拆分 COGS。
- 结论：HK 年报利润表格式不支持 gross profit 的直接行匹配或确定性 derivation 验证。

## Design

### 1. defer_tax_liab: Provider Raw Semantics

在 `field_catalog/provider_raw_semantics_hk.json` 新增一条 rule：

- `rule_id`: `hk_yahoo_defer_tax_liab`
- `turtle_field`: `defer_tax_liab`
- `provider`: `yahoo`
- `market`: `HK`
- `raw_field`: `Non Current Deferred Taxes Liabilities`
- `classification`: `provider_semantics_verified`
- `allowed_as_primary`: true
- `semantic_claim`: non-current deferred tax liabilities as reported on balance sheet
- `trusted_metadata`: currency=HKD, unit=raw, unit_multiplier=1
- `proof_origin`: `sampled_pdf_policy_proof`
- `samples`:
  - 0001.HK: page 136, "Deferred tax liabilities", HK$ million, pdf_value=17275, yahoo_raw=17275000000
  - 1113.HK: page 71, "Deferred tax liabilities", $ Million, pdf_value=14889, yahoo_raw=14889000000
- `negative_context`: `["Current Deferred Taxes Liabilities"]`

### 2. defer_tax_liab: HK Yahoo Trust Policy

在 `field_catalog/hk_yahoo_trust_policy.json` 新增 trust policy rule：

- `policy_id`: `hk_yahoo_raw_hkd_verified:defer_tax_liab`
- `turtle_field`: `defer_tax_liab`
- `classification`: `yahoo_pdf_verified`
- `yahoo_raw_fields`: `["Non Current Deferred Taxes Liabilities"]`
- `trusted_currency`: HKD
- `trusted_unit`: raw
- `trusted_unit_multiplier`: 1
- `samples`: 同上两条 PDF sample proof

### 3. defer_tax_liab: Source Mapping Catalog

更新 `field_catalog/turtle_v015_source_mapping_minimal.json` 的 `defer_tax_liab` 条目：

- 新增 yahoo aliases: `["Non Current Deferred Taxes Liabilities"]`
- 新增 HK market policy:
  - `primary_route`: `yahoo_direct`
  - `cross_check`: akshare
  - `conflict_resolution`: `select_primary_require_pdf`
- `verification_status`: `expected` → `verified`

### 4. gross_profit: Provider Raw Semantics 更新

更新 `field_catalog/provider_raw_semantics_hk.json` 中已有的两条 gross_profit rule：

**Yahoo `Gross Profit` rule:**

- `classification`: 保持 `provider_semantics_unverified`
- `allowed_as_primary`: 保持 false
- `proof_origin`: 从 `provider_semantics_missing` 改为 `hk_statement_format_incompatible`
- `required_proof`: 更新为 "HK formal income statements examined (00001 page 134, 01113 page 70) do not contain a gross profit row. Revenue-minus-COGS derivation is unreliable due to multi-line cost breakdown (00001) or bundled operating costs (01113). Proof requires either a different HK issuer with standard gross profit row, or a verified derivation formula."

**AKShare `毛利` rule:**

- 同样更新 `proof_origin` 为 `hk_statement_format_incompatible`
- 同样更新 `required_proof`，说明 HK 年报格式限制

### 5. gross_profit: HK Yahoo Trust Policy 更新

更新 `field_catalog/hk_yahoo_trust_policy.json` 中已有的 `hk_yahoo_raw_hkd_definition_unverified:gross_profit` rule：

- `classification`: 保持 `yahoo_definition_unverified`（不新增 bucket 类型）
- `definition_status_reason`: 更新为 "HK formal income statements do not contain a gross profit row; sampled 00001 (page 134) and 01113 (page 70) both use non-standard cost structures that prevent direct or derivation-based verification of Yahoo Gross Profit"
- `required_proof`: 更新为 "HK issuer with standard gross profit row, or verified revenue-minus-COGS derivation formula"

### 6. 不新增 terminal bucket 类型

gross_profit 保持 `yahoo_definition_unverified` bucket，不新增 `hk_format_incompatible` 等新类型。现有 vocabulary 足够，reason 文字已说明具体原因。

## Expected Replay Result

| 字段 | Before | After |
|------|--------|-------|
| defer_tax_liab | mapping_expansion_required | clean_present |
| gross_profit | yahoo_definition_unverified (reason: "not yet proven") | yahoo_definition_unverified (reason: "HK statement format incompatible, two samples examined") |

HK 15-field clean present: 10/15 → 11/15。

## Test Requirements

### defer_tax_liab

1. Provider semantics catalog test: verify new rule is `provider_semantics_verified` with `allowed_as_primary=true`.
2. Trust policy test: verify `yahoo_pdf_verified` classification with correct samples.
3. Source mapping catalog test: verify Yahoo alias is present and HK market policy is defined.
4. Replay integration: verify `defer_tax_liab` appears as clean present in 00001 and 01113 combined replay.
5. HK 15-field closure: verify `defer_tax_liab` moves out of `mapping_expansion_required`.

### gross_profit

1. Provider semantics catalog test: verify both rules remain `provider_semantics_unverified` with updated `proof_origin`.
2. Trust policy test: verify `yahoo_definition_unverified` classification with updated reason.
3. Replay integration: verify `gross_profit` remains non-clean with updated reason in closure report.

### Full validation

- `uv run pytest -v`: all pass.
- `uv run ruff check .`: pass.
- `uv run mypy src tests`: pass.

## Scope Boundaries

- Do not expand the 15-field denominator.
- Do not modify closure logic or add new terminal bucket types.
- Do not attempt gross_profit derivation.
- Do not touch `bond_payable`, `cip`, `invest_income` (remain source_unavailable).
- Do not start Phase N.
