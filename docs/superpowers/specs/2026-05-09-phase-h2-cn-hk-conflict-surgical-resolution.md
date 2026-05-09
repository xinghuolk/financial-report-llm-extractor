# Phase H2: CN/HK Conflict Surgical Resolution Spec

> 日期：2026-05-09
> 状态：Draft
> 前置：Phase EC（evaluate-company orchestrator）+ Tier 1 follow-ups（period 归一化、markdown 候选值显示、dead params cleanup）已落地。
> 触发：Phase EC live run 在 600519/2024 上暴露 7 个 normalized_value_conflict 字段，依据 root-cause 分析拆为「3 sign convention + 5 真语义差」两类需要 surgical resolution。

## 目标

按 H1 模式逐字段做 provider raw field semantics proof，把 7 个 normalized_value_conflict 字段（across CN+HK markets）按"能 clean 就 clean，不能就 terminal_unverified"原则收敛。**符合 drift §177**：未经 PDF 语义证明，不静默 promote；用 `provider_semantics_unverified` 类目维护 architectural honesty。

## Non-Goals

- 不解决 14 个 `missing_source_candidate`（属单源覆盖空洞，不是冲突；归 catalog 扩展 / Phase N5 范围）。
- 不重写 reconciliation / source_policy 的整体架构 —— 仅扩展 sign-normalize 单点机制。
- 不做新 provider adapter 工作。
- 不引入 LLM-based semantic disambiguation。
- 不动 H1 已落地的 HK fix_assets / accounts_receiv / acct_payable 决策（`provider_semantics_unverified` rules）。

## 7 个 Conflict 字段分类（基于 600519/2024 数据）

| 字段 | AKShare raw | Yahoo raw | AKShare 值 | Yahoo 值 | Δ% | 类别 |
|------|-------------|-----------|-----------|----------|-----|------|
| capital_expenditures | CONSTRUCT_LONG_ASSET | Capital Expenditure | +4.68B | −4.68B | 0%（abs） | **A: Sign convention** |
| interest_paid_cash | PAY_INTEREST_COMMISSION | Interest Paid Direct | +97M | −97M | 0%（abs） | **A: Sign convention** |
| dividends_paid | ASSIGN_DIVIDEND_PORFIT | Cash Dividends Paid | +70.95B | −68.79B | 2.9%（abs） | **A + B** |
| revenue | 营业收入 | Total Revenue | 170.9B | 174.1B | 1.86% | **B: 真语义差** |
| operating_profit | OPERATE_PROFIT | Operating Income | 119.69B | 118.28B | 1.18% | **B: 真语义差** |
| selling_general_administrative | MANAGE_EXPENSE | Selling General And Administration | 9.32B | 10.36B | 10.11% | **B: catalog 不全** |
| depreciation_amortization | FA_IR_DEPR | Depreciation And Amortization | 1.72B | 2.06B | 16.64% | **B: 真语义差** |

## 范围

### Markets
- **CN**: 600519 / 2024（Kweichow Moutai，已有 inventory + PDF）。primary CN sample。
- **HK**: 00001 / 2025（CK Hutchison，conglomerate）+ 01113 / 2025（CK Asset，real estate）。
  - HK 2 公司提供行业多样性以防 SGA / D&A 单家偏差。
- **Cross-market expectation**: 对每个 H2 字段都要在 CN AND HK 上独立判断 promote 或 terminal_unverified —— 不假设 CN 的决策直接迁移到 HK（H1 经验）。

### Sample data
- 已有 CN inventory: `tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz`
- 已有 HK inventory: 同上
- PDF for spot-check:
  - 600519: `downloads/cn_stocks/600519/annual/2024_年度报告.pdf`
  - 00001: `downloads/hk_stocks/00001/annual/2025_annual_en.pdf`
  - 01113: `downloads/hk_stocks/01113/annual/2025_annual_en.pdf`

## 三大模块

### Module A: Sign normalization 机制

