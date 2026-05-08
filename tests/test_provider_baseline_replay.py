import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from financial_report_llm_extractor.structured_sources.artifacts import (  # type: ignore[import-untyped]
    write_source_inventory,
)
from financial_report_llm_extractor.structured_sources.models import (  # type: ignore[import-untyped]
    SourceEvidence,
    SourceInventoryRecord,
)
from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (  # type: ignore[import-untyped]
    ProviderBaselineGroup,
    ProviderBaselineReplayResult,
    _company_market,
    _export_coverage,
    company_source_groups,
    select_latest_annual_records,
    write_provider_baseline_period_replay,
)
from financial_report_llm_extractor.structured_sources.export import (  # type: ignore[import-untyped]
    SourceFirstExportItem,
    SourceFirstExportResult,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_MAPPING_CATALOG_PATH = (
    REPO_ROOT / "field_catalog" / "turtle_v015_source_mapping_minimal.json"
)
PROVIDER_BASELINE_FIXTURE_DIR = (
    REPO_ROOT / "tests" / "fixtures" / "provider_captures" / "provider_field_baseline"
)
PROVIDER_BASELINE_INVENTORY_PATH = (
    PROVIDER_BASELINE_FIXTURE_DIR / "source_inventory.jsonl.gz"
)
PROVIDER_BASELINE_INVENTORY_SUMMARY_PATH = (
    PROVIDER_BASELINE_FIXTURE_DIR / "provider_field_inventory_summary.json"
)
PROVIDER_BASELINE_REPLAY_SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "run-provider-baseline-period-replay.sh"
)
HK_YAHOO_TRUST_POLICY_PATH = REPO_ROOT / "field_catalog" / "hk_yahoo_trust_policy.json"

HK_COMPANY_IDS = ("00001", "01113")
EXPECTED_HK_METADATA_BLOCKER_FIELDS = frozenset(
    {
        "total_assets",
        "total_cur_assets",
        "total_cur_liab",
        "total_liabilities",
    }
)
EXPECTED_HK_YAHOO_VERIFIED_FIELDS = frozenset(
    {
        "defer_tax_liab",
        "net_profit",
        "revenue",
        "total_assets",
        "total_cur_assets",
        "total_cur_liab",
        "total_liabilities",
    }
)
EXPECTED_HK_YAHOO_DEFINITION_UNVERIFIED_FIELDS = frozenset({"gross_profit"})
EXPECTED_HK_PDF_VERIFICATION_FIELDS = frozenset(
    {
        "gross_profit",
        "net_profit",
        "revenue",
        "total_assets",
        "total_cur_assets",
        "total_cur_liab",
        "total_liabilities",
    }
)
EXPECTED_HK_MAPPING_EXPANSION_FIELDS_BY_COMPANY: dict[str, list[str]] = {
    "00001": ["non_oper_exp", "non_oper_income", "other_cur_assets"],
    "01113": ["non_oper_exp", "non_oper_income"],
}
EXPECTED_HK_SOURCE_UNAVAILABLE_FIELDS = frozenset(
    {
        "bond_payable",
        "cip",
        "fv_value_chg_gain",
        "invest_income",
        "rd_exp",
    }
)
# 01113 also has selling_general_administrative as source_unavailable; 00001 does not
EXPECTED_01113_EXTRA_SOURCE_UNAVAILABLE = frozenset({"selling_general_administrative"})


CheckedInReplay = tuple[ProviderBaselineReplayResult, dict[str, Any]]


def test_export_coverage_clean_present_excludes_review_notes_and_conflicts() -> None:
    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="catalog",
        catalog_version="1",
        items={
            "clean": SourceFirstExportItem(field_id="clean", status="present"),
            "review_note": SourceFirstExportItem(
                field_id="review_note",
                status="present",
                review_notes=("statement_metadata_unproven",),
            ),
            "conflict": SourceFirstExportItem(
                field_id="conflict",
                status="present",
                conflict_classifications=("statement_metadata_unproven",),
            ),
        },
    )

    coverage = _export_coverage(export)

    assert coverage["selected_fields"] == ["clean", "conflict", "review_note"]
    assert coverage["clean_present_fields"] == ["clean"]
    assert coverage["clean_present_count"] == 1


