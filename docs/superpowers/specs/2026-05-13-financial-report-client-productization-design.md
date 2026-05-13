# FinancialReportClient 产品化设计 Spec

> 日期：2026-05-13（rev 4）
> 状态：Approved for implementation pending R5 prerequisite (R1 schema market-scoping)
> 背景：Turtle v0.15 phase3 68 mapped 字段已覆盖下游四因子分析所需 catalog 层数据。Phase R 已 ship 二级缓存（R1 SQLite DB + R2 provider cache + R3 LLM cache + R4 pipeline 编排），下游 `TradingAgents-CN` 需要一个稳定、可编程、不会泄露 extractor 内部实现的消费接口。

## 目标

将 `financial-report-llm-extractor` 产品化为一个可被 `TradingAgents-CN` 直接 import 的 Python library。下游只依赖公开的 `FinancialReportClient` API contract，不读取 extractor 内部 SQLite、cache、CLI 输出目录或中间 artifact。

核心目标：

- 对下游暴露纯 Python dataclass interface。
- 将 source-first bucket 语义翻译为 Pythonic reliability/confidence 语义。
- 继续保持 extractor 的 source-first guardrails：不做 canonical fact promotion，不把 LLM supplement 当 provider verified fact。
- **复用 Phase R 已有的 R1 DB query + R4 pipeline 内核**作为唯一 backend，不再造 ArtifactBackend 这种读 `tmp/runs/*.json` 的回退路径。
- 让 `TradingAgents-CN` 可以用 `FieldValue.is_reliable` 进行 Owner Earnings、FCF、ratio 等下游计算。

## Non-Goals

- 不把 extractor 的 SQLite schema 暴露给下游。
- 不要求 `TradingAgents-CN` 读 JSON 文件、拼 CLI 命令或理解 `tmp/runs` 路径约定。
- 不在 Phase 1 做 HTTP sidecar、job queue、多 process worker 或 auth。
- 不让 runtime 依赖 Codex/Claude skill。skill 仅作为 operator 触发 pipeline 与 audit artifact 的辅助入口。
- 不在 extractor 内部计算 Owner Earnings、FCF、payout ratio、估值 ratio 或 Turtle Agent 四因子结论；这些属于 `TradingAgents-CN` / `financial-report-analysis` 下游逻辑。

## 前置 Blocker（须在动工前 close）

### R5 prerequisite — R1 schema market-scoping

**当前 R1 `field_values` PK = `(company, period_end, field_id)` 不含 `market`**。`db_query.query_extraction()` 只 filter (company, period_end)，忽略 market（`db_query.py:53`）。R4 `pipeline` 命令在 dispatch 层手工校验 `hit.get("market") == args.market`（commit `6d195c5`）作为 patch，但 **client API 会直接调 `query_extraction()`**——同一 race 复现：

- 同 ticker 跨市场（如 CN A-share + HK ADR 映射到同一 ticker）会拿错 market 的字段
- 第二次跨市场 `index_run` 的 `DELETE WHERE company=? AND period_end=?` 会 wipe 前一次的 field_values

**Client API spec 要求 `market` 必选**（见下文 §Client Methods）。所以 Phase 1a 启动前必须先做 **R5: R1 schema market-scoping**：

1. `field_values` schema v2: PK 加入 `market`，新增 `idx_field_values_market`
2. `query_extraction()` / `query_field()` API 新增 `market` 必选参数
3. `index_run()` 写入时填充 `market` 列
4. CLI `query` 命令 `--market` flag 改为 required
5. `init_db()` 检测旧 schema → drop + recreate（接受重 index 成本；R1 设计原则"tmp/runs 是 source of truth"允许此操作）
6. Regression test：同 (company, period_end) 不同 market 共存不互覆盖

详细实施方案见独立 R5 brainstorm（暂不写 plan 文档，brainstorm 在 PR description 中）。**R5 effort: ~半天**。

### Python 版本对齐

`pyproject.toml` 已声明 `requires-python = ">=3.11"`。**Phase 1a 启动前必须确认 `TradingAgents-CN` 运行环境同样支持 Python 3.11+。** 如果其当前固定在 3.10，三个选项：

| 选项 | 含义 | 推荐度 |
|---|---|---|
| A. 升级 TradingAgents-CN 至 3.11 | 同环境 in-process import，最简单 | ✓ 推荐 |
| B. 降 extractor 到 3.10 兼容 | 放弃 PEP 654/673 等 3.11 特性 | 退而求其次 |
| C. subprocess backend | 跨 Python 版本隔离，但失去 in-process 优势，且 `pdf_resolver` Callable 无法跨进程传递（必须改为预解析的 `pdf_path: Path \| None` 参数） | 最后手段 |

**默认 spec 假设选项 A**。其他路径触发 spec 重新审视。

## 边界

```
TradingAgents-CN
  - own DB
  - own Owner Earnings / FCF / ratios / derived metrics
  - own analysis logic
  - imports financial-report-llm-extractor as a library
        |
        | FinancialReportClient API contract
        v
financial-report-llm-extractor
  PUBLIC:
    src/financial_report_llm_extractor/client.py
      FinancialReportClient
      ExtractorConfig
      ExtractionResult
      FieldValue
      ConfidenceLevel
      RefreshPolicy
      Staleness
      PdfQuery
      ExtractorError

  INTERNAL (downstream 永远不接触):
    data/extracted.db                              (R1)
    tmp/.cache/                                    (R2 + R3)
    pipeline / fetch-source-inventory / evaluate-company CLI
    evaluation.json / extraction_result.json / llm_evidence_supplement.json
```

