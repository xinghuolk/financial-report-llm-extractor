"""AKShare source adapter using injected clients.

This module intentionally does not import ``akshare``. Real API clients are
plugged in later; unit tests use fixture clients to avoid consuming API traffic.
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


HK_STATEMENT_SYMBOLS = {
    "balance_sheet": "资产负债表",
    "income_statement": "利润表",
    "cash_flow": "现金流量表",
}

CN_STATEMENT_FUNCTIONS = {
    "balance_sheet": "stock_balance_sheet_by_report_em",
    "income_statement": "stock_profit_sheet_by_report_em",
    "cash_flow": "stock_cash_flow_sheet_by_report_em",
}


class AkshareClient(Protocol):
    def stock_financial_hk_report_em(
        self,
        *,
        stock: str,
        symbol: str,
        indicator: str,
    ) -> list[dict[str, object]]: ...

    def stock_financial_hk_report_metadata(
        self,
        *,
        stock: str,
    ) -> list[dict[str, object]]: ...

    def stock_balance_sheet_by_report_em(
        self,
        *,
        symbol: str,
    ) -> list[dict[str, object]]: ...

    def stock_profit_sheet_by_report_em(
        self,
        *,
        symbol: str,
    ) -> list[dict[str, object]]: ...

    def stock_cash_flow_sheet_by_report_em(
        self,
        *,
        symbol: str,
    ) -> list[dict[str, object]]: ...


class AkshareAdapter:
    def __init__(self, *, client: AkshareClient, artifact_store: SourceArtifactStore) -> None:
        self.client = client
        self.artifact_store = artifact_store

    def fetch_hk_statement_inventory(
        self,
        *,
        ticker: str,
        statement_type: str,
        unit: str,
    ) -> tuple[SourceInventoryRecord, ...]:
        symbol = HK_STATEMENT_SYMBOLS[statement_type]
        rows = list(
            self.client.stock_financial_hk_report_em(
                stock=ticker,
                symbol=symbol,
                indicator="年度",
            )
        )
        metadata_rows = list(self.client.stock_financial_hk_report_metadata(stock=ticker))
        metadata_by_date = {
            str(row.get("REPORT_DATE")): row for row in metadata_rows if row.get("REPORT_DATE")
        }
        artifact = self.artifact_store.write_json(
            source="akshare",
            artifact_id=build_artifact_id(
                source="akshare",
                market="HK",
                ticker=ticker,
                artifact_type=statement_type,
            ),
            payload={"rows": rows, "metadata": metadata_rows},
        )

        records: list[SourceInventoryRecord] = []
        for index, row in enumerate(rows):
            period = _optional_str(row.get("REPORT_DATE"))
            metadata = metadata_by_date.get(period or "", {})
            raw_field_name = str(row.get("STD_ITEM_NAME", ""))
            raw_field_code = _optional_str(row.get("STD_ITEM_CODE"))
            evidence = SourceEvidence(
                source="akshare",
                adapter="akshare",
                function="stock_financial_hk_report_em",
                artifact_id=artifact.artifact_id,
                raw_record_id=f"{ticker}:HK:{statement_type}:{period}:{index}",
                raw_field_name=raw_field_name,
                raw_field_code=raw_field_code,
            )
            record = SourceInventoryRecord(
                source="akshare",
                market="HK",
                ticker=ticker,
                statement_type=statement_type,
                period=period,
                report_type=_normalize_report_type(_optional_str(metadata.get("REPORT_TYPE"))),
                fiscal_year=_optional_str(row.get("FISCAL_YEAR")),
                account_standard=_optional_str(metadata.get("ACCOUNT_STANDARD")),
                raw_field_name=raw_field_name,
                raw_field_code=raw_field_code,
                raw_value=_raw_value(row.get("AMOUNT")),
                parsed_numeric_value=_parse_decimal(row.get("AMOUNT")),
                currency=_normalize_currency(metadata.get("CURRENCY")),
                unit=unit,
                source_evidence=(evidence,),
            )
            record.validate()
            records.append(record)
        return tuple(records)

    def fetch_cn_statement_inventory(
        self,
        *,
        ticker: str,
        exchange: str,
        statement_type: str,
        unit: str,
    ) -> tuple[SourceInventoryRecord, ...]:
        function_name = CN_STATEMENT_FUNCTIONS[statement_type]
        symbol = f"{exchange.upper()}{ticker}"
        function = getattr(self.client, function_name)
        rows = list(function(symbol=symbol))
        artifact = self.artifact_store.write_json(
            source="akshare",
            artifact_id=build_artifact_id(
                source="akshare",
                market="CN",
                ticker=ticker,
                artifact_type=statement_type,
            ),
            payload={"rows": rows},
        )

        records: list[SourceInventoryRecord] = []
        for index, row in enumerate(rows):
            period = _optional_str(row.get("REPORT_DATE"))
            raw_field_name = str(row.get("STD_ITEM_NAME", ""))
            raw_field_code = _optional_str(row.get("STD_ITEM_CODE"))
            evidence = SourceEvidence(
                source="akshare",
                adapter="akshare",
                function=function_name,
                artifact_id=artifact.artifact_id,
                raw_record_id=f"{ticker}:CN:{statement_type}:{period}:{index}",
                raw_field_name=raw_field_name,
                raw_field_code=raw_field_code,
            )
            record = SourceInventoryRecord(
                source="akshare",
                market="CN",
                ticker=ticker,
                statement_type=statement_type,
                period=period,
                report_type="annual",
                raw_field_name=raw_field_name,
                raw_field_code=raw_field_code,
                raw_value=_raw_value(row.get("AMOUNT")),
                parsed_numeric_value=_parse_decimal(row.get("AMOUNT")),
                currency="CNY",
                unit=unit,
                source_evidence=(evidence,),
            )
            record.validate()
            records.append(record)
        return tuple(records)


def _normalize_currency(value: object) -> Currency:
    text = str(value or "").upper()
    if text in {"CNY", "RMB"}:
        return "CNY"
    if text in {"HKD", "HK$"}:
        return "HKD"
    if text in {"USD", "US$"}:
        return "USD"
    return "unknown"


def _normalize_report_type(value: str | None) -> str | None:
    if value in {"年报", "annual", "Annual"}:
        return "annual"
    return value


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
