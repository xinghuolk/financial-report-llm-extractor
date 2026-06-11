# 新公司分析标准工作流

> 适用：把一个新公司（CN 或 HK）纳入 source-first 财报抽取器的分析 cohort，
> 评估当前 catalog / trust policy / LLM supplement 在该公司上的覆盖率。
> Owner: 项目内部（Claude / 工程师）。
> 最近更新: 2026-05-12（Phase HK-B.9 抽象自 6 HK + 3 新 HK 公司经验）。

## TL;DR

```bash
# Step 0 (HK only): PDF 确认 reporting currency → 加入 HK_ISSUER_FINANCIAL_CURRENCY map
# Step 1: 实时拉取 AKShare + Yahoo
COMPANY=<ticker> YEAR=<year> MARKET=<CN|HK> PROVIDERS=akshare,yahoo \
  scripts/run-fetch-source-inventory.sh

# Step 1.5: 零成本 PDF 别名预检（先于花钱的 LLM 评估）
financial-report-llm-extractor audit-pdf-aliases \
  --pdf downloads/<market>_stocks/<ticker>/annual/<year>_annual_en.pdf \
  --emit-catalog-patch \
  --out tmp/runs/<ticker>_<year>_alias_audit
# 读 alias_audit.md：normalized_only/prose_only 字段先补 catalog 别名再进 Step 2

# Step 2: 全流程评估（⚠️ 必须带 PDF + LLM_CONFIG）
COMPANY=<ticker> YEAR=<year> MARKET=<CN|HK> \
  PDF_PATH=downloads/<market>_stocks/<ticker>/annual/<year>_annual_en.pdf \
  LLM_CONFIG=tmp/llm_configs/deepseek.json \
  scripts/run-evaluate-company.sh

# Step 3: 读 tmp/runs/<ticker>_<year>-12-31/evaluation.md
# Step 4: 按 unresolved_conflict.reason 分类决策
# Step 5: PDF spot-check + catalog 更新（若需 promotion）
# Step 6: 回归测试 + commit
```

**⚠️ 常见错误**：跑 Step 2 时漏 `PDF_PATH` + `LLM_CONFIG`，则 P3 pdf_only
字段（dividend_plan, dps, contingent_liabilities_commitments 等）全部留在
`missing_source_candidate`，看起来像覆盖率低；实际是 LLM supplement 步骤被
跳过。**LLM 是 source-first 链路的必要末端**（虽然按 design 是 fallback，
但对于 pdf_only 字段是唯一源）。

## 前置条件

1. 年报 PDF 已下载到 `downloads/<market>_stocks/<ticker>/annual/<year>_annual_en.pdf`
   （和 `_zh.pdf` 若可用）
2. `.env` 含 `DEEPSEEK_API_KEY`（或对应 LLM 配置）
3. **执行前先 source .env**（脚本不会自动 source）：
   ```bash
   set -a; source .env; set +a
   ```
   ⚠️ 不 source 则 LLM step 全部失败（error: "missing API key environment
   variable: DEEPSEEK_API_KEY"），所有 P3 pdf_only 字段都 `extraction_failed`。
4. 本地 venv 装好（`uv sync` 已跑过）
5. 网络可达 AKShare + Yahoo Finance（live fetch 阶段）

## Step 0: 确认 reporting currency（HK 公司）

HK 上市公司可以用 HKD / RMB(CNY) / USD 任一币种报告财务报表（functional
currency 由 issuer 决定）。Yahoo HK adapter 早期 hardcode `currency=HKD`，
现已由 `HK_ISSUER_FINANCIAL_CURRENCY` map（`source_inventory_fetch.py`）
按 issuer 给出正确币种。

新 HK 公司：

```bash
# 提取 BS 表头识别币种
pdftotext -layout downloads/hk_stocks/<ticker>/annual/<year>_annual_en.pdf \
  /tmp/<ticker>_<year>.txt
grep -nE "(HK\\\$ million|RMB.{0,3}('|million|thousand)|US\\\$ million|functional currency|reporting currency)" \
  /tmp/<ticker>_<year>.txt | head -10
```

**判断规则**：
- "HK$ million" 通篇主导 → `"HKD"`
- "RMB million" / "百萬人民幣" → `"CNY"`
- "US$ million" 或 SEC reporter（如 Yum China） → `"USD"`
- 多币种混用：以 Consolidated Statement of Financial Position 的列标题为准
- "functional currency was changed from X to Y" → 以 latest 为准