@pytest.fixture(scope="module")
def checked_in_provider_baseline_replay(
    tmp_path_factory: pytest.TempPathFactory,
) -> CheckedInReplay:
    output_dir = tmp_path_factory.mktemp("provider_baseline_replay") / "baseline"
    result = write_provider_baseline_period_replay(
        inventory_path=PROVIDER_BASELINE_INVENTORY_PATH,
        inventory_summary_path=PROVIDER_BASELINE_INVENTORY_SUMMARY_PATH,
        catalog_path=SOURCE_MAPPING_CATALOG_PATH,
        output_dir=output_dir,
    )
    payload = json.loads(result.summary_path.read_text(encoding="utf-8"))
    return result, payload


def _companies_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {company["company_id"]: company for company in payload["companies"]}


def _assert_hk_warning_classification(
    company: dict[str, Any],
    *,
    assert_artifact_payload: bool = False,
) -> None:
    company_id = company["company_id"]
    warning_classification = company["review"]["combined"]["warning_classification"]
    assert (
        warning_classification["counts_by_category"]["yahoo_pdf_verified"] >= 5
    )
    assert set(
        warning_classification["fields_by_category"]["yahoo_pdf_verified"]
    ) >= EXPECTED_HK_YAHOO_VERIFIED_FIELDS
    assert set(
        warning_classification["fields_by_category"]["yahoo_definition_unverified"]
    ) <= EXPECTED_HK_YAHOO_DEFINITION_UNVERIFIED_FIELDS
    expected_mapping_expansion = EXPECTED_HK_MAPPING_EXPANSION_FIELDS_BY_COMPANY.get(
        company_id, []
    )
    assert (
        warning_classification["fields_by_category"]["mapping_expansion_required"]
        == expected_mapping_expansion
    )
    assert set(
        warning_classification["fields_by_category"]["source_unavailable"]
    ) >= EXPECTED_HK_SOURCE_UNAVAILABLE_FIELDS

    assert "warning_classification" in company["artifact_paths"]["combined"]
    artifact_path = Path(company["artifact_paths"]["combined"]["warning_classification"])
    assert artifact_path.exists()
    if assert_artifact_payload:
        artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert (
            artifact_payload["items"]["revenue"]["category"]
            == "yahoo_pdf_verified"
        )

    assert "hk_15_field_closure_report" in company["artifact_paths"]["combined"]
    closure_path = Path(
        company["artifact_paths"]["combined"]["hk_15_field_closure_report"]
    )
    assert closure_path.exists()
    if assert_artifact_payload:
        closure_payload = json.loads(closure_path.read_text(encoding="utf-8"))
        assert closure_payload["total_fields"] == 15
        assert set(closure_payload["fields_by_category"]["clean_present"]) == {
            "cash",
            "defer_tax_liab",
            "financing_cash_flow",
            "investing_cash_flow",
            "operating_cash_flow",
            "net_profit",
            "revenue",
            "total_assets",
            "total_cur_assets",
            "total_cur_liab",
            "total_liabilities",
        }
        assert set(
            closure_payload["fields_by_category"]["yahoo_definition_unverified"]
        ) == {
            "gross_profit"
        }
        assert set(closure_payload["fields_by_category"]["pdf_required"]) == set()
        assert closure_payload["items"]["net_profit"]["category"] == "clean_present"
        assert "net_profit" in closure_payload["sampled_pdf_policy_proof_fields"]
        assert closure_payload["final_pdf_evidence_fields"] == []
        assert (
            "gross_profit"
            in closure_payload["provider_semantics_unverified_fields"]
        )

        trust_policy_path = Path(
            company["artifact_paths"]["combined"]["hk_yahoo_trust_policy_report"]
        )
        trust_policy_payload = json.loads(
            trust_policy_path.read_text(encoding="utf-8")
        )
        assert (
            "net_profit"
            in trust_policy_payload["sampled_pdf_policy_proof_fields"]
        )
        assert trust_policy_payload["final_pdf_evidence_fields"] == []
        assert (
            trust_policy_payload["items"]["net_profit"]["trust_policy_evidence"][
                "proof_class"
            ]
            == "sampled_pdf_policy_proof"
        )
        assert (
            trust_policy_payload["items"]["net_profit"]["trust_policy_evidence"][
                "is_final_pdf_evidence"
            ]
            is False
        )


