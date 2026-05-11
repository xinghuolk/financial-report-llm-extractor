"""PDF ingestion primitives for page-level artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class PageRecord:
    page: int
    text: str


@dataclass(frozen=True)
class IngestResult:
    pages_path: Path
    metadata_path: Path
    page_count: int


class PdfTextParser(Protocol):
    @property
    def name(self) -> str:
        pass

    @property
    def version(self) -> str:
        pass

    def extract_text(self, pdf_path: Path) -> str:
        pass


@dataclass(frozen=True)
class PdftotextParser:
    name: str = "pdftotext"
    version: str = "pdftotext-layout"

    def extract_text(self, pdf_path: Path) -> str:
        completed = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout


def split_pdftotext_pages(raw_text: str) -> list[PageRecord]:
    pages: list[PageRecord] = []
    for index, page_text in enumerate(raw_text.split("\f"), start=1):
        text = page_text.strip()
        if text:
            pages.append(PageRecord(page=index, text=text))
    return pages


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_pdf_text_parser(
    *,
    fallback_parser: PdfTextParser | None = None,
    pdftotext_path: str | None = None,
) -> PdfTextParser:
    resolved_pdftotext_path = (
        shutil.which("pdftotext") if pdftotext_path is None else pdftotext_path
    )
    if resolved_pdftotext_path:
        return PdftotextParser()
    if fallback_parser is not None:
        return fallback_parser
    raise RuntimeError(
        "no PDF text parser available: pdftotext is not on PATH and no fallback "
        "parser was provided"
    )


def ingest_pdf(
    pdf_path: Path,
    output_dir: Path,
    *,
    parser: PdfTextParser | None = None,
    fallback_parser: PdfTextParser | None = None,
) -> IngestResult:
    active_parser = parser or resolve_pdf_text_parser(fallback_parser=fallback_parser)
    source_pdf_hash = compute_sha256(pdf_path)
    pages = split_pdftotext_pages(active_parser.extract_text(pdf_path))

    output_dir.mkdir(parents=True, exist_ok=True)
    pages_path = output_dir / "pages.jsonl"
    metadata_path = output_dir / "run_metadata.json"

    with pages_path.open("w", encoding="utf-8") as pages_file:
        for page in pages:
            pages_file.write(
                json.dumps(
                    {
                        "page": page.page,
                        "text": page.text,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            pages_file.write("\n")

    metadata = {
        "source_pdf_path": str(pdf_path),
        "source_pdf_hash": source_pdf_hash,
        "parser_name": active_parser.name,
        "parser_version": active_parser.version,
        "chunker_version": "none",
        "page_count": len(pages),
        "artifacts": {
            "pages": str(pages_path),
            "metadata": str(metadata_path),
        },
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return IngestResult(
        pages_path=pages_path,
        metadata_path=metadata_path,
        page_count=len(pages),
    )
