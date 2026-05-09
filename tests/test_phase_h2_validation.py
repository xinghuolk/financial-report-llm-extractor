"""Phase H2: locked-in field-bucket expectations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


CATALOG_PATH = Path("field_catalog/turtle_v015_source_mapping_minimal.json")
SEMANTICS_CN = Path("field_catalog/provider_raw_semantics_cn.json")
SEMANTICS_HK = Path("field_catalog/provider_raw_semantics_hk.json")


def _load_semantics(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rules = payload.get("rules", [])
    assert isinstance(rules, list)
    return rules


def test_phase_h2_da_remains_unverified() -> None:
    """D&A stays terminal_unverified per H2: AKShare FA_IR_DEPR is
    fixed-asset-only; semantically unequal to Yahoo D&A (which includes
    intangibles amortization). No Phase H2.1 work for D&A."""
    cn_rules = _load_semantics(SEMANTICS_CN)
    hk_rules = _load_semantics(SEMANTICS_HK)
    da_rules = [
        r
        for r in cn_rules + hk_rules
        if r.get("turtle_field_id") == "depreciation_amortization"
    ]
    assert any(
        r.get("classification") == "provider_semantics_unverified" for r in da_rules
    ), (
        "depreciation_amortization must have at least one "
        "provider_semantics_unverified rule"
    )


def test_phase_h2_1_cn_sga_promoted_to_sample_verified() -> None:
    """Phase H2.1: CN SGA derivation MANAGE_EXPENSE + SALE_EXPENSE EXACT-matches
    PDF for 600519/2024 (14,954,950,119.87 CNY); promoted from
    provider_semantics_unverified to provider_semantics_sample_verified."""
    cn_rules = _load_semantics(SEMANTICS_CN)
    sga_cn_rules = [
        r
        for r in cn_rules
        if r.get("turtle_field_id") == "selling_general_administrative"
    ]
    assert sga_cn_rules, "expected at least one CN SGA rule"
    assert any(
        r.get("classification") == "provider_semantics_sample_verified"
        and r.get("provider") == "akshare"
        for r in sga_cn_rules
    ), (
        "CN SGA must have at least one akshare provider_semantics_sample_verified "
        "rule after Phase H2.1"
    )
    # Ensure the old unverified MANAGE_EXPENSE-only rule is gone — otherwise the
    # composite proof is moot and the unverified rule would still fire.
    assert not any(
        r.get("classification") == "provider_semantics_unverified"
        and r.get("raw_field_name") == "MANAGE_EXPENSE"
        for r in sga_cn_rules
    ), (
        "Phase H2.1 must remove the obsolete MANAGE_EXPENSE-only unverified rule "
        "for selling_general_administrative"
    )


def test_phase_h2_2_promoted_cn_rules_have_multi_company_samples() -> None:
    """Phase H2.2 Sub-A: each provider_semantics_sample_verified rule for CN
    should have ≥ 2 sample companies — single-sample sample_verified is a
    drift §177 sampling-bias risk."""
    cn_rules = _load_semantics(SEMANTICS_CN)
    promoted = [
        r for r in cn_rules
        if r.get("classification") == "provider_semantics_sample_verified"
    ]
    assert promoted, "expected at least one promoted rule"
    for rule in promoted:
        samples = rule.get("samples", [])
        sample_companies = {
            s.get("company_id") for s in samples if s.get("company_id")
        }
        assert len(sample_companies) >= 2, (
            f"rule for turtle_field_id="
            f"{rule.get('turtle_field_id')!r} (raw "
            f"{rule.get('raw_field_name')!r}) has only "
            f"{len(sample_companies)} sample companies: "
            f"{sample_companies}. Phase H2.2 Sub-A requires ≥ 2 to "
            f"mitigate sampling-bias."
        )


def test_phase_h2_dividends_paid_terminal_for_cn() -> None:
    """dividends_paid: even after sign-normalize, AKShare 70.95B vs Yahoo 68.79B
    has 2.9% residual gap (timing: 已付 vs 宣告)."""
    cn_rules = _load_semantics(SEMANTICS_CN)
    matches = [r for r in cn_rules if r.get("turtle_field_id") == "dividends_paid"]
    assert any(
        r.get("classification") == "provider_semantics_unverified"
        for r in matches
    )


def test_provider_semantics_merge_raises_on_duplicate_rule_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase H2 follow-up: when HK + CN catalogs declare the same lookup key
    (provider, market, turtle_field_id, raw_field_name), the merge must
    fail-loud rather than silently shadow.

    Without the explicit collision check, ProviderSemanticsCatalog.rule_for
    returns the first match and the second rule is silently ignored.
    """
    import json

    from financial_report_llm_extractor.structured_sources import provider_baseline_replay

    duplicate_rule = {
        "provider": "akshare",
        "market": "CN",
        "raw_field_name": "DUPLICATE_FIELD",
        "raw_field_code": "DUPLICATE_FIELD",
        "turtle_field_id": "revenue",
        "semantic_claim": "duplicate rule for collision test",
        "classification": "provider_semantics_unverified",
        "trusted_currency": "CNY",
        "trusted_unit": "yuan",
        "trusted_unit_multiplier": 1,
        "allowed_as_primary": False,
        "related_only_fields": [],
        "negative_examples": [],
        "proof_origin": "sampled_pdf_policy_proof",
        "samples": [],
        "required_proof": [],
    }
    fake_hk = tmp_path / "hk.json"
    fake_cn = tmp_path / "cn.json"
    fake_hk.write_text(json.dumps({"rules": [duplicate_rule]}))
    fake_cn.write_text(json.dumps({"rules": [duplicate_rule]}))

    monkeypatch.setattr(
        provider_baseline_replay, "DEFAULT_PROVIDER_RAW_SEMANTICS_PATH", fake_hk
    )
    monkeypatch.setattr(
        provider_baseline_replay, "DEFAULT_PROVIDER_RAW_SEMANTICS_CN_PATH", fake_cn
    )

    with pytest.raises(ValueError, match="duplicate provider semantics rule keys"):
        provider_baseline_replay._load_replay_provider_semantics_catalog()


