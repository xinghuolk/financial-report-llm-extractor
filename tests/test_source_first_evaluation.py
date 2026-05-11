from decimal import Decimal
import json
from pathlib import Path

from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
    SourceMappingEntry,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
)
from financial_report_llm_extractor.structured_sources.source_first_evaluation import (
    SourceFirstEvaluationFixture,
    default_source_first_evaluation_fixtures,
    run_default_source_first_fixture_evaluation,
    run_source_first_evaluation,
)


def test_source_first_evaluation_compares_source_coverage_modes(
    tmp_path: Path,
) -> None:
    fixture = SourceFirstEvaluationFixture(
        report_id="600519",
        records=(
            _record("akshare", "营业收入", "100"),
            _record("yahoo", "Cash And Cash Equivalents", "20"),
        ),
        chunks=(
            _chunk("chunk-revenue", "revenue 100"),
            _chunk("chunk-cash", "cash and cash equivalents 20"),
        ),
    )

    result = run_source_first_evaluation(
        fixtures=(fixture,),
        catalog=_catalog(),
        output_dir=tmp_path,
    )

    report = result.summary["reports"][0]
    assert report["report_id"] == "600519"
    assert report["coverage"]["akshare_only"]["coverage_ratio"] == 0.5
    assert report["coverage"]["yahoo_only"]["coverage_ratio"] == 0.5
    assert report["coverage"]["combined"]["coverage_ratio"] == 1.0
    assert report["coverage"]["combined_pdf_supplement"]["coverage_ratio"] == 1.0
    assert result.output_path == tmp_path / "evaluation_summary.json"


def test_source_first_evaluation_categorizes_remaining_gaps(
    tmp_path: Path,
) -> None:
    fixture = SourceFirstEvaluationFixture(
        report_id="00001",
        records=(
            _record("akshare", "营业收入", "100"),
            _record("yahoo", "Total Revenue", "101"),
        ),
        chunks=(_chunk("chunk-revenue", "revenue 100"),),
    )

    result = run_source_first_evaluation(
        fixtures=(fixture,),
        catalog=_catalog(),
        output_dir=tmp_path,
    )

    gaps = result.summary["reports"][0]["remaining_gaps"]
    assert gaps["source_availability"] == ["cash"]
    assert gaps["llm_review"] == ["revenue"]
    assert gaps["source_mapping"] == []
    assert gaps["pdf_supplement"] == []


def test_source_first_evaluation_writes_per_report_artifacts(tmp_path: Path) -> None:
    fixture = SourceFirstEvaluationFixture(
        report_id="01113",
        records=(
            _record("akshare", "营业收入", "100"),
            _record("yahoo", "Cash And Cash Equivalents", "20"),
        ),
        chunks=(
            _chunk("chunk-revenue", "revenue 100"),
            _chunk("chunk-cash", "cash and cash equivalents 20"),
        ),
    )

    run_source_first_evaluation(
        fixtures=(fixture,),
        catalog=_catalog(),
        output_dir=tmp_path,
    )

    report_dir = tmp_path / "01113"
    assert (tmp_path / "evaluation_summary.json").exists()
    assert (report_dir / "source_inventory.jsonl").exists()
    assert (report_dir / "turtle_mapping.json").exists()
    assert (report_dir / "source_coverage_summary.json").exists()
    assert (report_dir / "reconciliation_report.json").exists()
    assert (report_dir / "pdf_evidence_supplement.json").exists()
    assert (report_dir / "extraction_result.json").exists()
    assert (report_dir / "review_summary.json").exists()

    summary = json.loads((tmp_path / "evaluation_summary.json").read_text("utf-8"))
    assert summary["report_count"] == 1


def test_default_source_first_evaluation_fixtures_include_validation_reports() -> None:
    fixtures = default_source_first_evaluation_fixtures()

    assert tuple(fixture.report_id for fixture in fixtures) == (
        "600519",
        "00001",
        "01113",
    )


def test_run_default_source_first_fixture_evaluation_writes_summary(
    tmp_path: Path,
) -> None:
    result = run_default_source_first_fixture_evaluation(
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path,
    )

    assert result.summary["report_count"] == 3
    assert result.output_path == tmp_path / "evaluation_summary.json"


def test_source_first_evaluation_script_is_local_fixture_entrypoint() -> None:
    script = Path("scripts/run-source-first-e2e-evaluation.sh").read_text(
        encoding="utf-8"
    )

    assert "source_first_evaluation" in script
    assert "tmp/runs/source_first_evaluation" in script
    assert "DEEPSEEK_API_KEY" not in script
    assert "GEMINI_API_KEY" not in script


def _catalog() -> SourceMappingCatalog:
    return SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "revenue": SourceMappingEntry(
                field_id="revenue",
                priority="P0",
                value_type="money",
                statement_type="income_statement",
                currency_requirement="required",
                unit_requirement="required",
                source_aliases={
                    "akshare": ("营业收入",),
                    "yahoo": ("Total Revenue",),
                },
            ),
            "cash": SourceMappingEntry(
                field_id="cash",
                priority="P0",
                value_type="money",
                statement_type="balance_sheet",
                currency_requirement="required",
                unit_requirement="required",
                source_aliases={
                    "akshare": ("货币资金",),
                    "yahoo": ("Cash And Cash Equivalents",),
                },
            ),
        },
    )


def _record(
    source: str,
    raw_field_name: str,
    raw_value: str,
) -> SourceInventoryRecord:
    return SourceInventoryRecord(
        source=source,  # type: ignore[arg-type]
        market="CN" if source == "akshare" else "US",
        ticker="600519" if source == "akshare" else "600519.SS",
        statement_type="income_statement",
        period="2024-12-31",
        raw_field_name=raw_field_name,
        raw_value=raw_value,
        parsed_numeric_value=Decimal(raw_value),
        currency="CNY",
        unit="yuan",
        scope="consolidated",
        source_evidence=(
            SourceEvidence(
                source=source,  # type: ignore[arg-type]
                adapter=source,
                function="fixture",
                artifact_id=f"{source}_artifact",
                raw_record_id=f"{source}:{raw_field_name}",
                raw_field_name=raw_field_name,
            ),
        ),
    )


def _chunk(chunk_id: str, text: str) -> dict[str, object]:
    return {
        "record_type": "chunk",
        "chunk_id": chunk_id,
        "kind": "statement_table",
        "page_start": 10,
        "page_end": 10,
        "block_ids": ["p0010_b0001"],
        "block_texts": {"p0010_b0001": text},
        "text": text,
    }
