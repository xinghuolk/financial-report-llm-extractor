"""Tests for alias_audit (spec PR-1, component 2)."""
from __future__ import annotations

import json as _json
from pathlib import Path
from typing import cast

from financial_report_llm_extractor.field_metadata import (
    FieldDomain,
    FieldTaxonomyCatalog,
    FieldTaxonomyEntry,
    FieldValueType,
    Priority,
)
from financial_report_llm_extractor.structured_sources.alias_audit import (
    AuditReport,
    audit_chunks,
    emit_catalog_patch,
    write_alias_audit,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
    SourceMappingEntry,
    SourceValueType,
    StatementType,
)


def _entry(field_id: str, *, pdf_aliases: tuple[str, ...],
           statement_type: str = "balance_sheet",
           value_type: str = "money") -> SourceMappingEntry:
    return SourceMappingEntry(
        field_id=field_id, priority="P0",
        value_type=cast(SourceValueType, value_type),
        statement_type=cast(StatementType, statement_type),
        currency_requirement="required", unit_requirement="required",
        source_aliases={"yahoo": ("X",)}, pdf_aliases=pdf_aliases,
    )


def _tax(field_id: str, *, statement_type: str = "balance_sheet",
         value_type: str = "money") -> FieldTaxonomyEntry:
    return FieldTaxonomyEntry(
        field_id=field_id, priority=cast(Priority, "P0"),
        domain=cast(FieldDomain, statement_type),
        statement_type=cast(StatementType, statement_type),
        value_type=cast(FieldValueType, value_type),
        source_mode="direct", period_type="duration",
        scope_expectation="unknown", currency_requirement="required",
        unit_requirement="required",
        evidence_requirement="source_only_allowed",
        fallback_policy="pdf_allowed", description="d",
    )


def _catalog(entries: list[SourceMappingEntry]) -> SourceMappingCatalog:
    return SourceMappingCatalog(
        catalog_id="t", version="1",
        entries={e.field_id: e for e in entries},
    )


def _taxonomy(entries: list[FieldTaxonomyEntry]) -> FieldTaxonomyCatalog:
    return FieldTaxonomyCatalog(
        catalog_id="tt", version="1", source_priority_catalog="p",
        fields={e.field_id: e for e in entries},
    )


def _block(chunk_id: str, page: int, text: str) -> dict[str, object]:
    return {"block_id": chunk_id, "chunk_id": chunk_id, "page": str(page),
            "record_type": "block", "text": text}


_CHUNKS: list[dict[str, object]] = [
    # cash-flow section page (anchor: "statement of cash flows")
    _block("c1", 141,
           "Consolidated statement of cash flows. Tax paid (5,571). "
           "Net cash from operating activities"),
    # MD&A prose page (NOT a cash-flow section page)
    _block("c2", 56, "partly offset by higher taxes paid in the year"),
    # notes page for the normalized-only case
    _block("c3", 229,
           "The ageing analysis of the trade receivables, presented "
           "based on the invoice date"),
    # income-statement section page for the clean exact case
    _block("c4", 134, "Consolidated income statement. Revenue 280,036"),
    # a non-block record that must be IGNORED by alias diagnostics
    {"chunk_id": "p134", "page": "134", "record_type": "page_text",
     "text": "Revenue Revenue Revenue"},
]


def _make() -> AuditReport:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue",),
               statement_type="income_statement"),
        _entry("c_paid_for_taxes", pdf_aliases=("taxes paid",),
               statement_type="cash_flow"),
        _entry("receivables_aging",
               pdf_aliases=("ageing analysis of trade receivables",),
               statement_type="notes", value_type="text"),
        _entry("rd_exp", pdf_aliases=("research and development",),
               statement_type="income_statement"),
    ])
    taxonomy = _taxonomy([
        _tax("revenue", statement_type="income_statement"),
        _tax("c_paid_for_taxes", statement_type="cash_flow"),
        _tax("receivables_aging", statement_type="notes",
             value_type="text"),
        _tax("rd_exp", statement_type="income_statement"),
    ])
    return audit_chunks(
        chunks=list(_CHUNKS), catalog=catalog, taxonomy=taxonomy,
        priorities=("P0",), pdf_path=Path("fake.pdf"),
    )


def test_four_state_classification() -> None:
    r = _make()
    assert r.fields["revenue"].status == "exact_hit"
    # exact alias hit exists (p56) but outside the cash-flow section pages
    assert r.fields["c_paid_for_taxes"].status == "prose_only_hit"
    assert r.fields["receivables_aging"].status == "normalized_only_hit"
    assert r.fields["rd_exp"].status == "no_hit"


