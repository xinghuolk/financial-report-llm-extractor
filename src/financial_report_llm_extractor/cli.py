"""Command line interface for financial report extraction."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from financial_report_llm_extractor.chunking import build_chunk_store
from financial_report_llm_extractor.coverage_budget import (
    build_coverage_metrics,
    evaluate_coverage_gate,
    load_catalog_field_ids,
    write_coverage_budget_report,
)
from financial_report_llm_extractor.document_map import (
    write_document_map,
    write_parser_capability_probe,
)
from financial_report_llm_extractor.evaluation import write_review_summary
from financial_report_llm_extractor.extraction import run_fake_extraction
from financial_report_llm_extractor.ingestion import ingest_pdf
from financial_report_llm_extractor.llm_row_discovery import write_llm_row_inventory
from financial_report_llm_extractor.llm_transport import (
    LlmTransportConfig,
    create_llm_client,
    response_json_text,
    run_real_transport_probe,
)
from financial_report_llm_extractor.quick_validation_runner import run_quick_validation
from financial_report_llm_extractor.retrieval import write_retrieval_probe
from financial_report_llm_extractor.statement_discovery import (
    write_catalog_mapping,
    write_row_inventory,
    write_statement_map,
)
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    write_provider_field_candidate_report,
)
from financial_report_llm_extractor.structured_sources.provider_baseline_replay import (
    write_provider_baseline_period_replay,
)
from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
    PeriodSpec,
)
from financial_report_llm_extractor.structured_sources.source_mapping_expansion import (
    write_source_mapping_expansion_review,
)
from financial_report_llm_extractor.subscription_auth import subscription_auth_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="financial-report-llm-extractor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("--pdf", required=True, type=Path)
    ingest_parser.add_argument("--out", required=True, type=Path)

    chunk_parser = subparsers.add_parser("chunk")
    chunk_parser.add_argument("--pages", required=True, type=Path)
    chunk_parser.add_argument("--metadata", required=True, type=Path)
    chunk_parser.add_argument("--out", type=Path)

    probe_parser = subparsers.add_parser("probe-parser")
    probe_parser.add_argument("--pages", required=True, type=Path)
    probe_parser.add_argument("--metadata", required=True, type=Path)
    probe_parser.add_argument("--out", type=Path)

    map_document_parser = subparsers.add_parser("map-document")
    map_document_parser.add_argument("--chunks", required=True, type=Path)
    map_document_parser.add_argument("--out", type=Path)

    map_statements_parser = subparsers.add_parser("map-statements")
    map_statements_parser.add_argument("--chunks", required=True, type=Path)
    map_statements_parser.add_argument("--document-map", required=True, type=Path)
    map_statements_parser.add_argument("--out", type=Path)

    discover_rows_parser = subparsers.add_parser("discover-rows")
    discover_rows_parser.add_argument("--chunks", required=True, type=Path)
    discover_rows_parser.add_argument("--statement-map", required=True, type=Path)
    discover_rows_parser.add_argument("--out", type=Path)

    map_fields_parser = subparsers.add_parser("map-fields")
    map_fields_parser.add_argument("--row-inventory", required=True, type=Path)
    map_fields_parser.add_argument("--fields", required=True)
    map_fields_parser.add_argument("--out", type=Path)

    retrieve_parser = subparsers.add_parser("retrieve")
    retrieve_parser.add_argument("--catalog", required=True, type=Path)
    retrieve_parser.add_argument("--chunks", required=True, type=Path)
    retrieve_parser.add_argument("--out", type=Path)
    retrieve_parser.add_argument("--priorities", default="P0,P1")

    extract_fake_parser = subparsers.add_parser("extract-fake")
    extract_fake_parser.add_argument("--retrieval-probe", required=True, type=Path)
    extract_fake_parser.add_argument("--out", type=Path)

    extract_llm_parser = subparsers.add_parser(
        "extract-llm",
        help="LLM-assisted field extraction from a PDF",
    )
    extract_llm_parser.add_argument("--pdf", required=True, type=Path)
    extract_llm_parser.add_argument("--company-id", required=True)
    extract_llm_parser.add_argument(
        "--catalog", required=True, type=Path,
        help="source mapping catalog JSON",
    )
    extract_llm_parser.add_argument(
        "--taxonomy", required=True, type=Path,
        help="field taxonomy catalog JSON",
    )
    extract_llm_parser.add_argument(
        "--llm-config", required=True, type=Path,
        help="LLM transport config JSON",
    )
    extract_llm_parser.add_argument(
        "--out", required=True, type=Path,
        help="output directory for chunks + evidence supplement",
    )
    extract_llm_parser.add_argument(
        "--fields", default=None,
        help="comma-separated subset of field IDs (default: all)",
    )
    extract_llm_parser.add_argument(
        "--priorities", default="P0,P1",
        help="comma-separated priorities (default: P0,P1)",
    )
    extract_llm_parser.add_argument(
        "--confidence-threshold", type=float, default=None,
        help=(
            "Demote `present` results below this LLM-reported confidence to "
            "extraction_failed with a low_confidence error. Default: no gating."
        ),
    )

    extract_llm_batch_parser = subparsers.add_parser(
        "extract-llm-batch",
        help="LLM-assisted field extraction across multiple PDFs concurrently",
    )
    extract_llm_batch_parser.add_argument(
        "--manifest", required=True, type=Path,
        help="JSON manifest: list of {company_id, pdf_path}",
    )
    extract_llm_batch_parser.add_argument(
        "--catalog", required=True, type=Path,
        help="source mapping catalog JSON",
    )
    extract_llm_batch_parser.add_argument(
        "--taxonomy", required=True, type=Path,
        help="field taxonomy catalog JSON",
    )
    extract_llm_batch_parser.add_argument(
        "--llm-config", required=True, type=Path,
        help="LLM transport config JSON",
    )
    extract_llm_batch_parser.add_argument(
        "--out", required=True, type=Path,
        help="root output directory; per-company subdirectories under it",
    )
    extract_llm_batch_parser.add_argument(
        "--fields", default=None,
        help="comma-separated subset of field IDs (default: all)",
    )
    extract_llm_batch_parser.add_argument(
        "--priorities", default="P0,P1",
        help="comma-separated priorities (default: P0,P1)",
    )
    extract_llm_batch_parser.add_argument(
        "--workers", type=int, default=3,
        help="concurrent worker threads (default: 3)",
    )
    extract_llm_batch_parser.add_argument(
        "--confidence-threshold", type=float, default=None,
        help=(
            "Demote `present` results below this LLM-reported confidence to "
            "extraction_failed. Default: no gating."
        ),
    )

    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("--retrieval-probe", required=True, type=Path)
    extract_parser.add_argument("--config", required=True, type=Path)
    extract_parser.add_argument("--out", type=Path)
    extract_parser.add_argument("--raw-response-dir", type=Path)

    auth_status_parser = subparsers.add_parser("llm-auth-status")
    auth_status_parser.add_argument(
        "--provider",
        required=True,
        choices=["openai-codex", "claude-code"],
    )

    subscription_smoke_parser = subparsers.add_parser("llm-subscription-smoke")
    subscription_smoke_parser.add_argument("--config", required=True, type=Path)
    subscription_smoke_parser.add_argument("--out", required=True, type=Path)

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--root", required=True, type=Path)
    evaluate_parser.add_argument("--out", type=Path)

    quick_validate_parser = subparsers.add_parser("quick-validate")
    quick_validate_parser.add_argument("--pdf", required=True, type=Path)
    quick_validate_parser.add_argument("--report-id", required=True)
    quick_validate_parser.add_argument("--root", required=True, type=Path)

    coverage_budget_parser = subparsers.add_parser("coverage-budget")
    coverage_budget_parser.add_argument("--chunks", required=True, type=Path)
    coverage_budget_parser.add_argument("--catalog", required=True, type=Path)
    coverage_budget_parser.add_argument("--report-id", required=True)
    coverage_budget_parser.add_argument("--priorities", default="P0,P1")
    coverage_budget_parser.add_argument("--fields", default="")
    coverage_budget_parser.add_argument("--top-k-values", default="1,3,5,8")
    coverage_budget_parser.add_argument("--required-top-k", default=3, type=int)
    coverage_budget_parser.add_argument("--max-total-chars", default=40_000, type=int)
    coverage_budget_parser.add_argument("--max-field-chars", default=8_000, type=int)
    coverage_budget_parser.add_argument("--out-dir", required=True, type=Path)

    discover_rows_llm_parser = subparsers.add_parser("discover-rows-llm")
    discover_rows_llm_parser.add_argument("--chunks", required=True, type=Path)
    discover_rows_llm_parser.add_argument("--statement-map", required=True, type=Path)
    discover_rows_llm_parser.add_argument("--config", required=True, type=Path)
    discover_rows_llm_parser.add_argument("--out", required=True, type=Path)
    discover_rows_llm_parser.add_argument("--prompt-dir", required=True, type=Path)
    discover_rows_llm_parser.add_argument("--raw-response-dir", required=True, type=Path)
    discover_rows_llm_parser.add_argument("--parsed-response-dir", required=True, type=Path)

    provider_fields_parser = subparsers.add_parser("discover-provider-fields")
    provider_fields_parser.add_argument("--taxonomy", required=True, type=Path)
    provider_fields_parser.add_argument("--mapping-catalog", required=True, type=Path)
    provider_fields_parser.add_argument("--inventory", required=True, type=Path)
    provider_fields_parser.add_argument("--summary", required=True, type=Path)
    provider_fields_parser.add_argument("--out", required=True, type=Path)
    provider_fields_parser.add_argument("--priorities", default="P0,P1")

    expansion_review_parser = subparsers.add_parser("review-source-mapping-expansion")
    expansion_review_parser.add_argument("--candidate-report", required=True, type=Path)
    expansion_review_parser.add_argument("--mapping-catalog", required=True, type=Path)
    expansion_review_parser.add_argument("--out", required=True, type=Path)

    baseline_replay_parser = subparsers.add_parser("replay-provider-baseline")
    baseline_replay_parser.add_argument("--inventory", required=True, type=Path)
    baseline_replay_parser.add_argument("--inventory-summary", required=True, type=Path)
    baseline_replay_parser.add_argument("--catalog", required=True, type=Path)
    baseline_replay_parser.add_argument(
        "--taxonomy",
        default=Path("field_catalog/turtle_v015_field_taxonomy.json"),
        type=Path,
    )
    baseline_replay_parser.add_argument("--out", required=True, type=Path)
    baseline_replay_parser.add_argument("--hk-yahoo-trust-policy", type=Path)

    fetch_source_parser = subparsers.add_parser(
        "fetch-source-inventory",
        help="Live fetch AKShare/Yahoo data for a single (company, period).",
    )
    fetch_source_parser.add_argument("--company", required=True)
    fetch_source_parser.add_argument("--year", type=int)
    fetch_source_parser.add_argument("--period-end")
    fetch_source_parser.add_argument("--report-type", default="annual")
    fetch_source_parser.add_argument(
        "--market", required=True, choices=["CN", "HK"]
    )
    fetch_source_parser.add_argument("--providers", default="akshare,yahoo")
    fetch_source_parser.add_argument("--out", type=Path, required=True)
    fetch_source_parser.add_argument(
        "--catalog", type=Path, required=True,
        help="Source mapping catalog JSON path.",
    )

    index_parser = subparsers.add_parser("index")
    index_parser.add_argument("--runs", type=Path, required=True,
                              help="Directory containing per-company run subdirs")
    index_parser.add_argument("--db", type=Path, required=True,
                              help="SQLite DB path to create/update")
    index_parser.add_argument(
        "--taxonomy", type=Path,
        default=Path("field_catalog/turtle_v015_field_taxonomy.json"),
        help="Taxonomy JSON for catalog version + priority denormalization",
    )
    index_parser.add_argument(
        "--catalog-version", type=str, default=None,
        help="Override catalog_version (default: from --taxonomy 'version' field)",
    )

    query_parser = subparsers.add_parser("query")
    query_parser.add_argument("--db", type=Path, required=True,
                              help="SQLite DB path")
    query_parser.add_argument("--company", type=str, required=True)
    query_parser.add_argument("--period", type=str, required=True,
                              help="period_end like '2024-12-31'")
    query_parser.add_argument("--field", type=str, default=None,
                              help="Optional field_id; omit for full extraction")

    evaluate_parser = subparsers.add_parser(
        "evaluate-company",
        help="Per-(company, period) source-first + optional LLM evaluation.",
    )
    evaluate_parser.add_argument("--company", required=True)
    evaluate_parser.add_argument("--year", type=int)
    evaluate_parser.add_argument("--period-end")
    evaluate_parser.add_argument("--report-type", default="annual")
    evaluate_parser.add_argument(
        "--market", required=True, choices=["CN", "HK"]
    )
    evaluate_parser.add_argument("--inventory", type=Path, required=True)
    # Informational: not consumed by the orchestrator. Kept optional so users
    # can pass the path produced by fetch-source-inventory for parity.
    evaluate_parser.add_argument("--inventory-summary", type=Path)
    evaluate_parser.add_argument("--catalog", type=Path, required=True)
    evaluate_parser.add_argument("--taxonomy", type=Path, required=True)
    evaluate_parser.add_argument("--pdf", type=Path)
    evaluate_parser.add_argument("--llm-config", type=Path)
    evaluate_parser.add_argument("--priorities", default="P0,P1,P2,P3")
    evaluate_parser.add_argument("--out", type=Path, required=True)

    return parser


def _run_fetch_source_inventory(
    *,
    company: str,
    period: PeriodSpec,
    market: str,
    providers: tuple[str, ...],
    out_dir: Path,
    catalog_path: Path,
) -> None:
    from financial_report_llm_extractor.structured_sources.real_source_validation import (
        PandasAkshareClient,
        YFinanceStatementClient,
    )
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        fetch_source_inventory,
        hk_issuer_financial_currency,
    )

    # Phase HK-B.5.1: HK AKShare records get stamped with the issuer's
    # financial-reporting currency (not the HK trading-market currency).
    # CN companies stay "unknown" — `_fetch_akshare_for_company` uses the
    # explicit "yuan" unit for CN, so currency stamping for CN AKShare comes
    # from a different code path.
    akshare_hk_currency = (
        hk_issuer_financial_currency(company) if market == "HK" else "unknown"
    )
    akshare_client = (
        PandasAkshareClient(hk_default_currency=akshare_hk_currency)
        if "akshare" in providers
        else None
    )
    yahoo_client = YFinanceStatementClient() if "yahoo" in providers else None

    artifact = fetch_source_inventory(
        company=company,
        period=period,
        market=market,  # type: ignore[arg-type]
        providers=providers,  # type: ignore[arg-type]
        akshare_client=akshare_client,
        yahoo_client=yahoo_client,
        out_dir=out_dir,
        catalog_path=catalog_path,
    )
    print(json.dumps({
        "inventory_path": str(artifact.inventory_path),
        "summary_path": str(artifact.summary_path),
        "record_count": artifact.record_count,
    }, indent=2))


def _run_evaluate_company(**kwargs: object) -> None:
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        run_company_evaluation,
    )
    evaluation = run_company_evaluation(**kwargs)  # type: ignore[arg-type]
    print(json.dumps({
        "company": evaluation.company,
        "summary": dict(evaluation.by_bucket),
    }, indent=2))


def _run_subscription_smoke(config_path: Path, out_dir: Path) -> dict[str, object]:
    config = LlmTransportConfig.from_json(config_path)
    if config.provider not in {"openai-codex", "claude-code"}:
        raise SystemExit(
            "subscription smoke requires provider openai-codex or claude-code"
        )
    client = create_llm_client(config)
    prompt: dict[str, object] = {
        "task": "subscription_smoke",
        "provider": config.provider,
        "model": config.model,
        "response_schema": {
            "type": "object",
            "required": ["ok"],
            "properties": {"ok": {"type": "boolean"}},
        },
    }
    raw_response = client.complete_json(
        system_prompt="Return strict JSON for the subscription smoke request.",
        user_payload=prompt,
    )
    parsed = json.loads(response_json_text(raw_response))
    if not isinstance(parsed, dict):
        raise ValueError("subscription smoke response must be a JSON object")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prompt.json").write_text(
        json.dumps(prompt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "raw_response.json").write_text(
        json.dumps(raw_response, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "parsed_response.json").write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "ok": bool(parsed.get("ok")),
        "provider": config.provider,
        "model": config.model,
        "out": str(out_dir),
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "ingest":
        ingest_result = ingest_pdf(args.pdf, args.out)
        print(f"pages={ingest_result.page_count}")
        print(f"pages_path={ingest_result.pages_path}")
        print(f"metadata_path={ingest_result.metadata_path}")
        return 0

    if args.command == "chunk":
        chunk_result = build_chunk_store(
            args.pages,
            args.metadata,
            chunks_path=args.out,
        )
        print(f"blocks={chunk_result.block_count}")
        print(f"chunks={chunk_result.chunk_count}")
        print(f"chunks_path={chunk_result.chunks_path}")
        return 0

    if args.command == "probe-parser":
        parser_probe_result = write_parser_capability_probe(
            args.pages,
            args.metadata,
            output_path=args.out,
        )
        print(f"pages={parser_probe_result.page_count}")
        print(f"parser_capability_path={parser_probe_result.output_path}")
        return 0

    if args.command == "map-document":
        document_map_result = write_document_map(
            args.chunks,
            output_path=args.out,
        )
        print(f"sections={document_map_result.section_count}")
        print(f"document_map_path={document_map_result.output_path}")
        return 0

    if args.command == "map-statements":
        statement_map_result = write_statement_map(
            args.chunks,
            args.document_map,
            output_path=args.out,
        )
        print(f"statements={statement_map_result.statement_count}")
        print(f"statement_map_path={statement_map_result.output_path}")
        return 0

    if args.command == "discover-rows":
        row_inventory_result = write_row_inventory(
            args.chunks,
            args.statement_map,
            output_path=args.out,
        )
        print(f"rows={row_inventory_result.row_count}")
        print(f"row_inventory_path={row_inventory_result.output_path}")
        return 0

    if args.command == "map-fields":
        catalog_mapping_result = write_catalog_mapping(
            args.row_inventory,
            selected_fields=tuple(
                field.strip() for field in args.fields.split(",") if field.strip()
            ),
            output_path=args.out,
        )
        print(f"mappings={catalog_mapping_result.mapping_count}")
        print(f"catalog_mapping_path={catalog_mapping_result.output_path}")
        return 0

    if args.command == "retrieve":
        retrieval_result = write_retrieval_probe(
            args.catalog,
            args.chunks,
            output_path=args.out,
            priorities=tuple(
                priority.strip()
                for priority in args.priorities.split(",")
                if priority.strip()
            ),
        )
        print(f"fields={retrieval_result.field_count}")
        print(f"retrieval_probe_path={retrieval_result.output_path}")
        return 0

    if args.command == "extract-fake":
        extraction_result = run_fake_extraction(
            args.retrieval_probe,
            output_path=args.out,
        )
        print(f"items={extraction_result.item_count}")
        print(f"extraction_result_path={extraction_result.output_path}")
        return 0

    if args.command == "extract":
        real_result = run_real_transport_probe(
            args.retrieval_probe,
            config_path=args.config,
            output_path=args.out,
            raw_response_dir=args.raw_response_dir,
        )
        print(f"items={real_result.item_count}")
        print(f"raw_responses={real_result.raw_response_count}")
        print(f"extraction_result_path={real_result.output_path}")
        return 0

    if args.command == "llm-auth-status":
        status = subscription_auth_status(args.provider)
        print(json.dumps(asdict(status), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "llm-subscription-smoke":
        smoke_result = _run_subscription_smoke(args.config, args.out)
        print(json.dumps(smoke_result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "extract-llm":
        from financial_report_llm_extractor.field_metadata import load_field_taxonomy
        from financial_report_llm_extractor.llm_transport import (
            LlmTransportConfig,
            create_llm_client,
        )
        from financial_report_llm_extractor.structured_sources.catalog import (
            load_source_mapping_catalog,
        )
        from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
            extract_for_chunks,
            load_chunks_jsonl,
            write_llm_evidence_supplement,
        )

        out_dir = args.out
        out_dir.mkdir(parents=True, exist_ok=True)
        ingest_dir = out_dir / "ingest"

        priorities = tuple(p.strip() for p in args.priorities.split(",") if p.strip())
        fields_filter = (
            tuple(f.strip() for f in args.fields.split(",") if f.strip())
            if args.fields else None
        )

        chunks_path = ingest_dir / "chunks.jsonl"
        if not chunks_path.exists():
            ingest_dir.mkdir(parents=True, exist_ok=True)
            ingest_result = ingest_pdf(args.pdf, ingest_dir)
            build_chunk_store(
                ingest_result.pages_path,
                ingest_result.metadata_path,
                chunks_path=chunks_path,
            )

        chunks = load_chunks_jsonl(chunks_path)
        catalog = load_source_mapping_catalog(args.catalog, priorities=priorities)
        taxonomy = load_field_taxonomy(args.taxonomy)
        config = LlmTransportConfig.from_json(args.llm_config)
        client = create_llm_client(config)

        result = extract_for_chunks(
            chunks=chunks, catalog=catalog, taxonomy=taxonomy,
            client=client, company_id=args.company_id,
            pdf_path=args.pdf, out_dir=out_dir,
            priorities=priorities, fields=fields_filter,
            confidence_threshold=args.confidence_threshold,
        )
        write_llm_evidence_supplement(result)

        print(f"company_id={result.company_id}")
        print(f"chunk_count={result.chunk_count}")
        print(f"attempted={list(result.fields_attempted)}")
        print(f"present={list(result.fields_present)}")
        print(f"not_found={list(result.fields_not_found)}")
        print(f"failed={list(result.fields_failed)}")
        print(f"artifact={result.artifact_path}")
        return 0

    if args.command == "extract-llm-batch":
        from financial_report_llm_extractor.field_metadata import load_field_taxonomy
        from financial_report_llm_extractor.llm_transport import (
            LlmTransportConfig,
            create_llm_client,
        )
        from financial_report_llm_extractor.structured_sources.catalog import (
            load_source_mapping_catalog,
        )
        from financial_report_llm_extractor.structured_sources.llm_extraction_batch import (
            load_manifest,
            run_batch,
        )

        priorities = tuple(p.strip() for p in args.priorities.split(",") if p.strip())
        fields_filter = (
            tuple(f.strip() for f in args.fields.split(",") if f.strip())
            if args.fields else None
        )
        companies = load_manifest(args.manifest)
        catalog = load_source_mapping_catalog(args.catalog, priorities=priorities)
        taxonomy = load_field_taxonomy(args.taxonomy)
        config = LlmTransportConfig.from_json(args.llm_config)
        client = create_llm_client(config)

        summary = run_batch(
            companies=companies,
            out_dir=args.out,
            catalog=catalog,
            taxonomy=taxonomy,
            client=client,
            priorities=priorities,
            fields=fields_filter,
            workers=args.workers,
            confidence_threshold=args.confidence_threshold,
        )
        print(f"total_companies={summary.total_companies}")
        print(f"succeeded={summary.succeeded}")
        print(f"failed={summary.failed}")
        print(f"summary_path={summary.summary_path}")
        for entry in summary.companies:
            print(
                f"  {entry.company_id}: {entry.status} "
                f"present={list(entry.fields_present)} "
                f"not_found={list(entry.fields_not_found)} "
                f"failed={list(entry.fields_failed)}"
            )
        return 0

    if args.command == "evaluate":
        evaluation_result = write_review_summary(
            args.root,
            output_path=args.out,
        )
        print(f"reports={evaluation_result.report_count}")
        print(f"evaluation_summary_path={evaluation_result.output_path}")
        return 0

    if args.command == "quick-validate":
        quick_validation_result = run_quick_validation(
            pdf_path=args.pdf,
            report_id=args.report_id,
            root_dir=args.root,
        )
        print(f"run_dir={quick_validation_result.run_dir}")
        print(f"summary_path={quick_validation_result.artifacts['summary']}")
        return 0

    if args.command == "coverage-budget":
        priorities = tuple(
            priority.strip() for priority in args.priorities.split(",") if priority.strip()
        )
        explicit_fields = tuple(
            field.strip() for field in args.fields.split(",") if field.strip()
        )
        top_k_values = tuple(
            int(value.strip()) for value in args.top_k_values.split(",") if value.strip()
        )
        selected_fields = load_catalog_field_ids(
            args.catalog,
            priorities=priorities,
            explicit_fields=explicit_fields,
        )
        records = [
            json.loads(line)
            for line in args.chunks.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        metrics = build_coverage_metrics(
            records,
            selected_fields=selected_fields,
            top_k_values=top_k_values,
        )
        gate = evaluate_coverage_gate(
            metrics,
            required_top_k=args.required_top_k,
            max_total_chars=args.max_total_chars,
            max_field_chars=args.max_field_chars,
        )
        report = write_coverage_budget_report(
            output_dir=args.out_dir,
            report_id=args.report_id,
            catalog_id=args.catalog.stem,
            priorities=priorities,
            selected_fields=selected_fields,
            top_k_values=top_k_values,
            metrics=metrics,
            gate=gate,
        )
        selected_metric = next(
            metric for metric in metrics if metric["top_k"] == args.required_top_k
        )
        print(f"fields={selected_metric['total_fields']}")
        print(f"covered={selected_metric['covered_fields']}")
        print(f"gate={gate['status']}")
        print(f"coverage_budget_json={report['json']}")
        print(f"coverage_budget_markdown={report['markdown']}")
        return 0

    if args.command == "discover-rows-llm":
        llm_row_result = write_llm_row_inventory(
            args.chunks,
            args.statement_map,
            config_path=args.config,
            output_path=args.out,
            prompt_dir=args.prompt_dir,
            raw_response_dir=args.raw_response_dir,
            parsed_response_dir=args.parsed_response_dir,
        )
        print(f"rows={llm_row_result.row_count}")
        print(f"prompts={llm_row_result.prompt_count}")
        print(f"raw_responses={llm_row_result.raw_response_count}")
        print(f"row_inventory_llm_path={llm_row_result.output_path}")
        return 0

    if args.command == "discover-provider-fields":
        priorities = tuple(
            priority.strip()
            for priority in args.priorities.split(",")
            if priority.strip()
        )
        candidate_result = write_provider_field_candidate_report(
            taxonomy_path=args.taxonomy,
            mapping_catalog_path=args.mapping_catalog,
            inventory_path=args.inventory,
            summary_path=args.summary,
            output_dir=args.out,
            priorities=priorities,
        )
        print(f"fields={candidate_result.field_count}")
        print(f"candidate_report_path={candidate_result.json_path}")
        print(f"candidate_markdown_path={candidate_result.markdown_path}")
        return 0

    if args.command == "review-source-mapping-expansion":
        expansion_review_result = write_source_mapping_expansion_review(
            candidate_report_path=args.candidate_report,
            mapping_catalog_path=args.mapping_catalog,
            output_dir=args.out,
        )
        print(f"promoted={expansion_review_result.promoted_count}")
        print(f"deferred={expansion_review_result.deferred_count}")
        print(f"blocked={expansion_review_result.blocked_count}")
        print(f"source_mapping_expansion_json={expansion_review_result.json_path}")
        print(
            "source_mapping_expansion_markdown="
            f"{expansion_review_result.markdown_path}"
        )
        return 0

    if args.command == "replay-provider-baseline":
        replay_kwargs = {
            "inventory_path": args.inventory,
            "inventory_summary_path": args.inventory_summary,
            "catalog_path": args.catalog,
            "taxonomy_path": args.taxonomy,
            "output_dir": args.out,
        }
        if args.hk_yahoo_trust_policy is not None:
            replay_kwargs["hk_yahoo_trust_policy_path"] = args.hk_yahoo_trust_policy
        replay_result = write_provider_baseline_period_replay(**replay_kwargs)
        print(f"companies={replay_result.company_count}")
        print(f"provider_baseline_replay_summary={replay_result.summary_path}")
        print(f"provider_baseline_replay_markdown={replay_result.markdown_path}")
        return 0

    if args.command == "fetch-source-inventory":
        if args.year is not None and args.period_end is not None:
            parser.error("--year and --period-end are mutually exclusive")
        if args.year is not None:
            period = PeriodSpec.from_year(args.year)
        elif args.period_end is not None:
            period = PeriodSpec.from_period_end(args.period_end, args.report_type)
        else:
            parser.error("one of --year or --period-end is required")
        providers = tuple(
            p.strip() for p in args.providers.split(",") if p.strip()
        )
        _run_fetch_source_inventory(
            company=args.company,
            period=period,
            market=args.market,
            providers=providers,
            out_dir=args.out,
            catalog_path=args.catalog,
        )
        return 0

    if args.command == "index":
        import sys as _sys
        from financial_report_llm_extractor.cache.db import (
            init_db as _init_db,
        )
        from financial_report_llm_extractor.cache.indexer import (
            index_run as _index_run,
        )
        taxonomy = json.loads(args.taxonomy.read_text(encoding="utf-8"))
        taxonomy_version = str(taxonomy.get("version", "unknown"))
        catalog_version = args.catalog_version or taxonomy_version
        priority_map = {
            fid: str(info.get("priority", ""))
            for fid, info in taxonomy.get("fields", {}).items()
        }
        if (
            args.catalog_version is None
            and taxonomy_version != "unknown"
        ):
            print(
                f"warning: using current taxonomy version "
                f"'{taxonomy_version}' as catalog_version for all runs; "
                f"historical runs may have been generated under a different "
                f"catalog. Pass --catalog-version to override.",
                file=_sys.stderr,
            )
        _init_db(args.db)
        count_runs = 0
        count_fields = 0
        for sub in sorted(args.runs.iterdir()):
            if not sub.is_dir() or not (sub / "evaluation.json").exists():
                continue
            count_fields += _index_run(
                run_dir=sub, db_path=args.db,
                catalog_version=catalog_version,
                priority_map=priority_map,
            )
            count_runs += 1
        print(json.dumps({
            "indexed_runs": count_runs,
            "indexed_fields": count_fields,
            "db": str(args.db),
            "catalog_version": catalog_version,
        }, indent=2, sort_keys=True))
        return 0

    if args.command == "query":
        import sqlite3 as _sqlite3
        from financial_report_llm_extractor.cache.db_query import (
            query_extraction as _query_extraction,
            query_field as _query_field,
        )
        try:
            if args.field is not None:
                query_result: object = _query_field(
                    db_path=args.db, company=args.company,
                    period_end=args.period, field_id=args.field,
                )
            else:
                query_result = _query_extraction(
                    db_path=args.db, company=args.company,
                    period_end=args.period,
                )
        except _sqlite3.OperationalError as exc:
            print(json.dumps(
                {"miss": True, "reason": "db_not_initialized", "detail": str(exc)},
                sort_keys=True,
            ))
            return 2
        if query_result is None:
            print(json.dumps({"miss": True}, sort_keys=True))
            return 1
        print(json.dumps(query_result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0

    if args.command == "evaluate-company":
        if args.year is not None and args.period_end is not None:
            parser.error("--year and --period-end are mutually exclusive")
        if args.year is not None:
            period = PeriodSpec.from_year(args.year)
        elif args.period_end is not None:
            period = PeriodSpec.from_period_end(args.period_end, args.report_type)
        else:
            parser.error("one of --year or --period-end is required")
        priorities = tuple(
            p.strip() for p in args.priorities.split(",") if p.strip()
        )
        _run_evaluate_company(
            company=args.company,
            period=period,
            market=args.market,
            inventory_path=args.inventory,
            inventory_summary_path=args.inventory_summary,
            catalog_path=args.catalog,
            taxonomy_path=args.taxonomy,
            pdf_path=args.pdf,
            llm_config_path=args.llm_config,
            priorities=priorities,
            out_dir=args.out,
        )
        return 0

    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
