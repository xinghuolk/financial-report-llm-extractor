# Alias Lifecycle PR-2 (match ledger, reduced scope) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship spec PR-2 (reduced scope per rev 2): `index-alias-matches` CLI building a derived, regenerable match ledger (`field_catalog/alias_match_ledger.json`) from run artifacts + audits, with market-scoped governance signals (dead aliases / promotion candidates / terminal candidates) and a review-gated promotion artifact compatible with `source_mapping_expansion_review`.

**Architecture:** A pure module `alias_ledger.py` builds entries from two sources — LLM supplements (joined to `evaluation.json` for company/year/market, field-level `_llm` key since supplements carry no alias attribution) and audit JSONs (which gain optional company/market/year metadata in this PR). The ledger is timestamp-free and idempotent (rerun → byte-identical), so it diffs cleanly in git. Signals are computed from the ledger alone (audit field-statuses are embedded as `audit_statuses` to make it self-contained). The wheel must NOT ship the ledger.

**Tech Stack:** Python 3.11 stdlib, pytest, mypy strict, ruff 88. Branch: `feat/alias-lifecycle-pr2` stacked on `feat/alias-lifecycle-pr3`.

**Spec:** `docs/superpowers/specs/2026-06-10-alias-lifecycle-design.md` rev 2, "组件 3" section. Resequenced last per review #8; scope deliberately small.

**Verification gate per commit:** `uv run pytest -q && uv run ruff check . && uv run mypy src tests` (fully clean).

---

## Design decisions locked here (spec gaps closed)

1. **Audit metadata**: `alias_audit.json` currently has no company/market/year — the audit CLI only takes `--pdf`. Task 1 adds optional `--company/--market/--year` CLI args threaded into the JSON. `index-alias-matches` SKIPS audits lacking them (stderr warning) — no guessing from paths.
2. **Ledger is timestamp-free** (no `generated_at`): idempotent rerun must be byte-identical for git diffing. (`Date.now` analog rule: derived view, reproducibility over provenance timestamps.)
3. **Normalized entries carry `suggested`** (the lowercased PDF phrasing from the audit hit's suggestion) so promotion candidates can surface the actual phrase; spec's schema sketch lacked it.
4. **`audit_statuses` embedded in the ledger** (`{field: {market: {company: status}}}`) so the terminal-candidate signal (no_hit across ≥N companies) is computable from the ledger alone — the spec's signal #3 was otherwise uncomputable from hits-only data.
5. **Promotion artifact**: same decision shape as `source_mapping_expansion_review` (`CandidateDecision`: field_id/source/raw_field_name/raw_field_code/action/reason/aliases) with `report_id: "alias_promotion_review"` and `source: "pdf"`.

## File structure

| File | Change |
|---|---|
| `structured_sources/alias_audit.py` | `AuditReport` + `audit_chunks` + writer gain optional company/market/year |
| `cli.py` | audit parser: `--company/--market/--year`; new `index-alias-matches` subcommand |
| Create `structured_sources/alias_ledger.py` | ledger build/upsert/save, signals, md view, promotion artifact |
| Create `tests/test_alias_ledger.py` | Tasks 2-4 tests |
| `tests/test_alias_audit.py` | Task 1 metadata tests |
| `pyproject.toml` | wheel exclusion for the ledger |
| `docs/new-company-analysis-workflow.md` | Step 6 addition |
| `field_catalog/alias_match_ledger.json` | Task 5 operator artifact (committed) |

---

### Task 1: audit metadata embed

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/alias_audit.py`
- Modify: `src/financial_report_llm_extractor/cli.py` (audit parser ~line 392 + handler)
- Test: `tests/test_alias_audit.py`

- [ ] **Step 1: Failing tests** (append to tests/test_alias_audit.py):

```python
def test_audit_report_embeds_company_metadata(tmp_path: Path) -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue",),
               statement_type="income_statement"),
    ])
    taxonomy = _taxonomy([_tax("revenue", statement_type="income_statement")])
    r = audit_chunks(
        chunks=list(_CHUNKS), catalog=catalog, taxonomy=taxonomy,
        priorities=("P0",), pdf_path=Path("f.pdf"),
        company="00001", market="HK", year=2025,
    )
    write_alias_audit(r, tmp_path)
    data = _json.loads((tmp_path / "alias_audit.json").read_text())
    assert data["company"] == "00001"
    assert data["market"] == "HK"
    assert data["year"] == 2025