## 打包分发

### 包结构 + catalog 文件分发

`field_catalog/*.json` 当前在 repo root，**不在** `src/` 下。Phase 1a 必须把 catalog files 打包进 wheel：

```toml
# pyproject.toml — 添加：
[tool.hatch.build.targets.wheel.force-include]
"field_catalog" = "financial_report_llm_extractor/_catalog_data"
```

打包后，catalog 通过 `importlib.resources` 加载，**不依赖 CWD**：

```python
from importlib.resources import files

_CATALOG_ROOT = files("financial_report_llm_extractor") / "_catalog_data"
DEFAULT_CATALOG_PATH = _CATALOG_ROOT / "turtle_v015_source_mapping_minimal.json"
DEFAULT_TAXONOMY_PATH = _CATALOG_ROOT / "turtle_v015_field_taxonomy.json"
```

Phase 1a 启动时验证：`pip install -e .` 后从其它目录 `python -c "from financial_report_llm_extractor.client import FinancialReportClient; c=FinancialReportClient()"` 能正确解析 catalog 路径。

### 安装路径

Phase 1a：**`pip install -e ../financial-report-llm-extractor`**（editable local install）。`TradingAgents-CN` 的 requirements 文件加这一行 + `requires-python = ">=3.11"`。

Phase 2+：考虑 PyPI 发布。当前不在 scope。

### catalog_version ↔ package version 关系

`taxonomy.version` 字段（e.g. `"2026-05-02"`）独立于 Python package version。两者解耦的好处：catalog 升级（new fields, new aliases）不一定触发 minor/patch bump；反之 client API 改动也不需要碰 catalog version。下游用 `client.catalog_version()` 而非 `extractor.__version__` 作 derived-data invalidation key。

## 内部 Backend 架构

**不引入 ArtifactBackend**。Phase R 已经把数据通路做完了；client 只是上层 façade：

```
FinancialReportClient.get_extraction(company, period_end, market, ...)
    ↓
1. db_query.query_extraction(...)  ← R1 DB hit
    ↓ hit, fresh
    return ExtractionResult(staleness=FRESH)
    ↓ hit, stale (catalog_version mismatch)
    return ExtractionResult(staleness=STALE)
    ↓ miss (and refresh_policy != CACHE_ONLY)
2. pipeline_core.run(company, period_end, market, ...)  ← R4 pipeline in-process
    内部走 fetch (R2 cache) + evaluate (R3 cache) + index_run
    ↓ pipeline failure → raise ExtractorError(reason="fetch_failed"|"evaluate_failed")
3. db_query.query_extraction(...)  ← 再查一次，必中
    return ExtractionResult(staleness=FRESH)
```

关键点：

- **唯一 backend**：`R1 DB`（cache）+ `R4 pipeline`（fresh-run primitive）。
- **没有 in-process ArtifactBackend 读 `tmp/runs/*.json`**。`evaluation.json` 是 R4 pipeline 内部写盘 artifact，**仅供 R1 indexer 消费 + 操作员 audit**；client 不读它。R4→R1 的数据流动仍在，对 client 不可见。
- HTTP sidecar（Phase 2）只是把同一套 client API 包成 HTTP transport，业务路径不变。
- 测试模式 (`RefreshPolicy.CACHE_ONLY`) 永不进入 step 2；DB miss 直接返回 `Staleness.MISSING`。

## Public API

```python
from financial_report_llm_extractor.client import (
    ConfidenceLevel,
    ExtractionResult,
    ExtractorConfig,
    ExtractorError,
    FieldValue,
    FinancialReportClient,
    PdfQuery,
    RefreshPolicy,
    Staleness,
)
```

示例：

```python
from pathlib import Path

from financial_report_llm_extractor.client import (
    ExtractorConfig,
    FinancialReportClient,
    PdfQuery,
    RefreshPolicy,
)


def resolve_pdf(query: PdfQuery) -> Path | None:
    # TradingAgents-CN 注入自己的 PDF 命名和下载目录规则。
    return Path("downloads") / query.market.lower() / query.company / f"{query.period_end}.pdf"


client = FinancialReportClient(
    config=ExtractorConfig(
        llm_config_path=Path("tmp/llm_configs/codex_subscription.json"),
        pdf_resolver=resolve_pdf,
    )
)

result = client.get_extraction(
    company="600519",
    period_end="2024-12-31",
    market="CN",
    include_llm_supplement=False,
    refresh_policy=RefreshPolicy.CACHE_FIRST,
)

# Must guard staleness before iterating fields.
if result.staleness.is_missing:
    skip_company()  # no extraction available
elif result.staleness.is_stale:
    log_warning_then_decide()
else:
    revenue = result.fields["revenue"]
    if revenue.is_reliable:
        # TradingAgents-CN 自己执行 Owner Earnings / FCF / ratio 计算。
        ...
```

