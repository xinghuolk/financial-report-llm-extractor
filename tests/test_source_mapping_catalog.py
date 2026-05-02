import json
from pathlib import Path

from financial_report_llm_extractor.structured_sources.catalog import (
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
        assert entry.domain == taxonomy_entry.domain
        assert entry.source_mode == taxonomy_entry.source_mode
        assert entry.primary_route == coverage_entry.primary_route
        assert entry.verification_status == coverage_entry.verification
        if taxonomy_entry.statement_type != "mixed":
            assert entry.statement_type == taxonomy_entry.statement_type
        assert entry.source_mode not in {"pdf_only", "llm_review"}
