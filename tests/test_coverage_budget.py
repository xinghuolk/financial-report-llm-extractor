import json
from pathlib import Path

from financial_report_llm_extractor.coverage_budget import (
    build_coverage_metrics,
    load_catalog_field_ids,
)
from financial_report_llm_extractor.coverage_budget import evaluate_coverage_gate
from financial_report_llm_extractor.coverage_budget import write_coverage_budget_report


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


def test_evaluate_coverage_gate_blocks_missing_fields() -> None:
    metrics = [
        {
            "top_k": 3,
            "missing_fields": ["net_profit"],
            "total_candidate_text_chars": 100,
            "fields": [
                {"field_id": "revenue", "candidate_text_chars": 100},
                {"field_id": "net_profit", "candidate_text_chars": 0},
            ],
        }
    ]

    gate = evaluate_coverage_gate(
        metrics,
        required_top_k=3,
        max_total_chars=40_000,
        max_field_chars=8_000,
    )

    assert gate["status"] == "blocked_by_missing_fields"
    assert gate["blockers"] == ["net_profit"]


def test_evaluate_coverage_gate_blocks_empty_field_set() -> None:
    metrics = [
        {
            "top_k": 3,
            "total_fields": 0,
            "missing_fields": [],
            "total_candidate_text_chars": 0,
            "fields": [],
        }
    ]

    gate = evaluate_coverage_gate(
        metrics,
        required_top_k=3,
        max_total_chars=40_000,
        max_field_chars=8_000,
    )

    assert gate["status"] == "blocked_by_missing_fields"
    assert gate["blockers"] == ["__empty_field_set__"]


def test_evaluate_coverage_gate_blocks_missing_evidence_refs() -> None:
    metrics = [
        {
            "top_k": 3,
            "total_fields": 1,
            "missing_fields": [],
            "total_candidate_text_chars": 100,
            "fields": [
                {
                    "field_id": "revenue",
                    "status": "candidates_found",
                    "candidate_text_chars": 100,
                    "top_evidence": {
                        "page": 1,
                        "chunk_id": "page_p0001",
                        "block_id": None,
                        "snippet": "Revenue 100",
                    },
                }
            ],
        }
    ]

    gate = evaluate_coverage_gate(
        metrics,
        required_top_k=3,
        max_total_chars=40_000,
        max_field_chars=8_000,
    )

    assert gate["status"] == "blocked_by_missing_fields"
    assert gate["blockers"] == ["revenue"]


def test_evaluate_coverage_gate_blocks_prompt_budget() -> None:
    metrics = [
        {
            "top_k": 3,
            "missing_fields": [],
            "total_candidate_text_chars": 50_000,
            "fields": [{"field_id": "revenue", "candidate_text_chars": 50_000}],
        }
    ]

    gate = evaluate_coverage_gate(
        metrics,
        required_top_k=3,
        max_total_chars=40_000,
        max_field_chars=8_000,
    )

    assert gate["status"] == "blocked_by_prompt_budget"
    assert gate["blockers"] == ["total_candidate_text_chars", "revenue"]


def test_evaluate_coverage_gate_allows_ready_metrics() -> None:
    metrics = [
        {
            "top_k": 3,
            "total_fields": 1,
            "missing_fields": [],
            "total_candidate_text_chars": 10_000,
            "fields": [
                {
                    "field_id": "revenue",
                    "status": "candidates_found",
                    "candidate_text_chars": 1_000,
                    "top_evidence": {
                        "page": 1,
                        "chunk_id": "page_p0001",
                        "block_id": "p0001_b0001",
                        "snippet": "Revenue 100",
                    },
                }
            ],
        }
    ]

    gate = evaluate_coverage_gate(
        metrics,
        required_top_k=3,
        max_total_chars=40_000,
        max_field_chars=8_000,
    )

    assert gate["status"] == "ready_for_field_scoped_llm_probe"
    assert gate["blockers"] == []


def test_write_coverage_budget_report_writes_json_and_markdown(tmp_path: Path) -> None:
    metrics = [
        {
            "top_k": 3,
            "total_fields": 2,
            "covered_fields": 1,
            "missing_fields": ["net_profit"],
            "coverage_ratio": 0.5,
            "total_candidate_text_chars": 100,
            "rough_token_estimate": 25,
            "fields": [
                {
                    "field_id": "revenue",
                    "status": "candidates_found",
                    "candidate_count": 1,
                    "candidate_text_chars": 100,
                    "top_evidence": {
                        "page": 1,
                        "chunk_id": "page_p0001",
                        "block_id": "p0001_b0001",
                        "snippet": "Revenue 100",
                    },
                },
                {
                    "field_id": "net_profit",
                    "status": "missing",
                    "candidate_count": 0,
                    "candidate_text_chars": 0,
                    "top_evidence": {
                        "page": None,
                        "chunk_id": None,
                        "block_id": None,
                        "snippet": None,
                    },
                },
            ],
        }
    ]
    gate = {
        "status": "blocked_by_missing_fields",
        "required_top_k": 3,
        "max_total_chars": 40_000,
        "max_field_chars": 8_000,
        "blockers": ["net_profit"],
    }

    result = write_coverage_budget_report(
        output_dir=tmp_path,
        report_id="demo_report",
        catalog_id="demo_catalog",
        priorities=("P0", "P1"),
        selected_fields=("revenue", "net_profit"),
        top_k_values=(3,),
        metrics=metrics,
        gate=gate,
    )

    payload = json.loads(result["json"].read_text(encoding="utf-8"))
    assert payload["report_id"] == "demo_report"
    assert payload["gate"]["status"] == "blocked_by_missing_fields"
    markdown = result["markdown"].read_text(encoding="utf-8")
    assert "blocked_by_missing_fields" in markdown
    assert "net_profit" in markdown
    assert "Revenue 100" in markdown
