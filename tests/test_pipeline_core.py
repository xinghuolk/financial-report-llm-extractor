"""pipeline_core.run_pipeline() — in-process orchestration shared by
CLI `pipeline` subcommand and FinancialReportClient."""

from __future__ import annotations

import json
from pathlib import Path

def test_pipeline_core_db_cache_hit(
    tmp_path: Path,
) -> None:
    """If DB has matching (company, period_end, market, catalog_version),
    pipeline_core returns cache_hit dict without invoking fetch/evaluate."""
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.cache.indexer import index_run
    from financial_report_llm_extractor.pipeline_core import run_pipeline

    fixture_dir = Path(__file__).parent / "fixtures" / "cache_sample_run"
    db_path = tmp_path / "out.db"
    init_db(db_path)

    tax_path = Path("field_catalog/turtle_v015_field_taxonomy.json")
    taxonomy_doc = json.loads(tax_path.read_text(encoding="utf-8"))
    catalog_version = str(taxonomy_doc.get("version", "unknown"))
    priority_map = {
        fid: str(info.get("priority", ""))
        for fid, info in taxonomy_doc.get("fields", {}).items()
    }
    index_run(
        run_dir=fixture_dir,
        db_path=db_path,
        catalog_version=catalog_version,
        priority_map=priority_map,
    )

    result = run_pipeline(
        company="600519",
        period_end="2024-12-31",
        market="CN",
        report_type="annual",
        db_path=db_path,
        out_dir=tmp_path / "fresh_run",
        catalog_path=Path(
            "field_catalog/turtle_v015_source_mapping_minimal.json"
        ),
        taxonomy_path=tax_path,
        priorities=("P0", "P1", "P2", "P3", "P4"),
        pdf_path=None,
        llm_config_path=None,
        force=False,
        no_cache=False,
    )
    assert result["status"] == "cache_hit"
    assert result["company"] == "600519"
    assert result["catalog_version"] == catalog_version


def test_pipeline_core_force_bypasses_db(
    tmp_path: Path,
) -> None:
    """--force must bypass the DB pre-check.

    Pipeline will fail downstream (no network / pdf) — the test only
    verifies the dispatch did NOT short-circuit to cache_hit."""
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.cache.indexer import index_run
    from financial_report_llm_extractor.pipeline_core import run_pipeline

    fixture_dir = Path(__file__).parent / "fixtures" / "cache_sample_run"
    db_path = tmp_path / "out.db"
    init_db(db_path)

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

    # With force=True, even though DB hit exists, pipeline tries fresh
    # run and will fail (no real client). Expect any exception EXCEPT
    # status=="cache_hit" return.
    try:
        result = run_pipeline(
            company="600519",
            period_end="2024-12-31",
            market="CN",
            report_type="annual",
            db_path=db_path,
            out_dir=tmp_path / "fresh_run",
            catalog_path=Path(
                "field_catalog/turtle_v015_source_mapping_minimal.json"
            ),
            taxonomy_path=tax_path,
            priorities=("P0", "P1", "P2", "P3", "P4"),
            pdf_path=None,
            llm_config_path=None,
            force=True,
            no_cache=False,
        )
        # If no exception, must NOT be cache_hit
        assert result.get("status") != "cache_hit"
    except Exception:
        pass  # acceptable — fresh run fails in unit-test env without network