加入 `src/financial_report_llm_extractor/structured_sources/source_inventory_fetch.py`
的 `HK_ISSUER_FINANCIAL_CURRENCY` dict。CN 公司跳过本步（AKShare CN 已用 yuan）。

## Step 1.5: PDF 别名预检（audit-pdf-aliases，零 LLM 成本）

新 PDF 在进付费 LLM 评估前先跑一遍审计（秒级，纯本地）：

```bash
financial-report-llm-extractor audit-pdf-aliases \
  --pdf downloads/<market>_stocks/<ticker>/annual/<year>_annual_en.pdf \
  --emit-catalog-patch \
  --out tmp/runs/<ticker>_<year>_alias_audit
```

输出 `alias_audit.{json,md}` + `catalog_patch.json`，每字段四态：

| 状态 | 含义 | 动作 |
|---|---|---|
| `exact_hit` | 别名精确命中且落在对应报表 section | 无需动作 |
| `prose_only_hit` | 命中但全在 section 外（散文/MD&A）——付费 run 大概率仍 miss | 查 `alias_audit.md` 的命中页，决定是否补报表行措辞 |
| `normalized_only_hit` | 仅归一化命中（the/复数/连字符差异） | 把 `suggested_aliases`（PDF 原文措辞）经人工 review 后补进 catalog |
| `no_hit` | 全 miss | 大概率 issuer 不披露；勿盲目加词 |

`catalog_patch.json` 是 **review-gated 建议**，必须人工审核后手动应用——建议可能错误
（token 窗口可能落在更长短语内，如 "non-current asset" 被建议给 total_cur_assets）。
`warnings.empty_anchor_statement_types` 非空时表示该 PDF 的某报表 section 锚点全失效
（absence_means_zero 兜底对该 PDF 静默失效），需要补锚点。

## Step 1: 拉取 source inventory（live fetch）

```bash
COMPANY=<ticker> YEAR=<year> MARKET=<CN|HK> PROVIDERS=akshare,yahoo \
  OUT_DIR=tmp/runs/<ticker>_<year>-12-31 \
  scripts/run-fetch-source-inventory.sh
```

输出：
- `source_inventory.jsonl` — provider raw records（AKShare + Yahoo）
- `source_inventory_summary.json` — per-source 统计
- `source_artifacts/` — 原始 JSON dump（AKShare/Yahoo 响应）
- `source_artifact_manifest.json` — artifact 索引

**注意**：每个 fetch 是一次 live API call，AKShare HK 偶尔会限流；如果失败
等几秒重试。Yahoo Finance 通过 yfinance 库，可能因 rate limit 偶发空响应 —
检查 record_count，太低（< 100）时建议重跑。

## Step 2: 全流程评估（必须带 PDF + LLM_CONFIG）

```bash
COMPANY=<ticker> YEAR=<year> MARKET=<CN|HK> \
  INVENTORY=tmp/runs/<ticker>_<year>-12-31/source_inventory.jsonl \
  OUT_DIR=tmp/runs/<ticker>_<year>-12-31 \
  PDF_PATH=downloads/<market>_stocks/<ticker>/annual/<year>_annual_en.pdf \
  LLM_CONFIG=tmp/llm_configs/deepseek.json \
  PRIORITIES=P0,P1,P2,P3 \
  scripts/run-evaluate-company.sh
```

⚠️ **PDF_PATH 和 LLM_CONFIG 都必须**，否则 LLM supplement 步骤被 gate 跳过：

```python
# company_evaluation.py 内部门控
if pdf_provided and llm_config_path is not None:
    _run_llm_supplement_step(...)
```

输出：
- `evaluation.json` + `evaluation.md` — 主报告（人类先读）
- `extraction_result.json` — final export with selected_source / value per field
- `llm_evidence_supplement.json` — LLM 抽取的 P3 pdf_only 字段
- `source_policy_report.json` — bucket 分类 + verification_required + 冲突原因
- `warning_classification.json` + `.md` — 警告字段分类（mapping_expansion_required, statement_metadata_unproven 等）
- `hk_yahoo_trust_policy_report.json` — HK Yahoo trust 规则应用记录
- `hk_15_field_closure_report.{json,md}` — HK 15-field terminal/verified 闭合
- `reconciliation_report.json` — provider 间对账状态
- `turtle_mapping.json` — catalog mapping + candidate 值
- `review_summary.json` — 字段级 review 状态汇总
- `source_coverage_summary.{json,md}` — coverage 计数（含 unmapped）

