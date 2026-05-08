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


def test_map_source_inventory_marks_hk_akshare_statement_metadata_as_proven() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "total_assets": _entry(
                "total_assets",
                statement_type="balance_sheet",
                source_aliases={"akshare": ("资产总计",)},
            )
        },
    )
    records = [
        SourceInventoryRecord(
            source="akshare",
            market="HK",
            ticker="00001",
            statement_type="balance_sheet",
            period="2025-12-31",
            raw_field_name="资产总计",
            raw_value="100",
            parsed_numeric_value=Decimal("100"),
            report_type="annual",
            account_standard="HKFRS",
            currency="HKD",
            unit="million",
            scope="consolidated",
            source_evidence=(
                SourceEvidence(
                    source="akshare",
                    adapter="akshare",
                    function="fixture",
                    artifact_id="akshare_hk_balance_sheet",
                    raw_record_id="akshare:total_assets",
                    raw_field_name="资产总计",
                ),
            ),
        )
    ]

    result = map_source_inventory(catalog, records)

    candidate = result.fields["total_assets"].candidates[0]
    assert candidate.statement_metadata_proven is True
    assert candidate.to_dict()["statement_metadata_proven"] is True


def test_map_source_inventory_proves_hk_akshare_annual_raw_metadata() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "total_assets": _entry(
                "total_assets",
                statement_type="balance_sheet",
                source_aliases={"akshare": ("资产总计",)},
            )
        },
    )
    records = [
        SourceInventoryRecord(
            source="akshare",
            market="HK",
            ticker="00001",
            statement_type="balance_sheet",
            period="2025-12-31",
            raw_field_name="资产总计",
            raw_value="100",
            parsed_numeric_value=Decimal("100"),
            report_type="annual",
            account_standard="HKFRS",
            currency="HKD",
            unit="raw",
            scope="consolidated",
            source_evidence=(_source_evidence("akshare", "资产总计"),),
        )
    ]

    result = map_source_inventory(catalog, records)

    candidate = result.fields["total_assets"].candidates[0]
    assert candidate.statement_metadata_proven is True
    assert candidate.unit_multiplier == Decimal("1")
    assert candidate.currency_proof_source == "akshare_statement_metadata"
    assert candidate.unit_proof_source == "source_unit:raw"
    assert candidate.reporting_metadata_proof_source == "akshare_hk_metadata_join"
    payload = candidate.to_dict()
    assert payload["unit_multiplier"] == "1"
    assert payload["currency_proof_source"] == "akshare_statement_metadata"
    assert payload["unit_proof_source"] == "source_unit:raw"
    assert payload["reporting_metadata_proof_source"] == "akshare_hk_metadata_join"


def test_map_source_inventory_proves_hk_yahoo_annual_raw_metadata() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "total_assets": _entry(
                "total_assets",
                statement_type="balance_sheet",
                source_aliases={"yahoo": ("Total Assets",)},
            )
        },
    )
    records = [
        SourceInventoryRecord(
            source="yahoo",
            market="HK",
            ticker="00001.HK",
            statement_type="balance_sheet",
            period="2025-12-31",
            raw_field_name="Total Assets",
            raw_value="100",
            parsed_numeric_value=Decimal("100"),
            report_type="annual",
            currency="HKD",
            unit="raw",
            scope="consolidated",
            source_evidence=(_source_evidence("yahoo", "Total Assets"),),
        )
    ]

    result = map_source_inventory(catalog, records)

    candidate = result.fields["total_assets"].candidates[0]
    assert candidate.statement_metadata_proven is True
    assert candidate.unit_multiplier == Decimal("1")
    assert candidate.currency_proof_source == "yahoo_statement_metadata"
    assert candidate.unit_proof_source == "source_unit:raw"
    assert candidate.reporting_metadata_proof_source == "yahoo_annual_statement"


