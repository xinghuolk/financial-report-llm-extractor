"""Phase HK-LLM-2: regression-lock the LLM supplement merge integration.

Background (docs/phase_hk_llm_recon.md): the orchestrator wiring for LLM
supplement is complete; H2.2 evaluations showed `llm_supplement_present=0`
only because they were invoked without `--pdf` + `--llm-config`. This
test replays existing per-company LLM supplement files (captured in past
phase_i_c_validation_v2 / 600519_2024-12-31_llm runs) against the
current catalog and pins the per-company supplement delta.

It guards against silent regressions in:
- _merge_llm_evidence_supplement (provider_baseline_replay.py)
- bucket cascade `selected_source == "llm" → llm_supplement_present`
  (company_evaluation.py classify_field)
- catalog changes that accidentally re-classify a previously-LLM-merged
  field as source-first clean (which would silently shrink the supplement
  count without losing data, but worth surfacing).

Avoids live LLM API calls by monkey-patching `_run_llm_supplement_step` to
a no-op and pre-placing the captured supplement file in out_dir.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Iterator

import pytest

from financial_report_llm_extractor.structured_sources import company_evaluation
from financial_report_llm_extractor.structured_sources.company_evaluation import (
    run_company_evaluation,
)
from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
    PeriodSpec,
)


REPO = Path(__file__).resolve().parent.parent
CATALOG = REPO / "field_catalog" / "turtle_v015_source_mapping_minimal.json"
TAXONOMY = REPO / "field_catalog" / "turtle_v015_field_taxonomy.json"
DUMMY_PDF = REPO / "downloads" / "hk_stocks" / "01113" / "annual" / "2024_annual_en.pdf"
DUMMY_LLM_CONFIG = REPO / "tmp" / "llm_configs" / "deepseek.json"
HK_LLM_6_EXTENSION_FIXTURE = (
    REPO
    / "tests"
    / "fixtures"
    / "provider_captures"
    / "provider_field_baseline_hk_llm_6_extension"
)


@pytest.fixture
def no_live_llm() -> Iterator[None]:
    """Replace _run_llm_supplement_step with a no-op for the test scope."""
    original = company_evaluation._run_llm_supplement_step
    company_evaluation._run_llm_supplement_step = lambda **_: None  # type: ignore[assignment]
    try:
        yield
    finally:
        company_evaluation._run_llm_supplement_step = original  # type: ignore[assignment]


CASES = [
    # company, market, period_end, inventory_path, supplement_path,
    # expected_baseline_clean, expected_with_llm_total, expected_supplement_fields
    # Phase G1a: +3 P2 fields. CN 600519: +2 clean (c_pay_to_staff +
    # c_paid_for_taxes via AKShare; lt_eqt_invest=None for Maotai). HK 6: +1
    # each (lt_eqt_invest clean via Yahoo "Long Term Equity Investment";
    # c_pay_to_staff/c_paid_for_taxes have no HK provider data).
    # Phase G1b: +2 P3 fields (contract_liabilities_current +
    # contract_liabilities_non_current). 600519: +1 (cl_current via AKShare
    # CONTRACT_LIAB=9.59B; cl_non_current=None). 01810/02498/09987: +1 each
    # (cl_non_current via Yahoo "Non Current Deferred Revenue").
    # 00001/01113/06862: no change (cl_current/cl_non_current land in
    # unresolved_conflict or source_unavailable).
    # 2026-06-12 single-source primary gate: gross_profit CN drops from
    # clean (-1). Its only candidate is Yahoo while the CN primary route is
    # akshare_direct — the per-market single_source_requires_pdf=false
    # waiver no longer applies to a cross-check-source-only candidate, so
    # it lands single_source_unverified (honest: the Yahoo standardized
    # derivation was never adjudicated for CN; the HK acceptance rides the
    # yahoo_standardized_accepted trust rule, which is HK-scoped).
    (
        "600519", "CN", date(2024, 12, 31),
        REPO / "tmp" / "runs" / "600519_2024-12-31" / "source_inventory.jsonl",
        REPO / "tmp" / "runs" / "600519_2024-12-31_llm" / "llm_evidence_supplement.json",
        41, 46,
        ("buyback_cancellation_progress", "capitalized_rd",
         "contingent_liabilities_commitments", "dividend_plan",
         "related_party_receivables_payables"),
    ),
    (
        "00001", "HK", date(2025, 12, 31),
        REPO / "tmp" / "runs" / "h2_2_after" / "00001" / "source_inventory.jsonl",
        REPO / "tmp" / "runs" / "phase_i_c_validation_v2" / "00001"
            / "llm_evidence_supplement.json",
        33, 38,  # +lt_eqt_invest (G1a) +1, +gross_profit standardized +1
        ("capitalized_interest", "contingent_liabilities_commitments",
         "dividend_plan", "dps", "segment_revenue_profit"),
    ),
    (
        "01113", "HK", date(2025, 12, 31),
        REPO / "tmp" / "runs" / "h2_2_after" / "01113" / "source_inventory.jsonl",
        REPO / "tmp" / "runs" / "phase_i_c_validation_v2" / "01113"
            / "llm_evidence_supplement.json",
        34, 38,  # +lt_eqt_invest (G1a) +1, +gross_profit standardized +1
        ("bad_debt_provision", "contingent_liabilities_commitments",
         "dividend_plan", "dps"),
    ),
    (
        "01810", "HK", date(2024, 12, 31),
        HK_LLM_6_EXTENSION_FIXTURE / "01810" / "source_inventory.jsonl.gz",
        REPO / "tmp" / "runs" / "phase_i_c_validation_v2" / "01810"
            / "llm_evidence_supplement.json",
        36, 43,  # +lt_eqt_invest (G1a) +1, +contract_liabilities_non_current (G1b) +1, +gross_profit standardized +1
        ("bad_debt_provision", "buyback_cancellation_progress",
         "contingent_liabilities_commitments", "dividend_plan",
         "lease_liability_maturity", "receivables_aging",
         "segment_revenue_profit"),
    ),
    (
        "02498", "HK", date(2024, 12, 31),
        HK_LLM_6_EXTENSION_FIXTURE / "02498" / "source_inventory.jsonl.gz",
        REPO / "tmp" / "runs" / "phase_i_c_validation_v2" / "02498"
            / "llm_evidence_supplement.json",
        36, 41,  # +lt_eqt_invest (G1a) +1, +contract_liabilities_non_current (G1b) +1, +gross_profit standardized +1
        ("bad_debt_provision", "contingent_liabilities_commitments",
         "dividend_plan", "related_party_receivables_payables",
         "time_deposits_or_wealth_products"),
    ),
    (
        "06862", "HK", date(2024, 12, 31),
        HK_LLM_6_EXTENSION_FIXTURE / "06862" / "source_inventory.jsonl.gz",
        REPO / "tmp" / "runs" / "phase_i_c_validation_v2" / "06862"
            / "llm_evidence_supplement.json",
        36, 41,  # +lt_eqt_invest (G1a) +1, +gross_profit standardized +1
        ("bad_debt_provision", "contingent_liabilities_commitments",
         "dividend_plan", "related_party_receivables_payables",
         "time_deposits_or_wealth_products"),
    ),
    (
        "09987", "HK", date(2024, 12, 31),
        HK_LLM_6_EXTENSION_FIXTURE / "09987" / "source_inventory.jsonl.gz",
        REPO / "tmp" / "runs" / "phase_i_c_validation_v2" / "09987"
            / "llm_evidence_supplement.json",
        35, 38,  # +lt_eqt_invest (G1a) +1, +contract_liabilities_non_current (G1b) +1, +gross_profit standardized +1
        ("lease_liability_maturity", "segment_revenue_profit",
         "time_deposits_or_wealth_products"),
    ),
]


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_hk_llm_2_supplement_merge_delta(
    case: tuple,
    tmp_path: Path,
    no_live_llm: None,
) -> None:
    (
        company, market, period_end, inventory_path, supplement_path,
        expected_baseline_clean, expected_with_llm_total,
        expected_supplement_fields,
    ) = case

    if not inventory_path.exists():
        pytest.skip(f"inventory fixture missing: {inventory_path}")
    if not supplement_path.exists():
        pytest.skip(f"supplement fixture missing: {supplement_path}")

    period = PeriodSpec(period_end=period_end, report_type="annual")

    # Baseline: no LLM
    baseline_dir = tmp_path / f"{company}_baseline"
    ev_baseline = run_company_evaluation(
        company=company, period=period, market=market,
        inventory_path=inventory_path,
        catalog_path=CATALOG, taxonomy_path=TAXONOMY,
        pdf_path=None, llm_config_path=None,
        priorities=("P0", "P1", "P2", "P3"),
        out_dir=baseline_dir,
    )
    assert ev_baseline.by_bucket["clean_present"] == expected_baseline_clean, (
        f"{company} baseline clean drifted: expected {expected_baseline_clean}, "
        f"got {ev_baseline.by_bucket['clean_present']}"
    )
    assert ev_baseline.by_bucket["llm_supplement_present"] == 0

    # With LLM supplement (replayed)
    with_llm_dir = tmp_path / f"{company}_with_llm"
    with_llm_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(supplement_path, with_llm_dir / "llm_evidence_supplement.json")
    ev_with_llm = run_company_evaluation(
        company=company, period=period, market=market,
        inventory_path=inventory_path,
        catalog_path=CATALOG, taxonomy_path=TAXONOMY,
        pdf_path=DUMMY_PDF, llm_config_path=DUMMY_LLM_CONFIG,
        priorities=("P0", "P1", "P2", "P3"),
        out_dir=with_llm_dir,
    )
    clean = ev_with_llm.by_bucket["clean_present"]
    supp = ev_with_llm.by_bucket["llm_supplement_present"]
    assert clean + supp == expected_with_llm_total, (
        f"{company} with-LLM total drifted: expected {expected_with_llm_total}, "
        f"got clean={clean} + supplement={supp}"
    )

    # Lock the exact field set so a regression in catalog or merge logic
    # surfaces named — not just a count drift.
    actual_supp_fields = tuple(
        sorted(
            f.field_id
            for f in ev_with_llm.fields
            if f.bucket == "llm_supplement_present"
        )
    )
    assert actual_supp_fields == expected_supplement_fields, (
        f"{company} supplement field set drifted:\n"
        f"  expected: {expected_supplement_fields}\n"
        f"  actual:   {actual_supp_fields}"
    )
