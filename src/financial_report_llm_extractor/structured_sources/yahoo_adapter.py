"""Yahoo/yfinance source adapter using injected clients.

This module intentionally does not import ``yfinance``. Real clients are plugged
in later; unit tests use fixture clients so no external traffic is consumed.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Protocol

from financial_report_llm_extractor.models import Currency
from financial_report_llm_extractor.structured_sources.artifacts import (
    SourceArtifactStore,
    build_artifact_id,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
)


class YahooClient(Protocol):
    def get_financial_statement(
        self,
        *,
        ticker: str,
        statement_type: str,
    ) -> dict[str, object]: ...


class YahooAdapter:
    def __init__(self, *, client: YahooClient, artifact_store: SourceArtifactStore) -> None:
        self.client = client
        self.artifact_store = artifact_store

    def fetch_statement_inventory(
        self,
        *,
        ticker: str,
        market: str,
        statement_type: str,
        currency: Currency,
        unit: str,
    ) -> tuple[SourceInventoryRecord, ...]:
        payload = self.client.get_financial_statement(
            ticker=ticker,
            statement_type=statement_type,
        )
        artifact = self.artifact_store.write_json(
            source="yahoo",
            artifact_id=build_artifact_id(
                source="yahoo",
                market=market,
                ticker=ticker,
                artifact_type=statement_type,
            ),
            payload=payload,
        )
        metadata = _mapping(payload.get("metadata"))
        rows = list(_rows(payload.get("rows")))
        if not rows:
            evidence = SourceEvidence(
                source="yahoo",
                adapter="yahoo",
                function="get_financial_statement",
                artifact_id=artifact.artifact_id,
                raw_record_id=f"{ticker}:{market}:{statement_type}:missing",
                raw_field_name=statement_type,
            )
            record = SourceInventoryRecord(
                source="yahoo",
                market=market,
                ticker=ticker,
                statement_type=statement_type,
                period=None,
                raw_field_name=statement_type,
                raw_value=None,
                value_type="money",
                source_status="missing",
                currency=currency,
                unit=unit,
                source_evidence=(evidence,),
            )
            record.validate()
            return (record,)

        records: list[SourceInventoryRecord] = []
        for index, row in enumerate(rows):
            raw_field_name = str(row.get("field", ""))
            period = _optional_str(row.get("period"))
            evidence = SourceEvidence(
                source="yahoo",
                adapter="yahoo",
                function="get_financial_statement",
                artifact_id=artifact.artifact_id,
                raw_record_id=f"{ticker}:{market}:{statement_type}:{period}:{index}",
                raw_field_name=raw_field_name,
            )
            record = SourceInventoryRecord(
                source="yahoo",
                market=market,
                ticker=ticker,
                statement_type=statement_type,
                period=period,
                report_type=_optional_str(metadata.get("report_type")),
                raw_field_name=raw_field_name,
                raw_value=_raw_value(row.get("value")),
                parsed_numeric_value=_parse_decimal(row.get("value")),
                currency=currency,
                unit=unit,
                source_evidence=(evidence,),
            )
            record.validate()
            records.append(record)
        return tuple(records)


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _rows(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(row for row in value if isinstance(row, dict))


def _parse_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _raw_value(value: object) -> str | int | float | None:
    if value is None or isinstance(value, (str, int, float)):
        return value
    return str(value)
