from decimal import Decimal
import json
from pathlib import Path

from financial_report_llm_extractor.structured_sources.mapping import (
    MappedTurtleField,
    TurtleMappingCandidate,
    TurtleMappingResult,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceName,
)
from financial_report_llm_extractor.structured_sources.reconciliation import (
    reconcile_mapped_fields,
    write_reconciliation_report,
)


def test_reconcile_marks_equal_candidates_equivalent() -> None:
    result = _result(
        "revenue",
        _field(
            "revenue",
            _candidate("akshare", Decimal("100")),
            _candidate("yahoo", Decimal("100")),
        ),
    )

    report = reconcile_mapped_fields(result)

    assert report.items["revenue"].status == "equivalent"
    assert report.items["revenue"].reason == "candidate normalized values are equal"


def test_reconcile_treats_provider_unit_labels_as_equivalent_when_canonical_units_match() -> None:
    result = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "cash": MappedTurtleField(
                field_id="cash",
                status="ambiguous",
                candidates=(
                    _candidate(
                        "akshare",
                        Decimal("51690610946.5"),
                        unit="yuan",
                        canonical_unit="CNY",
                    ),
                    _candidate(
                        "yahoo",
                        Decimal("51690610946.5"),
                        unit="raw",
                        canonical_unit="CNY",
                    ),
                ),
                errors=("multiple source candidates matched catalog aliases",),
            )
        },
    )

    report = reconcile_mapped_fields(result)

    item = report.items["cash"]
    assert item.status == "equivalent"
    assert item.reason == "candidate normalized values are equal"
    assert item.max_difference == Decimal("0.0")


def test_reconcile_marks_different_values_conflict() -> None:
    result = _result(
        "revenue",
        _field(
            "revenue",
            _candidate("akshare", Decimal("100")),
            _candidate("yahoo", Decimal("101")),
        ),
    )

    report = reconcile_mapped_fields(result)

    assert report.items["revenue"].status == "conflict"
    assert report.items["revenue"].reason == "candidate normalized values differ"
    assert report.conflict_fields == ("revenue",)


def test_reconcile_keeps_same_canonical_unit_value_disagreements_as_conflicts() -> None:
    result = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "revenue": MappedTurtleField(
                field_id="revenue",
                status="ambiguous",
                candidates=(
                    _candidate(
                        "akshare",
                        Decimal("168838102514.79"),
                        unit="yuan",
                        canonical_unit="CNY",
                    ),
                    _candidate(
                        "yahoo",
                        Decimal("172054171890.91"),
                        unit="raw",
                        canonical_unit="CNY",
                    ),
                ),
                errors=("multiple source candidates matched catalog aliases",),
            )
        },
    )

    report = reconcile_mapped_fields(result)

    item = report.items["revenue"]
    assert item.status == "conflict"
    assert item.reason == "candidate normalized values differ"
    assert item.max_difference == Decimal("3216069376.12")


def test_reconcile_conflicts_when_canonical_units_differ() -> None:
    result = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "cash": MappedTurtleField(
                field_id="cash",
                status="ambiguous",
                candidates=(
                    _candidate("akshare", Decimal("100"), canonical_unit="CNY"),
                    _candidate(
                        "yahoo",
                        Decimal("100"),
                        unit="raw",
                        canonical_unit="HKD",
                    ),
                ),
                errors=("multiple source candidates matched catalog aliases",),
            )
        },
    )

    report = reconcile_mapped_fields(result)

    item = report.items["cash"]
    assert item.status == "conflict"
    assert item.reason == "candidate canonical units differ"


def test_reconcile_conflicts_when_known_scopes_differ() -> None:
    result = _result(
        "revenue",
        _field(
            "revenue",
            _candidate("akshare", Decimal("100"), scope="consolidated"),
            _candidate("yahoo", Decimal("100"), scope="standalone"),
            _candidate("eastmoney", Decimal("100"), scope="unknown"),
        ),
    )

    report = reconcile_mapped_fields(result)

    assert report.items["revenue"].status == "conflict"
    assert report.items["revenue"].reason == "candidate scopes differ"


