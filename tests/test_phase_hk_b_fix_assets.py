"""Phase HK-B.2: lock HK fix_assets conflict shape.

The 6-HK recon shows `fix_assets` has issuer-dependent semantics:
three issuers are clean via Yahoo Net PPE and three remain material
AKShare/Yahoo conflicts. This test locks that shape from persisted provider
fixtures so later source-policy work cannot silently promote conflict cases
where Net PPE may include right-of-use assets or other scope differences.
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
    # Phase HK-B.6: fix_assets multi-currency trust rule promotes 4 of 6 HK
    # issuers (00001/01113/06862/09987) where Yahoo Net PPE = PDF PP&E +
    # Right-of-use assets within rounding. 01810/02498 stay clean via the
    # single-source path (AKShare returns None for 固定资产 on these issuers)
    # but are explicitly excluded from the trust-policy allowlist due to
    # material PDF-vs-Yahoo discrepancies (01810: -22%, 02498: 2.9%).
    (
        "00001",
        date(2025, 12, 31),
        BASELINE_FIXTURE,
        "clean_present",
        "yahoo",
        Decimal("159240000000.0"),
        (("akshare", "90394257600.0"), ("yahoo", "159240000000.0")),
    ),
    (
        "01113",
        date(2025, 12, 31),
        BASELINE_FIXTURE,
        "clean_present",
        "yahoo",
        Decimal("72868000000.0"),
        (("akshare", "65815834960.0"), ("yahoo", "72868000000.0")),
    ),
    (
        "01810",
        date(2024, 12, 31),
        HK_LLM_6_FIXTURE / "01810" / "source_inventory.jsonl.gz",
        "clean_present",
        "yahoo",
        Decimal("24588261000.0"),
        (("yahoo", "24588261000.0"),),
    ),
    (
        "02498",
        date(2024, 12, 31),
        HK_LLM_6_FIXTURE / "02498" / "source_inventory.jsonl.gz",
        "clean_present",
        "yahoo",
        Decimal("321863000.0"),
        (("yahoo", "321863000.0"),),
    ),
    (
        "06862",
        date(2024, 12, 31),
        HK_LLM_6_FIXTURE / "06862" / "source_inventory.jsonl.gz",
        "clean_present",
        "yahoo",
        Decimal("6338547000.0"),
        (("yahoo", "6338547000.0"),),
    ),
    (
        "09987",
        date(2024, 12, 31),
        HK_LLM_6_FIXTURE / "09987" / "source_inventory.jsonl.gz",
        "clean_present",
        "yahoo",
        Decimal("4580000000.0"),
        (("akshare", "17302478800.0"), ("yahoo", "4580000000.0")),
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
def test_hk_b_fix_assets_shape_is_locked(
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
    field = next(f for f in evaluation.fields if f.field_id == "fix_assets")

    assert field.bucket == expected_bucket
    assert field.selected_source == expected_selected_source
    assert field.value == expected_value

    mapping_path = tmp_path / company / "evaluation" / "turtle_mapping.json"
    mapping = __import__("json").loads(mapping_path.read_text(encoding="utf-8"))
    candidates = tuple(
        (candidate["source"], candidate["normalized_value"])
        for candidate in mapping["fields"]["fix_assets"]["candidates"]
    )
    assert candidates == expected_candidate_values
