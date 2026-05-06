from financial_report_llm_extractor.structured_sources.source_mapping_expansion import (
    CandidateDecision,
    _decisions_from_candidate_report,
    decide_candidate_promotion,
    write_source_mapping_expansion_review,
)
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    write_provider_field_candidate_report,
)

import json
from pathlib import Path


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


def test_decide_candidate_promotion_blocks_later_alias_conflict() -> None:
    decision = decide_candidate_promotion(
        _candidate(raw_field_name="BOND_PAYABLE", raw_field_code="BOND_PAYABLE_CODE"),
        existing_aliases_by_source={
            "akshare": {
                "BOND_PAYABLE": "bond_payable",
                "BOND_PAYABLE_CODE": "other_field",
            }
        },
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


def test_decide_candidate_promotion_defers_when_candidate_alias_already_mapped() -> None:
    decision = decide_candidate_promotion(
        _candidate(raw_field_name="BOND_PAYABLE", raw_field_code="BOND_PAYABLE_CODE"),
        existing_aliases_by_source={"akshare": {"BOND_PAYABLE": "bond_payable"}},
    )

    assert decision.action == "defer"
    assert decision.reason == "candidate already mapped"
    assert decision.aliases == ()


def test_decisions_from_candidate_report_reserves_batch_promotions() -> None:
    decisions = _decisions_from_candidate_report(
        {
            "fields": {
                "alpha_field": {
                    "providers": {
                        "akshare": {
                            "candidates": [
                                _candidate(
                                    field_id="ignored",
                                    source="ignored",
                                    raw_field_name="SHARED_ALIAS",
                                    raw_field_code=None,
                                )
                            ]
                        }
                    }
                },
                "beta_field": {
                    "providers": {
                        "akshare": {
                            "candidates": [
                                _candidate(
                                    field_id="ignored",
                                    source="ignored",
                                    raw_field_name="SHARED_ALIAS",
                                    raw_field_code=None,
                                )
                            ]
                        }
                    }
                },
            }
        },
        existing_aliases_by_source={"akshare": {}},
    )

    assert decisions == (
        CandidateDecision(
            field_id="alpha_field",
            source="akshare",
            raw_field_name="SHARED_ALIAS",
            raw_field_code=None,
            action="promote",
            reason="strong deterministic candidate",
            aliases=("SHARED_ALIAS",),
        ),
        CandidateDecision(
            field_id="beta_field",
            source="akshare",
            raw_field_name="SHARED_ALIAS",
            raw_field_code=None,
            action="block",
            reason="alias already belongs to alpha_field",
            aliases=(),
        ),
    )


def test_write_source_mapping_expansion_review_uses_real_candidate_report(
    tmp_path: Path,
) -> None:
    candidate_result = write_provider_field_candidate_report(
        taxonomy_path=Path("field_catalog/turtle_v015_field_taxonomy.json"),
        mapping_catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        inventory_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz"
        ),
        summary_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/"
            "provider_field_inventory_summary.json"
        ),
        output_dir=tmp_path / "candidate_report",
        priorities=("P0", "P1"),
    )

    result = write_source_mapping_expansion_review(
        candidate_report_path=candidate_result.json_path,
        mapping_catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path / "review",
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    deferred_pairs_by_reason = {
        (item["field_id"], item["source"]): item["reason"]
        for item in payload["deferred"]
    }
    all_decisions = {
        (item["field_id"], item["source"]): item
        for section in ("promoted", "deferred", "blocked")
        for item in payload[section]
    }
    defer_tax_decisions = [
        item
        for section in ("promoted", "deferred", "blocked")
        for item in payload[section]
        if item["field_id"] == "defer_tax_liab"
    ]
    markdown = result.markdown_path.read_text(encoding="utf-8")

    assert deferred_pairs_by_reason[("bond_payable", "akshare")] == (
        "candidate already mapped"
    )
    assert deferred_pairs_by_reason[("financing_cash_flow", "yahoo")] == (
        "candidate already mapped"
    )
    assert payload["summary"]["promoted_count"] == 0
    assert payload["summary"]["deferred_count"] > 0
    assert payload["summary"]["no_candidate_count"] >= 0
    assert defer_tax_decisions
    assert ("defer_tax_liab", "akshare") in all_decisions or (
        "defer_tax_liab",
        "yahoo",
    ) in all_decisions
    assert not any(item["action"] == "promote" for item in defer_tax_decisions)
    assert "# Source Mapping Expansion Review" in markdown
    assert "## Promoted" in markdown
    assert "## Deferred" in markdown
    assert "## Blocked" in markdown
    assert "## No Provider Candidates" in markdown
    assert "bond_payable" in markdown
