import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from financial_report_llm_extractor.ingestion import (
    compute_sha256,
    ingest_pdf,
    split_pdftotext_pages,
)


@dataclass(frozen=True)
class FakeParser:
    name: str = "fake-parser"
    version: str = "fake-parser:1"

    def extract_text(self, pdf_path: Path) -> str:
        return "page one\n\fpage two\n"


def test_split_pdftotext_pages_uses_form_feed_boundaries() -> None:
    pages = split_pdftotext_pages(" first page \n\fsecond page\n\f")

    assert [page.page for page in pages] == [1, 2]
    assert [page.text for page in pages] == ["first page", "second page"]


def test_compute_sha256_hashes_file_bytes(tmp_path: Path) -> None:
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"fake-pdf-bytes")

    assert compute_sha256(pdf_path) == hashlib.sha256(b"fake-pdf-bytes").hexdigest()


def test_ingest_pdf_writes_pages_and_metadata(tmp_path: Path) -> None:
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"fake-pdf-bytes")
    output_dir = tmp_path / "run"

    result = ingest_pdf(pdf_path, output_dir, parser=FakeParser())

    assert result.page_count == 2
    assert result.pages_path == output_dir / "pages.jsonl"
    assert result.metadata_path == output_dir / "run_metadata.json"

    page_lines = result.pages_path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in page_lines] == [
        {"page": 1, "text": "page one"},
        {"page": 2, "text": "page two"},
    ]

    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["source_pdf_path"] == str(pdf_path)
    assert metadata["source_pdf_hash"] == hashlib.sha256(b"fake-pdf-bytes").hexdigest()
    assert metadata["parser_name"] == "fake-parser"
    assert metadata["parser_version"] == "fake-parser:1"
    assert metadata["chunker_version"] == "none"
    assert metadata["page_count"] == 2
    assert metadata["artifacts"] == {
        "pages": str(output_dir / "pages.jsonl"),
        "metadata": str(output_dir / "run_metadata.json"),
    }
