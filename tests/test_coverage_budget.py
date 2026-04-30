import json
from pathlib import Path

from financial_report_llm_extractor.coverage_budget import (
    build_coverage_metrics,
    load_catalog_field_ids,
)


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


def test_build_coverage_metrics_reports_missing_and_prompt_chars() -> None:
    records = [
        {
            "record_type": "chunk",
            "chunk_id": "page_p0001",
            "kind": "page_text",
            "statement_kind": None,
            "page_start": 1,
            "page_end": 1,
            "block_ids": ["p0001_b0001"],
            "block_texts": {"p0001_b0001": "Revenue 2025 HK$ million 100 2024 90"},
            "text": "Revenue 2025 HK$ million 100 2024 90",
        }
    ]

    metrics = build_coverage_metrics(
        records,
        selected_fields=("revenue", "net_profit"),
        top_k_values=(1, 3),
    )

    first = metrics[0]
    assert first["top_k"] == 1
    assert first["total_fields"] == 2
    assert first["covered_fields"] == 1
    assert first["missing_fields"] == ["net_profit"]
    assert first["coverage_ratio"] == 0.5
    assert first["total_candidate_text_chars"] > 0
    assert first["rough_token_estimate"] > 0
    fields = {field["field_id"]: field for field in first["fields"]}
    assert fields["revenue"]["status"] == "candidates_found"
    assert fields["revenue"]["candidate_count"] == 1
    assert fields["revenue"]["top_evidence"]["block_id"] == "p0001_b0001"
    assert fields["net_profit"]["status"] == "missing"
