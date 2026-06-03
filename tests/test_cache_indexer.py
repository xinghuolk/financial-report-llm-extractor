"""Round-trip: evaluation.json + llm_evidence_supplement.json -> DB -> SELECT.

Verifies that index_run correctly joins the two-file inputs by field_id and
picks the value/page/confidence/reasoning from llm_evidence_supplement.json
for llm_supplement_present buckets.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from financial_report_llm_extractor.cache.db import init_db
from financial_report_llm_extractor.cache.indexer import index_run

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "cache_sample_run"

PRIORITY_MAP = {
    "revenue": "P0",
    "audit_opinion": "P4",
    "fix_assets": "P0",
}


def test_index_run_inserts_extractions_row(tmp_path: Path) -> None:
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(
        run_dir=FIXTURE_DIR,
        db_path=db_path,
        catalog_version="2026-05-02",
        priority_map=PRIORITY_MAP,
    )
    conn = sqlite3.connect(db_path)
    try:
        rows = list(
            conn.execute(
                "SELECT company, period_end, market, report_type, "
                "catalog_version, llm_provider, llm_model "
                "FROM extractions"
            )
        )
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0][:5] == ("600519", "2024-12-31", "CN", "annual", "2026-05-02")


def test_index_run_persists_llm_metadata_from_supplement(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    run_dir = tmp_path / "run_with_llm_metadata"
    run_dir.mkdir()
    (run_dir / "evaluation.json").write_text(
        (FIXTURE_DIR / "evaluation.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    supplement_payload = json.loads(
        (FIXTURE_DIR / "llm_evidence_supplement.json").read_text(encoding="utf-8")
    )
    supplement_payload["llm_provider"] = "codex"
    supplement_payload["llm_model"] = "gpt-5.5"
    (run_dir / "llm_evidence_supplement.json").write_text(
        json.dumps(supplement_payload), encoding="utf-8",
    )

    index_run(
        run_dir=run_dir,
        db_path=db_path,
        catalog_version="2026-05-02",
        priority_map=PRIORITY_MAP,
    )

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT llm_provider, llm_model FROM extractions"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("codex", "gpt-5.5")


def test_index_run_clean_present_value_from_evaluation(tmp_path: Path) -> None:
    """clean_present bucket: value comes from evaluation.json directly."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(
        run_dir=FIXTURE_DIR, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT bucket, value, currency, unit, selected_source, "
            "priority, reason "
            "FROM field_values WHERE field_id = 'revenue'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "clean_present"
    assert json.loads(row[1]) == "170899152276.34"
    assert row[2] == "CNY"
    assert row[3] == "yuan"
    assert row[4] == "akshare"
    assert row[5] == "P0"
    assert row[6] is None


def test_index_run_llm_bucket_value_from_supplement(tmp_path: Path) -> None:
    """llm_supplement_present bucket: value/page/confidence/reasoning come from
    llm_evidence_supplement.json, NOT evaluation.json (where value is null)."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(
        run_dir=FIXTURE_DIR, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT bucket, value, evidence_page, llm_confidence, "
            "llm_reasoning_short, priority "
            "FROM field_values WHERE field_id = 'audit_opinion'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "llm_supplement_present"
    assert json.loads(row[1]).startswith("标准无保留意见")
    assert row[2] == 55
    assert row[3] == pytest.approx(0.98)
    assert row[4] is not None and "审计意见" in row[4]
    assert row[5] == "P4"


def test_index_run_unresolved_conflict_has_reason(tmp_path: Path) -> None:
    """unresolved_conflict bucket: value is null, reason is preserved."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(
        run_dir=FIXTURE_DIR, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT bucket, value, reason FROM field_values "
            "WHERE field_id = 'fix_assets'"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("unresolved_conflict", None, "missing_source_candidate")


