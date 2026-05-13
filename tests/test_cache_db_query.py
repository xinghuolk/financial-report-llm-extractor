"""Read-side queries: single field, single extraction, list companies."""

from pathlib import Path

from financial_report_llm_extractor.cache.db import init_db
from financial_report_llm_extractor.cache.db_query import (
    list_companies,
    query_extraction,
    query_field,
)
from financial_report_llm_extractor.cache.indexer import index_run

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "cache_sample_run"
PRIORITY_MAP = {"revenue": "P0", "audit_opinion": "P4", "fix_assets": "P0"}


def _setup(tmp_path: Path) -> Path:
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(
        run_dir=FIXTURE_DIR, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    return db_path


def test_query_field_clean_present(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    result = query_field(
        db_path=db_path,
        company="600519", period_end="2024-12-31", field_id="revenue",
    )
    assert result is not None
    assert result["bucket"] == "clean_present"
    assert result["value"] == "170899152276.34"  # decoded from JSON
    assert result["currency"] == "CNY"
    assert result["priority"] == "P0"


def test_query_field_llm_supplement(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    result = query_field(
        db_path=db_path,
        company="600519", period_end="2024-12-31", field_id="audit_opinion",
    )
    assert result is not None
    assert result["bucket"] == "llm_supplement_present"
    assert result["value"].startswith("标准无保留意见")
    assert result["evidence_page"] == 55
    assert result["llm_confidence"] == 0.98
    assert "审计意见" in result["llm_reasoning_short"]


def test_query_field_miss_returns_none(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    assert query_field(
        db_path=db_path, company="600519",
        period_end="2024-12-31", field_id="does_not_exist",
    ) is None


def test_query_extraction_returns_metadata_and_fields(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    result = query_extraction(
        db_path=db_path, company="600519", period_end="2024-12-31",
    )
    assert result is not None
    assert result["company"] == "600519"
    assert result["market"] == "CN"
    assert "fields" in result
    assert set(result["fields"]) == {"revenue", "audit_opinion", "fix_assets"}
    assert result["fields"]["revenue"]["priority"] == "P0"


def test_list_companies(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    rows = list_companies(db_path=db_path)
    assert ("600519", "2024-12-31", "CN", "v1") in rows
