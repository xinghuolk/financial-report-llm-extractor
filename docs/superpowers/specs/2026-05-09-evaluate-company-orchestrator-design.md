# evaluate-company Orchestrator 设计 Spec

> 日期：2026-05-09
> 状态：Draft (revised after Review Round 1)
> 前置阶段：Phase I-A/I-A.2（LLM 抽取）、Phase N4（P2/P3 扩展）、Phase I-C/I-C.1（text-mode + whitespace 修复）
> Roadmap follow-up：§"Status (2026-05-09)" 分支收尾准备 —— 本 orchestrator 成为 catalog/source-policy/LLM-prompt 改动后的常规本地验证 + 回归 gate 命令。

## Review Round 1: 修订记录

第一轮独立 review 发现 7 条 correctness 问题（全部 verified true），关键修订：

1. **Reuse list 名字错误**：`AKShareSourceAdapter`/`YahooSourceAdapter`/`run_llm_extraction_for_company`/`load_field_taxonomy_catalog` 都不存在。实际 API 见下文 §"复用清单"。
2. **少了 `build_source_policy_report`**：没有它，`SourceFirstExportItem.{conflict_classifications, review_notes, selected_source}` 全是 `()/None`，bucket 级联 #2 #3 永远不触发。
3. **Bucket 1 `verification_status` 取值不存在**：catalog 实际枚举只有 `verified/expected/unknown`；`yahoo_definition_unverified` 等是 **`warning_classification`** 的 `WarningCategory`，不是 catalog 字段。
4. **Bucket 1 用 `TERMINAL_LOCKED_FIELDS` 全局集合会错杀 CN clean 字段**：`gross_profit` CN 段 `primary_route=akshare_direct, on_conflict=preserve_conflict, single_source_requires_pdf=false`，可正常 clean；不能因为它在某个全局列表里就一刀切打成终态。
5. **`--period-end` 没有过滤实现**：现有 `_select_latest_annual_records` 只取 latest，不接外部 period 参数。需新增 period selector。
6. **与 `provider_baseline_replay._write_slice` 大量重叠**：`_write_slice` 已经做 map → policy_report → export → llm merge → warning_classification → coverage。新 orchestrator 应**在 `_write_slice` 之上**而非平行重写。
7. **"X/N clean" 度量违反 drift §177**：`summary.by_priority.{P0:{clean_present:22,total:22}}` 字面是 drift 警告的 metric。改成多桶并列计数，不立 "% clean" 主指标。

修订要点：
- Bucket 桶映射改为基于 `WarningCategory` 派生（不再 hardcode 字段集合）
- `run_company_evaluation` 内核改为调用从 `provider_baseline_replay._write_slice` 提取出的 public function
- 删除 "by_priority.{clean_present:N, total:N}" 形式，改为 `by_priority.<P>.<bucket>:N` 全分布
- LoC 估算上调
- 新增测试：policy_report wiring、period filter actually filtering、Bucket 4 不误升 LLM supplement

## 目标

一个可复用、env 或 args 驱动的验证模块，输入单个 (company, period)，产出完整可审 artifact 包：provider source-first export、可选 LLM PDF supplement、带 bucket 分类与覆盖率统计的 evaluation 结果。成为 catalog / source-policy / LLM prompt 改动后的常规回归验证。

## Non-Goals

- 多公司批量（`extract-llm-batch` 已覆盖 LLM 批量场景）。未来批量包装可在 evaluate-company 之上写循环。
- 新的 retrieval / chunking / mapping / reconciliation 逻辑。orchestrator 只串联现有模块。
- 新的 provider adapter 或新的字段语义证明。复用现有 `AKShareSourceAdapter`、`YahooSourceAdapter`、`provider_baseline_replay`、`extract-llm`。
- 实时监控或定时调度。
- 持久化运行历史 / 数据库。每次运行是 `tmp/runs/<company>_<period_end>/` 下自包含的目录。

## 架构总览

两步式 CLI 把网络调用与确定性求值分开：

```
fetch-source-inventory     →   live AKShare/Yahoo fetch       →   tmp/runs/<id>/source_inventory.jsonl
                                                                    + source_inventory_summary.json

evaluate-company           →   replay + (可选) LLM             →   tmp/runs/<id>/source_first_export.json
  读取 source_inventory                                            + llm_evidence_supplement.json (设了 PDF 才有)
                                                                   + evaluation.json
                                                                   + evaluation.md
```