def test_suggested_aliases_carry_pdf_phrasing() -> None:
    r = _make()
    s = r.fields["receivables_aging"].suggested_aliases
    assert s == ("ageing analysis of the trade receivables",)


def test_alias_diagnostics_skip_non_block_records() -> None:
    r = _make()
    hits = r.fields["revenue"].hits
    # one block hit on p134; the page_text record (3 occurrences) ignored
    assert len(hits) == 1 and hits[0].page == 134 and hits[0].count == 1


def test_in_statement_section_flags() -> None:
    r = _make()
    tax_hits = r.fields["c_paid_for_taxes"].hits
    assert [h.in_statement_section for h in tax_hits] == [False]
    # notes has no section anchors -> None (not applicable)
    aging = r.fields["receivables_aging"].hits
    assert aging[0].in_statement_section is None


def test_selected_chunks_use_production_selection() -> None:
    r = _make()
    sel = r.fields["revenue"].selected_chunks
    # broad_keyword path (single alias < 3 -> broad strategy per
    # derive_targets); chunk c4 contains the token 'revenue'
    assert any(c.chunk_id == "c4" for c in sel)
    assert all(c.via == "broad_keyword" for c in sel)


def test_section_anchor_coverage_reported() -> None:
    r = _make()
    assert 141 in r.section_anchor_coverage["cash_flow"]
    assert 134 in r.section_anchor_coverage["income_statement"]
    assert r.section_anchor_coverage["balance_sheet"] == ()


def test_summary_counts() -> None:
    r = _make()
    assert r.summary == {"exact_hit": 1, "prose_only_hit": 1,
                         "normalized_only_hit": 1, "no_hit": 1}


def test_write_alias_audit_json_and_md(tmp_path: Path) -> None:
    r = _make()
    write_alias_audit(r, tmp_path)
    data = _json.loads((tmp_path / "alias_audit.json").read_text())
    assert data["schema_version"] == "alias_audit_v1"
    assert data["fields"]["c_paid_for_taxes"]["status"] == "prose_only_hit"
    assert data["summary"]["no_hit"] == 1
    assert list(data["fields"].keys()) == sorted(data["fields"].keys())
    md = (tmp_path / "alias_audit.md").read_text()
    assert "prose_only_hit" in md and "receivables_aging" in md


def test_emit_catalog_patch_lists_suggested_adds(tmp_path: Path) -> None:
    r = _make()
    emit_catalog_patch(r, tmp_path)
    patch = _json.loads((tmp_path / "catalog_patch.json").read_text())
    assert patch == {
        "schema_version": "alias_catalog_patch_v1",
        "note": "review-gated suggestions; apply manually to "
                "field_catalog/turtle_v015_source_mapping_minimal.json",
        "add_pdf_aliases": {
            "receivables_aging": [
                "ageing analysis of the trade receivables"
            ],
        },
    }


def test_write_alias_audit_warns_on_empty_anchor_types(tmp_path: Path) -> None:
    r = _make()
    write_alias_audit(r, tmp_path)
    data = _json.loads((tmp_path / "alias_audit.json").read_text())
    # balance_sheet anchors matched zero pages in the fixture
    assert "balance_sheet" in data["warnings"]["empty_anchor_statement_types"]


def test_cli_audit_pdf_aliases_reuses_existing_chunks(tmp_path: Path) -> None:
    from financial_report_llm_extractor.cli import main

    out = tmp_path / "audit"
    ingest = out / "ingest"
    ingest.mkdir(parents=True)
    with (ingest / "chunks.jsonl").open("w") as f:
        for c in _CHUNKS:
            f.write(_json.dumps(c) + "\n")

    rc = main([
        "audit-pdf-aliases",
        "--pdf", "does-not-exist.pdf",  # unused: chunks.jsonl present
        "--out", str(out),
        "--priorities", "P0,P1,P2,P3,P4",
    ])
    assert rc == 0
    assert (out / "alias_audit.json").exists()
    assert (out / "alias_audit.md").exists()
    # default real catalog: revenue must be a key in the output
    data = _json.loads((out / "alias_audit.json").read_text())
    assert "revenue" in data["fields"]


def test_cli_audit_emits_catalog_patch_when_flagged(tmp_path: Path) -> None:
    from financial_report_llm_extractor.cli import main

    out = tmp_path / "audit2"
    ingest = out / "ingest"
    ingest.mkdir(parents=True)
    with (ingest / "chunks.jsonl").open("w") as f:
        for c in _CHUNKS:
            f.write(_json.dumps(c) + "\n")

    rc = main([
        "audit-pdf-aliases", "--pdf", "x.pdf", "--out", str(out),
        "--emit-catalog-patch",
    ])
    assert rc == 0
    assert (out / "catalog_patch.json").exists()


