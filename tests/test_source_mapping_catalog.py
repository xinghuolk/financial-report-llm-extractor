import json
from pathlib import Path
from typing import cast

import pytest

from financial_report_llm_extractor.field_metadata import (
    PRIMARY_ROUTE_MATCHES,
    PrimaryRoute,
    load_coverage_matrix,
    load_field_taxonomy,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingEntry,
    load_source_mapping_catalog,
)
from financial_report_llm_extractor.structured_sources.provider_semantics import (
    load_provider_semantics_catalog,
)


def test_load_source_mapping_catalog_expands_priority_fields(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "catalog_id": "demo",
                "version": "2026-05-01",
                "priorities": [{"priority": "P0", "fields": ["revenue"]}],
                "source_mappings": {
                    "revenue": {
                        "value_type": "money",
                        "statement_type": "income_statement",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "source_aliases": {
                            "akshare": ["营业收入"],
                            "yahoo": ["Total Revenue"],
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    catalog = load_source_mapping_catalog(path, priorities=("P0",))

    assert catalog.catalog_id == "demo"
    assert tuple(catalog.entries) == ("revenue",)
    assert catalog.entries["revenue"].source_aliases["akshare"] == ("营业收入",)


def test_minimal_source_mapping_fixture_loads_core_fields() -> None:
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0",),
    )

    assert "revenue" in catalog.entries
    assert "total_assets" in catalog.entries
    assert catalog.entries["revenue"].source_aliases["akshare"]
    assert catalog.entries["revenue"].source_aliases["yahoo"]


def test_source_mapping_entry_allows_default_unknown_domain_for_in_memory_catalogs() -> None:
    entry = SourceMappingEntry(
        field_id="revenue",
        priority="P0",
        value_type="money",
        statement_type="income_statement",
        currency_requirement="required",
        unit_requirement="required",
        source_aliases={"akshare": ("营业收入",)},
    )

    entry.validate()

    assert entry.domain == "unknown"


def test_source_mapping_catalog_loads_optional_source_policy(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "catalog_id": "test",
                "version": "1",
                "priorities": [{"priority": "P0", "fields": ["net_profit"]}],
                "source_mappings": {
                    "net_profit": {
                        "value_type": "money",
                        "statement_type": "income_statement",
                        "domain": "income_statement",
                        "source_mode": "direct",
                        "primary_route": "akshare_direct",
                        "verification_status": "verified",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "fallback_policy": "pdf_allowed",
                        "source_aliases": {
                            "akshare": [
                                "PARENT_NETPROFIT",
                                "归属于母公司股东的净利润",
                                "NETPROFIT",
                                "净利润",
                            ],
                            "yahoo": ["Net Income"],
                        },
                        "source_policy": {
                            "semantic_concept": (
                                "profit attributable to parent-company shareholders"
                            ),
                            "semantic_variants": {
                                "akshare": {
                                    "primary": [
                                        "PARENT_NETPROFIT",
                                        "归属于母公司股东的净利润",
                                    ],
                                    "related": ["NETPROFIT", "净利润"],
                                },
                                "yahoo": {"primary": ["Net Income"]},
                            },
                            "market_policies": {
                                "CN": {
                                    "primary_route": "akshare_direct",
                                    "cross_check_routes": ["yahoo_direct"],
                                    "on_conflict": "select_primary_require_pdf",
                                    "single_source_requires_pdf": False,
                                }
                            },
                            "verification_requirement": "pdf_required_on_conflict",
                        },
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    catalog = load_source_mapping_catalog(catalog_path, priorities=("P0",))

    policy = catalog.entries["net_profit"].source_policy
    assert policy is not None
    assert (
        policy.semantic_concept
        == "profit attributable to parent-company shareholders"
    )
    assert policy.semantic_variants["akshare"].primary == (
        "PARENT_NETPROFIT",
        "归属于母公司股东的净利润",
    )
    assert policy.semantic_variants["akshare"].related == ("NETPROFIT", "净利润")
    assert policy.market_policies["CN"].on_conflict == "select_primary_require_pdf"


def test_minimal_source_mapping_net_profit_prefers_parent_profit() -> None:
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    entry = catalog.entries["net_profit"]

    assert entry.source_aliases["akshare"][:2] == (
        "PARENT_NETPROFIT",
        "归属于母公司股东的净利润",
    )
    assert "NETPROFIT" in entry.source_aliases["akshare"][2:]
    assert entry.source_policy is not None
    assert (
        entry.source_policy.semantic_concept
        == "profit attributable to parent-company shareholders"
    )
    assert entry.source_aliases["yahoo"] == (
        "Net Income Common Stockholders",
        "Net Income",
        "Net Income From Continuing Operation Net Minority Interest",
    )
    assert entry.source_policy.semantic_variants["yahoo"].primary == (
        "Net Income Common Stockholders",
    )
    assert entry.source_policy.semantic_variants["yahoo"].related == (
        "Net Income",
        "Net Income From Continuing Operation Net Minority Interest",
    )


def test_minimal_source_mapping_net_profit_related_yahoo_rows_are_not_trusted() -> None:
    semantics = load_provider_semantics_catalog(
        Path("field_catalog/provider_raw_semantics_hk.json")
    )

    primary_rule = semantics.require_rule(
        provider="yahoo",
        market="HK",
        turtle_field_id="net_profit",
        raw_field_name="Net Income Common Stockholders",
    )

    assert primary_rule.allowed_as_primary is True
    assert "Net Income" in primary_rule.related_only_fields
    assert (
        "Net Income From Continuing Operation Net Minority Interest"
        in primary_rule.related_only_fields
    )


def test_minimal_source_mapping_gross_profit_is_not_hk_verified_direct() -> None:
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )
    coverage = load_coverage_matrix(
        Path("field_catalog/turtle_v015_coverage_matrix.json")
    )
    semantics = load_provider_semantics_catalog(
        Path("field_catalog/provider_raw_semantics_hk.json")
    )

    entry = catalog.entries["gross_profit"]
    yahoo_rule = semantics.require_rule(
        provider="yahoo",
        market="HK",
        turtle_field_id="gross_profit",
        raw_field_name="Gross Profit",
    )
    akshare_rule = semantics.require_rule(
        provider="akshare",
        market="HK",
        turtle_field_id="gross_profit",
        raw_field_name="毛利",
    )

    assert entry.verification_status == "expected"
    assert coverage.fields["gross_profit"].verification == "expected"
    assert yahoo_rule.allowed_as_primary is False
    assert akshare_rule.allowed_as_primary is False
    assert yahoo_rule.classification == "provider_semantics_unverified"
    assert akshare_rule.classification == "provider_semantics_unverified"


def test_minimal_source_mapping_revenue_declares_operating_revenue_policy() -> None:
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    entry = catalog.entries["revenue"]

    assert entry.source_aliases["akshare"][:2] == ("OPERATE_INCOME", "营业收入")
    assert entry.source_policy is not None
    assert entry.source_policy.semantic_variants["akshare"].related == (
        "TOTAL_OPERATE_INCOME",
        "营业总收入",
    )


@pytest.mark.parametrize("field_id", ["revenue", "net_profit"])
def test_minimal_source_mapping_revenue_and_profit_market_policies(
    field_id: str,
) -> None:
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    policy = catalog.entries[field_id].source_policy
    assert policy is not None
    cn_policy = policy.market_policies["CN"]
    assert cn_policy.primary_route == "akshare_direct"
    assert cn_policy.cross_check_routes == ("yahoo_direct",)
    assert cn_policy.on_conflict == "select_primary_require_pdf"
    assert cn_policy.single_source_requires_pdf is False

    hk_policy = policy.market_policies["HK"]
    assert hk_policy.primary_route == "yahoo_direct"
    assert hk_policy.cross_check_routes == ("akshare_direct",)
    assert hk_policy.on_conflict == "select_primary_require_pdf"
    assert hk_policy.single_source_requires_pdf is True


@pytest.mark.parametrize(
    ("field_id", "expected_hk_primary_route"),
    [
        ("gross_profit", "yahoo_direct"),
        ("total_assets", "yahoo_direct"),
        ("total_cur_assets", "yahoo_direct"),
        ("total_cur_liab", "yahoo_direct"),
        ("total_liabilities", "yahoo_direct"),
    ],
)
def test_minimal_source_mapping_statement_line_market_policies(
    field_id: str,
    expected_hk_primary_route: str,
) -> None:
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    policy = catalog.entries[field_id].source_policy
    assert policy is not None
    hk_policy = policy.market_policies["HK"]
    assert hk_policy.primary_route == expected_hk_primary_route
    expected_cross_check_route = (
        "akshare_direct"
        if expected_hk_primary_route == "yahoo_direct"
        else "yahoo_direct"
    )
    assert hk_policy.cross_check_routes == (expected_cross_check_route,)
    assert hk_policy.on_conflict == "select_primary_require_pdf"
    assert hk_policy.single_source_requires_pdf is (field_id == "gross_profit")

    cn_policy = policy.market_policies["CN"]
    assert cn_policy.primary_route == "akshare_direct"
    assert cn_policy.cross_check_routes == ("yahoo_direct",)
    assert cn_policy.on_conflict == "preserve_conflict"
    assert cn_policy.single_source_requires_pdf is False


@pytest.mark.parametrize(
    ("source_policy", "expected_message"),
    [
        (
            {"semantic_variants": {"akshare": {"primary": "NETPROFIT"}}},
            "source_policy semantic variant primary must be a list",
        ),
        (
            {
                "market_policies": {
                    "CN": {
                        "primary_route": "akshare_direct",
                        "cross_check_routes": "yahoo_direct",
                    }
                }
            },
            "source_policy market policy cross_check_routes must be a list",
        ),
        (
            {
                "market_policies": {
                    "CN": {
                        "primary_route": "akshare_direct",
                        "single_source_requires_pdf": "false",
                    }
                }
            },
            "source_policy market policy single_source_requires_pdf must be a bool",
        ),
        (
            {
                "market_policies": {
                    "CN": {
                        "primary_route": "akshare_direct",
                        "on_conflict": "select_secondary",
                    }
                }
            },
            "source_policy on_conflict has unsupported value: select_secondary",
        ),
        (
            {
                "market_policies": {
                    "CN": {"primary_route": "akshare_lookup"}
                }
            },
            "source_policy primary_route has unsupported value: akshare_lookup",
        ),
        (
            {
                "market_policies": {
                    "CN": {
                        "primary_route": "akshare_direct",
                        "cross_check_routes": ["akshare_lookup"],
                    }
                }
            },
            "source_policy cross_check_route has unsupported value: akshare_lookup",
        ),
        (
            {"verification_requirement": "pdf_always"},
            "source_policy verification_requirement has unsupported value: pdf_always",
        ),
    ],
)
def test_source_mapping_catalog_rejects_invalid_source_policy_metadata(
    tmp_path: Path,
    source_policy: object,
    expected_message: str,
) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "catalog_id": "test",
                "version": "1",
                "priorities": [{"priority": "P0", "fields": ["net_profit"]}],
                "source_mappings": {
                    "net_profit": {
                        "value_type": "money",
                        "statement_type": "income_statement",
                        "domain": "income_statement",
                        "source_mode": "direct",
                        "primary_route": "akshare_direct",
                        "verification_status": "verified",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "fallback_policy": "pdf_allowed",
                        "source_aliases": {"akshare": ["PARENT_NETPROFIT"]},
                        "source_policy": source_policy,
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=expected_message):
        load_source_mapping_catalog(catalog_path, priorities=("P0",))


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        ([], "source mapping catalog must be an object"),
        (
            {
                "catalog_id": "demo",
                "version": "2026-05-01",
                "priorities": {},
                "source_mappings": {},
            },
            "source mapping priorities must be a list",
        ),
        (
            {
                "catalog_id": "demo",
                "version": "2026-05-01",
                "priorities": ["P0"],
                "source_mappings": {},
            },
            "source mapping priority entry must be an object",
        ),
        (
            {
                "catalog_id": "demo",
                "version": "2026-05-01",
                "priorities": [{"priority": "P0", "fields": {}}],
                "source_mappings": {},
            },
            "source mapping priority fields must be a list",
        ),
        (
            {
                "catalog_id": "demo",
                "version": "2026-05-01",
                "priorities": [{"priority": "P0", "fields": ["revenue"]}],
                "source_mappings": [],
            },
            "source_mappings must be an object",
        ),
        (
            {
                "catalog_id": "demo",
                "version": "2026-05-01",
                "priorities": [{"priority": "P0", "fields": ["revenue"]}],
                "source_mappings": {"revenue": []},
            },
            "source mapping entry must be an object",
        ),
        (
            {
                "catalog_id": "demo",
                "version": "2026-05-01",
                "priorities": [{"priority": "P0", "fields": ["revenue"]}],
                "source_mappings": {
                    "revenue": {
                        "value_type": "money",
                        "statement_type": "income_statement",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "source_aliases": [],
                    }
                },
            },
            "source_aliases must be an object",
        ),
        (
            {
                "catalog_id": "demo",
                "version": "2026-05-01",
                "priorities": [{"priority": "P0", "fields": ["revenue"]}],
                "source_mappings": {
                    "revenue": {
                        "value_type": "money",
                        "statement_type": "income_statement",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "source_aliases": {"akshare": "营业收入"},
                    }
                },
            },
            "source alias values must be a list",
        ),
    ],
)
def test_source_mapping_catalog_rejects_malformed_shapes(
    tmp_path: Path,
    payload: object,
    expected_message: str,
) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=expected_message):
        load_source_mapping_catalog(path, priorities=("P0",))


def test_referenced_source_mapping_requires_explicit_selected_metadata(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "catalog_id": "demo",
                "version": "2026-05-01",
                "taxonomy_catalog": "turtle_v015_field_taxonomy",
                "coverage_matrix": "turtle_v015_coverage_matrix",
                "priorities": [{"priority": "P0", "fields": ["revenue"]}],
                "source_mappings": {
                    "revenue": {
                        "value_type": "money",
                        "statement_type": "income_statement",
                        "source_mode": "direct",
                        "verification_status": "verified",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "fallback_policy": "pdf_allowed",
                        "source_aliases": {"akshare": ["营业收入"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="revenue: domain is required in referenced source mapping catalog",
    ):
        load_source_mapping_catalog(path, priorities=("P0",))


def test_referenced_source_mapping_requires_explicit_selected_route_metadata(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "catalog_id": "demo",
                "version": "2026-05-01",
                "taxonomy_catalog": "turtle_v015_field_taxonomy",
                "coverage_matrix": "turtle_v015_coverage_matrix",
                "priorities": [{"priority": "P0", "fields": ["revenue"]}],
                "source_mappings": {
                    "revenue": {
                        "value_type": "money",
                        "statement_type": "income_statement",
                        "domain": "income_statement",
                        "source_mode": "direct",
                        "verification_status": "verified",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "fallback_policy": "pdf_allowed",
                        "source_aliases": {"akshare": ["营业收入"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="revenue: primary_route is required in referenced source mapping catalog",
    ):
        load_source_mapping_catalog(path, priorities=("P0",))


def test_referenced_source_mapping_rejects_unknown_domain(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "catalog_id": "demo",
                "version": "2026-05-01",
                "taxonomy_catalog": "turtle_v015_field_taxonomy",
                "coverage_matrix": "turtle_v015_coverage_matrix",
                "priorities": [{"priority": "P0", "fields": ["revenue"]}],
                "source_mappings": {
                    "revenue": {
                        "value_type": "money",
                        "statement_type": "income_statement",
                        "domain": "unknown",
                        "source_mode": "direct",
                        "primary_route": "akshare_direct",
                        "verification_status": "verified",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "fallback_policy": "pdf_allowed",
                        "source_aliases": {"akshare": ["营业收入"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="domain has unsupported value: unknown"):
        load_source_mapping_catalog(path, priorities=("P0",))


@pytest.mark.parametrize(
    ("metadata_key", "metadata_value", "message"),
    [
        ("value_type", "currency", "invalid value_type has unsupported value: currency"),
        (
            "statement_type",
            "profit_statement",
            "invalid statement_type has unsupported value: profit_statement",
        ),
        ("domain", "equity", "domain has unsupported value: equity"),
        ("source_mode", "driect", "source_mode has unsupported value: driect"),
        (
            "primary_route",
            "akshare_lookup",
            "invalid primary_route has unsupported value: akshare_lookup",
        ),
        (
            "verification_status",
            "confirmed",
            "invalid verification_status has unsupported value: confirmed",
        ),
        (
            "currency_requirement",
            "mandatory",
            "currency_requirement has unsupported value: mandatory",
        ),
        (
            "unit_requirement",
            "mandatory",
            "unit_requirement has unsupported value: mandatory",
        ),
        (
            "fallback_policy",
            "silent_default",
            "invalid fallback_policy has unsupported value: silent_default",
        ),
    ],
)
def test_source_mapping_rejects_invalid_metadata_literals(
    tmp_path: Path,
    metadata_key: str,
    metadata_value: str,
    message: str,
) -> None:
    path = tmp_path / "catalog.json"
    mapping = {
        "value_type": "money",
        "statement_type": "income_statement",
        "domain": "income_statement",
        "source_mode": "direct",
        "primary_route": "akshare_direct",
        "verification_status": "verified",
        "currency_requirement": "required",
        "unit_requirement": "required",
        "fallback_policy": "pdf_allowed",
        "source_aliases": {"akshare": ["营业收入"]},
    }
    mapping[metadata_key] = metadata_value
    path.write_text(
        json.dumps(
            {
                "catalog_id": "demo",
                "version": "2026-05-01",
                "priorities": [{"priority": "P0", "fields": ["revenue"]}],
                "source_mappings": {"revenue": mapping},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        load_source_mapping_catalog(path, priorities=("P0",))


def test_minimal_source_mapping_fixture_includes_akshare_field_codes() -> None:
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    assert "TOTAL_ASSETS" in catalog.entries["total_assets"].source_aliases["akshare"]
    assert (
        "TOTAL_LIABILITIES"
        in catalog.entries["total_liabilities"].source_aliases["akshare"]
    )
    assert "MONETARYFUNDS" in catalog.entries["cash"].source_aliases["akshare"]
    assert (
        "NETCASH_OPERATE"
        in catalog.entries["operating_cash_flow"].source_aliases["akshare"]
    )


def test_minimal_source_mapping_includes_first_candidate_promotions() -> None:
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    assert catalog.entries["bond_payable"].source_aliases["akshare"] == (
        "BOND_PAYABLE",
    )
    assert catalog.entries["cip"].source_aliases["akshare"] == ("CIP",)
    assert catalog.entries["defer_tax_liab"].source_aliases["akshare"] == (
        "DEFER_TAX_LIAB",
    )
    assert catalog.entries["financing_cash_flow"].source_aliases["yahoo"] == (
        "Financing Cash Flow",
    )
    assert catalog.entries["financing_cash_flow"].primary_route == "yahoo_direct"
    assert set(catalog.entries["financing_cash_flow"].source_aliases) == {"yahoo"}
    assert catalog.entries["invest_income"].source_aliases["akshare"] == (
        "INVEST_INCOME",
    )
    assert catalog.entries["investing_cash_flow"].source_aliases["yahoo"] == (
        "Investing Cash Flow",
    )
    assert catalog.entries["investing_cash_flow"].primary_route == "yahoo_direct"
    assert set(catalog.entries["investing_cash_flow"].source_aliases) == {"yahoo"}


def test_minimal_source_mapping_references_taxonomy_and_coverage() -> None:
    taxonomy = load_field_taxonomy(
        Path("field_catalog/turtle_v015_field_taxonomy.json")
    )
    coverage = load_coverage_matrix(
        Path("field_catalog/turtle_v015_coverage_matrix.json")
    )
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    revenue = catalog.entries["revenue"]

    assert revenue.domain == taxonomy.fields["revenue"].domain
    assert revenue.source_mode == taxonomy.fields["revenue"].source_mode
    assert revenue.primary_route == coverage.fields["revenue"].primary_route
    assert revenue.verification_status in {"verified", "expected", "unknown"}


def test_source_policy_routes_are_advertised_by_coverage_matrix() -> None:
    coverage = load_coverage_matrix(
        Path("field_catalog/turtle_v015_coverage_matrix.json")
    )
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    for field_id, entry in catalog.entries.items():
        if entry.source_policy is None:
            continue
        coverage_routes = {
            (route.source, route.mode)
            for route in coverage.fields[field_id].routes
        }
        for market_policy in entry.source_policy.market_policies.values():
            route_ids = (
                market_policy.primary_route,
                *market_policy.cross_check_routes,
            )
            for route_id in route_ids:
                assert route_id in PRIMARY_ROUTE_MATCHES
                expected_route = PRIMARY_ROUTE_MATCHES[
                    cast(PrimaryRoute, route_id)
                ]
                assert expected_route in coverage_routes, (
                    f"{field_id} source_policy route {route_id} is missing from "
                    "coverage routes"
                )


def test_minimal_source_mapping_defer_tax_liab_has_yahoo_alias_and_hk_policy() -> None:
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    entry = catalog.entries["defer_tax_liab"]

    assert "Non Current Deferred Taxes Liabilities" in entry.source_aliases["yahoo"]
    assert entry.verification_status == "verified"
    assert entry.source_policy is not None
    assert entry.source_policy.market_policies["HK"].primary_route == "yahoo_direct"


def test_minimal_source_mapping_entries_match_taxonomy_and_coverage() -> None:
    taxonomy = load_field_taxonomy(
        Path("field_catalog/turtle_v015_field_taxonomy.json")
    )
    coverage = load_coverage_matrix(
        Path("field_catalog/turtle_v015_coverage_matrix.json")
    )
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    for field_id, entry in catalog.entries.items():
        taxonomy_entry = taxonomy.fields[field_id]
        coverage_entry = coverage.fields[field_id]
        assert entry.domain == taxonomy_entry.domain
        assert entry.source_mode == taxonomy_entry.source_mode
        assert entry.primary_route == coverage_entry.primary_route
        assert entry.verification_status == coverage_entry.verification
        if taxonomy_entry.statement_type != "mixed":
            assert entry.statement_type == taxonomy_entry.statement_type
        assert entry.source_mode not in {"pdf_only", "llm_review"}