**LLM 成本估算**（DeepSeek）：14 个 P3 pdf_only 字段 × ~$0.001/call ≈ $0.014 per company。

## Step 3: 读 evaluation.md

人类可读，看 3 个关键 section：

1. **Coverage by priority × bucket** 矩阵（顶部）：一眼看出 P0/P1/P2/P3 在
   clean_present / unresolved_conflict / llm_supplement_present / terminal_unverified
   / not_in_scope / source_unavailable 的分布。
2. **Per-field detail** 表：每字段 bucket + selected_source + value + 冲突原因
3. （隐含）markdown 内还会引用其他 report 路径

## Step 4: 字段分类分析

`unresolved_conflict` 字段按 **reason** 字段细分（关键！别只看总数）：

| reason | 含义 | 处理路径 |
|---|---|---|
| `missing_source_candidate` | 该 field 没有 provider raw 数据（Yahoo 和 AKShare 都没返回） | - 若是 P3 pdf_only 字段 → LLM supplement 应该 cover（若 LLM 也 miss 则记为 P3 LLM 命中率分母+1）<br>- 若是 CN-only AKShare 字段（fv_value_chg_gain, invest_income, non_oper_income/exp, receiv_tax_refund 等） → 对 HK 是 by-design 不可用<br>- 若是 P0/P1 字段 → 数据真缺失，记录原因 |
| `normalized_value_conflict` | 两个 provider 都有数据但实质不一致 | PDF spot-check 决定哪个 provider 匹配 PDF；该 issuer 加入 allowlist or 终态化 |
| `single_source_unverified` | 只有一个 provider 有值，且该字段需 PDF 验证（trust rule 未 cover 该 issuer） | PDF spot-check + 加入 allowlist or 标记 single-source acceptable |
| `currency_as_unit` / `metadata_currency_suspected` | HK Yahoo 元数据警告（pre-HK-B.5.1 历史问题） | 已基本由 HK_ISSUER_FINANCIAL_CURRENCY map 处理 |

**已知 CN-only fields**（HK reporter 看不到，跳过）：
- `fv_value_chg_gain`, `invest_income`, `non_oper_income`, `non_oper_exp`,
  `receiv_tax_refund` — AKShare CN-only，HK 端 missing 是 by-design

## Step 5: PDF spot-check（针对实质冲突）

对每个 `normalized_value_conflict` / `single_source_unverified` 字段：

```bash
# 提取 PDF 文本
pdftotext -layout downloads/<market>_stocks/<ticker>/annual/<year>_annual_en.pdf \
  /tmp/spotcheck_<ticker>.txt

# Grep 字段对应的 PDF 行项目
grep -nE "(Trade payables|应付帐款|Creditors|Accounts payable)" \
  /tmp/spotcheck_<ticker>.txt | head -10
```

**对比表**：

| 字段 | Yahoo 值 | AKShare 值 | PDF 行 (位置) | PDF 值 | 匹配 |
|---|---|---|---|---|---|
| acct_payable | 3.38B | 3.91B | "Trade payables" Note X p.Y | 3.38B | Yahoo ✓ |
| ... | ... | ... | ... | ... | ... |

**决策**：
- Yahoo 匹配 PDF：把 issuer 加入 `hk_yahoo_trust_policy.json` 对应 rule 的
  `pdf_verified_company_ids` allowlist + 加 sample
- AKShare 匹配 PDF：考虑 CN-style derivation rule 或 market-specific override
- 都不匹配：标记 terminal_unverified，记录在 recon doc

**已知 HK 物业公司命名约定**：
- Trade payables → "Creditors"
- Trade receivables → "Debtors"
（01113 CK Asset 是参考案例，见 `docs/phase_hk_b_5_recon.md`）

## Step 6: Catalog 更新 + regression test + commit

1. 编辑 `field_catalog/hk_yahoo_trust_policy.json`：
   - 加 issuer 到 `pdf_verified_company_ids`
   - 加 sample（含 pdf_page, statement_line, pdf_value, pdf_unit_multiplier,
     reported_currency, reported_unit, match_basis）
2. 编辑 `field_catalog/provider_raw_semantics_hk.json`：
   - 同步 `pdf_verified_company_ids`
3. 更新 regression test 文件：
   - `tests/test_phase_hk_b_<field>.py`：加新 issuer case
   - `tests/test_hk_yahoo_trust_policy.py`：调整 verified sample 总数
   - 若涉及 `test_provider_baseline_replay.py`：调整 `EXPECTED_HK_YAHOO_VERIFIED_FIELDS`