def test_cli_audit_returns_2_when_pdf_missing(tmp_path: Path) -> None:
    """No reusable chunks + nonexistent PDF → documented exit code 2."""
    from financial_report_llm_extractor.cli import main

    rc = main([
        "audit-pdf-aliases",
        "--pdf", str(tmp_path / "missing.pdf"),
        "--out", str(tmp_path / "audit3"),
    ])
    assert rc == 2


def test_exact_hit_when_no_cash_flow_anchor_present() -> None:
    """Empty anchor coverage for a statement type → in_statement_section None,
    and an exact-hit alias must still classify as exact_hit (not prose_only)."""
    catalog = _catalog([
        _entry("c_paid_for_taxes", pdf_aliases=("taxes paid",),
               statement_type="cash_flow"),
    ])
    taxonomy = _taxonomy([
        _tax("c_paid_for_taxes", statement_type="cash_flow"),
    ])
    # Only chunk: exact match on p56 but NO cash-flow section anchor block
    chunks = [_block("c1", 56, "partly offset by higher taxes paid in the year")]
    r = audit_chunks(
        chunks=chunks, catalog=catalog, taxonomy=taxonomy,
        priorities=("P0",), pdf_path=Path("fake.pdf"),
    )
    assert r.section_anchor_coverage["cash_flow"] == ()
    fr = r.fields["c_paid_for_taxes"]
    assert fr.status == "exact_hit"
    assert all(h.in_statement_section is None for h in fr.hits)


_REPO_ROOT = Path(__file__).resolve().parents[1]
_MINI_FIXTURE = (
    _REPO_ROOT / "tests/fixtures/pdf_chunks/alias_audit_mini_00001.jsonl"
)


def test_acceptance_00001_known_states_with_real_catalog() -> None:
    """Spec PR-1 acceptance canary against the LIVE production catalog.

    Reproduces three documented failure-class statuses (② prose_only,
    ① normalized_only, ⑤ no_hit) plus the healthy exact_hit path using
    real FY2025 00001 phrasings. Catalog alias edits to the asserted
    fields are EXPECTED to trip this test — that is its job.

    Fixture decoys p0059/p0076/p0007 (pledged-as-security, treasury
    shares, one-time loss) hit no catalog alias and are deliberately
    unasserted; restricted_cash's "pledged deposits" alias shares no
    full-token window with "pledged as security" (synonym, not
    normalization-reachable).
    """
    from financial_report_llm_extractor.field_metadata import (
        load_field_taxonomy,
    )
    from financial_report_llm_extractor.structured_sources.catalog import (
        load_source_mapping_catalog,
    )
    from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
        load_chunks_jsonl,
    )

    chunks = load_chunks_jsonl(_MINI_FIXTURE)
    catalog = load_source_mapping_catalog(
        _REPO_ROOT / "field_catalog/turtle_v015_source_mapping_minimal.json",
        priorities=("P0", "P1", "P2", "P3", "P4"),
    )
    taxonomy = load_field_taxonomy(
        _REPO_ROOT / "field_catalog/turtle_v015_field_taxonomy.json",
    )
    r = audit_chunks(
        chunks=chunks, catalog=catalog, taxonomy=taxonomy,
        priorities=("P0", "P1", "P2", "P3", "P4"),
        pdf_path=Path("00001_2025_mini.pdf"),
    )

    # class ② wrong-page: the ONLY hit is 'taxes paid' exact on p56,
    # which is not a cash-flow anchor page -> prose_only. p141's real
    # line 'Tax paid' matches no alias at all, not even normalized
    # (naive es-strip: taxes->taxe != tax).
    assert r.fields["c_paid_for_taxes"].status == "prose_only_hit"
    # class ① alias gap healed by normalization, suggestion recovered
    aging = r.fields["receivables_aging"]
    assert aging.status == "normalized_only_hit"
    assert any(
        "ageing analysis of the trade receivables" in s
        for s in aging.suggested_aliases
    )
    related = r.fields["related_party_receivables_payables"]
    assert related.status == "normalized_only_hit"
    # class ⑤ genuinely absent
    assert r.fields["rd_exp"].status == "no_hit"
    assert r.fields["time_deposits_or_wealth_products"].status == "no_hit"
    # healthy field stays exact
    assert r.fields["revenue"].status == "exact_hit"


