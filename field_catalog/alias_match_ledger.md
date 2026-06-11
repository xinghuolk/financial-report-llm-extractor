# Alias Match Ledger — governance view

- note: derived view; regenerable from run artifacts + audits; rm + re-index is safe

## Promotion candidates (normalized phrase, >= 2 companies per market)

| Field | Market | Suggested alias | Companies |
|---|---|---|---|
| `amounts_due_from_subsidiaries` | HK | amounts due from subsidiaries | 02498, 06862 |
| `amounts_due_from_subsidiaries` | HK | due from subsidiaries | 02498, 06862, 09987 |
| `audit_opinion` | HK | independent auditor’s report | 00001, 01113, 01810, 02498, 03320, 06862, 09987 |
| `capital_expenditures` | HK | capital expenditure | 00001, 01810, 02498, 06862, 09987 |
| `capital_expenditures` | HK | purchase of property, plant and equipment | 01810, 02498, 06862 |
| `cash` | HK | cash and cash equivalent | 02498, 09987 |
| `change_in_inventory` | HK | changes in inventories | 02498, 09987 |
| `contingent_liabilities_commitments` | HK | commitment | 00001, 01113, 01810, 02498, 03320, 06862, 09987 |
| `contingent_liabilities_commitments` | HK | guarantee | 00001, 01113, 01810, 02498, 03320, 06862, 09987 |
| `contract_liabilities_current` | HK | contract liabilities | 00001, 01810, 02498, 03320, 06862, 09987 |
| `contract_liabilities_current` | HK | contract liability | 02498, 03320, 06862 |
| `defer_tax_assets` | HK | deferred tax asset | 00001, 01113, 02498, 06862, 09987 |
| `defer_tax_liab` | HK | deferred tax liabilities | 00001, 01113, 01810, 02498, 03320, 06862, 09987 |
| `defer_tax_liab` | HK | deferred tax liability | 01810, 06862 |
| `dividends_paid` | HK | dividend paid | 00001, 01113, 01810, 03320 |
| `dividends_paid` | HK | dividends paid | 00001, 01113, 01810, 02498, 03320, 06862, 09987 |
| `dps` | HK | dividends per share | 00001, 01113 |
| `equity_investment_in_subsidiaries` | HK | interests in subsidiaries | 01810, 03320, 06862 |
| `equity_investment_in_subsidiaries` | HK | investment in subsidiaries | 01810, 02498, 03320, 09987 |
| `equity_investment_in_subsidiaries` | HK | investments in subsidiaries | 00001, 01810, 02498, 03320, 06862 |
| `fix_assets` | HK | fixed asset | 00001, 06862 |
| `fix_assets` | HK | property, plant and equipment | 01810, 02498, 03320, 06862, 09987 |
| `inventories` | HK | inventory | 00001, 01113, 01810, 02498, 06862, 09987 |
| `invest_income` | HK | investments and other | 01810, 03320 |
| `lt_eqt_invest` | HK | investment in an associate | 01113, 02498, 03320 |
| `lt_eqt_invest` | HK | investments in associates | 00001, 01113, 01810, 02498, 03320, 06862 |
| `minority_int` | HK | non-controlling interest | 00001, 01810, 03320, 09987 |
| `money_cap` | HK | cash and cash equivalent | 02498, 09987 |
| `segment_revenue_profit` | HK | operating segment | 00001, 01810, 02498, 06862, 09987 |

## Dead aliases (zero hits in an audited market)

