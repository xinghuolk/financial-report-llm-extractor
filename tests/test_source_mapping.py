from decimal import Decimal
import json
from pathlib import Path

from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
    SourceMappingEntry,
    load_source_mapping_catalog,
)
from financial_report_llm_extractor.structured_sources.artifacts import (
    read_source_inventory,
)
from financial_report_llm_extractor.structured_sources.mapping import (
    map_source_inventory,
    TurtleMappingCandidate,
    write_turtle_mapping_artifacts,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
)


def test_map_source_inventory_maps_present_money_field() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "revenue": _entry(
                "revenue",
                source_aliases={"akshare": ("营业收入",)},
            )
        },
    )
    records = [_record("营业收入", "100", Decimal("100"))]

    result = map_source_inventory(catalog, records)

    mapped = result.fields["revenue"]
    assert mapped.status == "present"
    assert len(mapped.candidates) == 1
    assert mapped.candidates[0].normalized_value == Decimal("100")
    assert mapped.candidates[0].currency == "CNY"
    assert mapped.candidates[0].unit == "yuan"
    assert mapped.source_evidence[0].raw_field_name == "营业收入"


def test_map_source_inventory_preserves_provider_unit_and_adds_canonical_unit() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "cash": _entry(
                "cash",
                statement_type="balance_sheet",
                source_aliases={"yahoo": ("Cash And Cash Equivalents",)},
            )
        },
    )
    records = [
        SourceInventoryRecord(
            source="yahoo",
            market="CN",
            ticker="600519.SS",
            statement_type="balance_sheet",
            period="2025-12-31",
            raw_field_name="Cash And Cash Equivalents",
            raw_value="51690610946.5",
            parsed_numeric_value=Decimal("51690610946.5"),
            currency="CNY",
            unit="raw",
            scope="consolidated",
            source_evidence=(
                SourceEvidence(
                    source="yahoo",
                    adapter="yahoo",
                    function="fixture",
                    artifact_id="yahoo_cn_600519_ss_balance_sheet",
                    raw_record_id="cash",
                    raw_field_name="Cash And Cash Equivalents",
                ),
            ),
        )
    ]

    result = map_source_inventory(catalog, records)

    mapped = result.fields["cash"]
    assert mapped.status == "present"
    assert mapped.unit == "raw"
    assert mapped.canonical_unit == "CNY"
    assert mapped.candidates[0].unit == "raw"
    assert mapped.candidates[0].canonical_unit == "CNY"


def test_map_source_inventory_marks_missing_field() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "revenue": _entry(
                "revenue",
                source_aliases={"akshare": ("营业收入",)},
            )
        },
    )

    result = map_source_inventory(catalog, [])

    mapped = result.fields["revenue"]
    assert mapped.status == "missing"
    assert mapped.candidates == ()
    assert mapped.errors == ("no source candidates matched catalog aliases",)


def test_map_source_inventory_blocks_when_matched_candidate_fails_normalization() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "revenue": _entry(
                "revenue",
                source_aliases={"akshare": ("营业收入",)},
            )
        },
    )
    records = [_record("营业收入", "-", Decimal("0"))]

    result = map_source_inventory(catalog, records)

    mapped = result.fields["revenue"]
    assert mapped.status == "blocked"
    assert len(mapped.candidates) == 1
    assert mapped.candidates[0].errors == ("missing numeric value",)
    assert mapped.errors == ("matched source candidates failed validation or normalization",)


def test_map_source_inventory_marks_multiple_candidates_ambiguous() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "revenue": _entry(
                "revenue",
                source_aliases={
                    "akshare": ("营业收入",),
                    "yahoo": ("Total Revenue",),
                },
            )
        },
    )
    records = [
        _record("营业收入", "100", Decimal("100"), source="akshare"),
        _record("Total Revenue", "101", Decimal("101"), source="yahoo"),
    ]

    result = map_source_inventory(catalog, records)

    mapped = result.fields["revenue"]
    assert mapped.status == "ambiguous"
    assert len(mapped.candidates) == 2
    assert mapped.errors == ("multiple source candidates matched catalog aliases",)


