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


@dataclass(frozen=True)
class FakeStatementMapResult:
    output_path: Path
    statement_count: int


@dataclass(frozen=True)
class FakeRowInventoryResult:
    output_path: Path
    row_count: int


@dataclass(frozen=True)
class FakeCatalogMappingResult:
    output_path: Path
    mapping_count: int


@dataclass(frozen=True)
class FakeQuickValidationResult:
    run_dir: Path
    artifacts: dict[str, Path]


@dataclass(frozen=True)
class FakeLlmRowDiscoveryResult:
    output_path: Path
    row_count: int
    prompt_count: int
    raw_response_count: int


@dataclass(frozen=True)
class FakeProviderFieldCandidateResult:
    json_path: Path
    markdown_path: Path
    field_count: int


@dataclass(frozen=True)
class FakeSourceMappingExpansionReviewResult:
    json_path: Path
    markdown_path: Path
    promoted_count: int
    deferred_count: int
    blocked_count: int


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


def test_discover_provider_fields_command_calls_candidate_discovery_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    taxonomy_path = tmp_path / "taxonomy.json"
    mapping_path = tmp_path / "mapping.json"
    inventory_path = tmp_path / "source_inventory.jsonl.gz"
    summary_path = tmp_path / "provider_field_inventory_summary.json"
    output_dir = tmp_path / "candidate_report"
    calls: list[tuple[Path, Path, Path, Path, Path, tuple[str, ...]]] = []

    def fake_write_provider_field_candidate_report(
        *,
        taxonomy_path: Path,
        mapping_catalog_path: Path,
        inventory_path: Path,
        summary_path: Path,
        output_dir: Path,
        priorities: tuple[str, ...] = ("P0", "P1"),
    ) -> FakeProviderFieldCandidateResult:
        calls.append(
            (
                taxonomy_path,
                mapping_catalog_path,
                inventory_path,
                summary_path,
                output_dir,
                priorities,
            )
        )
        return FakeProviderFieldCandidateResult(
            json_path=output_dir / "provider_field_candidate_report.json",
            markdown_path=output_dir / "provider_field_candidate_report.md",
            field_count=33,
        )

    monkeypatch.setattr(
        cli,
        "write_provider_field_candidate_report",
        fake_write_provider_field_candidate_report,
    )

    exit_code = cli.main(
        [
            "discover-provider-fields",
            "--taxonomy",
            str(taxonomy_path),
            "--mapping-catalog",
            str(mapping_path),
            "--inventory",
            str(inventory_path),
            "--summary",
            str(summary_path),
            "--out",
            str(output_dir),
            "--priorities",
            "P0,P1",
        ]
    )

    assert exit_code == 0
    assert calls == [
        (
            taxonomy_path,
            mapping_path,
            inventory_path,
            summary_path,
            output_dir,
            ("P0", "P1"),
        )
    ]