def test_audit_metadata_defaults_to_null(tmp_path: Path) -> None:
    r = _make()
    write_alias_audit(r, tmp_path)
    data = _json.loads((tmp_path / "alias_audit.json").read_text())
    assert data["company"] is None and data["market"] is None


def test_cli_audit_company_metadata_flags(tmp_path: Path) -> None:
    from financial_report_llm_extractor.cli import main

    out = tmp_path / "audit_meta"
    ingest = out / "ingest"
    ingest.mkdir(parents=True)
    with (ingest / "chunks.jsonl").open("w") as f:
        for c in _CHUNKS:
            f.write(_json.dumps(c) + "\n")
    rc = main([
        "audit-pdf-aliases", "--pdf", "x.pdf", "--out", str(out),
        "--company", "00001", "--market", "HK", "--year", "2025",
    ])
    assert rc == 0
    data = _json.loads((out / "alias_audit.json").read_text())
    assert (data["company"], data["market"], data["year"]) == ("00001", "HK", 2025)
```

- [ ] **Step 2: Run → FAIL** (unexpected kwargs)

- [ ] **Step 3: Implement.** `AuditReport` gains `company: str | None = None`, `market: str | None = None`, `year: int | None = None` (after existing fields). `audit_chunks` gains the same keyword-only params, passes through. `write_alias_audit` payload adds `"company": report.company, "market": report.market, "year": report.year` right after `"pdf_path"`. CLI: `audit_parser.add_argument("--company")`, `--market` (choices CN/HK), `--year` (type=int) — all optional, default None — threaded into `audit_chunks(...)` in the handler.

- [ ] **Step 4: Run tests + full gate.**

- [ ] **Step 5: Commit** `feat: audit metadata embed for ledger indexing (PR-2 task 1)`

---

### Task 2: ledger core module

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/alias_ledger.py`
- Test: `tests/test_alias_ledger.py`

- [ ] **Step 1: Failing tests:**

```python
"""Tests for alias_ledger (spec PR-2, component 3 — reduced scope)."""
from __future__ import annotations

import json
from pathlib import Path

from financial_report_llm_extractor.structured_sources.alias_ledger import (
    index_audit_dir,
    index_run_dir,
    load_ledger,
    new_ledger,
    save_ledger,
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
```

- [ ] **Step 2: Run → ModuleNotFoundError FAIL**

- [ ] **Step 3: Implement** `alias_ledger.py`:

```python
"""Derived match ledger (spec PR-2, component 3 — reduced scope).

Aggregates which alias actually hit, per (company, year, field), from two
sources: LLM evidence supplements (joined to the run's evaluation.json for
company/year/market — supplements carry NO alias attribution, so their
hits live under the reserved field-level key "_llm") and alias audits
(which carry alias-level kind/page plus optional company metadata).

The ledger is a DERIVED VIEW: regenerable from artifacts, timestamp-free
(idempotent rerun is byte-identical), safe to rm + re-index. It must NOT
ship in the wheel (pyproject excludes it from the catalog force-include).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LEDGER_SCHEMA = "alias_ledger_v1"
LEDGER_NOTE = (
    "derived view; regenerable from run artifacts + audits; "
    "rm + re-index is safe"
)
LLM_KEY = "_llm"

Ledger = dict[str, Any]


def new_ledger() -> Ledger:
    return {
        "schema_version": LEDGER_SCHEMA,
        "note": LEDGER_NOTE,
        "fields": {},
        "audit_statuses": {},
    }


def load_ledger(path: Path) -> Ledger:
    if not path.exists():
        return new_ledger()
    data: Ledger = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != LEDGER_SCHEMA:
        # schema drift: treat as fresh (derived view, nothing is lost)
        return new_ledger()
    return data


def save_ledger(ledger: Ledger, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    canon = {
        "schema_version": ledger["schema_version"],
        "note": ledger["note"],
        "fields": {
            fid: {
                alias: sorted(
                    entries,
                    key=lambda e: (e["company"], e["year"], e.get("page") or 0),
                )
                for alias, entries in sorted(aliases.items())
            }
            for fid, aliases in sorted(ledger["fields"].items())
        },
        "audit_statuses": {
            fid: {
                mkt: dict(sorted(by_co.items()))
                for mkt, by_co in sorted(by_mkt.items())
            }
            for fid, by_mkt in sorted(ledger["audit_statuses"].items())
        },
    }
    path.write_text(
        json.dumps(canon, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _upsert(ledger: Ledger, field_id: str, alias: str,
            entry: dict[str, Any]) -> None:
    entries = ledger["fields"].setdefault(field_id, {}).setdefault(alias, [])
    if entry not in entries:
        entries.append(entry)


def index_run_dir(ledger: Ledger, run_dir: Path) -> list[str]:
    """Index one run dir's LLM supplement. Returns warnings."""
    supp_path = run_dir / "llm_evidence_supplement.json"
    eval_path = run_dir / "evaluation.json"
    if not supp_path.exists():
        return [f"{run_dir}: no llm_evidence_supplement.json, skipped"]
    if not eval_path.exists():
        return [
            f"{run_dir}: supplement without evaluation.json "
            f"(company/year/market join impossible), skipped"
        ]
    ev = json.loads(eval_path.read_text(encoding="utf-8"))
    company = str(ev["company"])
    market = str(ev["market"])
    year = int(str(ev["period_end"])[:4])
    supp = json.loads(supp_path.read_text(encoding="utf-8"))
    for field_id, item in supp.get("items", {}).items():
        if item.get("status") != "present":
            continue
        _upsert(ledger, field_id, LLM_KEY, {
            "company": company, "year": year,
            "page": item.get("page"), "market": market,
        })
    return []


def index_audit_dir(ledger: Ledger, audit_dir: Path) -> list[str]:
    """Index one audit dir's alias-level hits + field statuses."""
    audit_path = audit_dir / "alias_audit.json"
    if not audit_path.exists():
        return [f"{audit_dir}: no alias_audit.json, skipped"]
    data = json.loads(audit_path.read_text(encoding="utf-8"))
    company, market, year = (
        data.get("company"), data.get("market"), data.get("year"),
    )
    if not (company and market and year):
        return [
            f"{audit_dir}: audit lacks company/market/year metadata "
            f"(re-run audit-pdf-aliases with --company/--market/--year), "
            f"skipped"
        ]
    catalog_version = str(data.get("catalog_version", ""))
    for field_id, fr in data.get("fields", {}).items():
        suggested_by_text = {
            str(s).lower(): str(s) for s in fr.get("suggested_aliases", [])
        }
        for hit in fr.get("hits", []):
            entry: dict[str, Any] = {
                "company": str(company), "year": int(year),
                "page": hit.get("page"),
                "match_kind": str(hit.get("kind")),
                "market": str(market),
                "catalog_version": catalog_version,
            }
            if hit.get("kind") == "normalized":
                # recover the suggestion phrase this hit produced
                stripped = str(hit.get("matched_text", "")).strip(
                    ",.;:").lower()
                if stripped in suggested_by_text:
                    entry["suggested"] = stripped
            _upsert(ledger, field_id, str(hit.get("alias")), entry)
        ledger["audit_statuses"].setdefault(field_id, {}).setdefault(
            str(market), {},
        )[str(company)] = str(fr.get("status"))
    return []
```

NOTE on the `suggested` strip: it mirrors `_audit_field`'s `_EDGE_PUNCT` strip — to avoid drift, IMPORT `_EDGE_PUNCT` from `alias_matching` and use it instead of the literal `",.;:"`.

- [ ] **Step 4: Run tests + full gate.**

