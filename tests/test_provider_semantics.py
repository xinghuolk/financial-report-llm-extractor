from pathlib import Path

import pytest

from financial_report_llm_extractor.structured_sources.provider_semantics import (
    load_provider_semantics_catalog,
)


CATALOG = Path("field_catalog/provider_raw_semantics_hk.json")


def test_loads_hk_yahoo_net_profit_semantics() -> None:
    catalog = load_provider_semantics_catalog(CATALOG)

    rule = catalog.require_rule(
        provider="yahoo",
        market="HK",
        turtle_field_id="net_profit",
        raw_field_name="Net Income Common Stockholders",
    )

    assert rule.allowed_as_primary is True
    assert rule.classification == "provider_semantics_sample_verified"
    assert rule.proof_origin == "sampled_pdf_policy_proof"
    assert rule.trusted_currency == "HKD"
    assert rule.trusted_unit == "raw"
    assert rule.trusted_unit_multiplier == 1
    assert "Net Income" in rule.related_only_fields
    assert (
        "Net Income From Continuing Operation Net Minority Interest"
        in rule.related_only_fields
    )


def test_gross_profit_is_not_primary_without_semantics_proof() -> None:
    catalog = load_provider_semantics_catalog(CATALOG)

    rule = catalog.require_rule(
        provider="yahoo",
        market="HK",
        turtle_field_id="gross_profit",
        raw_field_name="Gross Profit",
    )

    assert rule.allowed_as_primary is False
    assert rule.classification == "provider_semantics_unverified"
    assert rule.required_proof


def test_related_fields_cannot_also_be_primary(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        """
{
  "rules": [
    {
      "provider": "yahoo",
      "market": "HK",
      "raw_field_name": "Net Income Common Stockholders",
      "raw_field_code": null,
      "turtle_field_id": "net_profit",
      "semantic_claim": "profit attributable to ordinary shareholders",
      "classification": "provider_semantics_sample_verified",
      "trusted_currency": "HKD",
      "trusted_unit": "raw",
      "trusted_unit_multiplier": 1,
      "allowed_as_primary": true,
      "related_only_fields": ["Net Income Common Stockholders"],
      "negative_examples": [],
      "proof_origin": "sampled_pdf_policy_proof",
      "samples": [],
      "required_proof": []
    }
  ]
}
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="related_only_fields must not include raw_field_name",
    ):
        load_provider_semantics_catalog(path)


def test_defer_tax_liab_yahoo_hk_is_verified_primary() -> None:
    catalog = load_provider_semantics_catalog(CATALOG)

    rule = catalog.require_rule(
        provider="yahoo",
        market="HK",
        turtle_field_id="defer_tax_liab",
        raw_field_name="Non Current Deferred Taxes Liabilities",
    )

    assert rule.allowed_as_primary is True
    assert rule.classification == "provider_semantics_sample_verified"
    assert rule.proof_origin == "sampled_pdf_policy_proof"
    assert rule.trusted_currency == "HKD"
    assert rule.trusted_unit == "raw"
    assert rule.trusted_unit_multiplier == 1
    assert "Current Deferred Taxes Liabilities" in rule.negative_examples
    assert len(rule.samples) == 2


def test_gross_profit_yahoo_hk_has_statement_format_incompatible_reason() -> None:
    catalog = load_provider_semantics_catalog(CATALOG)

    rule = catalog.require_rule(
        provider="yahoo",
        market="HK",
        turtle_field_id="gross_profit",
        raw_field_name="Gross Profit",
    )

    assert rule.allowed_as_primary is False
    assert rule.classification == "provider_semantics_unverified"
    assert rule.proof_origin == "hk_statement_format_incompatible"


def test_gross_profit_akshare_hk_has_statement_format_incompatible_reason() -> None:
    catalog = load_provider_semantics_catalog(CATALOG)

    rule = catalog.require_rule(
        provider="akshare",
        market="HK",
        turtle_field_id="gross_profit",
        raw_field_name="毛利",
    )

    assert rule.allowed_as_primary is False
    assert rule.classification == "provider_semantics_unverified"
    assert rule.proof_origin == "hk_statement_format_incompatible"