## Dataclass Contract

```python
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Callable, Literal


class ConfidenceLevel(Enum):
    VERIFIED = "verified"              # clean_present
    LLM_SUPPLEMENT = "llm_supplement"  # llm_supplement_present
    AMBIGUOUS = "ambiguous"            # unresolved_conflict
    UNAVAILABLE = "unavailable"        # terminal_unverified / source_unavailable / not_in_scope


class RefreshPolicy(Enum):
    CACHE_ONLY = "cache_only"          # DB miss → return staleness=MISSING；不触发 pipeline
    CACHE_FIRST = "cache_first"        # DB hit (含 stale) 直接返回；miss → 跑 pipeline
    FORCE_REFRESH = "force_refresh"    # 总是跑 pipeline


class Staleness(Enum):
    FRESH = "fresh"      # DB hit + catalog_version 匹配
    STALE = "stale"      # DB hit + catalog_version 不匹配
    MISSING = "missing"  # DB miss + CACHE_ONLY 拒绝拉新

    @property
    def is_fresh(self) -> bool:
        return self == Staleness.FRESH

    @property
    def is_stale(self) -> bool:
        return self == Staleness.STALE

    @property
    def is_missing(self) -> bool:
        return self == Staleness.MISSING


# source 字段实际取值（从源代码 + production evaluation.json 实测）：
#   "akshare"  — provider-direct (AKShare 数据)
#   "yahoo"    — provider-direct (Yahoo Finance 数据)
#   "llm"      — LLM supplement（**不细分模型**；per-LLM 区分通过
#                ExtractionResult.llm_provider + .llm_model 暴露）
#   None       — value 缺失，无 source（如 unresolved_conflict / source_unavailable）
# 未来扩展前缀（**Phase 1a 不要假设其存在，按现有 4 个取值实现**）：
#   "derived"  — catalog derivation 规则（如 SGA = MANAGE + SALE）
#   "pdf"     — pdf_only 字段（目前与 "llm" 不区分）
SourceLabel = Literal["akshare", "yahoo", "llm"]  # None 用 Optional 表达


@dataclass(frozen=True, kw_only=True)
class PdfQuery:
    """Keyword-only dataclass for pdf_resolver to prevent positional misuse."""
    company: str
    period_end: str
    market: str


@dataclass(frozen=True)
class ExtractorConfig:
    """All paths optional. None = use packaged default (importlib.resources)
    for catalog/taxonomy; env var FR_LLM_CACHE_ROOT for cache_root/db_path,
    falling back to ~/.cache/financial-report-llm-extractor/."""
    llm_config_path: Path | None = None
    pdf_resolver: Callable[[PdfQuery], Path | None] | None = None
    cache_root: Path | None = None       # default: $FR_LLM_CACHE_ROOT or ~/.cache/financial-report-llm-extractor/
    db_path: Path | None = None          # default: <cache_root>/extracted.db
    catalog_path: Path | None = None     # default: importlib.resources lookup
    taxonomy_path: Path | None = None    # default: importlib.resources lookup


@dataclass(frozen=True)
class FieldValue:
    """Per-field result. value type follows taxonomy.value_type:
      money/number  → Decimal
      text          → str
      boolean       → bool
    None when value is absent or filtered."""
    field_id: str
    value: Decimal | str | bool | None
    currency: str | None     # ISO code: "CNY" / "HKD" / "USD" / None
    unit: str | None         # "yuan" / "thousand" / "million" / ...
    confidence: ConfidenceLevel
    source: SourceLabel | None   # "akshare" / "yahoo" / "llm" / None
    evidence_page: int | None
    raw_bucket: str          # for audit only; do NOT branch business logic on this
    reason: str | None = None

    @property
    def is_reliable(self) -> bool:
        return self.confidence == ConfidenceLevel.VERIFIED

    @property
    def is_present(self) -> bool:
        return self.value is not None

    @property
    def verification_required(self) -> bool:
        """True for LLM-sourced values (downstream should apply confidence
        threshold / consensus check before relying on them).
        Derived from `source`; not stored."""
        return self.source == "llm"


@dataclass(frozen=True)
class ExtractionResult:
    """A single extraction snapshot.

    When staleness == MISSING, fields == {} (no extraction available).
    When staleness == STALE or FRESH, fields contains all catalog-known
    fields with their per-field FieldValue (possibly confidence=UNAVAILABLE).

    Callers MUST guard staleness before iterating fields:
        if result.staleness.is_missing: skip
        elif result.staleness.is_stale: warn-then-decide
        else: use fields
    """
    company: str
    period_end: str
    market: str
    catalog_version: str
    generated_at: str           # ISO 8601
    extraction_id: str          # stable hash for downstream dedup
    staleness: Staleness
    fields: dict[str, FieldValue]
    llm_provider: str | None = None  # "deepseek" / "openai-codex" / "claude-code" / None
    llm_model: str | None = None     # "deepseek-chat" / "gpt-5.5" / "claude-sonnet-4-6" / None
    # Both above mirror R1 extractions table columns; downstream uses them
    # for per-LLM trust policy (e.g. "trust gpt-5.5 more than deepseek-chat"
    # per Phase Q's 7.1% DS shallow FP finding).


class ExtractorError(Exception):
    """统一 internal exception wrapper. 不向下游泄露 sqlite3/subprocess/provider 异常。"""

    def __init__(
        self,
        *,
        reason: str,           # 见 §错误语义 表格
        message: str,
        company: str | None = None,
        period_end: str | None = None,
        market: str | None = None,
        cause_type: str | None = None,  # 原始异常类名，仅用于诊断
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.company = company
        self.period_end = period_end
        self.market = market
        self.cause_type = cause_type
```

