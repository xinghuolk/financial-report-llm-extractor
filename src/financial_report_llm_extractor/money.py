"""Deterministic money parsing and normalization."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import cast

from financial_report_llm_extractor.models import Currency, MoneyAmount


class MoneyNormalizationError(ValueError):
    """Raised when a monetary value cannot be normalized deterministically."""


def parse_numeric_value(raw_value: str) -> Decimal:
    text = raw_value.strip()
    if text in {"", "-", "—", "–", "－"}:
        raise MoneyNormalizationError("missing numeric value")

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    if text.startswith("-"):
        negative = True
        text = text[1:].strip()

    text = text.replace(",", "")
    try:
        value = Decimal(text)
    except InvalidOperation as error:
        raise MoneyNormalizationError(f"invalid numeric value: {raw_value}") from error
    return -value if negative else value


def resolve_money_unit(
    unit_context: str,
    *,
    currency_hint: str | None = None,
) -> tuple[Currency, str, Decimal, Currency]:
    unit = unit_context.strip()
    currency = _resolve_currency(unit)
    if currency in {"unknown", "ambiguous"} and currency_hint in {"CNY", "HKD", "USD"}:
        currency = cast(Currency, currency_hint)
    if currency in {"unknown", "ambiguous"}:
        raise MoneyNormalizationError("currency is ambiguous")
    multiplier = _resolve_multiplier(unit)
    return currency, unit, multiplier, currency


def normalize_money(
    raw_value: str,
    *,
    unit_context: str,
    currency_hint: str | None = None,
) -> MoneyAmount:
    value = parse_numeric_value(raw_value)
    currency, unit, multiplier, normalized_unit = resolve_money_unit(
        unit_context, currency_hint=currency_hint
    )
    money = MoneyAmount(
        value_raw=raw_value,
        value=value,
        currency=currency,
        unit=unit,
        unit_multiplier=multiplier,
        normalized_value=value * multiplier,
        normalized_unit=normalized_unit,
    )
    money.validate()
    return money


def _resolve_currency(unit: str) -> Currency:
    normalized = unit.lower()
    if any(marker in unit for marker in ("人民币", "元")) or "cny" in normalized or "rmb" in normalized:
        return "CNY"
    if "hkd" in normalized or "hk$" in normalized or "港元" in unit or "港币" in unit:
        return "HKD"
    if "usd" in normalized or "us$" in normalized or "美元" in unit:
        return "USD"
    return "unknown"


def _resolve_multiplier(unit: str) -> Decimal:
    normalized = unit.lower()
    if "billion" in normalized or "十亿元" in unit or "十亿" in unit:
        return Decimal("1000000000")
    if "万亿" in unit:
        return Decimal("1000000000000")
    if "千亿" in unit:
        return Decimal("100000000000")
    if "百亿" in unit:
        return Decimal("10000000000")
    if "亿元" in unit or "亿" in unit:
        return Decimal("100000000")
    if "million" in normalized or "百万元" in unit or "百万" in unit:
        return Decimal("1000000")
    if "万元" in unit or "万" in unit:
        return Decimal("10000")
    if "thousand" in normalized or "千元" in unit or "千" in unit:
        return Decimal("1000")
    return Decimal("1")