#### Catalog 扩展

`SourceMappingEntry.source_policy.market_policies.<MARKET>` 增加：

```jsonc
{
  "primary_route": "...",
  "cross_check_routes": [...],
  "on_conflict": "...",
  "single_source_requires_pdf": ...,
  "sign_normalize": "absolute"  // NEW; default "raw"
}
```

值：
- `"raw"`（默认）：reconciliation 比较 `normalized_value` 原值
- `"absolute"`：reconciliation 比较 `abs(normalized_value)`

适用前提：两 provider 报告同一现金流量项但符号约定不同（AKShare = 现金支付正向；Yahoo = 现金流出负向）。

#### Reconciliation 改动

`src/financial_report_llm_extractor/structured_sources/reconciliation.py`:
- 新增 `MarketPolicy.sign_normalize` 读取
- `_compare_candidates`（或等价函数）当 `sign_normalize == "absolute"` 时，比较前先 `abs()`
- `ReconciliationItem.status` = `"match"` 或 `"close"` 不变；只是输入数值变了
- 单测：测 sign_normalize=absolute 时 `+100 vs -100` 判 `match`；默认 `raw` 仍判 `conflict`

#### 应用范围（H2 阶段）

- `capital_expenditures`：CN sign_normalize=absolute；HK sign_normalize=absolute
- `interest_paid_cash`：CN sign_normalize=absolute；HK sign_normalize=absolute

`dividends_paid` 不放进 sign_normalize（abs 后仍有 2.9% 余差，需 Module B 单独处理）。

#### 不变量

- AKShare value 在 export 中保留原符号（不修改 normalized_value 本身），仅在 reconciliation 比较层做 abs。
- 仅同 currency + 同 unit + 同 period 的两候选才走 sign_normalize 比较，避免符号 + 单位错配的 false positives。
- 终态：sign-normalized 的 `clean_present` 行选 primary（按市场 source priority）的原始 normalized_value 显示在 evaluation.md。

### Module B: 5 真语义差 surgical resolution

每字段按下表流程：

1. PDF spot-check：定位字段在 PDF 中实际值
2. 比对 AKShare/Yahoo normalized_value
3. 决策：promote / terminal_unverified
4. 编辑 catalog + 加 `provider_raw_semantics_<market>.json` rule

#### 字段判断（基于已知信息 + drift §"net_profit raw field semantics" 模式预期）

| 字段 | 600519 (CN) | HK 期望 | 备注 |
|------|-------------|---------|------|
| **revenue** | promote AKShare（`OPERATE_INCOME` 营业收入；Yahoo Total Revenue 含 finance subsidiary 利息）→ clean_present | 各公司独判 | H1 已 revert 过 alias swap；H2 用 provider_semantics_sample_verified rule 加 PDF 证明 |
| **operating_profit** | TBD by PDF（差 1.18% 微小，可能是 OPERATE_PROFIT 含 vs 不含 fair_value_change） | TBD | 待 PDF 验证 |
| **selling_general_administrative** | terminal_unverified（catalog `derivation` 当前仅支持 `A - B` 减法；`MANAGE_EXPENSE + SALE_EXPENSE` 加法 derivation 不在本 phase 范围） | terminal_unverified（per H1，HK Yahoo SGA 不可信） | 加 `provider_semantics_unverified: akshare_sga_partial` rule 记录 H1 已知问题；加法 derivation 留给 Phase H2.1 单独立项 |
| **depreciation_amortization** | terminal_unverified（AKShare FA_IR_DEPR 仅 fixed asset 折旧；Yahoo 含无形资产 amortization；二者非等价） | terminal_unverified | drift §"don't promote without semantics proof" |
| **dividends_paid** | sign 处理后仍差 2.9%（`已付` vs `宣告`时点差）→ terminal_unverified | TBD | catalog 加 `provider_semantics_unverified: dividends_paid_timing_mismatch` rule |

