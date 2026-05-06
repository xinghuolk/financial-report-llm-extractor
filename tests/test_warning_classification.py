import json
from pathlib import Path

from financial_report_llm_extractor.structured_sources.export import (
    SourceFirstExportItem,
    SourceFirstExportResult,
)
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    FieldCandidateReportEntry,
    ProviderCandidateGroup,
    ProviderFieldCandidate,
)
from financial_report_llm_extractor.structured_sources.warning_classification import (
    build_warning_classification,
    write_warning_classification_artifacts,
)


def _item(
    field_id: str,
    *,
    status: str = "missing",
    review_notes: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
    verification_required: bool = False,
    reconciliation_status: str | None = None,
    selected_source: str | None = None,
    conflict_classifications: tuple[str, ...] = (),
) -> SourceFirstExportItem:
    return SourceFirstExportItem(
        field_id=field_id,
        status=status,  # type: ignore[arg-type]
        review_notes=review_notes,
        warnings=warnings,
        verification_required=verification_required,
        reconciliation_status=reconciliation_status,  # type: ignore[arg-type]
        selected_source=selected_source,
        conflict_classifications=conflict_classifications,
    )


def _candidate_entry() -> FieldCandidateReportEntry:
    return FieldCandidateReportEntry(
        priority="P0",
        statement_type="balance_sheet",
        source_mode="direct",
        status="has_candidates",
        providers={
            "yahoo": ProviderCandidateGroup(
                candidates=(
                    ProviderFieldCandidate(
                        raw_field_name="Non Current Deferred Taxes Liabilities",
                        raw_field_code=None,
                        score=65,
                        strength="medium",
                        signals=("keyword_overlap", "statement_match"),
                        target_count=1,
                        period_count=1,
                        record_count=1,
                    ),
                )
            )
        },
    )


def test_warning_classification_uses_mapping_expansion_for_missing_with_candidates() -> None:
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test",
        catalog_version="1",
        items={
            "defer_tax_liab": _item("defer_tax_liab"),
            "bond_payable": _item("bond_payable"),
        },
    )

    result = build_warning_classification(
        export,
        candidate_entries={"defer_tax_liab": _candidate_entry()},
    )

    assert result.fields_by_category["mapping_expansion_required"] == [
        "defer_tax_liab"
    ]
    assert result.fields_by_category["source_unavailable"] == ["bond_payable"]


def test_warning_classification_prioritizes_pdf_verification_over_metadata_notes() -> None:
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test",
        catalog_version="1",
        items={
            "total_assets": _item(
                "total_assets",
                status="conflict",
                review_notes=(
                    "metadata_currency_suspected",
                    "statement_metadata_unproven",
                ),
                verification_required=True,
                reconciliation_status="conflict",
            )
        },
    )

    result = build_warning_classification(export, candidate_entries={})

    assert result.fields_by_category["pdf_verification_required"] == ["total_assets"]
    item = result.items["total_assets"]
    assert item.category == "pdf_verification_required"
    assert "reconciliation_conflict" in item.reasons
    assert "statement_metadata_unproven" in item.reasons


def test_warning_classification_marks_metadata_only_issue_source_policy_resolvable() -> None:
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test",
        catalog_version="1",
        items={
            "cash": _item(
                "cash",
                status="conflict",
                review_notes=("currency_as_unit", "statement_metadata_unproven"),
            )
        },
    )

    result = build_warning_classification(export, candidate_entries={})

    assert result.fields_by_category["source_policy_resolvable"] == ["cash"]


def test_warning_classification_does_not_allow_metadata_notes_to_override_verification_required() -> None:
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test",
        catalog_version="1",
        items={
            "cash": _item(
                "cash",
                status="conflict",
                review_notes=("currency_as_unit", "statement_metadata_unproven"),
                verification_required=True,
            )
        },
    )

    result = build_warning_classification(export, candidate_entries={})

    assert result.fields_by_category["pdf_verification_required"] == ["cash"]


def test_warning_classification_uses_verification_required_for_pdf_queue() -> None:
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test",
        catalog_version="1",
        items={
            "revenue": _item(
                "revenue",
                status="present",
                warnings=("single source selected; PDF verification required",),
                verification_required=True,
                selected_source="yahoo",
            )
        },
    )

    result = build_warning_classification(export, candidate_entries={})

    assert result.fields_by_category["pdf_verification_required"] == ["revenue"]


def test_warning_classification_reserves_mapping_expansion_for_missing_fields() -> None:
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test",
        catalog_version="1",
        items={
            "ambiguous_field": _item("ambiguous_field", status="ambiguous"),
            "blocked_field": _item("blocked_field", status="blocked"),
        },
    )

    result = build_warning_classification(
        export,
        candidate_entries={
            "ambiguous_field": _candidate_entry(),
            "blocked_field": _candidate_entry(),
        },
    )

    assert result.fields_by_category["mapping_expansion_required"] == []
    assert result.fields_by_category["source_policy_resolvable"] == [
        "ambiguous_field",
        "blocked_field",
    ]


def test_warning_classification_excludes_only_clean_present_items() -> None:
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test",
        catalog_version="1",
        items={
            "clean_present": _item("clean_present", status="present"),
            "present_with_warning": _item(
                "present_with_warning",
                status="present",
                warnings=("single source selected; PDF verification required",),
            ),
            "present_with_note": _item(
                "present_with_note",
                status="present",
                review_notes=("currency_as_unit",),
            ),
            "present_with_verification": _item(
                "present_with_verification",
                status="present",
                verification_required=True,
            ),
            "present_with_conflict_classification": _item(
                "present_with_conflict_classification",
                status="present",
                conflict_classifications=("normalized_value_conflict",),
            ),
        },
    )

    result = build_warning_classification(export, candidate_entries={})

    assert "clean_present" not in result.items
    assert set(result.items) == {
        "present_with_warning",
        "present_with_note",
        "present_with_verification",
        "present_with_conflict_classification",
    }


def test_warning_classification_uses_conflict_classifications_as_reasons() -> None:
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test",
        catalog_version="1",
        items={
            "total_assets": _item(
                "total_assets",
                status="present",
                conflict_classifications=("normalized_value_conflict",),
            )
        },
    )

    result = build_warning_classification(export, candidate_entries={})

    item = result.items["total_assets"]
    assert item.category == "pdf_verification_required"
    assert "normalized_value_conflict" in item.reasons


def test_write_warning_classification_artifacts_writes_json_and_markdown(
    tmp_path: Path,
) -> None:
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="test",
        catalog_version="1",
        items={"bond_payable": _item("bond_payable")},
    )
    result = build_warning_classification(export, candidate_entries={})

    paths = write_warning_classification_artifacts(result, tmp_path)

    assert set(paths) == {"json", "markdown"}
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["fields_by_category"]["source_unavailable"] == ["bond_payable"]
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "# Warning Classification" in markdown
    assert "- source_unavailable: 1 (bond_payable)" in markdown
