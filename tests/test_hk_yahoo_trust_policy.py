import json
from pathlib import Path

import pytest

from financial_report_llm_extractor.structured_sources.hk_yahoo_trust_policy import (
    HkYahooTrustSample,
    load_hk_yahoo_trust_policy,
    validate_hk_yahoo_trust_policy_samples,
)


POLICY_PATH = (
    Path(__file__).resolve().parents[1]
    / "field_catalog"
    / "hk_yahoo_trust_policy.json"
)


def test_load_hk_yahoo_trust_policy_validates_samples() -> None:
    policy = load_hk_yahoo_trust_policy(POLICY_PATH)

    assert policy.version == 1
    assert policy.market == "HK"
    assert policy.provider == "yahoo"
    verified_samples = [
        sample
        for rule in policy.rules
        if rule.classification == "yahoo_pdf_verified"
        for sample in rule.samples
    ]

    # Phase H1: +2 samples from inventories (00001, 01113).
    # Phase HK-B.5/B.5.2: +6 acct_payable samples (all 6 HK issuers).
    # Phase HK-B.5.3: +4 revenue + 4 net_profit samples for non-HKD issuers.
    # Phase HK-B.6: +4 fix_assets samples (00001/01113/06862/09987 — 4 of 6).
    # Phase HK-B.7: +4 each for total_assets / total_liabilities /
    # total_cur_assets / total_cur_liab / inventories (5 BS aggregates ×
    # 4 non-HKD issuers = 20 new samples; explicit traceability for fields
    # that previously survived backfill via deterministic-candidate path).
    assert len(verified_samples) == 52
    assert {sample.pdf_page > 0 for sample in verified_samples} == {True}
    assert policy.rule_for_field("revenue") is not None
    assert policy.is_pdf_verified("revenue") is True

    evidence = policy.build_policy_evidence("total_assets")

    assert evidence["policy_id"] == "hk_yahoo_raw_hkd_pdf_verified:total_assets"
    assert evidence["classification"] == "yahoo_pdf_verified"
    # Phase HK-B.7: total_assets extended with 4 non-HKD samples
    assert evidence["sample_companies"] == [
        "01113", "01810", "02498", "06862", "09987"
    ]
    assert evidence["sample_count"] == 5


def test_hk_yahoo_trust_policy_rejects_bad_multiplier_match(tmp_path: Path) -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["rules"][0]["samples"][0]["expected_yahoo_raw_value"] = "1"
    policy_path = tmp_path / "bad_policy.json"
    policy_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sample arithmetic mismatch"):
        load_hk_yahoo_trust_policy(policy_path)


def test_hk_yahoo_trust_policy_exposes_verified_and_unverified_classifications() -> None:
    policy = load_hk_yahoo_trust_policy(POLICY_PATH)
    gross_profit_rule = policy.rule_for_field("gross_profit")
    net_profit_rule = policy.rule_for_field("net_profit")

    assert policy.is_pdf_verified("total_cur_assets") is True
    assert policy.is_pdf_verified("gross_profit") is False
    assert policy.is_pdf_verified("net_profit") is True
    assert gross_profit_rule is not None
    assert gross_profit_rule.classification == "yahoo_definition_unverified"
    assert net_profit_rule is not None
    assert net_profit_rule.classification == "yahoo_pdf_verified"
    assert net_profit_rule.allowed_yahoo_raw_fields == (
        "Net Income Common Stockholders",
    )
    assert policy.build_policy_evidence("gross_profit")["sample_count"] == 0

    gross_evidence = policy.build_policy_evidence("gross_profit")
    net_evidence = policy.build_policy_evidence("net_profit")

    assert gross_evidence["definition_status_reason"] == (
        "HK formal income statements do not contain a gross profit row; "
        "sampled 00001 (page 134) and 01113 (page 70) both use non-standard "
        "cost structures that prevent direct or derivation-based verification "
        "of Yahoo Gross Profit"
    )
    assert gross_evidence["required_proof"] == (
        "HK issuer with standard gross profit row, or verified "
        "revenue-minus-COGS derivation formula"
    )
    # Phase HK-B.5.3: net_profit extended with 4 non-HKD samples
    # (01810/02498/06862/09987) to recover honest coverage post-HK-B.5.2.
    assert net_evidence["sample_companies"] == [
        "00001", "01113", "01810", "02498", "06862", "09987"
    ]
    assert net_evidence["sample_count"] == 6


def test_hk_yahoo_trust_policy_validates_sample_page_text() -> None:
    policy = load_hk_yahoo_trust_policy(POLICY_PATH)

    def resolver(sample: HkYahooTrustSample) -> str:
        return (
            f"{sample.statement_line}\n"
            f"Reported in {sample.reported_currency} {sample.reported_unit}\n"
            f"{sample.pdf_value}\n"
        )

    validate_hk_yahoo_trust_policy_samples(policy, resolver)


def test_hk_yahoo_trust_policy_rejects_sample_page_text_without_statement_line() -> None:
    policy = load_hk_yahoo_trust_policy(POLICY_PATH)

    def resolver(sample: HkYahooTrustSample) -> str:
        return f"{sample.reported_currency} {sample.reported_unit} {sample.pdf_value}"

    with pytest.raises(ValueError, match="sample statement_line not found on pdf_page"):
        validate_hk_yahoo_trust_policy_samples(policy, resolver)


def test_hk_yahoo_trust_policy_requires_reason_for_definition_unverified_rule(
    tmp_path: Path,
) -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    for rule in payload["rules"]:
        if rule["field_id"] == "gross_profit":
            rule.pop("definition_status_reason", None)
    policy_path = tmp_path / "bad_policy.json"
    policy_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="definition_status_reason is required"):
        load_hk_yahoo_trust_policy(policy_path)


def test_hk_yahoo_trust_policy_requires_proof_for_definition_unverified_rule(
    tmp_path: Path,
) -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    for rule in payload["rules"]:
        if rule["field_id"] == "gross_profit":
            rule.pop("required_proof", None)
    policy_path = tmp_path / "bad_policy.json"
    policy_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="required_proof is required"):
        load_hk_yahoo_trust_policy(policy_path)


def test_hk_yahoo_trust_policy_rejects_non_string_definition_status_reason(
    tmp_path: Path,
) -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    for rule in payload["rules"]:
        if rule["field_id"] == "gross_profit":
            rule["definition_status_reason"] = 1
    policy_path = tmp_path / "bad_policy.json"
    policy_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="definition_status_reason must be a string"):
        load_hk_yahoo_trust_policy(policy_path)


def test_hk_yahoo_trust_policy_defer_tax_liab_is_pdf_verified() -> None:
    policy = load_hk_yahoo_trust_policy(POLICY_PATH)

    assert policy.is_pdf_verified("defer_tax_liab") is True

    rule = policy.rule_for_field("defer_tax_liab")
    assert rule is not None
    assert rule.classification == "yahoo_pdf_verified"
    assert rule.allowed_yahoo_raw_fields == (
        "Non Current Deferred Taxes Liabilities",
    )

    evidence = policy.build_policy_evidence("defer_tax_liab")
    assert evidence["sample_companies"] == ["00001", "01113"]
    assert evidence["sample_count"] == 2
