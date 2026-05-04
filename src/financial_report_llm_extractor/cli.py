"""Command line interface for financial report extraction."""

from __future__ import annotations

import argparse
import json
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
from financial_report_llm_extractor.llm_transport import run_real_transport_probe
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
from financial_report_llm_extractor.structured_sources.source_mapping_expansion import (
    write_source_mapping_expansion_review,
)


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

    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("--retrieval-probe", required=True, type=Path)
    extract_parser.add_argument("--config", required=True, type=Path)
    extract_parser.add_argument("--out", type=Path)
    extract_parser.add_argument("--raw-response-dir", type=Path)

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
    baseline_replay_parser.add_argument("--out", required=True, type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

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
        replay_result = write_provider_baseline_period_replay(
            inventory_path=args.inventory,
            inventory_summary_path=args.inventory_summary,
            catalog_path=args.catalog,
            output_dir=args.out,
        )
        print(f"companies={replay_result.company_count}")
        print(f"provider_baseline_replay_summary={replay_result.summary_path}")
        print(f"provider_baseline_replay_markdown={replay_result.markdown_path}")
        return 0

    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