最终预期：CN 5 个真语义差中 ~1-2 promote（revenue 高概率，operating_profit 待 PDF）、~3-4 terminal_unverified（SGA / D&A / dividends_paid 锁定）；HK 偏保守 ~0-1 promote、~4-5 terminal_unverified。

**"TBD by PDF" 字段处理流程**（执行 plan 时）：
1. PDF spot-check 阶段（commit 3 前）：在 600519/00001/01113 PDF 中查找 operating_profit、revenue 等字段实际值
2. 在 plan 执行的某 task 中，把 spot-check 记录写入 `provider_raw_semantics_<market>.json` 的 `samples[]`，并据此填 `matches_raw_value`
3. 决策（promote / terminal_unverified）跟随 spot-check 结果。如 600519 PDF 不能提供决定性证据 → terminal_unverified（保守）
4. plan 不预设最终 promote 数量；`Module C 验证报告`产出最终统计

#### Catalog edit pattern（per market）

```jsonc
"<field_id>": {
  ...
  "source_policy": {
    "market_policies": {
      "CN": {
        "primary_route": "akshare_direct",        // <-- 调整 if promote
        "cross_check_routes": ["yahoo_direct"],
        "on_conflict": "select_primary_require_pdf"  // <-- 调整 if proven
                     | "preserve_conflict"            // <-- if terminal
      },
      "HK": {...}
    }
  }
}
```

#### `provider_raw_semantics_<market>.json` rule pattern

参考 `provider_raw_semantics_hk.json` 现有 schema：

```json
{
  "provider": "akshare",
  "market": "CN",
  "raw_field_name": "OPERATE_INCOME",
  "raw_field_code": null,
  "turtle_field_id": "revenue",
  "semantic_claim": "营业收入 = 主营业务收入 + 其他业务收入；不含 finance subsidiary 利息收入",
  "classification": "provider_semantics_sample_verified",
  "trusted_currency": "CNY",
  "trusted_unit": "yuan",
  "trusted_unit_multiplier": 1,
  "allowed_as_primary": true,
  "related_only_fields": [
    {"raw_field": "TOTAL_OPERATE_INCOME", "reason": "营业总收入；包含其他业务/利息收入；不等价 Turtle revenue"}
  ],
  "negative_examples": [],
  "proof_origin": "sampled_pdf_policy_proof",
  "samples": [
    {"company_id": "600519", "period_end": "2024-12-31",
     "pdf_page": "TBD", "pdf_value": "170,899,152,276.34", "currency": "CNY",
     "matches_raw_value": true}
  ],
  "required_proof": []
}
```

如不能 promote，使用 `classification: "provider_semantics_unverified"` + 在 `samples[].matches_raw_value: false` 记录原因。

### Module C: Live before/after report

#### 输出
`docs/phase_h2_validation_report.md`：

```markdown
# Phase H2 Validation Report

> Date: YYYY-MM-DD
> Companies: 600519/2024-12-31, 00001/2025-12-31, 01113/2025-12-31

## Summary table

| Company | clean_present BEFORE | clean_present AFTER | Δ |
|---------|----------------------|---------------------|---|
| 600519 | X | Y | +N |
| 00001 | X | Y | +N |
| 01113 | X | Y | +N |

## Per-field migration

| Field | Company | BEFORE bucket | AFTER bucket | Reason |
|-------|---------|---------------|--------------|--------|
| revenue | 600519 | unresolved_conflict | clean_present | provider_semantics_sample_verified (akshare OPERATE_INCOME) |
| ... |
```

#### 生成方式

1. 改 catalog 前：保存当前 evaluation.json 副本（`tmp/runs/h2_before/<company>_<period>/`）
2. 改 catalog 后：重跑 evaluate-company（`tmp/runs/h2_after/<company>_<period>/`）
3. 写 diff 脚本生成 `phase_h2_validation_report.md`