def test_reconcile_ignores_unknown_scope_when_known_scope_matches() -> None:
    result = _result(
        "revenue",
        _field(
            "revenue",
            _candidate("akshare", Decimal("100"), scope="consolidated"),
            _candidate("yahoo", Decimal("100"), unit="raw", scope="unknown"),
        ),
    )

    report = reconcile_mapped_fields(result)

    assert report.items["revenue"].status == "equivalent"
    assert report.items["revenue"].reason == "candidate normalized values are equal"


def test_reconcile_marks_close_values_within_tolerance() -> None:
    result = _result(
        "revenue",
        _field(
            "revenue",
            _candidate("akshare", Decimal("100.00")),
            _candidate("yahoo", Decimal("100.01")),
        ),
    )

    report = reconcile_mapped_fields(result, tolerance=Decimal("0.01"))

    assert report.items["revenue"].status == "close"
    assert report.items["revenue"].max_difference == Decimal("0.01")
    assert report.conflict_fields == ()


def test_reconcile_marks_one_candidate_single_source() -> None:
    result = _result(
        "revenue",
        MappedTurtleField(
            field_id="revenue",
            status="present",
            candidates=(_candidate("akshare", Decimal("100")),),
        ),
    )

    report = reconcile_mapped_fields(result)

    assert report.items["revenue"].status == "single_source"
    assert report.items["revenue"].sources == ("akshare",)


def test_reconcile_marks_metadata_mismatch_conflict() -> None:
    result = _result(
        "revenue",
        _field(
            "revenue",
            _candidate("akshare", Decimal("100"), period="2024-12-31"),
            _candidate("yahoo", Decimal("100"), period="2023-12-31"),
        ),
    )

    report = reconcile_mapped_fields(result)

    assert report.items["revenue"].status == "conflict"
    assert report.items["revenue"].reason == "candidate periods differ"


def test_write_reconciliation_report_writes_json(tmp_path: Path) -> None:
    result = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "revenue": _field(
                "revenue",
                _candidate("akshare", Decimal("100")),
                _candidate("yahoo", Decimal("101")),
            ),
            "cash": MappedTurtleField(
                field_id="cash",
                status="present",
                candidates=(_candidate("akshare", Decimal("20")),),
            ),
        },
    )
    report = reconcile_mapped_fields(result)

    path = write_reconciliation_report(report, tmp_path / "reconciliation_report.json")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["catalog_id"] == "test"
    assert payload["status_counts"] == {"conflict": 1, "single_source": 1}
    assert payload["conflict_fields"] == ["revenue"]
    assert payload["items"]["cash"]["status"] == "single_source"


def _result(field_id: str, field: MappedTurtleField) -> TurtleMappingResult:
    return TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={field_id: field},
    )


def _field(
    field_id: str,
    *candidates: TurtleMappingCandidate,
) -> MappedTurtleField:
    return MappedTurtleField(
        field_id=field_id,
        status="ambiguous",
        candidates=candidates,
    )


def _candidate(
    source: SourceName,
    normalized_value: Decimal,
    *,
    period: str = "2024-12-31",
    currency: str = "CNY",
    unit: str = "yuan",
    canonical_unit: str | None = "CNY",
    scope: str = "consolidated",
) -> TurtleMappingCandidate:
    return TurtleMappingCandidate(
        source=source,
        raw_field_name="Revenue",
        raw_field_code=None,
        raw_value=str(normalized_value),
        value=normalized_value,
        normalized_value=normalized_value,
        currency=currency,  # type: ignore[arg-type]
        unit=unit,
        canonical_unit=canonical_unit,  # type: ignore[arg-type]
        period=period,
        scope=scope,
        source_evidence=(
            SourceEvidence(
                source=source,
                adapter=source,
                function="fixture",
                artifact_id=f"{source}_artifact",
                raw_record_id=f"{source}:revenue",
                raw_field_name="Revenue",
            ),
        ),
    )
