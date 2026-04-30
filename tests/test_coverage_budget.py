import json
from pathlib import Path

from financial_report_llm_extractor.coverage_budget import load_catalog_field_ids


def test_load_catalog_field_ids_reads_priorities(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "catalog_id": "demo",
                "version": "2026-04-30",
                "priorities": [
                    {"priority": "P0", "fields": ["revenue", "net_profit"]},
                    {"priority": "P1", "fields": ["cash"]},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert load_catalog_field_ids(catalog_path, priorities=("P0",)) == (
        "revenue",
        "net_profit",
    )
    assert load_catalog_field_ids(catalog_path, priorities=("P0", "P1")) == (
        "revenue",
        "net_profit",
        "cash",
    )


def test_load_catalog_field_ids_uses_explicit_fields(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps({"catalog_id": "demo", "version": "2026-04-30", "priorities": []}),
        encoding="utf-8",
    )

    assert load_catalog_field_ids(
        catalog_path,
        priorities=("P0",),
        explicit_fields=("cash", "revenue"),
    ) == ("cash", "revenue")
