# Phase M2: HK 15 字段终态闭环 Spec

> 日期：2026-05-07
> 状态：已实现，本文用于对齐当前实现与后续交接
> 路线图阶段：Phase M2

## 背景

Phase M 已经把 HK Yahoo trust policy 接入 provider baseline replay。当前 `00001` 和 `01113` 的 combined replay 基线是：

| 公司 | selected/covered | clean present |
|---|---:|---:|
| `00001` | `10/15` | `9/15` |
| `01113` | `10/15` | `9/15` |

Phase M2 的目标不是强行做到 `15/15 clean present`，而是让当前 HK 15 个字段全部进入稳定、可审查、可回归的终态 bucket。也就是说：

- 能 clean 的字段继续保持 clean。
- 不能 clean 的字段必须有明确原因。
- 不允许把 missing、mapping 未扩、Yahoo 定义未证明、PDF required、source unavailable 混在一个 warning 队列里。

## 现有实现

当前实现已经落在：

```text
src/financial_report_llm_extractor/structured_sources/hk_15_field_closure.py
```

核心合同：

- `HK_15_FIELD_IDS`
- `ClosureCategory`
- `Hk15FieldClosureItem`
- `Hk15FieldClosureReport`
- `build_hk_15_field_closure_report(...)`
- `write_hk_15_field_closure_artifacts(...)`

provider baseline replay 会为 HK slice 写出：

```text
hk_15_field_closure_report.json
hk_15_field_closure_report.md
```

并在 replay summary 的 `artifact_paths` 中暴露：

```json
{
  "hk_15_field_closure_report": ".../hk_15_field_closure_report.json",
  "hk_15_field_closure_markdown": ".../hk_15_field_closure_report.md"
}
```

## Closure Categories

当前 `ClosureCategory` 支持：

1. `clean_present`
2. `selected_with_warnings`
3. `yahoo_pdf_verified`
4. `yahoo_definition_unverified`
5. `pdf_required`
6. `mapping_expansion_required`
7. `source_unavailable`

`selected_with_warnings` 只作为兜底分类。HK 15-field closure 的目标是把剩余字段尽量归入更具体、更可审查的 bucket。

## 当前 15 字段结果

当前 `00001` 和 `01113` combined replay 的稳定结果如下。

`clean_present`：

1. `cash`
2. `financing_cash_flow`
3. `investing_cash_flow`
4. `operating_cash_flow`
5. `revenue`
6. `total_assets`
7. `total_cur_assets`
8. `total_cur_liab`
9. `total_liabilities`

`yahoo_definition_unverified`：

1. `net_profit`

`pdf_required`：

1. `gross_profit`

`mapping_expansion_required`：

1. `defer_tax_liab`

`source_unavailable`：

1. `bond_payable`
2. `cip`
3. `invest_income`

## 字段决策

`net_profit` 有 Yahoo 值，但仍保持 `yahoo_definition_unverified`。

原因：

```text
Yahoo net-income semantics are not yet tied to the exact Turtle net_profit row
```

需要的证明：

```text
PDF row semantics and value match for profit attributable to owners/shareholders
```

因此当前不能把 `net_profit` 提升为 `yahoo_pdf_verified` 或 clean present。

`gross_profit` 保持 `pdf_required`。

原因：

```text
formal annual-report gross-profit row semantics are not yet proven
```

需要的证明：

```text
formal PDF row or deterministic derivation matching Yahoo Gross Profit
```

因此当前不能把 `gross_profit` 提升为 clean present，也不能把它写成已被 Yahoo definition bucket 稳定接住。它的真实终态是：当前 API 路径无法证明正式年报行语义，需要 PDF row 或 deterministic derivation proof。

`defer_tax_liab` 保持 `mapping_expansion_required`。

原因：

1. provider candidate 可见；
2. AKShare candidate 已经被当前 mapping 处理，不能重复当作新覆盖；
3. Yahoo candidate 不够强，不能直接 promote。

`bond_payable`、`cip`、`invest_income` 保持 `source_unavailable`。

原因：

1. 当前 captured AKShare/Yahoo 数据没有可用候选；
2. 不引入新 provider fixture 或 PDF fallback 时，不应伪造 clean 覆盖。

## 验收标准

Phase M2 已达到的验收标准：

1. HK 15 个字段都出现在 closure report 中。
2. 每个字段都有且只有一个 closure category。
3. non-clean 字段有稳定、可 review 的 terminal reason。
4. provider replay 写出 JSON 和 Markdown closure artifact。
5. replay regression 锁定当前 exact bucket 分布。

## 验证

已运行 focused verification：

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_hk_15_field_closure.py tests/test_provider_baseline_replay.py tests/test_hk_yahoo_trust_policy.py tests/test_warning_classification.py -q
```

结果：

```text
36 passed
```

## 下一步

Phase N 仍然放在 Phase M2 之后。当前 15-field baseline 已能稳定区分：

1. clean source-first values；
2. Yahoo PDF-verified policy values；
3. Yahoo definition-unverified values；
4. PDF-required proof gaps；
5. mapping expansion cases；
6. source-unavailable cases。

后续最值得优先做的是 `net_profit` PDF row semantics proof。若能证明 Yahoo net income 与 Turtle `net_profit` 的年度报告行语义和值一致，HK clean baseline 可能从 `9/15` 推到 `10/15`。