def test_index_run_returns_field_count(tmp_path: Path) -> None:
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    n = index_run(
        run_dir=FIXTURE_DIR, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    assert n == 3


def test_index_run_upsert_replaces_field_values(tmp_path: Path) -> None:
    """Re-indexing same (company, period_end) replaces field_values atomically."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(run_dir=FIXTURE_DIR, db_path=db_path,
              catalog_version="v1", priority_map=PRIORITY_MAP)
    index_run(run_dir=FIXTURE_DIR, db_path=db_path,
              catalog_version="v1", priority_map=PRIORITY_MAP)
    conn = sqlite3.connect(db_path)
    try:
        ext_count = conn.execute(
            "SELECT COUNT(*) FROM extractions").fetchone()[0]
        fv_count = conn.execute(
            "SELECT COUNT(*) FROM field_values").fetchone()[0]
    finally:
        conn.close()
    assert ext_count == 1
    assert fv_count == 3


def test_index_run_different_catalog_versions_extractions_coexist(
    tmp_path: Path,
) -> None:
    """Different catalog_versions create separate extractions rows.
    field_values is replaced on every index (latest catalog_version only)."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(run_dir=FIXTURE_DIR, db_path=db_path,
              catalog_version="v1", priority_map=PRIORITY_MAP)
    index_run(run_dir=FIXTURE_DIR, db_path=db_path,
              catalog_version="v2", priority_map=PRIORITY_MAP)
    conn = sqlite3.connect(db_path)
    try:
        ext_count = conn.execute(
            "SELECT COUNT(*) FROM extractions").fetchone()[0]
        fv_count = conn.execute(
            "SELECT COUNT(*) FROM field_values").fetchone()[0]
    finally:
        conn.close()
    assert ext_count == 2
    assert fv_count == 3


def test_index_run_missing_evaluation_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    empty_run = tmp_path / "empty_run"
    empty_run.mkdir()
    with pytest.raises(FileNotFoundError):
        index_run(run_dir=empty_run, db_path=db_path,
                  catalog_version="v1", priority_map={})


def test_index_run_market_column_populated(tmp_path: Path) -> None:
    """All inserted field_values rows must have market column set."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(
        run_dir=FIXTURE_DIR, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    conn = sqlite3.connect(db_path)
    try:
        rows = list(conn.execute("SELECT market FROM field_values"))
    finally:
        conn.close()
    assert len(rows) == 3
    for (market,) in rows:
        assert market == "CN"  # fixture market


def test_index_run_cross_market_does_not_collide(tmp_path: Path) -> None:
    """Same (company, period_end) under different markets must coexist.

    R5 invariant: DELETE+INSERT scopes by market; cross-market re-index
    does NOT wipe previously indexed market's field_values.
    """
    db_path = tmp_path / "extracted.db"
    init_db(db_path)

    # Build a copy of the fixture but flip market to HK
    cn_dir = FIXTURE_DIR  # market=CN
    hk_dir = tmp_path / "hk_fake"
    hk_dir.mkdir()
    eval_payload = json.loads(
        (cn_dir / "evaluation.json").read_text(encoding="utf-8")
    )
    eval_payload["market"] = "HK"
    (hk_dir / "evaluation.json").write_text(
        json.dumps(eval_payload), encoding="utf-8",
    )
    # Copy llm_evidence_supplement.json if present
    supp = cn_dir / "llm_evidence_supplement.json"
    if supp.exists():
        (hk_dir / "llm_evidence_supplement.json").write_text(
            supp.read_text(encoding="utf-8"), encoding="utf-8",
        )

    # Index CN first
    index_run(
        run_dir=cn_dir, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    # Index HK second — must NOT wipe CN's field_values
    index_run(
        run_dir=hk_dir, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )

    conn = sqlite3.connect(db_path)
    try:
        cn_count = conn.execute(
            "SELECT COUNT(*) FROM field_values "
            "WHERE company = '600519' AND period_end = '2024-12-31' AND market = 'CN'"
        ).fetchone()[0]
        hk_count = conn.execute(
            "SELECT COUNT(*) FROM field_values "
            "WHERE company = '600519' AND period_end = '2024-12-31' AND market = 'HK'"
        ).fetchone()[0]
        ext_count = conn.execute(
            "SELECT COUNT(*) FROM extractions"
        ).fetchone()[0]
    finally:
        conn.close()

    assert cn_count == 3, f"CN field_values wiped! got {cn_count}, expected 3"
    assert hk_count == 3, f"HK field_values missing! got {hk_count}"
    assert ext_count == 2, f"expected 2 extractions rows, got {ext_count}"


def test_index_run_missing_supplement_does_not_break(tmp_path: Path) -> None:
    """If llm_evidence_supplement.json is absent, LLM rows have null value but
    the row is still inserted with the bucket from evaluation.json."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    run_dir = tmp_path / "run_no_supplement"
    run_dir.mkdir()
    (run_dir / "evaluation.json").write_text(
        (FIXTURE_DIR / "evaluation.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    n = index_run(
        run_dir=run_dir, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    assert n == 3
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT value, evidence_page FROM field_values "
            "WHERE field_id = 'audit_opinion'"
        ).fetchone()
    finally:
        conn.close()
    assert row == (None, None)
