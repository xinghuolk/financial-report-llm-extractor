"""Decimal precision is the most explicit Phase 1a acceptance criterion.

R1 stores `value` as JSON-encoded text. The client must deserialize numeric
fields as Decimal via `Decimal(str(json.loads(text)))` (the str() detour
prevents float precision loss).
"""

from __future__ import annotations

from decimal import Decimal

import pytest


def test_decode_value_money_string_returns_decimal() -> None:
    """R1 stores money values as stringified-numbers in JSON
    (e.g. '"170899152276.34"'). Client must return Decimal."""
    from financial_report_llm_extractor.client import decode_value

    # JSON-encoded string representation
    result = decode_value(
        value_text='"170899152276.34"', value_type="money",
    )
    assert isinstance(result, Decimal)
    assert result == Decimal("170899152276.34")


def test_decode_value_money_number_returns_decimal_via_str() -> None:
    """If R1 ever stores a value as a JSON number, the str() detour
    must preserve precision."""
    from financial_report_llm_extractor.client import decode_value

    result = decode_value(value_text="0.1", value_type="money")
    assert isinstance(result, Decimal)
    # Critical: Decimal(str(0.1)) == Decimal("0.1"), NOT Decimal(0.1)
    assert result == Decimal("0.1")


def test_decode_value_number_returns_decimal() -> None:
    from financial_report_llm_extractor.client import decode_value

    result = decode_value(value_text="42", value_type="number")
    assert isinstance(result, Decimal)
    assert result == Decimal("42")


def test_decode_value_text_returns_str() -> None:
    from financial_report_llm_extractor.client import decode_value

    result = decode_value(
        value_text='"标准无保留意见"', value_type="text",
    )
    assert isinstance(result, str)
    assert result == "标准无保留意见"


def test_decode_value_boolean_returns_bool() -> None:
    from financial_report_llm_extractor.client import decode_value

    assert decode_value(value_text="true", value_type="boolean") is True
    assert decode_value(value_text="false", value_type="boolean") is False


def test_decode_value_null_returns_none() -> None:
    from financial_report_llm_extractor.client import decode_value

    assert decode_value(value_text=None, value_type="money") is None
    assert decode_value(value_text=None, value_type="text") is None
    assert decode_value(value_text="null", value_type="money") is None


def test_decode_value_unknown_value_type_raises() -> None:
    """Defensive: unknown value_type should surface, not silently coerce."""
    from financial_report_llm_extractor.client import decode_value

    with pytest.raises(ValueError, match="unsupported value_type"):
        decode_value(value_text='"x"', value_type="enum")  # type: ignore[arg-type]