def test_map_source_inventory_uses_catalog_alias_order_for_same_source_candidates() -> None:
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )
    records = read_source_inventory(
        Path("tests/fixtures/akshare/600519_income_statement_2025_required_fields.jsonl")
    )

    result = map_source_inventory(catalog, records)

    revenue = result.fields["revenue"]
    assert revenue.status == "present"
    assert revenue.value == Decimal("168838102514.79")
    assert revenue.source_evidence[0].raw_field_code == "OPERATE_INCOME"
    net_profit = result.fields["net_profit"]
    assert net_profit.status == "present"
    assert net_profit.value == Decimal("85310324833.67")
    assert net_profit.source_evidence[0].raw_field_code == "NETPROFIT"


def test_map_source_inventory_derives_money_field_from_compatible_inputs() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "total_assets": _entry(
                "total_assets",
                statement_type="balance_sheet",
                source_aliases={"akshare": ("资产总计",)},
            ),
            "total_liabilities": _entry(
                "total_liabilities",
                statement_type="balance_sheet",
                source_aliases={"akshare": ("负债合计",)},
            ),
            "equity": _entry(
                "equity",
                statement_type="balance_sheet",
                source_aliases={"akshare": ("所有者权益合计",)},
                derivation="total_assets - total_liabilities",
            ),
        },
    )
    records = [
        _record("资产总计", "1000", Decimal("1000"), statement_type="balance_sheet"),
        _record("负债合计", "400", Decimal("400"), statement_type="balance_sheet"),
    ]

    result = map_source_inventory(catalog, records)

    mapped = result.fields["equity"]
    assert mapped.status == "derived"
    assert mapped.value == Decimal("600")
    assert mapped.currency == "CNY"
    assert mapped.unit == "yuan"
    assert mapped.canonical_unit == "CNY"
    assert mapped.derived_from == ("total_assets", "total_liabilities")
    assert len(mapped.source_evidence) == 2


def test_map_source_inventory_derives_when_provider_units_differ_but_canonical_units_match() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "total_assets": _entry(
                "total_assets",
                statement_type="balance_sheet",
                source_aliases={"akshare": ("资产总计",)},
            ),
            "total_liabilities": _entry(
                "total_liabilities",
                statement_type="balance_sheet",
                source_aliases={"yahoo": ("Total Liabilities",)},
            ),
            "equity": _entry(
                "equity",
                statement_type="balance_sheet",
                source_aliases={"akshare": ("所有者权益合计",)},
                derivation="total_assets - total_liabilities",
            ),
        },
    )
    records = [
        _record("资产总计", "1000", Decimal("1000"), statement_type="balance_sheet"),
        SourceInventoryRecord(
            source="yahoo",
            market="CN",
            ticker="600519.SS",
            statement_type="balance_sheet",
            period="2024-12-31",
            raw_field_name="Total Liabilities",
            raw_value="400",
            parsed_numeric_value=Decimal("400"),
            currency="CNY",
            unit="raw",
            scope="consolidated",
            source_evidence=(
                SourceEvidence(
                    source="yahoo",
                    adapter="yahoo",
                    function="fixture",
                    artifact_id="yahoo_artifact",
                    raw_record_id="yahoo:Total Liabilities",
                    raw_field_name="Total Liabilities",
                ),
            ),
        ),
    ]

    result = map_source_inventory(catalog, records)

    mapped = result.fields["equity"]
    assert mapped.status == "derived"
    assert mapped.value == Decimal("600")
    assert mapped.unit == "yuan"
    assert mapped.canonical_unit == "CNY"


def test_map_source_inventory_blocks_derivation_when_currencies_differ() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "total_assets": _entry(
                "total_assets",
                statement_type="balance_sheet",
                source_aliases={"akshare": ("资产总计",)},
            ),
            "total_liabilities": _entry(
                "total_liabilities",
                statement_type="balance_sheet",
                source_aliases={"yahoo": ("Total Liabilities",)},
            ),
            "equity": _entry(
                "equity",
                statement_type="balance_sheet",
                source_aliases={"akshare": ("所有者权益合计",)},
                derivation="total_assets - total_liabilities",
            ),
        },
    )
    records = [
        _record("资产总计", "1000", Decimal("1000"), statement_type="balance_sheet"),
        SourceInventoryRecord(
            source="yahoo",
            market="HK",
            ticker="00001.HK",
            statement_type="balance_sheet",
            period="2024-12-31",
            raw_field_name="Total Liabilities",
            raw_value="400",
            parsed_numeric_value=Decimal("400"),
            currency="HKD",
            unit="raw",
            scope="consolidated",
            source_evidence=(
                SourceEvidence(
                    source="yahoo",
                    adapter="yahoo",
                    function="fixture",
                    artifact_id="yahoo_artifact",
                    raw_record_id="yahoo:Total Liabilities",
                    raw_field_name="Total Liabilities",
                ),
            ),
        ),
    ]

    result = map_source_inventory(catalog, records)

    mapped = result.fields["equity"]
    assert mapped.status == "blocked"
    assert mapped.errors == ("derivation inputs use different currencies",)