def test_review_source_mapping_expansion_command_calls_review_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    candidate_report = tmp_path / "provider_field_candidate_report.json"
    mapping_catalog = tmp_path / "mapping.json"
    output_dir = tmp_path / "review"
    calls: list[tuple[Path, Path, Path]] = []

    def fake_write_source_mapping_expansion_review(
        *,
        candidate_report_path: Path,
        mapping_catalog_path: Path,
        output_dir: Path,
    ) -> FakeSourceMappingExpansionReviewResult:
        calls.append((candidate_report_path, mapping_catalog_path, output_dir))
        return FakeSourceMappingExpansionReviewResult(
            json_path=output_dir / "source_mapping_expansion_review.json",
            markdown_path=output_dir / "source_mapping_expansion_review.md",
            promoted_count=6,
            deferred_count=10,
            blocked_count=0,
        )

    monkeypatch.setattr(
        cli,
        "write_source_mapping_expansion_review",
        fake_write_source_mapping_expansion_review,
    )

    exit_code = cli.main(
        [
            "review-source-mapping-expansion",
            "--candidate-report",
            str(candidate_report),
            "--mapping-catalog",
            str(mapping_catalog),
            "--out",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert calls == [(candidate_report, mapping_catalog, output_dir)]


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


def test_map_statements_command_calls_statement_discovery_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    document_map_path = tmp_path / "document_map.json"
    output_path = tmp_path / "statement_map.json"
    calls: list[tuple[Path, Path, Path | None]] = []

    def fake_write_statement_map(
        chunks: Path,
        document_map: Path,
        *,
        output_path: Path | None = None,
    ) -> FakeStatementMapResult:
        calls.append((chunks, document_map, output_path))
        return FakeStatementMapResult(
            output_path=output_path or chunks.parent / "statement_map.json",
            statement_count=3,
        )

    monkeypatch.setattr(cli, "write_statement_map", fake_write_statement_map)

    exit_code = cli.main(
        [
            "map-statements",
            "--chunks",
            str(chunks_path),
            "--document-map",
            str(document_map_path),
            "--out",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert calls == [(chunks_path, document_map_path, output_path)]


def test_discover_rows_command_calls_statement_discovery_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    statement_map_path = tmp_path / "statement_map.json"
    output_path = tmp_path / "row_inventory.json"
    calls: list[tuple[Path, Path, Path | None]] = []

    def fake_write_row_inventory(
        chunks: Path,
        statement_map: Path,
        *,
        output_path: Path | None = None,
    ) -> FakeRowInventoryResult:
        calls.append((chunks, statement_map, output_path))
        return FakeRowInventoryResult(
            output_path=output_path or chunks.parent / "row_inventory.json",
            row_count=5,
        )

    monkeypatch.setattr(cli, "write_row_inventory", fake_write_row_inventory)

    exit_code = cli.main(
        [
            "discover-rows",
            "--chunks",
            str(chunks_path),
            "--statement-map",
            str(statement_map_path),
            "--out",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert calls == [(chunks_path, statement_map_path, output_path)]


def test_map_fields_command_calls_statement_discovery_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    row_inventory_path = tmp_path / "row_inventory.json"
    output_path = tmp_path / "catalog_mapping.json"
    calls: list[tuple[Path, tuple[str, ...], Path | None]] = []

    def fake_write_catalog_mapping(
        row_inventory: Path,
        *,
        selected_fields: tuple[str, ...],
        output_path: Path | None = None,
    ) -> FakeCatalogMappingResult:
        calls.append((row_inventory, selected_fields, output_path))
        return FakeCatalogMappingResult(
            output_path=output_path or row_inventory.parent / "catalog_mapping.json",
            mapping_count=2,
        )

    monkeypatch.setattr(cli, "write_catalog_mapping", fake_write_catalog_mapping)

    exit_code = cli.main(
        [
            "map-fields",
            "--row-inventory",
            str(row_inventory_path),
            "--fields",
            "revenue,total_assets",
            "--out",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert calls == [(row_inventory_path, ("revenue", "total_assets"), output_path)]


def test_quick_validate_command_calls_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "report.pdf"
    calls: list[tuple[Path, str, Path]] = []

    def fake_run_quick_validation(
        *,
        pdf_path: Path,
        report_id: str,
        root_dir: Path,
    ) -> FakeQuickValidationResult:
        calls.append((pdf_path, report_id, root_dir))
        run_dir = root_dir / "tmp" / "runs" / "quick_validation" / report_id
        return FakeQuickValidationResult(
            run_dir=run_dir,
            artifacts={"summary": run_dir / "quick_validation_summary.json"},
        )

    monkeypatch.setattr(cli, "run_quick_validation", fake_run_quick_validation)

    exit_code = cli.main(
        [
            "quick-validate",
            "--pdf",
            str(pdf_path),
            "--report-id",
            "00001_2025_en",
            "--root",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert calls == [(pdf_path, "00001_2025_en", tmp_path)]


def test_discover_rows_llm_command_calls_row_discovery_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    statement_map_path = tmp_path / "statement_map.json"
    config_path = tmp_path / "llm_config.json"
    output_path = tmp_path / "row_inventory_llm.json"
    prompt_dir = tmp_path / "prompt_payloads"
    raw_dir = tmp_path / "raw_llm_responses"
    parsed_dir = tmp_path / "parsed_llm_responses"
    calls: list[tuple[Path, Path, Path, Path, Path, Path, Path]] = []

    def fake_write_llm_row_inventory(
        chunks: Path,
        statement_map: Path,
        *,
        config_path: Path,
        output_path: Path,
        prompt_dir: Path,
        raw_response_dir: Path,
        parsed_response_dir: Path,
    ) -> FakeLlmRowDiscoveryResult:
        calls.append(
            (
                chunks,
                statement_map,
                config_path,
                output_path,
                prompt_dir,
                raw_response_dir,
                parsed_response_dir,
            )
        )
        return FakeLlmRowDiscoveryResult(
            output_path=output_path,
            row_count=2,
            prompt_count=1,
            raw_response_count=1,
        )

    monkeypatch.setattr(cli, "write_llm_row_inventory", fake_write_llm_row_inventory)

    exit_code = cli.main(
        [
            "discover-rows-llm",
            "--chunks",
            str(chunks_path),
            "--statement-map",
            str(statement_map_path),
            "--config",
            str(config_path),
            "--out",
            str(output_path),
            "--prompt-dir",
            str(prompt_dir),
            "--raw-response-dir",
            str(raw_dir),
            "--parsed-response-dir",
            str(parsed_dir),
        ]
    )

    assert exit_code == 0
    assert calls == [
        (
            chunks_path,
            statement_map_path,
            config_path,
            output_path,
            prompt_dir,
            raw_dir,
            parsed_dir,
        )
    ]
