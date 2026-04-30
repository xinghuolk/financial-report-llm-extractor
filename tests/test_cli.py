from dataclasses import dataclass
from pathlib import Path

import pytest

from financial_report_llm_extractor import cli


@dataclass(frozen=True)
class FakeResult:
    pages_path: Path
    metadata_path: Path
    page_count: int


@dataclass(frozen=True)
class FakeChunkResult:
    chunks_path: Path
    block_count: int
    chunk_count: int


@dataclass(frozen=True)
class FakeRetrievalResult:
    output_path: Path
    field_count: int


@dataclass(frozen=True)
class FakeExtractionResult:
    output_path: Path
    item_count: int


@dataclass(frozen=True)
class FakeRealExtractionResult:
    output_path: Path
    item_count: int
    raw_response_count: int


@dataclass(frozen=True)
class FakeEvaluationResult:
    output_path: Path
    report_count: int


@dataclass(frozen=True)
class FakeParserCapabilityResult:
    output_path: Path
    page_count: int


@dataclass(frozen=True)
class FakeDocumentMapResult:
    output_path: Path
    section_count: int


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


def test_chunk_command_calls_chunking_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pages_path = tmp_path / "pages.jsonl"
    metadata_path = tmp_path / "run_metadata.json"
    chunks_path = tmp_path / "custom-chunks.jsonl"
    calls: list[tuple[Path, Path, Path | None]] = []

    def fake_build_chunk_store(
        pages: Path,
        metadata: Path,
        *,
        chunks_path: Path | None = None,
    ) -> FakeChunkResult:
        calls.append((pages, metadata, chunks_path))
        return FakeChunkResult(
            chunks_path=chunks_path or pages.parent / "chunks.jsonl",
            block_count=4,
            chunk_count=6,
        )

    monkeypatch.setattr(cli, "build_chunk_store", fake_build_chunk_store)

    exit_code = cli.main(
        [
            "chunk",
            "--pages",
            str(pages_path),
            "--metadata",
            str(metadata_path),
            "--out",
            str(chunks_path),
        ]
    )

    assert exit_code == 0
    assert calls == [(pages_path, metadata_path, chunks_path)]


def test_retrieve_command_calls_retrieval_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog.json"
    chunks_path = tmp_path / "chunks.jsonl"
    output_path = tmp_path / "retrieval_probe.json"
    calls: list[tuple[Path, Path, Path | None, tuple[str, ...]]] = []

    def fake_write_retrieval_probe(
        catalog: Path,
        chunks: Path,
        *,
        output_path: Path | None = None,
        priorities: tuple[str, ...] = ("P0", "P1"),
    ) -> FakeRetrievalResult:
        calls.append((catalog, chunks, output_path, priorities))
        return FakeRetrievalResult(
            output_path=output_path or chunks.parent / "retrieval_probe.json",
            field_count=3,
        )

    monkeypatch.setattr(cli, "write_retrieval_probe", fake_write_retrieval_probe)

    exit_code = cli.main(
        [
            "retrieve",
            "--catalog",
            str(catalog_path),
            "--chunks",
            str(chunks_path),
            "--out",
            str(output_path),
            "--priorities",
            "P0,P1",
        ]
    )

    assert exit_code == 0
    assert calls == [(catalog_path, chunks_path, output_path, ("P0", "P1"))]


