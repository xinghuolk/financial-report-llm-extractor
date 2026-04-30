"""Command line interface for financial report extraction."""

from __future__ import annotations

import argparse
from pathlib import Path

from financial_report_llm_extractor.ingestion import ingest_pdf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="financial-report-llm-extractor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("--pdf", required=True, type=Path)
    ingest_parser.add_argument("--out", required=True, type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "ingest":
        result = ingest_pdf(args.pdf, args.out)
        print(f"pages={result.page_count}")
        print(f"pages_path={result.pages_path}")
        print(f"metadata_path={result.metadata_path}")
        return 0

    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