def test_map_source_inventory_keeps_hk_akshare_currency_unit_metadata_unproven() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "total_assets": _entry(
                "total_assets",
                statement_type="balance_sheet",
                source_aliases={"akshare": ("资产总计",)},
            )
        },
    )
    records = [
        SourceInventoryRecord(
            source="akshare",
            market="HK",
            ticker="00001",
            statement_type="balance_sheet",
            period="2025-12-31",
            raw_field_name="资产总计",
            raw_value="100",
            parsed_numeric_value=Decimal("100"),
            report_type="annual",
            account_standard="HKFRS",
            currency="HKD",
            unit="HKD",
            scope="consolidated",
            source_evidence=(_source_evidence("akshare", "资产总计"),),
        )
    ]

    result = map_source_inventory(catalog, records)

    candidate = result.fields["total_assets"].candidates[0]
    assert candidate.statement_metadata_proven is False
    assert candidate.unit_multiplier == Decimal("1")
    assert candidate.unit_proof_source == "invalid_currency_as_unit"


def test_map_source_inventory_suppresses_metadata_proof_when_source_record_invalid() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "total_assets": _entry(
                "total_assets",
                statement_type="balance_sheet",
                source_aliases={"akshare": ("资产总计",)},
            )
        },
    )
    records = [
        SourceInventoryRecord(
            source="akshare",
            market="HK",
            ticker="00001",
            statement_type="balance_sheet",
            period="2025-12-31",
            raw_field_name="资产总计",
            raw_value="100",
            parsed_numeric_value=Decimal("100"),
            report_type="annual",
            account_standard="HKFRS",
            currency="HKD",
            unit="raw",
            scope="consolidated",
            source_evidence=(),
        )
    ]

    result = map_source_inventory(catalog, records)

    mapped = result.fields["total_assets"]
    assert mapped.status == "blocked"
    candidate = mapped.candidates[0]
    assert candidate.errors == ("present source records require source_evidence",)
    assert candidate.statement_metadata_proven is False
    assert candidate.currency_proof_source is None
    assert candidate.unit_proof_source is None
    assert candidate.reporting_metadata_proof_source is None


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
    assert net_profit.value == Decimal("82320067101.68")
    assert net_profit.source_evidence[0].raw_field_code == "PARENT_NETPROFIT"


def test_map_source_inventory_preserves_related_policy_evidence_candidates() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "revenue": _entry(
                "revenue",
                statement_type="income_statement",
                source_aliases={
                    "akshare": (
                        "OPERATE_INCOME",
                        "营业收入",
                        "TOTAL_OPERATE_INCOME",
                        "营业总收入",
                    ),
                    "yahoo": ("Total Revenue",),
                },
            )
        },
    )
    records = (
        _record(
            "营业收入",
            "168838102514.79",
            Decimal("168838102514.79"),
            raw_field_code="OPERATE_INCOME",
        ),
        _record(
            "营业总收入",
            "172054171890.91",
            Decimal("172054171890.91"),
            raw_field_code="TOTAL_OPERATE_INCOME",
        ),
        _record(
            "Total Revenue",
            "172054171890.91",
            Decimal("172054171890.91"),
            source="yahoo",
            raw_field_code=None,
        ),
    )

    result = map_source_inventory(catalog, records)

    mapped = result.fields["revenue"]
    assert mapped.status == "ambiguous"
    assert [candidate.raw_field_code for candidate in mapped.candidates] == [
        "OPERATE_INCOME",
        None,
    ]
    assert [
        candidate.raw_field_code
        for candidate in mapped.policy_evidence_candidates
    ] == ["TOTAL_OPERATE_INCOME"]


def test_minimal_hk_net_profit_keeps_related_yahoo_rows_as_policy_evidence() -> None:
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )
    records = (
        _record(
            "Net Income Common Stockholders",
            "10847000000",
            Decimal("10847000000"),
            source="yahoo",
            raw_field_code=None,
        ),
        _record(
            "Net Income",
            "11133000000",
            Decimal("11133000000"),
            source="yahoo",
            raw_field_code=None,
        ),
        _record(
            "Net Income From Continuing Operation Net Minority Interest",
            "11133000000",
            Decimal("11133000000"),
            source="yahoo",
            raw_field_code=None,
        ),
    )

    result = map_source_inventory(catalog, records)

    mapped = result.fields["net_profit"]
    assert mapped.status == "present"
    assert [candidate.raw_field_name for candidate in mapped.candidates] == [
        "Net Income Common Stockholders"
    ]
    assert [
        candidate.raw_field_name for candidate in mapped.policy_evidence_candidates
    ] == [
        "Net Income",
        "Net Income From Continuing Operation Net Minority Interest",
    ]


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
    assert mapped.unit == "CNY"
    assert mapped.canonical_unit == "CNY"


