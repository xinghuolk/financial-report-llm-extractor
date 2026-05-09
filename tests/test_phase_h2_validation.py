"""Phase H2: locked-in field-bucket expectations."""

from __future__ import annotations

import json
from pathlib import Path


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


def test_phase_h2_sga_and_da_have_unverified_rules() -> None:
    """SGA: catalog derivation only supports A-B; addition is out of scope.
    D&A: AKShare FA_IR_DEPR is fixed-asset-only; semantically unequal to
    Yahoo D&A (which includes intangibles amortization).
    Both stay terminal_unverified across CN+HK in H2."""
    cn_rules = _load_semantics(SEMANTICS_CN)
    hk_rules = _load_semantics(SEMANTICS_HK)

    for field_id in ("selling_general_administrative", "depreciation_amortization"):
        cn_match = [r for r in cn_rules if r.get("turtle_field_id") == field_id]
        hk_match = [r for r in hk_rules if r.get("turtle_field_id") == field_id]
        assert any(
            r.get("classification") == "provider_semantics_unverified"
            for r in cn_match + hk_match
        ), f"{field_id} must have at least one provider_semantics_unverified rule"


def test_phase_h2_dividends_paid_terminal_for_cn() -> None:
    """dividends_paid: even after sign-normalize, AKShare 70.95B vs Yahoo 68.79B
    has 2.9% residual gap (timing: 已付 vs 宣告)."""
    cn_rules = _load_semantics(SEMANTICS_CN)
    matches = [r for r in cn_rules if r.get("turtle_field_id") == "dividends_paid"]
    assert any(
        r.get("classification") == "provider_semantics_unverified"
        for r in matches
    )


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