def test_turtle_mapping_candidate_preserves_old_positional_constructor_shape() -> None:
    evidence = SourceEvidence(
        source="akshare",
        adapter="akshare",
        function="fixture",
        artifact_id="akshare_artifact",
        raw_record_id="akshare:revenue",
        raw_field_name="Revenue",
    )

    candidate = TurtleMappingCandidate(
        "akshare",
        "Revenue",
        None,
        "100",
        Decimal("100"),
        Decimal("100"),
        "CNY",
        "yuan",
        "2024-12-31",
        "consolidated",
        (evidence,),
    )

    assert candidate.period == "2024-12-31"
    assert candidate.scope == "consolidated"
    assert candidate.source_evidence == (evidence,)
    assert candidate.canonical_unit is None

    candidate_with_errors = TurtleMappingCandidate(
        "akshare",
        "Revenue",
        None,
        "100",
        Decimal("100"),
        Decimal("100"),
        "CNY",
        "yuan",
        "2024-12-31",
        "consolidated",
        (evidence,),
        ("bad",),
    )

    assert candidate_with_errors.errors == ("bad",)
    assert candidate_with_errors.canonical_unit is None


def test_write_turtle_mapping_artifacts_writes_json_and_markdown(
    tmp_path: Path,
) -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "revenue": _entry(
                "revenue",
                source_aliases={"akshare": ("营业收入",)},
            ),
            "net_profit": _entry(
                "net_profit",
                source_aliases={"akshare": ("净利润",)},
            ),
        },
    )
    result = map_source_inventory(catalog, [_record("营业收入", "100", Decimal("100"))])

    paths = write_turtle_mapping_artifacts(result, tmp_path)

    assert paths["mapping"].name == "turtle_mapping.json"
    assert paths["coverage_json"].name == "source_coverage_summary.json"
    assert paths["coverage_markdown"].name == "source_coverage_summary.md"

    mapping_payload = json.loads(paths["mapping"].read_text(encoding="utf-8"))
    summary_payload = json.loads(paths["coverage_json"].read_text(encoding="utf-8"))
    markdown = paths["coverage_markdown"].read_text(encoding="utf-8")

    assert mapping_payload["fields"]["revenue"]["status"] == "present"
    assert summary_payload["total_fields"] == 2
    assert summary_payload["status_counts"] == {"missing": 1, "present": 1}
    assert summary_payload["blocker_fields"] == {
        "missing": ["net_profit"],
        "ambiguous": [],
    }
    assert "| status | count |" in markdown
    assert "- missing: net_profit" in markdown


def _entry(
    field_id: str,
    *,
    statement_type: str = "income_statement",
    source_aliases: dict[str, tuple[str, ...]],
    derivation: str | None = None,
) -> SourceMappingEntry:
    return SourceMappingEntry(
        field_id=field_id,
        priority="P0",
        value_type="money",
        statement_type=statement_type,
        currency_requirement="required",
        unit_requirement="required",
        source_aliases=source_aliases,
        derivation=derivation,
    )


def _record(
    raw_field_name: str,
    raw_value: str,
    parsed_value: Decimal,
    *,
    source: str = "akshare",
    statement_type: str = "income_statement",
) -> SourceInventoryRecord:
    return SourceInventoryRecord(
        source=source,  # type: ignore[arg-type]
        market="CN" if source == "akshare" else "US",
        ticker="600519" if source == "akshare" else "600519.SS",
        statement_type=statement_type,
        period="2024-12-31",
        raw_field_name=raw_field_name,
        raw_value=raw_value,
        parsed_numeric_value=parsed_value,
        currency="CNY",
        unit="yuan",
        scope="consolidated",
        source_evidence=(
            SourceEvidence(
                source=source,  # type: ignore[arg-type]
                adapter=source,
                function="fixture",
                artifact_id=f"{source}_artifact",
                raw_record_id=f"{source}:{raw_field_name}",
                raw_field_name=raw_field_name,
            ),
        ),
    )
