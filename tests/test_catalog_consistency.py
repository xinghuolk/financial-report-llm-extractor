"""Phase N0: Catalog Consistency Gate.

Cross-catalog invariant tests spanning all 5 field_catalog JSON files.
Each test enforces one structural invariant with clear failure messages.
"""

import json
from pathlib import Path

import pytest

from financial_report_llm_extractor.field_metadata import (
    load_coverage_matrix,
    load_field_taxonomy,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    load_source_mapping_catalog,
)
from financial_report_llm_extractor.structured_sources.hk_yahoo_trust_policy import (
    load_hk_yahoo_trust_policy,
)
from financial_report_llm_extractor.structured_sources.provider_semantics import (
    load_provider_semantics_catalog,
)

CATALOG_DIR = Path("field_catalog")
SOURCE_MAPPING = CATALOG_DIR / "turtle_v015_source_mapping_minimal.json"
COVERAGE_MATRIX = CATALOG_DIR / "turtle_v015_coverage_matrix.json"
TAXONOMY = CATALOG_DIR / "turtle_v015_field_taxonomy.json"
PROVIDER_SEMANTICS = CATALOG_DIR / "provider_raw_semantics_hk.json"
TRUST_POLICY = CATALOG_DIR / "hk_yahoo_trust_policy.json"
PRIORITY_FIELDS = CATALOG_DIR / "turtle_v015_priority_fields.json"


def test_source_mapping_aligns_with_coverage_matrix() -> None:
    """Every source_mapping entry must exist in coverage_matrix with matching
    primary_route and verification_status."""
    source_mapping = load_source_mapping_catalog(
        SOURCE_MAPPING, priorities=("P0", "P1")
    )
    coverage = load_coverage_matrix(COVERAGE_MATRIX)

    for field_id, entry in source_mapping.entries.items():
        assert field_id in coverage.fields, (
            f"source_mapping field '{field_id}' not found in coverage_matrix"
        )
        cov = coverage.fields[field_id]
        assert entry.primary_route == cov.primary_route, (
            f"field '{field_id}': source_mapping.primary_route={entry.primary_route!r} "
            f"!= coverage_matrix.primary_route={cov.primary_route!r}"
        )
        assert entry.verification_status == cov.verification, (
            f"field '{field_id}': source_mapping.verification_status="
            f"{entry.verification_status!r} "
            f"!= coverage_matrix.verification={cov.verification!r}"
        )


def test_source_mapping_aligns_with_taxonomy() -> None:
    """Every source_mapping entry must exist in taxonomy with matching
    statement_type and value_type (only when taxonomy has non-empty values)."""
    source_mapping = load_source_mapping_catalog(
        SOURCE_MAPPING, priorities=("P0", "P1")
    )
    taxonomy = load_field_taxonomy(TAXONOMY)

    for field_id, entry in source_mapping.entries.items():
        assert field_id in taxonomy.fields, (
            f"source_mapping field '{field_id}' not found in taxonomy"
        )
        tax = taxonomy.fields[field_id]
        if tax.statement_type:
            assert entry.statement_type == tax.statement_type, (
                f"field '{field_id}': source_mapping.statement_type="
                f"{entry.statement_type!r} "
                f"!= taxonomy.statement_type={tax.statement_type!r}"
            )
        if tax.value_type:
            assert entry.value_type == tax.value_type, (
                f"field '{field_id}': source_mapping.value_type={entry.value_type!r} "
                f"!= taxonomy.value_type={tax.value_type!r}"
            )


def test_provider_semantics_aligns_with_source_mapping() -> None:
    """Every provider_semantics rule's turtle_field_id must exist in
    source_mapping. When allowed_as_primary==True, the raw_field_name must
    appear in the entry's source_aliases for that provider."""
    source_mapping = load_source_mapping_catalog(
        SOURCE_MAPPING, priorities=("P0", "P1")
    )
    semantics = load_provider_semantics_catalog(PROVIDER_SEMANTICS)

    for rule in semantics.rules:
        field_id = rule.turtle_field_id
        assert field_id in source_mapping.entries, (
            f"provider_semantics rule turtle_field_id={field_id!r} "
            f"({rule.provider}, {rule.market}, {rule.raw_field_name!r}) "
            f"is not in source_mapping; rule must reference a mapped field"
        )

        if rule.allowed_as_primary:
            entry = source_mapping.entries[field_id]
            provider_aliases = entry.source_aliases.get(rule.provider, ())
            assert rule.raw_field_name in provider_aliases, (
                f"field '{field_id}': provider_semantics rule "
                f"(provider={rule.provider!r}, raw_field_name={rule.raw_field_name!r}) "
                f"has allowed_as_primary=True but raw_field_name not found in "
                f"source_mapping.source_aliases[{rule.provider!r}]={provider_aliases!r}"
            )


