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


def _expected_total_fields() -> int:
    """Derive total P0/P1/P2 field count from the source mapping catalog.

    Why: hardcoding numbers means catalog growth requires manual updates in
    multiple test files. Compute from the catalog so per-company expected_clean
    sets stay as behavioral expectations while denominator tracks the catalog.

    Only counts P0/P1/P2 priorities — provider_baseline_replay loads these
    by default. P3 fields are opt-in.
    """
    payload = json.loads(SOURCE_MAPPING_CATALOG_PATH.read_text(encoding="utf-8"))
    selected = {"P0", "P1", "P2"}
    field_ids: set[str] = set()
    for group in payload.get("priorities", []):
        if group.get("priority") in selected:
            for fid in group.get("fields", []):
                field_ids.add(str(fid))
    return len(field_ids)


EXPECTED_TOTAL_FIELDS = _expected_total_fields()

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
        "inventories",
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
    # invest_income: post-Phase-I-A.2 description expansion now matches
    # provider raw fields via keyword_overlap, moving it from source_unavailable
    # to mapping_expansion_required (correct: provider candidates exist).
    # receiv_tax_refund: CN-only AKShare field; HK companies have no provider data
    # but the alias matches partial inventory entries so lands in mapping_expansion.
    # stock_based_compensation: N4.B added with no provider raw, but
    # taxonomy.description tokens match partial inventory entries so it
    # lands in mapping_expansion_required for HK.
    "00001": ["invest_income", "non_oper_exp", "non_oper_income", "other_cur_assets", "receiv_tax_refund", "stock_based_compensation"],
    "01113": ["invest_income", "non_oper_exp", "non_oper_income", "receiv_tax_refund", "stock_based_compensation"],
}
EXPECTED_HK_SOURCE_UNAVAILABLE_FIELDS = frozenset(
    {
        "bond_payable",
        "cip",
        "fv_value_chg_gain",
        "rd_exp",
    }
)
# 01113 also has selling_general_administrative as source_unavailable; 00001 does not.
# 00001 also has repurchase_of_stock as source_unavailable (no Yahoo data for 00001).
EXPECTED_01113_EXTRA_SOURCE_UNAVAILABLE = frozenset({"selling_general_administrative"})
EXPECTED_00001_EXTRA_SOURCE_UNAVAILABLE = frozenset({"repurchase_of_stock"})


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
        company["coverage"]["combined"]["total_fields"] == EXPECTED_TOTAL_FIELDS
        for company in payload["companies"]
    )
    companies = {company["company_id"]: company for company in payload["companies"]}
    assert companies["600519"]["selected_periods"]["akshare"]["normalized"] == "2025-12-31"
    assert companies["600519"]["selected_periods"]["yahoo"]["normalized"] == "2025-12-31"
    assert companies["600519"]["coverage"]["akshare_only"]["covered_count"] >= 11
    assert companies["600519"]["coverage"]["yahoo_only"]["covered_count"] >= 11
    assert companies["00001"]["coverage"]["yahoo_only"]["covered_count"] >= 11
    assert companies["01113"]["coverage"]["yahoo_only"]["covered_count"] >= 11
    # 600519: revenue/operating_profit/SGA are unresolved_conflict (AKShare and Yahoo
    # present with different values; preserve_conflict policy does not select a primary).
    assert "revenue" in companies["600519"]["review"]["combined"]["conflict_fields"]
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
    # Phase H0: null_means_zero promotes bond_payable/st_borr/lt_borr to clean_present.
    # revenue/operating_profit/SGA remain non-clean: AKShare and Yahoo have different
    # values with preserve_conflict policy — unresolved_conflict, architecturally honest.
    # N4.A: P2 cash-flow fields added; 600519 gains change_in_receivables/payables/inventory
    # → clean_present_count rises from 30 to 33.
    assert maotai_combined["clean_present_count"] == 33
    assert {"bond_payable", "st_borr", "lt_borr"} <= set(
        maotai_combined["clean_present_fields"]
    )
    assert not (
        {"revenue", "operating_profit", "selling_general_administrative"}
        & set(maotai_combined["clean_present_fields"])
    )
    # source_policy_resolvable no longer contains null_means_zero fields.
    maotai_wc = companies["600519"]["review"]["combined"]["warning_classification"]
    assert "bond_payable" not in maotai_wc["fields_by_category"]["source_policy_resolvable"]
    assert "st_borr" not in maotai_wc["fields_by_category"]["source_policy_resolvable"]
    assert "lt_borr" not in maotai_wc["fields_by_category"]["source_policy_resolvable"]
    # revenue/operating_profit/SGA are unresolved conflicts — present in conflict_fields.
    maotai_review = companies["600519"]["review"]["combined"]
    assert {"revenue", "operating_profit", "selling_general_administrative"} <= set(
        maotai_review["conflict_fields"]
    )

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


