# Turtle Field Taxonomy Design

> Date: 2026-05-02
> Status: design spec
> Scope: classify Turtle v0.15 fields by financial statement domain before expanding source mappings.

## 1. Purpose

The Turtle field catalog currently uses priority layers (`P0` to `P4`) as the main organizing view. That is useful for implementation order, but it is not enough for source-first mapping. A field mapping catalog needs a semantic taxonomy first, because AKShare, Yahoo/yfinance, PDF evidence, and LLM review each align with different parts of the annual report.

The field catalog should therefore be modeled with two independent axes:

- `priority`: extraction importance and implementation order.
- `domain`: where the field belongs in financial reporting semantics.

Priority answers "when should we build it?" Domain answers "where should the system look, how should it validate the value, and what kind of fallback is allowed?"

## 2. Required Field Metadata

Every Turtle field should eventually carry these metadata fields:

- `field_id`
- `priority`: `P0`, `P1`, `P2`, `P3`, or `P4`
- `domain`: one of the taxonomy domains below
- `statement_type`: `income_statement`, `balance_sheet`, `cash_flow`, `notes`, `mda`, `announcement`, or `mixed`
- `value_type`: `money`, `number`, `percent`, `text`, or `derived`
- `source_mode`: `direct`, `derived`, `source_optional`, `pdf_only`, or `llm_review`
- `period_type`: `duration`, `point_in_time`, `annual_text`, or `event`
- `scope_expectation`: `consolidated`, `parent`, `attributable_to_owners`, `unknown`, or `not_applicable`
- `currency_requirement`: `required`, `optional`, or `not_applicable`
- `unit_requirement`: `required`, `optional`, or `not_applicable`
- `evidence_requirement`: `source_only_allowed`, `pdf_required`, or `llm_review_required`
- `fallback_policy`: `source_required`, `pdf_allowed`, `llm_review_required`, or `manual_review_required`

## 3. Taxonomy Domains

### 3.1 Income Statement

Fields primarily sourced from the statement of profit or loss / income statement.

Initial fields:

- `revenue`
- `operating_cost`
- `gross_profit`
- `selling_general_administrative`
- `rd_exp`
- `operating_profit`
- `invest_income`
- `fv_value_chg_gain`
- `non_oper_income`
- `non_oper_exp`
- `net_profit`

Default metadata:

- `statement_type`: `income_statement`
- `period_type`: `duration`
- `currency_requirement`: `required` for money fields
- `unit_requirement`: `required` for money fields
- `evidence_requirement`: `source_only_allowed` unless a downstream export profile requires PDF page evidence

Mapping notes:

- AKShare A-share wide tables often expose stable raw field codes such as `OPERATE_INCOME`, `TOTAL_OPERATE_INCOME`, `NETPROFIT`, and `PARENT_NETPROFIT`.
- Yahoo/yfinance often exposes standardized English field names such as `Total Revenue`, `Operating Revenue`, `Cost Of Revenue`, `Gross Profit`, `Operating Income`, and `Net Income`.
- Same-source duplicate candidates may use catalog alias order as deterministic precedence.
- Cross-source disagreements must go through reconciliation.

### 3.2 Balance Sheet

Fields primarily sourced from the statement of financial position / balance sheet.

Initial fields:

- `total_assets`
- `total_liabilities`
- `equity_attributable_to_owners`
- `cash`
- `money_cap`
- `st_borr`
- `lt_borr`
- `bond_payable`
- `accounts_receiv`
- `acct_payable`
- `inventories`
- `fix_assets`
- `cip`
- `total_cur_assets`
- `other_cur_assets`
- `total_cur_liab`
- `defer_tax_assets`
- `defer_tax_liab`
- `minority_int`

Default metadata:

- `statement_type`: `balance_sheet`
- `period_type`: `point_in_time`
- `currency_requirement`: `required` for money fields
- `unit_requirement`: `required` for money fields
- `evidence_requirement`: `source_only_allowed` unless a downstream export profile requires PDF page evidence

Mapping notes:

- Current AKShare validation already proves `TOTAL_ASSETS`, `TOTAL_LIABILITIES`, `MONETARYFUNDS`, `TOTAL_CURRENT_ASSETS`, and `TOTAL_CURRENT_LIAB` can map through the source-first pipeline for `600519`.
- Debt fields should be treated carefully. `st_borr`, `lt_borr`, and `bond_payable` are direct balance sheet fields when raw source rows exist, but broader "debt" values should be derived explicitly from component fields.
- Cash-like fields must distinguish cash and cash equivalents, restricted cash, deposits, and wealth products. Do not silently merge them.

### 3.3 Cash Flow Statement

Fields primarily sourced from the statement of cash flows.

Initial fields:

- `operating_cash_flow`
- `investing_cash_flow`
- `financing_cash_flow`
- `stock_based_compensation`
- `change_in_receivables`
- `change_in_payables`
- `change_in_inventory`
- `receiv_tax_refund`
- `repurchase_of_stock`
- `dividends_paid`
- `capital_expenditures`
- `depreciation_amortization`
- `interest_paid_cash`

Default metadata:

- `statement_type`: `cash_flow`
- `period_type`: `duration`
- `currency_requirement`: `required` for money fields
- `unit_requirement`: `required` for money fields
- `evidence_requirement`: `source_only_allowed` for direct source rows, `pdf_required` for fields whose source semantics are weak

Mapping notes:

- Current AKShare validation proves `NETCASH_OPERATE` can map to `operating_cash_flow` for `600519`.
- Investing and financing cash flow should be mapped from cash-flow statement subtotals, not inferred from balance sheet deltas.
- Working-capital change fields are high risk because source providers may present them with opposite signs or normalized labels. These should start as `source_optional` or `llm_review` until verified.

### 3.4 Shareholder Return And Capital Actions

Fields about dividends, buybacks, and shareholder distributions. Some values may appear in cash flow statements, while policy and plan fields usually appear in announcements, notes, or board report text.

Initial fields:

- `dps`
- `dividend_plan`
- `buyback_cancellation_progress`
- `repurchase_of_stock`
- `dividends_paid`

Default metadata:

- `statement_type`: `mixed`
- `period_type`: `duration` for cash amounts, `event` or `annual_text` for plans and policy text
- `source_mode`: `direct` for cash-flow amounts when source rows exist, `pdf_only` or `llm_review` for plan/progress text
- `evidence_requirement`: `pdf_required` or `llm_review_required` for narrative fields

Mapping notes:

- `repurchase_of_stock` and `dividends_paid` may be direct cash-flow rows.
- `dps`, `dividend_plan`, and buyback progress often require announcement or annual-report text evidence and should not be forced into structured source mapping.

### 3.5 R&D, Capitalization, And Accounting Adjustments

Fields that may be split between income statement, cash flow, notes, and accounting policy disclosures.

Initial fields:

- `rd_exp`
- `capitalized_rd`
- `capitalized_interest`
- `depreciation_amortization`
- `defer_tax_assets`
- `defer_tax_liab`

Default metadata:

- `statement_type`: `mixed`
- `source_mode`: `direct` only when a trusted structured row exists; otherwise `source_optional` or `pdf_only`
- `evidence_requirement`: `pdf_required` for capitalization details and accounting-policy-sensitive values

Mapping notes:

- `rd_exp` may be direct from the income statement for many A-share reports.
- `capitalized_rd` and `capitalized_interest` are usually notes fields and should start as `pdf_only` or `llm_review`.
- Deferred tax assets/liabilities are balance sheet fields but are grouped here too because they are accounting-adjustment-sensitive. The primary domain remains balance sheet.

### 3.6 Notes, Risk, And Operating Text

Fields that usually require notes, management discussion, audit report, or other narrative evidence.

Initial fields:

- `receivables_aging`
- `bad_debt_provision`
- `related_party_receivables_payables`
- `contingent_liabilities_commitments`
- `lease_liability_maturity`
- `segment_revenue_profit`
- `restricted_cash`
- `time_deposits_or_wealth_products`
- `mda_business_review`
- `mda_forward_guidance`
- `mda_risk_factors`
- `dividend_policy_text`
- `audit_opinion`
- `auditor_change_history`

Default metadata:

- `statement_type`: `notes` or `mda`
- `source_mode`: `pdf_only` or `llm_review`
- `period_type`: `annual_text`, `event`, or `point_in_time`
- `currency_requirement`: depends on field
- `unit_requirement`: depends on field
- `evidence_requirement`: `pdf_required` or `llm_review_required`

Mapping notes:

- These fields should not block source-first three-statement coverage.
- They should enter selected PDF retrieval only after the source coverage gate identifies them as needed.
- LLM may assist with extraction and review, but output must still cite PDF page/block/snippet evidence.

## 4. Priority Overlay

Priority remains useful, but it should be applied after domain classification.

- `P0`: core three-statement fields needed for first source-first viability.
- `P1`: high-value statement enhancements.
- `P2`: cash-flow and reconciliation enhancements.
- `P3`: notes and announcement bridge signals.
- `P4`: long-form text review artifacts.

The catalog should support queries such as:

- all `P0` balance sheet fields
- all income statement fields with `source_mode=direct`
- all fields requiring PDF evidence
- all `P2` cash-flow fields that are still unverified

## 5. Implementation Implications

The next source mapping catalog should not be a flat alias list. It should be generated or maintained as a field metadata catalog with domain and source-mode first.

Recommended staged rollout:

1. Add taxonomy metadata for all existing Turtle v0.15 fields without changing mapper behavior.
2. Expand source aliases for P0 income statement, balance sheet, and cash-flow fields.
3. Add derived-field metadata only for formulas with clear lineage.
4. Mark notes and narrative fields as `pdf_only` or `llm_review` instead of forcing source aliases.
5. Use captured AKShare/Yahoo inventories to update verification status per field.

## 6. Validation Expectations

Taxonomy validation should assert:

- Every field in `field_catalog/turtle_v015_priority_fields.json` appears in exactly one primary domain.
- Fields may have secondary domains, but primary domain is required.
- Every field has `source_mode`.
- Every money field has currency/unit requirements.
- `pdf_only` and `llm_review` fields are not counted as missing structured-source failures in the first source-first coverage gate.
- Source-first coverage can be reported by both priority and domain.

## 7. Current Evidence

Current captured validation supports this taxonomy direction:

- AKShare `600519` combined three-statement replay covers 8 of 9 minimal source-mapping fields.
- Yahoo/yfinance `0001.HK` income statement replay covers `revenue`, `net_profit`, and `gross_profit`.
- The remaining work is not to broaden PDF retrieval. It is to expand the source mapping catalog by domain, then prove each field family with captured source artifacts.