### `extraction_id` 计算规则

```python
import hashlib

extraction_id = hashlib.sha256(
    f"{company}|{period_end}|{market}|{catalog_version}|{generated_at}".encode("utf-8")
).hexdigest()[:32]
```

- 同一 (company, period_end, market, catalog_version) 同一次 fresh run = 同一 `extraction_id`
- 重跑 (fresh) 会得到不同 `generated_at` → 不同 `extraction_id`
- 下游用 `extraction_id` 作为自己 derived-data DB 的 invalidation key

### Numeric 值反序列化规则

`value` 列在 R1 DB 中是 JSON-encoded text。client 反序列化遵循 catalog `value_type`：

| taxonomy.value_type | Python 类型 | 反序列化规则 |
|---|---|---|
| `money` | `Decimal` | `Decimal(str(json.loads(text)))`（先 str-ify 防 float 精度丢失） |
| `number` | `Decimal` | 同上 |
| `text` | `str` | `json.loads(text)` |
| `boolean` | `bool` | `bool(json.loads(text))` |

**Decimal 转换强制走 `str(...)` 中间步骤**，避免 `Decimal(0.1) != Decimal("0.1")` 类 float 精度问题。

## Client Methods

```python
class FinancialReportClient:
    def __init__(self, config: ExtractorConfig | None = None) -> None:
        """If config is None, all paths use defaults (env var or packaged data)."""

    def get_extraction(
        self,
        *,
        company: str,
        period_end: str,
        market: Literal["CN", "HK"],
        include_llm_supplement: bool = False,
        refresh_policy: RefreshPolicy = RefreshPolicy.CACHE_FIRST,
    ) -> ExtractionResult:
        """
        返回一次 extraction 的完整 ExtractionResult.

        include_llm_supplement (symmetric semantics — 同时控制 filter + LLM step):
          False (默认):
            - 已有 DB row: LLM_SUPPLEMENT 字段以占位返回
                FieldValue(confidence=UNAVAILABLE, value=None,
                           raw_bucket="llm_supplement_present",
                           reason="llm_supplement_filtered")
              字段 IS in result.fields，is_reliable=False, is_present=False。
            - DB miss + CACHE_FIRST: pipeline 跑但**跳过 LLM step**（evaluate
              不带 pdf_path / llm_config）。
            - DB miss + FORCE_REFRESH: 同上。
          True:
            - 已有 DB row: LLM 字段照常包含 (confidence=LLM_SUPPLEMENT)。
            - DB miss + CACHE_FIRST: pipeline 跑且**包含 LLM step** — 需
              pdf_resolver + llm_config_path 都已配齐，否则 raise
              ExtractorError(reason="pdf_not_found" | "llm_config_missing")。
            - DB miss + FORCE_REFRESH: 同上。
          ⚠ Edge case: 已有 DB row 但 row 当初未跑 LLM
            (extractions.llm_provider=None) → `include_llm_supplement=True`
            仍返回 0 LLM 字段。要补抽取，用 FORCE_REFRESH。

        refresh_policy:
          CACHE_ONLY:    DB miss → staleness=MISSING, fields={}
                         DB hit + catalog_version 不匹配 → staleness=STALE,
                           fields=旧值（含所有 catalog 字段）
                         DB hit + 匹配 → staleness=FRESH
                         **永不触发 fetch/evaluate**（测试 + offline 模式）
          CACHE_FIRST:   DB hit (含 stale) → 直接返回，不触发 pipeline
                         DB miss → 跑 pipeline → 再查 DB
          FORCE_REFRESH: 总是跑 pipeline (fetch + evaluate + index)，
                         无视 DB cache。**注意**：FORCE_REFRESH 仍消费
                         R2/R3 cache（24h TTL + content-addressed），
                         不重新拉 provider 数据或重调 LLM；只是确保
                         pipeline 跑一遍。绕过所有 cache 用 operator CLI
                         `pipeline --no-cache`，client 不暴露此选项。

        Performance note: 一次 get_extraction = 2 DB queries (metadata + 
        所有 field_values). 批量场景请用本方法而非循环 get_field。

        Raises (统一 ExtractorError，见 §错误语义):
          - unsupported_market: market 不在 {"CN", "HK"}
          - invalid_period: period_end 不可解析为 ISO date
          - fetch_failed: pipeline fetch 阶段失败（仅 CACHE_FIRST miss / FORCE_REFRESH 时）
          - evaluate_failed: pipeline evaluate 阶段失败
            ⚠ partial failure 语义：DB 旧 row（如有）保持不变（R4 pipeline
            内部走 transaction，evaluate 失败不会 DELETE 旧 field_values）。
            下游可 catch 后 fallback CACHE_FIRST 拿旧值。
          - pdf_not_found: FORCE_REFRESH + include_llm_supplement=True 但
            pdf_resolver 返回 None
          - llm_config_missing: FORCE_REFRESH + include_llm_supplement=True
            但 ExtractorConfig.llm_config_path 未设
        """

    def get_field(
        self,
        *,
        company: str,
        period_end: str,
        market: Literal["CN", "HK"],
        field_id: str,
        include_llm_supplement: bool = False,
        refresh_policy: RefreshPolicy = RefreshPolicy.CACHE_FIRST,
    ) -> FieldValue:
        """
        返回单个字段（行为与 get_extraction 一致）。

        field_id 必须在 taxonomy 中：
          - 在 taxonomy 中 → 返回 FieldValue（即使 confidence=UNAVAILABLE）
          - 不在 taxonomy 中 → raise ExtractorError(reason="unknown_field")
          - 在 taxonomy 但 include_llm_supplement=False 且字段为 LLM_SUPPLEMENT
            → 返回 FieldValue(confidence=UNAVAILABLE, value=None,
                              raw_bucket="llm_supplement_present",
                              reason="llm_supplement_filtered")
            **与 get_extraction filter 行为一致** — 占位返回，不 hard-filter。

        Performance: get_field = 1-2 DB queries + 1 taxonomy lookup. 循环
        调用 68 次成本相当 = 68 × N。访问多个字段请用 get_extraction。

        Raises (额外):
          - unknown_field: field_id 不在 taxonomy.fields
        """

    def get_status(
        self,
        *,
        company: str,
        period_end: str,
        market: Literal["CN", "HK"],
    ) -> Staleness:
        """轻量 DB lookup，不触发任何 fetch/evaluate。"""

    def catalog_fields(self) -> tuple[str, ...]:
        """Return all field_ids known to the current catalog (taxonomy)."""

    def catalog_version(self) -> str:
        """Return current catalog version (= taxonomy.version)."""
```

