import json
from pathlib import Path

from financial_report_llm_extractor.structured_sources.catalog import (
    load_source_mapping_catalog,
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
