"""Tests for the LLM extraction orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from financial_report_llm_extractor.field_metadata import (
    FieldDomain,
    FieldTaxonomyCatalog,
    FieldTaxonomyEntry,
    FieldValueType,
    Priority,
    StatementType,
    load_field_taxonomy,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
    SourceMappingEntry,
    load_source_mapping_catalog,
)
from financial_report_llm_extractor.structured_sources.models import SourceValueType
from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
    LlmExtractionRunResult,
    LlmExtractionTarget,
    derive_targets,
    extract_for_chunks,
    load_chunks_jsonl,
    select_chunks,
    select_statement_section_chunks,
    write_llm_evidence_supplement,
)


_REPO_ROOT = Path(__file__).resolve().parents[1]


def _entry(field_id: str, *, pdf_aliases: tuple[str, ...] = (),
           statement_type: str = "balance_sheet",
           value_type: str = "money",
           priority: str = "P0",
           absence_means_zero: bool = False) -> SourceMappingEntry:
    return SourceMappingEntry(
        field_id=field_id,
        priority=priority,
        value_type=cast(SourceValueType, value_type),
        statement_type=cast(StatementType, statement_type),
        currency_requirement="required",
        unit_requirement="required",
        source_aliases={"akshare": ("X",)},
        pdf_aliases=pdf_aliases,
        absence_means_zero=absence_means_zero,
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


# ---------------------------------------------------------------------------
# Task 1: derive_targets
# ---------------------------------------------------------------------------

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


def test_derive_targets_propagates_absence_means_zero() -> None:
    catalog = _catalog([
        _entry(
            "repurchase_of_stock",
            pdf_aliases=("repurchase of capital stock",),
            statement_type="cash_flow",
            absence_means_zero=True,
        ),
        _entry("revenue", pdf_aliases=("revenue",)),
    ])
    taxonomy = _taxonomy([
        _tax_entry("repurchase_of_stock", statement_type="cash_flow"),
        _tax_entry("revenue"),
    ])

    targets = {t.field_id: t for t in
               derive_targets(catalog, taxonomy, priorities=("P0",))}

    assert targets["repurchase_of_stock"].absence_means_zero is True
    assert targets["revenue"].absence_means_zero is False


def test_extract_for_chunks_threads_absence_means_zero_into_prompt(
    tmp_path: Path,
) -> None:
    catalog = _catalog([
        _entry(
            "repurchase_of_stock",
            pdf_aliases=("repurchase of capital stock",),
            statement_type="cash_flow",
            absence_means_zero=True,
        ),
    ])
    taxonomy = _taxonomy([
        _tax_entry("repurchase_of_stock", statement_type="cash_flow"),
    ])
    chunks = [_chunk("c1", 139, "financing activities repurchase of capital stock")]

    captured: dict[str, object] = {}

    class _CapturingClient:
        def complete_json(
            self, *, system_prompt: str, user_payload: dict[str, object],
        ) -> dict[str, object]:
            captured.update(user_payload)
            return {"field_id": "repurchase_of_stock", "found": True, "value": "0"}

    extract_for_chunks(
        chunks=chunks,
        catalog=catalog,
        taxonomy=taxonomy,
        client=_CapturingClient(),
        company_id="TEST",
        pdf_path=Path("test.pdf"),
        out_dir=tmp_path,
    )

    assert "zero_inference" in captured


def test_extract_for_chunks_absence_zero_falls_back_to_statement_section(
    tmp_path: Path,
) -> None:
    """The genuine absence_means_zero case: the buyback line (and its aliases)
    is absent from the PDF, so alias selection matches nothing. The runner must
    fall back to the field's statement section so the LLM still receives the
    zero_inference instruction and can return a real 0 — instead of bailing to
    not_found before the request is ever built.
    """
    catalog = _catalog([
        _entry(
            "repurchase_of_stock",
            pdf_aliases=("repurchase of capital stock", "share buyback"),
            statement_type="cash_flow",
            absence_means_zero=True,
        ),
    ])
    taxonomy = _taxonomy([
        _tax_entry("repurchase_of_stock", statement_type="cash_flow"),
    ])
    # Cash-flow section IS present, but it lists no buyback line / alias.
    chunks = [
        _chunk(
            "c1", 240,
            "Consolidated statement of cash flows. "
            "Net cash used in financing activities (33,434)",
        ),
        _chunk("c2", 10, "Unrelated note about segment revenue 507,297"),
    ]

    captured: dict[str, object] = {}

    class _CapturingClient:
        def complete_json(
            self, *, system_prompt: str, user_payload: dict[str, object],
        ) -> dict[str, object]:
            captured.update(user_payload)
            return {"field_id": "repurchase_of_stock", "found": True, "value": "0"}

    result = extract_for_chunks(
        chunks=chunks,
        catalog=catalog,
        taxonomy=taxonomy,
        client=_CapturingClient(),
        company_id="TEST",
        pdf_path=Path("test.pdf"),
        out_dir=tmp_path,
    )

    # Fallback fired: the LLM was invoked with zero_inference on the section,
    # and the field resolved to a real 0 rather than not_found.
    assert "zero_inference" in captured
    assert "repurchase_of_stock" in result.fields_present
    assert result.items["repurchase_of_stock"].value == "0"


def test_extract_for_chunks_absence_zero_stays_not_found_without_section(
    tmp_path: Path,
) -> None:
    """If the statement section itself is absent from the chunks, the fallback
    finds nothing and the field stays not_found — the LLM is never invoked
    (no section means no basis to infer a zero)."""
    catalog = _catalog([
        _entry(
            "repurchase_of_stock",
            pdf_aliases=("repurchase of capital stock",),
            statement_type="cash_flow",
            absence_means_zero=True,
        ),
    ])
    taxonomy = _taxonomy([
        _tax_entry("repurchase_of_stock", statement_type="cash_flow"),
    ])
    # No cash-flow section anchor and no alias anywhere.
    chunks = [_chunk("c1", 10, "Notes to inventory valuation 1,234")]

    class _NeverClient:
        def complete_json(
            self, *, system_prompt: str, user_payload: dict[str, object],
        ) -> dict[str, object]:
            raise AssertionError("LLM must not be called without a section")

    result = extract_for_chunks(
        chunks=chunks,
        catalog=catalog,
        taxonomy=taxonomy,
        client=_NeverClient(),
        company_id="TEST",
        pdf_path=Path("test.pdf"),
        out_dir=tmp_path,
    )

    assert "repurchase_of_stock" in result.fields_not_found


def test_select_statement_section_chunks_matches_anchors() -> None:
    """The section fallback selects chunks by bilingual statement anchors and
    by explicit chunk statement_type metadata when present."""
    target = LlmExtractionTarget(
        field_id="repurchase_of_stock",
        field_description="d",
        statement_type="cash_flow",
        value_type="money",
        aliases=("repurchase of capital stock",),
        chunk_strategy="alias_top_k",
        absence_means_zero=True,
    )
    chunks = [
        _chunk("en", 1, "Consolidated statement of cash flows ... financing activities"),
        _chunk("zh", 2, "综合现金流量表 筹资活动产生的现金流量"),
        _chunk("meta", 3, "tabular numbers only", statement_type="cash_flow"),
        _chunk("other", 4, "Consolidated balance sheet: total assets"),
    ]

    selected_ids = {
        c["chunk_id"]
        for c in select_statement_section_chunks(chunks, target)
    }

    assert selected_ids == {"en", "zh", "meta"}


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


# ---------------------------------------------------------------------------
# Task 2: select_chunks
# ---------------------------------------------------------------------------

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


def test_select_chunks_alias_top_k_matches_across_pdf_layout_whitespace() -> None:
    """A multi-word alias should match across PDF-layout newlines and runs of
    whitespace inside chunk text.

    Real PDFs (via pdftotext -layout) wrap lines mid-phrase, so a chunk may
    contain `"aging analysis of trade and notes\\nreceivables ..."` while the
    catalog stores the canonical single-spaced phrase. Substring count without
    whitespace normalization scores 0 and the chunk is dropped from retrieval,
    even though the disclosure is actually present.
    """
    target = LlmExtractionTarget(
        field_id="receivables_aging",
        field_description="d",
        statement_type="notes",
        value_type="text",
        aliases=("aging analysis of trade and notes receivables",),
        chunk_strategy="alias_top_k",
    )
    chunks = [
        _chunk(
            "wrapped",
            336,
            "The Group ... Aging analysis of trade and notes\n"
            "receivables based on invoice date is as follows: ...",
        ),
        _chunk("nope", 99, "unrelated content"),
    ]

    selected = select_chunks(chunks, target, top_k_standard=10)

    assert [c["chunk_id"] for c in selected] == ["wrapped"]


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


# ---------------------------------------------------------------------------
# Task 3: extract_for_chunks orchestrator
# ---------------------------------------------------------------------------

class _CannedJsonClient:
    """Returns canned response per field_id from request payload."""

    def __init__(self, responses: dict[str, dict[str, object]]) -> None:
        self._responses = responses

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        field_obj = user_payload.get("field", {})
        if isinstance(field_obj, dict):
            fid = str(field_obj.get("field_id"))
        else:
            fid = ""
        return self._responses.get(fid, {"field_id": fid, "found": False})


def test_extract_for_chunks_iterates_targets_and_collects_results(
    tmp_path: Path,
) -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue", "营业收入", "total revenue")),
        _entry("rd_exp", pdf_aliases=("research and development",)),
    ])
    taxonomy = _taxonomy([
        _tax_entry("revenue", description="operating revenue"),
        _tax_entry("rd_exp", description="research and development expenses"),
    ])
    chunks = [
        _chunk("c1", 4, "revenue 168838 营业收入"),
        _chunk("c2", 9, "research and development 615434"),
    ]

    client = _CannedJsonClient({
        "revenue": {
            "field_id": "revenue", "found": True, "value": "168838",
            "currency": "CNY", "unit": "thousand", "page": 4,
            "statement_line": "revenue 168838",
            "confidence": 0.95, "reasoning": "ok",
        },
        "rd_exp": {
            "field_id": "rd_exp", "found": True, "value": "615434",
            "currency": "RMB", "unit": "thousand", "page": 9,
            "statement_line": "research and development 615434",
            "confidence": 0.9, "reasoning": "ok",
        },
    })

    result = extract_for_chunks(
        chunks=chunks,
        catalog=catalog,
        taxonomy=taxonomy,
        client=client,
        company_id="TEST",
        pdf_path=Path("test.pdf"),
        out_dir=tmp_path,
    )

    assert isinstance(result, LlmExtractionRunResult)
    assert result.company_id == "TEST"
    assert result.chunk_count == 2
    assert set(result.fields_attempted) == {"revenue", "rd_exp"}
    assert set(result.fields_present) == {"revenue", "rd_exp"}
    assert result.fields_not_found == ()
    assert result.fields_failed == ()


def test_extract_for_chunks_marks_field_not_found_when_no_chunks_selected(
    tmp_path: Path,
) -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue", "营业收入", "total revenue"))
    ])
    taxonomy = _taxonomy([_tax_entry("revenue")])
    chunks = [_chunk("c1", 4, "no relevant content")]

    client = _CannedJsonClient({})

    result = extract_for_chunks(
        chunks=chunks,
        catalog=catalog,
        taxonomy=taxonomy,
        client=client,
        company_id="TEST",
        pdf_path=Path("test.pdf"),
        out_dir=tmp_path,
    )

    # No chunks matched the aliases, so revenue is "no_chunks" → not_found
    assert "revenue" in result.fields_not_found
    assert "revenue" not in result.fields_present


# ---------------------------------------------------------------------------
# Task 4: write_llm_evidence_supplement
# ---------------------------------------------------------------------------

def test_write_llm_evidence_supplement_produces_well_formed_artifact(
    tmp_path: Path,
) -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue", "营业收入", "total revenue"))
    ])
    taxonomy = _taxonomy([_tax_entry("revenue", description="operating revenue")])
    chunks = [_chunk("c1", 4, "revenue 168838")]
    client = _CannedJsonClient({
        "revenue": {
            "field_id": "revenue", "found": True, "value": "168838",
            "currency": "CNY", "unit": "thousand", "page": 4,
            "statement_line": "revenue 168838", "confidence": 0.95,
            "reasoning": "ok",
        },
    })

    result = extract_for_chunks(
        chunks=chunks, catalog=catalog, taxonomy=taxonomy,
        client=client, company_id="TEST",
        pdf_path=Path("test.pdf"), out_dir=tmp_path,
    )
    written_path = write_llm_evidence_supplement(result)

    assert written_path == tmp_path / "llm_evidence_supplement.json"
    assert written_path.exists()
    payload = json.loads(written_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "llm-evidence-supplement-v1"
    assert payload["company_id"] == "TEST"
    assert payload["pdf_path"] == "test.pdf"
    assert "extracted_at" in payload  # ISO timestamp string
    item = payload["items"]["revenue"]
    assert item["status"] == "present"
    assert item["value"] == "168838"
    assert item["currency"] == "CNY"
    assert item["page"] == 4


def test_write_llm_evidence_supplement_persists_llm_metadata(
    tmp_path: Path,
) -> None:
    result = LlmExtractionRunResult(
        pdf_path=Path("test.pdf"),
        company_id="TEST",
        chunk_count=0,
        fields_attempted=(),
        fields_present=(),
        fields_not_found=(),
        fields_failed=(),
        artifact_path=tmp_path / "llm_evidence_supplement.json",
        llm_provider="codex",
        llm_model="gpt-5.5",
    )

    written_path = write_llm_evidence_supplement(result)

    payload = json.loads(written_path.read_text(encoding="utf-8"))
    assert payload["llm_provider"] == "codex"
    assert payload["llm_model"] == "gpt-5.5"


# ---------------------------------------------------------------------------
# Task 5: load_chunks_jsonl helper
# ---------------------------------------------------------------------------

def test_load_chunks_jsonl_parses_one_chunk_per_line(tmp_path: Path) -> None:
    chunks_file = tmp_path / "chunks.jsonl"
    chunks_file.write_text(
        '{"chunk_id": "c1", "page": 1, "text": "a"}\n'
        '\n'
        '{"chunk_id": "c2", "page": 2, "text": "b"}\n',
        encoding="utf-8",
    )

    chunks = load_chunks_jsonl(chunks_file)

    assert len(chunks) == 2
    assert chunks[0]["chunk_id"] == "c1"
    assert chunks[1]["text"] == "b"


# ---------------------------------------------------------------------------
# Task 6: Integration test against 00001 fixture
# ---------------------------------------------------------------------------

def test_extract_for_chunks_against_00001_fixture_with_canned_response(
    tmp_path: Path,
) -> None:
    catalog = load_source_mapping_catalog(
        _REPO_ROOT / "field_catalog" / "turtle_v015_source_mapping_minimal.json",
        priorities=("P0", "P1"),
    )
    taxonomy = load_field_taxonomy(
        _REPO_ROOT / "field_catalog" / "turtle_v015_field_taxonomy.json"
    )
    chunks_path = (
        _REPO_ROOT / "tests" / "fixtures" / "pdf_chunks" / "00001_2025_chunks.jsonl"
    )
    assert chunks_path.exists(), "00001 chunks fixture must exist"
    chunks = load_chunks_jsonl(chunks_path)

    canned = {
        "revenue": {
            "field_id": "revenue", "found": True, "value": "280036",
            "currency": "HKD", "unit": "million", "period": "2024-12-31",
            "page": 134, "statement_line": "Revenue 280,036",
            "confidence": 0.95, "reasoning": "ok",
        },
    }
    client = _CannedJsonClient(canned)

    result = extract_for_chunks(
        chunks=chunks, catalog=catalog, taxonomy=taxonomy,
        client=client, company_id="00001",
        pdf_path=Path("downloads/hk_stocks/00001/annual/2025_annual_en.pdf"),
        out_dir=tmp_path,
        fields=("revenue",),
    )

    assert "revenue" in result.fields_present, (
        f"revenue should be present; got attempted={result.fields_attempted} "
        f"present={result.fields_present} not_found={result.fields_not_found} "
        f"failed={result.fields_failed}"
    )
    written = write_llm_evidence_supplement(result)
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["items"]["revenue"]["value"] == "280036"


# ---------------------------------------------------------------------------
# Phase I-A.2 follow-up #4: confidence threshold gating
# ---------------------------------------------------------------------------

def test_extract_for_chunks_demotes_low_confidence_present_to_extraction_failed(
    tmp_path: Path,
) -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue", "营业收入", "operating revenue"))
    ])
    taxonomy = _taxonomy([_tax_entry("revenue", description="operating revenue")])
    chunks = [_chunk("c1", 4, "revenue 100")]
    client = _CannedJsonClient({
        "revenue": {
            "field_id": "revenue", "found": True, "value": "100",
            "currency": "HKD", "unit": "million", "page": 4,
            "statement_line": "revenue 100",
            "confidence": 0.5,  # below threshold
            "reasoning": "uncertain",
        },
    })

    result = extract_for_chunks(
        chunks=chunks, catalog=catalog, taxonomy=taxonomy,
        client=client, company_id="TEST",
        pdf_path=Path("test.pdf"), out_dir=tmp_path,
        confidence_threshold=0.8,
    )

    assert "revenue" in result.fields_failed
    assert "revenue" not in result.fields_present
    item = result.items["revenue"]
    assert item.status == "extraction_failed"
    assert any("low_confidence" in err for err in item.errors)
    # Original LLM response data preserved for audit
    assert item.value == "100"
    assert item.confidence == 0.5


def test_extract_for_chunks_keeps_high_confidence_present(tmp_path: Path) -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue", "营业收入", "operating revenue"))
    ])
    taxonomy = _taxonomy([_tax_entry("revenue")])
    chunks = [_chunk("c1", 4, "revenue 100")]
    client = _CannedJsonClient({
        "revenue": {
            "field_id": "revenue", "found": True, "value": "100",
            "currency": "HKD", "unit": "million", "page": 4,
            "statement_line": "revenue 100",
            "confidence": 0.95,
            "reasoning": "ok",
        },
    })

    result = extract_for_chunks(
        chunks=chunks, catalog=catalog, taxonomy=taxonomy,
        client=client, company_id="TEST",
        pdf_path=Path("test.pdf"), out_dir=tmp_path,
        confidence_threshold=0.8,
    )

    assert "revenue" in result.fields_present
    assert result.items["revenue"].status == "present"


def test_extract_for_chunks_no_threshold_means_no_gating(tmp_path: Path) -> None:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue", "营业收入", "operating revenue"))
    ])
    taxonomy = _taxonomy([_tax_entry("revenue")])
    chunks = [_chunk("c1", 4, "revenue 100")]
    client = _CannedJsonClient({
        "revenue": {
            "field_id": "revenue", "found": True, "value": "100",
            "currency": "HKD", "unit": "million", "page": 4,
            "statement_line": "revenue 100",
            "confidence": 0.1,  # very low
            "reasoning": "uncertain",
        },
    })

    # No threshold provided
    result = extract_for_chunks(
        chunks=chunks, catalog=catalog, taxonomy=taxonomy,
        client=client, company_id="TEST",
        pdf_path=Path("test.pdf"), out_dir=tmp_path,
    )

    # Should still be present despite low confidence
    assert "revenue" in result.fields_present


# ---------------------------------------------------------------------------
# Phase I-A.2 review fix: end-to-end transport unwrap coverage
# ---------------------------------------------------------------------------

class _OpenAiWrappedJsonClient:
    """Returns OpenAI-format wrapped responses to exercise unwrap_llm_content."""

    def __init__(self, inner_payloads: dict[str, dict[str, object]]) -> None:
        self._inner = inner_payloads

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        del system_prompt
        field_obj = user_payload.get("field", {})
        fid = (
            str(field_obj.get("field_id"))
            if isinstance(field_obj, dict) else ""
        )
        inner = self._inner.get(fid, {"field_id": fid, "found": False})
        # Wrap as OpenAI chat.completion response
        return {
            "id": "test-id",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(inner),
                },
                "finish_reason": "stop",
            }],
            "usage": {"total_tokens": 100},
        }


def test_extract_for_chunks_unwraps_openai_wrapped_response(tmp_path: Path) -> None:
    """Verify the runner handles wrapped LLM responses end-to-end (not just
    pre-unwrapped FakeJsonClient dicts).
    """
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue", "营业收入", "operating revenue"))
    ])
    taxonomy = _taxonomy([_tax_entry("revenue")])
    chunks = [_chunk("c1", 4, "revenue 100")]
    client = _OpenAiWrappedJsonClient({
        "revenue": {
            "field_id": "revenue", "found": True, "value": "100",
            "currency": "HKD", "unit": "million", "page": 4,
            "statement_line": "revenue 100", "confidence": 0.95,
        },
    })

    result = extract_for_chunks(
        chunks=chunks, catalog=catalog, taxonomy=taxonomy,
        client=client, company_id="TEST",
        pdf_path=Path("test.pdf"), out_dir=tmp_path,
    )

    assert "revenue" in result.fields_present
    item = result.items["revenue"]
    assert item.value == "100"
    assert item.currency == "HKD"


def test_statement_section_pages_maps_anchor_pages() -> None:
    from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
        statement_section_pages,
    )
    chunks = [
        _chunk("a", 141, "Consolidated statement of cash flows ..."),
        _chunk("b", 134, "Consolidated income statement. Revenue"),
        _chunk("c", 10, "no anchors here"),
    ]
    pages = statement_section_pages(chunks)
    assert 141 in pages["cash_flow"]
    assert 134 in pages["income_statement"]
    assert pages["balance_sheet"] == ()


def test_derive_targets_stamps_alias_normalization() -> None:
    catalog = _catalog([_entry("revenue", pdf_aliases=("a", "b", "c"))])
    taxonomy = _taxonomy([_tax_entry("revenue")])

    off = derive_targets(catalog, taxonomy, priorities=("P0",))[0]
    assert off.alias_normalization is False

    from dataclasses import replace
    on_catalog = replace(catalog, alias_normalization=True)
    on = derive_targets(on_catalog, taxonomy, priorities=("P0",))[0]
    assert on.alias_normalization is True
