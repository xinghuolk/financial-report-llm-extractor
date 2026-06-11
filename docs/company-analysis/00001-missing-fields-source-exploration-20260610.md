# 00001.HK 缺失字段溯源与补充优先级

日期：2026-06-10
方法：对照 `00001-ckh-3yr-2023-2025.md`（C/A0/A-/B 分级）与 `00001_hk_latest_value_analysis_data_gaps_20260604.md`（下游价值缺口），逐字段在 **2025 年报 ingested 全文**（`tmp/runs/00001_2025_postmerge/ingest/pages.jsonl`，350 页）中检索证据，并比对 catalog `pdf_aliases` 与 LLM supplement 的实际 reasoning，定位每个缺失的**根因**。

## 0. 核心发现

21 个 C 级字段并非同一种"缺失"。按根因分五类：

| 根因 | 字段数 | 含义 | 修复成本 |
|---|---|---|---|
| **①检索别名缺口** | 5 | 数据在 PDF 里，但 `pdf_aliases` 与年报措辞不匹配 → `no chunks matched aliases`，LLM 根本没看到 | 极低（catalog 加别名） |
| **②选错 chunk / 语义映射** | 4 | 别名命中了错误页面（MD&A 散文而非报表行），或 HK 措辞需要语义映射决策 | 低-中 |
| **③absence_means_zero 扩展** | 2 | LLM 已看到正确 section 且确认无该行 → 真零，但字段没挂 flag | 极低（catalog 加 flag） |
| **④口径/工程决策** | 4 | 数据存在但口径冲突（gross_profit）或需下游工程支持（dps 单位） | 中（需决策） |
| **⑤issuer 真不披露** | 8 | 全文 0 命中，CN 概念科目或综合企业不拆分 | 不可修（应转 terminal） |

## 1. 逐字段证据表

### ① 检索别名缺口 —— 数据就在 PDF 里（最高 ROI）

| 字段 | PDF 证据（2025 年报） | 现有别名为何 miss | 建议新增别名 |
|---|---|---|---|
| `receivables_aging` (P1) | **p229** "The ageing analysis of **the** trade receivables, presented based on the invoice date"（p247 另有应付账龄） | 别名是 `ageing analysis of trade receivables`，年报多了 "the" → substring 不中 | `ageing analysis of the trade receivables` 或宽化为 `ageing analysis` |
| `restricted_cash` (P1) | **p59** "assets totalling **HK$1,571 million** … were **pledged as security** for bank loans"；p269 note 同 | 别名 `pledged deposits` 措辞不存在 | `pledged as security` |
| `buyback_cancellation_progress` (P0↓) | **p76/p89** "the Company **did not hold any treasury shares**" → 无回购、无待注销，可作文本终态 | 别名无 `treasury shares` | `treasury shares` |
| `lease_liability_maturity` (P1) | **p280-283** "contractual **undiscounted** principal cash flows…Within/After" 到期表；p210 租赁 note | 别名 `lease liabilities maturity` 等短语不存在 | `undiscounted`、`maturity profile` |
| `related_party_receivables_payables` (P1) | **p269** note 39 "Related **parties** transactions Except as disclosed elsewhere…" | 别名是单数 `related party transactions`，年报用复数 "parties" | `related parties transactions` |

LLM reasoning 实证：这 5 个字段在 postmerge run 全部是 `no chunks matched aliases for this field` —— 检索层 miss，不是 LLM 抽取失败。

### ② 选错 chunk / 语义映射

| 字段 | PDF 证据 | 根因 | 修复 |
|---|---|---|---|
| `c_paid_for_taxes` (P2) | **p141** 现金流量表正文 "**Tax paid (5,571)**" | 别名 `taxes paid`(复数) 命中的是 p56 MD&A 散文 "higher taxes paid"，正文行是单数 "Tax paid" | 加别名 `tax paid`；预期值 -5,571 HK$M |
| `non_recurring_items_breakdown` (P2) | **p7-8/12/14-15** "one-time non-cash loss arising from the UK merger…HK$10,46x million / HK$9,915 million disposal loss / HK$1,445 million…" | 年报用 "**one-time**/one-off non-cash"，别名只有 `one-off items` 短语 | 加 `one-time`、`one-off`。**高价值**：2025 净利下滑主因就是这笔 UK merger 一次性损失 |
| `stock_based_compensation` (P2) | **p207** "do not have share option scheme or other dilutive potential ordinary shares"；**p269** note 35 "Share-based payments **Neither** the Company nor its subsidiary companies had…" | 年报**显式披露为无** → 真零；LLM 选到现金流 chunk 没看到 note 35 | 语义上等同 absence_means_zero/not_applicable，可加 notes 别名 `share-based payments neither` 或挂 flag |
| `other_cur_assets` (P1) / `non_oper_income`/`non_oper_exp` (P1) | p136 合并行 "Trade receivables **and other current assets** 42,307"+note 25 拆分；p134 "**Other income and gains** 976" | HK 报表无独立行，需决策：other_cur_assets=合并行−trade receivables（派生）；Other income and gains 映射 non_oper_income（此前 Codex run 已抽到 976） | 派生规则 / by_market alias 映射决策 |

