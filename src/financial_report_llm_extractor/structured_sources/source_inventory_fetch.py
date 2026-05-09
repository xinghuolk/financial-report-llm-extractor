"""Per-(company, period) live source inventory fetch for evaluate-company.

Wraps real_source_validation adapter primitives with a (company, period_end,
market)-keyed sample builder, so each call produces a single-period
source_inventory.jsonl + summary in a deterministic out_dir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
)

ReportType = Literal["annual", "half_year", "quarterly", "ttm"]


@dataclass(frozen=True)
class PeriodSpec:
    period_end: date
    report_type: ReportType

    @classmethod
    def from_year(cls, year: int) -> "PeriodSpec":
        return cls(period_end=date(year, 12, 31), report_type="annual")

    @classmethod
    def from_period_end(
        cls, period_end: str, report_type: ReportType = "annual"
    ) -> "PeriodSpec":
        parsed = date.fromisoformat(period_end)
        return cls(period_end=parsed, report_type=report_type)


def select_records_for_period(
    records: tuple[SourceInventoryRecord, ...],
    period: PeriodSpec,
) -> tuple[SourceInventoryRecord, ...]:
    """按 PeriodSpec.period_end 过滤记录。

    fail-loud：如果记录中没有匹配 period 的 present 记录，raise ValueError。
    与现有 _select_latest_annual_records 不同 —— 不 silently fall back to latest。
    """
    target = period.period_end.isoformat()
    matching = tuple(
        r for r in records
        if r.period is not None and r.period.startswith(target)
    )
    has_present = any(r.source_status == "present" for r in matching)
    if not has_present:
        raise ValueError(
            f"no present records for period {target}; "
            f"available periods: {sorted({r.period for r in records if r.period})}"
        )
    return matching
