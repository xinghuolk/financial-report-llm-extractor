"""Tests for alias_matching (spec rev 2 component 1)."""
from __future__ import annotations

from financial_report_llm_extractor.structured_sources.alias_matching import (
    AliasMatch,
    match_alias,
    normalize_phrase,
)


def test_normalize_lowercases_and_folds_whitespace() -> None:
    assert normalize_phrase("Tax  Paid\n today") == "tax paid today"


def test_normalize_folds_apostrophes() -> None:
    # ASCII and U+2019; apostrophe fold happens before plural fold,
    # so auditor's -> auditors -> auditor.
    assert normalize_phrase("auditor's opinion") == "auditor opinion"
    assert normalize_phrase("auditor’s opinion") == "auditor opinion"


def test_normalize_folds_hyphens_to_spaces() -> None:
    # 'loss' -> 'los' is the trailing-s strip, not the hyphen rule (symmetric)
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


def test_match_exact_is_whitespace_folded_substring() -> None:
    m: AliasMatch | None = match_alias("tax paid", "Income taxes.  Tax  paid (5,571)")
    assert m is not None
    assert m.kind == "exact"
    assert m.count == 1


def test_match_exact_counts_occurrences() -> None:
    m = match_alias("revenue", "Revenue 280,036  total revenue note")
    assert m is not None and m.kind == "exact" and m.count == 2


def test_match_normalized_recovers_original_phrasing() -> None:
    # The motivating 00001 case: alias misses on inserted "the".
    text = (
        "The ageing analysis of the trade receivables, presented based "
        "on the invoice date, is as follows"
    )
    m = match_alias("ageing analysis of trade receivables", text)
    assert m is not None
    assert m.kind == "normalized"
    assert m.matched_text == "ageing analysis of the trade receivables,"


def test_match_normalized_plural_and_hyphen() -> None:
    m = match_alias("related party transactions", "39 Related parties transactions Except")
    assert m is not None and m.kind == "normalized"
    m2 = match_alias("one-off items", "certain one-time items in the year")
    # 'one-off' vs 'one-time' differ in tokens -> still no match (synonyms
    # are out of scope; catalog gains 'one-time' via suggested_aliases of
    # OTHER aliases or manual addition).
    assert m2 is None


def test_match_chinese_exact() -> None:
    m = match_alias("应收账款账龄", "本期 应收账款账龄 分析如下")
    assert m is not None and m.kind == "exact"


def test_match_none_when_absent() -> None:
    assert match_alias("research and development", "no such topic here") is None


def test_exact_preempts_normalized() -> None:
    # When the literal alias is present, kind must be exact even though
    # the normalized form also matches.
    m = match_alias("treasury shares", "did not hold any treasury shares")
    assert m is not None and m.kind == "exact"