每一步可独立调用。Step 1 联网，opt-in。Step 2 完全确定性，CI 友好。

## CLI 接口

### Subcommand `fetch-source-inventory`

```
uv run financial-report-llm-extractor fetch-source-inventory \
  --company 600519 \
  --period-end 2024-12-31 \
  --market CN \
  --providers akshare,yahoo \
  --out tmp/runs/600519_2024-12-31/
```

可选 shortcut：`--year 2024` 展开为 `--period-end 2024-12-31 --report-type annual`。`--year` 与 `--period-end` 互斥；同设报错。

### Subcommand `evaluate-company`

```
uv run financial-report-llm-extractor evaluate-company \
  --company 600519 \
  --period-end 2024-12-31 \
  --market CN \
  --inventory tmp/runs/600519_2024-12-31/source_inventory.jsonl \
  --inventory-summary tmp/runs/600519_2024-12-31/source_inventory_summary.json \
  --catalog field_catalog/turtle_v015_source_mapping_minimal.json \
  --taxonomy field_catalog/turtle_v015_field_taxonomy.json \
  --pdf downloads/cn_stocks/600519/annual/2024_年度报告.pdf \
  --llm-config tmp/llm_configs/deepseek.json \
  --priorities P0,P1,P2,P3 \
  --out tmp/runs/600519_2024-12-31/
```

LLM 步骤仅当 `--pdf` 与 `--llm-config` 同时设置时执行；否则跳过。无论本次是否生成，orchestrator 在构造 source-first export 时都会 merge 当前 out 目录下任何已存在的 `llm_evidence_supplement.json`（用户也可以独立先跑 `extract-llm` 再来 evaluate）。

### Shell 包装

```bash
# scripts/run-fetch-source-inventory.sh
COMPANY=600519 PERIOD_END=2024-12-31 MARKET=CN \
  PROVIDERS=akshare,yahoo \
  scripts/run-fetch-source-inventory.sh
```

```bash
# scripts/run-evaluate-company.sh
COMPANY=600519 PERIOD_END=2024-12-31 MARKET=CN \
  PDF_PATH=downloads/cn_stocks/600519/annual/2024_年度报告.pdf \
  LLM_CONFIG=tmp/llm_configs/deepseek.json \
  scripts/run-evaluate-company.sh
```

`YEAR=2024` 在两个 wrapper 都可作 shortcut（与 `PERIOD_END` 互斥）。

未设时的默认值：
- `MARKET`：从 ticker 模式推断（`6\d{5}` / `[03]\d{5}` → CN，`\d{4,5}` → HK 加 `.HK` 后缀）；无法判定时报错。
- `PROVIDERS`：`akshare,yahoo`。
- `REPORT_TYPE`：`annual`。
- `OUT_DIR`：`tmp/runs/${COMPANY}_${PERIOD_END}/`。
- `CATALOG`：`field_catalog/turtle_v015_source_mapping_minimal.json`。
- `TAXONOMY`：`field_catalog/turtle_v015_field_taxonomy.json`。
- `PRIORITIES`：`P0,P1,P2,P3`。

## 输出 Artifacts

```
tmp/runs/<COMPANY>_<PERIOD_END>/
├── source_inventory.jsonl                    # fetch-source-inventory 写
├── source_inventory_summary.json             # fetch-source-inventory 写
├── source_first_export.json                  # evaluate-company 写
├── llm_evidence_supplement.json              # evaluate-company 写（PDF + llm-config 设了才有）
├── evaluation.json                           # evaluate-company 写
└── evaluation.md                             # evaluate-company 写
```

### evaluation.json schema

```json
{
  "schema_version": "company-evaluation-v1",
  "company": "600519",
  "period_end": "2024-12-31",
  "report_type": "annual",
  "market": "CN",
  "generated_at": "2026-05-09T...",
  "summary": {
    "total_fields": 56,
    "by_bucket": {
      "clean_present": 30,
      "unresolved_conflict": 3,
      "llm_supplement_present": 4,
      "terminal_unverified": 5,
      "not_in_scope": 2,
      "source_unavailable": 12
    },
    "by_priority": {
      "P0": {"clean_present": 22, "unresolved_conflict": 0, "llm_supplement_present": 0, "terminal_unverified": 0, "not_in_scope": 0, "source_unavailable": 0},
      "P1": {"clean_present": 8,  "unresolved_conflict": 1, "llm_supplement_present": 0, "terminal_unverified": 1, "not_in_scope": 0, "source_unavailable": 1},
      "P2": {"clean_present": 0,  "unresolved_conflict": 1, "llm_supplement_present": 1, "terminal_unverified": 2, "not_in_scope": 0, "source_unavailable": 5},
      "P3": {"clean_present": 0,  "unresolved_conflict": 1, "llm_supplement_present": 3, "terminal_unverified": 2, "not_in_scope": 2, "source_unavailable": 6}
    }
  },
  "fields": {
    "revenue": {
      "bucket": "clean_present",
      "selected_source": "akshare",
      "value": "168838700000",
      "currency": "CNY",
      "unit": "raw"
    },
    "gross_profit": {
      "bucket": "terminal_unverified",
      "reason": "yahoo_definition_unverified",
      "selected_source": null
    },
    ...
  }
}
```

