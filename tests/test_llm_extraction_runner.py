"""Tests for the LLM extraction orchestrator."""

from __future__ import annotations

from typing import cast

from financial_report_llm_extractor.field_metadata import (
    FieldDomain,
    FieldTaxonomyCatalog,
    FieldTaxonomyEntry,
    FieldValueType,
    Priority,
    StatementType,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
    SourceMappingEntry,
)
from financial_report_llm_extractor.structured_sources.models import SourceValueType
from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
    LlmExtractionTarget,
    derive_targets,
    select_chunks,
)


def _entry(field_id: str, *, pdf_aliases: tuple[str, ...] = (),
           statement_type: str = "balance_sheet",
           value_type: str = "money",
           priority: str = "P0") -> SourceMappingEntry:
    return SourceMappingEntry(
        field_id=field_id,
        priority=priority,
        value_type=cast(SourceValueType, value_type),
        statement_type=cast(StatementType, statement_type),
        currency_requirement="required",
        unit_requirement="required",
        source_aliases={"akshare": ("X",)},
        pdf_aliases=pdf_aliases,
    )


def _tax_entry(field_id: str, *, description: str = "desc",
               statement_type: str = "balance_sheet",
               value_type: str = "money",
               priority: str = "P0") -> FieldTaxonomyEntry:
    return FieldTaxonomyEntry(
        field_id=field_id,
        priority=cast(Priority, priority),
        domain=cast(FieldDomain, statement_type),
        statement_type=cast(StatementType, statement_type),
        value_type=cast(FieldValueType, value_type),
        source_mode="direct",
        period_type="duration",
        scope_expectation="unknown",
        currency_requirement="required",
        unit_requirement="required",
        evidence_requirement="source_only_allowed",
        fallback_policy="pdf_allowed",
        description=description,
    )


def _catalog(entries: list[SourceMappingEntry]) -> SourceMappingCatalog:
    return SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={e.field_id: e for e in entries},
    )


def _taxonomy(entries: list[FieldTaxonomyEntry]) -> FieldTaxonomyCatalog:
    return FieldTaxonomyCatalog(
        catalog_id="test_taxonomy",
        version="1",
        source_priority_catalog="prio",
        fields={e.field_id: e for e in entries},
    )


def test_derive_targets_uses_taxonomy_description() -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue", "营业收入"))
    ])
    taxonomy = _taxonomy([_tax_entry("revenue", description="operating revenue")])

    targets = derive_targets(catalog, taxonomy, priorities=("P0",))

    assert len(targets) == 1
    t = targets[0]
    assert t.field_id == "revenue"
    assert t.field_description == "operating revenue"
    assert t.aliases == ("revenue", "营业收入")


def test_derive_targets_skips_fields_without_pdf_aliases() -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue",)),
        _entry("net_profit", pdf_aliases=()),  # no aliases
    ])
    taxonomy = _taxonomy([
        _tax_entry("revenue"),
        _tax_entry("net_profit"),
    ])

    targets = derive_targets(catalog, taxonomy, priorities=("P0",))

    assert [t.field_id for t in targets] == ["revenue"]


def test_derive_targets_filters_by_priority() -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("a",), priority="P0"),
        _entry("rd_exp", pdf_aliases=("b",), priority="P1"),
        _entry("dps", pdf_aliases=("c",), priority="P3"),
    ])
    taxonomy = _taxonomy([
        _tax_entry("revenue", priority="P0"),
        _tax_entry("rd_exp", priority="P1"),
        _tax_entry("dps", priority="P3"),
    ])

    targets = derive_targets(catalog, taxonomy, priorities=("P0", "P1"))

    assert {t.field_id for t in targets} == {"revenue", "rd_exp"}


def test_derive_target_chooses_alias_top_k_for_three_or_more_aliases() -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("a", "b", "c"))
    ])
    taxonomy = _taxonomy([_tax_entry("revenue")])

    target = derive_targets(catalog, taxonomy, priorities=("P0",))[0]
    assert target.chunk_strategy == "alias_top_k"


def test_derive_target_chooses_broad_keyword_for_few_aliases() -> None:
    catalog = _catalog([
        _entry("rd_exp", pdf_aliases=("research and development",))
    ])
    taxonomy = _taxonomy([_tax_entry("rd_exp")])

    target = derive_targets(catalog, taxonomy, priorities=("P0",))[0]
    assert target.chunk_strategy == "broad_keyword"


def _chunk(chunk_id: str, page: int, text: str,
           statement_type: str | None = None) -> dict[str, object]:
    rec: dict[str, object] = {
        "chunk_id": chunk_id,
        "page": page,
        "text": text,
    }
    if statement_type is not None:
        rec["statement_type"] = statement_type
    return rec


def test_select_chunks_alias_top_k_orders_by_alias_count() -> None:
    target = LlmExtractionTarget(
        field_id="revenue",
        field_description="d",
        statement_type="income_statement",
        value_type="money",
        aliases=("revenue", "营业收入"),
        chunk_strategy="alias_top_k",
    )
    chunks = [
        _chunk("a", 1, "营业收入 1000"),  # 1 hit
        _chunk("b", 2, "revenue revenue revenue"),  # 3 hits
        _chunk("c", 3, "no match"),
        _chunk("d", 4, "revenue 营业收入"),  # 2 hits
    ]

    selected = select_chunks(chunks, target, top_k_standard=10)

    selected_ids = [c["chunk_id"] for c in selected]
    # b (3 hits), d (2 hits), a (1 hit); c excluded (zero hits)
    assert selected_ids == ["b", "d", "a"]


def test_select_chunks_alias_top_k_caps_at_top_k() -> None:
    target = LlmExtractionTarget(
        field_id="revenue",
        field_description="d",
        statement_type="income_statement",
        value_type="money",
        aliases=("rev",),
        chunk_strategy="alias_top_k",
    )
    chunks = [_chunk(f"c{i}", i, "rev") for i in range(20)]

    selected = select_chunks(chunks, target, top_k_standard=5)

    assert len(selected) == 5


def test_select_chunks_broad_keyword_returns_keyword_matching_chunks() -> None:
    target = LlmExtractionTarget(
        field_id="rd_exp",
        field_description="d",
        statement_type="income_statement",
        value_type="money",
        aliases=("research and development",),
        chunk_strategy="broad_keyword",
    )
    chunks = [
        _chunk("a", 1, "Research and Development costs 100"),
        _chunk("b", 2, "no match"),
        _chunk("c", 3, "research expense 50"),
    ]

    selected = select_chunks(chunks, target, broad_limit=10)

    selected_ids = {c["chunk_id"] for c in selected}
    # Both a and c match (broad keyword splits aliases on spaces)
    assert "a" in selected_ids
    assert "c" in selected_ids
    assert "b" not in selected_ids


def test_select_chunks_broad_keyword_caps_at_broad_limit() -> None:
    target = LlmExtractionTarget(
        field_id="rd_exp",
        field_description="d",
        statement_type="income_statement",
        value_type="money",
        aliases=("research",),
        chunk_strategy="broad_keyword",
    )
    chunks = [_chunk(f"c{i}", i, "research") for i in range(50)]

    selected = select_chunks(chunks, target, broad_limit=10)

    assert len(selected) == 10


def test_select_chunks_alias_top_k_returns_empty_when_no_match() -> None:
    target = LlmExtractionTarget(
        field_id="x",
        field_description="d",
        statement_type="balance_sheet",
        value_type="money",
        aliases=("xyzzy",),
        chunk_strategy="alias_top_k",
    )
    chunks = [_chunk("a", 1, "no match")]

    assert select_chunks(chunks, target) == []
