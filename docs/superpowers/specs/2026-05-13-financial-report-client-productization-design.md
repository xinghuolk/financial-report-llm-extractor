# FinancialReportClient 产品化设计 Spec

> 日期：2026-05-13
> 状态：Draft
> 背景：Turtle v0.15 phase3 68 mapped 字段已覆盖下游四因子分析所需 catalog 层数据。`evaluate-company` 已能产出 `evaluation.json` 与 `llm_evidence_supplement.json`，下游 `TradingAgents-CN` 需要一个稳定、可编程、不会泄露 extractor 内部实现的消费接口。

## 目标

将 `financial-report-llm-extractor` 产品化为一个可被 `TradingAgents-CN` 直接 import 的 Python library。下游只依赖公开的 `FinancialReportClient` API contract，不读取 extractor 内部 SQLite、cache、CLI 输出目录或中间 artifact。

核心目标：

- 对下游暴露纯 Python dataclass interface。
- 将 source-first bucket 语义翻译为 Pythonic reliability/confidence 语义。
- 继续保持 extractor 的 source-first guardrails：不做 canonical fact promotion，不把 LLM supplement 当 provider verified fact。
- 内部保留 DB/cache/CLI/pipeline 的实现自由，后续可替换为 SQLite、artifact backend、pipeline backend 或 HTTP backend。
- 让 `TradingAgents-CN` 可以用 `FieldValue.is_reliable` 进行 Owner Earnings、FCF、ratio 等下游计算。

## Non-Goals

- 不把 extractor 的 SQLite schema 暴露给下游。
- 不要求 `TradingAgents-CN` 读 JSON 文件、拼 CLI 命令或理解 `tmp/runs` 路径约定。
- 不在 Phase 1 做 HTTP sidecar、job queue、多 process worker 或 auth。
- 不让 runtime 依赖 Codex/Claude skill。skill 仅作为 operator 触发 pipeline 与 audit artifact 的辅助入口。
- 不在 extractor 内部计算 Owner Earnings、FCF、payout ratio、估值 ratio 或 Turtle Agent 四因子结论；这些属于 `TradingAgents-CN` / `financial-report-analysis` 下游逻辑。

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
      ExtractorError

  INTERNAL:
    data/extracted.db
    tmp/.cache/
    pipeline CLI
    fetch-source-inventory / evaluate-company stages
    evaluation.json / extraction_result.json intermediate artifacts
```

下游只看到 `FinancialReportClient`。DB、cache、CLI、artifact path、fetch/evaluate stages 都是 extractor 内部实现细节。

## Public API

建议第一版公开模块：

```python
from financial_report_llm_extractor.client import (
    ConfidenceLevel,
    ExtractionResult,
    ExtractorConfig,
    ExtractorError,
    FieldValue,
    FinancialReportClient,
    RefreshPolicy,
)
```

示例：

```python
from pathlib import Path

from financial_report_llm_extractor.client import (
    ExtractorConfig,
    FinancialReportClient,
    RefreshPolicy,
)


def resolve_pdf(company: str, period_end: str, market: str) -> Path | None:
    # TradingAgents-CN 注入自己的 PDF 命名和下载目录规则。
    return Path("downloads") / market.lower() / company / f"{period_end}.pdf"


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

revenue = result.fields["revenue"]
if revenue.is_reliable:
    # TradingAgents-CN 自己执行 Owner Earnings / FCF / ratio 计算。
    ...
```

## Dataclass Contract

```python
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Callable


class ConfidenceLevel(Enum):
    VERIFIED = "verified"
    LLM_SUPPLEMENT = "llm_supplement"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"


class RefreshPolicy(Enum):
    CACHE_ONLY = "cache_only"
    CACHE_FIRST = "cache_first"
    FORCE_REFRESH = "force_refresh"


@dataclass(frozen=True)
class ExtractorConfig:
    llm_config_path: Path | None = None
    pdf_resolver: Callable[[str, str, str], Path | None] | None = None
    cache_root: Path | None = None
    catalog_path: Path | None = None
    taxonomy_path: Path | None = None


