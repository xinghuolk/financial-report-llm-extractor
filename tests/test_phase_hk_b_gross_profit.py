"""Phase HK-B.4: lock HK gross_profit non-clean shape.

The 6-HK recon shows `gross_profit` must remain conservative: four issuers
still have AKShare/Yahoo normalized-value conflicts and two exact provider-
provider matches still land in terminal_unverified because HK gross-profit
provider semantics are not proven. This test locks that non-clean shape so
provider-provider agreement alone cannot become a clean promotion.
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
    # company, period_end, inventory fixture, expected bucket, selected source,
    # expected value, candidate normalized values.
    (
        "00001",
        date(2025, 12, 31),
        BASELINE_FIXTURE,
        "clean_present",
        "yahoo",
        Decimal("139204000000.0"),
        (("akshare", "141671863440.0"), ("yahoo", "139204000000.0")),
    ),
    (
        "01113",
        date(2025, 12, 31),
        BASELINE_FIXTURE,
        "clean_present",
        "yahoo",
        Decimal("25558000000.0"),
        (("akshare", "23084496760.0"), ("yahoo", "25558000000.0")),
    ),
    (
        "01810",
        date(2024, 12, 31),
        HK_LLM_6_FIXTURE / "01810" / "source_inventory.jsonl.gz",
        "clean_present",
        "yahoo",
        Decimal("76560194000.0"),
        (("akshare", "76560194000.0"), ("yahoo", "76560194000.0")),
    ),
    (
        "02498",
        date(2024, 12, 31),
        HK_LLM_6_FIXTURE / "02498" / "source_inventory.jsonl.gz",
        "clean_present",
        "yahoo",
        Decimal("283553000.0"),
        (("akshare", "283553000.0"), ("yahoo", "283553000.0")),
    ),
    (
        "06862",
        date(2024, 12, 31),
        HK_LLM_6_FIXTURE / "06862" / "source_inventory.jsonl.gz",
        "clean_present",
        "yahoo",
        Decimal("12108412000.0"),
        (("akshare", "26543610000.0"), ("yahoo", "12108412000.0")),
    ),
    (
        "09987",
        date(2024, 12, 31),
        HK_LLM_6_FIXTURE / "09987" / "source_inventory.jsonl.gz",
        "clean_present",
        "yahoo",
        Decimal("1890000000.0"),
        (("akshare", "16756160400.0"), ("yahoo", "1890000000.0")),
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
def test_hk_b_gross_profit_standardized_shape_is_locked(
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
    field = next(f for f in evaluation.fields if f.field_id == "gross_profit")

    # Operator decision 2026-06-12 (supersedes the HK-B non-clean lock):
    # gross_profit for HK reporters is a standardized derivation — Yahoo's
    # value is ACCEPTED as clean_present with provenance labeling
    # (select_primary_standardized + yahoo_standardized_accepted), because
    # it matches the PDF-disclosed Gross profit EXACTLY where checkable
    # (01810 FY2024 three-way match, pinned below). Divergent candidates
    # stay visible in turtle_mapping for audit.
    assert field.bucket == "clean_present"
    assert field.bucket == expected_bucket
    assert field.selected_source == expected_selected_source
    assert field.value == expected_value

    mapping_path = tmp_path / company / "evaluation" / "turtle_mapping.json"
    mapping = __import__("json").loads(mapping_path.read_text(encoding="utf-8"))
    candidates = tuple(
        (candidate["source"], candidate["normalized_value"])
        for candidate in mapping["fields"]["gross_profit"]["candidates"]
    )
    assert candidates == expected_candidate_values
