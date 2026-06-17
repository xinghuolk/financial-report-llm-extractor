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
        company="600519", period_end="2024-12-31", market="CN",
        field_id="revenue",
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
        company="600519", period_end="2024-12-31", market="CN",
        field_id="audit_opinion",
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
        period_end="2024-12-31", market="CN", field_id="does_not_exist",
    ) is None


def test_query_extraction_returns_metadata_and_fields(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    result = query_extraction(
        db_path=db_path, company="600519", period_end="2024-12-31",
        market="CN",
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


def test_query_extraction_isolates_by_market(tmp_path: Path) -> None:
    """R5: same (company, period_end) indexed under CN and HK; query with
    market=CN must return CN-only fields, not HK's."""
    import json
    db_path = tmp_path / "extracted.db"
    init_db(db_path)

    # Seed CN (from fixture)
    index_run(
        run_dir=FIXTURE_DIR, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    # Seed HK (copy fixture, flip market)
    hk_dir = tmp_path / "hk_fake"
    hk_dir.mkdir()
    eval_payload = json.loads(
        (FIXTURE_DIR / "evaluation.json").read_text(encoding="utf-8")
    )
    eval_payload["market"] = "HK"
    (hk_dir / "evaluation.json").write_text(
        json.dumps(eval_payload), encoding="utf-8",
    )
    supp = FIXTURE_DIR / "llm_evidence_supplement.json"
    if supp.exists():
        (hk_dir / "llm_evidence_supplement.json").write_text(
            supp.read_text(encoding="utf-8"), encoding="utf-8",
        )
    index_run(
        run_dir=hk_dir, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )

    cn = query_extraction(
        db_path=db_path, company="600519", period_end="2024-12-31",
        market="CN",
    )
    hk = query_extraction(
        db_path=db_path, company="600519", period_end="2024-12-31",
        market="HK",
    )
    assert cn is not None
    assert hk is not None
    assert cn["market"] == "CN"
    assert hk["market"] == "HK"
    assert set(cn["fields"]) == {"revenue", "audit_opinion", "fix_assets"}
    assert set(hk["fields"]) == {"revenue", "audit_opinion", "fix_assets"}


def test_query_field_isolates_by_market(tmp_path: Path) -> None:
    """R5: query_field with wrong market returns None even if the same
    (company, period_end, field_id) exists under another market."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)

    # Seed CN
    index_run(
        run_dir=FIXTURE_DIR, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )

    # Same (company, period_end, field_id) but market=HK should miss
    result = query_field(
        db_path=db_path, company="600519", period_end="2024-12-31",
        market="HK", field_id="revenue",
    )
    assert result is None

    # market=CN should hit
    result = query_field(
        db_path=db_path, company="600519", period_end="2024-12-31",
        market="CN", field_id="revenue",
    )
    assert result is not None
    assert result["market"] == "CN"


def test_query_extraction_miss_by_market(tmp_path: Path) -> None:
    """If only CN row exists, query_extraction(market='HK') returns None."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(
        run_dir=FIXTURE_DIR, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    result = query_extraction(
        db_path=db_path, company="600519", period_end="2024-12-31",
        market="HK",
    )
    assert result is None


def test_query_field_result_includes_market(tmp_path: Path) -> None:
    """query_field result dict includes the market key."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(
        run_dir=FIXTURE_DIR, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    result = query_field(
        db_path=db_path, company="600519", period_end="2024-12-31",
        market="CN", field_id="revenue",
    )
    assert result is not None
    assert result["market"] == "CN"


def test_normalized_value_roundtrip(tmp_path: Path) -> None:
    from financial_report_llm_extractor.cache.db import init_db, connect
    from financial_report_llm_extractor.cache.db_query import query_field

    db = tmp_path / "extracted.db"
    init_db(db)
    conn = connect(db)
    conn.execute(
        "INSERT INTO field_values (company, period_end, market, field_id, priority,"
        " bucket, value, currency, unit, selected_source, reason, evidence_page,"
        " llm_confidence, llm_reasoning_short, normalized_value, canonical_unit)"
        " VALUES ('603345','2024-12-31','CN','sbc','P3','llm_supplement_present',"
        " '\"10080.83\"','CNY','万元','llm',NULL,NULL,NULL,NULL,'100808300','CNY')"
    )
    conn.commit()
    conn.close()

    row = query_field(db_path=db, company="603345", period_end="2024-12-31",
                      market="CN", field_id="sbc")
    assert row["normalized_value"] == "100808300"
    assert row["canonical_unit"] == "CNY"