所有方法**全 keyword-only**。这样 `company` 和 `market` 位置错乱不会变成静默 bug。

## Bucket 到 Confidence 翻译

下游不应写 `if bucket == "clean_present"`。client 层负责把 `evaluation.json` bucket 翻译为 Python 类型语义。`raw_bucket` 保留以供 audit、报告、retry 决策。

| evaluation bucket | ConfidenceLevel | `is_reliable` | `is_present` | filter (include_llm_supplement=False) | 默认下游用途 |
| --- | --- | --- | --- | --- | --- |
| `clean_present` | `VERIFIED` | true | true | 保留 | 可参与结构化计算 |
| `llm_supplement_present` | `LLM_SUPPLEMENT` | false | true | **占位 UNAVAILABLE** | opt-in 才参与计算 |
| `unresolved_conflict` | `AMBIGUOUS` | false | false | 保留 | 展示冲突，禁止自动计算 |
| `terminal_unverified` | `UNAVAILABLE` | false | false | 保留 | 展示终态原因，禁止补值 |
| `source_unavailable` | `UNAVAILABLE` | false | false | 保留 | 显式缺失（provider 真无数据） |
| `not_in_scope` | `UNAVAILABLE` | false | false | 保留 | 故意不抽取；下游 retry 无意义 |

**关于 `not_in_scope` vs `source_unavailable`**：两者都映射 `UNAVAILABLE`，但 retry 策略不同。`source_unavailable` 可能因 provider 数据更新而后续可得；`not_in_scope` 永远不会。下游用 `raw_bucket` 做二级判断：

```python
if field.confidence == ConfidenceLevel.UNAVAILABLE:
    if field.raw_bucket == "not_in_scope":
        skip_field_permanently()  # 永不 retry
    else:
        mark_for_periodic_retry()  # 可能未来 provider 数据可用
```

关键 guardrails：

- `llm_evidence_supplement.json` 不直接给下游 merge；下游只消费 client 产出的 `FieldValue`。
- `source == "llm"` 必须映射为 `LLM_SUPPLEMENT`；`verification_required` 自动 True。
- HK `gross_profit` 在 provider raw semantics 未证明前不能映射为 `VERIFIED`（保持 `UNAVAILABLE` + raw_bucket=`terminal_unverified`）。
- HK `net_profit` 可以是 provider semantics sampled proof，但不能被表述成最终逐公司 PDF evidence。
- **Evidence kind 不在 Phase 1a 暴露**。当前 `selected_source` 字段只携带 4 个值 `{"akshare", "yahoo", "llm", None}`，**抹平**了内部细分：
  - `"yahoo"` 直接 raw match vs `"yahoo"` 经过 H2 PDF semantics promotion → 同字符串
  - `"akshare"` 直接 vs 经过 trust_policy_evidence sampled proof → 同字符串
  - `"llm"` 只标记 LLM 来源，`ExtractionResult.llm_provider` 标记模型，但**不区分**该 LLM 字段是否带 PDF spot-check 证据

  下游若需细分（如 caveat 报告区分 "raw provider match" vs "PDF-verified sample promotion"），通过未来 `evidence_kind` 字段或 separate `client.get_evidence(field_id)` API 暴露——这是 **Phase 2 deliverable**，不在 Phase 1a contract 中。Phase 1a 只暴露 value + bucket-derived ConfidenceLevel + 最粗粒度 source label。

