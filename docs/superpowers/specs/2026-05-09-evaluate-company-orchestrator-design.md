# evaluate-company Orchestrator 设计 Spec

> 日期：2026-05-09
> 状态：Draft
> 前置阶段：Phase I-A/I-A.2（LLM 抽取）、Phase N4（P2/P3 扩展）、Phase I-C/I-C.1（text-mode + whitespace 修复）
> Roadmap follow-up：§"Status (2026-05-09)" 分支收尾准备 —— 本 orchestrator 成为 catalog/source-policy/LLM-prompt 改动后的常规本地验证 + 回归 gate 命令。

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
      "source_unavailable": 12,
      "terminal_locked": 5,
      "not_in_scope": 2
    },
    "by_priority": {
      "P0": {"clean_present": 22, "total": 22},
      "P1": {"clean_present": 8,  "total": 11},
      "P2": {"clean_present": 0,  "total": 9},
      "P3": {"clean_present": 0,  "total": 14}
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
      "bucket": "terminal_locked",
      "reason": "yahoo_definition_unverified",
      "selected_source": null
    },
    ...
  }
}
```

### evaluation.md 格式

人可读总结，三个段落：
1. 头部：company / period / market / generated_at
2. 覆盖率表：priority × bucket 网格
3. 逐字段明细表（clean_present 折叠，conflict / supplement / terminal 展开）

用于人工审查与 PR review 附件。

## 桶分类（Bucket Classification）

`classify_field` 是关于 `(SourceFirstExportItem, LlmEvidenceSupplementItem | None, SourceMappingEntry, FieldTaxonomyEntry, *, pdf_provided: bool)` 的纯函数。桶互斥；级联按下表顺序匹配，第一命中胜出。

| # | Bucket | 触发条件 |
|---|--------|----------|
| 1 | `terminal_locked` | catalog `verification_status` ∈ `{"yahoo_definition_unverified", "provider_semantics_unverified"}` 或字段属于 roadmap "Locked Terminal States" 集合，定义为 `gross_profit, cip, non_oper_income, non_oper_exp, other_cur_assets`。（来源：`docs/2026-05-08-roadmap-evaluation.zh.md` §0 bucket 4；在 `company_evaluation.py` 中编码为常量 `TERMINAL_LOCKED_FIELDS` 以便溯源。） |
| 2 | `unresolved_conflict` | `export.conflict_classifications` 非空 |
| 3 | `clean_present` | `export.status == "present"` 且无 review_notes 且无 conflicts |
| 4 | `llm_supplement_present` | `export.status != "present"` 且 `supplement is not None` 且 `supplement.status == "present"` |
| 5 | `not_in_scope` | catalog `source_mode == "pdf_only"` 且 `pdf_provided is False`（连 LLM 路径都没尝试） |
| 6 | `source_unavailable` | 其他（export missing、无 provider candidate、LLM 因 source_mode 未跑或跑了未找到） |

说明：

- `not_in_scope` 与 `source_unavailable` 不同：前者表示该字段只能来自 PDF + LLM 而我们根本没有跑 LLM 步骤；后者表示已经把所有可用路径跑完都没拿到值。这一区分关键 —— 给后续 evaluate-company 加上 PDF 后，字段从 `not_in_scope` 转为 present 或 supplement 桶不是回归。
- `not_disclosed`（针对"LLM 已查阅并确认不存在"的 `source_unavailable` 严格子桶）刻意推迟到披露存在性检测可靠之后。在 Open Questions 中跟踪。

## 模块边界

### `src/financial_report_llm_extractor/structured_sources/source_inventory_fetch.py`（约 120 行）

```python
@dataclass(frozen=True)
class PeriodSpec:
    period_end: date          # 规范形式
    report_type: ReportType   # annual | half_year | quarterly | ttm

    @classmethod
    def from_year(cls, year: int) -> "PeriodSpec": ...
    @classmethod
    def from_period_end(cls, period_end: str, report_type: str = "annual") -> "PeriodSpec": ...


def fetch_source_inventory(
    *,
    company: str,
    period: PeriodSpec,
    market: Literal["CN", "HK"],
    providers: tuple[ProviderName, ...],
    akshare_client: AkShareClientProtocol | None = None,
    yahoo_client: YahooClientProtocol | None = None,
    out_dir: Path,
) -> SourceInventoryArtifact:
    """从真实（或注入的 fake）provider client live fetch。
    写 source_inventory.jsonl + source_inventory_summary.json。
    复用 real_source_validation 的 AKShareSourceAdapter / YahooSourceAdapter primitives；
    新的 sample builder 是按 (company, period) 而非 build_default_validation_samples 写死的列表。
    """
```

### `src/financial_report_llm_extractor/structured_sources/company_evaluation.py`（约 180 行）

```python
BucketName = Literal[
    "clean_present", "unresolved_conflict", "llm_supplement_present",
    "source_unavailable", "terminal_locked", "not_in_scope",
]


@dataclass(frozen=True)
class CompanyFieldEvaluation:
    field_id: str
    bucket: BucketName
    selected_source: str | None
    value: str | None
    currency: str | None
    unit: str | None
    reason: str | None  # 非 clean 桶填这里


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
    supplement_item: LlmEvidenceItem | None,
    mapping_entry: SourceMappingEntry,
    taxonomy_entry: FieldTaxonomyEntry,
    *,
    pdf_provided: bool,
) -> tuple[BucketName, str | None]: ...


