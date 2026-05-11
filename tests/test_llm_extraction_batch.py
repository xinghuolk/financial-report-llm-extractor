"""Tests for the concurrent multi-company LLM extraction batch runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from financial_report_llm_extractor.field_metadata import (
    FieldDomain,
    FieldTaxonomyCatalog,
    FieldTaxonomyEntry,
    FieldValueType,
    Priority,
    StatementType,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
    SourceMappingEntry,
    SourceValueType,
)
from financial_report_llm_extractor.structured_sources.llm_extraction_batch import (
    BatchSummary,
    CompanyInput,
    load_manifest,
    run_batch,
)


_REPO_ROOT = Path(__file__).resolve().parents[1]


class _CannedJsonClient:
    """Returns canned per-field response."""

    def __init__(self, response: dict[str, object]) -> None:
        self._response = response

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        del system_prompt, user_payload
        return self._response


def _entry(field_id: str) -> SourceMappingEntry:
    return SourceMappingEntry(
        field_id=field_id,
        priority=cast(Priority, "P0"),
        value_type=cast(SourceValueType, "money"),
        statement_type=cast(StatementType, "income_statement"),
        currency_requirement="required",
        unit_requirement="required",
        source_aliases={"akshare": ("X",)},
        pdf_aliases=("revenue", "营业收入", "operating revenue"),
    )


def _tax_entry(field_id: str) -> FieldTaxonomyEntry:
    return FieldTaxonomyEntry(
        field_id=field_id,
        priority=cast(Priority, "P0"),
        domain=cast(FieldDomain, "income_statement"),
        statement_type=cast(StatementType, "income_statement"),
        value_type=cast(FieldValueType, "money"),
        source_mode="direct",
        period_type="duration",
        scope_expectation="consolidated",
        currency_requirement="required",
        unit_requirement="required",
        evidence_requirement="source_only_allowed",
        fallback_policy="pdf_allowed",
        description="operating revenue",
    )


def _catalog() -> SourceMappingCatalog:
    return SourceMappingCatalog(
        catalog_id="test", version="1",
        entries={"revenue": _entry("revenue")},
    )


def _taxonomy() -> FieldTaxonomyCatalog:
    return FieldTaxonomyCatalog(
        catalog_id="test_taxonomy",
        version="1",
        source_priority_catalog="prio",
        fields={"revenue": _tax_entry("revenue")},
    )


def test_load_manifest_parses_company_pdf_pairs(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps([
        {"company_id": "00001", "pdf_path": "downloads/a.pdf"},
        {"company_id": "01113", "pdf_path": "downloads/b.pdf"},
    ]), encoding="utf-8")

    companies = load_manifest(manifest_path)

    assert len(companies) == 2
    assert companies[0].company_id == "00001"
    assert companies[0].pdf_path == Path("downloads/a.pdf")
    assert companies[1].company_id == "01113"


def test_load_manifest_rejects_non_list_payload(tmp_path: Path) -> None:
    manifest_path = tmp_path / "bad.json"
    manifest_path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest must be a list"):
        load_manifest(manifest_path)


def test_load_manifest_rejects_missing_fields(tmp_path: Path) -> None:
    manifest_path = tmp_path / "bad.json"
    manifest_path.write_text(json.dumps([{"company_id": "x"}]), encoding="utf-8")

    with pytest.raises(ValueError, match="missing"):
        load_manifest(manifest_path)


def test_run_batch_isolates_failures_per_company(tmp_path: Path) -> None:
    """Verify that one company's ingest failure does not abort the batch.

    Uses non-existent PDF path for one company to trigger ingest_failed.
    """
    out_dir = tmp_path / "batch_out"
    chunks_fixture = (
        _REPO_ROOT / "tests" / "fixtures" / "pdf_chunks" / "00001_2025_chunks.jsonl"
    )
    assert chunks_fixture.exists(), "00001 chunks fixture must exist"

    # Pre-stage chunks for company A so its run skips ingest+chunk and goes
    # straight to extraction.
    company_a_dir = out_dir / "GOOD" / "ingest"
    company_a_dir.mkdir(parents=True)
    (company_a_dir / "chunks.jsonl").write_text(
        chunks_fixture.read_text(encoding="utf-8"), encoding="utf-8",
    )

    companies = (
        CompanyInput(company_id="GOOD", pdf_path=Path("downloads/fake.pdf")),
        CompanyInput(company_id="BAD", pdf_path=Path("/nonexistent/missing.pdf")),
    )

    canned_response = {
        "field_id": "revenue", "found": True, "value": "100",
        "currency": "HKD", "unit": "million", "page": 1,
        "statement_line": "revenue 100", "confidence": 0.9,
        "reasoning": "ok",
    }
    client = _CannedJsonClient(canned_response)

    summary: BatchSummary = run_batch(
        companies=companies,
        out_dir=out_dir,
        catalog=_catalog(),
        taxonomy=_taxonomy(),
        client=client,
        workers=2,
    )

    assert summary.total_companies == 2
    assert summary.succeeded == 1
    assert summary.failed == 1

    by_id = {c.company_id: c for c in summary.companies}
    assert by_id["GOOD"].status == "ok"
    assert "revenue" in by_id["GOOD"].fields_present
    assert by_id["BAD"].status == "ingest_failed"
    assert by_id["BAD"].error is not None

    # batch_summary.json must be well-formed
    payload = json.loads(summary.summary_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "llm-extraction-batch-summary-v1"
    assert payload["total_companies"] == 2
    assert payload["succeeded"] == 1
    assert payload["failed"] == 1


def test_run_batch_writes_per_company_artifact(tmp_path: Path) -> None:
    """Verify each successful company gets its own llm_evidence_supplement.json."""
    out_dir = tmp_path / "batch_out"
    chunks_fixture = (
        _REPO_ROOT / "tests" / "fixtures" / "pdf_chunks" / "00001_2025_chunks.jsonl"
    )

    for cid in ["A", "B"]:
        d = out_dir / cid / "ingest"
        d.mkdir(parents=True)
        (d / "chunks.jsonl").write_text(
            chunks_fixture.read_text(encoding="utf-8"), encoding="utf-8",
        )

    companies = (
        CompanyInput(company_id="A", pdf_path=Path("downloads/a.pdf")),
        CompanyInput(company_id="B", pdf_path=Path("downloads/b.pdf")),
    )

    canned = {
        "field_id": "revenue", "found": True, "value": "200",
        "currency": "HKD", "unit": "million", "page": 1,
        "statement_line": "revenue 200", "confidence": 0.9,
        "reasoning": "ok",
    }
    client = _CannedJsonClient(canned)

    run_batch(
        companies=companies,
        out_dir=out_dir,
        catalog=_catalog(),
        taxonomy=_taxonomy(),
        client=client,
        workers=2,
    )

    for cid in ["A", "B"]:
        art = out_dir / cid / "llm_evidence_supplement.json"
        assert art.exists(), f"missing artifact for {cid}"
        payload = json.loads(art.read_text(encoding="utf-8"))
        assert payload["company_id"] == cid
        assert payload["items"]["revenue"]["value"] == "200"


class _RaisingJsonClient:
    """Always raises on complete_json, to test extraction_failed handling."""

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        del system_prompt, user_payload
        raise RuntimeError("simulated LLM transport failure")


def test_run_batch_records_extraction_failed_when_llm_raises(tmp_path: Path) -> None:
    """Phase I-A.2 review fix: cover the extraction_failed code path.
    Existing tests cover ingest_failed but not the inner LLM-call failure."""
    out_dir = tmp_path / "batch_out"
    chunks_fixture = (
        _REPO_ROOT / "tests" / "fixtures" / "pdf_chunks" / "00001_2025_chunks.jsonl"
    )

    company_dir = out_dir / "TEST" / "ingest"
    company_dir.mkdir(parents=True)
    (company_dir / "chunks.jsonl").write_text(
        chunks_fixture.read_text(encoding="utf-8"), encoding="utf-8",
    )

    companies = (CompanyInput(company_id="TEST", pdf_path=Path("downloads/x.pdf")),)
    client = _RaisingJsonClient()

    summary = run_batch(
        companies=companies, out_dir=out_dir,
        catalog=_catalog(), taxonomy=_taxonomy(),
        client=client, workers=1,
    )

    assert summary.total_companies == 1
    # The runner catches exceptions per field and marks the field as
    # extraction_failed; it does NOT mark the whole company as failed.
    # So company status is "ok" but fields are in fields_failed.
    entry = summary.companies[0]
    assert entry.status == "ok"
    assert "revenue" in entry.fields_failed
    assert "revenue" not in entry.fields_present
