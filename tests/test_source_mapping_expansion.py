from financial_report_llm_extractor.structured_sources.source_mapping_expansion import (
    CandidateDecision,
    decide_candidate_promotion,
)


def _candidate(
    *,
    field_id: str = "bond_payable",
    source: str = "akshare",
    raw_field_name: str = "BOND_PAYABLE",
    raw_field_code: str | None = "BOND_PAYABLE",
    strength: str = "strong",
    signals: tuple[str, ...] = ("exact_text", "statement_match", "period_support"),
) -> dict[str, object]:
    return {
        "field_id": field_id,
        "source": source,
        "raw_field_name": raw_field_name,
        "raw_field_code": raw_field_code,
        "score": 90,
        "strength": strength,
        "signals": list(signals),
        "target_count": 1,
        "period_count": 5,
        "record_count": 5,
    }


def test_decide_candidate_promotion_promotes_strong_exact_text_candidate() -> None:
    assert decide_candidate_promotion(
        _candidate(),
        existing_aliases_by_source={"akshare": {}},
    ) == CandidateDecision(
        field_id="bond_payable",
        source="akshare",
        raw_field_name="BOND_PAYABLE",
        raw_field_code="BOND_PAYABLE",
        action="promote",
        reason="strong deterministic candidate",
        aliases=("BOND_PAYABLE",),
    )


def test_decide_candidate_promotion_defers_keyword_overlap_candidate() -> None:
    decision = decide_candidate_promotion(
        _candidate(
            raw_field_name="Accounts Receivable",
            raw_field_code=None,
            strength="medium",
            signals=("keyword_overlap", "statement_match", "period_support"),
        ),
        existing_aliases_by_source={"yahoo": {}},
    )

    assert decision.action == "defer"
    assert decision.reason == "candidate is not strong"
    assert decision.aliases == ()


def test_decide_candidate_promotion_blocks_alias_conflict() -> None:
    decision = decide_candidate_promotion(
        _candidate(raw_field_name="BOND_PAYABLE", raw_field_code="BOND_PAYABLE"),
        existing_aliases_by_source={"akshare": {"BOND_PAYABLE": "other_field"}},
    )

    assert decision.action == "block"
    assert decision.reason == "alias already belongs to other_field"


def test_decide_candidate_promotion_defers_already_mapped_alias() -> None:
    decision = decide_candidate_promotion(
        _candidate(raw_field_name="BOND_PAYABLE", raw_field_code="BOND_PAYABLE"),
        existing_aliases_by_source={"akshare": {"BOND_PAYABLE": "bond_payable"}},
    )

    assert decision.action == "defer"
    assert decision.reason == "candidate already mapped"
    assert decision.aliases == ()