`by_priority` 显示**完整 6 桶分布**，刻意不计算 "% clean" 主指标 —— 与 drift §177 一致。

### evaluation.md 格式

人可读总结，三个段落：
1. 头部：company / period / market / generated_at
2. 覆盖率表：priority × bucket 网格
3. 逐字段明细表（clean_present 折叠，conflict / supplement / terminal 展开）

用于人工审查与 PR review 附件。

## 桶分类（Bucket Classification）

桶分类**不再独立实现**，而是基于现有 `WarningClassificationResult.items[field_id].category`（`warning_classification.py:23-32`）派生。WarningCategory 已枚举 7 类终态：`yahoo_pdf_verified, yahoo_definition_unverified, pdf_required, source_policy_resolvable, pdf_verification_required, mapping_expansion_required, source_unavailable`。

`classify_field` 是关于 `(SourceFirstExportItem, WarningClassificationItem | None, LlmEvidenceItem | None, SourceMappingEntry, *, pdf_provided: bool)` 的纯函数。桶互斥；级联按下表顺序匹配，第一命中胜出。

| # | Bucket | 触发条件 |
|---|--------|----------|
| 1 | `unresolved_conflict` | `export.conflict_classifications` 非空 |
| 2 | `clean_present` | `export.status == "present"` 且 `warning_item is None` 且 `selected_source != "llm"` |
| 3 | `llm_supplement_present` | `selected_source == "llm"` AND `export.status == "present"`（即 supplement merge 已发生） |
| 4 | `terminal_unverified` | `warning_item.category` ∈ `{"yahoo_definition_unverified", "pdf_required", "pdf_verification_required", "mapping_expansion_required"}` —— 该 (公司, 字段, 市场) 在当前架构下确已锁定为非 clean 终态 |
| 5 | `not_in_scope` | catalog `source_mode == "pdf_only"` 且 `pdf_provided is False`（连 LLM 路径都没尝试） |
| 6 | `source_unavailable` | 其他（warning category 是 `source_unavailable`，或 export.status=missing 且无对应 warning） |

设计要点：

- **桶是 per-(公司, 字段, 市场) 派生**，不是全局集合。CN `gross_profit` 因 `primary_route=akshare_direct` 落到 `clean_present`（合理）；HK `gross_profit` 因 yahoo 语义未证 落到 `terminal_unverified`。这正是修订前 review 指出的"全局列表会错杀 CN clean 字段"。
- **`source_policy_resolvable` 不另起桶**：该 category 表示 source policy 已能解决，事实上 export 会成为 clean_present 或 unresolved_conflict 之一，已被前面级联覆盖。
- **`yahoo_pdf_verified` 不另起桶**：该 category 表示 trust policy 通过且字段 clean，落入 `clean_present`。
- `not_in_scope` 与 `source_unavailable` 不同：前者表示该字段只能来自 PDF + LLM 而我们根本没有跑 LLM 步骤；后者表示已经把所有可用路径跑完都没拿到值。后续 evaluate-company 给 PDF 后字段从 `not_in_scope` 转为 present 或 supplement 桶不是回归。
- `not_disclosed`（针对"LLM 已查阅并确认不存在"的 `source_unavailable` 严格子桶）刻意推迟到披露存在性检测可靠之后。在 Open Questions 中跟踪。

### Bucket 4 的 LLM supplement 守卫

修订前 review 指出 Bucket 4（原 `llm_supplement_present`）会让 `pdf_only` 字段在没有 provider 语义证明的情况下，从 supplement 直接看起来像 verified。本次修订把 `selected_source == "llm"` 显式写进 Bucket 3 触发条件，并保留 `evaluation.json.fields[<id>]` 输出的 `selected_source: "llm"` 字段，markdown 渲染必须高亮这一来源（"LLM-only, no provider semantics proof"）。