def test_trust_policy_aligns_with_source_mapping() -> None:
    """Every trust_policy rule's field_id must exist in source_mapping.
    All allowed_yahoo_raw_fields must appear in source_mapping's yahoo aliases."""
    source_mapping = load_source_mapping_catalog(
        SOURCE_MAPPING, priorities=("P0", "P1")
    )
    trust_policy = load_hk_yahoo_trust_policy(TRUST_POLICY)

    for rule in trust_policy.rules:
        field_id = rule.field_id
        assert field_id in source_mapping.entries, (
            f"trust_policy rule field_id='{field_id}' not found in source_mapping.entries"
        )
        entry = source_mapping.entries[field_id]
        yahoo_aliases = entry.source_aliases.get("yahoo", ())
        for raw_field in rule.allowed_yahoo_raw_fields:
            assert raw_field in yahoo_aliases, (
                f"field '{field_id}': trust_policy allowed_yahoo_raw_fields contains "
                f"{raw_field!r} which is not in source_mapping.source_aliases['yahoo']="
                f"{yahoo_aliases!r}"
            )


def test_trust_policy_pdf_verified_rules_have_provider_semantics_proof() -> None:
    """For every trust_policy rule with classification=='yahoo_pdf_verified',
    each raw_field in allowed_yahoo_raw_fields must have a corresponding
    provider_semantics rule with allowed_as_primary==True."""
    trust_policy = load_hk_yahoo_trust_policy(TRUST_POLICY)
    semantics = load_provider_semantics_catalog(PROVIDER_SEMANTICS)

    for rule in trust_policy.rules:
        if rule.classification != "yahoo_pdf_verified":
            continue
        for raw_field_name in rule.allowed_yahoo_raw_fields:
            try:
                sem_rule = semantics.require_rule(
                    provider="yahoo",
                    market="HK",
                    turtle_field_id=rule.field_id,
                    raw_field_name=raw_field_name,
                )
            except ValueError:
                pytest.fail(
                    f"field '{rule.field_id}': trust_policy has "
                    f"classification='yahoo_pdf_verified' for "
                    f"raw_field_name={raw_field_name!r} but no matching "
                    "provider_semantics rule found "
                    f"(provider='yahoo', market='HK', "
                    f"turtle_field_id='{rule.field_id}', "
                    f"raw_field_name={raw_field_name!r})"
                )
            else:
                assert sem_rule.allowed_as_primary, (
                    f"field '{rule.field_id}': trust_policy has "
                    f"classification='yahoo_pdf_verified' for "
                    f"raw_field_name={raw_field_name!r} but provider_semantics "
                    f"rule has allowed_as_primary=False"
                )


def test_source_mapping_priority_aligns_with_priority_list() -> None:
    """For each P0/P1 field that appears in source_mapping, the entry's
    priority must match the priority bucket from the priority list."""
    source_mapping = load_source_mapping_catalog(
        SOURCE_MAPPING, priorities=("P0", "P1")
    )
    raw_priorities = json.loads(PRIORITY_FIELDS.read_text(encoding="utf-8"))
    priority_buckets = raw_priorities.get("priorities", [])

    for bucket in priority_buckets:
        bucket_priority = str(bucket.get("priority", ""))
        if bucket_priority not in {"P0", "P1"}:
            continue
        for field_id in bucket.get("fields", []):
            if field_id not in source_mapping.entries:
                # Not yet promoted — expansion is in progress; skip.
                continue
            entry = source_mapping.entries[field_id]
            assert entry.priority == bucket_priority, (
                f"field '{field_id}': source_mapping.priority={entry.priority!r} "
                f"!= priority_list bucket priority={bucket_priority!r}"
            )


def test_taxonomy_evidence_requirement_matches_coverage_routes() -> None:
    """For each field in source_mapping, if taxonomy specifies evidence_requirement
    and the coverage_matrix specifies evidence_requirement on at least one route,
    at least one route must match the taxonomy value.

    Taxonomy is the policy authority; coverage_matrix routes must not conflict."""
    source_mapping = load_source_mapping_catalog(
        SOURCE_MAPPING, priorities=("P0", "P1")
    )
    taxonomy = load_field_taxonomy(TAXONOMY)
    coverage = load_coverage_matrix(COVERAGE_MATRIX)

    for field_id in source_mapping.entries:
        tax = taxonomy.fields.get(field_id)
        if tax is None:
            continue
        tax_req = tax.evidence_requirement
        if not tax_req:
            continue

        cov = coverage.fields.get(field_id)
        if cov is None:
            continue

        route_reqs = [r.evidence_requirement for r in cov.routes if r.evidence_requirement]
        if not route_reqs:
            # No route specifies evidence_requirement — lenient, no assertion needed.
            continue

        assert any(r == tax_req for r in route_reqs), (
            f"field '{field_id}': taxonomy.evidence_requirement={tax_req!r} "
            f"but no coverage_matrix route matches; route evidence_requirements={route_reqs!r}. "
            f"Taxonomy is the policy authority — update coverage_matrix routes to align."
        )
