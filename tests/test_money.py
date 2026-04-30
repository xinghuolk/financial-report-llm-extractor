from decimal import Decimal

import pytest

from financial_report_llm_extractor.money import (
    MoneyNormalizationError,
    normalize_money,
    parse_numeric_value,
    resolve_money_unit,
)


def test_parse_numeric_value_handles_commas_and_parentheses() -> None:
    assert parse_numeric_value("1,234.50") == Decimal("1234.50")
    assert parse_numeric_value("(1,234)") == Decimal("-1234")
    assert parse_numeric_value("-1,234") == Decimal("-1234")


def test_parse_numeric_value_rejects_dash_missing_values() -> None:
    with pytest.raises(MoneyNormalizationError, match="missing numeric value"):
        parse_numeric_value("-")

    with pytest.raises(MoneyNormalizationError, match="missing numeric value"):
        parse_numeric_value("—")


def test_resolve_money_unit_supports_common_currencies_and_scales() -> None:
    assert resolve_money_unit("人民币百万元") == (
        "CNY",
        "人民币百万元",
        Decimal("1000000"),
        "CNY",
    )
    assert resolve_money_unit("HKD million") == (
        "HKD",
        "HKD million",
        Decimal("1000000"),
        "HKD",
    )
    assert resolve_money_unit("US$ thousand") == (
        "USD",
        "US$ thousand",
        Decimal("1000"),
        "USD",
    )


def test_normalize_money_returns_valid_money_amount() -> None:
    money = normalize_money("280,036", unit_context="HKD million")

    assert money.value_raw == "280,036"
    assert money.value == Decimal("280036")
    assert money.currency == "HKD"
    assert money.unit == "HKD million"
    assert money.unit_multiplier == Decimal("1000000")
    assert money.normalized_value == Decimal("280036000000")
    assert money.normalized_unit == "HKD"
    money.validate()


def test_normalize_money_requires_unambiguous_currency() -> None:
    with pytest.raises(MoneyNormalizationError, match="currency is ambiguous"):
        normalize_money("100", unit_context="million")
