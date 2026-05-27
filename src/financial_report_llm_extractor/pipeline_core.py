"""In-process pipeline orchestration: fetch + evaluate + auto-index.

Shared by `cli.py pipeline` subcommand and `client.FinancialReportClient`.
Returns a status dict; raises on internal pipeline errors (callers wrap as
needed).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from financial_report_llm_extractor.cache.db import init_db
from financial_report_llm_extractor.cache.db_query import query_extraction
from financial_report_llm_extractor.cache.indexer import index_run
from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
    PeriodSpec,
    ReportType,
)


def _resolve_period(
    *,
    period_end: str | None,
    year: int | None,
    report_type: ReportType,
) -> PeriodSpec:
    """Resolve period from either ISO period_end or year."""
    if year is not None and period_end is not None:
        raise ValueError("year and period_end are mutually exclusive")
    if year is not None:
        return PeriodSpec.from_year(year)
    if period_end is not None:
        return PeriodSpec.from_period_end(period_end, report_type)
    raise ValueError("one of year or period_end is required")


def run_pipeline(
    *,
    company: str,
    period_end: str | None = None,
    year: int | None = None,
    market: str,
    report_type: ReportType = "annual",
    db_path: Path,
    out_dir: Path,
    catalog_path: Path,
    taxonomy_path: Path,
    priorities: tuple[str, ...] = ("P0", "P1", "P2", "P3", "P4"),
    pdf_path: Path | None = None,
    llm_config_path: Path | None = None,
    force: bool = False,
    no_cache: bool = False,
    subscription_token: str | None = None,
) -> dict[str, Any]:
    """Run the DB-aware pipeline. Returns status dict.

    Status values:
      "cache_hit"  — DB has matching extraction (skipped fresh run)
      "fresh_run"  — fetch + evaluate + index completed
    """
    period = _resolve_period(
        period_end=period_end, year=year, report_type=report_type,
    )

    taxonomy_doc = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    catalog_version = str(taxonomy_doc.get("version", "unknown"))
    period_end_str = period.period_end.isoformat()

    init_db(db_path)
    if not force:
        hit = query_extraction(
            db_path=db_path,
            company=company,
            period_end=period_end_str,
            market=market,
        )
        if hit is not None and hit.get("catalog_version") == catalog_version:
            return {
                "status": "cache_hit",
                "company": company,
                "period_end": period_end_str,
                "market": market,
                "catalog_version": catalog_version,
                "artifact_path": hit.get("artifact_path"),
                "field_count": len(hit.get("fields", {})),
            }

    # Cache miss / force: run fetch + evaluate + index.
    # Lazy imports to avoid slow startup for callers that only need the
    # cache lookup path.
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        run_company_evaluation,
    )
    from financial_report_llm_extractor.structured_sources.real_source_validation import (
        PandasAkshareClient,
        YFinanceStatementClient,
    )
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        fetch_source_inventory,
        hk_issuer_financial_currency,
    )

    cache_root: Path | None = None if no_cache else Path("tmp/.cache")
    providers: tuple[str, ...] = ("akshare", "yahoo")

    # Construct provider clients (mirrors _run_fetch_source_inventory in cli.py).
    # HK AKShare records get stamped with the issuer's financial-reporting
    # currency (Phase HK-B.5.1); CN stays "unknown".
    akshare_hk_currency = (
        hk_issuer_financial_currency(company) if market == "HK" else "unknown"
    )
    akshare_client = PandasAkshareClient(hk_default_currency=akshare_hk_currency)
    yahoo_client = YFinanceStatementClient()

    fetch_result = fetch_source_inventory(
        company=company,
        period=period,
        market=market,  # type: ignore[arg-type]
        providers=providers,  # type: ignore[arg-type]
        akshare_client=akshare_client,
        yahoo_client=yahoo_client,
        out_dir=out_dir,
        catalog_path=catalog_path,
        cache_root=cache_root,
        ttl_hours=24,
    )

    run_company_evaluation(
        company=company,
        period=period,
        market=market,
        inventory_path=fetch_result.inventory_path,
        inventory_summary_path=fetch_result.summary_path,
        catalog_path=catalog_path,
        taxonomy_path=taxonomy_path,
        pdf_path=pdf_path,
        llm_config_path=llm_config_path,
        priorities=priorities,
        out_dir=out_dir,
        # no_cache maps to combined provider+llm bypass: pass as cache_root
        cache_root=cache_root,
        subscription_token=subscription_token,
    )

    priority_map = {
        fid: str(info.get("priority", ""))
        for fid, info in taxonomy_doc.get("fields", {}).items()
    }
    n_fields = index_run(
        run_dir=out_dir,
        db_path=db_path,
        catalog_version=catalog_version,
        priority_map=priority_map,
    )

    return {
        "status": "fresh_run",
        "company": company,
        "period_end": period_end_str,
        "market": market,
        "catalog_version": catalog_version,
        "artifact_path": str(out_dir),
        "field_count": n_fields,
    }