## 模块边界

### Refactor 0：把 `_write_slice` 提为公开函数

`provider_baseline_replay._write_slice`（lines 306-433）现为私有，本次将其重命名为 `evaluate_source_first_slice` 并提为公开 API（保留所有现有调用点行为）。新 orchestrator 直接调用之，避免业务逻辑双份维护（drift §"Material overlap" 警告）。

### `src/financial_report_llm_extractor/structured_sources/source_inventory_fetch.py`（约 280 行）

```python
@dataclass(frozen=True)
class PeriodSpec:
    period_end: date          # 规范形式
    report_type: ReportType   # annual | half_year | quarterly | ttm

    @classmethod
    def from_year(cls, year: int) -> "PeriodSpec":
        return cls(period_end=date(year, 12, 31), report_type="annual")

    @classmethod
    def from_period_end(cls, period_end: str, report_type: str = "annual") -> "PeriodSpec":
        ...


def select_records_for_period(
    records: tuple[SourceInventoryRecord, ...],
    period: PeriodSpec,
) -> tuple[SourceInventoryRecord, ...]:
    """新增：按 PeriodSpec.period_end 过滤记录。
    现有 `_select_latest_annual_records` 不接外部 period，本函数补充。
    fail-loud：如果记录中没有匹配 period 的 present 记录，raise 而非 silently 返回 latest。
    """


def fetch_source_inventory(
    *,
    company: str,
    period: PeriodSpec,
    market: Literal["CN", "HK"],
    providers: tuple[ProviderName, ...],
    akshare_client: AkshareLikeClient | None = None,   # Protocol from real_source_validation:59
    yahoo_client: YahooLikeClient | None = None,       # Protocol from real_source_validation:93
    out_dir: Path,
) -> SourceInventoryArtifact:
    """从 provider client live fetch。
    内部按 (company, period, market) 构造 RealSourceValidationSample（替代 build_default_validation_samples 的写死列表），
    沿用 real_source_validation._fetch_sample_records 调用 AkshareAdapter / YahooAdapter（akshare_adapter.py / yahoo_adapter.py），
    用 select_records_for_period 过滤到指定 period。
    写 source_inventory.jsonl + source_inventory_summary.json + provider_field_inventory_summary.json（与 replay-provider-baseline 兼容）。
    """
```

### `src/financial_report_llm_extractor/structured_sources/company_evaluation.py`（约 220 行）

```python
BucketName = Literal[
    "clean_present", "unresolved_conflict", "llm_supplement_present",
    "terminal_unverified", "not_in_scope", "source_unavailable",
]


@dataclass(frozen=True)
class CompanyFieldEvaluation:
    field_id: str
    bucket: BucketName
    selected_source: str | None
    value: str | None
    currency: str | None
    unit: str | None
    reason: str | None  # 非 clean 桶填这里（warning category 或解释）


@dataclass(frozen=True)
class CompanyEvaluation:
    company: str
    period: PeriodSpec
    market: str
    generated_at: str
    fields: tuple[CompanyFieldEvaluation, ...]
    by_bucket: Mapping[BucketName, int]
    by_priority: Mapping[str, Mapping[BucketName, int]]


def classify_field(
    export_item: SourceFirstExportItem,
    warning_item: WarningClassificationItem | None,
    supplement_item: LlmEvidenceItem | None,
    mapping_entry: SourceMappingEntry,
    *,
    pdf_provided: bool,
) -> tuple[BucketName, str | None]:
    """纯函数桶映射，见 §"桶分类" 级联表。"""


def build_company_evaluation(
    *, company, period, market,
    export: SourceFirstExportResult,
    warning_classification: WarningClassificationResult,
    supplement: dict[str, LlmEvidenceItem] | None,
    catalog: SourceMappingCatalog,
    taxonomy: FieldTaxonomyCatalog,
) -> CompanyEvaluation: ...


def render_evaluation_markdown(evaluation: CompanyEvaluation) -> str: ...


def run_company_evaluation(
    *,
    company, period, market,
    inventory_path, inventory_summary_path,
    catalog_path, taxonomy_path,
    pdf_path: Path | None,
    llm_config_path: Path | None,
    priorities: tuple[str, ...],
    out_dir: Path,
    json_client: JsonClient | None = None,
) -> CompanyEvaluation:
    """Orchestrator：
    1. 读 source_inventory + summary
    2. （可选 PDF + llm-config）走 _process_one_company 风格 ingest+chunk+extract+write llm_evidence_supplement
    3. 调 evaluate_source_first_slice（提为 public 的 _write_slice）→ 拿到 export + warning_classification（已含 supplement merge）
    4. build_company_evaluation → 写 evaluation.json + evaluation.md
    """
```

