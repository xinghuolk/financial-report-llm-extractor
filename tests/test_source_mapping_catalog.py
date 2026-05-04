import json
from pathlib import Path

import pytest

from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingEntry,
    load_source_mapping_catalog,
)
from financial_report_llm_extractor.field_metadata import (
    load_coverage_matrix,
    load_field_taxonomy,
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
    assert catalog.entries["invest_income"].source_aliases["akshare"] == (
        "INVEST_INCOME",
    )
    assert catalog.entries["investing_cash_flow"].source_aliases["yahoo"] == (
        "Investing Cash Flow",
    )


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
        expected_primary_route = coverage_entry.primary_route
        if field_id in {"financing_cash_flow", "investing_cash_flow"}:
            expected_primary_route = "yahoo_direct"
        assert entry.domain == taxonomy_entry.domain
        assert entry.source_mode == taxonomy_entry.source_mode
        assert entry.primary_route == expected_primary_route
        assert entry.verification_status == coverage_entry.verification
        if taxonomy_entry.statement_type != "mixed":
            assert entry.statement_type == taxonomy_entry.statement_type
        assert entry.source_mode not in {"pdf_only", "llm_review"}