@dataclass(frozen=True)
class FieldValue:
    field_id: str
    value: Decimal | str | None
    currency: str | None
    unit: str | None
    confidence: ConfidenceLevel
    source: str | None
    evidence_page: int | None
    raw_bucket: str
    reason: str | None = None
    verification_required: bool = False

    @property
    def is_reliable(self) -> bool:
        return self.confidence == ConfidenceLevel.VERIFIED

    @property
    def is_present(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class ExtractionResult:
    company: str
    period_end: str
    market: str
    catalog_version: str
    generated_at: str
    fields: dict[str, FieldValue]
    artifact_id: str | None = None


class ExtractorError(Exception):
    reason: str
```

`get_field()` 不应把 catalog 内缺失字段简单返回 `None`。只要字段属于 catalog，就返回 `FieldValue(value=None, confidence=UNAVAILABLE, reason=...)`，保留缺失原因。只有未知字段、市场不支持或调用参数非法时，才抛 `ExtractorError`。

## Client Methods

```python
class FinancialReportClient:
    def __init__(self, config: ExtractorConfig) -> None: ...

    def get_extraction(
        self,
        *,
        company: str,
        period_end: str,
        market: str,
        include_llm_supplement: bool = False,
        refresh_policy: RefreshPolicy = RefreshPolicy.CACHE_FIRST,
    ) -> ExtractionResult: ...

    def get_field(
        self,
        company: str,
        period_end: str,
        market: str,
        field_id: str,
        *,
        include_llm_supplement: bool = False,
        refresh_policy: RefreshPolicy = RefreshPolicy.CACHE_FIRST,
    ) -> FieldValue: ...

    def get_status(
        self,
        company: str,
        period_end: str,
        market: str,
    ) -> str: ...
```

`get_status()` 返回：

- `fresh`：当前 cache 与 catalog/version policy 匹配。
- `stale`：已有结果，但 catalog/version/provider policy 已变化或超出内部 freshness policy。
- `missing`：没有可用结果。

下游决定是否使用 `FORCE_REFRESH`，extractor 不替下游决定衍生指标是否失效。

## Bucket 到 Confidence 翻译

下游不应写 `if bucket == "clean_present"`。client 层负责把 `evaluation.json` bucket 翻译为 Python 类型语义，但保留 `raw_bucket` 作为审计信息。

| evaluation bucket | ConfidenceLevel | `is_reliable` | `is_present` | 默认下游用途 |
| --- | --- | --- | --- | --- |
| `clean_present` | `VERIFIED` | true | true | 可参与结构化计算 |
| `llm_supplement_present` | `LLM_SUPPLEMENT` | false | true | 可展示，可在 opt-in policy 下参与计算并打 caveat |
| `unresolved_conflict` | `AMBIGUOUS` | false | false | 展示冲突，禁止自动计算 |
| `terminal_unverified` | `UNAVAILABLE` | false | false | 展示终态原因，禁止补值 |
| `source_unavailable` | `UNAVAILABLE` | false | false | 显式缺失 |
| `not_in_scope` | `UNAVAILABLE` | false | false | 表示本次没有跑对应路径，不视为 provider 失败 |

关键 guardrails：

- `llm_evidence_supplement.json` 不直接给下游 merge；下游只消费 client 产出的 `FieldValue`。
- `selected_source == "llm"` 必须映射为 `LLM_SUPPLEMENT`，并设置 `verification_required=True`。
- HK `gross_profit` 在 provider raw semantics 未证明前不能映射为 `VERIFIED`。
- HK `net_profit` 可以是 provider semantics sampled proof，但不能被表述成最终逐公司 PDF evidence。
- `source_evidence`、`trust_policy_evidence`、`pdf_evidence` 的区别不能在内部 export 层被抹平。

## 内部 Backend 分层

Phase 1a 不要求一次性完成 SQLite。建议 public client contract 先稳定，内部 backend 可渐进实现：

1. `ArtifactBackend`
   - 读取现有 `evaluation.json` / `extraction_result.json`。
   - 用于快速测试 client contract 与 TradingAgents-CN adapter。

2. `PipelineBackend`
   - 在 in-process 中调用已有 evaluate-company 内核。
   - `RefreshPolicy.FORCE_REFRESH` 映射到重新 fetch/evaluate。
   - 不让 downstream 接触 CLI 或 `tmp/runs`。

3. `SqliteBackend`
   - 将 R1 `data/extracted.db` 作为内部持久化。
   - 支持 catalog_version invalidation、fresh/stale/missing status。
   - schema 仅 extractor 内部使用，不作为 public contract。

后续 Phase 2 的 HTTP sidecar 只包装同一套 `FinancialReportClient` contract，不改变业务语义。

## 错误语义

内部异常必须统一包成 `ExtractorError`，避免向下游泄露：

- `db_not_initialized`
- `cache_unavailable`
- `fetch_failed`
- `evaluate_failed`
- `llm_config_missing`
- `pdf_not_found`
- `unsupported_market`
- `unknown_field`
- `catalog_mismatch`
- `invalid_period`

错误对象应包含 `reason`、`message`、`company`、`period_end`、`market`、可选 `cause_type`。不得直接抛 `sqlite3.OperationalError`、`subprocess.CalledProcessError`、provider-specific exception。

## PDF 路径责任

extractor 不拥有 TradingAgents-CN 的 PDF 命名和下载目录规则。`ExtractorConfig` 接受 `pdf_resolver` callable：

```python
Callable[[company, period_end, market], Path | None]
```

如果 `include_llm_supplement=True` 但 resolver 返回 `None` 或文件不存在，client 返回清晰的 `ExtractorError(reason="pdf_not_found")`，或在 `CACHE_ONLY` 场景下返回已有 cache 并标记未刷新。

## Catalog Version 与下游失效

`ExtractionResult` 必须携带 `catalog_version`。当 extractor 升级 Turtle catalog、source mapping catalog 或 provider trust policy 时，下游 derived-data DB 可用 `(company, period_end, market, catalog_version)` 作为 invalidation key。

extractor 负责判断自身 cache fresh/stale；TradingAgents-CN 负责判断 Owner Earnings、FCF、ratio 等衍生结果是否需要重算。

## TradingAgents-CN 接入建议

Phase 1b 在 `TradingAgents-CN` 内新增 `FinancialReportAdapter`：

- 封装 `FinancialReportClient`。
- 对 fundamentals tool 暴露一段 analyst-readable summary。
- 对 value investment tool 暴露结构化字段字典。
- 默认只使用 `FieldValue.is_reliable` 字段参与计算。
- `LLM_SUPPLEMENT` 字段只在配置 `allow_llm_data=True` 时参与计算，并在报告里输出 caveat。

自然接入点：

- `tradingagents/agents/utils/agent_utils.py` 的 `get_stock_fundamentals_unified`。
- `tradingagents/tools/value_investment_tool.py` 的结构化财务数据获取/补缺流程。
- `tradingagents/dataflows/value_investment/report_data_mapper.py` 旁边新增 Turtle mapper，而不是复用 report-collector schema。

## Tradeoffs

### In-process vs subprocess

推荐 Phase 1a 目标为 in-process import，因为单一 Python env 简单、无 spawn 开销、错误类型可控。但当前有一个前置风险：extractor `requires-python >=3.11`，TradingAgents-CN 当前可能支持 `>=3.10`。落地前必须确认目标部署环境使用 Python 3.11。

如果 TradingAgents-CN 仍需 Python 3.10，保留同一 public contract，但内部临时使用 subprocess backend，直到运行环境统一。

### 是否同时做下游接入

建议 1a + 1b 同一周内完成。只 ship client library 而没有 TradingAgents-CN adapter，contract 没有真实 consumer，容易腐烂。闭环验证应以 `TradingAgents-CN` 能读取 `600519`、`00001`、`01810/09987` 等代表性 artifact 并正确跳过 non-reliable 字段为完成标准。

### 是否保留 raw bucket

保留。业务代码不依赖 raw bucket，但 audit、日志、报告解释需要它。`ConfidenceLevel` 是 runtime 语义；`raw_bucket` 是 source-first catalog/review 语义。

## 产品化路线

| Phase | 内容 | Effort | Out-of-scope |
| --- | --- | --- | --- |
| 1a | `FinancialReportClient` library、dataclass contract、artifact/pipeline backend、pip-installable package、focused tests | ~2 天 | HTTP、job queue、多 process、DB schema 暴露 |
| 1b | `TradingAgents-CN` 写 `FinancialReportAdapter`，接 fundamentals/value-investment，默认只用 `is_reliable` | ~1 天 | extractor 内部知识、bucket 直读 |
| 2 | HTTP sidecar，同 contract 包一层 transport，服务多 consumer | ~2-3 天 | 业务语义变动 |
| 3 | skill/operator workflow：触发 pipeline、审查 artifact、生成 audit prompt | 暂缓 | runtime dependency |

## 验收标准

Phase 1a：

- `from financial_report_llm_extractor.client import FinancialReportClient` 可用。
- `get_extraction()` 返回 frozen dataclass，不返回裸 JSON dict。
- `get_field()` 对 catalog 内 missing/unavailable 字段返回 `FieldValue`，不丢 reason。
- bucket 到 `ConfidenceLevel` 映射有单元测试。
- `llm_supplement_present` 不会让 `is_reliable=True`。
- HK `gross_profit` non-clean fixture 不会映射成 `VERIFIED`。
- 所有内部异常统一成 `ExtractorError`。

Phase 1b：

- TradingAgents-CN 可以通过 adapter 消费 `600519`、`00001`、一个 HK USD/CNY issuer 的 extraction。
- 默认计算只使用 `is_reliable` 字段。
- 打开 `allow_llm_data` 时，报告明确标记 LLM caveat。
- 下游没有 SQL、JSON path、CLI command、tmp path 依赖。

## Open Decisions

1. TradingAgents-CN 目标运行环境是否统一到 Python 3.11。
2. Phase 1a 是否先做 `ArtifactBackend`，再接 `PipelineBackend`，还是一次完成两者。
3. `ExtractorConfig.cache_root` 默认目录是否使用 package-local `data/`，还是由调用方显式传入。
4. 是否在 `FieldValue` 增加 `evidence_snippet` 与 `evidence_kind`，用于 TradingAgents-CN 报告引用。
