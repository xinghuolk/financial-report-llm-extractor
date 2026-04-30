"""Core data contracts for evidence-grounded extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal


ExtractionStatus = Literal[
    "present",
    "missing",
    "ambiguous",
    "not_applicable",
    "extraction_failed",
]


Currency = Literal["CNY", "HKD", "USD", "unknown", "ambiguous"]
ValueType = Literal["text", "number", "money"]
ChunkKind = Literal[
    "page_text",
    "paragraph",
    "section_window",
    "layout_line",
    "statement_line",
    "table_fragment",
    "statement_table",
    "table_row",
]


@dataclass(frozen=True)
class Evidence:
    page: int
    chunk_id: str
    block_id: str
    snippet: str
    table_id: str | None = None
    cell_id: str | None = None
    bbox: tuple[float, float, float, float] | None = None

    def validate(self) -> None:
        if self.page <= 0:
            raise ValueError("page must be positive")
        if not self.chunk_id:
            raise ValueError("chunk_id is required")
        if not self.block_id:
            raise ValueError("block_id is required")
        if not self.snippet:
            raise ValueError("snippet is required")


@dataclass(frozen=True)
class MoneyAmount:
    value_raw: str
    value: Decimal
    currency: Currency
    unit: str
    unit_multiplier: Decimal
    normalized_value: Decimal
    normalized_unit: Currency

    def validate(self) -> None:
        if not self.value_raw:
            raise ValueError("value_raw is required")
        if not self.unit:
            raise ValueError("unit is required")
        if self.unit_multiplier <= 0:
            raise ValueError("unit_multiplier must be positive")
        expected = self.value * self.unit_multiplier
        if self.normalized_value != expected:
            raise ValueError("normalized_value must equal value * unit_multiplier")
        if self.currency in {"CNY", "HKD", "USD"} and self.normalized_unit != self.currency:
            raise ValueError("normalized_unit must match currency")


@dataclass(frozen=True)
class ExtractedItem:
    field_id: str
    status: ExtractionStatus
    value: str | int | float | None = None
    value_type: ValueType = "number"
    money: MoneyAmount | None = None
    unit: str | None = None
    period: str | None = None
    scope: str = "unknown"
    confidence: float | None = None
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        if self.status == "present" and not self.evidence:
            raise ValueError("present extracted items must include evidence")
        if self.status == "present" and self.value_type == "money" and self.money is None:
            raise ValueError("present money items must include money")
        if self.money is not None:
            self.money.validate()
        for evidence in self.evidence:
            evidence.validate()


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    kind: ChunkKind
    page_start: int
    page_end: int
    block_ids: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        if not self.chunk_id:
            raise ValueError("chunk_id is required")
        if self.page_start <= 0:
            raise ValueError("page_start must be positive")
        if self.page_end <= 0:
            raise ValueError("page_end must be positive")
        if self.page_start > self.page_end:
            raise ValueError("page_start must be <= page_end")
        if not self.block_ids:
            raise ValueError("block_ids is required")
        if any(not block_id for block_id in self.block_ids):
            raise ValueError("block_ids cannot contain empty values")


@dataclass(frozen=True)
class ExtractionRun:
    source_pdf_hash: str
    parser_version: str
    chunker_version: str
    llm_provider: str | None = None
    llm_model: str | None = None
    prompt_version: str | None = None
    schema_version: str | None = None
    artifact_paths: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        if not self.source_pdf_hash:
            raise ValueError("source_pdf_hash is required")
        if not self.parser_version:
            raise ValueError("parser_version is required")
        if not self.chunker_version:
            raise ValueError("chunker_version is required")
        if any(not artifact_path for artifact_path in self.artifact_paths):
            raise ValueError("artifact_paths cannot contain empty values")