def test_checked_in_hk_replay_reports_exact_42_field_closure_buckets(
    checked_in_provider_baseline_replay: CheckedInReplay,
) -> None:
    _, payload = checked_in_provider_baseline_replay
    companies = _companies_by_id(payload)
    # N4.A added 8 P2 cash-flow fields (41 total: P0+P1+P2).
    # rd_exp/fv_value_chg_gain are CN-only akshare fields: source_unavailable for HK.
    # non_oper_income/non_oper_exp land in mapping_expansion_required for HK (partial provider data found).
    # receiv_tax_refund is CN-only AKShare: lands in mapping_expansion for HK.
    # repurchase_of_stock: Yahoo has no data for 00001 → source_unavailable for 00001.
    # 00001: gained capital_expenditures/change_in_payables/change_in_receivables/
    #         depreciation_amortization/dividends_paid → 26 clean.
    # 01113: additionally gained change_in_inventory/repurchase_of_stock → 28 clean.
    # H1: inventories clean_present for both 00001 and 01113 (Yahoo Inventory proven against PDF).
    expected_clean_by_company = {
        "00001": {
            "capital_expenditures",
            "cash",
            "change_in_inventory",
            "change_in_payables",
            "change_in_receivables",
            "defer_tax_assets",
            "defer_tax_liab",
            "depreciation_amortization",
            "dividends_paid",
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
            "revenue",
            "selling_general_administrative",
            "st_borr",
            "total_assets",
            "total_cur_assets",
            "total_cur_liab",
            "total_liabilities",
        },
        "01113": {
            "capital_expenditures",
            "cash",
            "change_in_inventory",
            "change_in_payables",
            "change_in_receivables",
            "defer_tax_assets",
            "defer_tax_liab",
            "depreciation_amortization",
            "dividends_paid",
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
            "repurchase_of_stock",
            "revenue",
            "st_borr",
            "total_assets",
            "total_cur_assets",
            "total_cur_liab",
            "total_liabilities",
        },
    }
    expected_clean_count_by_company = {"00001": 27, "01113": 28}

    for company_id in HK_COMPANY_IDS:
        combined = companies[company_id]["coverage"]["combined"]
        review = companies[company_id]["review"]["combined"]
        warning_fields = review["warning_classification"]["fields_by_category"]

        assert set(combined["clean_present_fields"]) == expected_clean_by_company[company_id]
        assert combined["clean_present_count"] == expected_clean_count_by_company[company_id]
        assert combined["total_fields"] == EXPECTED_TOTAL_FIELDS
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
            assert (
                EXPECTED_00001_EXTRA_SOURCE_UNAVAILABLE
                <= set(warning_fields["source_unavailable"])
            ), (
                f"00001 expected {EXPECTED_00001_EXTRA_SOURCE_UNAVAILABLE} in source_unavailable "
                f"but got: {warning_fields['source_unavailable']!r}"
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
    # revenue is non-clean: AKShare OPERATE_INCOME (168,838M 营业收入) ≠ Yahoo Total Revenue
    # (172,054M = TOTAL_OPERATE_INCOME). preserve_conflict policy leaves it unresolved.
    assert "revenue" in combined_review["conflict_fields"]
    assert "revenue" not in company["coverage"]["combined"]["clean_present_fields"]
    assert "net_profit" in combined_review["present_fields"]
    assert "net_profit" not in combined_review["conflict_fields"]
    # revenue IS in real_reconciliation_conflict (values differ between sources).
    assert "revenue" in combined_review["gap_categories"][
        "real_reconciliation_conflict"
    ]
    assert "revenue" in combined_review["gap_categories"][
        "policy_unresolved_conflict"
    ]
    assert "policy_unresolved_conflict" in combined_review["gap_categories"]

    report_path = Path(
        company["artifact_paths"]["combined"]["reconciliation_report"]
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    # cash still reconciles as equivalent; revenue is now a conflict.
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


def test_merge_llm_evidence_supplement_promotes_missing_to_present(
    tmp_path: Path,
) -> None:
    from decimal import Decimal
    from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
        _merge_llm_evidence_supplement,
    )

    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="catalog",
        catalog_version="1",
        items={
            "rd_exp": SourceFirstExportItem(field_id="rd_exp", status="missing"),
            "revenue": SourceFirstExportItem(
                field_id="revenue", status="present", value=Decimal("100"),
            ),
        },
    )
    supplement_path = tmp_path / "llm_evidence_supplement.json"
    supplement_path.write_text(json.dumps({
        "schema_version": "llm-evidence-supplement-v1",
        "company_id": "00001",
        "pdf_path": "x.pdf",
        "extracted_at": "2026-05-08T00:00:00",
        "summary": {},
        "items": {
            "rd_exp": {
                "status": "present", "value": "615434",
                "currency": "CNY", "unit": "thousand",
            },
            "revenue": {
                "status": "present", "value": "999",  # should be IGNORED
                "currency": "CNY", "unit": "thousand",
            },
        },
    }), encoding="utf-8")

    merged = _merge_llm_evidence_supplement(export, supplement_path)

    assert merged.items["rd_exp"].status == "present"
    assert merged.items["rd_exp"].value == Decimal("615434")
    assert "llm_supplemented" in merged.items["rd_exp"].review_notes
    assert merged.items["rd_exp"].selected_source == "llm"
    assert merged.items["rd_exp"].verification_required
    # revenue must NOT be overridden
    assert merged.items["revenue"].value == Decimal("100")