def _record(
    *,
    source: str = "akshare",
    market: str = "CN",
    ticker: str = "600519",
    statement_type: str = "income_statement",
    period: str | None = "2024-12-31",
    raw_field_name: str = "营业收入",
    raw_field_code: str | None = "OPERATE_INCOME",
    raw_value: str = "100",
    source_status: str = "present",
) -> SourceInventoryRecord:
    evidence = SourceEvidence(
        source=source,  # type: ignore[arg-type]
        adapter=source,
        function=statement_type,
        artifact_id=f"{source}_{ticker}_{statement_type}",
        raw_record_id=f"{source}:{ticker}:{statement_type}:{period}:{raw_field_name}",
        raw_field_name=raw_field_name,
        raw_field_code=raw_field_code,
    )
    return SourceInventoryRecord(
        source=source,  # type: ignore[arg-type]
        market=market,
        ticker=ticker,
        statement_type=statement_type,
        period=period,
        raw_field_name=raw_field_name,
        raw_field_code=raw_field_code,
        raw_value=raw_value,
        parsed_numeric_value=Decimal(raw_value),
        currency="CNY" if market == "CN" else "HKD",
        unit="yuan" if market == "CN" else "raw",
        source_status=source_status,  # type: ignore[arg-type]
        source_evidence=(evidence,),
    )


def test_select_latest_annual_records_ignores_interim_periods() -> None:
    records = (
        _record(period="2024-12-31", raw_value="100"),
        _record(period="2025-12-31 00:00:00", raw_value="120"),
        _record(period="2025-09-30", raw_value="200"),
        _record(period="2023-12-31", raw_value="50"),
    )

    selected = select_latest_annual_records(records)

    assert [record.period for record in selected] == ["2025-12-31"]
    assert [record.raw_value for record in selected] == ["120"]


def test_select_latest_annual_records_drops_non_present_when_annual_present() -> None:
    records = (
        _record(period="2025-12-31 00:00:00", raw_value="120"),
        _record(period=None, raw_value="0", source_status="source_error"),
    )

    selected = select_latest_annual_records(records)

    assert len(selected) == 1
    assert selected[0].source_status == "present"
    assert selected[0].period == "2025-12-31"


def test_select_latest_annual_records_keeps_all_when_no_annual_present() -> None:
    records = (
        _record(period="2025-09-30", raw_value="120"),
        _record(period=None, raw_value="0", source_status="source_error"),
    )

    selected = select_latest_annual_records(records)

    assert selected == records


def test_select_latest_annual_records_is_group_local() -> None:
    akshare_2025 = _record(
        source="akshare",
        ticker="600519",
        period="2025-12-31 00:00:00",
    )
    yahoo_2024 = _record(
        source="yahoo",
        market="CN",
        ticker="600519.SS",
        period="2024-12-31",
        raw_field_name="Total Revenue",
        raw_field_code=None,
    )

    assert select_latest_annual_records((akshare_2025,))[0].period == "2025-12-31"
    assert select_latest_annual_records((yahoo_2024,)) == (yahoo_2024,)


