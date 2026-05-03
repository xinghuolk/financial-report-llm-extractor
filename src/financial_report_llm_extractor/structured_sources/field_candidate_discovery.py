"""Provider raw field candidate discovery for Turtle mappings."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Iterable, Literal

from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
    SourceName,
)

CandidateStrength = Literal["strong", "medium", "weak"]
FieldCandidateStatus = Literal[
    "has_candidates",
    "no_candidates",
    "not_applicable",
    "catalog_gap",
]

_COMMON_WORDS = {
    "and",
    "the",
    "of",
    "from",
    "to",
    "for",
    "net",
    "total",
}


@dataclass(frozen=True)
class ProviderRawField:
    source: SourceName
    statement_type: str
    raw_field_name: str
    raw_field_code: str | None
    normalized_names: tuple[str, ...]
    normalized_codes: tuple[str, ...]
    tickers: tuple[str, ...]
    periods: tuple[str, ...]
    record_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class _RawFieldBucket:
    source: SourceName
    statement_type: str
    raw_field_name: str
    raw_field_code: str | None
    tickers: set[str]
    periods: set[str]
    record_count: int


def normalize_match_text(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if re.search(r"[\u4e00-\u9fff]", text):
        return re.sub(r"\s+", "", text)
    text = text.replace("_", " ")
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"[^0-9A-Za-z]+", " ", text)
    return " ".join(text.lower().split())


def build_provider_raw_field_index(
    records: Iterable[SourceInventoryRecord],
) -> dict[tuple[str, str, str, str | None], ProviderRawField]:
    grouped: dict[tuple[str, str, str, str | None], _RawFieldBucket] = {}
    for record in records:
        if record.source_status != "present":
            continue
        key = (
            record.source,
            record.statement_type,
            record.raw_field_name,
            record.raw_field_code,
        )
        bucket = grouped.setdefault(
            key,
            _RawFieldBucket(
                source=record.source,
                statement_type=record.statement_type,
                raw_field_name=record.raw_field_name,
                raw_field_code=record.raw_field_code,
                tickers=set(),
                periods=set(),
                record_count=0,
            ),
        )
        bucket.tickers.add(record.ticker)
        if record.period is not None:
            bucket.periods.add(record.period)
        bucket.record_count += 1

    index: dict[tuple[str, str, str, str | None], ProviderRawField] = {}
    for key, bucket in grouped.items():
        raw_field_name = bucket.raw_field_name
        raw_field_code = bucket.raw_field_code
        normalized_names = tuple(
            value
            for value in (normalize_match_text(raw_field_name),)
            if value
        )
        normalized_codes = tuple(
            value
            for value in (
                (
                    normalize_match_text(raw_field_code)
                    if isinstance(raw_field_code, str)
                    else ""
                ),
            )
            if value
        )
        index[key] = ProviderRawField(
            source=bucket.source,
            statement_type=bucket.statement_type,
            raw_field_name=raw_field_name,
            raw_field_code=raw_field_code,
            normalized_names=normalized_names,
            normalized_codes=normalized_codes,
            tickers=tuple(sorted(bucket.tickers)),
            periods=tuple(sorted(bucket.periods)),
            record_count=bucket.record_count,
        )
    return index
