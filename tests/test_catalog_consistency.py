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
        SOURCE_MAPPING, priorities=("P0", "P1", "P2", "P3")
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
        SOURCE_MAPPING, priorities=("P0", "P1", "P2", "P3")
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
        SOURCE_MAPPING, priorities=("P0", "P1", "P2", "P3")
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
        SOURCE_MAPPING, priorities=("P0", "P1", "P2", "P3")
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
        SOURCE_MAPPING, priorities=("P0", "P1", "P2", "P3")
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
        SOURCE_MAPPING, priorities=("P0", "P1", "P2", "P3")
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


def test_provider_raw_semantics_cn_loads_h2_rules() -> None:
    """Phase H2 Task 3: provider_raw_semantics_cn.json must include sample-verified
    rules for revenue + operating_profit (CN promote AKShare per 600519/2024 PDF)."""
    catalog = load_provider_semantics_catalog(
        Path("field_catalog/provider_raw_semantics_cn.json")
    )
    rule_field_ids = {rule.turtle_field_id for rule in catalog.rules}
    assert "revenue" in rule_field_ids
    assert "operating_profit" in rule_field_ids

    # The CN revenue + operating_profit rules must be sample-verified (promote).
    cn_revenue_rules = [r for r in catalog.rules if r.turtle_field_id == "revenue"]
    assert any(
        r.classification == "provider_semantics_sample_verified"
        for r in cn_revenue_rules
    )


def test_akshare_aliases_appear_in_provider_baseline_inventory() -> None:
    """N4 review fix: akshare aliases in source_mapping must appear in the
    captured provider field baseline. Catches fabricated/typo aliases.

    For each akshare alias of a P0/P1/P2/P3 source_mapping field, verify it
    appears at least once as a raw_field_code or raw_field_name in the
    provider_field_inventory_summary.json.
    """
    summary_path = (
        Path(__file__).resolve().parents[1]
        / "tests" / "fixtures" / "provider_captures"
        / "provider_field_baseline" / "provider_field_inventory_summary.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    # Collect all observed akshare raw field names + codes from baseline
    observed: set[str] = set()
    for target in summary.get("targets", []):
        if target.get("source") != "akshare":
            continue
        for code in target.get("raw_field_codes", []) or []:
            observed.add(str(code))
        for name in target.get("raw_field_names", []) or []:
            observed.add(str(name))

    catalog = load_source_mapping_catalog(
        SOURCE_MAPPING, priorities=("P0", "P1", "P2", "P3")
    )
    missing: list[tuple[str, str]] = []
    for field_id, entry in catalog.entries.items():
        for alias in entry.source_aliases.get("akshare", ()):
            # Chinese-character-only aliases are display labels — skip
            # (AKShare returns code keys, not labels)
            if all(ord(c) > 127 for c in alias):
                continue
            if alias not in observed:
                missing.append((field_id, alias))

    if missing:
        msg = "\n".join(f"  {fid}: {alias!r}" for fid, alias in missing)
        raise AssertionError(
            f"akshare aliases in source_mapping not found in provider baseline:\n{msg}"
        )


# 4 P4 fields that are deliberately defined in taxonomy + coverage_matrix
# (for downstream Turtle Agent reference) but NOT in source_mapping_minimal.
# Paragraph-level MD&A extraction and multi-period audit-firm tenure tracking
# are out of project scope for this data-collection layer.
# See Phase G4-C Implementation Result in the roadmap and the description
# field on each taxonomy entry for the rationale.
_P4_INTENTIONALLY_UNMAPPED: tuple[str, ...] = (
    "mda_business_review",
    "mda_forward_guidance",
    "mda_risk_factors",
    "auditor_change_history",
)


def test_alias_normalization_rollout_state() -> None:
    """N0 gate: the live catalog's alias_normalization flag must match the
    gated rollout state. Flip BOTH together after the PR-3 cohort gate
    (selection diff + paid revalidation) passes."""
    ALIAS_NORMALIZATION_ROLLED_OUT = False
    catalog = load_source_mapping_catalog(
        SOURCE_MAPPING,
        priorities=("P0", "P1", "P2", "P3", "P4"),
    )
    assert catalog.alias_normalization is ALIAS_NORMALIZATION_ROLLED_OUT


def test_p4_intentionally_unmapped_fields_stay_unmapped() -> None:
    """Regression lock: the 4 P4 fields documented as out-of-project-scope
    must remain unmapped in source_mapping_minimal but present in taxonomy
    and coverage_matrix. If a future contributor maps one of them, this
    test forces them to update _P4_INTENTIONALLY_UNMAPPED here and the
    description marker in turtle_v015_field_taxonomy.json so the scope
    decision stays explicit.

    See Phase G4-C Implementation Result (loose end #1) in the roadmap.
    """
    taxonomy = load_field_taxonomy(TAXONOMY)
    coverage = load_coverage_matrix(COVERAGE_MATRIX)
    # Load with all priorities so source_mapping_minimal entries are visible.
    source_mapping = load_source_mapping_catalog(
        SOURCE_MAPPING, priorities=("P0", "P1", "P2", "P3", "P4")
    )

    for field_id in _P4_INTENTIONALLY_UNMAPPED:
        assert field_id in taxonomy.fields, (
            f"intentionally-unmapped P4 field '{field_id}' missing from "
            f"taxonomy; coverage gap doc and downstream Turtle Agent rely "
            f"on it being defined."
        )
        assert taxonomy.fields[field_id].priority == "P4", (
            f"field '{field_id}' expected priority P4, got "
            f"{taxonomy.fields[field_id].priority!r}"
        )
        assert "[Intentionally unmapped" in taxonomy.fields[field_id].description, (
            f"field '{field_id}' description must start with marker "
            f"'[Intentionally unmapped — out of project scope]' so the "
            f"out-of-scope decision is machine-readable. Update the "
            f"taxonomy description if you are deliberately mapping this "
            f"field, then remove it from _P4_INTENTIONALLY_UNMAPPED."
        )
        assert field_id in coverage.fields, (
            f"intentionally-unmapped P4 field '{field_id}' missing from "
            f"coverage_matrix"
        )
        assert field_id not in source_mapping.entries, (
            f"P4 field '{field_id}' is documented as intentionally unmapped "
            f"(out of project scope) but appears in source_mapping_minimal. "
            f"Either (a) remove it from source_mapping, or (b) update "
            f"_P4_INTENTIONALLY_UNMAPPED in this test and the taxonomy "
            f"description marker to reflect the scope decision change."
        )