- [ ] **Step 5: Commit** `feat: alias match ledger build/upsert core (PR-2 task 2)`

---

### Task 3: governance signals + md view

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/alias_ledger.py`
- Test: `tests/test_alias_ledger.py`

- [ ] **Step 1: Failing tests:**

```python
from financial_report_llm_extractor.structured_sources.alias_ledger import (
    compute_signals,
    write_ledger_views,
)


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
```

- [ ] **Step 2: Run → ImportError FAIL**

- [ ] **Step 3: Implement** (append to alias_ledger.py):

```python
def compute_signals(
    ledger: Ledger,
    *,
    catalog_aliases: dict[str, tuple[str, ...]],
    min_companies: int = 2,
) -> dict[str, list[dict[str, Any]]]:
    """Market-scoped governance signals.

    Market scoping is load-bearing: pdf_aliases mix EN + 中文 in one list,
    so cross-market aggregation would mark the whole Chinese half dead on
    an English cohort (and vice versa). Markets = those observed in the
    ledger, per signal.
    """
    # markets observed anywhere in the ledger
    markets: set[str] = set()
    for aliases in ledger["fields"].values():
        for entries in aliases.values():
            markets.update(str(e["market"]) for e in entries)
    for by_mkt in ledger["audit_statuses"].values():
        markets.update(by_mkt.keys())

    hit_by_market: dict[tuple[str, str, str], bool] = {}
    for fid, aliases in ledger["fields"].items():
        for alias, entries in aliases.items():
            if alias == LLM_KEY:
                continue
            for e in entries:
                hit_by_market[(fid, alias, str(e["market"]))] = True

    dead: list[dict[str, Any]] = []
    for fid, alias_list in sorted(catalog_aliases.items()):
        for market in sorted(markets):
            # only markets where this FIELD was audited at least once
            audited = ledger["audit_statuses"].get(fid, {}).get(market)
            if not audited:
                continue
            for alias in alias_list:
                if not hit_by_market.get((fid, alias, market)):
                    dead.append({"field_id": fid, "market": market,
                                  "alias": alias})

    promo_groups: dict[tuple[str, str, str], set[str]] = {}
    for fid, aliases in ledger["fields"].items():
        for alias, entries in aliases.items():
            if alias == LLM_KEY:
                continue
            for e in entries:
                sugg = e.get("suggested")
                if e.get("match_kind") == "normalized" and sugg:
                    promo_groups.setdefault(
                        (fid, str(e["market"]), str(sugg)), set(),
                    ).add(str(e["company"]))
    promotions = [
        {"field_id": fid, "market": market, "suggested_alias": sugg,
         "companies": sorted(cos)}
        for (fid, market, sugg), cos in sorted(promo_groups.items())
        if len(cos) >= min_companies
    ]

    terminals = []
    for fid, by_mkt in sorted(ledger["audit_statuses"].items()):
        for market, by_co in sorted(by_mkt.items()):
            no_hit = sorted(c for c, s in by_co.items() if s == "no_hit")
            if len(no_hit) >= min_companies:
                terminals.append({"field_id": fid, "market": market,
                                   "no_hit_companies": no_hit})

    return {"dead_aliases": dead, "promotion_candidates": promotions,
            "terminal_candidates": terminals}


