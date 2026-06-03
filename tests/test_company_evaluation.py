"""Tests for company_evaluation module: bucket cascade + orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _make_export_item(
    field_id: str = "revenue",
    *,
    status: str = "present",
    selected_source: str | None = "akshare",
    conflict_classifications: tuple[str, ...] = (),
    review_notes: tuple[str, ...] = (),
    value_decimal: str = "100",
) -> Any:
    """Construct minimal SourceFirstExportItem for tests.

    Note: SourceFirstExportItem.value is `Decimal | None`, not `str`. Tests use
    Decimal(value_decimal) for present items.
    """
    from decimal import Decimal
    from financial_report_llm_extractor.structured_sources.export import (
        SourceFirstExportItem,
    )
    return SourceFirstExportItem(
        field_id=field_id,
        status=status,  # type: ignore[arg-type]
        selected_source=selected_source,
        value=Decimal(value_decimal) if status == "present" else None,
        currency="CNY",
        unit="raw",
        conflict_classifications=conflict_classifications,
        review_notes=review_notes,
    )


def _make_warning_item(category: str, *, field_id: str = "x") -> Any:
    from financial_report_llm_extractor.structured_sources.warning_classification import (
        WarningClassificationItem,
    )
    return WarningClassificationItem(
        field_id=field_id,
        category=category,  # type: ignore[arg-type]
        status="missing",
        reasons=(),
        review_notes=(),
        warnings=(),
        selected_source=None,
        candidate_sources=(),
        verification_required=False,
    )


def _make_mapping_entry(source_mode: str = "direct") -> Any:
    from financial_report_llm_extractor.structured_sources.catalog import (
        SourceMappingEntry,
    )
    return SourceMappingEntry(
        field_id="revenue",
        priority="P0",
        value_type="money",
        statement_type="income_statement",
        domain="income_statement",
        source_mode=source_mode,
        primary_route="akshare_direct",
        verification_status="expected",
        currency_requirement="required",
        unit_requirement="required",
        fallback_policy="pdf_allowed",
        source_aliases={},
        pdf_aliases=(),
    )


def test_classify_clean_present() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, reason = classify_field(
        export_item=_make_export_item(),
        warning_item=None,
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "clean_present"
    assert reason is None


def test_classify_unresolved_conflict() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, reason = classify_field(
        export_item=_make_export_item(conflict_classifications=("provider_value_mismatch",)),
        warning_item=None,
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "unresolved_conflict"
    assert "provider_value_mismatch" in (reason or "")


def test_classify_llm_supplement_present() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, _ = classify_field(
        export_item=_make_export_item(selected_source="llm"),
        warning_item=None,
        mapping_entry=_make_mapping_entry(source_mode="pdf_only"),
        pdf_provided=True,
    )

    assert bucket == "llm_supplement_present"


def test_classify_terminal_unverified_for_yahoo_definition_unverified() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, reason = classify_field(
        export_item=_make_export_item(status="missing", selected_source=None),
        warning_item=_make_warning_item("yahoo_definition_unverified"),
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "terminal_unverified"
    assert reason == "yahoo_definition_unverified"


def test_classify_not_in_scope_pdf_only_without_pdf() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, _ = classify_field(
        export_item=_make_export_item(status="missing", selected_source=None),
        warning_item=None,
        mapping_entry=_make_mapping_entry(source_mode="pdf_only"),
        pdf_provided=False,
    )

    assert bucket == "not_in_scope"


def test_classify_source_unavailable_default() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, reason = classify_field(
        export_item=_make_export_item(status="missing", selected_source=None),
        warning_item=_make_warning_item("source_unavailable"),
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "source_unavailable"
    assert reason == "source_unavailable"


def test_classify_cn_gross_profit_clean_not_terminal() -> None:
    """Review §"全局列表会错杀 CN clean": gross_profit clean via akshare_direct
    must land in clean_present, not terminal_unverified — even though it
    appears in the roadmap "Locked Terminal States" cohort that the original
    spec hardcoded."""
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, _ = classify_field(
        export_item=_make_export_item(field_id="gross_profit", selected_source="akshare"),
        warning_item=None,  # 关键：CN clean 时无 warning
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "clean_present"


def test_classify_clean_present_with_yahoo_pdf_verified_warning() -> None:
    """A field with status='present' AND a benign warning (yahoo_pdf_verified
    or source_policy_resolvable) must land in clean_present, NOT source_unavailable.

    Regression for review §"clean-with-warning" cascade gap.
    """
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    bucket, reason = classify_field(
        export_item=_make_export_item(selected_source="yahoo"),
        warning_item=_make_warning_item("yahoo_pdf_verified"),
        mapping_entry=_make_mapping_entry(),
        pdf_provided=False,
    )

    assert bucket == "clean_present"
    assert reason is None


def _build_minimal_catalog() -> Any:
    """3-field SourceMappingCatalog: P0=revenue, P1=gross_profit, P3=dividend_plan."""
    from financial_report_llm_extractor.structured_sources.catalog import (
        SourceMappingCatalog,
    )
    return SourceMappingCatalog(
        catalog_id="test-catalog",
        version="v0",
        entries={
            "revenue": _make_mapping_entry(source_mode="direct"),  # priority defaults P0
            "gross_profit": _replace(_make_mapping_entry(source_mode="direct"),
                                     field_id="gross_profit", priority="P1"),
            "dividend_plan": _replace(_make_mapping_entry(source_mode="pdf_only"),
                                      field_id="dividend_plan", priority="P3"),
        },
    )


def _build_minimal_taxonomy() -> Any:
    """Minimal FieldTaxonomyCatalog stub."""
    from financial_report_llm_extractor.field_metadata import FieldTaxonomyCatalog
    return FieldTaxonomyCatalog(
        catalog_id="test-taxonomy",
        version="v0",
        source_priority_catalog="test-priorities",
        fields={},
    )


def _replace(entry: Any, **kwargs: Any) -> Any:
    """Frozen-dataclass shallow replace helper for test fixtures."""
    import dataclasses
    return dataclasses.replace(entry, **kwargs)


def test_build_company_evaluation_counts_buckets_and_priorities() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        build_company_evaluation,
    )
    from financial_report_llm_extractor.structured_sources.export import (
        SourceFirstExportResult,
    )
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
    )
    from financial_report_llm_extractor.structured_sources.warning_classification import (
        WarningClassificationResult,
    )

    catalog = _build_minimal_catalog()

    # Note: SourceFirstExportResult requires profile + catalog_id + catalog_version
    # + items: dict (NOT tuple).
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test-catalog",
        catalog_version="v0",
        items={
            "revenue": _make_export_item(field_id="revenue", status="present", selected_source="akshare"),
            "gross_profit": _make_export_item(field_id="gross_profit", status="missing", selected_source=None),
            "dividend_plan": _make_export_item(field_id="dividend_plan", status="missing", selected_source=None),
        },
    )
    warning = WarningClassificationResult(items={
        "gross_profit": _make_warning_item("yahoo_definition_unverified", field_id="gross_profit"),
    })

    evaluation = build_company_evaluation(
        company="01113",
        period=PeriodSpec.from_year(2024),
        market="HK",
        export=export,
        warning_classification=warning,
        catalog=catalog,
        pdf_provided=False,
    )

    assert evaluation.by_bucket["clean_present"] == 1
    assert evaluation.by_bucket["terminal_unverified"] == 1
    assert evaluation.by_bucket["not_in_scope"] == 1  # dividend_plan pdf_only

    assert evaluation.by_priority["P0"]["clean_present"] == 1
    assert evaluation.by_priority["P1"]["terminal_unverified"] == 1
    assert evaluation.by_priority["P3"]["not_in_scope"] == 1


def _build_sample_evaluation() -> Any:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        build_company_evaluation,
    )
    from financial_report_llm_extractor.structured_sources.export import (
        SourceFirstExportResult,
    )
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
    )
    from financial_report_llm_extractor.structured_sources.warning_classification import (
        WarningClassificationResult,
    )

    catalog = _build_minimal_catalog()
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test-catalog",
        catalog_version="v0",
        items={
            "revenue": _make_export_item(field_id="revenue", status="present", selected_source="akshare"),
            "gross_profit": _make_export_item(field_id="gross_profit", status="missing", selected_source=None),
            "dividend_plan": _make_export_item(field_id="dividend_plan", status="missing", selected_source=None),
        },
    )
    warning = WarningClassificationResult(items={
        "gross_profit": _make_warning_item("yahoo_definition_unverified", field_id="gross_profit"),
    })

    return build_company_evaluation(
        company="01113",
        period=PeriodSpec.from_year(2024),
        market="HK",
        export=export,
        warning_classification=warning,
        catalog=catalog,
        pdf_provided=False,
    )


def test_render_evaluation_markdown_lists_priority_bucket_grid() -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        render_evaluation_markdown,
    )

    evaluation = _build_sample_evaluation()
    md = render_evaluation_markdown(evaluation)

    assert "01113" in md  # company
    assert "2024-12-31" in md  # period
    assert "clean_present" in md
    assert "P0" in md and "P3" in md
    # 不出现 "% clean" 字面 —— 与 drift §177 一致
    assert "% clean" not in md.lower()
    assert "/ total" not in md.lower()


def test_render_markdown_shows_candidate_values_for_conflict_rows() -> None:
    """Phase EC Tier 1: unresolved_conflict rows show 'src1:val / src2:val'
    inline so reviewers can triage without opening source_policy_report.json."""
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        CompanyEvaluation, CompanyFieldEvaluation, render_evaluation_markdown,
    )
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
    )

    evaluation = CompanyEvaluation(
        company="600519",
        period=PeriodSpec.from_year(2024),
        market="CN",
        generated_at="2026-05-09T00:00:00+00:00",
        fields=(
            CompanyFieldEvaluation(
                field_id="revenue",
                bucket="unresolved_conflict",
                selected_source=None,
                value=None,
                currency=None,
                unit=None,
                reason="normalized_value_conflict",
                candidate_values=(("akshare", "170.90B"), ("yahoo", "174.14B")),
            ),
        ),
        by_bucket={
            "clean_present": 0, "unresolved_conflict": 1, "llm_supplement_present": 0,
            "terminal_unverified": 0, "not_in_scope": 0, "source_unavailable": 0,
        },
        by_priority={"P0": {
            "clean_present": 0, "unresolved_conflict": 1, "llm_supplement_present": 0,
            "terminal_unverified": 0, "not_in_scope": 0, "source_unavailable": 0,
        }},
    )

    md = render_evaluation_markdown(evaluation)

    # Candidate values appear in the Value column for conflict rows.
    assert "akshare:170.90B" in md
    assert "yahoo:174.14B" in md
    assert "akshare:170.90B / yahoo:174.14B" in md


def test_render_markdown_shows_candidate_values_for_clean_present_with_multi_source() -> None:
    """Phase H2.2 Sub-C: clean_present rows with >= 2 candidates show all
    provider values inline (audit transparency). Single-candidate rows render
    only the selected value."""
    from decimal import Decimal
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        CompanyEvaluation, CompanyFieldEvaluation, render_evaluation_markdown,
    )
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
    )

    evaluation = CompanyEvaluation(
        company="600519",
        period=PeriodSpec.from_year(2024),
        market="CN",
        generated_at="2026-05-09T00:00:00+00:00",
        fields=(
            CompanyFieldEvaluation(
                field_id="revenue",
                bucket="clean_present",
                selected_source="akshare",
                value=Decimal("170899152276.34"),
                currency="CNY",
                unit="yuan",
                reason=None,
                candidate_values=(
                    ("akshare", "170.90B"),
                    ("yahoo", "174.14B"),
                ),
            ),
        ),
        by_bucket={
            "clean_present": 1, "unresolved_conflict": 0, "llm_supplement_present": 0,
            "terminal_unverified": 0, "not_in_scope": 0, "source_unavailable": 0,
        },
        by_priority={"P0": {
            "clean_present": 1, "unresolved_conflict": 0, "llm_supplement_present": 0,
            "terminal_unverified": 0, "not_in_scope": 0, "source_unavailable": 0,
        }},
    )

    md = render_evaluation_markdown(evaluation)

    assert "akshare:170.90B" in md
    assert "yahoo:174.14B" in md
    # Selected source still appears in Source column.
    assert "akshare" in md


def test_run_llm_supplement_step_persists_metadata_from_config(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    import json

    from financial_report_llm_extractor.structured_sources import (
        company_evaluation,
        llm_extraction_runner,
    )
    from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
        LlmExtractionRunResult,
    )

    chunks_path = tmp_path / "ingest" / "chunks.jsonl"
    chunks_path.parent.mkdir()
    chunks_path.write_text(
        '{"chunk_id": "c1", "page": 1, "text": "revenue 100"}\n',
        encoding="utf-8",
    )
    llm_config_path = tmp_path / "llm.json"
    llm_config_path.write_text(
        json.dumps(
            {
                "provider": "codex",
                "model": "gpt-5.5",
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, str | None] = {}

    def fake_extract_for_chunks(**kwargs: Any) -> LlmExtractionRunResult:
        return LlmExtractionRunResult(
            pdf_path=kwargs["pdf_path"],
            company_id=kwargs["company_id"],
            chunk_count=len(kwargs["chunks"]),
            fields_attempted=(),
            fields_present=(),
            fields_not_found=(),
            fields_failed=(),
            artifact_path=kwargs["out_dir"] / "llm_evidence_supplement.json",
        )

    def fake_write_llm_evidence_supplement(result: LlmExtractionRunResult) -> Path:
        captured["llm_provider"] = result.llm_provider
        captured["llm_model"] = result.llm_model
        return result.artifact_path

    monkeypatch.setattr(
        llm_extraction_runner, "extract_for_chunks", fake_extract_for_chunks
    )
    monkeypatch.setattr(
        llm_extraction_runner,
        "write_llm_evidence_supplement",
        fake_write_llm_evidence_supplement,
    )

    company_evaluation._run_llm_supplement_step(
        company="TEST",
        pdf_path=Path("test.pdf"),
        llm_config_path=llm_config_path,
        catalog=_build_minimal_catalog(),
        taxonomy=_build_minimal_taxonomy(),
        priorities=("P0",),
        out_dir=tmp_path,
        json_client=object(),  # type: ignore[arg-type]
    )

    assert captured == {
        "llm_provider": "codex",
        "llm_model": "gpt-5.5",
    }


def test_orchestrator_with_fake_stack_writes_all_artifacts(
    tmp_path: Path,
) -> None:
    """End-to-end with fake provider client → fetch → evaluate. No PDF, no LLM."""
    import sys

    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        run_company_evaluation,
    )
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
        fetch_source_inventory,
    )

    # The tests/ dir is on sys.path via pytest's rootdir mechanism but not as
    # a package; load _FakeAkshareClient by direct module name since there is
    # no tests/__init__.py.
    tests_dir = str(Path(__file__).parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_source_inventory_fetch import _FakeAkshareClient  # type: ignore[import-not-found]

    catalog_path = Path("field_catalog/turtle_v015_source_mapping_minimal.json")
    taxonomy_path = Path("field_catalog/turtle_v015_field_taxonomy.json")

    # 1. Live fetch with fake client (writes inventory artifacts to tmp_path).
    fetch_source_inventory(
        company="600519",
        period=PeriodSpec.from_year(2024),
        market="CN",
        providers=("akshare",),
        akshare_client=_FakeAkshareClient(),
        yahoo_client=None,
        out_dir=tmp_path,
        catalog_path=catalog_path,
    )

    # 2. Evaluate (no PDF → skip LLM step).
    evaluation = run_company_evaluation(
        company="600519",
        period=PeriodSpec.from_year(2024),
        market="CN",
        inventory_path=tmp_path / "source_inventory.jsonl",
        inventory_summary_path=tmp_path / "source_inventory_summary.json",
        catalog_path=catalog_path,
        taxonomy_path=taxonomy_path,
        pdf_path=None,
        llm_config_path=None,
        priorities=("P0", "P1", "P2", "P3"),
        out_dir=tmp_path,
    )

    # IMPORTANT: real artifact name is `extraction_result.json` (not
    # `source_first_export.json`); see export.py:189.
    assert (tmp_path / "extraction_result.json").exists()
    assert (tmp_path / "evaluation.json").exists()
    assert (tmp_path / "evaluation.md").exists()
    assert evaluation.company == "600519"
    # Revenue should be clean_present after the fake-client fetch.
    revenue = next(f for f in evaluation.fields if f.field_id == "revenue")
    assert revenue.bucket == "clean_present"

    # R4 Task 1: evaluation.json must embed catalog_version from the taxonomy.
    import json as _json
    eval_payload = _json.loads((tmp_path / "evaluation.json").read_text(encoding="utf-8"))
    expected_version = _json.loads(taxonomy_path.read_text(encoding="utf-8"))["version"]
    assert eval_payload["catalog_version"] == expected_version