### CLI 集成

`cli.py` 加两个 subparser（`fetch-source-inventory`、`evaluate-company`）dispatch 到上述函数。`cli.py` 不放业务逻辑。

### 复用清单（不重写，**已 verified**）

| 现有模块/函数 | 实际位置 | 被谁用 |
|----------|--------|--------|
| `AkshareLikeClient` / `YahooLikeClient` (Protocol) | `real_source_validation.py:59, :93` | `fetch_source_inventory` 注入点 |
| `PandasAkshareClient` / `YFinanceStatementClient` | `real_source_validation.py:301, :358` | live mode 默认实例 |
| `AkshareAdapter` / `YahooAdapter` | `akshare_adapter.py` / `yahoo_adapter.py` | 由 `_fetch_sample_records` 内部使用 |
| `_fetch_sample_records` | `real_source_validation.py:265-298` | `fetch_source_inventory` 调度 |
| `_select_latest_annual_records` | `real_source_validation.py:432` | 仍被 default sample-set 用，本次不动 |
| `evaluate_source_first_slice`（即原 `_write_slice`） | `provider_baseline_replay.py:306-433` (本次提为 public) | `run_company_evaluation` 内核 |
| `map_source_inventory` | `mapping.py` | 经由 `_write_slice` 间接调用 |
| `reconcile_mapped_fields` | `reconciliation.py` | 同上 |
| `build_source_policy_report` | `source_policy.py` | **同上 —— 关键：没有它则 conflict_classifications 为空** |
| `build_source_first_export` | `export.py:213` | 同上 |
| `_merge_llm_evidence_supplement` | `provider_baseline_replay.py` | 同上 |
| `build_warning_classification` | `warning_classification.py:110` | 同上；为新桶分类提供分类源 |
| `derive_targets`, `select_chunks`, `extract_for_chunks`, `write_llm_evidence_supplement` | `llm_extraction_runner.py:58, :94, :171, :292` | LLM step（需配 `ingest_pdf` + `build_chunk_store` + `load_chunks_jsonl`，参见 `llm_extraction_batch._process_one_company:60-85`） |
| `load_field_taxonomy` | `field_metadata.py:250` | 两个 subcommand |
| `load_source_mapping_catalog` | `structured_sources/catalog.py` | 两个 subcommand |

## 测试策略

| 测试 | 类型 | 覆盖 | 默认跑 |
|------|------|------|--------|
| `test_source_inventory_fetch.py::test_fetch_with_fake_clients` | 单测 | Fake AkshareLike + YahooLike client 返回 canned record → 写 inventory artifact | ✅ |
| `test_source_inventory_fetch.py::test_period_spec_year_shortcut_expands` | 单测 | `PeriodSpec.from_year(2024)` → period_end=2024-12-31, report_type=annual | ✅ |
| `test_source_inventory_fetch.py::test_period_spec_rejects_both_year_and_period_end` | 单测 | CLI parser 在同设 --year 与 --period-end 时报错 | ✅ |
| `test_source_inventory_fetch.py::test_select_records_for_period_filters_correctly` | 单测 | **新增**：records 含 2023/2024 两期，给 PeriodSpec(2024-12-31)，只返回 2024 记录 | ✅ |
| `test_source_inventory_fetch.py::test_select_records_for_period_raises_on_missing` | 单测 | **新增**：records 不含目标 period 时 fail-loud（不 fall back to latest） | ✅ |
| `test_source_inventory_fetch.py::test_real_fetch_smoke` | 集成 | gate `REAL_SOURCE_VALIDATION=1`；fetch 一个 CN ticker | ❌ opt-in |
| `test_company_evaluation.py::test_classify_field_buckets` | 单测 | 每个桶至少一个正例 + 一个反例 | ✅ |
| `test_company_evaluation.py::test_classify_cn_gross_profit_clean_not_terminal` | 单测 | **新增**：CN gross_profit 走 akshare_direct clean → 必须是 `clean_present`，不是 `terminal_unverified`（直接对应 review §"全局列表会错杀"） | ✅ |
| `test_company_evaluation.py::test_orchestrator_wires_policy_report` | 单测 | **新增**：构造一个 AKShare↔Yahoo 冲突的 inventory，确认 evaluation.json 中字段进入 `unresolved_conflict` 而非 `clean_present`（直接对应 review §4 "少了 build_source_policy_report"） | ✅ |
| `test_company_evaluation.py::test_orchestrator_with_fake_clients` | 单测 | 整套 evaluate-company 流程，Fake clients + FakeJsonClient + canned PDF chunks | ✅ |
| `test_company_evaluation.py::test_orchestrator_llm_supplement_marks_selected_source_llm` | 单测 | **新增**：supplement 引入的字段桶为 `llm_supplement_present`，`selected_source == "llm"`，markdown 高亮（直接对应 review Bucket 4 守卫） | ✅ |
| `test_company_evaluation.py::test_renders_evaluation_markdown` | 单测 | 对 markdown 输出做 snapshot 风格断言 | ✅ |
| `test_company_evaluation.py::test_orchestrator_skips_llm_without_pdf` | 单测 | pdf_path=None 时仍能跑完 evaluation | ✅ |
| `test_cli.py::test_evaluate_company_subcommand_dispatches_correctly` | 单测 | CLI argv 解析 → run_company_evaluation 拿到正确参数 | ✅ |

