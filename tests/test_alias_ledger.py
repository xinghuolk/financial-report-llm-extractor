"""Tests for alias_ledger (spec PR-2, component 3 — reduced scope)."""
from __future__ import annotations

import json
from pathlib import Path

from financial_report_llm_extractor.structured_sources.alias_ledger import (
    compute_signals,
    index_audit_dir,
    index_run_dir,
    load_ledger,
    new_ledger,
    save_ledger,
    write_ledger_views,
)


def _write_run_dir(root: Path, *, company: str = "00001",
                   period_end: str = "2025-12-31", market: str = "HK",
                   items: dict[str, dict[str, object]] | None = None) -> Path:
    d = root / f"{company}_run"
    d.mkdir(parents=True)
    (d / "evaluation.json").write_text(json.dumps({
        "company": company, "period_end": period_end, "market": market,
        "fields": {}, "summary": {},
    }))
    (d / "llm_evidence_supplement.json").write_text(json.dumps({
        "company_id": company,
        "items": items if items is not None else {
            "bond_payable": {"status": "present", "value": "165366",
                              "page": 232},
            "rd_exp": {"status": "not_found", "value": None, "page": None},
        },
    }))
    return d


def _write_audit_dir(root: Path, *, company: str | None = "00001",
                     market: str | None = "HK", year: int | None = 2025) -> Path:
    d = root / "audit"
    d.mkdir(parents=True)
    (d / "alias_audit.json").write_text(json.dumps({
        "schema_version": "alias_audit_v1",
        "pdf_path": "x.pdf", "catalog_version": "2026-05-01",
        "company": company, "market": market, "year": year,
        "section_anchor_coverage": {},
        "warnings": {"empty_anchor_statement_types": []},
        "fields": {
            "receivables_aging": {
                "status": "normalized_only_hit",
                "selected_chunks": [],
                "hits": [{"alias": "ageing analysis of trade receivables",
                           "kind": "normalized", "page": 229, "count": 1,
                           "in_statement_section": None,
                           "matched_text": "ageing analysis of the trade receivables,"}],
                "suggested_aliases": ["ageing analysis of the trade receivables"],
            },
            "revenue": {
                "status": "exact_hit", "selected_chunks": [],
                "hits": [{"alias": "revenue", "kind": "exact", "page": 134,
                           "count": 2, "in_statement_section": True,
                           "matched_text": "revenue"}],
                "suggested_aliases": [],
            },
            "rd_exp": {"status": "no_hit", "selected_chunks": [],
                        "hits": [], "suggested_aliases": []},
        },
        "summary": {},
    }))
    return d


def test_index_run_dir_llm_hits_under_reserved_key(tmp_path: Path) -> None:
    run = _write_run_dir(tmp_path)
    ledger = new_ledger()
    warnings = index_run_dir(ledger, run)
    assert warnings == []
    entries = ledger["fields"]["bond_payable"]["_llm"]
    assert entries == [{"company": "00001", "year": 2025,
                         "page": 232, "market": "HK"}]
    # not_found items are not indexed
    assert "rd_exp" not in ledger["fields"]


def test_index_run_dir_skips_without_evaluation(tmp_path: Path) -> None:
    run = _write_run_dir(tmp_path)
    (run / "evaluation.json").unlink()
    ledger = new_ledger()
    warnings = index_run_dir(ledger, run)
    assert len(warnings) == 1 and "evaluation.json" in warnings[0]
    assert ledger["fields"] == {}


def test_index_audit_dir_alias_entries_and_statuses(tmp_path: Path) -> None:
    audit = _write_audit_dir(tmp_path)
    ledger = new_ledger()
    warnings = index_audit_dir(ledger, audit)
    assert warnings == []
    aging = ledger["fields"]["receivables_aging"][
        "ageing analysis of trade receivables"]
    assert aging == [{
        "company": "00001", "year": 2025, "page": 229,
        "match_kind": "normalized", "market": "HK",
        "catalog_version": "2026-05-01",
        "suggested": "ageing analysis of the trade receivables",
    }]
    rev = ledger["fields"]["revenue"]["revenue"]
    assert rev[0]["match_kind"] == "exact" and "suggested" not in rev[0]
    # field-level audit statuses for the terminal signal
    assert ledger["audit_statuses"]["rd_exp"]["HK"]["00001"] == "no_hit"


def test_index_audit_dir_skips_without_metadata(tmp_path: Path) -> None:
    audit = _write_audit_dir(tmp_path, company=None, market=None, year=None)
    ledger = new_ledger()
    warnings = index_audit_dir(ledger, audit)
    assert len(warnings) == 1 and "metadata" in warnings[0]
    assert ledger["fields"] == {}


def test_indexing_is_idempotent(tmp_path: Path) -> None:
    run = _write_run_dir(tmp_path)
    audit = _write_audit_dir(tmp_path)
    ledger = new_ledger()
    for _ in range(2):
        index_run_dir(ledger, run)
        index_audit_dir(ledger, audit)
    assert len(ledger["fields"]["bond_payable"]["_llm"]) == 1
    assert len(ledger["fields"]["revenue"]["revenue"]) == 1