def write_ledger_views(
    ledger: Ledger,
    *,
    catalog_aliases: dict[str, tuple[str, ...]],
    out_md: Path,
    min_companies: int = 2,
) -> None:
    signals = compute_signals(
        ledger, catalog_aliases=catalog_aliases, min_companies=min_companies,
    )
    lines = ["# Alias Match Ledger — governance view", "",
             f"- note: {ledger['note']}", ""]
    lines += ["## Promotion candidates (normalized phrase, "
              f">= {min_companies} companies per market)", "",
              "| Field | Market | Suggested alias | Companies |",
              "|---|---|---|---|"]
    for p in signals["promotion_candidates"]:
        lines.append(
            f"| `{p['field_id']}` | {p['market']} | "
            f"{str(p['suggested_alias']).replace('|', chr(92) + '|')} | "
            f"{', '.join(p['companies'])} |")
    lines += ["", "## Dead aliases (zero hits in an audited market)", "",
              "| Field | Market | Alias |", "|---|---|---|"]
    for d in signals["dead_aliases"]:
        lines.append(
            f"| `{d['field_id']}` | {d['market']} | "
            f"{str(d['alias']).replace('|', chr(92) + '|')} |")
    lines += ["", f"## Terminal candidates (no_hit across >= {min_companies} "
              "companies in a market)", "",
              "| Field | Market | Companies |", "|---|---|---|"]
    for t in signals["terminal_candidates"]:
        lines.append(f"| `{t['field_id']}` | {t['market']} | "
                     f"{', '.join(t['no_hit_companies'])} |")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

(If the `chr(92)` pipe-escape reads poorly, use a small `_md_escape` helper — match what `write_alias_audit` does.)

- [ ] **Step 4: Run tests + full gate.**

- [ ] **Step 5: Commit** `feat: market-scoped ledger governance signals + md view (PR-2 task 3)`

---

### Task 4: CLI `index-alias-matches` + promotion review artifact

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/alias_ledger.py` (promotion artifact writer)
- Modify: `src/financial_report_llm_extractor/cli.py`
- Test: `tests/test_alias_ledger.py`

- [ ] **Step 1: Failing tests:**

```python
def test_emit_promotion_review_compatible_shape(tmp_path: Path) -> None:
    from financial_report_llm_extractor.structured_sources.alias_ledger import (
        emit_promotion_review,
    )
    ledger = _signal_ledger()
    emit_promotion_review(
        ledger,
        catalog_aliases={"receivables_aging": (
            "ageing analysis of trade receivables",)},
        output_dir=tmp_path,
        min_companies=2,
    )
    data = json.loads((tmp_path / "alias_promotion_review.json").read_text())
    assert data["report_id"] == "alias_promotion_review"
    promoted = data["promoted"]
    assert promoted == [{
        "field_id": "receivables_aging",
        "source": "pdf",
        "raw_field_name": "ageing analysis of the trade receivables",
        "raw_field_code": None,
        "action": "promote",
        "reason": "normalized phrase hit in 2 HK companies (00001, 01113)",
        "aliases": ["ageing analysis of the trade receivables"],
    }]
    assert (tmp_path / "alias_promotion_review.md").exists()


def test_cli_index_alias_matches_end_to_end(tmp_path: Path) -> None:
    from financial_report_llm_extractor.cli import main

    runs = tmp_path / "runs"
    _write_run_dir(runs)
    audits = tmp_path / "audits"
    _write_audit_dir(audits)
    ledger_path = tmp_path / "ledger.json"

    rc = main([
        "index-alias-matches",
        "--runs", str(runs),
        "--audits", str(audits),
        "--ledger", str(ledger_path),
        "--emit-promotion-review", str(tmp_path / "promo"),
    ])
    assert rc == 0
    data = json.loads(ledger_path.read_text())
    assert "bond_payable" in data["fields"]
    assert "receivables_aging" in data["fields"]
    assert (ledger_path.with_suffix(".md")).exists()
    # idempotent rerun: byte-identical ledger
    first = ledger_path.read_bytes()
    rc2 = main([
        "index-alias-matches", "--runs", str(runs),
        "--audits", str(audits), "--ledger", str(ledger_path),
    ])
    assert rc2 == 0 and ledger_path.read_bytes() == first
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement.**

`emit_promotion_review` (append to alias_ledger.py) — shape-compatible with `source_mapping_expansion.CandidateDecision` (read that module first; field-for-field: field_id/source/raw_field_name/raw_field_code/action/reason/aliases):

