from decimal import Decimal
import json
from pathlib import Path

from financial_report_llm_extractor.models import Currency, Evidence
from financial_report_llm_extractor.structured_sources.export import (
    build_source_first_export,
    write_source_first_export_artifacts,
)
from financial_report_llm_extractor.structured_sources.mapping import (
    MappedTurtleField,
    TurtleMappingCandidate,
    TurtleMappingResult,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceName,
)
from financial_report_llm_extractor.structured_sources.reconciliation import (
    reconcile_mapped_fields,
)
from financial_report_llm_extractor.structured_sources.source_policy import (
    SourcePolicyItem,
    SourcePolicyReport,
)


def test_source_only_export_keeps_source_evidence_separate() -> None:
    mapping = _mapping(
        "revenue",
        MappedTurtleField(
            field_id="revenue",
            status="present",
            value=Decimal("100"),
            normalized_value=Decimal("100"),
            currency="CNY",
            unit="yuan",
            period="2024-12-31",
            scope="consolidated",
            candidates=(_candidate("akshare", Decimal("100")),),
            source_evidence=(_source_evidence("akshare"),),
        ),
    )
    reconciliation = reconcile_mapped_fields(mapping)

    result = build_source_first_export(mapping, reconciliation, profile="source_only")

    item = result.items["revenue"]
    assert item.status == "present"
    assert item.source_evidence[0].source == "akshare"
    assert item.pdf_evidence == ()
    assert result.summary["status_counts"] == {"present": 1}


def test_source_export_marks_reconciliation_conflict() -> None:
    mapping = _mapping(
        "revenue",
        MappedTurtleField(
            field_id="revenue",
            status="ambiguous",
            candidates=(
                _candidate("akshare", Decimal("100")),
                _candidate("yahoo", Decimal("101")),
            ),
        ),
    )
    reconciliation = reconcile_mapped_fields(mapping)

    result = build_source_first_export(mapping, reconciliation, profile="source_only")

    item = result.items["revenue"]
    assert item.status == "conflict"
    assert item.reconciliation_status == "conflict"
    assert result.summary["conflict_fields"] == ["revenue"]
    assert result.summary["unresolved_conflict_fields"] == []


def test_source_first_export_preserves_policy_selected_conflict_metadata() -> None:
    mapping = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "revenue": MappedTurtleField(
                field_id="revenue",
                status="ambiguous",
                candidates=(
                    _candidate("akshare", Decimal("168"), canonical_unit="CNY"),
                    _candidate("yahoo", Decimal("172"), canonical_unit="CNY"),
                ),
                errors=("multiple source candidates matched catalog aliases",),
            )
        },
    )
    reconciliation = reconcile_mapped_fields(mapping)
    policy_report = SourcePolicyReport(
        catalog_id="test",
        catalog_version="1",
        company_id="600519",
        market="CN",
        items={
            "revenue": SourcePolicyItem(
                field_id="revenue",
                selection_status="selected_primary",
                selected_candidate=mapping.fields["revenue"].candidates[0],
                conflict_classifications=("semantic_mismatch",),
                verification_required=True,
                warnings=(
                    "source policy selected primary candidate despite semantic_mismatch",
                ),
                reconciliation_status="conflict",
            )
        },
    )

    result = build_source_first_export(
        mapping,
        reconciliation,
        profile="source_only",
        source_policy_report=policy_report,
    )

    item = result.items["revenue"]
    assert item.status == "present"
    assert item.selection_status == "selected_primary"
    assert item.selected_source == "akshare"
    assert item.verification_required is True
    assert item.conflict_classifications == ("semantic_mismatch",)
    assert item.warnings == (
        "source policy selected primary candidate despite semantic_mismatch",
    )
    assert item.value == Decimal("168")
    assert result.summary["selected_with_warnings_fields"] == ["revenue"]
    assert result.summary["fields_requiring_pdf_evidence"] == ["revenue"]


def test_pdf_required_policy_selected_without_pdf_keeps_selection_metadata() -> None:
    mapping = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "revenue": MappedTurtleField(
                field_id="revenue",
                status="ambiguous",
                candidates=(
                    _candidate("akshare", Decimal("168"), canonical_unit="CNY"),
                    _candidate("yahoo", Decimal("172"), canonical_unit="CNY"),
                ),
                errors=("multiple source candidates matched catalog aliases",),
            )
        },
    )
    reconciliation = reconcile_mapped_fields(mapping)
    policy_report = SourcePolicyReport(
        catalog_id="test",
        catalog_version="1",
        company_id="600519",
        market="CN",
        items={
            "revenue": SourcePolicyItem(
                field_id="revenue",
                selection_status="selected_primary",
                selected_candidate=mapping.fields["revenue"].candidates[0],
                conflict_classifications=("semantic_mismatch",),
                verification_required=True,
                warnings=(
                    "source policy selected primary candidate despite semantic_mismatch",
                ),
                reconciliation_status="conflict",
            )
        },
    )

    result = build_source_first_export(
        mapping,
        reconciliation,
        profile="pdf_required",
        source_policy_report=policy_report,
    )

    item = result.items["revenue"]
    assert item.status == "needs_pdf_evidence"
    assert item.selection_status == "selected_primary"
    assert item.selected_source == "akshare"
    assert item.verification_required is True
    assert item.conflict_classifications == ("semantic_mismatch",)
    assert item.value == Decimal("168")
    assert result.summary["fields_requiring_pdf_evidence"] == ["revenue"]


