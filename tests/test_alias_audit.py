"""Tests for alias_audit (spec PR-1, component 2)."""
from __future__ import annotations

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
    assert all(c.via in ("alias_top_k", "broad_keyword",
                         "section_fallback") for c in sel)


def test_section_anchor_coverage_reported() -> None:
    r = _make()
    assert 141 in r.section_anchor_coverage["cash_flow"]
    assert 134 in r.section_anchor_coverage["income_statement"]
    assert r.section_anchor_coverage["balance_sheet"] == ()


def test_summary_counts() -> None:
    r = _make()
    assert r.summary == {"exact_hit": 1, "prose_only_hit": 1,
                         "normalized_only_hit": 1, "no_hit": 1}
