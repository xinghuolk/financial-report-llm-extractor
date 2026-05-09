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