## CACHE_FIRST 撞 Stale 的精确语义

明文：**`CACHE_FIRST` 撞 stale → 直接返回 stale 值**，`result.staleness = STALE`。Client 不自动 refresh。

下游典型用法：

```python
result = client.get_extraction(...)
if result.staleness.is_stale:
    if business_logic_requires_fresh_data:
        result = client.get_extraction(..., refresh_policy=RefreshPolicy.FORCE_REFRESH)
    else:
        log_warning_and_continue()
```

这样 catalog 升级后 downstream 不会被静默拉网络/烧 LLM token；显式 trigger 是 downstream policy。

## 错误语义

内部异常必须统一包成 `ExtractorError`，避免向下游泄露：

| reason | 触发场景 |
|---|---|
| `unsupported_market` | market 不在 {"CN", "HK"} |
| `invalid_period` | period_end 不是合法 ISO date |
| `unknown_field` | field_id 不在 taxonomy |
| `pdf_not_found` | FORCE_REFRESH + include_llm_supplement=True 但 pdf_resolver 返回 None / 文件不存在 |
| `llm_config_missing` | FORCE_REFRESH + include_llm_supplement=True 但 ExtractorConfig.llm_config_path=None |
| `fetch_failed` | pipeline 内部 fetch 阶段 raise（AKShare/Yahoo 网络 / parsing 失败） |
| `evaluate_failed` | pipeline 内部 evaluate 阶段 raise（DB 旧 row 不受影响） |
| `db_not_initialized` | DB 不存在且 refresh_policy=CACHE_ONLY |

不得直接抛 `sqlite3.OperationalError`、`subprocess.CalledProcessError`、`urllib.error.URLError`、provider-specific exception。所有这些都被 catch 后包成 `ExtractorError(cause_type="sqlite3.OperationalError", ...)`。

`catalog_mismatch` 不是 ExtractorError reason — 它映射为 `Staleness.STALE`（不抛异常）。

## PDF 路径责任

extractor 不拥有 TradingAgents-CN 的 PDF 命名和下载目录规则。`ExtractorConfig.pdf_resolver` 接受 callable：

```python
Callable[[PdfQuery], Path | None]
```

`PdfQuery` 是 frozen kw-only dataclass `(company, period_end, market)`，避免 3 个位置 `str` 顺序错乱。

resolver 返回 `None` 或文件不存在 → 三种处理：

- `include_llm_supplement=False`：忽略，正常返回（不进 LLM 步骤）。
- `include_llm_supplement=True` + `refresh_policy=CACHE_ONLY/CACHE_FIRST`：返回 DB cache（即使 stale），标 `staleness=STALE`。
- `include_llm_supplement=True` + `refresh_policy=FORCE_REFRESH`：raise `ExtractorError(reason="pdf_not_found")`。

## Catalog Version 与下游失效

`ExtractionResult.catalog_version` + `extraction_id` 是 downstream 持久层失效的两把钥匙：

- catalog 升级（如 G1-G4-C 新增字段）→ DB row catalog_version 不匹配 → `staleness=STALE`
- 同 cohort 重跑（FORCE_REFRESH）→ 新 `generated_at` → 新 `extraction_id`

downstream 在自己的 derived-data DB 用 `extraction_id` 作 FK；catalog_version 升级时旧 derived-data 自然 stale。extractor 负责告知 staleness，**不替 downstream 决定衍生指标是否失效**。

## TradingAgents-CN 接入建议

Phase 1b 在 `TradingAgents-CN` 内新增 `FinancialReportAdapter`：

- 封装 `FinancialReportClient`。
- 对 fundamentals tool 暴露 analyst-readable summary（按 ConfidenceLevel 分组）。
- 对 value investment tool 暴露结构化字段字典（默认只 `is_reliable`）。
- `LLM_SUPPLEMENT` 字段只在配置 `allow_llm_data=True` 时参与计算，并在报告里输出 caveat 注明 LLM 来源（`result.llm_provider` / `result.llm_model`）。
- **per-LLM trust policy**：`result.llm_model == "gpt-5.5"` 可作为更可信的 LLM 来源（Phase Q 数据支撑：DS 7.1% FP，Codex 显著更低）；`result.llm_model == "deepseek-chat"` 需更严格 caveat。**注意**：trust policy 在 `ExtractionResult` 层而非 `FieldValue` 层判断，因为同一 extraction 所有 LLM 字段来自同一模型。

自然接入点：

- `tradingagents/agents/utils/agent_utils.py` 的 `get_stock_fundamentals_unified`。
- `tradingagents/tools/value_investment_tool.py` 的结构化财务数据获取/补缺流程。
- `tradingagents/dataflows/value_investment/report_data_mapper.py` 旁边新增 Turtle mapper，而不是复用 report-collector schema。

## 内部实现要点（不属于 public contract，但影响 Phase 1a 工作量）

