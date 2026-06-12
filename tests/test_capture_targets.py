from financial_report_llm_extractor.structured_sources.capture_targets import (
    build_provider_field_capture_targets,
)


def test_provider_field_capture_targets_cover_expected_matrix() -> None:
    targets = build_provider_field_capture_targets()

    assert len(targets) == 18
    actual = {
        (
            target.provider,
            target.company_id,
            target.provider_ticker,
            target.market,
            target.statement_type,
            target.currency,
            target.unit,
            target.exchange,
        )
        for target in targets
    }

    assert (
        "akshare",
        "600519",
        "600519",
        "CN",
        "balance_sheet",
        "CNY",
        "yuan",
        "SH",
    ) in actual
    # AKShare HK targets carry CNY — the EastMoney feed's actual currency
    # for every issuer (docs/gates/2026-06-12-gross-profit-divergence-
    # investigation.md); the Yahoo HK targets below keep the issuer label.
    assert (
        "akshare",
        "00001",
        "00001",
        "HK",
        "income_statement",
        "CNY",
        "raw",
        None,
    ) in actual
    assert (
        "akshare",
        "01113",
        "01113",
        "HK",
        "cash_flow",
        "CNY",
        "raw",
        None,
    ) in actual
    assert (
        "yahoo",
        "600519",
        "600519.SS",
        "CN",
        "balance_sheet",
        "CNY",
        "raw",
        None,
    ) in actual
    assert (
        "yahoo",
        "00001",
        "0001.HK",
        "HK",
        "income_statement",
        "HKD",
        "raw",
        None,
    ) in actual
    assert (
        "yahoo",
        "01113",
        "1113.HK",
        "HK",
        "cash_flow",
        "HKD",
        "raw",
        None,
    ) in actual


def test_provider_field_capture_targets_can_filter_providers() -> None:
    targets = build_provider_field_capture_targets(providers=("akshare",))

    assert len(targets) == 9
    assert {target.provider for target in targets} == {"akshare"}
