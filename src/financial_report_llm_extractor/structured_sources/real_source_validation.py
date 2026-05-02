"""Opt-in validation against real structured source clients."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol, cast

from financial_report_llm_extractor.models import Currency
from financial_report_llm_extractor.structured_sources.akshare_adapter import (
    AkshareAdapter,
)
from financial_report_llm_extractor.structured_sources.artifacts import (
    SourceArtifactStore,
    build_artifact_id,
    finalize_source_artifacts,
    read_source_inventory,
    write_source_inventory,
)
from financial_report_llm_extractor.structured_sources.capture_targets import (
    ProviderName,
    build_provider_field_capture_targets,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    load_source_mapping_catalog,
)
from financial_report_llm_extractor.structured_sources.export import (
    build_source_first_export,
    write_source_first_export_artifacts,
)
from financial_report_llm_extractor.structured_sources.field_inventory_summary import (
    write_provider_field_inventory_summary,
)
from financial_report_llm_extractor.structured_sources.mapping import (
    TurtleMappingResult,
    map_source_inventory,
    write_turtle_mapping_artifacts,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
    SourceName,
)
from financial_report_llm_extractor.structured_sources.reconciliation import (
    reconcile_mapped_fields,
    write_reconciliation_report,
)
from financial_report_llm_extractor.structured_sources.yahoo_adapter import (
    YahooAdapter,
)


Provider = ProviderName


class AkshareLikeClient(Protocol):
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


class YahooLikeClient(Protocol):
    def get_financial_statement(
        self,
        *,
        ticker: str,
        statement_type: str,
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class RealSourceValidationSample:
    provider: Provider
    market: str
    ticker: str
    statement_type: str
    currency: Currency
    unit: str
    exchange: str | None = None


@dataclass(frozen=True)
class RealSourceValidationResult:
    output_path: Path
    summary: dict[str, Any]
    records: tuple[SourceInventoryRecord, ...]


def run_real_source_validation(
    *,
    samples: tuple[RealSourceValidationSample, ...],
    catalog_path: Path,
    output_dir: Path,
    sample_set: str = "real_source_adapter",
    akshare_client: AkshareLikeClient | None = None,
    yahoo_client: YahooLikeClient | None = None,
) -> RealSourceValidationResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_store = SourceArtifactStore(output_dir / "source_artifacts")

    records: list[SourceInventoryRecord] = []
    source_errors: list[dict[str, str]] = []
    for sample in samples:
        try:
            records.extend(
                _records_for_sample(
                    _fetch_sample_records(
                        sample,
                        artifact_store,
                        akshare_client=akshare_client,
                        yahoo_client=yahoo_client,
                    ),
                    sample_set=sample_set,
                )
            )
        except Exception as exc:  # noqa: BLE001 - validation must archive failures
            error_record = _source_error_record(sample, artifact_store, str(exc))
            records.append(error_record)
            source_errors.append(
                {
                    "provider": sample.provider,
                    "market": sample.market,
                    "ticker": sample.ticker,
                    "statement_type": sample.statement_type,
                    "error": str(exc),
                }
            )

    write_source_inventory(output_dir / "source_inventory.jsonl", records)
    manifest = finalize_source_artifacts(
        artifact_root=output_dir / "source_artifacts",
        artifacts=artifact_store.artifacts,
        records=records,
        manifest_path=output_dir / "source_artifact_manifest.json",
    )

    return _write_validation_outputs(
        records=tuple(records),
        catalog_path=catalog_path,
        output_dir=output_dir,
        validation_mode="real_source_adapter",
        sample_set=sample_set,
        sample_count=len(samples),
        source_errors=source_errors,
        source_artifact_manifest_path=output_dir / "source_artifact_manifest.json",
        source_artifact_count=len(manifest.artifacts),
    )


def run_captured_source_validation(
    *,
    inventory_path: Path,
    catalog_path: Path,
    output_dir: Path,
) -> RealSourceValidationResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = read_source_inventory(inventory_path)
    write_source_inventory(output_dir / "source_inventory.jsonl", records)
    return _write_validation_outputs(
        records=records,
        catalog_path=catalog_path,
        output_dir=output_dir,
        validation_mode="captured_source_inventory",
        sample_set="captured_source_inventory",
        sample_count=1,
        source_errors=[],
    )


def _write_validation_outputs(
    *,
    records: tuple[SourceInventoryRecord, ...],
    catalog_path: Path,
    output_dir: Path,
    validation_mode: str,
    sample_set: str,
    sample_count: int,
    source_errors: list[dict[str, str]],
    source_artifact_manifest_path: Path | None = None,
    source_artifact_count: int | None = None,
) -> RealSourceValidationResult:
    catalog = load_source_mapping_catalog(catalog_path, priorities=("P0", "P1"))
    mapping = map_source_inventory(catalog, records)
    reconciliation = reconcile_mapped_fields(mapping)
    export = build_source_first_export(mapping, reconciliation, profile="source_only")

    write_turtle_mapping_artifacts(mapping, output_dir)
    write_reconciliation_report(reconciliation, output_dir / "reconciliation_report.json")
    write_source_first_export_artifacts(export, output_dir)
    provider_field_inventory_summary_path = (
        output_dir / "provider_field_inventory_summary.json"
    )
    write_provider_field_inventory_summary(
        provider_field_inventory_summary_path,
        records=records,
        sample_set=sample_set,
        source_artifact_count=source_artifact_count,
    )

    artifact_paths = {
        "source_inventory": str(output_dir / "source_inventory.jsonl"),
        "turtle_mapping": str(output_dir / "turtle_mapping.json"),
        "reconciliation_report": str(output_dir / "reconciliation_report.json"),
        "extraction_result": str(output_dir / "extraction_result.json"),
        "review_summary": str(output_dir / "review_summary.json"),
        "provider_field_inventory_summary": str(
            provider_field_inventory_summary_path
        ),
    }
    summary: dict[str, Any] = {
        "validation_mode": validation_mode,
        "status": "completed_with_source_errors" if source_errors else "completed",
        "sample_count": sample_count,
        "record_count": len(records),
        "source_errors": source_errors,
        "mapping_coverage": _mapping_coverage(mapping),
        "artifact_paths": artifact_paths,
    }
    if source_artifact_manifest_path is not None:
        artifact_paths["source_artifact_manifest"] = str(source_artifact_manifest_path)
        summary["source_artifact_count"] = source_artifact_count
    output_path = output_dir / "real_source_validation_summary.json"
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return RealSourceValidationResult(
        output_path=output_path,
        summary=summary,
        records=records,
    )


def _fetch_sample_records(
    sample: RealSourceValidationSample,
    artifact_store: SourceArtifactStore,
    *,
    akshare_client: AkshareLikeClient | None,
    yahoo_client: YahooLikeClient | None,
) -> tuple[SourceInventoryRecord, ...]:
    if sample.provider == "akshare":
        client = akshare_client or PandasAkshareClient(hk_default_currency=sample.currency)
        adapter = AkshareAdapter(client=client, artifact_store=artifact_store)
        if sample.market.upper() == "CN":
            return adapter.fetch_cn_statement_inventory(
                ticker=sample.ticker,
                exchange=sample.exchange or _default_cn_exchange(sample.ticker),
                statement_type=sample.statement_type,
                unit=sample.unit,
            )
        return adapter.fetch_hk_statement_inventory(
            ticker=sample.ticker,
            statement_type=sample.statement_type,
            unit=sample.unit,
        )

    yahoo_adapter = YahooAdapter(
        client=yahoo_client or YFinanceStatementClient(),
        artifact_store=artifact_store,
    )
    return yahoo_adapter.fetch_statement_inventory(
        ticker=sample.ticker,
        market=sample.market,
        statement_type=sample.statement_type,
        currency=sample.currency,
        unit=sample.unit,
    )


class PandasAkshareClient:
    def __init__(self, *, hk_default_currency: Currency = "unknown") -> None:
        self.hk_default_currency = hk_default_currency
        self._hk_report_dates: tuple[str, ...] = ()

    def stock_financial_hk_report_em(
        self,
        *,
        stock: str,
        symbol: str,
        indicator: str,
    ) -> list[dict[str, object]]:
        akshare = _import_module("akshare")
        frame = akshare.stock_financial_hk_report_em(
            stock=stock,
            symbol=symbol,
            indicator=indicator,
        )
        rows = _records_from_dataframe(frame)
        self._hk_report_dates = tuple(
            sorted(
                {
                    str(row["REPORT_DATE"])
                    for row in rows
                    if row.get("REPORT_DATE") is not None
                }
            )
        )
        return rows

    def stock_financial_hk_report_metadata(
        self,
        *,
        stock: str,
    ) -> list[dict[str, object]]:
        return [
            {
                "REPORT_DATE": report_date,
                "CURRENCY": self.hk_default_currency,
                "REPORT_TYPE": "annual",
            }
            for report_date in self._hk_report_dates
        ]

    def stock_balance_sheet_by_report_em(self, *, symbol: str) -> list[dict[str, object]]:
        akshare = _import_module("akshare")
        return _records_from_dataframe(akshare.stock_balance_sheet_by_report_em(symbol=symbol))

    def stock_profit_sheet_by_report_em(self, *, symbol: str) -> list[dict[str, object]]:
        akshare = _import_module("akshare")
        return _records_from_dataframe(akshare.stock_profit_sheet_by_report_em(symbol=symbol))

    def stock_cash_flow_sheet_by_report_em(self, *, symbol: str) -> list[dict[str, object]]:
        akshare = _import_module("akshare")
        return _records_from_dataframe(akshare.stock_cash_flow_sheet_by_report_em(symbol=symbol))


class YFinanceStatementClient:
    def get_financial_statement(
        self,
        *,
        ticker: str,
        statement_type: str,
    ) -> dict[str, object]:
        yfinance = _import_module("yfinance")
        ticker_obj = yfinance.Ticker(ticker)
        frame = _yfinance_statement_frame(ticker_obj, statement_type)
        return {
            "metadata": {
                "currency": _ticker_currency(ticker_obj),
                "report_type": "annual",
            },
            "rows": _yfinance_rows_from_dataframe(frame),
        }


def _source_error_record(
    sample: RealSourceValidationSample,
    artifact_store: SourceArtifactStore,
    error: str,
) -> SourceInventoryRecord:
    source = cast(SourceName, sample.provider)
    artifact = artifact_store.write_json(
        source=source,
        artifact_id=build_artifact_id(
            source=source,
            market=sample.market,
            ticker=sample.ticker,
            artifact_type=f"{sample.statement_type}_source_error",
        ),
        payload={
            "provider": sample.provider,
            "market": sample.market,
            "ticker": sample.ticker,
            "statement_type": sample.statement_type,
            "error": error,
        },
    )
    evidence = SourceEvidence(
        source=source,
        adapter=sample.provider,
        function=sample.statement_type,
        artifact_id=artifact.artifact_id,
        raw_record_id=f"{sample.provider}:{sample.ticker}:{sample.statement_type}:error",
        raw_field_name=sample.statement_type,
    )
    record = SourceInventoryRecord(
        source=source,
        market=sample.market,
        ticker=sample.ticker,
        statement_type=sample.statement_type,
        period=None,
        raw_field_name=sample.statement_type,
        raw_value=None,
        source_status="source_error",
        currency=sample.currency,
        unit=sample.unit,
        source_evidence=(evidence,),
    )
    record.validate()
    return record


def _records_from_dataframe(frame: object) -> list[dict[str, object]]:
    if hasattr(frame, "to_dict"):
        rows = frame.to_dict(orient="records")
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _select_latest_annual_records(
    records: tuple[SourceInventoryRecord, ...],
) -> tuple[SourceInventoryRecord, ...]:
    present_periods = {
        record.period
        for record in records
        if record.source_status == "present"
        and record.period is not None
        and _is_annual_period(record.period)
    }
    if not present_periods:
        return records
    target_period = sorted(present_periods)[-1]
    return tuple(
        record
        for record in records
        if record.source_status != "present" or record.period == target_period
    )


def _select_latest_annual_period_records(
    records: tuple[SourceInventoryRecord, ...],
    *,
    limit: int,
) -> tuple[SourceInventoryRecord, ...]:
    annual_periods = {
        record.period
        for record in records
        if record.source_status == "present"
        and record.period is not None
        and _is_annual_period(record.period)
    }
    if annual_periods:
        target_periods = set(sorted(annual_periods)[-limit:])
    else:
        present_periods = {
            record.period
            for record in records
            if record.source_status == "present" and record.period is not None
        }
        if not present_periods:
            return records
        target_periods = set(sorted(present_periods)[-limit:])
    return tuple(
        record
        for record in records
        if record.source_status != "present" or record.period in target_periods
    )


def _records_for_sample(
    records: tuple[SourceInventoryRecord, ...],
    *,
    sample_set: str,
) -> tuple[SourceInventoryRecord, ...]:
    if sample_set == "provider_field_baseline":
        return _select_latest_annual_period_records(records, limit=5)
    return _select_latest_annual_records(records)


def _is_annual_period(period: str) -> bool:
    date_part = period.split(" ")[0]
    return date_part.endswith("-12-31")


def _yfinance_statement_frame(ticker_obj: object, statement_type: str) -> object:
    if statement_type == "income_statement":
        return getattr(ticker_obj, "income_stmt")
    if statement_type == "balance_sheet":
        return getattr(ticker_obj, "balance_sheet")
    if statement_type == "cash_flow":
        return getattr(ticker_obj, "cashflow")
    raise ValueError(f"unsupported yahoo statement_type: {statement_type}")


def _yfinance_rows_from_dataframe(frame: object) -> list[dict[str, object]]:
    if getattr(frame, "empty", True):
        return []
    rows: list[dict[str, object]] = []
    iterrows = getattr(frame, "iterrows", None)
    if iterrows is None:
        return []
    for field_name, series in iterrows():
        for period, raw_value in series.items():
            value = _jsonable_number(raw_value)
            if value is None:
                continue
            rows.append(
                {
                    "field": str(field_name),
                    "period": _period_to_string(period),
                    "value": value,
                }
            )
    return rows


def _ticker_currency(ticker_obj: object) -> Currency:
    for source in (_safe_getattr(ticker_obj, "fast_info"), _safe_getattr(ticker_obj, "info")):
        if isinstance(source, dict):
            currency = str(source.get("currency", "")).upper()
            if currency in {"CNY", "HKD", "USD"}:
                return cast(Currency, currency)
    return "unknown"


def _safe_getattr(obj: object, name: str) -> object:
    try:
        return getattr(obj, name)
    except Exception:  # noqa: BLE001 - metadata failures should not block rows
        return None


def _jsonable_number(value: object) -> str | None:
    text = str(value)
    if text in {"", "None", "NaN", "nan", "NaT"}:
        return None
    try:
        return str(Decimal(text))
    except (InvalidOperation, ValueError):
        return text


def _period_to_string(value: object) -> str:
    if hasattr(value, "date"):
        return str(value.date())
    return str(value)


def _mapping_coverage(mapping: TurtleMappingResult) -> dict[str, object]:
    covered = [
        field_id
        for field_id, field in mapping.fields.items()
        if field.status in {"present", "derived"}
    ]
    total = len(mapping.fields)
    return {
        "covered_fields": sorted(covered),
        "covered_count": len(covered),
        "total_fields": total,
        "coverage_ratio": len(covered) / total if total else 0.0,
    }


def _default_cn_exchange(ticker: str) -> str:
    return "SH" if ticker.startswith("6") else "SZ"


def _import_module(name: str) -> Any:
    import importlib

    return importlib.import_module(name)


def build_default_validation_samples(
    *,
    providers: tuple[Provider, ...],
    akshare_cn_statements: tuple[str, ...] = ("income_statement",),
) -> tuple[RealSourceValidationSample, ...]:
    samples: list[RealSourceValidationSample] = []
    if "akshare" in providers:
        samples.extend(
            RealSourceValidationSample(
                provider="akshare",
                market="CN",
                ticker="600519",
                statement_type=statement_type,
                currency="CNY",
                unit="yuan",
                exchange="SH",
            )
            for statement_type in akshare_cn_statements
        )
    if "yahoo" in providers:
        samples.append(
            RealSourceValidationSample(
                provider="yahoo",
                market="HK",
                ticker="0001.HK",
                statement_type="income_statement",
                currency="HKD",
                unit="raw",
            )
        )
    return tuple(samples)


def build_provider_field_capture_samples(
    providers: tuple[ProviderName, ...] = ("akshare", "yahoo"),
) -> tuple[RealSourceValidationSample, ...]:
    return tuple(
        RealSourceValidationSample(
            provider=target.provider,
            market=target.market,
            ticker=target.provider_ticker,
            statement_type=target.statement_type,
            currency=target.currency,
            unit=target.unit,
            exchange=target.exchange,
        )
        for target in build_provider_field_capture_targets(providers=providers)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("tmp/runs/real_source_validation"),
    )
    parser.add_argument(
        "--providers",
        default="akshare",
        help="Comma-separated providers: akshare,yahoo",
    )
    parser.add_argument(
        "--akshare-cn-statements",
        default="income_statement",
        help="Comma-separated AKShare CN statements to request.",
    )
    parser.add_argument(
        "--inventory-fixture",
        type=Path,
        help="Use saved source_inventory.jsonl instead of calling real providers.",
    )
    parser.add_argument(
        "--sample-set",
        choices=("default", "provider_field_baseline"),
        default="default",
        help="Real-provider sample set to request.",
    )
    args = parser.parse_args()
    if args.inventory_fixture is not None:
        result = run_captured_source_validation(
            inventory_path=args.inventory_fixture,
            catalog_path=args.catalog,
            output_dir=args.out_dir,
        )
    else:
        providers = tuple(
            cast(Provider, provider.strip())
            for provider in args.providers.split(",")
            if provider.strip()
        )
        akshare_cn_statements = tuple(
            statement.strip()
            for statement in args.akshare_cn_statements.split(",")
            if statement.strip()
        )
        if args.sample_set == "provider_field_baseline":
            samples = build_provider_field_capture_samples(providers=providers)
        else:
            samples = build_default_validation_samples(
                providers=providers,
                akshare_cn_statements=akshare_cn_statements,
            )
        result = run_real_source_validation(
            samples=samples,
            catalog_path=args.catalog,
            output_dir=args.out_dir,
            sample_set=args.sample_set,
        )
    print(json.dumps(result.summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
