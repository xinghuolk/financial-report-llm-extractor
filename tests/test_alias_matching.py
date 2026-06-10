"""Tests for alias_matching (spec rev 2 component 1)."""
from __future__ import annotations

from financial_report_llm_extractor.structured_sources.alias_matching import (
    normalize_phrase,
)


def test_normalize_lowercases_and_folds_whitespace() -> None:
    assert normalize_phrase("Tax  Paid\n today") == "tax paid today"


def test_normalize_folds_apostrophes() -> None:
    # ASCII and U+2019; apostrophe fold happens before plural fold,
    # so auditor's -> auditors -> auditor.
    assert normalize_phrase("auditor's opinion") == "auditor opinion"
    assert normalize_phrase("auditor's opinion") == "auditor opinion"


def test_normalize_folds_hyphens_to_spaces() -> None:
    assert normalize_phrase("one-time loss") == "one time los"


def test_normalize_plural_ies_to_y() -> None:
    assert normalize_phrase("related parties") == "related party"


def test_normalize_strips_trailing_s_only_for_long_tokens() -> None:
    # len > 3 guard: 'as'/'is' untouched (this guard supersedes the
    # rule-ordering concern from spec review: no 'as'->'a' asymmetry).
    assert normalize_phrase("payments as is") == "payment as is"


def test_normalize_drops_stop_tokens() -> None:
    assert (
        normalize_phrase("ageing analysis of the trade receivables")
        == "ageing analysi of trade receivable"
    )


def test_normalize_chinese_passthrough() -> None:
    # CJK aliases have no whitespace tokens / hyphens / trailing s.
    assert normalize_phrase("应收账款账龄") == "应收账款账龄"
    assert normalize_phrase("非经常性损益") == "非经常性损益"


def test_normalize_does_not_mangle_numbers_or_units() -> None:
    assert normalize_phrase("HK$ 5,571 million") == "hk$ 5,571 million"


def test_normalize_strips_edge_punctuation_before_plural_fold() -> None:
    # PDF tokens carry punctuation: "receivables," must still fold.
    assert normalize_phrase("trade receivables,") == "trade receivable"
    assert normalize_phrase("(5,571)") == "5,571"
