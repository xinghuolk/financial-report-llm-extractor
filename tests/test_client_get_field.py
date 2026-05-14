"""get_field() behavior: known field, unknown field (raise),
LLM filter consistent with get_extraction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _seed_db_and_client(tmp_path: Path):
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.cache.indexer import index_run
    from financial_report_llm_extractor.client import (
        ExtractorConfig,
        FinancialReportClient,
    )

    db_path = tmp_path / "out.db"
    init_db(db_path)

    fixture_dir = Path(__file__).parent / "fixtures" / "cache_sample_run"
    tax_path = Path("field_catalog/turtle_v015_field_taxonomy.json")
    taxonomy_doc = json.loads(tax_path.read_text(encoding="utf-8"))
    catalog_version = str(taxonomy_doc.get("version", "unknown"))
    priority_map = {
        fid: str(info.get("priority", ""))
        for fid, info in taxonomy_doc.get("fields", {}).items()
    }
    index_run(
        run_dir=fixture_dir, db_path=db_path,
        catalog_version=catalog_version, priority_map=priority_map,
    )

    client = FinancialReportClient(
        config=ExtractorConfig(db_path=db_path, cache_root=tmp_path),
    )
    return client


def test_get_field_returns_field_value(tmp_path: Path) -> None:
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        RefreshPolicy,
    )

    client = _seed_db_and_client(tmp_path)
    fv = client.get_field(
        company="600519", period_end="2024-12-31", market="CN",
        field_id="revenue",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
    )
    assert fv.field_id == "revenue"
    assert fv.confidence == ConfidenceLevel.VERIFIED
    assert fv.is_reliable


def test_get_field_unknown_field_raises(tmp_path: Path) -> None:
    from financial_report_llm_extractor.client import (
        ExtractorError,
        RefreshPolicy,
    )

    client = _seed_db_and_client(tmp_path)
    with pytest.raises(ExtractorError) as excinfo:
        client.get_field(
            company="600519", period_end="2024-12-31", market="CN",
            field_id="totally_made_up_field_xyz",
            refresh_policy=RefreshPolicy.CACHE_ONLY,
        )
    assert excinfo.value.reason == "unknown_field"


def test_get_field_taxonomy_field_but_no_db_data_returns_unavailable(
    tmp_path: Path,
) -> None:
    """field is in taxonomy but DB has no row for it (because fixture
    only has 3 fields) → UNAVAILABLE placeholder."""
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        RefreshPolicy,
    )

    client = _seed_db_and_client(tmp_path)
    # `total_assets` is in taxonomy but not in cache_sample_run fixture
    fv = client.get_field(
        company="600519", period_end="2024-12-31", market="CN",
        field_id="total_assets",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
    )
    assert fv.field_id == "total_assets"
    assert fv.confidence == ConfidenceLevel.UNAVAILABLE
    assert fv.value is None


def test_get_field_llm_supplement_filter_same_as_get_extraction(
    tmp_path: Path,
) -> None:
    """get_field and get_extraction must agree on LLM filter behavior."""
    from financial_report_llm_extractor.client import (
        ConfidenceLevel,
        RefreshPolicy,
    )

    client = _seed_db_and_client(tmp_path)
    # include=False → UNAVAILABLE placeholder
    fv = client.get_field(
        company="600519", period_end="2024-12-31", market="CN",
        field_id="audit_opinion",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
        include_llm_supplement=False,
    )
    assert fv.confidence == ConfidenceLevel.UNAVAILABLE
    assert fv.reason == "llm_supplement_filtered"
    assert fv.raw_bucket == "llm_supplement_present"

    # include=True → full LLM_SUPPLEMENT
    fv2 = client.get_field(
        company="600519", period_end="2024-12-31", market="CN",
        field_id="audit_opinion",
        refresh_policy=RefreshPolicy.CACHE_ONLY,
        include_llm_supplement=True,
    )
    assert fv2.confidence == ConfidenceLevel.LLM_SUPPLEMENT
    assert fv2.value is not None