### ③ absence_means_zero 扩展候选（merge 刚落地的机制直接复用）

| 字段 | 证据 | 说明 |
|---|---|---|
| `interest_bearing_debt_parent_company` (P1) | **p271** 母公司资产负债表完整：负债只有 "Other payables and accruals 134"，**无任何借款行** | postmerge LLM reasoning 原话："contain the parent-company statement of financial position (page 271) but do not include any line items for borrowings" —— **LLM 已看到正确 section 并确认无该行**，正是 zero_inference 设计场景，只差 catalog 上的 `absence_means_zero: true` |
| `stock_based_compensation` (P2) | p269 note 35 显式 "Neither…had" | 同上，亦可走 flag 路径（与②二选一） |

### ④ 口径 / 工程决策（不是抽取问题）

| 项 | 现状 | 证据与建议 |
|---|---|---|
| `gross_profit` (P1) | A- 冲突无定值 | PDF 只有 "Cost of inventories sold 113,633"（→毛利 166,403），akshare 141.67B、yahoo 139.20B 三方口径互不相同。需**定义决策**（采哪种 cost 口径），非加别名可解 |
| `selling_general_administrative` (P1) | terminal_unverified | **p202** note 8 有组分 "Office and general administrative expenses and others (9,466)" 等，可拼出 PDF 佐证完成 pdf_required 验证 |
| `dps` 单位 | 下游不支持 per-share 单位 | 纯下游工程项（结构化单位系统支持 `per share`） |
| `commitment_ratio`（下游字段） | 未提取 | **p125** Dividend Policy 全文已核：只承诺 "sustainable dividend in line with earnings improvement"，**无任何数字派息率承诺** → 应记录为"政策存在但无承诺比率"，`payout_M` commitment cap 对 00001 **不适用**，不是抽取缺口 |

### ⑤ issuer 真不披露（建议转 terminal not_applicable，停止重试）

全文 350 页 0 命中或仅有不相关上下文：

| 字段 | 说明 |
|---|---|
| `rd_exp` / `capitalized_rd` (P0/P3) | 综合企业不单列研发；"research and development" 全文无 |
| `receiv_tax_refund` (P2) | CN 现金流概念，HK 报表无 |
| `c_pay_to_staff` (P2) | HK 间接法现金流无此行；最接近的是利润表 "Staff costs 43,688"（费用≠现金），如要用须显式口径标注 |
| `time_deposits_or_wealth_products` (P1) | "time deposit/wealth management" 全文无 |
| `contract_liabilities_non_current` (P3) | 仅 p247 流动 5,321，无非流动拆分 |
| `fv_value_chg_gain` (P1) | P&L 无独立公允价值变动行（FV 变动走 OCI，p135/138-140） |

## 2. 下一步优先级（按下游价值信号 ROI 排序）

**第一批（本周可做，纯 catalog 改动 + 重跑验证）：**

1. **②非经常性损益别名**（`one-time`/`one-off`）—— 单项最高价值：2025 净利 11.8B 含 UK merger 一次性损失 ~10.5B，缺它下游利润质量判断整体失真。
2. **①五个别名缺口批量补**（receivables_aging / restricted_cash / buyback_cancellation_progress / lease_liability_maturity / related_parties）—— 一次 catalog PR，直接消掉 5 个 C 级；其中 buyback_cancellation 补完后，下游 P0 回购链(回购 0 + 无注销待办)完整闭环。
3. **②`tax paid` 别名** —— 预期直接抽到 -5,571 HK$M，消掉下游 P2 税务现金缺口。
4. **③`interest_bearing_debt_parent_company` 挂 `absence_means_zero`** —— 复用刚 merge 的机制，LLM 已证实 section 完整无该行。

**第二批（需小决策）：**

5. `stock_based_compensation`：选 flag 路径或 notes 别名路径，二选一落 0/N-A。
6. ⑤的 8 个字段在 catalog 标 terminal/not_applicable（HK market scope），停止每次 run 空转重试。
7. `commitment_ratio`：下游记录"政策无承诺比率"，关闭该缺口。

**第三批（口径决策，单独立项）：**

8. `gross_profit` 口径仲裁、SGA note-8 验证、`dps` per-share 单位支持、other_cur_assets/non_oper_income HK 语义映射。

**预期收益**：第一批落地后 00001 的 C 级从 21 → ~13，下游 P0/P1 缺口表中 7 项可关闭或终态化；且这些别名是 HK 年报通用措辞（ageing/pledged as security/treasury shares/undiscounted/one-time），大概率惠及其余 6 家 HK cohort。

## 3. 验证方式

每批改完跑：

```bash
financial-report-llm-extractor pipeline \
  --company 00001 --period-end 2025-12-31 --market HK \
  --pdf downloads/hk_stocks/00001/annual/2025_annual_en.pdf \
  --llm-config tmp/llm_configs/deepseek.json \
  --priorities P0,P1,P2,P3,P4 --force --no-cache \
  --out tmp/runs/00001_2025_alias_batch1
```

对照本表逐字段核对：预期值（p141 tax -5,571 / p59 pledged 1,571 / p76 no treasury shares / p7-8 one-time 明细）与 LLM 抽取页码一致才算闭环。