| Field | Market | Alias |
|---|---|---|
| `accounts_receiv` | CN | accounts receivable |
| `accounts_receiv` | CN | trade receivables |
| `accounts_receiv` | CN | debtors |
| `accounts_receiv` | HK | 应收账款 |
| `acct_payable` | CN | accounts payable |
| `acct_payable` | CN | trade payables |
| `acct_payable` | CN | creditors |
| `acct_payable` | HK | 应付账款 |
| `amounts_due_from_subsidiaries` | CN | 应收子公司款 |
| `amounts_due_from_subsidiaries` | CN | 应收子公司款项 |
| `amounts_due_from_subsidiaries` | CN | 其他应收款 子公司 |
| `amounts_due_from_subsidiaries` | CN | 母公司其他应收款 |
| `amounts_due_from_subsidiaries` | CN | amount due from subsidiaries |
| `amounts_due_from_subsidiaries` | CN | amount due from a subsidiary |
| `amounts_due_from_subsidiaries` | CN | amounts due from subsidiaries |
| `amounts_due_from_subsidiaries` | CN | amounts due from a subsidiary |
| `amounts_due_from_subsidiaries` | CN | loans to subsidiaries |
| `amounts_due_from_subsidiaries` | CN | loans to a subsidiary |
| `amounts_due_from_subsidiaries` | CN | receivables from subsidiaries |
| `amounts_due_from_subsidiaries` | CN | due from subsidiaries |
| `amounts_due_from_subsidiaries` | CN | due from a subsidiary |
| `amounts_due_from_subsidiaries` | CN | financial position of the company |
| `amounts_due_from_subsidiaries` | CN | balance sheet of the company |
| `amounts_due_from_subsidiaries` | HK | 应收子公司款 |
| `amounts_due_from_subsidiaries` | HK | 应收子公司款项 |
| `amounts_due_from_subsidiaries` | HK | 其他应收款 子公司 |
| `amounts_due_from_subsidiaries` | HK | 母公司其他应收款 |
| `amounts_due_from_subsidiaries` | HK | 母公司资产负债表 |
| `amounts_due_from_subsidiaries` | HK | loans to subsidiaries |
| `amounts_due_from_subsidiaries` | HK | loans to a subsidiary |
| `amounts_due_from_subsidiaries` | HK | receivables from subsidiaries |
| `audit_opinion` | CN | 独立审计师的报告 |
| `audit_opinion` | CN | 独立审计师报告 |
| `audit_opinion` | CN | 否定意见 |
| `audit_opinion` | CN | 无法表示意见 |
| `audit_opinion` | CN | 强调事项 |
| `audit_opinion` | CN | independent auditor's report |
| `audit_opinion` | CN | auditor's opinion |
| `audit_opinion` | CN | audit opinion |
| `audit_opinion` | CN | our opinion |
| `audit_opinion` | CN | in our opinion |
| `audit_opinion` | CN | in our opinion, the consolidated |
| `audit_opinion` | CN | what we have audited |
| `audit_opinion` | CN | opinion of the auditors |
| `audit_opinion` | CN | report of the auditors |
| `audit_opinion` | CN | report of the independent auditor |
| `audit_opinion` | CN | unqualified opinion |
| `audit_opinion` | CN | qualified opinion |
| `audit_opinion` | CN | adverse opinion |
| `audit_opinion` | CN | disclaimer of opinion |
| `audit_opinion` | CN | emphasis of matter |
| `audit_opinion` | CN | give a true and fair view |
| `audit_opinion` | CN | present fairly |
| `audit_opinion` | CN | independent auditor’s report |
| `audit_opinion` | HK | 审计意见 |
| `audit_opinion` | HK | 审计报告 |
| `audit_opinion` | HK | 审计意见类型 |
| `audit_opinion` | HK | 标准无保留意见 |
| `audit_opinion` | HK | 标准的无保留意见 |
| `audit_opinion` | HK | 独立审计师的报告 |
| `audit_opinion` | HK | 独立审计师报告 |
| `audit_opinion` | HK | 无保留意见 |
| `audit_opinion` | HK | 保留意见 |
| `audit_opinion` | HK | 否定意见 |
| `audit_opinion` | HK | 无法表示意见 |
| `audit_opinion` | HK | 强调事项 |
| `audit_opinion` | HK | auditor's opinion |
| `audit_opinion` | HK | opinion of the auditors |
| `audit_opinion` | HK | report of the auditors |
| `audit_opinion` | HK | report of the independent auditor |
| `audit_opinion` | HK | unqualified opinion |
| `audit_opinion` | HK | qualified opinion |
| `audit_opinion` | HK | adverse opinion |
| `audit_opinion` | HK | disclaimer of opinion |
| `audit_opinion` | HK | emphasis of matter |
| `audit_opinion` | HK | present fairly |
| `bad_debt_provision` | CN | allowance for doubtful accounts |
| `bad_debt_provision` | CN | loss allowance |
| `bad_debt_provision` | CN | expected credit loss |
| `bad_debt_provision` | CN | bad debt provision |
| `bad_debt_provision` | HK | 坏账准备 |
| `bond_payable` | CN | bonds payable |
| `buyback_cancellation_progress` | CN | share buyback |
| `buyback_cancellation_progress` | CN | share repurchase progress |
| `buyback_cancellation_progress` | CN | cancellation of shares |
| `buyback_cancellation_progress` | CN | 回购进展 |
| `buyback_cancellation_progress` | HK | share buyback |
| `buyback_cancellation_progress` | HK | share repurchase progress |
| `buyback_cancellation_progress` | HK | 回购进展 |
| `buyback_cancellation_progress` | HK | 注销 |
| `c_paid_for_taxes` | CN | income tax paid |
| `c_paid_for_taxes` | CN | cash paid for taxes |
| `c_paid_for_taxes` | CN | taxes paid |
| `c_paid_for_taxes` | HK | 支付的各项税费 |
| `c_paid_for_taxes` | HK | cash paid for taxes |
| `c_pay_to_staff` | CN | cash paid to employees |
| `c_pay_to_staff` | CN | cash paid to and on behalf of employees |
| `c_pay_to_staff` | HK | 支付给职工以及为职工支付的现金 |
| `c_pay_to_staff` | HK | cash paid to employees |
| `c_pay_to_staff` | HK | cash paid to and on behalf of employees |
| `capital_expenditures` | CN | capital expenditures |
| `capital_expenditures` | CN | purchase of property plant and equipment |
| `capital_expenditures` | CN | capital expenditure |
| `capital_expenditures` | CN | purchase of property, plant and equipment |
| `capital_expenditures` | HK | 购建固定资产 |
| `capitalized_interest` | CN | capitalized borrowing costs |
| `capitalized_interest` | CN | capitalized interest |
| `capitalized_interest` | CN | interest capitalised |
| `capitalized_interest` | CN | 资本化利息 |
| `capitalized_interest` | HK | capitalized borrowing costs |
| `capitalized_interest` | HK | capitalized interest |
| `capitalized_interest` | HK | 资本化利息 |
| `capitalized_rd` | CN | capitalized research and development |
| `capitalized_rd` | CN | development costs capitalized |
| `capitalized_rd` | CN | research costs capitalized |
| `capitalized_rd` | HK | capitalized research and development |
| `capitalized_rd` | HK | development costs capitalized |
| `capitalized_rd` | HK | research costs capitalized |
| `capitalized_rd` | HK | 资本化研发 |
| `cash` | CN | cash and cash equivalents |
| `cash` | CN | cash and cash equivalent |
| `cash` | HK | 货币资金 |
| `cash_parent_company` | CN | 母公司现金及现金等价物 |
| `cash_parent_company` | CN | 母公司货币资金 |
| `cash_parent_company` | CN | 母公司 货币资金 |
| `cash_parent_company` | CN | parent company balance sheet |
| `cash_parent_company` | CN | company balance sheet |
| `cash_parent_company` | CN | balance sheet of the company |
| `cash_parent_company` | CN | financial position of the company |
| `cash_parent_company` | CN | financial position and reserve movement of the company |
| `cash_parent_company` | CN | company cash and cash equivalents |
| `cash_parent_company` | CN | holding company cash |
| `cash_parent_company` | HK | 母公司资产负债表 |
| `cash_parent_company` | HK | 母公司现金及现金等价物 |
| `cash_parent_company` | HK | 母公司货币资金 |
| `cash_parent_company` | HK | 母公司 货币资金 |
| `cash_parent_company` | HK | 公司资产负债表 |
| `cash_parent_company` | HK | parent company balance sheet |
| `cash_parent_company` | HK | company balance sheet |
| `cash_parent_company` | HK | company cash and cash equivalents |
| `cash_parent_company` | HK | holding company cash |
| `change_in_inventory` | CN | change in inventory |
| `change_in_inventory` | CN | decrease in inventory |
| `change_in_inventory` | CN | 存货减少 |
| `change_in_inventory` | CN | changes in inventories |
| `change_in_inventory` | HK | 存货减少 |
| `change_in_payables` | CN | change in payables |
| `change_in_payables` | CN | increase in payables |
| `change_in_payables` | CN | 应付账款增加 |
| `change_in_payables` | HK | change in payables |
| `change_in_payables` | HK | increase in payables |
| `change_in_payables` | HK | 应付账款增加 |
| `change_in_receivables` | CN | change in receivables |
| `change_in_receivables` | CN | decrease in receivables |
| `change_in_receivables` | CN | 应收账款减少 |
| `change_in_receivables` | HK | change in receivables |
| `change_in_receivables` | HK | decrease in receivables |
| `change_in_receivables` | HK | 应收账款减少 |
| `cip` | CN | construction in progress |
| `contingent_liabilities_commitments` | CN | contingent liabilities |
| `contingent_liabilities_commitments` | CN | commitments |
| `contingent_liabilities_commitments` | CN | guarantees |
| `contingent_liabilities_commitments` | HK | 或有负债 |
| `contingent_liabilities_commitments` | HK | 承诺 |
| `contract_liabilities_current` | CN | contract liabilities |
| `contract_liabilities_current` | CN | deferred revenue |
| `contract_liabilities_current` | CN | advance from customers |
| `contract_liabilities_current` | CN | contract liability |
| `contract_liabilities_current` | HK | 合同负债 |
| `contract_liabilities_non_current` | CN | non current deferred revenue |
| `contract_liabilities_non_current` | CN | long-term deferred revenue |
| `contract_liabilities_non_current` | CN | non-current contract liabilities |
| `contract_liabilities_non_current` | HK | 递延收益 |
| `contract_liabilities_non_current` | HK | non current deferred revenue |
| `contract_liabilities_non_current` | HK | long-term deferred revenue |
| `contract_liabilities_non_current` | HK | non-current contract liabilities |
| `defer_tax_assets` | CN | deferred tax assets |
| `defer_tax_assets` | CN | deferred tax asset |
| `defer_tax_liab` | CN | deferred tax liabilities |
| `defer_tax_liab` | CN | deferred tax liability |
| `depreciation_amortization` | CN | depreciation and amortization |
| `depreciation_amortization` | CN | depreciation |
| `depreciation_amortization` | CN | amortization |
| `depreciation_amortization` | HK | 折旧及摊销 |
| `dividend_plan` | CN | dividend plan |
| `dividend_plan` | CN | dividend policy |
| `dividend_plan` | CN | proposed dividend |
| `dividend_plan` | CN | final dividend |
| `dividend_plan` | CN | 股息政策 |
| `dividend_plan` | HK | dividend plan |
| `dividend_plan` | HK | proposed dividend |
| `dividend_plan` | HK | 派息 |
| `dividend_policy_text` | CN | 股利分配政策 |
| `dividend_policy_text` | CN | 派息政策 |
| `dividend_policy_text` | CN | 股利政策 |
| `dividend_policy_text` | CN | 未来三年股东回报规划 |
| `dividend_policy_text` | CN | 股东回报规划 |
| `dividend_policy_text` | CN | dividend policy |
| `dividend_policy_text` | CN | dividend distribution policy |
| `dividend_policy_text` | CN | shareholder returns policy |
| `dividend_policy_text` | CN | policy on dividend |
| `dividend_policy_text` | HK | 股利分配政策 |
| `dividend_policy_text` | HK | 现金分红政策 |
| `dividend_policy_text` | HK | 利润分配政策 |
| `dividend_policy_text` | HK | 派息政策 |
| `dividend_policy_text` | HK | 股利政策 |
| `dividend_policy_text` | HK | 分红政策 |
| `dividend_policy_text` | HK | 未来三年股东回报规划 |
| `dividend_policy_text` | HK | 股东回报规划 |
| `dividend_policy_text` | HK | dividend distribution policy |
| `dividend_policy_text` | HK | shareholder returns policy |
| `dividend_policy_text` | HK | policy on dividend |
| `dividends_paid` | CN | dividends paid |
| `dividends_paid` | CN | cash dividends paid |
| `dividends_paid` | CN | dividend paid |
| `dividends_paid` | HK | 分配股利 |
| `dps` | CN | dividends per share |
| `dps` | CN | dividend per share |
| `dps` | CN | 每股股息 |
| `dps` | HK | 每股股息 |
| `equity_attributable_to_owners` | CN | total ordinary shareholders' funds |
| `equity_attributable_to_owners` | CN | stockholders equity |
| `equity_attributable_to_owners` | CN | 归属于母公司股东权益 |
| `equity_attributable_to_owners` | HK | 归属于母公司股东权益 |
| `equity_investment_in_subsidiaries` | CN | 长期股权投资 子公司 |
| `equity_investment_in_subsidiaries` | CN | 投资性主体对子公司投资 |
| `equity_investment_in_subsidiaries` | CN | 母公司长期股权投资 |
| `equity_investment_in_subsidiaries` | CN | investment in subsidiaries |
| `equity_investment_in_subsidiaries` | CN | investments in subsidiaries |
| `equity_investment_in_subsidiaries` | CN | interests in subsidiaries |
| `equity_investment_in_subsidiaries` | CN | interest in subsidiaries |
| `equity_investment_in_subsidiaries` | CN | investment in subsidiaries at cost |
| `equity_investment_in_subsidiaries` | CN | financial position of the company |
| `equity_investment_in_subsidiaries` | CN | balance sheet of the company |
| `equity_investment_in_subsidiaries` | HK | 对子公司投资 |
| `equity_investment_in_subsidiaries` | HK | 对子公司的投资 |
| `equity_investment_in_subsidiaries` | HK | 长期股权投资 子公司 |
| `equity_investment_in_subsidiaries` | HK | 投资性主体对子公司投资 |
| `equity_investment_in_subsidiaries` | HK | 母公司长期股权投资 |
| `equity_investment_in_subsidiaries` | HK | 母公司资产负债表 |
| `financing_cash_flow` | CN | financing cash flow |
| `fix_assets` | CN | fixed assets |
| `fix_assets` | CN | property plant and equipment |
| `fix_assets` | CN | fixed asset |
| `fix_assets` | CN | property, plant and equipment |
| `fix_assets` | HK | 固定资产 |
| `fv_value_chg_gain` | CN | fair value change |
| `fv_value_chg_gain` | HK | 公允价值变动收益 |
| `gross_profit` | CN | gross profit |
| `interest_bearing_debt_parent_company` | CN | 母公司短期借款 |
| `interest_bearing_debt_parent_company` | CN | 母公司长期借款 |
| `interest_bearing_debt_parent_company` | CN | 母公司应付债券 |
| `interest_bearing_debt_parent_company` | CN | 母公司有息负债 |
| `interest_bearing_debt_parent_company` | CN | financial position of the company |
| `interest_bearing_debt_parent_company` | CN | balance sheet of the company |
| `interest_bearing_debt_parent_company` | CN | company borrowings |
| `interest_bearing_debt_parent_company` | CN | company short-term borrowings |
| `interest_bearing_debt_parent_company` | CN | company long-term borrowings |
| `interest_bearing_debt_parent_company` | CN | company bonds payable |
| `interest_bearing_debt_parent_company` | CN | parent company borrowings |
| `interest_bearing_debt_parent_company` | CN | borrowings of the company |
| `interest_bearing_debt_parent_company` | HK | 母公司短期借款 |
| `interest_bearing_debt_parent_company` | HK | 母公司长期借款 |
| `interest_bearing_debt_parent_company` | HK | 母公司应付债券 |
| `interest_bearing_debt_parent_company` | HK | 母公司有息负债 |
| `interest_bearing_debt_parent_company` | HK | 母公司资产负债表 |
| `interest_bearing_debt_parent_company` | HK | company borrowings |
| `interest_bearing_debt_parent_company` | HK | company short-term borrowings |
| `interest_bearing_debt_parent_company` | HK | company long-term borrowings |
| `interest_bearing_debt_parent_company` | HK | company bonds payable |
| `interest_bearing_debt_parent_company` | HK | parent company borrowings |
| `interest_bearing_debt_parent_company` | HK | borrowings of the company |
| `interest_paid_cash` | CN | interest paid |
| `interest_paid_cash` | HK | 支付的利息 |
| `inventories` | CN | inventories |
| `inventories` | CN | properties for sale |
| `inventories` | HK | 存货 |
| `invest_income` | CN | share of profits of joint ventures |
| `invest_income` | CN | share of profits less losses |
| `invest_income` | CN | share of profits of associated companies |
| `invest_income` | CN | share of net profits of investments |
| `invest_income` | CN | share of net profit |
| `invest_income` | CN | equity in net earnings |
| `invest_income` | CN | investment and others |
| `invest_income` | HK | share of profits of associated companies |
| `investing_cash_flow` | CN | investing cash flow |
| `lease_liability_maturity` | CN | lease liabilities maturity |
| `lease_liability_maturity` | CN | lease liability analysis |
| `lease_liability_maturity` | CN | minimum lease payments |
| `lease_liability_maturity` | CN | 租赁负债到期 |
| `lease_liability_maturity` | HK | lease liabilities maturity |
| `lease_liability_maturity` | HK | lease liability analysis |
| `lease_liability_maturity` | HK | 租赁负债到期 |
| `lt_borr` | CN | long-term borrowings |
| `lt_borr` | CN | bank and other debts non-current |
| `lt_borr` | HK | long-term borrowings |
| `lt_borr` | HK | bank and other debts non-current |
| `lt_borr` | HK | 长期借款 |
| `lt_eqt_invest` | CN | long-term equity investment |
| `lt_eqt_invest` | CN | investments in associates |
| `lt_eqt_invest` | CN | investments in joint ventures |
| `lt_eqt_invest` | CN | investment in an associate |
| `lt_eqt_invest` | HK | 长期股权投资 |
| `minority_int` | CN | non-controlling interests |
| `minority_int` | CN | minority interest |
| `minority_int` | CN | non-controlling interest |
| `minority_int` | HK | 少数股东权益 |
| `money_cap` | CN | cash and cash equivalents |
| `money_cap` | CN | bank balances and deposits |
| `money_cap` | CN | cash and cash equivalent |
| `money_cap` | HK | 货币资金 |
| `net_profit` | CN | net profit |
| `net_profit` | CN | profit attributable |
| `net_profit` | HK | 净利润 |
| `non_oper_exp` | CN | non-operating expense |
| `non_oper_exp` | HK | non-operating expense |
| `non_oper_exp` | HK | 营业外支出 |
| `non_oper_income` | CN | non-operating income |
| `non_oper_income` | HK | non-operating income |
| `non_oper_income` | HK | 营业外收入 |
| `non_recurring_items_breakdown` | CN | 非经常性损益情况 |
| `non_recurring_items_breakdown` | CN | non-recurring items |
| `non_recurring_items_breakdown` | CN | non-recurring profit or loss |
| `non_recurring_items_breakdown` | CN | exceptional items |
| `non_recurring_items_breakdown` | CN | items affecting comparability |
| `non_recurring_items_breakdown` | CN | one-off items |
| `non_recurring_items_breakdown` | HK | 非经常性损益 |
| `non_recurring_items_breakdown` | HK | 非经常性损益项目 |
| `non_recurring_items_breakdown` | HK | 非经常性损益明细 |
| `non_recurring_items_breakdown` | HK | 非经常性损益情况 |
| `non_recurring_items_breakdown` | HK | 扣除非经常性损益 |
| `non_recurring_items_breakdown` | HK | non-recurring items |
| `non_recurring_items_breakdown` | HK | exceptional items |
| `operating_cash_flow` | CN | operating cash flow |
| `operating_cash_flow` | HK | 经营活动产生的现金流量净额 |
| `operating_cost` | CN | operating costs |
| `operating_cost` | CN | cost of revenue |
| `operating_cost` | HK | cost of revenue |
| `operating_cost` | HK | 营业成本 |
| `operating_profit` | CN | operating profit |
| `operating_profit` | CN | operating income |
| `operating_profit` | HK | 营业利润 |
| `other_cur_assets` | CN | other current assets |
| `other_cur_assets` | HK | 其他流动资产 |
| `rd_exp` | CN | research and development |
| `rd_exp` | CN | research expense |
| `rd_exp` | HK | research expense |
| `rd_exp` | HK | 研发费用 |
| `receiv_tax_refund` | CN | receipts of tax refunds |
| `receiv_tax_refund` | CN | tax refund received |
| `receiv_tax_refund` | HK | receipts of tax refunds |
| `receiv_tax_refund` | HK | tax refund received |
| `receiv_tax_refund` | HK | 收到的税费返还 |
| `receivables_aging` | CN | ageing analysis of trade receivables |
| `receivables_aging` | CN | aging analysis of trade receivables |
| `receivables_aging` | CN | ageing analysis of trade and notes receivables |
| `receivables_aging` | CN | aging analysis of trade and notes receivables |
| `receivables_aging` | CN | ageing analysis of receivables |
| `receivables_aging` | CN | aging analysis of receivables |
| `receivables_aging` | CN | trade receivables aging |
| `receivables_aging` | CN | trade receivables ageing |
| `receivables_aging` | HK | ageing analysis of trade and notes receivables |
| `receivables_aging` | HK | ageing analysis of receivables |
| `receivables_aging` | HK | aging analysis of receivables |
| `receivables_aging` | HK | trade receivables aging |
| `receivables_aging` | HK | trade receivables ageing |
| `receivables_aging` | HK | 应收账款账龄 |
| `related_party_receivables_payables` | CN | related party transactions |
| `related_party_receivables_payables` | CN | amounts due from related parties |
| `related_party_receivables_payables` | CN | amounts due to related parties |
| `related_party_receivables_payables` | HK | 关联方 |
| `repurchase_of_stock` | CN | repurchase of capital stock |
| `repurchase_of_stock` | CN | share buyback |
| `repurchase_of_stock` | CN | stock repurchase |
| `repurchase_of_stock` | HK | repurchase of capital stock |
| `repurchase_of_stock` | HK | share buyback |
| `repurchase_of_stock` | HK | 回购股票 |
| `repurchase_of_stock` | HK | 回购股份 |
| `restricted_cash` | CN | restricted cash |
| `restricted_cash` | CN | pledged deposits |
| `restricted_cash` | CN | cash held as collateral |
| `restricted_cash` | CN | 受限制现金 |
| `restricted_cash` | CN | 受限制存款 |
| `restricted_cash` | HK | cash held as collateral |
| `restricted_cash` | HK | 受限制现金 |
| `revenue` | CN | revenue |
| `revenue` | HK | 营业收入 |
| `segment_revenue_profit` | CN | operating segment information |
| `segment_revenue_profit` | CN | segment revenue |
| `segment_revenue_profit` | CN | segment profit |
| `segment_revenue_profit` | CN | operating segments |
| `segment_revenue_profit` | CN | operating segment |
| `segment_revenue_profit` | HK | segment profit |
| `segment_revenue_profit` | HK | 分部信息 |
| `selling_general_administrative` | CN | selling general and administrative |
| `selling_general_administrative` | CN | management expenses |
| `selling_general_administrative` | HK | selling general and administrative |
| `selling_general_administrative` | HK | management expenses |
| `selling_general_administrative` | HK | 销售费用 |
| `selling_general_administrative` | HK | 管理费用 |
| `st_borr` | CN | short-term borrowings |
| `st_borr` | CN | bank and other debts current |
| `st_borr` | HK | bank and other debts current |
| `st_borr` | HK | 短期借款 |
| `stock_based_compensation` | CN | share-based payment |
| `stock_based_compensation` | CN | share-based compensation |
| `stock_based_compensation` | CN | stock-based compensation |
| `stock_based_compensation` | CN | equity-settled share-based |
| `stock_based_compensation` | HK | 股权激励 |
| `time_deposits_or_wealth_products` | CN | time deposits |
| `time_deposits_or_wealth_products` | CN | wealth management products |
| `time_deposits_or_wealth_products` | CN | structured deposits |
| `time_deposits_or_wealth_products` | HK | 理财产品 |
| `total_assets` | CN | total assets |
| `total_assets` | HK | 资产总计 |
| `total_cur_assets` | CN | current assets |
| `total_cur_assets` | HK | 流动资产合计 |
| `total_cur_liab` | CN | current liabilities |
| `total_cur_liab` | HK | 流动负债合计 |
| `total_liabilities` | CN | total liabilities |
| `total_liabilities` | HK | 负债合计 |

## Terminal candidates (no_hit across >= 2 companies in a market; PDF-only diagnostic — provider-clean fields excluded, verify against source policy before acting)

| Field | Market | Companies |
|---|---|---|
| `c_pay_to_staff` | HK | 00001, 01113, 01810, 02498, 03320, 06862, 09987 |
| `capitalized_interest` | CN | 300750, 600519, 601919, 688008 |
| `capitalized_rd` | HK | 00001, 01113, 01810, 02498, 03320, 06862, 09987 |
| `depreciation_amortization` | CN | 300750, 600519, 601919 |
| `dps` | CN | 300750, 600519, 601919, 688008 |
| `lease_liability_maturity` | CN | 300750, 600519, 601919, 688008 |
| `receiv_tax_refund` | HK | 00001, 01113, 01810, 02498, 03320, 06862, 09987 |
| `restricted_cash` | CN | 300750, 600519, 601919, 688008 |
| `segment_revenue_profit` | CN | 300750, 600519 |
| `selling_general_administrative` | HK | 00001, 01113, 01810, 02498, 03320, 06862, 09987 |