def test_audit_chunks_normalization_override() -> None:
    # Use aliases that cannot accidentally substring-match the chunk text.
    # "zzz_dummy_*" are inert; only the primary alias participates.
    catalog = _catalog([
        _entry("receivables_aging",
               pdf_aliases=("ageing analysis of trade receivables",
                            "zzz_dummy_1", "zzz_dummy_2"),
               statement_type="notes", value_type="text"),
    ])
    taxonomy = _taxonomy([
        _tax("receivables_aging", statement_type="notes", value_type="text"),
    ])
    chunks = [_block("c3", 229,
                     "The ageing analysis of the trade receivables, presented")]
    # Exact tier fails here by design: the alias lacks the text's "the"
    # (stop-word) — only the normalized fold bridges it. If exact matching
    # is ever relaxed, this test's off-branch premise changes.
    off = audit_chunks(chunks=chunks, catalog=catalog, taxonomy=taxonomy,
                       priorities=("P0",), pdf_path=Path("f.pdf"))
    on = audit_chunks(chunks=chunks, catalog=catalog, taxonomy=taxonomy,
                      priorities=("P0",), pdf_path=Path("f.pdf"),
                      alias_normalization_override=True)
    # selection simulation differs: off -> no selected chunks (exact miss),
    # on -> the normalized chunk is selected
    assert off.fields["receivables_aging"].selected_chunks == ()
    assert [c.chunk_id for c in
            on.fields["receivables_aging"].selected_chunks] == ["c3"]


def test_cli_audit_alias_normalization_flag(tmp_path: Path) -> None:
    from financial_report_llm_extractor.cli import main

    out = tmp_path / "audit_on"
    ingest = out / "ingest"
    ingest.mkdir(parents=True)
    with (ingest / "chunks.jsonl").open("w") as f:
        for c in _CHUNKS:
            f.write(_json.dumps(c) + "\n")

    rc = main([
        "audit-pdf-aliases", "--pdf", "x.pdf", "--out", str(out),
        "--alias-normalization", "on",
    ])
    assert rc == 0
    data = _json.loads((out / "alias_audit.json").read_text())
    # with normalization on, receivables_aging's selection simulation
    # now selects the normalized chunk
    assert [c["chunk_id"] for c in
            data["fields"]["receivables_aging"]["selected_chunks"]] == ["c3"]


def test_cli_audit_alias_normalization_off(tmp_path: Path) -> None:
    from financial_report_llm_extractor.cli import main

    out = tmp_path / "audit_off"
    ingest = out / "ingest"
    ingest.mkdir(parents=True)
    with (ingest / "chunks.jsonl").open("w") as f:
        for c in _CHUNKS:
            f.write(_json.dumps(c) + "\n")

    rc = main([
        "audit-pdf-aliases", "--pdf", "x.pdf", "--out", str(out),
        "--alias-normalization", "off",
    ])
    assert rc == 0
    data = _json.loads((out / "alias_audit.json").read_text())
    # exact tier misses the "the"-bridged phrasing -> nothing selected
    assert data["fields"]["receivables_aging"]["selected_chunks"] == []


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


def test_cli_audit_rejects_chunks_from_different_pdf(tmp_path: Path) -> None:
    """Review F1: cached chunks built from another PDF must hard-fail, not
    silently emit an audit attributed to the requested PDF."""
    from financial_report_llm_extractor.cli import main

    pdf = tmp_path / "real.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake content for hashing")
    out = tmp_path / "audit_stale"
    ingest = out / "ingest"
    ingest.mkdir(parents=True)
    with (ingest / "chunks.jsonl").open("w") as f:
        for c in _CHUNKS:
            rec = dict(c)
            rec["source_pdf_hash"] = "deadbeef" * 8
            f.write(_json.dumps(rec) + "\n")

    rc = main([
        "audit-pdf-aliases", "--pdf", str(pdf), "--out", str(out),
    ])
    assert rc == 2
    assert not (out / "alias_audit.json").exists()


def test_cli_audit_accepts_chunks_matching_pdf_hash(tmp_path: Path) -> None:
    from financial_report_llm_extractor.cli import main
    from financial_report_llm_extractor.ingestion import compute_sha256

    pdf = tmp_path / "real.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake content for hashing")
    out = tmp_path / "audit_match"
    ingest = out / "ingest"
    ingest.mkdir(parents=True)
    h = compute_sha256(pdf)
    with (ingest / "chunks.jsonl").open("w") as f:
        for c in _CHUNKS:
            rec = dict(c)
            rec["source_pdf_hash"] = h
            f.write(_json.dumps(rec) + "\n")

    rc = main(["audit-pdf-aliases", "--pdf", str(pdf), "--out", str(out)])
    assert rc == 0
    assert (out / "alias_audit.json").exists()