- **In-process pipeline 调用**：把 `cli.py` `pipeline` 分支抽出来成为 `pipeline_core.run_pipeline(...)` 函数，client 直接 import。CLI 变成对 `pipeline_core` 的薄包装。**注意**：`_run_fetch_source_inventory` 和 `_run_evaluate_company` helpers 当前在 cli.py 中，需一并提到 `pipeline_core` 或同等位置。
- **catalog/taxonomy 默认路径**：用 `importlib.resources.files("financial_report_llm_extractor") / "_catalog_data"`（参见 §打包分发）。
- **cache_root 默认**：环境变量 `FR_LLM_CACHE_ROOT` > `~/.cache/financial-report-llm-extractor/` > 显式 config 覆盖。
- **db_path 默认**：`<cache_root>/extracted.db`（不再是 repo-relative `data/extracted.db`）。
- **测试不依赖 LLM/network**：所有 client 单元测试用 `RefreshPolicy.CACHE_ONLY` + 预 seed 的 DB fixture。**复用现有 `tests/fixtures/cache_sample_run/`** 而不是新造。Integration 测试可选 `FORCE_REFRESH` 但 mark 为 slow。

## Tradeoffs

### 是否同时做下游接入

建议 1a + 1b 同一周内完成。只 ship client library 而没有 `TradingAgents-CN` adapter，contract 没有真实 consumer，容易腐烂。闭环验证应以 `TradingAgents-CN` 能读取 `600519`、`00001`、`01810/09987` 等代表性 artifact 并正确跳过 non-reliable 字段为完成标准。

### 是否保留 raw bucket

保留。业务代码不依赖 raw bucket，但 audit、日志、报告解释、`not_in_scope` vs `source_unavailable` 的 retry 决策都需要它。`ConfidenceLevel` 是 runtime 语义；`raw_bucket` 是 source-first catalog/review 语义。

### `Decimal` vs `float`

强制 `Decimal`。所有 money / number 字段反序列化必走 `Decimal(str(...))`。性能 cost 可忽略；精度收益对 Owner Earnings / FCF 等链式计算关键。

### 并发访问

Phase 1a **不保证多进程安全**。SQLite busy_timeout（R1 已设 10s）足以支撑串行 access；多 TradingAgents-CN agent 并发触发 pipeline 时可能竞争 LLM 调用 / cache 写入。如有真实并发需求 → Phase 2 HTTP sidecar 时加文件锁或 job queue。文档化此限制。

### FORCE_REFRESH 成本警告

每次 `FORCE_REFRESH` 触发完整 pipeline：

| 阶段 | 是否仍走 cache | 成本 |
|---|---|---|
| R2 provider fetch | ✓ 走（24h TTL） | 网络 0（cache hit）/ 数 MB（miss） |
| R3 LLM call | ✓ 走（content-addressed，无 TTL） | $$ 0（cache hit，几乎总命中）/ $$ N×0.01-0.1（miss） |
| R4 pipeline orchestration | 总会跑 | CPU 数秒 |

**经验值**：FORCE_REFRESH 同一 cohort 第二次几乎免费（R2+R3 都命中）；catalog 升级 / model change 后第一次 FORCE_REFRESH 会 miss 重跑 LLM。下游**不应在每次 request 都 FORCE_REFRESH** — 仅在以下场景使用：

- catalog 升级后第一次拉新数据
- 已知 provider 数据已修订（如年报重发）
- TradingAgents-CN 用户显式触发 "refresh data" 按钮

### `evaluation.json` 是否完全 invisible 给下游

是。R4 pipeline 写 `evaluation.json` → R1 indexer 读 → UPSERT DB → client 从 DB 读。**client 不读 `evaluation.json`**。这个 internal pipe 对 client 用户不可见。

## 产品化路线

| Phase | 内容 | Effort | Out-of-scope |
| --- | --- | --- | --- |
| **R5 (prerequisite)** | R1 schema market-scoping：`field_values` PK 加 market、query API 加 market 必选参数、indexer 写 market、CLI `query --market` required、init_db schema v2 检测+rebuild、cross-market 非冲突 regression test | ~半天 | client API（仍是 Phase 1a） |
| 1a | `FinancialReportClient` library、dataclass contract、单一 backend（R1 DB + R4 pipeline in-process）、importlib.resources 打包 catalog、pip-installable package、focused tests | ~2-3 天 | HTTP、job queue、多 process、DB schema 暴露、subprocess fallback |
| 1b | `TradingAgents-CN` 写 `FinancialReportAdapter`，接 fundamentals/value-investment，默认只用 `is_reliable` | ~1 天 | extractor 内部知识、bucket 直读 |
| 2 | HTTP sidecar，同 contract 包一层 transport，服务多 consumer | ~2-3 天 | 业务语义变动 |
| 3 | skill/operator workflow：触发 pipeline、审查 artifact、生成 audit prompt | 暂缓 | runtime dependency |

## 验收标准

### Phase 1a

