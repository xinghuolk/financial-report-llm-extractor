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

from financial_report_llm_extractor.structured_sources.alias_matching import (
    _EDGE_PUNCT,
)

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
    try:
        year = int(str(ev["period_end"])[:4])
    except (ValueError, TypeError):
        return [
            f"{run_dir}: period_end {ev.get('period_end')!r} not parseable "
            f"as year, skipped"
        ]
    supp = json.loads(supp_path.read_text(encoding="utf-8"))
    raw_items = supp.get("items")
    if not isinstance(raw_items, dict):
        return [f"{run_dir}: supplement 'items' is not a dict, skipped"]
    for field_id, item in raw_items.items():
        if not isinstance(item, dict):
            continue
        if item.get("status") != "present":
            continue
        _upsert(ledger, field_id, LLM_KEY, {
            "company": company, "year": year,
            "page": item.get("page"), "market": market,
        })
    return []


def _md_escape(s: str) -> str:
    """Escape pipe characters for Markdown table cells."""
    return s.replace("|", "\\|")


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
            alias = hit.get("alias")
            if alias is None:
                continue
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
                    _EDGE_PUNCT).lower()
                if stripped in suggested_by_text:
                    entry["suggested"] = stripped
            _upsert(ledger, field_id, str(alias), entry)
        ledger["audit_statuses"].setdefault(field_id, {}).setdefault(
            str(market), {},
        )[str(company)] = str(fr.get("status"))
    return []


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
            f"{_md_escape(str(p['suggested_alias']))} | "
            f"{', '.join(p['companies'])} |")
    lines += ["", "## Dead aliases (zero hits in an audited market)", "",
              "| Field | Market | Alias |", "|---|---|---|"]
    for d in signals["dead_aliases"]:
        lines.append(
            f"| `{d['field_id']}` | {d['market']} | "
            f"{_md_escape(str(d['alias']))} |")
    lines += ["", f"## Terminal candidates (no_hit across >= {min_companies} "
              "companies in a market)", "",
              "| Field | Market | Companies |", "|---|---|---|"]
    for t in signals["terminal_candidates"]:
        lines.append(f"| `{t['field_id']}` | {t['market']} | "
                     f"{', '.join(t['no_hit_companies'])} |")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