4. 跑全套验证：

```bash
uv run pytest -v && uv run ruff check . && uv run mypy src tests
```

5. 写 recon doc（如果是新 phase）：`docs/phase_hk_b_X_recon.md` 记录 PDF
   samples + 决策 + 例外情况
6. Commit 按项目惯例：`feat: phase hk-b.X - <field> <action> (<n-issuer> promotion)`

## 常见陷阱（按出现频率）

0. **跳过 Step 1.5 直接进 LLM 评估**
   → 别名缺口（the/复数/措辞差异）要花一次付费 run 才暴露，然后人肉翻 PDF 定位；
   预检 7 秒就能给出 suggested_aliases
1. **漏 PDF_PATH + LLM_CONFIG**（最常见，本文档诞生的直接原因）
   → P3 pdf_only 字段全部 unresolved；coverage 表面低
2. **没 source .env**（仅次于上面，Phase HK-B.9 中曾踩）
   → LLM step 跑了但全部失败，`extraction_failed` 错误："missing API key
   environment variable: DEEPSEEK_API_KEY"。需先 `set -a; source .env; set +a`。
3. **不读 evaluation.md，只看 total counts**
   → 把 by-design missing 当作问题
3. **不按 reason 分类，把所有 unresolved 一起 grep**
   → 浪费时间分析 `missing_source_candidate`（无 actionable item）
4. **不区分 CN-only fields**（fv_value_chg_gain 等对 HK 是 by-design 缺失）
5. **未先确认 reporting currency 直接 fetch**
   → Yahoo HK record 标错币种（HK_ISSUER_FINANCIAL_CURRENCY 漏配 → fallback HKD）
6. **新 issuer 直接广播 promote 而无 PDF spot-check**
   → 违反 drift §177；catalog 应只在 `pdf_verified_company_ids` 中的 issuer
   触发 trust rule
7. **PDF spot-check 选错行**（如把"Trade payables and other current liabilities"
   combined 行用为 pure trade scope 的对照）
   → 需注意 HK 物业公司用 "Creditors"/"Debtors"；银行用合并行 + Note 拆分；
   美国 reporter (Yum) 用 "Accounts receivable, net" 而非 Trade receivables

## 已知 HK reporter 币种映射（HK_ISSUER_FINANCIAL_CURRENCY）

| Ticker | Issuer | Currency | 备注 |
|---|---|---|---|
| 00001 | HSBC / CK Hutchison | HKD | 银行系，BS 用 HKD millions |
| 00392 | Beijing Enterprises | CNY | 2024 起 functional currency HKD→RMB |
| 01113 | CK Asset Holdings | HKD | 物业 (用 Creditors/Debtors 命名) |
| 01810 | Xiaomi | CNY | RMB '000 |
| 02498 | RoboSense | CNY | RMB '000 |
| 02669 | China Overseas Property Services | CNY | RMB million |
| 03320 | China Resources Pharmaceutical | CNY | RMB million |
| 06862 | Haidilao | CNY | RMB '000 (含中英对照) |
| 09987 | Yum China | USD | US-domiciled SEC filer |

加新 HK ticker 时务必先 PDF 验证币种 → 加进 map → 再 fetch。

## 参考 phase 实例

- `docs/phase_hk_b_5_recon.md` — HK-B.5 (acct_payable) → .5.1/.5.2/.5.3
  (currency-label fix triplet) → .6 (fix_assets) 的完整 PDF spot-check 史
- `docs/phase_hk_b_recon.md` — HK-B 初版 recon（pre-promotion conflict shape）
- `docs/2026-05-11-phase-summary.md` — Wave 7 整体串联

## 相关脚本与文件

- `scripts/run-fetch-source-inventory.sh` — Step 1
- `scripts/run-evaluate-company.sh` — Step 2（注意带全部 env）
- `src/financial_report_llm_extractor/structured_sources/source_inventory_fetch.py`
  — `HK_ISSUER_FINANCIAL_CURRENCY` map 位置
- `field_catalog/hk_yahoo_trust_policy.json` — Yahoo HK trust 规则 + allowlist
- `field_catalog/provider_raw_semantics_hk.json` — provider semantic 规则
- `tmp/llm_configs/deepseek.json` — 默认 LLM config
- `.env` — `DEEPSEEK_API_KEY` 等 secrets
