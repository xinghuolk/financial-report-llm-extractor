# gross_profit 06862/09987 派生分歧核查（PR #20 follow-up）

日期：2026-06-12。结论先行：**两家是两种完全不同的问题**——09987 是
**AKShare HK 币种错标 artifact**（且污染面不止毛利），06862 是**真实口径差**
（决策成立）。两项均有 PDF 地面真值实锤。

## 09987 Yum China（8.9x）：币种错标，非口径差

| 证据 | 值 |
|---|---|
| PDF p76 "Total revenues" FY2024 | **$11,303M USD** |
| Yahoo Total Revenue | 11,303,000,000 USD（与 PDF 精确一致） |
| AKShare 营业额（标 USD） | 80,258,486,000 |
| **比值** | 80,258,486,000 ÷ 11,303,000,000 = **7.1006 = USD/CNY 汇率** |

AKShare HK feed（东财 `stock_financial_hk_report_em`）下发的是 **CNY 折算
值**，但 inventory 用 issuer 申报币种图（`hk_issuer_financial_currency`，
09987=USD）给 AKShare 记录盖章——`PandasAkshareClient(hk_default_currency=…)`
把 issuer 币种当成了 feed 币种。结果：**09987 的全部 AKShare 记录数值是
CNY、标签是 USD**。毛利 16,756M"USD"实为 ~16.76B CNY ≈ 2.36B USD（币种
修正后与 Yahoo 1.89B 的残差 ~1.25x 才是口径差部分）。

**影响面**：所有非 CNY 申报的 HK issuer（00001/01113 HKD、09987 USD）的
AKShare 候选全部可疑。00001 的 total_assets A- 分歧（akshare 1043.83B vs
yahoo/PDF 1155.67B）与 CNY 折算假设方向一致（1043.83 CNY ≈ 1138 HKD，差
1.5% 可由折算日汇率解释），但不如 09987 的 7.1006 决定性。

**Recon 行为**：`_metadata_error` 本有 "candidate currencies differ" 检查
——正因两侧都被错标成同币种，recon 才做了无意义的跨币种数值比较并报出
8.9x 伪冲突。修正标签后 recon 会给出诚实的币种不匹配分类。

## 06862 海底捞（2.2x）：真实口径差，决策成立

PDF p142 利润表（RMB'000）：Revenue 42,754,687；Raw materials and
consumables used (16,211,077)；Staff costs (14,113,263)…

| 候选 | 派生 | 验证 |
|---|---|---|
| AKShare 毛利 26,543,610 | 收入 − 原材料 | 42,754,687 − 26,543,610 = **16,211,077，与 PDF 原材料行逐数字一致** |
| Yahoo Gross Profit 12,108,412 | 收入 − Cost Of Revenue 30,646,275（原材料+员工成本等） | 常规 COGS 口径 |

两家同币种（CNY）、同营收。AKShare 的"毛利"是**原材料毛利**（餐饮业惯用
指标），Yahoo 是**常规毛利**。跨公司可比性上 Yahoo 口径更标准——PR #20
的 standardized acceptance 决策对 06862 成立且无需修正。

## 建议（待决策）

1. **修 AKShare HK 币种盖章**：feed 实证为 CNY（09987 比值 7.1006 决定性；
   06862 与 RMB'000 报表逐数字一致；00001 方向一致）。建议 AKShare HK
   记录统一标 CNY（不再沿用 issuer 申报币种图——那张图只适用于 Yahoo 路
   径）。效果：09987 伪冲突变诚实的 currency-mismatch；00001/01113 的部分
   A- 分歧将重新分类。
2. 修正后重跑 cohort recon，复核 00001/01113 的 A- 分歧簇有多少属于折算
   artifact。
