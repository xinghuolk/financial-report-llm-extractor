import pytest
from decimal import Decimal

from financial_report_llm_extractor.models import (
    Chunk,
    Evidence,
    ExtractedItem,
    ExtractionRun,
    MoneyAmount,
)


def test_present_item_requires_evidence() -> None:
    item = ExtractedItem(field_id="revenue", status="present", value=100)

    with pytest.raises(ValueError, match="must include evidence"):
        item.validate()


def test_present_item_with_evidence_is_valid() -> None:
    item = ExtractedItem(
        field_id="revenue",
        status="present",
        value=100,
        evidence=(
            Evidence(
                page=12,
                chunk_id="p12_t1",
                block_id="p12_t1_r1",
                snippet="Revenue 100",
            ),
        ),
    )

    item.validate()


def test_evidence_requires_page_chunk_block_and_snippet() -> None:
    with pytest.raises(ValueError, match="page must be positive"):
        Evidence(
            page=0,
            chunk_id="c1",
            block_id="b1",
            snippet="Revenue 100",
        ).validate()

    with pytest.raises(ValueError, match="block_id is required"):
        Evidence(
            page=1,
            chunk_id="c1",
            block_id="",
            snippet="Revenue 100",
        ).validate()


def test_money_amount_requires_consistent_normalized_value() -> None:
    money = MoneyAmount(
        value_raw="280,036",
        value=Decimal("280036"),
        currency="HKD",
        unit="HKD million",
        unit_multiplier=Decimal("1000000"),
        normalized_value=Decimal("280036000000"),
        normalized_unit="HKD",
    )

    money.validate()


def test_money_amount_rejects_inconsistent_normalized_value() -> None:
    money = MoneyAmount(
        value_raw="280,036",
        value=Decimal("280036"),
        currency="HKD",
        unit="HKD million",
        unit_multiplier=Decimal("1000000"),
        normalized_value=Decimal("280036"),
        normalized_unit="HKD",
    )

    with pytest.raises(ValueError, match="normalized_value must equal"):
        money.validate()


def test_present_money_item_requires_money_amount() -> None:
    item = ExtractedItem(
        field_id="revenue",
        status="present",
        value_type="money",
        evidence=(
            Evidence(
                page=12,
                chunk_id="c12",
                block_id="b12",
                snippet="Revenue 100",
            ),
        ),
    )

    with pytest.raises(ValueError, match="present money items must include money"):
        item.validate()


def test_ambiguous_money_item_can_omit_money_amount() -> None:
    item = ExtractedItem(field_id="revenue", status="ambiguous", value_type="money")

    item.validate()


def test_chunk_page_range_must_be_ordered() -> None:
    chunk = Chunk(
        chunk_id="stmt_cashflow_p64_p66",
        kind="statement_table",
        page_start=66,
        page_end=64,
        block_ids=("b1",),
    )

    with pytest.raises(ValueError, match="page_start must be <= page_end"):
        chunk.validate()


def test_chunk_requires_block_ids() -> None:
    chunk = Chunk(
        chunk_id="stmt_cashflow_p64_p66",
        kind="statement_table",
        page_start=64,
        page_end=66,
    )

    with pytest.raises(ValueError, match="block_ids is required"):
        chunk.validate()


def test_extraction_run_requires_source_and_versions() -> None:
    run = ExtractionRun(
        source_pdf_hash="",
        parser_version="pdftotext:1",
        chunker_version="v1",
    )

    with pytest.raises(ValueError, match="source_pdf_hash is required"):
        run.validate()