CI gate 给默认 `pytest -v` 加 ≥ 11 个单测。真 provider / 真 LLM 测试维持 env-gated opt-in。

## 实现拆分

五个独立 commit（修订后增加 Refactor 0）：

| Commit | 主题 | LoC | 备注 |
|--------|------|----:|------|
| 0 | `refactor: 把 _write_slice 提为公开 evaluate_source_first_slice` | ~30 | 重命名 + 更新现有 3 处 caller + 1 个回归测保证 replay-provider-baseline 行为不变 |
| 1 | `feat: source_inventory_fetch + fetch-source-inventory subcommand` | ~280 | 新模块（含 `select_records_for_period` fail-loud filter）+ CLI 接线 + 6 单测 + shell 包装 |
| 2 | `feat: company_evaluation pure-function bucket classifier + markdown` | ~220 | 新模块 + 5 单测；尚无 CLI；桶分类基于 `WarningClassificationItem.category` 派生 |
| 3 | `feat: evaluate-company subcommand orchestrator + shell wrapper` | ~300 | 接 Commit 0+1+2，含 PDF→chunks→LLM→supplement 流水（参考 `_process_one_company`）；1 个 orchestrator 测 + 1 个 CLI 测 |
| 4 | `docs: 把 evaluate-company 加进 CLAUDE.md + roadmap §6 + sample run + 与 replay-provider-baseline 区分说明` | ~80 | 仅文档；明确 `evaluate-company` vs `replay-provider-baseline` 的使用边界（前者 per-(company, period) live or fixture，后者 multi-company batch from captured fixture） |

每个 commit 独立绿灯：pytest + ruff + mypy。

## Open Questions / 出本分支跟踪

- 多公司批量包装（post-MVP）。可能就是 evaluate-company 调用上的薄循环。
- 与上次跑的 coverage delta（比较两个 evaluation.json）。用于"这次 catalog 改动有没有回归？"。Phase 2。
- 按 `<company>_<period>` 约定从 downloads 目录自动解析 `--pdf`。MVP 阶段 YAGNI。
- TTM 计算。PeriodSpec 已经留了 `report_type=ttm`，但实际推导逻辑（4 个季度求和）不在本次范围。
- `not_disclosed` terminal 子桶。当前归到 `source_unavailable`。Phase 2 待披露存在性检测可靠后再做。

## 验收标准

- `uv run pytest -v` 显示 ≥ 11 个新增单测通过（含 review 修订项关键测试）。
- `uv run ruff check .` clean。
- `uv run mypy src tests` clean。
- `replay-provider-baseline` 行为不变（Refactor 0 的回归测保证）。
- 一个端到端 demo run 在 600519 / 2024 上跑通，4 个 artifact 都生成（gate 在 `REAL_SOURCE_VALIDATION=1` 与 DeepSeek API key 上）。
- `evaluation.md` 人可读且符合上文 priority × bucket 形式（不含 "% clean" 主指标）。
- 600519 CN `gross_profit` 在 evaluation.json 中桶为 `clean_present`（不是 `terminal_unverified`）—— 验证 Bucket 分类不再误升 CN 字段。
- roadmap `## 6. Validation Commands` 块列出新 CLI 及与 `replay-provider-baseline` 的边界说明。