def test_merge_llm_evidence_supplement_no_op_when_file_missing() -> None:
    from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
        _merge_llm_evidence_supplement,
    )

    export = SourceFirstExportResult(
        profile="source_only", catalog_id="c", catalog_version="1", items={},
    )
    merged = _merge_llm_evidence_supplement(export, Path("/nonexistent/path.json"))
    assert merged.items == export.items


def test_merge_llm_evidence_supplement_no_op_when_schema_mismatch(
    tmp_path: Path,
) -> None:
    from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
        _merge_llm_evidence_supplement,
    )

    bad_path = tmp_path / "wrong_schema.json"
    bad_path.write_text(json.dumps({
        "schema_version": "different-v999",
        "items": {"x": {"status": "present", "value": "1"}},
    }), encoding="utf-8")

    export = SourceFirstExportResult(
        profile="source_only", catalog_id="c", catalog_version="1",
        items={"x": SourceFirstExportItem(field_id="x", status="missing")},
    )

    merged = _merge_llm_evidence_supplement(export, bad_path)
    assert merged.items["x"].status == "missing"


def test_replay_slice_only_merges_llm_supplement_for_combined_slice(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Verify the slice gate: per-source slices (akshare_only, yahoo_only)
    must NOT consume llm_evidence_supplement.json. Only the combined
    slice merges LLM evidence — otherwise per-source coverage views get
    polluted with cross-source LLM values.
    """
    output_dir = tmp_path_factory.mktemp("slice_gate") / "baseline"
    company_id = "00001"

    # Pre-create a supplement at the company-dir level. _write_slice
    # looks at output_dir.parent which is company_dir.
    company_dir = output_dir / company_id
    company_dir.mkdir(parents=True, exist_ok=True)
    (company_dir / "llm_evidence_supplement.json").write_text(json.dumps({
        "schema_version": "llm-evidence-supplement-v1",
        "company_id": company_id,
        "pdf_path": "x.pdf",
        "extracted_at": "2026-05-08T00:00:00",
        "summary": {},
        "items": {
            "rd_exp": {
                "status": "present", "value": "999999",
                "currency": "CNY", "unit": "thousand",
            },
        },
    }), encoding="utf-8")

    write_provider_baseline_period_replay(
        inventory_path=PROVIDER_BASELINE_INVENTORY_PATH,
        inventory_summary_path=PROVIDER_BASELINE_INVENTORY_SUMMARY_PATH,
        catalog_path=SOURCE_MAPPING_CATALOG_PATH,
        output_dir=output_dir,
    )

    def _rd_exp_review_notes(slice_name: str) -> list[str]:
        path = company_dir / slice_name / "extraction_result.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("items", {})
        if not isinstance(items, dict):
            return []
        rd_exp_item = items.get("rd_exp")
        if not isinstance(rd_exp_item, dict):
            return []
        notes = rd_exp_item.get("review_notes", [])
        if not isinstance(notes, list):
            return []
        return [str(n) for n in notes]

    combined_notes = _rd_exp_review_notes("combined")
    akshare_notes = _rd_exp_review_notes("akshare_only")
    yahoo_notes = _rd_exp_review_notes("yahoo_only")

    # combined slice should have llm_supplemented review note
    assert "llm_supplemented" in combined_notes, (
        f"combined slice should pick up llm supplement; got {combined_notes}"
    )

    # per-source slices must NOT have consumed the supplement
    assert "llm_supplemented" not in akshare_notes, (
        f"akshare_only slice unexpectedly got llm supplement: {akshare_notes}"
    )
    assert "llm_supplemented" not in yahoo_notes, (
        f"yahoo_only slice unexpectedly got llm supplement: {yahoo_notes}"
    )


def test_normalize_llm_currency_maps_rmb_and_hk_dollar() -> None:
    """Phase I-A.2 review fix: LLM may report currency as RMB / HK$ / etc.

    Verify _normalize_llm_currency maps these to the project's Currency
    Literal correctly, instead of silently coercing to "unknown".
    """
    from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
        _normalize_llm_currency,
    )

    # Direct matches
    assert _normalize_llm_currency("CNY") == "CNY"
    assert _normalize_llm_currency("HKD") == "HKD"
    assert _normalize_llm_currency("USD") == "USD"

    # Common LLM aliases
    assert _normalize_llm_currency("RMB") == "CNY"
    assert _normalize_llm_currency("rmb") == "CNY"  # case insensitive
    assert _normalize_llm_currency("Renminbi") == "CNY"
    assert _normalize_llm_currency("人民币") == "CNY"
    assert _normalize_llm_currency("人民幣") == "CNY"
    assert _normalize_llm_currency("HK$") == "HKD"
    assert _normalize_llm_currency("港币") == "HKD"
    assert _normalize_llm_currency("US$") == "USD"
    assert _normalize_llm_currency("美元") == "USD"

    # Empty / None
    assert _normalize_llm_currency(None) == "unknown"
    assert _normalize_llm_currency("") == "unknown"
    assert _normalize_llm_currency("   ") == "unknown"

    # Ambiguous "$" — could be HK$ or US$, must not silently coerce
    assert _normalize_llm_currency("$") == "ambiguous"

    # Unknown currency
    assert _normalize_llm_currency("EUR") == "unknown"
    assert _normalize_llm_currency("garbage") == "unknown"


def test_merge_llm_evidence_supplement_normalizes_rmb_currency(tmp_path: Path) -> None:
    """Phase I-A.2 review fix: regression test for currency normalization
    in the merge path. RMB-tagged LLM values must surface as CNY, not unknown.
    """
    from decimal import Decimal
    from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
        _merge_llm_evidence_supplement,
    )

    export = SourceFirstExportResult(
        profile="source_only",
        catalog_id="catalog",
        catalog_version="1",
        items={
            "rd_exp": SourceFirstExportItem(field_id="rd_exp", status="missing"),
        },
    )
    supplement_path = tmp_path / "llm_evidence_supplement.json"
    supplement_path.write_text(json.dumps({
        "schema_version": "llm-evidence-supplement-v1",
        "company_id": "01810",
        "pdf_path": "x.pdf",
        "extracted_at": "2026-05-08T00:00:00",
        "summary": {},
        "items": {
            "rd_exp": {
                "status": "present",
                "value": "24050",
                "currency": "RMB",  # not literal CNY
                "unit": "million",
            },
        },
    }), encoding="utf-8")

    merged = _merge_llm_evidence_supplement(export, supplement_path)

    assert merged.items["rd_exp"].status == "present"
    assert merged.items["rd_exp"].value == Decimal("24050")
    # CRITICAL: RMB must map to CNY, not silently degrade to "unknown"
    assert merged.items["rd_exp"].currency == "CNY"