可作为新 utility `scripts/run-evaluate-company-diff.sh` 的雏形（Tier 2 中 "coverage delta tool" 的最小版本）。

## 测试策略

| 测试 | 类型 | 默认 CI |
|------|------|--------|
| `test_reconcile_sign_normalize_absolute_treats_mirrored_values_as_match` | 单测 | ✅ |
| `test_reconcile_sign_normalize_default_raw_unchanged` | 单测（回归） | ✅ |
| `test_market_policy_loads_sign_normalize_field` | 单测（catalog) | ✅ |
| `test_catalog_consistency_h2` | 单测：assert sign_normalize 字段值 ∈ {raw, absolute} | ✅ |
| `test_catalog_validate_dividends_paid_terminal_unverified_for_cn` | 单测 + JSON 验证 | ✅ |
| `test_phase_h2_live_e2e_600519_revenue_promotes_to_clean` | 集成测，opt-in `REAL_SOURCE_VALIDATION=1` 或 fixture-replay | ❌ opt-in |

## 实现拆分（5 commits）

| Commit | 主题 | LoC | 依赖 |
|--------|------|----:|------|
| 1 | feat: sign_normalize market policy + reconciliation abs comparison | ~80 | 无 |
| 2 | feat: apply sign_normalize=absolute to capital_expenditures + interest_paid_cash (CN+HK) | ~60 | C1 |
| 3 | feat: surgical resolution for revenue + operating_profit (PDF-verified per market) | ~120 | C1 |
| 4 | feat: SGA derivation (MANAGE+SALE for CN) + D&A/dividends_paid terminal_unverified | ~150 | C3 |
| 5 | docs: Phase H2 validation report + roadmap implementation result | ~100 | C1-C4 |

每 commit 独立绿。

## 验收标准

- 5 commits 全部独立 pytest + ruff + mypy 绿
- ≥ 5 新单测
- catalog_consistency 测试覆盖新加 `sign_normalize` 字段
- `evaluate-company` 重跑 600519/2024 显示：unresolved_conflict 21 → 21 - N（N ≥ 2，至少 capital_expenditures + interest_paid_cash 两个 sign-convention 字段 promote；revenue/operating_profit promote 数取决于 PDF spot-check 结果）
- HK 2 公司同样跑通，桶迁移记录在 phase_h2_validation_report.md
- roadmap 加 "Phase H2 Implementation Result" 段落，明确 promote/terminal 分类
- 不引入 H1 类型的"silent semantic promotion"（每个 promote 都有对应 `provider_raw_semantics_<market>.json` 中的 sample-verified rule）

## Open Questions / 风险

- **加法 derivation 限制（已 verified）**: catalog `derivation` 字段当前仅支持 `A - B`（mapping.py:251-258，`parts[1] != "-"` → `unsupported derivation`），不支持加法。SGA `MANAGE_EXPENSE + SALE_EXPENSE` 加法在 H2 内不实现，留给 Phase H2.1（独立 spec）。SGA + D&A 在 H2 阶段都按 terminal_unverified 处理。
- **HK PDF 取页**：HK 公司年报多语言（en/zh）；spot-check 选 en 版方便对照 Yahoo 字段名，但 zh 版可能更精确。
- **Yahoo HK Total Revenue 语义**：H1 没动 HK revenue。本次 promotion 决策可能不一致 across markets（CN promote akshare、HK 保留 unresolved）。这是 architecturally honest 的，但需在文档中明确说明。
- **`sign_normalize` 与 H1 H0 `null_means_zero` 的交互**：当 null_means_zero 字段在某 provider 缺失时，是否还跑 sign_normalize 比较？应该不跑（仅当两侧都 present 才比较），但需在测试中明确。
- **Sample size**: 单 CN 公司（600519）做语义证明可能不够。drift 文档强调 sampled proof 不是 final per-export evidence；如 H2 后期 review 提出"600519 单样本证明不足"，可能需要回到 commit 1 加更多 CN 公司。
