import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from financial_report_llm_extractor.field_metadata import (
    CoverageMatrix,
    FieldTaxonomyCatalog,
    load_field_taxonomy,
    load_coverage_matrix,
    summarize_coverage_matrix,
    validate_coverage_matrix_against_taxonomy,
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


def test_field_taxonomy_rejects_invalid_value_type(tmp_path: Path) -> None:
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
                        "value_type": "mony",
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

    with pytest.raises(ValueError, match="invalid value_type"):
        load_field_taxonomy(taxonomy_path)


def test_field_taxonomy_rejects_empty_fields(tmp_path: Path) -> None:
    taxonomy_path = tmp_path / "taxonomy.json"
    taxonomy_path.write_text(
        json.dumps(
            {
                "catalog_id": "demo_taxonomy",
                "version": "2026-05-02",
                "source_priority_catalog": "demo_priority",
                "fields": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="fields is required"):
        load_field_taxonomy(taxonomy_path)


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        ([], "taxonomy catalog must be an object"),
        (
            {
                "catalog_id": "demo_taxonomy",
                "version": "2026-05-02",
                "source_priority_catalog": "demo_priority",
                "fields": [],
            },
            "taxonomy fields must be an object",
        ),
        (
            {
                "catalog_id": "demo_taxonomy",
                "version": "2026-05-02",
                "source_priority_catalog": "demo_priority",
                "fields": {"revenue": []},
            },
            "taxonomy field entry must be an object",
        ),
    ],
)
def test_field_taxonomy_rejects_malformed_shapes(
    tmp_path: Path,
    payload: object,
    expected_message: str,
) -> None:
    taxonomy_path = tmp_path / "taxonomy.json"
    taxonomy_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=expected_message):
        load_field_taxonomy(taxonomy_path)


