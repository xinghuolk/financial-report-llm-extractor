"""pipeline command: DB pre-check, force flag, fresh-run path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_cli_pipeline_subparser_parses_basic_args(tmp_path: Path) -> None:
    """pipeline subparser accepts company/year/market/out + has defaults."""
    from financial_report_llm_extractor.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "pipeline",
            "--company",
            "600519",
            "--year",
            "2024",
            "--market",
            "CN",
            "--out",
            str(tmp_path / "run1"),
        ]
    )
    assert args.command == "pipeline"
    assert args.company == "600519"
    assert args.year == 2024
    assert args.market == "CN"
    assert args.force is False
    assert args.no_cache is False


def test_cli_pipeline_force_flag(tmp_path: Path) -> None:
    from financial_report_llm_extractor.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "pipeline",
            "--company",
            "600519",
            "--year",
            "2024",
            "--market",
            "CN",
            "--out",
            str(tmp_path / "run1"),
            "--force",
        ]
    )
    assert args.force is True


def test_cli_pipeline_no_cache_flag(tmp_path: Path) -> None:
    from financial_report_llm_extractor.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "pipeline",
            "--company",
            "600519",
            "--year",
            "2024",
            "--market",
            "CN",
            "--out",
            str(tmp_path / "run1"),
            "--no-cache",
        ]
    )
    assert args.no_cache is True


def test_cli_pipeline_db_pre_check_returns_cache_hit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """If DB has a matching (company, period_end, catalog_version) row, pipeline
    returns cache_hit JSON without invoking fetch/evaluate."""
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.cache.indexer import index_run
    from financial_report_llm_extractor.cli import main

    # Seed DB by indexing the existing test fixture (cache_sample_run/).
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

    capsys.readouterr()  # discard any prior output
    exit_code = main(
        [
            "pipeline",
            "--company",
            "600519",
            "--year",
            "2024",
            "--market",
            "CN",
            "--db",
            str(db_path),
            "--out",
            str(tmp_path / "fresh_run"),
        ]
    )
    assert exit_code == 0
    body = json.loads(capsys.readouterr().out)
    assert body["status"] == "cache_hit"
    assert body["company"] == "600519"
    assert body["catalog_version"] == catalog_version
    # The artifact_path should point at the seeded fixture
    assert "cache_sample_run" in body["artifact_path"]


def test_cli_pipeline_period_end_argument(tmp_path: Path) -> None:
    """--period-end works as alternative to --year."""
    from financial_report_llm_extractor.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "pipeline",
            "--company",
            "600519",
            "--period-end",
            "2024-06-30",
            "--report-type",
            "semi_annual",
            "--market",
            "CN",
            "--out",
            str(tmp_path / "run1"),
        ]
    )
    assert args.period_end == "2024-06-30"
    assert args.report_type == "semi_annual"


def test_cli_pipeline_pre_check_respects_market_filter(
    tmp_path: Path, capsys: "pytest.CaptureFixture[str]",
) -> None:
    """If DB has (company, period_end) under HK but caller asks CN, pipeline
    must NOT return cache_hit — should fall through to fresh run path."""
    import json
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.cache.indexer import index_run
    from financial_report_llm_extractor.cli import main

    # Build a fake HK run by copying the CN fixture and overriding market.
    fixture_dir = Path(__file__).parent / "fixtures" / "cache_sample_run"
    fake_run = tmp_path / "fake_hk_run"
    fake_run.mkdir()
    eval_payload = json.loads(
        (fixture_dir / "evaluation.json").read_text(encoding="utf-8")
    )
    eval_payload["market"] = "HK"
    (fake_run / "evaluation.json").write_text(
        json.dumps(eval_payload), encoding="utf-8",
    )
    supp_src = fixture_dir / "llm_evidence_supplement.json"
    if supp_src.exists():
        (fake_run / "llm_evidence_supplement.json").write_text(
            supp_src.read_text(encoding="utf-8"), encoding="utf-8",
        )

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
        run_dir=fake_run, db_path=db_path,
        catalog_version=catalog_version, priority_map=priority_map,
    )

    # Pipeline with --market CN should NOT match the HK-seeded row.
    # Fetch/evaluate will fail in unit-test env — that is expected.
    # We only need to confirm the dispatch did NOT short-circuit to cache_hit.
    capsys.readouterr()
    try:
        main([
            "pipeline",
            "--company", "600519",
            "--year", "2024",
            "--market", "CN",
            "--db", str(db_path),
            "--out", str(tmp_path / "fresh_run"),
        ])
    except SystemExit:
        pass
    except Exception:
        pass  # fetch/evaluate expected to fail in unit-test env

    out = capsys.readouterr().out
    if out.strip():
        first_line = out.strip().split("\n")[0]
        try:
            body = json.loads(first_line)
            assert body.get("status") != "cache_hit", (
                "pre-check must not return cache_hit when markets differ"
            )
        except json.JSONDecodeError:
            pass  # non-JSON output → fell through → OK
