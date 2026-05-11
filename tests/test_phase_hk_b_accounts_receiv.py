"""Phase HK-B.3 / HK-B.8: lock HK accounts_receiv post-promotion shape.

HK-B.3 initially locked accounts_receiv at 6/6 unresolved_conflict. HK-B.8
PDF spot-check across all 6 HK issuers then confirmed Yahoo HK
`Accounts Receivable` = PDF pure Trade receivables (using each issuer's
preferred terminology: 'Trade receivables' / 'Debtors' for HK property cos
/ 'Accounts receivable, net' for Yum China). All 6 PDF samples are recorded
in `hk_yahoo_trust_policy.json` under `accounts_receiv` with multi-currency
support, and the source mapping now carries an HK market policy
(`primary_route: yahoo_direct`) so the Yahoo candidate is selected and
trust-policy-cleared into `clean_present` for every HK issuer.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from financial_report_llm_extractor.structured_sources.artifacts import (
    read_source_inventory,
    write_source_inventory,
)
from financial_report_llm_extractor.structured_sources.company_evaluation import (
    run_company_evaluation,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceInventoryRecord,
)
from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
    PeriodSpec,
    select_records_for_period,
)


REPO = Path(__file__).resolve().parent.parent
CATALOG = REPO / "field_catalog" / "turtle_v015_source_mapping_minimal.json"
TAXONOMY = REPO / "field_catalog" / "turtle_v015_field_taxonomy.json"
BASELINE_FIXTURE = (
    REPO
    / "tests"
    / "fixtures"
    / "provider_captures"
    / "provider_field_baseline"
    / "source_inventory.jsonl.gz"
)
HK_LLM_6_FIXTURE = (
    REPO
    / "tests"
    / "fixtures"
    / "provider_captures"
    / "provider_field_baseline_hk_llm_6_extension"
)


CASES = [
    # Phase HK-B.8: accounts_receiv promoted to clean_present for all 6 HK
    # issuers via multi-currency trust rule. PDF spot-check confirmed Yahoo
    # 'Accounts Receivable' = PDF pure Trade Receivables (HK: 'Debtors' for
    # property cos; Yum China: 'Accounts receivable, net'). AKShare 应收帐款
    # conflicts (broader scope) are resolved by selecting Yahoo as primary.
    (
        "00001",
        date(2025, 12, 31),
        BASELINE_FIXTURE,
        "clean_present",
        "yahoo",
        Decimal("14952000000.0"),
        (("akshare", "38212528540.0"), ("yahoo", "14952000000.0")),
    ),
    (
        "01113",
        date(2025, 12, 31),
        BASELINE_FIXTURE,
        "clean_present",
        "yahoo",
        Decimal("2028000000.0"),
        (("akshare", "6755182380.0"), ("yahoo", "2028000000.0")),
    ),
    (
        "01810",
        date(2024, 12, 31),
        HK_LLM_6_FIXTURE / "01810" / "source_inventory.jsonl.gz",
        "clean_present",
        "yahoo",
        Decimal("12662060000.0"),
        (("akshare", "14588579000.0"), ("yahoo", "12662060000.0")),
    ),
    (
        "02498",
        date(2024, 12, 31),
        HK_LLM_6_FIXTURE / "02498" / "source_inventory.jsonl.gz",
        "clean_present",
        "yahoo",
        Decimal("410611000.0"),
        (("akshare", "462189000.0"), ("yahoo", "410611000.0")),
    ),
    (
        "06862",
        date(2024, 12, 31),
        HK_LLM_6_FIXTURE / "06862" / "source_inventory.jsonl.gz",
        "clean_present",
        "yahoo",
        Decimal("346347000.0"),
        (("akshare", "1517431000.0"), ("yahoo", "346347000.0")),
    ),
    (
        "09987",
        date(2024, 12, 31),
        HK_LLM_6_FIXTURE / "09987" / "source_inventory.jsonl.gz",
        "clean_present",
        "yahoo",
        Decimal("79000000.0"),
        (("akshare", "567883600.0"), ("yahoo", "79000000.0")),
    ),
]


def _inventory_for_company(
    source_path: Path,
    *,
    company: str,
    period: PeriodSpec,
    tmp_path: Path,
) -> Path:
    records = read_source_inventory(source_path)
    yahoo_ticker = f"{(company.lstrip('0') or '0').zfill(4)}.HK"
    filtered: tuple[SourceInventoryRecord, ...] = tuple(
        record
        for record in records
        if record.ticker in {company, yahoo_ticker}
    )
    assert filtered, f"fixture {source_path} has no records for {company}"
    filtered = select_records_for_period(filtered, period)
    out = tmp_path / company / "source_inventory.jsonl"
    write_source_inventory(out, filtered)
    return out


@pytest.mark.parametrize("case", CASES, ids=[case[0] for case in CASES])
def test_hk_b_accounts_receiv_shape_is_locked(
    case: tuple,
    tmp_path: Path,
) -> None:
    (
        company,
        period_end,
        source_inventory,
        expected_bucket,
        expected_selected_source,
        expected_value,
        expected_candidate_values,
    ) = case

    period = PeriodSpec(period_end=period_end, report_type="annual")
    inventory_path = _inventory_for_company(
        source_inventory,
        company=company,
        period=period,
        tmp_path=tmp_path,
    )
    evaluation = run_company_evaluation(
        company=company,
        period=period,
        market="HK",
        inventory_path=inventory_path,
        inventory_summary_path=None,
        catalog_path=CATALOG,
        taxonomy_path=TAXONOMY,
        pdf_path=None,
        llm_config_path=None,
        priorities=("P0", "P1", "P2", "P3"),
        out_dir=tmp_path / company / "evaluation",
    )
    field = next(f for f in evaluation.fields if f.field_id == "accounts_receiv")

    assert field.bucket == expected_bucket
    assert field.selected_source == expected_selected_source
    assert field.value == expected_value

    mapping_path = tmp_path / company / "evaluation" / "turtle_mapping.json"
    mapping = __import__("json").loads(mapping_path.read_text(encoding="utf-8"))
    candidates = tuple(
        (candidate["source"], candidate["normalized_value"])
        for candidate in mapping["fields"]["accounts_receiv"]["candidates"]
    )
    assert candidates == expected_candidate_values