def test_field_taxonomy_rejects_missing_required_field_metadata(
    tmp_path: Path,
) -> None:
    taxonomy_path = tmp_path / "taxonomy.json"
    taxonomy_path.write_text(
        json.dumps(
            {
                "catalog_id": "demo_taxonomy",
                "version": "2026-05-02",
                "source_priority_catalog": "demo_priority",
                "fields": {
                    "revenue": {
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

    with pytest.raises(ValueError, match="priority is required"):
        load_field_taxonomy(taxonomy_path)


def test_load_coverage_matrix_reads_routes(tmp_path: Path) -> None:
    path = tmp_path / "coverage.json"
    path.write_text(
        json.dumps(
            {
                "matrix_id": "demo_coverage",
                "version": "2026-05-02",
                "taxonomy_catalog": "demo_taxonomy",
                "fields": {
                    "revenue": {
                        "domain": "income_statement",
                        "priority": "P0",
                        "primary_route": "akshare_direct",
                        "verification": "verified",
                        "routes": [
                            {
                                "source": "akshare",
                                "mode": "direct",
                                "status": "verified",
                                "statement_type": "income_statement",
                                "evidence_requirement": "source_only_allowed",
                            }
                        ],
                        "notes": "Verified by captured AKShare fixture.",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    matrix = load_coverage_matrix(path)

    assert matrix.matrix_id == "demo_coverage"
    assert matrix.fields["revenue"].primary_route == "akshare_direct"
    assert matrix.fields["revenue"].verification == "verified"
    assert matrix.fields["revenue"].routes[0].status == "verified"


def test_coverage_matrix_rejects_empty_fields(tmp_path: Path) -> None:
    path = tmp_path / "coverage.json"
    path.write_text(
        json.dumps(
            {
                "matrix_id": "demo_coverage",
                "version": "2026-05-02",
                "taxonomy_catalog": "demo_taxonomy",
                "fields": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="coverage fields are required"):
        load_coverage_matrix(path)


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        ([], "coverage matrix must be an object"),
        ("not an object", "coverage matrix must be an object"),
        (
            {
                "matrix_id": "demo_coverage",
                "version": "2026-05-02",
                "taxonomy_catalog": "demo_taxonomy",
                "fields": [],
            },
            "coverage fields must be an object",
        ),
    ],
)
def test_coverage_matrix_rejects_malformed_top_level_shapes(
    tmp_path: Path,
    payload: object,
    expected_message: str,
) -> None:
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=expected_message):
        load_coverage_matrix(path)


@pytest.mark.parametrize("entry_payload", ["not an object", []])
def test_coverage_matrix_rejects_malformed_field_entry_shapes(
    tmp_path: Path,
    entry_payload: object,
) -> None:
    data = _coverage_matrix_payload()
    data["fields"]["revenue"] = entry_payload
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="coverage field entry must be an object"):
        load_coverage_matrix(path)


def test_coverage_matrix_rejects_malformed_routes_shape(tmp_path: Path) -> None:
    data = _coverage_matrix_payload()
    data["fields"]["revenue"]["routes"] = {}
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="coverage routes must be a list"):
        load_coverage_matrix(path)


@pytest.mark.parametrize("route_payload", ["not an object", []])
def test_coverage_matrix_rejects_malformed_route_shapes(
    tmp_path: Path,
    route_payload: object,
) -> None:
    data = _coverage_matrix_payload()
    data["fields"]["revenue"]["routes"] = [route_payload]
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="coverage route must be an object"):
        load_coverage_matrix(path)


@pytest.mark.parametrize(
    ("missing_key", "expected_message"),
    [
        ("matrix_id", "matrix_id is required"),
        ("version", "version is required"),
        ("taxonomy_catalog", "taxonomy_catalog is required"),
    ],
)
def test_coverage_matrix_rejects_missing_top_level_fields(
    tmp_path: Path,
    missing_key: str,
    expected_message: str,
) -> None:
    data = {
        "matrix_id": "demo_coverage",
        "version": "2026-05-02",
        "taxonomy_catalog": "demo_taxonomy",
        "fields": {
            "revenue": {
                "domain": "income_statement",
                "priority": "P0",
                "primary_route": "akshare_direct",
                "verification": "verified",
                "notes": "Verified by captured AKShare fixture.",
                "routes": [
                    {
                        "source": "akshare",
                        "mode": "direct",
                        "status": "verified",
                        "statement_type": "income_statement",
                        "evidence_requirement": "source_only_allowed",
                    }
                ],
            }
        },
    }
    data.pop(missing_key)
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match=expected_message):
        load_coverage_matrix(path)


def test_coverage_matrix_rejects_missing_entry_notes(tmp_path: Path) -> None:
    data = _coverage_matrix_payload()
    data["fields"]["revenue"].pop("notes")
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="notes are required"):
        load_coverage_matrix(path)


@pytest.mark.parametrize(
    ("missing_key", "expected_message"),
    [
        ("domain", "domain is required"),
        ("priority", "priority is required"),
        ("primary_route", "primary_route is required"),
        ("verification", "verification is required"),
        ("routes", "coverage routes are required"),
    ],
)
def test_coverage_matrix_rejects_missing_entry_fields(
    tmp_path: Path,
    missing_key: str,
    expected_message: str,
) -> None:
    data = _coverage_matrix_payload()
    data["fields"]["revenue"].pop(missing_key)
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match=expected_message):
        load_coverage_matrix(path)


@pytest.mark.parametrize(
    ("missing_key", "expected_message"),
    [
        ("source", "source is required"),
        ("mode", "mode is required"),
        ("status", "status is required"),
        ("statement_type", "statement_type is required"),
        ("evidence_requirement", "evidence_requirement is required"),
    ],
)
def test_coverage_matrix_rejects_missing_route_fields(
    tmp_path: Path,
    missing_key: str,
    expected_message: str,
) -> None:
    data = _coverage_matrix_payload()
    data["fields"]["revenue"]["routes"][0].pop(missing_key)
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match=expected_message):
        load_coverage_matrix(path)


@pytest.mark.parametrize(
    ("field_name", "bad_value", "expected_message"),
    [
        ("source", "wind", "invalid source"),
        ("mode", "lookup", "invalid mode"),
        ("status", "confirmed", "invalid status"),
        ("statement_type", "income_statment", "invalid statement_type"),
        ("evidence_requirement", "none", "invalid evidence_requirement"),
    ],
)
def test_coverage_matrix_rejects_invalid_route_vocabulary(
    tmp_path: Path,
    field_name: str,
    bad_value: str,
    expected_message: str,
) -> None:
    data = _coverage_matrix_payload()
    data["fields"]["revenue"]["routes"][0][field_name] = bad_value
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match=expected_message):
        load_coverage_matrix(path)


@pytest.mark.parametrize(
    ("field_name", "bad_value", "expected_message"),
    [
        ("primary_route", "akshare_lookup", "invalid primary_route"),
        ("verification", "confirmed", "invalid verification"),
    ],
)
def test_coverage_matrix_rejects_invalid_entry_vocabulary(
    tmp_path: Path,
    field_name: str,
    bad_value: str,
    expected_message: str,
) -> None:
    data = _coverage_matrix_payload()
    data["fields"]["revenue"][field_name] = bad_value
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match=expected_message):
        load_coverage_matrix(path)


