from dataclasses import dataclass
from pathlib import Path

import pytest

from financial_report_llm_extractor import cli


@dataclass(frozen=True)
class FakeResult:
    pages_path: Path
    metadata_path: Path
    page_count: int


def test_ingest_command_calls_ingestion_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "report.pdf"
    output_dir = tmp_path / "out"
    calls: list[tuple[Path, Path]] = []

    def fake_ingest_pdf(pdf: Path, out: Path) -> FakeResult:
        calls.append((pdf, out))
        return FakeResult(
            pages_path=out / "pages.jsonl",
            metadata_path=out / "run_metadata.json",
            page_count=2,
        )

    monkeypatch.setattr(cli, "ingest_pdf", fake_ingest_pdf)

    exit_code = cli.main(["ingest", "--pdf", str(pdf_path), "--out", str(output_dir)])

    assert exit_code == 0
    assert calls == [(pdf_path, output_dir)]