def test_extract_fake_command_calls_extraction_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    retrieval_probe_path = tmp_path / "retrieval_probe.json"
    output_path = tmp_path / "extraction_result.json"
    calls: list[tuple[Path, Path | None]] = []

    def fake_run_fake_extraction(
        retrieval_probe: Path,
        *,
        output_path: Path | None = None,
    ) -> FakeExtractionResult:
        calls.append((retrieval_probe, output_path))
        return FakeExtractionResult(
            output_path=output_path or retrieval_probe.parent / "extraction_result.json",
            item_count=2,
        )

    monkeypatch.setattr(cli, "run_fake_extraction", fake_run_fake_extraction)

    exit_code = cli.main(
        [
            "extract-fake",
            "--retrieval-probe",
            str(retrieval_probe_path),
            "--out",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert calls == [(retrieval_probe_path, output_path)]


def test_extract_command_calls_real_transport_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    retrieval_probe_path = tmp_path / "retrieval_probe.json"
    config_path = tmp_path / "llm_config.json"
    output_path = tmp_path / "extraction_result.json"
    raw_dir = tmp_path / "raw"
    calls: list[tuple[Path, Path, Path | None, Path | None]] = []

    def fake_run_real_transport_probe(
        retrieval_probe: Path,
        *,
        config_path: Path,
        output_path: Path | None = None,
        raw_response_dir: Path | None = None,
    ) -> FakeRealExtractionResult:
        calls.append((retrieval_probe, config_path, output_path, raw_response_dir))
        return FakeRealExtractionResult(
            output_path=output_path or retrieval_probe.parent / "extraction_result.json",
            item_count=2,
            raw_response_count=2,
        )

    monkeypatch.setattr(cli, "run_real_transport_probe", fake_run_real_transport_probe)

    exit_code = cli.main(
        [
            "extract",
            "--retrieval-probe",
            str(retrieval_probe_path),
            "--config",
            str(config_path),
            "--out",
            str(output_path),
            "--raw-response-dir",
            str(raw_dir),
        ]
    )

    assert exit_code == 0
    assert calls == [(retrieval_probe_path, config_path, output_path, raw_dir)]


def test_evaluate_command_calls_evaluation_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "evaluation_summary.json"
    calls: list[tuple[Path, Path | None]] = []

    def fake_write_review_summary(
        root_dir: Path,
        *,
        output_path: Path | None = None,
    ) -> FakeEvaluationResult:
        calls.append((root_dir, output_path))
        return FakeEvaluationResult(
            output_path=output_path or root_dir / "evaluation_summary.json",
            report_count=3,
        )

    monkeypatch.setattr(cli, "write_review_summary", fake_write_review_summary)

    exit_code = cli.main(
        [
            "evaluate",
            "--root",
            str(tmp_path),
            "--out",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert calls == [(tmp_path, output_path)]


def test_probe_parser_command_calls_document_map_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pages_path = tmp_path / "pages.jsonl"
    metadata_path = tmp_path / "run_metadata.json"
    output_path = tmp_path / "parser_capability.json"
    calls: list[tuple[Path, Path, Path | None]] = []

    def fake_write_parser_capability_probe(
        pages: Path,
        metadata: Path,
        *,
        output_path: Path | None = None,
    ) -> FakeParserCapabilityResult:
        calls.append((pages, metadata, output_path))
        return FakeParserCapabilityResult(
            output_path=output_path or pages.parent / "parser_capability.json",
            page_count=3,
        )

    monkeypatch.setattr(
        cli,
        "write_parser_capability_probe",
        fake_write_parser_capability_probe,
    )

    exit_code = cli.main(
        [
            "probe-parser",
            "--pages",
            str(pages_path),
            "--metadata",
            str(metadata_path),
            "--out",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert calls == [(pages_path, metadata_path, output_path)]


def test_map_document_command_calls_document_map_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    output_path = tmp_path / "document_map.json"
    calls: list[tuple[Path, Path | None]] = []

    def fake_write_document_map(
        chunks: Path,
        *,
        output_path: Path | None = None,
    ) -> FakeDocumentMapResult:
        calls.append((chunks, output_path))
        return FakeDocumentMapResult(
            output_path=output_path or chunks.parent / "document_map.json",
            section_count=6,
        )

    monkeypatch.setattr(cli, "write_document_map", fake_write_document_map)

    exit_code = cli.main(
        [
            "map-document",
            "--chunks",
            str(chunks_path),
            "--out",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert calls == [(chunks_path, output_path)]