def test_map_source_inventory_derives_mixed_provider_scales_in_canonical_scale() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "total_assets": _entry(
                "total_assets",
                statement_type="balance_sheet",
                source_aliases={"yahoo": ("Total Assets",)},
            ),
            "total_liabilities": _entry(
                "total_liabilities",
                statement_type="balance_sheet",
                source_aliases={"yahoo": ("Total Liabilities",)},
            ),
            "equity": _entry(
                "equity",
                statement_type="balance_sheet",
                source_aliases={"yahoo": ("Stockholders Equity",)},
                derivation="total_assets - total_liabilities",
            ),
        },
    )
    records = [
        SourceInventoryRecord(
            source="yahoo",
            market="HK",
            ticker="00001.HK",
            statement_type="balance_sheet",
            period="2024-12-31",
            raw_field_name="Total Assets",
            raw_value="100",
            parsed_numeric_value=Decimal("100"),
            currency="HKD",
            unit="million",
            scope="consolidated",
            source_evidence=(
                SourceEvidence(
                    source="yahoo",
                    adapter="yahoo",
                    function="fixture",
                    artifact_id="yahoo_artifact",
                    raw_record_id="yahoo:Total Assets",
                    raw_field_name="Total Assets",
                ),
            ),
        ),
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
    assert mapped.status == "derived"
    assert mapped.value == Decimal("99999600")
    assert mapped.normalized_value == Decimal("99999600")
    assert mapped.unit == "HKD"
    assert mapped.canonical_unit == "HKD"


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


def test_map_source_inventory_reports_period_mismatch_before_canonical_unit_mismatch() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "total_assets": _entry(
                "total_assets",
                statement_type="balance_sheet",
                source_aliases={"yahoo": ("Total Assets",)},
            ),
            "total_liabilities": _entry(
                "total_liabilities",
                statement_type="balance_sheet",
                source_aliases={"yahoo": ("Total Liabilities",)},
            ),
            "equity": _entry(
                "equity",
                statement_type="balance_sheet",
                source_aliases={"yahoo": ("Stockholders Equity",)},
                derivation="total_assets - total_liabilities",
            ),
        },
    )
    records = [
        SourceInventoryRecord(
            source="yahoo",
            market="US",
            ticker="TEST",
            statement_type="balance_sheet",
            period="2024-12-31",
            raw_field_name="Total Assets",
            raw_value="1000",
            parsed_numeric_value=Decimal("1000"),
            currency="USD",
            unit="raw",
            scope="consolidated",
            source_evidence=(
                SourceEvidence(
                    source="yahoo",
                    adapter="yahoo",
                    function="fixture",
                    artifact_id="yahoo_artifact",
                    raw_record_id="yahoo:Total Assets",
                    raw_field_name="Total Assets",
                ),
            ),
        ),
        SourceInventoryRecord(
            source="yahoo",
            market="US",
            ticker="TEST",
            statement_type="balance_sheet",
            period="2025-12-31",
            raw_field_name="Total Liabilities",
            raw_value="400",
            parsed_numeric_value=Decimal("400"),
            currency="USD",
            unit="CNY",
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
    assert mapped.errors == ("derivation inputs use different periods",)


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
    assert candidate.statement_metadata_proven is False

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
    assert candidate_with_errors.statement_metadata_proven is False


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


def test_null_record_with_null_means_zero_produces_present_zero_field() -> None:
    """null_means_zero=True causes null AKShare value to map to clean zero."""
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "st_borr": SourceMappingEntry(
                field_id="st_borr",
                priority="P0",
                value_type="money",
                statement_type="balance_sheet",
                currency_requirement="required",
                unit_requirement="required",
                source_aliases={"akshare": ("SHORT_LOAN",)},
                null_means_zero=True,
            )
        },
    )
    null_record = SourceInventoryRecord(
        source="akshare",
        ticker="600519",
        market="CN",
        statement_type="balance_sheet",
        period="2025-12-31",
        scope="consolidated",
        raw_field_name="SHORT_LOAN",
        raw_field_code="SHORT_LOAN",
        raw_value=None,
        parsed_numeric_value=None,
        currency="CNY",
        unit="yuan",
        source_evidence=(
            SourceEvidence(
                source="akshare",
                adapter="akshare",
                function="stock_balance_sheet_by_report_em",
                artifact_id="akshare_cn_600519_balance_sheet",
                raw_record_id="600519:CN:balance_sheet:2025-12-31:SHORT_LOAN",
                raw_field_name="SHORT_LOAN",
                raw_field_code="SHORT_LOAN",
            ),
        ),
    )

    result = map_source_inventory(catalog, [null_record])

    mapped = result.fields["st_borr"]
    assert mapped.status == "present"
    assert mapped.value == Decimal("0")
    assert mapped.normalized_value == Decimal("0")
    assert mapped.currency == "CNY"
    assert mapped.unit == "yuan"
    assert len(mapped.candidates) == 1
    candidate = mapped.candidates[0]
    assert candidate.errors == ()
    assert candidate.value == Decimal("0")
    assert candidate.normalized_value == Decimal("0")
    # Audit trail must reach both candidate and mapped field
    assert candidate.review_notes == ("null_interpreted_as_zero",)
    assert mapped.review_notes == ("null_interpreted_as_zero",)


