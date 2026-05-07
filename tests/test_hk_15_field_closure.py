from decimal import Decimal

from financial_report_llm_extractor.structured_sources.export import (
    ExportItemStatus,
    SourceFirstExportItem,
    SourceFirstExportResult,
)
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    FieldCandidateReportEntry,
    ProviderCandidateGroup,
    ProviderFieldCandidate,
)
from financial_report_llm_extractor.structured_sources.hk_15_field_closure import (
    HK_15_FIELD_IDS,
    build_hk_15_field_closure_report,
)
from financial_report_llm_extractor.structured_sources.hk_yahoo_trust_policy import (
    HkYahooTrustPolicy,
    HkYahooTrustRule,
)
from financial_report_llm_extractor.structured_sources.warning_classification import (
    build_warning_classification,
)


def _item(
    field_id: str,
    *,
    status: ExportItemStatus = "missing",
    selected_source: str | None = None,
    verification_required: bool = False,
    warnings: tuple[str, ...] = (),
) -> SourceFirstExportItem:
    return SourceFirstExportItem(
        field_id=field_id,
        status=status,
        selected_source=selected_source,
        verification_required=verification_required,
        warnings=warnings,
    )


def _candidate_entry() -> FieldCandidateReportEntry:
    return FieldCandidateReportEntry(
        priority="P1",
        statement_type="balance_sheet",
        source_mode="direct",
        status="has_candidates",
        providers={
            "yahoo": ProviderCandidateGroup(
                candidates=(
                    ProviderFieldCandidate(
                        raw_field_name="Deferred Tax Liabilities",
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


def _policy() -> HkYahooTrustPolicy:
    return HkYahooTrustPolicy(
        version=1,
        market="HK",
        provider="yahoo",
        rules=(
            HkYahooTrustRule(
                policy_id="hk_yahoo_raw_hkd_pdf_verified:revenue",
                field_id="revenue",
                classification="yahoo_pdf_verified",
                trusted_currency="HKD",
                trusted_unit="raw",
                trusted_unit_multiplier=Decimal("1"),
                allowed_yahoo_raw_fields=("Total Revenue",),
            ),
            HkYahooTrustRule(
                policy_id="hk_yahoo_raw_hkd_pdf_verified:net_profit",
                field_id="net_profit",
                classification="yahoo_pdf_verified",
                trusted_currency="HKD",
                trusted_unit="raw",
                trusted_unit_multiplier=Decimal("1"),
                allowed_yahoo_raw_fields=("Net Income Common Stockholders",),
            ),
        ),
    )


def test_hk_15_field_closure_report_classifies_remaining_gap_types() -> None:
    items = {field_id: _item(field_id, status="present") for field_id in HK_15_FIELD_IDS}
    items["net_profit"] = _item(
        "net_profit",
        status="present",
        selected_source="yahoo",
        verification_required=True,
    )
    items["defer_tax_liab"] = _item("defer_tax_liab")
    items["bond_payable"] = _item("bond_payable")
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="catalog",
        catalog_version="1",
        items=items,
    )
    warning = build_warning_classification(
        export,
        candidate_entries={"defer_tax_liab": _candidate_entry()},
        market="HK",
        hk_yahoo_trust_policy=_policy(),
    )

    report = build_hk_15_field_closure_report(
        export=export,
        warning_classification=warning,
        candidate_entries={"defer_tax_liab": _candidate_entry()},
        policy=_policy(),
        company_id="00001",
        market="HK",
    )

    assert report.company_id == "00001"
    assert report.total_fields == 15
    assert report.items["revenue"].category == "clean_present"
    assert report.items["net_profit"].category == "yahoo_pdf_verified"
    assert report.items["defer_tax_liab"].category == "mapping_expansion_required"
    assert report.items["defer_tax_liab"].candidate_sources == ("yahoo",)
    assert report.items["bond_payable"].category == "source_unavailable"


def test_hk_15_field_closure_does_not_apply_yahoo_policy_to_missing_field() -> None:
    items = {field_id: _item(field_id, status="present") for field_id in HK_15_FIELD_IDS}
    items["net_profit"] = _item("net_profit")
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="catalog",
        catalog_version="1",
        items=items,
    )
    warning = build_warning_classification(
        export,
        candidate_entries={},
        market="HK",
        hk_yahoo_trust_policy=_policy(),
    )

    report = build_hk_15_field_closure_report(
        export=export,
        warning_classification=warning,
        candidate_entries={},
        policy=_policy(),
        company_id="00001",
        market="HK",
    )

    assert report.items["net_profit"].category == "source_unavailable"


def test_hk_15_field_closure_does_not_apply_yahoo_policy_to_akshare_field() -> None:
    items = {field_id: _item(field_id, status="present") for field_id in HK_15_FIELD_IDS}
    items["net_profit"] = _item(
        "net_profit",
        status="present",
        selected_source="akshare",
    )
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="catalog",
        catalog_version="1",
        items=items,
    )
    warning = build_warning_classification(
        export,
        candidate_entries={},
        market="HK",
        hk_yahoo_trust_policy=_policy(),
    )

    report = build_hk_15_field_closure_report(
        export=export,
        warning_classification=warning,
        candidate_entries={},
        policy=_policy(),
        company_id="00001",
        market="HK",
    )

    assert report.items["net_profit"].category == "clean_present"