def test_source_first_export_promotes_equivalent_ambiguous_candidates_with_candidate_metadata() -> None:
    akshare_evidence = SourceEvidence(
        source="akshare",
        adapter="akshare",
        function="fixture",
        artifact_id="akshare_cash",
        raw_record_id="a",
        raw_field_name="货币资金",
    )
    yahoo_evidence = SourceEvidence(
        source="yahoo",
        adapter="yahoo",
        function="fixture",
        artifact_id="yahoo_cash",
        raw_record_id="y",
        raw_field_name="Cash And Cash Equivalents",
    )
    mapping = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "cash": MappedTurtleField(
                field_id="cash",
                status="ambiguous",
                candidates=(
                    TurtleMappingCandidate(
                        source="akshare",
                        raw_field_name="货币资金",
                        raw_field_code="MONETARYFUNDS",
                        raw_value="100",
                        value=Decimal("100"),
                        normalized_value=Decimal("100"),
                        currency="CNY",
                        unit="yuan",
                        canonical_unit="CNY",
                        period="2025-12-31",
                        scope="consolidated",
                        source_evidence=(akshare_evidence,),
                    ),
                    TurtleMappingCandidate(
                        source="yahoo",
                        raw_field_name="Cash And Cash Equivalents",
                        raw_field_code=None,
                        raw_value="100",
                        value=Decimal("100"),
                        normalized_value=Decimal("100"),
                        currency="CNY",
                        unit="raw",
                        canonical_unit="CNY",
                        period="2025-12-31",
                        scope="consolidated",
                        source_evidence=(yahoo_evidence,),
                    ),
                ),
                errors=("multiple source candidates matched catalog aliases",),
            )
        },
    )
    reconciliation = reconcile_mapped_fields(mapping)

    exported = build_source_first_export(
        mapping,
        reconciliation,
        profile="source_only",
    )

    item = exported.items["cash"]
    assert item.status == "present"
    assert item.value == Decimal("100")
    assert item.normalized_value == Decimal("100")
    assert item.currency == "CNY"
    assert item.unit == "yuan"
    assert item.canonical_unit == "CNY"
    assert item.period == "2025-12-31"
    assert item.scope == "consolidated"
    assert len(item.source_evidence) == 2
    assert item.errors == ()
    assert item.warnings == ("multiple source candidates reconciled as equivalent",)


def test_source_first_export_does_not_promote_policy_unresolved_equivalent_conflict() -> None:
    mapping = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "cash": MappedTurtleField(
                field_id="cash",
                status="ambiguous",
                candidates=(
                    _candidate("akshare", Decimal("100"), canonical_unit="CNY"),
                    _candidate("yahoo", Decimal("100"), canonical_unit="CNY"),
                ),
                errors=("multiple source candidates matched catalog aliases",),
            )
        },
    )
    reconciliation = reconcile_mapped_fields(mapping)
    policy_report = SourcePolicyReport(
        catalog_id="test",
        catalog_version="1",
        company_id="00001",
        market="HK",
        items={
            "cash": SourcePolicyItem(
                field_id="cash",
                selection_status="unresolved_conflict",
                conflict_classifications=("currency_metadata_required",),
                verification_required=True,
                warnings=("selected primary candidate lacks proven currency metadata",),
                reconciliation_status="equivalent",
            )
        },
    )

    result = build_source_first_export(
        mapping,
        reconciliation,
        profile="source_only",
        source_policy_report=policy_report,
    )

    item = result.items["cash"]
    assert reconciliation.items["cash"].status == "equivalent"
    assert item.status == "conflict"
    assert item.selection_status == "unresolved_conflict"
    assert item.verification_required is True
    assert item.conflict_classifications == ("currency_metadata_required",)
    assert item.review_notes == ("currency_metadata_required",)
    assert item.warnings == ("selected primary candidate lacks proven currency metadata",)
    assert result.summary["unresolved_conflict_fields"] == ["cash"]