def test_null_record_without_null_means_zero_is_blocked() -> None:
    """null_means_zero=False (default) causes null AKShare value to block."""
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "st_borr": SourceMappingEntry(
                field_id="st_borr",
                priority="P0",
                value_type="money",
                statement_type="balance_sheet",
                currency_requirement="required",
                unit_requirement="required",
                source_aliases={"akshare": ("SHORT_LOAN",)},
                null_means_zero=False,
            )
        },
    )
    null_record = SourceInventoryRecord(
        source="akshare",
        ticker="600519",
        market="CN",
        statement_type="balance_sheet",
        period="2025-12-31",
        scope="consolidated",
        raw_field_name="SHORT_LOAN",
        raw_field_code="SHORT_LOAN",
        raw_value=None,
        parsed_numeric_value=None,
        currency="CNY",
        unit="yuan",
        source_evidence=(
            SourceEvidence(
                source="akshare",
                adapter="akshare",
                function="stock_balance_sheet_by_report_em",
                artifact_id="akshare_cn_600519_balance_sheet",
                raw_record_id="600519:CN:balance_sheet:2025-12-31:SHORT_LOAN",
                raw_field_name="SHORT_LOAN",
                raw_field_code="SHORT_LOAN",
            ),
        ),
    )

    result = map_source_inventory(catalog, [null_record])

    mapped = result.fields["st_borr"]
    assert mapped.status == "blocked"
    assert len(mapped.candidates) == 1
    assert mapped.candidates[0].errors != ()


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
    raw_field_code: str | None = None,
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
        raw_field_code=raw_field_code,
        scope="consolidated",
        source_evidence=(
            SourceEvidence(
                source=source,  # type: ignore[arg-type]
                adapter=source,
                function="fixture",
                artifact_id=f"{source}_artifact",
                raw_record_id=f"{source}:{raw_field_name}",
                raw_field_name=raw_field_name,
                raw_field_code=raw_field_code,
            ),
        ),
    )


def _source_evidence(source: str, raw_field_name: str) -> SourceEvidence:
    return SourceEvidence(
        source=source,  # type: ignore[arg-type]
        adapter=source,
        function="fixture",
        artifact_id=f"{source}_artifact",
        raw_record_id=f"{source}:{raw_field_name}",
        raw_field_name=raw_field_name,
    )