```python
def emit_promotion_review(
    ledger: Ledger,
    *,
    catalog_aliases: dict[str, tuple[str, ...]],
    output_dir: Path,
    min_companies: int = 2,
) -> None:
    signals = compute_signals(
        ledger, catalog_aliases=catalog_aliases, min_companies=min_companies,
    )
    promoted = [
        {
            "field_id": p["field_id"],
            "source": "pdf",
            "raw_field_name": p["suggested_alias"],
            "raw_field_code": None,
            "action": "promote",
            "reason": (
                f"normalized phrase hit in {len(p['companies'])} "
                f"{p['market']} companies ({', '.join(p['companies'])})"
            ),
            "aliases": [p["suggested_alias"]],
        }
        for p in signals["promotion_candidates"]
    ]
    payload = {
        "report_id": "alias_promotion_review",
        "ledger_note": ledger["note"],
        "promoted": promoted,
        "deferred": [],
        "blocked": [],
        "summary": {"promoted": len(promoted), "deferred": 0, "blocked": 0},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "alias_promotion_review.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = ["# Alias promotion review (review-gated)", "",
             "| Field | Suggested alias | Reason |", "|---|---|---|"]
    for p in promoted:
        lines.append(f"| `{p['field_id']}` | {p['raw_field_name']} | "
                     f"{p['reason']} |")
    (output_dir / "alias_promotion_review.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8",
    )
```

CLI parser (after audit-pdf-aliases block):

```python
    ledger_parser = subparsers.add_parser(
        "index-alias-matches",
        help="Aggregate alias hits from runs + audits into the match ledger.",
    )
    ledger_parser.add_argument(
        "--runs", type=Path, action="append", default=[],
        help="Run roots; each immediate subdir with llm_evidence_supplement"
             ".json + evaluation.json is indexed.",
    )
    ledger_parser.add_argument(
        "--audits", type=Path, action="append", default=[],
        help="Audit roots; each immediate subdir (or the dir itself) with "
             "alias_audit.json is indexed.",
    )
    ledger_parser.add_argument(
        "--ledger", type=Path,
        default=Path("field_catalog/alias_match_ledger.json"),
    )
    ledger_parser.add_argument(
        "--catalog", type=Path,
        default=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
    )
    ledger_parser.add_argument("--min-companies", type=int, default=2)
    ledger_parser.add_argument(
        "--emit-promotion-review", type=Path, default=None, metavar="DIR",
    )
```

Handler:

```python
    if args.command == "index-alias-matches":
        import sys as _sys

        from financial_report_llm_extractor.structured_sources.alias_ledger import (
            emit_promotion_review,
            index_audit_dir,
            index_run_dir,
            load_ledger,
            save_ledger,
            write_ledger_views,
        )

        ledger = load_ledger(args.ledger)
        warnings: list[str] = []

        def _candidates(root: Path) -> list[Path]:
            if (root / "alias_audit.json").exists() or (
                root / "llm_evidence_supplement.json"
            ).exists():
                return [root]
            return sorted(p for p in root.iterdir() if p.is_dir())

        for root in args.runs:
            for d in _candidates(root):
                warnings += index_run_dir(ledger, d)
        for root in args.audits:
            for d in _candidates(root):
                warnings += index_audit_dir(ledger, d)
        for w in warnings:
            print(f"warning: {w}", file=_sys.stderr)

        catalog = load_source_mapping_catalog(
            args.catalog, priorities=("P0", "P1", "P2", "P3", "P4"),
        )
        catalog_aliases = {
            fid: entry.pdf_aliases
            for fid, entry in catalog.entries.items()
            if entry.pdf_aliases
        }
        save_ledger(ledger, args.ledger)
        write_ledger_views(
            ledger, catalog_aliases=catalog_aliases,
            out_md=args.ledger.with_suffix(".md"),
            min_companies=args.min_companies,
        )
        if args.emit_promotion_review is not None:
            emit_promotion_review(
                ledger, catalog_aliases=catalog_aliases,
                output_dir=args.emit_promotion_review,
                min_companies=args.min_companies,
            )
        print(json.dumps({
            "ledger": str(args.ledger),
            "fields": len(ledger["fields"]),
            "warnings": len(warnings),
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
```

- [ ] **Step 4: Run tests + full gate.**

