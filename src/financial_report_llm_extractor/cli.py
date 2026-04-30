"""Command line interface for financial report extraction."""

from __future__ import annotations

import argparse
from pathlib import Path

from financial_report_llm_extractor.chunking import build_chunk_store
from financial_report_llm_extractor.document_map import (
    write_document_map,
    write_parser_capability_probe,
)
from financial_report_llm_extractor.evaluation import write_review_summary
from financial_report_llm_extractor.extraction import run_fake_extraction
from financial_report_llm_extractor.ingestion import ingest_pdf
from financial_report_llm_extractor.llm_transport import run_real_transport_probe
from financial_report_llm_extractor.retrieval import write_retrieval_probe


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

    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
