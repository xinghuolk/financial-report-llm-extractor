"""get_extraction() behavior across RefreshPolicy × Staleness × LLM filter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _seed_db_with_fixture(
    tmp_path: Path,
    catalog_version_override: str | None = None,
) -> Path:
    """Seed DB with the cache_sample_run fixture; return db_path."""
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.cache.indexer import index_run

    db_path = tmp_path / "out.db"
    init_db(db_path)

    fixture_dir = Path(__file__).parent / "fixtures" / "cache_sample_run"
    tax_path = Path("field_catalog/turtle_v015_field_taxonomy.json")
    taxonomy_doc = json.loads(tax_path.read_text(encoding="utf-8"))
    catalog_version = catalog_version_override or str(
        taxonomy_doc.get("version", "unknown")
    )
    priority_map = {
        fid: str(info.get("priority", ""))
        for fid, info in taxonomy_doc.get("fields", {}).items()
    }
    index_run(
        run_dir=fixture_dir, db_path=db_path,
        catalog_version=catalog_version, priority_map=priority_map,
    )
    return db_path


def test_get_extraction_cache_only_db_miss_returns_missing(
    tmp_path: Path,
) -> None:
    """CACHE_ONLY + DB miss → staleness=MISSING, fields={}, no pipeline."""
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        FinancialReportClient,
        RefreshPolicy,
        Staleness,
    )

    db_path = tmp_path / "empty.db"
    init_db(db_path)
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    result = client.get_extraction(
        company="600519", period_end="2024-12-31", market="CN",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
    )
    assert result.staleness == Staleness.MISSING
    assert result.fields == {}


def test_get_extraction_cache_only_hit_returns_fresh(
    tmp_path: Path,
) -> None:
    """CACHE_ONLY + DB hit + matching catalog_version → FRESH."""
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        FinancialReportClient,
        RefreshPolicy,
        Staleness,
    )

    db_path = _seed_db_with_fixture(tmp_path)
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    result = client.get_extraction(
        company="600519", period_end="2024-12-31", market="CN",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
    )
    assert result.staleness == Staleness.FRESH
    assert "revenue" in result.fields


def test_get_extraction_cache_only_stale_returns_stale_with_data(
    tmp_path: Path,
) -> None:
    """CACHE_ONLY + DB hit + mismatched catalog_version → STALE,
    fields still returned."""
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        FinancialReportClient,
        RefreshPolicy,
        Staleness,
    )

    # Seed with a stale catalog_version
    db_path = _seed_db_with_fixture(tmp_path, catalog_version_override="stale-v0")
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    result = client.get_extraction(
        company="600519", period_end="2024-12-31", market="CN",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
    )
    assert result.staleness == Staleness.STALE
    assert "revenue" in result.fields, "STALE must still return fields"


def test_get_extraction_decimal_value_preserved(tmp_path: Path) -> None:
    """Critical acceptance test: Decimal precision preserved end-to-end."""
    from decimal import Decimal
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        FinancialReportClient,
        RefreshPolicy,
    )

    db_path = _seed_db_with_fixture(tmp_path)
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    result = client.get_extraction(
        company="600519", period_end="2024-12-31", market="CN",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
    )
    revenue = result.fields["revenue"]
    assert isinstance(revenue.value, Decimal), (
        f"expected Decimal, got {type(revenue.value).__name__}"
    )
    assert revenue.value == Decimal("170899152276.34")


def test_get_extraction_extraction_id_stable(tmp_path: Path) -> None:
    """extraction_id is reproducible from result metadata."""
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        FinancialReportClient,
        RefreshPolicy,
        compute_extraction_id,
    )

    db_path = _seed_db_with_fixture(tmp_path)
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    result = client.get_extraction(
        company="600519", period_end="2024-12-31", market="CN",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
    )
    expected = compute_extraction_id(
        company=result.company,
        period_end=result.period_end,
        market=result.market,
        catalog_version=result.catalog_version,
        generated_at=result.generated_at,
    )
    assert result.extraction_id == expected


def test_get_extraction_include_llm_supplement_false_filters_llm_fields(
    tmp_path: Path,
) -> None:
    """include_llm_supplement=False: LLM fields returned as UNAVAILABLE
    placeholder (still in dict, not silently dropped)."""
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        ExtractorConfig,
        FinancialReportClient,
        RefreshPolicy,
    )

    db_path = _seed_db_with_fixture(tmp_path)
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    result = client.get_extraction(
        company="600519", period_end="2024-12-31", market="CN",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
        include_llm_supplement=False,  # default but explicit
    )
    # audit_opinion in fixture is bucket=llm_supplement_present
    audit = result.fields["audit_opinion"]
    assert audit.confidence == ConfidenceLevel.UNAVAILABLE
    assert audit.value is None
    assert audit.raw_bucket == "llm_supplement_present"
    assert audit.reason == "llm_supplement_filtered"


def test_get_extraction_include_llm_supplement_true_keeps_llm_fields(
    tmp_path: Path,
) -> None:
    """include_llm_supplement=True: LLM fields returned with original value."""
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        ExtractorConfig,
        FinancialReportClient,
        RefreshPolicy,
    )

    db_path = _seed_db_with_fixture(tmp_path)
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    result = client.get_extraction(
        company="600519", period_end="2024-12-31", market="CN",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
        include_llm_supplement=True,
    )
    audit = result.fields["audit_opinion"]
    assert audit.confidence == ConfidenceLevel.LLM_SUPPLEMENT
    assert audit.value is not None  # fixture has actual opinion text


def test_get_extraction_invalid_market_raises(tmp_path: Path) -> None:
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        ExtractorError,
        FinancialReportClient,
        RefreshPolicy,
    )

    db_path = _seed_db_with_fixture(tmp_path)
    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    with pytest.raises(ExtractorError) as excinfo:
        client.get_extraction(
            company="600519", period_end="2024-12-31", market="US",
            refresh_policy=RefreshPolicy.CACHE_ONLY,
        )
    assert excinfo.value.reason == "unsupported_market"