def test_company_source_groups_resolve_provider_tickers_from_targets() -> None:
    groups = company_source_groups()

    assert groups["600519"]["akshare"] == ProviderBaselineGroup(
        company_id="600519",
        source="akshare",
        market="CN",
        provider_ticker="600519",
    )
    assert groups["600519"]["yahoo"] == ProviderBaselineGroup(
        company_id="600519",
        source="yahoo",
        market="CN",
        provider_ticker="600519.SS",
    )
    assert groups["00001"]["yahoo"].provider_ticker == "0001.HK"
    assert groups["01113"]["yahoo"].provider_ticker == "1113.HK"


def test_company_market_rejects_mixed_provider_markets() -> None:
    with pytest.raises(ValueError, match="provider markets differ for 600519"):
        _company_market(
            {
                "akshare": ProviderBaselineGroup(
                    company_id="600519",
                    source="akshare",
                    market="CN",
                    provider_ticker="600519",
                ),
                "yahoo": ProviderBaselineGroup(
                    company_id="600519",
                    source="yahoo",
                    market="HK",
                    provider_ticker="600519.HK",
                ),
            }
        )


def test_write_provider_baseline_period_replay_selects_one_period_per_source(
    tmp_path: Path,
) -> None:
    inventory_path = tmp_path / "source_inventory.jsonl"
    inventory_summary_path = tmp_path / "provider_field_inventory_summary.json"
    inventory_summary_path.write_text("{}\n", encoding="utf-8")
    write_source_inventory(
        inventory_path,
        (
            _record(period="2024-12-31", raw_value="100"),
            _record(period="2025-12-31 00:00:00", raw_value="120"),
            _record(
                source="yahoo",
                market="CN",
                ticker="600519.SS",
                statement_type="balance_sheet",
                period="2024-12-31",
                raw_field_name="Cash And Cash Equivalents",
                raw_field_code=None,
                raw_value="90",
            ),
            _record(
                source="yahoo",
                market="CN",
                ticker="600519.SS",
                statement_type="balance_sheet",
                period="2025-12-31",
                raw_field_name="Cash And Cash Equivalents",
                raw_field_code=None,
                raw_value="120",
            ),
        ),
    )

    result = write_provider_baseline_period_replay(
        inventory_path=inventory_path,
        inventory_summary_path=inventory_summary_path,
        catalog_path=SOURCE_MAPPING_CATALOG_PATH,
        output_dir=tmp_path / "replay",
        company_ids=("600519",),
    )

    payload = json.loads(result.summary_path.read_text(encoding="utf-8"))
    company = payload["companies"][0]
    assert payload["inventory_summary_path"] == str(inventory_summary_path)
    assert company["company_id"] == "600519"
    assert company["selected_periods"] == {
        "akshare": {
            "normalized": "2025-12-31",
            "raw_periods": ["2025-12-31 00:00:00"],
        },
        "yahoo": {
            "normalized": "2025-12-31",
            "raw_periods": ["2025-12-31"],
        },
    }
    assert company["coverage"]["akshare_only"]["covered_fields"] == ["revenue"]
    # money_cap shares the Yahoo alias "Cash And Cash Equivalents" with cash
    assert set(company["coverage"]["yahoo_only"]["covered_fields"]) == {"cash", "money_cap"}
    assert set(company["coverage"]["combined"]["covered_fields"]) == {
        "cash",
        "money_cap",
        "revenue",
    }
    assert "cash" in company["review"]["akshare_only"]["gap_categories"][
        "source_availability"
    ]
    assert company["review"]["combined"]["gap_categories"][
        "real_reconciliation_conflict"
    ] == []
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "present_fields:" in markdown
    assert "source_availability:" in markdown
    assert "policy_unresolved_conflict:" in markdown
    assert "review_summary: " in markdown
    assert (tmp_path / "replay" / "600519" / "combined" / "review_summary.json").exists()