def test_coverage_matrix_rejects_primary_route_without_matching_route(
    tmp_path: Path,
) -> None:
    path = tmp_path / "coverage.json"
    path.write_text(
        json.dumps(
            {
                "matrix_id": "demo_coverage",
                "version": "2026-05-02",
                "taxonomy_catalog": "demo_taxonomy",
                "fields": {
                    "revenue": {
                        "domain": "income_statement",
                        "priority": "P0",
                        "primary_route": "akshare_direct",
                        "verification": "expected",
                        "notes": "Expected source route coverage.",
                        "routes": [
                            {
                                "source": "pdf",
                                "mode": "evidence",
                                "status": "expected",
                                "statement_type": "income_statement",
                                "evidence_requirement": "pdf_required",
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="primary_route has no matching route"):
        load_coverage_matrix(path)


def test_coverage_matrix_rejects_invalid_route_statement_type(
    tmp_path: Path,
) -> None:
    path = tmp_path / "coverage.json"
    path.write_text(
        json.dumps(
            {
                "matrix_id": "demo_coverage",
                "version": "2026-05-02",
                "taxonomy_catalog": "demo_taxonomy",
                "fields": {
                    "revenue": {
                        "domain": "income_statement",
                        "priority": "P0",
                        "primary_route": "akshare_direct",
                        "verification": "verified",
                        "notes": "Invalid statement type regression fixture.",
                        "routes": [
                            {
                                "source": "akshare",
                                "mode": "direct",
                                "status": "verified",
                                "statement_type": "income_statment",
                                "evidence_requirement": "source_only_allowed",
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid statement_type"):
        load_coverage_matrix(path)


def test_coverage_matrix_rejects_verified_field_with_unverified_primary_route(
    tmp_path: Path,
) -> None:
    path = tmp_path / "coverage.json"
    path.write_text(
        json.dumps(
            {
                "matrix_id": "demo_coverage",
                "version": "2026-05-02",
                "taxonomy_catalog": "demo_taxonomy",
                "fields": {
                    "revenue": {
                        "domain": "income_statement",
                        "priority": "P0",
                        "primary_route": "akshare_direct",
                        "verification": "verified",
                        "notes": "Verified status requires verified primary route.",
                        "routes": [
                            {
                                "source": "akshare",
                                "mode": "direct",
                                "status": "expected",
                                "statement_type": "income_statement",
                                "evidence_requirement": "source_only_allowed",
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="verified field requires verified primary route",
    ):
        load_coverage_matrix(path)


def test_coverage_matrix_rejects_expected_field_with_unsupported_primary_route(
    tmp_path: Path,
) -> None:
    data = _coverage_matrix_payload()
    data["fields"]["revenue"]["verification"] = "expected"
    data["fields"]["revenue"]["routes"][0]["status"] = "unsupported"
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="field verification exceeds primary route status",
    ):
        load_coverage_matrix(path)


def test_coverage_matrix_accepts_expected_field_with_expected_primary_route(
    tmp_path: Path,
) -> None:
    data = _coverage_matrix_payload()
    data["fields"]["revenue"]["verification"] = "expected"
    data["fields"]["revenue"]["routes"][0]["status"] = "expected"
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    matrix = load_coverage_matrix(path)

    assert matrix.fields["revenue"].verification == "expected"


def test_coverage_matrix_rejects_pdf_only_taxonomy_with_direct_primary_route(
    tmp_path: Path,
) -> None:
    taxonomy = _write_and_load_taxonomy(
        tmp_path,
        field_metadata={
            "source_mode": "pdf_only",
            "evidence_requirement": "pdf_required",
        },
    )
    matrix = _write_and_load_coverage_matrix(tmp_path)

    with pytest.raises(
        ValueError,
        match="source mode requires PDF or LLM route",
    ):
        validate_coverage_matrix_against_taxonomy(matrix, taxonomy)


def test_coverage_matrix_validation_rejects_direct_taxonomy_without_provider_route(
    tmp_path: Path,
) -> None:
    taxonomy = _write_and_load_taxonomy(tmp_path)
    matrix = _write_and_load_coverage_matrix(
        tmp_path,
        field_metadata={
            "primary_route": "pdf_evidence",
            "verification": "expected",
            "routes": [
                {
                    "source": "pdf",
                    "mode": "evidence",
                    "status": "expected",
                    "statement_type": "income_statement",
                    "evidence_requirement": "pdf_required",
                }
            ],
        },
    )

    with pytest.raises(
        ValueError,
        match="direct source mode requires provider route unless unknown",
    ):
        validate_coverage_matrix_against_taxonomy(matrix, taxonomy)


def test_coverage_matrix_validation_allows_unknown_direct_taxonomy_without_provider_route(
    tmp_path: Path,
) -> None:
    taxonomy = _write_and_load_taxonomy(tmp_path)
    matrix = _write_and_load_coverage_matrix(
        tmp_path,
        field_metadata={
            "primary_route": "pdf_evidence",
            "verification": "unknown",
            "routes": [
                {
                    "source": "pdf",
                    "mode": "evidence",
                    "status": "unknown",
                    "statement_type": "income_statement",
                    "evidence_requirement": "pdf_required",
                }
            ],
        },
    )

    validate_coverage_matrix_against_taxonomy(matrix, taxonomy)


def test_coverage_matrix_validation_rejects_missing_coverage_fields(
    tmp_path: Path,
) -> None:
    taxonomy = _write_and_load_taxonomy(tmp_path)
    taxonomy.fields["net_profit"] = replace(
        taxonomy.fields["revenue"],
        field_id="net_profit",
    )
    matrix = _write_and_load_coverage_matrix(tmp_path)

    with pytest.raises(ValueError, match="missing coverage fields"):
        validate_coverage_matrix_against_taxonomy(matrix, taxonomy)


def test_coverage_matrix_validation_rejects_unknown_coverage_fields(
    tmp_path: Path,
) -> None:
    taxonomy = _write_and_load_taxonomy(tmp_path)
    matrix = _write_and_load_coverage_matrix(tmp_path)
    matrix.fields["unexpected_field"] = replace(
        matrix.fields["revenue"],
        field_id="unexpected_field",
    )

    with pytest.raises(ValueError, match="unknown coverage fields"):
        validate_coverage_matrix_against_taxonomy(matrix, taxonomy)


def test_coverage_matrix_validation_rejects_taxonomy_catalog_mismatch(
    tmp_path: Path,
) -> None:
    taxonomy = _write_and_load_taxonomy(tmp_path)
    matrix = _write_and_load_coverage_matrix(
        tmp_path,
        matrix_metadata={"taxonomy_catalog": "different_taxonomy"},
    )

    with pytest.raises(ValueError, match="taxonomy_catalog mismatch"):
        validate_coverage_matrix_against_taxonomy(matrix, taxonomy)


def test_coverage_matrix_validation_rejects_domain_mismatch(
    tmp_path: Path,
) -> None:
    taxonomy = _write_and_load_taxonomy(
        tmp_path,
        field_metadata={"domain": "balance_sheet"},
    )
    matrix = _write_and_load_coverage_matrix(tmp_path)

    with pytest.raises(ValueError, match="domain mismatch"):
        validate_coverage_matrix_against_taxonomy(matrix, taxonomy)


def test_coverage_matrix_validation_rejects_priority_mismatch(
    tmp_path: Path,
) -> None:
    taxonomy = _write_and_load_taxonomy(
        tmp_path,
        field_metadata={"priority": "P1"},
    )
    matrix = _write_and_load_coverage_matrix(tmp_path)

    with pytest.raises(ValueError, match="priority mismatch"):
        validate_coverage_matrix_against_taxonomy(matrix, taxonomy)


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


def test_taxonomy_validation_rejects_unknown_taxonomy_fields(tmp_path: Path) -> None:
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
                    },
                    "unexpected_field": {
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
                        "description": "Unexpected field.",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    taxonomy = load_field_taxonomy(taxonomy_path)

    with pytest.raises(ValueError, match="unknown taxonomy fields"):
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


def test_real_turtle_taxonomy_covers_all_priority_fields() -> None:
    taxonomy = load_field_taxonomy(
        Path("field_catalog/turtle_v015_field_taxonomy.json")
    )

    validate_taxonomy_against_priority_catalog(
        taxonomy,
        Path("field_catalog/turtle_v015_priority_fields.json"),
    )

    assert taxonomy.fields["revenue"].domain == "income_statement"
    assert taxonomy.fields["total_assets"].domain == "balance_sheet"
    assert taxonomy.fields["operating_cash_flow"].domain == "cash_flow"
    assert taxonomy.fields["mda_risk_factors"].source_mode == "llm_review"


def test_real_coverage_matrix_covers_taxonomy_fields() -> None:
    taxonomy = load_field_taxonomy(
        Path("field_catalog/turtle_v015_field_taxonomy.json")
    )
    matrix = load_coverage_matrix(
        Path("field_catalog/turtle_v015_coverage_matrix.json")
    )

    validate_coverage_matrix_against_taxonomy(matrix, taxonomy)

    assert matrix.fields["revenue"].primary_route == "akshare_direct"
    assert matrix.fields["gross_profit"].primary_route == "yahoo_direct"
    assert matrix.fields["mda_business_review"].primary_route == "llm_review"


def test_coverage_matrix_can_summarize_by_domain_and_route() -> None:
    matrix = load_coverage_matrix(
        Path("field_catalog/turtle_v015_coverage_matrix.json")
    )

    summary = summarize_coverage_matrix(matrix)

    assert summary["total_fields"] == len(matrix.fields)
    by_domain = summary["by_domain"]
    by_primary_route = summary["by_primary_route"]
    assert isinstance(by_domain, dict)
    assert isinstance(by_primary_route, dict)
    assert by_domain["income_statement"] >= 1
    assert by_primary_route["llm_review"] >= 1


def test_real_turtle_taxonomy_matches_expected_metadata() -> None:
    taxonomy = load_field_taxonomy(
        Path("field_catalog/turtle_v015_field_taxonomy.json")
    )
    expected = {
        "revenue": (
            "P0",
            "income_statement",
            "income_statement",
            "money",
            "direct",
            "duration",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "operating_cost": (
            "P0",
            "income_statement",
            "income_statement",
            "money",
            "direct",
            "duration",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "operating_profit": (
            "P0",
            "income_statement",
            "income_statement",
            "money",
            "direct",
            "duration",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "net_profit": (
            "P0",
            "income_statement",
            "income_statement",
            "money",
            "direct",
            "duration",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "total_assets": (
            "P0",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "total_liabilities": (
            "P0",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "equity_attributable_to_owners": (
            "P0",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "attributable_to_owners",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "operating_cash_flow": (
            "P0",
            "cash_flow",
            "cash_flow",
            "money",
            "direct",
            "duration",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "investing_cash_flow": (
            "P0",
            "cash_flow",
            "cash_flow",
            "money",
            "direct",
            "duration",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "financing_cash_flow": (
            "P0",
            "cash_flow",
            "cash_flow",
            "money",
            "direct",
            "duration",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "cash": (
            "P0",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "money_cap": (
            "P0",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "st_borr": (
            "P0",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "lt_borr": (
            "P0",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "bond_payable": (
            "P0",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "accounts_receiv": (
            "P0",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "acct_payable": (
            "P0",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "inventories": (
            "P0",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "fix_assets": (
            "P0",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "cip": (
            "P0",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "rd_exp": (
            "P0",
            "income_statement",
            "income_statement",
            "money",
            "source_optional",
            "duration",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "invest_income": (
            "P0",
            "income_statement",
            "income_statement",
            "money",
            "direct",
            "duration",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "gross_profit": (
            "P1",
            "income_statement",
            "income_statement",
            "money",
            "direct",
            "duration",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "selling_general_administrative": (
            "P1",
            "income_statement",
            "income_statement",
            "money",
            "direct",
            "duration",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "fv_value_chg_gain": (
            "P1",
            "income_statement",
            "income_statement",
            "money",
            "source_optional",
            "duration",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "non_oper_income": (
            "P1",
            "income_statement",
            "income_statement",
            "money",
            "direct",
            "duration",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "non_oper_exp": (
            "P1",
            "income_statement",
            "income_statement",
            "money",
            "direct",
            "duration",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "total_cur_assets": (
            "P1",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "other_cur_assets": (
            "P1",
            "balance_sheet",
            "balance_sheet",
            "money",
            "source_optional",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "total_cur_liab": (
            "P1",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "defer_tax_assets": (
            "P1",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "defer_tax_liab": (
            "P1",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "minority_int": (
            "P1",
            "balance_sheet",
            "balance_sheet",
            "money",
            "direct",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "source_only_allowed",
            "pdf_allowed",
        ),
        "stock_based_compensation": (
            "P2",
            "cash_flow",
            "cash_flow",
            "money",
            "source_optional",
            "duration",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "change_in_receivables": (
            "P2",
            "cash_flow",
            "cash_flow",
            "money",
            "source_optional",
            "duration",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "change_in_payables": (
            "P2",
            "cash_flow",
            "cash_flow",
            "money",
            "source_optional",
            "duration",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "change_in_inventory": (
            "P2",
            "cash_flow",
            "cash_flow",
            "money",
            "source_optional",
            "duration",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "receiv_tax_refund": (
            "P2",
            "cash_flow",
            "cash_flow",
            "money",
            "source_optional",
            "duration",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "repurchase_of_stock": (
            "P2",
            "shareholder_return",
            "cash_flow",
            "money",
            "source_optional",
            "duration",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "dividends_paid": (
            "P2",
            "shareholder_return",
            "cash_flow",
            "money",
            "source_optional",
            "duration",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "capital_expenditures": (
            "P2",
            "cash_flow",
            "cash_flow",
            "money",
            "source_optional",
            "duration",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "depreciation_amortization": (
            "P2",
            "accounting_adjustments",
            "cash_flow",
            "money",
            "source_optional",
            "duration",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "dps": (
            "P3",
            "shareholder_return",
            "announcement",
            "money",
            "source_optional",
            "event",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "dividend_plan": (
            "P3",
            "shareholder_return",
            "announcement",
            "text",
            "pdf_only",
            "event",
            "not_applicable",
            "not_applicable",
            "not_applicable",
            "pdf_required",
            "pdf_allowed",
        ),
        "buyback_cancellation_progress": (
            "P3",
            "shareholder_return",
            "announcement",
            "text",
            "pdf_only",
            "event",
            "not_applicable",
            "not_applicable",
            "not_applicable",
            "pdf_required",
            "pdf_allowed",
        ),
        "capitalized_rd": (
            "P3",
            "accounting_adjustments",
            "notes",
            "money",
            "pdf_only",
            "duration",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "capitalized_interest": (
            "P3",
            "accounting_adjustments",
            "notes",
            "money",
            "pdf_only",
            "duration",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "receivables_aging": (
            "P3",
            "notes_and_mda",
            "notes",
            "text",
            "pdf_only",
            "point_in_time",
            "consolidated",
            "not_applicable",
            "not_applicable",
            "pdf_required",
            "pdf_allowed",
        ),
        "bad_debt_provision": (
            "P3",
            "notes_and_mda",
            "notes",
            "money",
            "pdf_only",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "related_party_receivables_payables": (
            "P3",
            "notes_and_mda",
            "notes",
            "text",
            "pdf_only",
            "point_in_time",
            "consolidated",
            "not_applicable",
            "not_applicable",
            "pdf_required",
            "pdf_allowed",
        ),
        "contingent_liabilities_commitments": (
            "P3",
            "notes_and_mda",
            "notes",
            "text",
            "pdf_only",
            "point_in_time",
            "consolidated",
            "not_applicable",
            "not_applicable",
            "pdf_required",
            "pdf_allowed",
        ),
        "lease_liability_maturity": (
            "P3",
            "notes_and_mda",
            "notes",
            "text",
            "pdf_only",
            "point_in_time",
            "consolidated",
            "not_applicable",
            "not_applicable",
            "pdf_required",
            "pdf_allowed",
        ),
        "segment_revenue_profit": (
            "P3",
            "notes_and_mda",
            "notes",
            "text",
            "pdf_only",
            "duration",
            "consolidated",
            "not_applicable",
            "not_applicable",
            "pdf_required",
            "pdf_allowed",
        ),
        "restricted_cash": (
            "P3",
            "notes_and_mda",
            "notes",
            "money",
            "pdf_only",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "time_deposits_or_wealth_products": (
            "P3",
            "notes_and_mda",
            "notes",
            "money",
            "pdf_only",
            "point_in_time",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "interest_paid_cash": (
            "P3",
            "cash_flow",
            "cash_flow",
            "money",
            "source_optional",
            "duration",
            "consolidated",
            "required",
            "required",
            "pdf_required",
            "pdf_allowed",
        ),
        "mda_business_review": (
            "P4",
            "notes_and_mda",
            "mda",
            "text",
            "llm_review",
            "annual_text",
            "not_applicable",
            "not_applicable",
            "not_applicable",
            "llm_review_required",
            "llm_review_required",
        ),
        "mda_forward_guidance": (
            "P4",
            "notes_and_mda",
            "mda",
            "text",
            "llm_review",
            "annual_text",
            "not_applicable",
            "not_applicable",
            "not_applicable",
            "llm_review_required",
            "llm_review_required",
        ),
        "mda_risk_factors": (
            "P4",
            "notes_and_mda",
            "mda",
            "text",
            "llm_review",
            "annual_text",
            "not_applicable",
            "not_applicable",
            "not_applicable",
            "llm_review_required",
            "llm_review_required",
        ),
        "dividend_policy_text": (
            "P4",
            "notes_and_mda",
            "notes",
            "text",
            "llm_review",
            "annual_text",
            "not_applicable",
            "not_applicable",
            "not_applicable",
            "llm_review_required",
            "llm_review_required",
        ),
        "audit_opinion": (
            "P4",
            "notes_and_mda",
            "notes",
            "text",
            "llm_review",
            "annual_text",
            "not_applicable",
            "not_applicable",
            "not_applicable",
            "llm_review_required",
            "llm_review_required",
        ),
        "auditor_change_history": (
            "P4",
            "notes_and_mda",
            "notes",
            "text",
            "llm_review",
            "annual_text",
            "not_applicable",
            "not_applicable",
            "not_applicable",
            "llm_review_required",
            "llm_review_required",
        ),
    }

    assert set(expected) == set(taxonomy.fields)
    for field_id, expected_metadata in expected.items():
        entry = taxonomy.fields[field_id]
        actual_metadata = (
            entry.priority,
            entry.domain,
            entry.statement_type,
            entry.value_type,
            entry.source_mode,
            entry.period_type,
            entry.scope_expectation,
            entry.currency_requirement,
            entry.unit_requirement,
            entry.evidence_requirement,
            entry.fallback_policy,
        )
        assert actual_metadata == expected_metadata


def test_real_turtle_taxonomy_supports_domain_queries() -> None:
    taxonomy = load_field_taxonomy(
        Path("field_catalog/turtle_v015_field_taxonomy.json")
    )

    p0_balance_sheet = sorted(
        entry.field_id
        for entry in taxonomy.fields.values()
        if entry.priority == "P0" and entry.domain == "balance_sheet"
    )

    assert "total_assets" in p0_balance_sheet
    assert "cash" in p0_balance_sheet
    assert "revenue" not in p0_balance_sheet


def _write_and_load_taxonomy(
    tmp_path: Path,
    *,
    field_metadata: dict[str, str] | None = None,
) -> FieldTaxonomyCatalog:
    metadata = {
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
    if field_metadata:
        metadata.update(field_metadata)
    path = tmp_path / "taxonomy.json"
    path.write_text(
        json.dumps(
            {
                "catalog_id": "demo_taxonomy",
                "version": "2026-05-02",
                "source_priority_catalog": "demo_priority",
                "fields": {"revenue": metadata},
            }
        ),
        encoding="utf-8",
    )
    return load_field_taxonomy(path)


def _coverage_matrix_payload() -> dict[str, Any]:
    return {
        "matrix_id": "demo_coverage",
        "version": "2026-05-02",
        "taxonomy_catalog": "demo_taxonomy",
        "fields": {
            "revenue": {
                "domain": "income_statement",
                "priority": "P0",
                "primary_route": "akshare_direct",
                "verification": "verified",
                "notes": "Verified by captured AKShare fixture.",
                "routes": [
                    {
                        "source": "akshare",
                        "mode": "direct",
                        "status": "verified",
                        "statement_type": "income_statement",
                        "evidence_requirement": "source_only_allowed",
                    }
                ],
            }
        },
    }


def _write_and_load_coverage_matrix(
    tmp_path: Path,
    *,
    field_metadata: dict[str, object] | None = None,
    matrix_metadata: dict[str, object] | None = None,
) -> CoverageMatrix:
    metadata: dict[str, object] = {
        "domain": "income_statement",
        "priority": "P0",
        "primary_route": "akshare_direct",
        "verification": "verified",
        "notes": "Verified by captured AKShare fixture.",
        "routes": [
            {
                "source": "akshare",
                "mode": "direct",
                "status": "verified",
                "statement_type": "income_statement",
                "evidence_requirement": "source_only_allowed",
            }
        ],
    }
    if field_metadata:
        metadata.update(field_metadata)
    matrix_payload: dict[str, object] = {
        "matrix_id": "demo_coverage",
        "version": "2026-05-02",
        "taxonomy_catalog": "demo_taxonomy",
        "fields": {"revenue": metadata},
    }
    if matrix_metadata:
        matrix_payload.update(matrix_metadata)
    path = tmp_path / "coverage.json"
    path.write_text(
        json.dumps(matrix_payload),
        encoding="utf-8",
    )
    return load_coverage_matrix(path)
