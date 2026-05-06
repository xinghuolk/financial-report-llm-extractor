# Phase K: HK Source Metadata Proof Spec

> Date: 2026-05-06
> Status: draft for implementation planning
> Roadmap phase: Phase K, HK Currency, Unit, And Reporting Metadata Proof

## 背景

Source-first 路线已经证明 AKShare + Yahoo 对港股不是完全无字段。当前 provider baseline 中，`00001` 和 `01113` 在 15 个 minimal source mapping 字段上都能达到 `11/15` combined selected coverage，但 clean present 都只有 `4/15`。

这说明下一步主要问题不是继续扩大字段数量，而是先证明结构化 source 候选值的元数据质量。尤其是港股字段存在以下风险：

- `currency` 和 `unit` 容易混用。`HKD` 是币种证据，不是单位倍率。
- AKShare HK 行数据需要从 metadata join 证明 `report_type`、`account_standard`、`currency`。
- Yahoo/yfinance 字段通常有 currency，但没有年报页码，也没有 AKShare 式 accounting standard。
- 跨源数值出现稳定比例差异时，可能是币种/单位 metadata 错误，也可能是真实 provider 语义差异。
- 现在直接扩到 33 个 P0/P1 字段，会把这些 warning 复制到更多字段，覆盖率会变得不好解释。

## 目标

Phase K 的目标是让港股 source candidates 在进入 source policy 和 export 前具备可审查的 metadata proof。

完成后，系统应能回答：

- 这个值来自 AKShare 还是 Yahoo。
- 原始 provider 值是什么。
- 该值的币种是什么，币种证据来自哪里。
- 该值的单位倍率是什么，单位证据来自哪里。
- 是否证明了年度报告口径。
- 是否证明了 statement metadata。
- 如果仍然需要 PDF verification，原因是 metadata 缺失、FX-like ratio、语义冲突，还是单源未验证。

## 非目标

- 不扩展 minimal source mapping 到 33 字段。那是 Phase M。
- 不实现 PDF evidence supplement。Phase K 只产出是否需要 PDF verification。
- 不刷新真实 AKShare/Yahoo provider fixture，除非现有 fixture 无法支撑测试。
- 不做隐式 FX conversion。
- 不把 source data promote 为 canonical facts。

## 设计决策

### 1. 保持 source-first 合同小步演进

当前 `SourceInventoryRecord` 已包含：

- `currency`
- `unit`
- `report_type`
- `account_standard`
- `source_evidence`

当前 `TurtleMappingCandidate` 已包含：

- `canonical_unit`
- `statement_metadata_proven`
- `errors`

Phase K 不先引入大型 metadata 子模型。优先复用这些字段，并加强生成、读取、映射和 policy 判断。只有当实现中发现 `unit` 无法表达 multiplier proof 时，再增加最小字段，例如 `unit_multiplier` 或独立 proof artifact。

### 2. `currency` 与 `unit` 语义必须分离

规则：

- `currency` 只能是 `CNY`、`HKD`、`USD`、`unknown`、`ambiguous`。
- `unit` 表示 source value 的倍率语义，例如 `raw`、`yuan`、`thousand`、`million`。
- `HKD`、`CNY`、`USD` 不应作为港股 source row 的 clean unit proof。
- 如果历史 captured fixture 中存在 `unit == currency`，replay 层必须把它标成 metadata issue，不能静默算 clean present。

### 3. 港股 metadata proof 分 source 处理

AKShare HK clean proof 要求：

- `currency` 已知。
- `unit` 已知且不是 currency label。
- `report_type` 证明为 annual。
- `account_standard` 存在，或 policy 明确允许缺失但保留 warning。
- source evidence 指向 AKShare raw artifact。

Yahoo HK clean proof 要求：

- `currency` 已知。
- `unit` 已知且不是 currency label。
- `report_type` 为 annual，或 yfinance annual statement frame 被 adapter 明确标记为 annual。
- source evidence 指向 Yahoo raw artifact。
- 不要求 `account_standard`，但如果跨源冲突存在，仍可能需要 PDF verification。

### 4. Source policy 继续负责选择与阻断

Phase K 不让 adapter 决定最终字段是否 present。Adapter 只负责写出尽可能准确的 source metadata。

Source policy 负责：

- `currency_metadata_required`
- `metadata_currency_suspected`
- `fx_like_ratio`
- `semantic_mismatch`
- `single_source_unverified`
- selected primary with warning
- unresolved conflict

Phase K 要让这些分类更准确，避免把 metadata-only 问题和真实 semantic conflict 混在一起。

## 组件影响

主要修改文件：

- `src/financial_report_llm_extractor/structured_sources/akshare_adapter.py`
- `src/financial_report_llm_extractor/structured_sources/yahoo_adapter.py`
- `src/financial_report_llm_extractor/structured_sources/mapping.py`
- `src/financial_report_llm_extractor/structured_sources/source_policy.py`
- `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`
- `src/financial_report_llm_extractor/structured_sources/artifacts.py`

主要测试文件：

- `tests/test_akshare_adapter.py`
- `tests/test_yahoo_adapter.py`
- `tests/test_source_mapping.py`
- `tests/test_source_policy.py`
- `tests/test_provider_baseline_replay.py`
- `tests/test_source_artifacts.py`

如果实现需要新增 helper，优先新增：

- `src/financial_report_llm_extractor/structured_sources/metadata_proof.py`
- `tests/test_metadata_proof.py`

## 输出要求

Provider baseline replay summary 应继续输出：

- selected coverage
- clean present coverage
- selected with warnings
- fields requiring PDF evidence
- source policy report paths

Phase K 需要额外保证：

- `source_policy_report.json` 中 selected candidate 的 metadata proof 可审查。
- clean present 不包含 `unit == currency` 的 HK money fields。
- HK metadata warning 的原因可读，至少区分 missing metadata、currency-as-unit、FX-like ratio、semantic conflict。

## 验收标准

- AKShare HK adapter tests 使用 `unit="raw"` 或等价倍率语义，不再把 `HKD` 当作 unit。
- Yahoo HK metadata proof 可以在没有 `account_standard` 时仍表达 annual + currency + raw-unit proof。
- Mapping tests 覆盖 `statement_metadata_proven` 的 AKShare HK 和 Yahoo HK 场景。
- Source policy tests 覆盖：
  - HK primary candidate metadata proof 通过。
  - HK primary candidate `unit == currency` 时不能 clean present。
  - HK FX-like ratio 且 metadata proof 不足时保持 PDF verification required。
- Provider baseline replay 对 `00001`、`01113` 的 summary 仍能生成，并保留 clean present 与 selected-with-warning 的区分。

## 后续衔接

Phase K 完成后进入 Phase L：

- 对 `00001` 和 `01113` 当前 15 字段 warning 做分类。
- 将 warning 分成 source policy 可解决、必须 PDF verification、mapping expansion required、source unavailable。

Phase L 完成后再进入 Phase M：

- 把 minimal source mapping 从 15 扩到完整 P0/P1 33 字段。