- [ ] **Step 5: Commit** `feat: index-alias-matches CLI + promotion review artifact (PR-2 task 4)`

---

### Task 5: wheel exclusion + workflow doc + operator ledger build

**Files:**
- Modify: `pyproject.toml`
- Modify: `docs/new-company-analysis-workflow.md`
- Create (operator): `field_catalog/alias_match_ledger.json` + `.md`

- [ ] **Step 1: Wheel exclusion.** The wheel force-includes the whole `field_catalog/` dir (`pyproject.toml` `[tool.hatch.build.targets.wheel.force-include]`). Add:

```toml
[tool.hatch.build.targets.wheel]
exclude = [
  "field_catalog/alias_match_ledger.json",
  "field_catalog/alias_match_ledger.md",
]
```

VERIFY hatchling actually honors exclude against force-include — create a dummy `field_catalog/alias_match_ledger.json` (`{}`), run `uv build`, then `unzip -l dist/*.whl | grep alias_match_ledger` → MUST be empty. If hatchling does NOT honor it, fall back: change the force-include mapping to a `[tool.hatch.build.targets.wheel.force-include]` per-file list of the 6 real catalog JSONs (grep `field_catalog/*.json` for the canonical set referenced in tests/test_catalog_consistency.py) and document why. Clean `dist/` afterward.

- [ ] **Step 2: Workflow doc.** In `docs/new-company-analysis-workflow.md` Step 6 list, add item:

```markdown
7. 跑 `financial-report-llm-extractor index-alias-matches --runs tmp/runs/<run-dir> --audits tmp/runs/<audit-dir>` 更新台账
   （`field_catalog/alias_match_ledger.{json,md}`）；catalog 加别名时引用台账证据，
   转正建议走 `--emit-promotion-review` 的 review 工件。
```

(Adapt numbering to the actual list; also add one TL;DR line after Step 6.)

- [ ] **Step 3: Operator ledger build** (controller, not subagent). The 8 pr3_gate on-audits lack company metadata — re-run them WITH metadata (chunks cached, seconds each):

```bash
# for each cohort company: audit with metadata into the same _on dir
financial-report-llm-extractor audit-pdf-aliases --pdf <pdf> \
  --alias-normalization on --company <co> --market <CN|HK> --year <yr> \
  --out tmp/runs/pr3_gate/<co>_on
# then index everything
financial-report-llm-extractor index-alias-matches \
  --runs tmp/runs/00001_2025_postmerge --runs tmp/runs/00001_2024_postmerge \
  --runs tmp/runs/00001_2023_postmerge --runs tmp/runs/pr3_gate/reval_00001_on \
  --runs tmp/runs/pr3_gate/reval_600519_on \
  --audits tmp/runs/pr3_gate/00001_on ... (all 8 _on dirs) \
  --emit-promotion-review tmp/runs/pr3_gate/promo
```

Acceptance: ledger contains 8-cohort audit hits + LLM hits; rerun is byte-identical; promotion review surfaces ≥1 multi-company candidate (expect the fix_assets/equity_attributable normalized phrases seen in the gate diff). Commit the ledger + md.

- [ ] **Step 4: Full gate + commit** `feat: ledger wheel exclusion + workflow step + cohort ledger (PR-2 task 5)`

---

## Self-review notes

- Spec coverage: `_llm` field-level key (no fake alias attribution) → Task 2; evaluation.json join + skip-warning → Task 2; market-scoped 3 signals → Task 3 (terminal signal made computable via `audit_statuses`, decision #4); promotion via expansion-review-shaped artifact → Task 4; derived-view note + no timestamps + rm-safe → Task 2 (decision #2); wheel exclusion → Task 5; workflow Step 6 → Task 5.
- Type consistency: `Ledger = dict[str, Any]` (JSON-shaped, not frozen dataclasses — it's a mutable accumulator and a derived artifact, not a pipeline contract; consistent with R1 indexer's dict-shaped handling).
- Audit metadata (Task 1) feeds `index_audit_dir`'s skip-guard (Task 2) — names `company/market/year` identical across CLI/JSON/ledger.
