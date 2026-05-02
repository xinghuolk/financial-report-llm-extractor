import json
from pathlib import Path

import pytest

from financial_report_llm_extractor.field_metadata import (
    load_field_taxonomy,
    validate_taxonomy_against_priority_catalog,
)


def test_load_field_taxonomy_reads_field_metadata(tmp_path: Path) -> None:
    taxonomy_path = tmp_path / "taxonomy.json"
    taxonomy_path.write_text(
        json.dumps(
            {
                "catalog_id": "demo_taxonomy",
                "version": "2026-05-02",
                "source_priority_catalog": "demo_priority",
                "fields": {
                    "revenue": {
                        "priority": "P0",
                        "domain": "income_statement",
                        "statement_type": "income_statement",
                        "value_type": "money",
                        "source_mode": "direct",
                        "period_type": "duration",
                        "scope_expectation": "consolidated",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "evidence_requirement": "source_only_allowed",
                        "fallback_policy": "pdf_allowed",
                        "description": "Revenue from contracts or operations.",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    taxonomy = load_field_taxonomy(taxonomy_path)

    assert taxonomy.catalog_id == "demo_taxonomy"
    assert taxonomy.fields["revenue"].domain == "income_statement"
    assert taxonomy.fields["revenue"].source_mode == "direct"


def test_taxonomy_validation_requires_exact_priority_catalog_coverage(
    tmp_path: Path,
) -> None:
    priority_path = tmp_path / "priority.json"
    priority_path.write_text(
        json.dumps(
            {
                "catalog_id": "priority",
                "version": "2026-05-02",
                "priorities": [
                    {"priority": "P0", "fields": ["revenue", "net_profit"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    taxonomy_path = tmp_path / "taxonomy.json"
    taxonomy_path.write_text(
        json.dumps(
            {
                "catalog_id": "taxonomy",
                "version": "2026-05-02",
                "source_priority_catalog": "priority",
                "fields": {
                    "revenue": {
                        "priority": "P0",
                        "domain": "income_statement",
                        "statement_type": "income_statement",
                        "value_type": "money",
                        "source_mode": "direct",
                        "period_type": "duration",
                        "scope_expectation": "consolidated",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "evidence_requirement": "source_only_allowed",
                        "fallback_policy": "pdf_allowed",
                        "description": "Revenue.",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    taxonomy = load_field_taxonomy(taxonomy_path)

    with pytest.raises(ValueError, match="missing taxonomy fields"):
        validate_taxonomy_against_priority_catalog(taxonomy, priority_path)


def test_taxonomy_validation_rejects_priority_mismatch(tmp_path: Path) -> None:
    priority_path = tmp_path / "priority.json"
    priority_path.write_text(
        json.dumps(
            {
                "catalog_id": "priority",
                "version": "2026-05-02",
                "priorities": [{"priority": "P0", "fields": ["revenue"]}],
            }
        ),
        encoding="utf-8",
    )
    taxonomy_path = tmp_path / "taxonomy.json"
    taxonomy_path.write_text(
        json.dumps(
            {
                "catalog_id": "taxonomy",
                "version": "2026-05-02",
                "source_priority_catalog": "priority",
                "fields": {
                    "revenue": {
                        "priority": "P1",
                        "domain": "income_statement",
                        "statement_type": "income_statement",
                        "value_type": "money",
                        "source_mode": "direct",
                        "period_type": "duration",
                        "scope_expectation": "consolidated",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "evidence_requirement": "source_only_allowed",
                        "fallback_policy": "pdf_allowed",
                        "description": "Revenue.",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    taxonomy = load_field_taxonomy(taxonomy_path)

    with pytest.raises(ValueError, match="priority mismatch"):
        validate_taxonomy_against_priority_catalog(taxonomy, priority_path)


def test_taxonomy_validation_rejects_duplicate_priority_catalog_fields(
    tmp_path: Path,
) -> None:
    priority_path = tmp_path / "priority.json"
    priority_path.write_text(
        json.dumps(
            {
                "catalog_id": "priority",
                "version": "2026-05-02",
                "priorities": [
                    {"priority": "P0", "fields": ["revenue"]},
                    {"priority": "P1", "fields": ["revenue"]},
                ],
            }
        ),
        encoding="utf-8",
    )
    taxonomy_path = tmp_path / "taxonomy.json"
    taxonomy_path.write_text(
        json.dumps(
            {
                "catalog_id": "taxonomy",
                "version": "2026-05-02",
                "source_priority_catalog": "priority",
                "fields": {
                    "revenue": {
                        "priority": "P0",
                        "domain": "income_statement",
                        "statement_type": "income_statement",
                        "value_type": "money",
                        "source_mode": "direct",
                        "period_type": "duration",
                        "scope_expectation": "consolidated",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "evidence_requirement": "source_only_allowed",
                        "fallback_policy": "pdf_allowed",
                        "description": "Revenue.",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    taxonomy = load_field_taxonomy(taxonomy_path)

    with pytest.raises(ValueError, match="duplicate priority catalog fields"):
        validate_taxonomy_against_priority_catalog(taxonomy, priority_path)


def test_taxonomy_validation_requires_source_priority_catalog_id_match(
    tmp_path: Path,
) -> None:
    priority_path = tmp_path / "priority.json"
    priority_path.write_text(
        json.dumps(
            {
                "catalog_id": "priority",
                "version": "2026-05-02",
                "priorities": [{"priority": "P0", "fields": ["revenue"]}],
            }
        ),
        encoding="utf-8",
    )
    taxonomy_path = tmp_path / "taxonomy.json"
    taxonomy_path.write_text(
        json.dumps(
            {
                "catalog_id": "taxonomy",
                "version": "2026-05-02",
                "source_priority_catalog": "different_priority",
                "fields": {
                    "revenue": {
                        "priority": "P0",
                        "domain": "income_statement",
                        "statement_type": "income_statement",
                        "value_type": "money",
                        "source_mode": "direct",
                        "period_type": "duration",
                        "scope_expectation": "consolidated",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "evidence_requirement": "source_only_allowed",
                        "fallback_policy": "pdf_allowed",
                        "description": "Revenue.",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    taxonomy = load_field_taxonomy(taxonomy_path)

    with pytest.raises(ValueError, match="source_priority_catalog mismatch"):
        validate_taxonomy_against_priority_catalog(taxonomy, priority_path)