def test_source_first_export_marks_reconciliation_blocked() -> None:
    mapping = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "cash": MappedTurtleField(
                field_id="cash",
                status="ambiguous",
                candidates=(
                    _candidate("akshare", Decimal("100"), canonical_unit=None),
                    _candidate("yahoo", Decimal("100"), canonical_unit="CNY"),
                ),
                errors=("multiple source candidates matched catalog aliases",),
            )
        },
    )
    reconciliation = reconcile_mapped_fields(mapping)

    result = build_source_first_export(mapping, reconciliation, profile="source_only")

    item = result.items["cash"]
    assert reconciliation.items["cash"].status == "blocked"
    assert item.status == "blocked"
    assert item.reconciliation_status == "blocked"
    assert result.summary["blocked_fields"] == ["cash"]


def test_pdf_required_export_lists_fields_needing_pdf_evidence() -> None:
    mapping = _mapping(
        "cash",
        MappedTurtleField(
            field_id="cash",
            status="present",
            value=Decimal("20"),
            normalized_value=Decimal("20"),
            currency="CNY",
            unit="yuan",
            period="2024-12-31",
            scope="consolidated",
            candidates=(_candidate("akshare", Decimal("20")),),
            source_evidence=(_source_evidence("akshare"),),
        ),
    )
    reconciliation = reconcile_mapped_fields(mapping)

    result = build_source_first_export(mapping, reconciliation, profile="pdf_required")

    assert result.items["cash"].status == "needs_pdf_evidence"
    assert result.summary["fields_requiring_pdf_evidence"] == ["cash"]


def test_pdf_required_export_accepts_separate_pdf_evidence() -> None:
    mapping = _mapping(
        "cash",
        MappedTurtleField(
            field_id="cash",
            status="present",
            value=Decimal("20"),
            normalized_value=Decimal("20"),
            currency="CNY",
            unit="yuan",
            period="2024-12-31",
            scope="consolidated",
            candidates=(_candidate("akshare", Decimal("20")),),
            source_evidence=(_source_evidence("akshare"),),
        ),
    )
    reconciliation = reconcile_mapped_fields(mapping)
    pdf_evidence = Evidence(
        page=10,
        chunk_id="chunk-10",
        block_id="p0010_b0001",
        snippet="Cash and cash equivalents 20",
    )

    result = build_source_first_export(
        mapping,
        reconciliation,
        profile="pdf_required",
        pdf_evidence_by_field={"cash": (pdf_evidence,)},
    )

    item = result.items["cash"]
    assert item.status == "present"
    assert item.pdf_evidence == (pdf_evidence,)
    assert item.source_evidence[0].raw_field_name == "Revenue"
    assert result.summary["fields_requiring_pdf_evidence"] == []


def test_write_source_first_export_artifacts_writes_review_files(
    tmp_path: Path,
) -> None:
    mapping = _mapping(
        "revenue",
        MappedTurtleField(
            field_id="revenue",
            status="present",
            value=Decimal("100"),
            normalized_value=Decimal("100"),
            currency="CNY",
            unit="yuan",
            period="2024-12-31",
            scope="consolidated",
            candidates=(_candidate("akshare", Decimal("100")),),
            source_evidence=(_source_evidence("akshare"),),
        ),
    )
    result = build_source_first_export(
        mapping,
        reconcile_mapped_fields(mapping),
        profile="source_only",
    )

    paths = write_source_first_export_artifacts(result, tmp_path)

    extraction_payload = json.loads(
        paths["extraction_result"].read_text(encoding="utf-8")
    )
    summary_payload = json.loads(paths["review_summary"].read_text(encoding="utf-8"))

    assert paths["extraction_result"].name == "extraction_result.json"
    assert paths["review_summary"].name == "review_summary.json"
    assert extraction_payload["profile"] == "source_only"
    assert extraction_payload["items"]["revenue"]["source_evidence"][0]["source"] == "akshare"
    assert summary_payload["status_counts"] == {"present": 1}


def _mapping(field_id: str, field: MappedTurtleField) -> TurtleMappingResult:
    return TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={field_id: field},
    )


def _candidate(
    source: SourceName,
    normalized_value: Decimal,
    *,
    canonical_unit: Currency | None = "CNY",
) -> TurtleMappingCandidate:
    return TurtleMappingCandidate(
        source=source,
        raw_field_name="Revenue",
        raw_field_code=None,
        raw_value=str(normalized_value),
        value=normalized_value,
        normalized_value=normalized_value,
        currency="CNY",
        unit="yuan",
        canonical_unit=canonical_unit,
        period="2024-12-31",
        scope="consolidated",
        source_evidence=(_source_evidence(source),),
    )


def _source_evidence(source: SourceName) -> SourceEvidence:
    return SourceEvidence(
        source=source,
        adapter=source,
        function="fixture",
        artifact_id=f"{source}_artifact",
        raw_record_id=f"{source}:revenue",
        raw_field_name="Revenue",
    )