def test_phase_h2_cn_akshare_rule_raw_field_name_matches_adapter_alias_map() -> None:
    """Defensive regression for the OPERATE_PROFIT raw_field_name fragility flagged
    by Phase H2 cumulative review.

    AKShare CN wide-row records emit `raw_field_name` per `CN_WIDE_FIELD_ALIASES`:
    when a code IS in the alias map, name = alias value (Chinese); when NOT,
    name = code (uppercase fallback).

    `provider_raw_semantics_cn.json` rules key by `(provider, market,
    turtle_field_id, raw_field_name)`. If someone adds e.g.
    `"OPERATE_PROFIT": "营业利润"` to `CN_WIDE_FIELD_ALIASES`, the existing
    OPERATE_PROFIT rule (raw_field_name="OPERATE_PROFIT") would silently stop
    matching and operating_profit would silently regress to unresolved_conflict.

    This test enforces the cross-file invariant: every akshare CN rule's
    raw_field_name must reflect what the adapter actually emits today.
    """
    from financial_report_llm_extractor.structured_sources.akshare_adapter import (
        CN_WIDE_FIELD_ALIASES,
    )

    flat_aliases: dict[str, str] = {}
    for stmt_aliases in CN_WIDE_FIELD_ALIASES.values():
        flat_aliases.update(stmt_aliases)

    cn_rules = _load_semantics(SEMANTICS_CN)
    akshare_cn_rules = [
        r for r in cn_rules
        if r.get("provider") == "akshare" and r.get("market") == "CN"
    ]
    assert akshare_cn_rules, "expected at least one akshare CN rule to exist"

    for rule in akshare_cn_rules:
        # Rule key for adapter lookup: prefer raw_field_code if present,
        # else fall back to raw_field_name (treated as the upstream code).
        code = rule.get("raw_field_code") or rule.get("raw_field_name")
        actual_name = rule.get("raw_field_name")
        if not isinstance(code, str) or not isinstance(actual_name, str):
            continue  # malformed rule; not this test's concern
        expected_name = flat_aliases.get(code, code)
        assert actual_name == expected_name, (
            f"rule for code={code!r} declares raw_field_name={actual_name!r} "
            f"but akshare adapter emits {expected_name!r} "
            f"(per CN_WIDE_FIELD_ALIASES). Rule will silently miss the candidate "
            f"and the field will regress to unresolved_conflict. Either:\n"
            f"  (a) update raw_field_name in provider_raw_semantics_cn.json to "
            f"{expected_name!r}, OR\n"
            f"  (b) revert the CN_WIDE_FIELD_ALIASES change."
        )