def test_save_load_roundtrip_byte_stable(tmp_path: Path) -> None:
    run = _write_run_dir(tmp_path)
    ledger = new_ledger()
    index_run_dir(ledger, run)
    p = tmp_path / "ledger.json"
    save_ledger(ledger, p)
    first = p.read_bytes()
    ledger2 = load_ledger(p)
    index_run_dir(ledger2, run)  # idempotent re-index
    save_ledger(ledger2, p)
    assert p.read_bytes() == first
    data = json.loads(first)
    assert data["schema_version"] == "alias_ledger_v1"
    assert "regenerable" in data["note"]
    assert "generated_at" not in data  # timestamp-free by design


def test_load_ledger_schema_drift_returns_fresh(tmp_path: Path) -> None:
    p = tmp_path / "ledger.json"
    p.write_text(json.dumps({"schema_version": "alias_ledger_v0",
                              "fields": {"x": {}}}))
    ledger = load_ledger(p)
    assert ledger["fields"] == {}
    assert ledger["schema_version"] == "alias_ledger_v1"


def test_byte_stable_with_audit_entries(tmp_path: Path) -> None:
    run = _write_run_dir(tmp_path)
    audit = _write_audit_dir(tmp_path)
    ledger = new_ledger()
    index_run_dir(ledger, run)
    index_audit_dir(ledger, audit)
    p = tmp_path / "ledger.json"
    save_ledger(ledger, p)
    first = p.read_bytes()
    ledger2 = load_ledger(p)
    index_run_dir(ledger2, run)
    index_audit_dir(ledger2, audit)
    save_ledger(ledger2, p)
    assert p.read_bytes() == first


def test_index_run_dir_warns_on_bad_period_end(tmp_path: Path) -> None:
    run = _write_run_dir(tmp_path, period_end="")
    ledger = new_ledger()
    warnings = index_run_dir(ledger, run)
    assert len(warnings) == 1 and "period_end" in warnings[0]
    assert ledger["fields"] == {}


def _signal_ledger() -> dict[str, object]:
    ledger = new_ledger()
    f = ledger["fields"]
    # promotion candidate: same suggested phrase, 2 HK companies
    f["receivables_aging"] = {
        "ageing analysis of trade receivables": [
            {"company": "00001", "year": 2025, "page": 229,
             "match_kind": "normalized", "market": "HK",
             "catalog_version": "v",
             "suggested": "ageing analysis of the trade receivables"},
            {"company": "01113", "year": 2025, "page": 80,
             "match_kind": "normalized", "market": "HK",
             "catalog_version": "v",
             "suggested": "ageing analysis of the trade receivables"},
        ],
    }
    # exact hits for one alias of revenue; its other alias is dead in HK
    f["revenue"] = {
        "revenue": [
            {"company": "00001", "year": 2025, "page": 134,
             "match_kind": "exact", "market": "HK", "catalog_version": "v"},
        ],
    }
    ledger["audit_statuses"] = {
        "rd_exp": {"HK": {"00001": "no_hit", "01113": "no_hit",
                           "01810": "no_hit"}},
        "revenue": {"HK": {"00001": "exact_hit"}},
    }
    return ledger


def test_promotion_candidates_market_scoped() -> None:
    signals = compute_signals(
        _signal_ledger(),
        catalog_aliases={"receivables_aging": ("ageing analysis of trade receivables",),
                          "revenue": ("revenue", "营业收入"),
                          "rd_exp": ("research and development",)},
        min_companies=2,
    )
    promos = signals["promotion_candidates"]
    assert promos == [{
        "field_id": "receivables_aging",
        "market": "HK",
        "suggested_alias": "ageing analysis of the trade receivables",
        "companies": ["00001", "01113"],
    }]


def test_dead_aliases_market_scoped() -> None:
    signals = compute_signals(
        _signal_ledger(),
        catalog_aliases={"revenue": ("revenue", "营业收入"),
                          "receivables_aging": ("ageing analysis of trade receivables",),
                          "rd_exp": ("research and development",)},
        min_companies=2,
    )
    dead = signals["dead_aliases"]
    # 营业收入 never hit in HK; research and development never hit in HK.
    assert {"field_id": "revenue", "market": "HK",
            "alias": "营业收入"} in dead
    assert {"field_id": "rd_exp", "market": "HK",
            "alias": "research and development"} in dead
    # 'revenue' (hit) and the normalized-hit aging alias are NOT dead
    assert not any(d["alias"] == "revenue" for d in dead)


def test_terminal_candidates_threshold() -> None:
    signals = compute_signals(
        _signal_ledger(),
        catalog_aliases={"rd_exp": ("research and development",)},
        min_companies=2,
    )
    terms = signals["terminal_candidates"]
    assert terms == [{
        "field_id": "rd_exp", "market": "HK",
        "no_hit_companies": ["00001", "01113", "01810"],
    }]


def test_write_ledger_views_md(tmp_path: Path) -> None:
    ledger = _signal_ledger()
    write_ledger_views(
        ledger,
        catalog_aliases={"receivables_aging": ("ageing analysis of trade receivables",),
                          "revenue": ("revenue", "营业收入"),
                          "rd_exp": ("research and development",)},
        out_md=tmp_path / "ledger.md",
        min_companies=2,
    )
    md = (tmp_path / "ledger.md").read_text()
    assert "ageing analysis of the trade receivables" in md
    assert "营业收入" in md  # dead-alias table
    assert "rd_exp" in md  # terminal table