- `pip install -e .` 后从 **任意目录**：`from financial_report_llm_extractor.client import FinancialReportClient; FinancialReportClient()` 成功（catalog 路径通过 importlib.resources 解析）。
- `get_extraction()` 返回 `ExtractionResult` frozen dataclass，不返回裸 JSON dict。
- `get_field()` 对 catalog 内 missing/unavailable 字段返回 `FieldValue(confidence=UNAVAILABLE)`，不丢 reason。
- `get_field()` 对 unknown field_id raise `ExtractorError(reason="unknown_field")`。
- bucket 到 `ConfidenceLevel` 映射有单元测试覆盖全部 6 种 bucket。
- `llm_supplement_present` 不会让 `is_reliable=True`。
- `include_llm_supplement=False` filter 占位 `FieldValue(confidence=UNAVAILABLE, raw_bucket="llm_supplement_present", reason="llm_supplement_filtered")`，**字段仍在 result.fields 中**。
- `get_extraction()` 和 `get_field()` 对 LLM filter 行为一致（都返回占位 UNAVAILABLE，不静默删字段）。
- HK `gross_profit` (terminal_unverified) 不会映射成 `VERIFIED`。
- 所有内部异常统一成 `ExtractorError`，`cause_type` 字段携带原始异常类名。
- `ExtractorError` 可被 `try / except` 正确捕获，`.reason / .message / .company / .period_end / .market / .cause_type` 可访问。
- **Decimal 精度 round-trip 测试**：从 fixture DB → `ExtractionResult.fields["revenue"].value` → 期望 `Decimal("170899152276.34")`，**不**期望 `float`。
- **Staleness 测试**：DB row catalog_version='v1'，client catalog_version='v2' → `result.staleness == STALE`，`fields` 仍返回旧值。
- **CACHE_ONLY DB miss 测试**：`fields == {}`, `staleness == MISSING`，不触发任何 fetch/evaluate。
- **CACHE_ONLY guard 测试**：测试明确包含 `if result.staleness.is_missing: skip` 模式，验证 empty fields 不会被误 iterate。
- **`extraction_id` 稳定性测试**：相同 (company, period_end, market, catalog_version, generated_at) → 相同 hash。
- **`include_llm_supplement=True` symmetric semantics 测试**:
  - 已有 DB row 不带 LLM 字段 + CACHE_ONLY → 0 LLM 字段返回
  - DB miss + CACHE_FIRST + `include_llm_supplement=True` + pdf_resolver/llm_config 配齐 → pipeline 跑且执行 LLM step → 返回 LLM 字段
  - DB miss + CACHE_FIRST + `include_llm_supplement=False` → pipeline 跑但跳过 LLM step → 返回时 LLM 字段以占位 UNAVAILABLE 返回
  - DB miss + CACHE_FIRST + `include_llm_supplement=True` + pdf_resolver 缺 → raise ExtractorError(pdf_not_found)
- **R5 prerequisite test (cross-market non-collision)**：indexing 同 (company, period_end) 在 CN + HK 两次，验证 field_values 两套独立、不互覆盖；query_extraction(market="CN") 与 query_extraction(market="HK") 返回不同 fields dict。
- **`PdfQuery` kw-only 测试**：`PdfQuery("600519", "2024-12-31", "CN")` 位置构造 raise；`PdfQuery(company=..., period_end=..., market=...)` 正常。
- **测试 fixture 优先复用 `tests/fixtures/cache_sample_run/`**；现 fixture 仅含 3 buckets (clean_present / llm_supplement_present / unresolved_conflict)，不足处通过 **程序化 seed**（`init_db()` + 直接 SQL INSERT 或 `index_run()` + 临时 evaluation.json 文件）添加缺失 bucket (`terminal_unverified` / `source_unavailable` / `not_in_scope`) 与 catalog_version mismatch 的 stale 场景。禁止新建独立 client-only 整套 fixture 目录。

### Phase 1b

- TradingAgents-CN 可以通过 adapter 消费 `600519`、`00001`、一个 HK USD/CNY issuer 的 extraction。
- 默认计算只使用 `is_reliable` 字段。
- 打开 `allow_llm_data` 时，报告明确标记 LLM caveat 含 `result.llm_provider` + `result.llm_model`。
- 下游没有 SQL、JSON path、CLI command、tmp path 依赖。
- **Per-LLM trust policy 测试**：`result.llm_model == "deepseek-chat"` 和 `result.llm_model == "gpt-5.5"` 在 caveat 输出中可区分。

## Open Decisions

唯一遗留：

1. **是否在 `FieldValue` 增加 `evidence_snippet` 与 `evidence_kind`**：TradingAgents-CN 报告需要引用原文片段（如 audit_opinion 的实际段落 / dividend_policy_text 的段落）。需要 → 加；不需要 → Phase 2 通过 separate `client.get_evidence(field_id)` API 暴露，避免 FieldValue 体积膨胀（R1 schema `llm_reasoning_short` 已 truncate 到 500 chars；如要全文需查 `llm_evidence_supplement.json`）。

**已 close 的 decisions**（rev 2 后定）：

- ~~cache_root 默认目录~~ → `$FR_LLM_CACHE_ROOT > ~/.cache/financial-report-llm-extractor/`
- ~~是否 fields=[...] 过滤~~ → 不加；下游自己过滤
- ~~nuclear_refresh 选项~~ → 不加；operator 用 CLI `--no-cache`
- ~~source 字段细分~~ → 不在 FieldValue.source 细分；在 ExtractionResult.llm_model 暴露
- ~~Phase 1a 单 vs 双 backend~~ → 单 backend (R1 + R4)，不读 tmp/runs/*.json
- ~~Python 版本~~ → 假设 3.11+；其他路径触发 spec 重审
