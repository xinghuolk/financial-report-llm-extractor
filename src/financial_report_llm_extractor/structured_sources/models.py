"""Data contracts for source-first financial extraction."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Literal

from financial_report_llm_extractor.models import Currency


SourceName = Literal["akshare", "yahoo", "fixture"]
SourceStatus = Literal["present", "missing", "ambiguous", "source_error", "unsupported"]
SourceValueType = Literal["money", "number", "percent", "text", "derived"]


@dataclass(frozen=True)
class SourceEvidence:
    source: SourceName
    adapter: str
    function: str
    artifact_id: str
    raw_record_id: str
    raw_field_name: str
    raw_field_code: str | None = None
    retrieved_at: str | None = None
    provider_version: str | None = None

    def validate(self) -> None:
        if not self.source:
            raise ValueError("source is required")
        if not self.adapter:
            raise ValueError("adapter is required")
        if not self.function:
            raise ValueError("function is required")
        if not self.artifact_id:
            raise ValueError("artifact_id is required")
        if not self.raw_record_id:
            raise ValueError("raw_record_id is required")
        if not self.raw_field_name:
            raise ValueError("raw_field_name is required")

    def to_dict(self) -> dict[str, str | None]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class SourceArtifact:
    source: SourceName
    artifact_id: str
    path: str
    content_type: str

    def validate(self) -> None:
        if not self.source:
            raise ValueError("source is required")
        if not self.artifact_id:
            raise ValueError("artifact_id is required")
        if not self.path:
            raise ValueError("path is required")
        if not self.content_type:
            raise ValueError("content_type is required")


@dataclass(frozen=True)
class SourceInventoryRecord:
    source: SourceName
    market: str
    ticker: str
    statement_type: str
    period: str | None
    raw_field_name: str
    raw_value: str | int | float | None
    parsed_numeric_value: Decimal | None = None
    value_type: SourceValueType = "money"
    source_status: SourceStatus = "present"
    report_type: str | None = None
    fiscal_year: str | None = None
    scope: str = "unknown"
    account_standard: str | None = None
    currency: Currency = "unknown"
    unit: str | None = None
    raw_field_code: str | None = None
    source_evidence: tuple[SourceEvidence, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        if not self.source:
            raise ValueError("source is required")
        if not self.market:
            raise ValueError("market is required")
        if not self.ticker:
            raise ValueError("ticker is required")
        if not self.statement_type:
            raise ValueError("statement_type is required")
        if not self.raw_field_name and self.source_status == "present":
            raise ValueError("raw_field_name is required for present source records")
        if self.value_type == "money" and self.source_status == "present":
            if self.currency in {"unknown", "ambiguous"} or not self.unit:
                raise ValueError("money source records require currency and unit")
        if self.source_status == "present" and not self.source_evidence:
            raise ValueError("present source records require source_evidence")
        for evidence in self.source_evidence:
            evidence.validate()

    def to_dict(self) -> dict[str, object]:
        self.validate()
        payload = asdict(self)
        if self.parsed_numeric_value is not None:
            payload["parsed_numeric_value"] = str(self.parsed_numeric_value)
        return payload