def build_company_evaluation(
    *, company, period, market, export, supplement, catalog, taxonomy
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
    """Orchestrator：replay → 可选 LLM → classify → 写 artifacts。"""
```

### CLI 集成

`cli.py` 加两个 subparser（`fetch-source-inventory`、`evaluate-company`）dispatch 到上述函数。`cli.py` 不放业务逻辑。

### 复用清单（不重写）

| 现有模块 | 被谁用 |
|----------|--------|
| `AKShareSourceAdapter`、`YahooSourceAdapter`（real_source_validation.py） | source_inventory_fetch.fetch_source_inventory |
| `map_source_inventory`（mapping.py） | run_company_evaluation |
| `reconcile_mapped_fields`（reconciliation.py） | run_company_evaluation |
| `build_source_first_export`（export.py） | run_company_evaluation |
| `run_llm_extraction_for_company`（llm_extraction_runner.py） | run_company_evaluation 当 pdf_path + llm_config 设了 |
| `load_source_mapping_catalog`、`load_field_taxonomy_catalog` | 两个 subcommand |

## 测试策略

| 测试 | 类型 | 覆盖 | 默认跑 |
|------|------|------|--------|
| `test_source_inventory_fetch.py::test_fetch_with_fake_clients` | 单测 | Fake AKShare + Yahoo client 返回 canned record → 写 inventory artifact | ✅ |
| `test_source_inventory_fetch.py::test_period_spec_year_shortcut_expands` | 单测 | `PeriodSpec.from_year(2024)` → period_end=2024-12-31, report_type=annual | ✅ |
| `test_source_inventory_fetch.py::test_period_spec_rejects_both_year_and_period_end` | 单测 | CLI parser 在同设 --year 与 --period-end 时报错 | ✅ |
| `test_source_inventory_fetch.py::test_real_fetch_smoke` | 集成 | gate `REAL_SOURCE_VALIDATION=1`；fetch 一个 CN ticker | ❌ opt-in |
| `test_company_evaluation.py::test_classify_field_buckets` | 单测 | 每个桶至少一个正例 + 一个反例 | ✅ |
| `test_company_evaluation.py::test_orchestrator_with_fake_clients` | 单测 | 整套 evaluate-company 流程，FakeAkShareClient + FakeYahooClient + FakeJsonClient + canned PDF chunks | ✅ |
| `test_company_evaluation.py::test_renders_evaluation_markdown` | 单测 | 对 markdown 输出做 snapshot 风格断言 | ✅ |
| `test_company_evaluation.py::test_orchestrator_skips_llm_without_pdf` | 单测 | pdf_path=None 时仍能跑完 evaluation | ✅ |
| `test_cli.py::test_evaluate_company_subcommand_dispatches_correctly` | 单测 | CLI argv 解析 → run_company_evaluation 拿到正确参数 | ✅ |

CI gate 给默认 `pytest -v` 加 5 个单测。真 provider / 真 LLM 测试维持 env-gated opt-in。

## 实现拆分

四个独立 commit：

| Commit | 主题 | LoC | 备注 |
|--------|------|----:|------|
| 1 | `feat: source_inventory_fetch + fetch-source-inventory subcommand` | ~200 | 新模块 + CLI 接线 + 4 单测 + shell 包装 |
| 2 | `feat: company_evaluation pure-function bucket classifier + markdown` | ~250 | 新模块 + 4 单测；尚无 CLI |
| 3 | `feat: evaluate-company subcommand orchestrator + shell wrapper` | ~150 | 接 Commit 1+2；1 个 orchestrator 测 + 1 个 CLI 测 |
| 4 | `docs: 把 evaluate-company 加进 CLAUDE.md + roadmap §6 + sample run` | ~50 | 仅文档 |

每个 commit 独立绿灯：pytest + ruff + mypy。

## Open Questions / 出本分支跟踪

- 多公司批量包装（post-MVP）。可能就是 evaluate-company 调用上的薄循环。
- 与上次跑的 coverage delta（比较两个 evaluation.json）。用于"这次 catalog 改动有没有回归？"。Phase 2。
- 按 `<company>_<period>` 约定从 downloads 目录自动解析 `--pdf`。MVP 阶段 YAGNI。
- TTM 计算。PeriodSpec 已经留了 `report_type=ttm`，但实际推导逻辑（4 个季度求和）不在本次范围。
- `not_disclosed` terminal 子桶。当前归到 `source_unavailable`。Phase 2 待披露存在性检测可靠后再做。

## 验收标准

- `uv run pytest -v` 显示 ≥ 9 个新增单测通过。
- `uv run ruff check .` clean。
- `uv run mypy src tests` clean。
- 一个端到端 demo run 在 600519 / 2024 上跑通，4 个 artifact 都生成（gate 在 `REAL_SOURCE_VALIDATION=1` 与 DeepSeek API key 上）。
- `evaluation.md` 人可读且符合上文 priority × bucket 形式。
- roadmap `## 6. Validation Commands` 块列出新 CLI。
