"""Phase I-A.2 follow-up: concurrent multi-company LLM extraction runner.

Reads a manifest of (company_id, pdf_path) pairs and runs `extract_for_chunks`
in parallel. Each company gets its own output directory; ingest+chunk and the
LLM call happen in worker threads (LLM and pdftotext are IO-bound).
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from financial_report_llm_extractor.chunking import build_chunk_store
from financial_report_llm_extractor.field_metadata import FieldTaxonomyCatalog
from financial_report_llm_extractor.ingestion import ingest_pdf
from financial_report_llm_extractor.llm_field_extraction import JsonClient
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
)
from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
    LlmExtractionRunResult,
    extract_for_chunks,
    load_chunks_jsonl,
    write_llm_evidence_supplement,
)


@dataclass(frozen=True)
class CompanyInput:
    company_id: str
    pdf_path: Path


@dataclass(frozen=True)
class BatchResultEntry:
    company_id: str
    pdf_path: Path
    status: str  # "ok" | "ingest_failed" | "extraction_failed"
    fields_attempted: tuple[str, ...] = ()
    fields_present: tuple[str, ...] = ()
    fields_not_found: tuple[str, ...] = ()
    fields_failed: tuple[str, ...] = ()
    artifact_path: Path | None = None
    error: str | None = None


@dataclass(frozen=True)
class BatchSummary:
    out_dir: Path
    companies: tuple[BatchResultEntry, ...]
    total_companies: int
    succeeded: int
    failed: int
    summary_path: Path


def _process_one_company(
    *,
    company: CompanyInput,
    out_root: Path,
    catalog: SourceMappingCatalog,
    taxonomy: FieldTaxonomyCatalog,
    client: JsonClient,
    priorities: tuple[str, ...],
    fields: tuple[str, ...] | None,
) -> BatchResultEntry:
    company_dir = out_root / company.company_id
    company_dir.mkdir(parents=True, exist_ok=True)
    ingest_dir = company_dir / "ingest"
    chunks_path = ingest_dir / "chunks.jsonl"

    try:
        if not chunks_path.exists():
            ingest_dir.mkdir(parents=True, exist_ok=True)
            ingest_result = ingest_pdf(company.pdf_path, ingest_dir)
            build_chunk_store(
                ingest_result.pages_path,
                ingest_result.metadata_path,
                chunks_path=chunks_path,
            )
        chunks = load_chunks_jsonl(chunks_path)
    except Exception as exc:  # ingest/chunk are IO-heavy; surface failures
        return BatchResultEntry(
            company_id=company.company_id,
            pdf_path=company.pdf_path,
            status="ingest_failed",
            error=f"{type(exc).__name__}: {exc}",
        )

    try:
        result: LlmExtractionRunResult = extract_for_chunks(
            chunks=chunks,
            catalog=catalog,
            taxonomy=taxonomy,
            client=client,
            company_id=company.company_id,
            pdf_path=company.pdf_path,
            out_dir=company_dir,
            priorities=priorities,
            fields=fields,
        )
        write_llm_evidence_supplement(result)
        return BatchResultEntry(
            company_id=company.company_id,
            pdf_path=company.pdf_path,
            status="ok",
            fields_attempted=result.fields_attempted,
            fields_present=result.fields_present,
            fields_not_found=result.fields_not_found,
            fields_failed=result.fields_failed,
            artifact_path=result.artifact_path,
        )
    except Exception as exc:
        return BatchResultEntry(
            company_id=company.company_id,
            pdf_path=company.pdf_path,
            status="extraction_failed",
            error=f"{type(exc).__name__}: {exc}",
        )


def run_batch(
    *,
    companies: tuple[CompanyInput, ...],
    out_dir: Path,
    catalog: SourceMappingCatalog,
    taxonomy: FieldTaxonomyCatalog,
    client: JsonClient,
    priorities: tuple[str, ...] = ("P0", "P1"),
    fields: tuple[str, ...] | None = None,
    workers: int = 3,
) -> BatchSummary:
    """Run extract-llm for multiple companies concurrently.

    Workers are threads (LLM and pdftotext are IO-bound). Each company gets
    a dedicated output directory under `out_dir/{company_id}/`. A combined
    summary is written to `out_dir/batch_summary.json`.

    Failures (ingest, chunk, LLM call) are isolated per-company — one
    company's failure does not abort the batch.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[BatchResultEntry] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {
            executor.submit(
                _process_one_company,
                company=c,
                out_root=out_dir,
                catalog=catalog,
                taxonomy=taxonomy,
                client=client,
                priorities=priorities,
                fields=fields,
            ): c
            for c in companies
        }
        for future in as_completed(future_map):
            results.append(future.result())

    # Sort by company_id for stable output
    results.sort(key=lambda r: r.company_id)

    summary_path = out_dir / "batch_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": "llm-extraction-batch-summary-v1",
                "out_dir": str(out_dir),
                "total_companies": len(results),
                "succeeded": sum(1 for r in results if r.status == "ok"),
                "failed": sum(1 for r in results if r.status != "ok"),
                "companies": [
                    {
                        "company_id": r.company_id,
                        "pdf_path": str(r.pdf_path),
                        "status": r.status,
                        "fields_attempted": list(r.fields_attempted),
                        "fields_present": list(r.fields_present),
                        "fields_not_found": list(r.fields_not_found),
                        "fields_failed": list(r.fields_failed),
                        "artifact_path": (
                            str(r.artifact_path) if r.artifact_path else None
                        ),
                        "error": r.error,
                    }
                    for r in results
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return BatchSummary(
        out_dir=out_dir,
        companies=tuple(results),
        total_companies=len(results),
        succeeded=sum(1 for r in results if r.status == "ok"),
        failed=sum(1 for r in results if r.status != "ok"),
        summary_path=summary_path,
    )


def load_manifest(path: Path) -> tuple[CompanyInput, ...]:
    """Load a JSON manifest: list of {company_id, pdf_path}.

    Schema:
        [
          {"company_id": "00001", "pdf_path": "downloads/.../2025_annual_en.pdf"},
          ...
        ]
    """
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"manifest must be a list, got {type(payload).__name__}")
    out: list[CompanyInput] = []
    for entry in payload:
        if not isinstance(entry, dict):
            raise ValueError(f"manifest entry must be an object, got {entry!r}")
        company_id = entry.get("company_id")
        pdf_path_raw = entry.get("pdf_path")
        if not company_id or not pdf_path_raw:
            raise ValueError(f"manifest entry missing company_id or pdf_path: {entry!r}")
        out.append(CompanyInput(
            company_id=str(company_id),
            pdf_path=Path(str(pdf_path_raw)),
        ))
    return tuple(out)