def test_write_provider_baseline_period_replay_rejects_unknown_company_id(
    tmp_path: Path,
) -> None:
    inventory_path = tmp_path / "source_inventory.jsonl"
    inventory_summary_path = tmp_path / "provider_field_inventory_summary.json"
    inventory_summary_path.write_text("{}\n", encoding="utf-8")
    write_source_inventory(inventory_path, ())

    with pytest.raises(ValueError, match="unknown company ids: 99999"):
        write_provider_baseline_period_replay(
            inventory_path=inventory_path,
            inventory_summary_path=inventory_summary_path,
            catalog_path=SOURCE_MAPPING_CATALOG_PATH,
            output_dir=tmp_path / "replay",
            company_ids=("99999",),
        )


def test_provider_baseline_period_replay_uses_checked_in_fixture(
    checked_in_provider_baseline_replay: CheckedInReplay,
) -> None:
    result, payload = checked_in_provider_baseline_replay

    assert result.company_count == 3
    assert payload["company_count"] == 3
    assert {company["company_id"] for company in payload["companies"]} == {
        "00001",
        "01113",
        "600519",
    }
    assert all(
        company["coverage"]["combined"]["total_fields"] == 33
        for company in payload["companies"]
    )
    companies = {company["company_id"]: company for company in payload["companies"]}
    assert companies["600519"]["selected_periods"]["akshare"]["normalized"] == "2025-12-31"
    assert companies["600519"]["selected_periods"]["yahoo"]["normalized"] == "2025-12-31"
    assert companies["600519"]["coverage"]["akshare_only"]["covered_count"] >= 11
    assert companies["600519"]["coverage"]["yahoo_only"]["covered_count"] >= 11
    assert companies["00001"]["coverage"]["yahoo_only"]["covered_count"] >= 11
    assert companies["01113"]["coverage"]["yahoo_only"]["covered_count"] >= 11
    assert companies["600519"]["review"]["combined"][
        "selected_with_warnings_fields"
    ]
    assert companies["00001"]["review"]["combined"]["gap_categories"][
        "pdf_llm_supplement_candidates"
    ]
    for company_id in HK_COMPANY_IDS:
        _assert_hk_warning_classification(
            companies[company_id],
            assert_artifact_payload=True,
        )

    for company_id in ("600519", "00001", "01113"):
        report_path = Path(
            companies[company_id]["artifact_paths"]["combined"][
                "reconciliation_report"
            ]
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        reasons = {item["reason"] for item in report["items"].values()}
        assert "candidate periods differ" not in reasons


def test_provider_baseline_replay_reports_policy_selected_and_clean_counts(
    checked_in_provider_baseline_replay: CheckedInReplay,
) -> None:
    _, payload = checked_in_provider_baseline_replay
    companies = _companies_by_id(payload)

    maotai_combined = companies["600519"]["coverage"]["combined"]
    assert maotai_combined["selected_count"] >= maotai_combined["covered_count"]
    assert maotai_combined["clean_present_count"] <= maotai_combined["selected_count"]
    assert "revenue" in companies["600519"]["review"]["combined"][
        "selected_with_warnings_fields"
    ]

    for company_id in HK_COMPANY_IDS:
        hk_combined = companies[company_id]["review"]["combined"]
        assert "present_metadata_warning_fields" in hk_combined
        assert "metadata_blocker_fields" in hk_combined
        assert set(hk_combined["selected_with_warnings_fields"]) >= set(
            hk_combined["present_metadata_warning_fields"]
        )
        assert set(hk_combined["fields_requiring_pdf_evidence"]) >= set(
            hk_combined["metadata_blocker_fields"]
        )
        assert "source_policy_report" in companies[company_id]["artifact_paths"][
            "combined"
        ]
        _assert_hk_warning_classification(companies[company_id])

        hk_akshare = companies[company_id]["review"]["akshare_only"]
        assert set(hk_akshare["metadata_blocker_fields"]) >= (
            EXPECTED_HK_METADATA_BLOCKER_FIELDS
        )
        assert not (
            set(companies[company_id]["coverage"]["akshare_only"]["clean_present_fields"])
            & set(hk_akshare["metadata_blocker_fields"])
        )

        policy_report_path = Path(
            companies[company_id]["artifact_paths"]["combined"]["source_policy_report"]
        )
        policy_report = json.loads(policy_report_path.read_text(encoding="utf-8"))
        selected_candidate = policy_report["items"]["revenue"]["selected_candidate"]
        assert selected_candidate["unit_multiplier"] == "1"
        assert selected_candidate["currency_proof_source"] == "yahoo_statement_metadata"
        assert selected_candidate["unit_proof_source"] == "source_unit:raw"


def test_provider_baseline_replay_applies_default_hk_yahoo_trust_policy(
    checked_in_provider_baseline_replay: CheckedInReplay,
) -> None:
    _, payload = checked_in_provider_baseline_replay
    companies = _companies_by_id(payload)

    for company_id in HK_COMPANY_IDS:
        company = companies[company_id]
        combined_coverage = company["coverage"]["combined"]
        combined_review = company["review"]["combined"]
        warning_fields = combined_review["warning_classification"]["fields_by_category"]

        assert EXPECTED_HK_YAHOO_VERIFIED_FIELDS <= set(
            combined_coverage["clean_present_fields"]
        )
        assert not (
            EXPECTED_HK_YAHOO_DEFINITION_UNVERIFIED_FIELDS
            & set(combined_coverage["clean_present_fields"])
        )
        assert (
            set(combined_review["yahoo_pdf_verified_fields"])
            == EXPECTED_HK_YAHOO_VERIFIED_FIELDS
        )
        assert (
            set(combined_review["yahoo_definition_unverified_fields"])
            == EXPECTED_HK_YAHOO_DEFINITION_UNVERIFIED_FIELDS
        )
        assert set(warning_fields["yahoo_pdf_verified"]) == (
            EXPECTED_HK_YAHOO_VERIFIED_FIELDS
        )
        assert set(warning_fields["yahoo_definition_unverified"]) == (
            EXPECTED_HK_YAHOO_DEFINITION_UNVERIFIED_FIELDS
            & set(warning_fields["yahoo_definition_unverified"])
        )
        assert EXPECTED_HK_SOURCE_UNAVAILABLE_FIELDS <= set(
            warning_fields["source_unavailable"]
        )
        expected_mapping_expansion = EXPECTED_HK_MAPPING_EXPANSION_FIELDS_BY_COMPANY.get(
            company_id, []
        )
        assert expected_mapping_expansion == warning_fields[
            "mapping_expansion_required"
        ]

        artifact_paths = company["artifact_paths"]["combined"]
        assert "hk_yahoo_trust_policy_report" in artifact_paths
        trust_report_path = Path(artifact_paths["hk_yahoo_trust_policy_report"])
        assert trust_report_path.exists()
        trust_report = json.loads(trust_report_path.read_text(encoding="utf-8"))
        assert set(trust_report["yahoo_pdf_verified_fields"]) == (
            EXPECTED_HK_YAHOO_VERIFIED_FIELDS
        )
        assert set(trust_report["yahoo_definition_unverified_fields"]) == (
            EXPECTED_HK_YAHOO_DEFINITION_UNVERIFIED_FIELDS
        )
        assert "pdf_required_fields" in trust_report

        source_policy_path = Path(artifact_paths["source_policy_report"])
        source_policy_report = json.loads(source_policy_path.read_text(encoding="utf-8"))
        extraction_path = Path(artifact_paths["extraction_result"])
        extraction_result = json.loads(extraction_path.read_text(encoding="utf-8"))
        for field_id in EXPECTED_HK_YAHOO_VERIFIED_FIELDS:
            policy_item = source_policy_report["items"][field_id]
            export_item = extraction_result["items"][field_id]
            assert policy_item["trust_policy_evidence"]["classification"] == (
                "yahoo_pdf_verified"
            )
            assert export_item["trust_policy_evidence"]["classification"] == (
                "yahoo_pdf_verified"
            )
            assert export_item["pdf_evidence"] == []
        for field_id in EXPECTED_HK_YAHOO_DEFINITION_UNVERIFIED_FIELDS:
            assert (
                source_policy_report["items"][field_id]["trust_policy_evidence"]
                is None
            )
            assert extraction_result["items"][field_id]["trust_policy_evidence"] is None
            assert extraction_result["items"][field_id]["pdf_evidence"] == []

    markdown = checked_in_provider_baseline_replay[0].markdown_path.read_text(
        encoding="utf-8"
    )
    assert "yahoo_pdf_verified_fields: " in markdown
    assert "yahoo_definition_unverified_fields: " in markdown
    assert "pdf_required_fields: " in markdown
    assert "hk_yahoo_trust_policy_report: " in markdown


def test_checked_in_hk_replay_reports_exact_33_field_closure_buckets(
    checked_in_provider_baseline_replay: CheckedInReplay,
) -> None:
    _, payload = checked_in_provider_baseline_replay
    companies = _companies_by_id(payload)
    # N3 added 4 more fields to catalog (33 total).
    # rd_exp/fv_value_chg_gain are CN-only akshare fields: source_unavailable for HK.
    # non_oper_income/non_oper_exp land in mapping_expansion_required for HK (partial provider data found).
    # 00001: equity_to_owners/operating_cost/operating_profit/sga all clean_present.
    # 01113: equity_to_owners/operating_cost/operating_profit clean; sga source_unavailable.
    # fix_assets/accounts_receiv/acct_payable remain conflicts for HK; inventories conflict for 00001.
    expected_clean_by_company = {
        "00001": {
            "cash",
            "defer_tax_assets",
            "defer_tax_liab",
            "equity_attributable_to_owners",
            "financing_cash_flow",
            "investing_cash_flow",
            "lt_borr",
            "minority_int",
            "money_cap",
            "net_profit",
            "operating_cash_flow",
            "operating_cost",
            "operating_profit",
            "revenue",
            "selling_general_administrative",
            "st_borr",
            "total_assets",
            "total_cur_assets",
            "total_cur_liab",
            "total_liabilities",
        },
        "01113": {
            "cash",
            "defer_tax_assets",
            "defer_tax_liab",
            "equity_attributable_to_owners",
            "financing_cash_flow",
            "inventories",
            "investing_cash_flow",
            "lt_borr",
            "minority_int",
            "money_cap",
            "net_profit",
            "operating_cash_flow",
            "operating_cost",
            "operating_profit",
            "other_cur_assets",
            "revenue",
            "st_borr",
            "total_assets",
            "total_cur_assets",
            "total_cur_liab",
            "total_liabilities",
        },
    }
    expected_clean_count_by_company = {"00001": 20, "01113": 21}

    for company_id in HK_COMPANY_IDS:
        combined = companies[company_id]["coverage"]["combined"]
        review = companies[company_id]["review"]["combined"]
        warning_fields = review["warning_classification"]["fields_by_category"]

        assert set(combined["clean_present_fields"]) == expected_clean_by_company[company_id]
        assert combined["clean_present_count"] == expected_clean_count_by_company[company_id]
        assert combined["total_fields"] == 33
        assert set(review["yahoo_definition_unverified_fields"]) == {
            "gross_profit",
        }
        expected_mapping_expansion = EXPECTED_HK_MAPPING_EXPANSION_FIELDS_BY_COMPANY.get(
            company_id, []
        )
        assert warning_fields["mapping_expansion_required"] == expected_mapping_expansion
        assert set(warning_fields["source_unavailable"]) >= EXPECTED_HK_SOURCE_UNAVAILABLE_FIELDS
        # 01113 has selling_general_administrative as source_unavailable; 00001 does not
        if company_id == "01113":
            assert (
                EXPECTED_01113_EXTRA_SOURCE_UNAVAILABLE
                <= set(warning_fields["source_unavailable"])
            ), (
                f"01113 expected selling_general_administrative in source_unavailable "
                f"but got: {warning_fields['source_unavailable']!r}"
            )
        elif company_id == "00001":
            assert (
                not EXPECTED_01113_EXTRA_SOURCE_UNAVAILABLE
                & set(warning_fields["source_unavailable"])
            ), (
                f"00001 should NOT have {EXPECTED_01113_EXTRA_SOURCE_UNAVAILABLE} "
                f"in source_unavailable but got: {warning_fields['source_unavailable']!r}"
            )


def test_provider_baseline_replay_can_disable_hk_yahoo_trust_policy(
    tmp_path: Path,
) -> None:
    result = write_provider_baseline_period_replay(
        inventory_path=PROVIDER_BASELINE_INVENTORY_PATH,
        inventory_summary_path=PROVIDER_BASELINE_INVENTORY_SUMMARY_PATH,
        catalog_path=SOURCE_MAPPING_CATALOG_PATH,
        output_dir=tmp_path / "baseline",
        company_ids=("00001",),
        hk_yahoo_trust_policy_path=None,
    )
    payload = json.loads(result.summary_path.read_text(encoding="utf-8"))
    company = payload["companies"][0]

    assert "hk_yahoo_trust_policy_report" not in company["artifact_paths"]["combined"]
    assert not (
        EXPECTED_HK_YAHOO_VERIFIED_FIELDS
        <= set(company["coverage"]["combined"]["clean_present_fields"])
    )


def test_provider_baseline_replay_combined_uses_canonical_units_for_600519(
    checked_in_provider_baseline_replay: CheckedInReplay,
) -> None:
    _, payload = checked_in_provider_baseline_replay
    company = _companies_by_id(payload)["600519"]
    combined_coverage = company["coverage"]["combined"]
    combined_review = company["review"]["combined"]

    assert company["company_id"] == "600519"
    assert combined_coverage["covered_count"] >= 12
    assert set(combined_review["present_fields"]) >= {
        "cash",
        "operating_cash_flow",
        "total_assets",
        "total_cur_assets",
        "total_cur_liab",
        "total_liabilities",
    }
    assert "revenue" in combined_review["selected_with_warnings_fields"]
    assert "net_profit" in combined_review["present_fields"]
    assert "revenue" not in combined_review["conflict_fields"]
    assert "net_profit" not in combined_review["conflict_fields"]
    assert "revenue" in combined_review["gap_categories"][
        "real_reconciliation_conflict"
    ]
    assert "revenue" not in combined_review["gap_categories"][
        "policy_unresolved_conflict"
    ]
    assert "policy_unresolved_conflict" in combined_review["gap_categories"]

    report_path = Path(
        company["artifact_paths"]["combined"]["reconciliation_report"]
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    # Raw reconciliation and policy-selected export/review intentionally report
    # different layers: revenue is still a provider disagreement before policy
    # selection, while net_profit is equivalent after PARENT_NETPROFIT alias priority.
    assert report["items"]["cash"]["status"] == "equivalent"
    assert (
        report["items"]["cash"]["reason"]
        == "candidate normalized values are equal"
    )
    assert report["items"]["revenue"]["status"] == "conflict"
    assert (
        report["items"]["revenue"]["reason"]
        == "candidate normalized values differ"
    )
    assert report["items"]["net_profit"]["status"] != "conflict"


def test_provider_baseline_period_replay_script_is_local_fixture_entrypoint() -> None:
    script = PROVIDER_BASELINE_REPLAY_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "replay-provider-baseline" in script
    assert "source_inventory.jsonl.gz" in script
    assert "provider_field_inventory_summary.json" in script
    assert "TAXONOMY" in script
    assert "field_catalog/turtle_v015_field_taxonomy.json" in script
    assert "--taxonomy" in script
    assert "tmp/runs/provider_baseline_period_replay" in script
