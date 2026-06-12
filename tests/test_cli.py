import json
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


@dataclass(frozen=True)
class FakeProviderBaselineReplayResult:
    summary_path: Path
    markdown_path: Path
    company_count: int


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


def test_replay_provider_baseline_command_calls_replay_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inventory_path = tmp_path / "source_inventory.jsonl.gz"
    inventory_summary_path = tmp_path / "provider_field_inventory_summary.json"
    catalog_path = tmp_path / "catalog.json"
    taxonomy_path = tmp_path / "taxonomy.json"
    output_dir = tmp_path / "replay"
    trust_policy_path = tmp_path / "hk_yahoo_trust_policy.json"
    calls: list[tuple[Path, Path, Path, Path, Path, Path | None]] = []

    def fake_write_provider_baseline_period_replay(
        *,
        inventory_path: Path,
        inventory_summary_path: Path,
        catalog_path: Path,
        taxonomy_path: Path,
        output_dir: Path,
        output_summary_path: Path | None = None,
        company_ids: tuple[str, ...] | None = None,
        hk_yahoo_trust_policy_path: Path | None = None,
    ) -> FakeProviderBaselineReplayResult:
        assert output_summary_path is None
        assert company_ids is None
        calls.append(
            (
                inventory_path,
                inventory_summary_path,
                catalog_path,
                taxonomy_path,
                output_dir,
                hk_yahoo_trust_policy_path,
            )
        )
        return FakeProviderBaselineReplayResult(
            summary_path=output_dir / "provider_baseline_period_replay_summary.json",
            markdown_path=output_dir / "provider_baseline_period_replay_summary.md",
            company_count=3,
        )

    monkeypatch.setattr(
        cli,
        "write_provider_baseline_period_replay",
        fake_write_provider_baseline_period_replay,
    )

    exit_code = cli.main(
        [
            "replay-provider-baseline",
            "--inventory",
            str(inventory_path),
            "--inventory-summary",
            str(inventory_summary_path),
            "--catalog",
            str(catalog_path),
            "--taxonomy",
            str(taxonomy_path),
            "--out",
            str(output_dir),
            "--hk-yahoo-trust-policy",
            str(trust_policy_path),
        ]
    )

    assert exit_code == 0
    assert calls == [
        (
            inventory_path,
            inventory_summary_path,
            catalog_path,
            taxonomy_path,
            output_dir,
            trust_policy_path,
        )
    ]


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


def test_llm_auth_status_command_prints_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from financial_report_llm_extractor.subscription_auth import (
        SubscriptionCredentialStatus,
    )

    def fake_status(provider: str) -> SubscriptionCredentialStatus:
        assert provider == "openai-codex"
        return SubscriptionCredentialStatus(
            provider="openai-codex",
            available=True,
            credential_source="test-source",
            token_status="valid",
            base_url="https://chatgpt.com/backend-api/codex",
        )

    monkeypatch.setattr(cli, "subscription_auth_status", fake_status)

    exit_code = cli.main(["llm-auth-status", "--provider", "openai-codex"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider"] == "openai-codex"
    assert payload["available"] is True
    assert payload["credential_source"] == "test-source"


def test_llm_subscription_smoke_rejects_non_subscription_provider(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "llm_config.json"
    config_path.write_text(
        json.dumps({"provider": "ollama", "model": "qwen2.5:7b"}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        cli.main(
            [
                "llm-subscription-smoke",
                "--config",
                str(config_path),
                "--out",
                str(tmp_path / "smoke"),
            ]
        )


def test_llm_subscription_smoke_writes_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "llm_config.json"
    out_dir = tmp_path / "smoke"
    config_path.write_text(
        json.dumps({"provider": "openai-codex", "model": "gpt-5.3-codex"}),
        encoding="utf-8",
    )

    class FakeSmokeClient:
        raw_exchanges: list[object] = []

        def complete_json(
            self,
            *,
            system_prompt: str,
            user_payload: dict[str, object],
        ) -> dict[str, object]:
            assert "Return strict JSON" in system_prompt
            assert user_payload["task"] == "subscription_smoke"
            return {"choices": [{"message": {"content": json.dumps({"ok": True})}}]}

    def fake_create_client(config: object) -> FakeSmokeClient:
        return FakeSmokeClient()

    monkeypatch.setattr(cli, "create_llm_client", fake_create_client)

    exit_code = cli.main(
        [
            "llm-subscription-smoke",
            "--config",
            str(config_path),
            "--out",
            str(out_dir),
        ]
    )

    assert exit_code == 0
    assert (out_dir / "prompt.json").exists()
    assert (out_dir / "raw_response.json").exists()
    assert (out_dir / "parsed_response.json").exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True


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


def test_fetch_source_inventory_subcommand_dispatches_correctly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """argv → run_fetch wiring 测，主体逻辑 mock 掉。"""
    from financial_report_llm_extractor.cli import main
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        SourceInventoryArtifact,
    )

    captured: dict[str, object] = {}

    def fake_runner(**kwargs: object) -> SourceInventoryArtifact:
        captured.update(kwargs)
        return SourceInventoryArtifact(
            inventory_path=tmp_path / "source_inventory.jsonl",
            summary_path=tmp_path / "source_inventory_summary.json",
            record_count=0,
        )

    monkeypatch.setattr(
        "financial_report_llm_extractor.cli._run_fetch_source_inventory",
        fake_runner,
    )

    main([
        "fetch-source-inventory",
        "--company", "600519",
        "--year", "2024",
        "--market", "CN",
        "--providers", "akshare",
        "--out", str(tmp_path),
        "--catalog", "field_catalog/turtle_v015_source_mapping_minimal.json",
    ])

    assert captured["company"] == "600519"
    assert captured["market"] == "CN"
    # YEAR shortcut expanded
    from datetime import date

    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
    )

    period = captured["period"]
    assert isinstance(period, PeriodSpec)
    assert period.period_end == date(2024, 12, 31)


def test_fetch_source_inventory_subcommand_rejects_year_and_period_end_together(
    tmp_path: Path,
) -> None:
    from financial_report_llm_extractor.cli import main

    with pytest.raises(SystemExit):
        main([
            "fetch-source-inventory",
            "--company", "600519",
            "--year", "2024",
            "--period-end", "2024-12-31",
            "--market", "CN",
            "--providers", "akshare",
            "--out", str(tmp_path),
            "--catalog", "field_catalog/turtle_v015_source_mapping_minimal.json",
        ])


@pytest.mark.parametrize(
    "company, expected_currency",
    [
        # 2026-06-12 investigation (docs/gates/2026-06-12-gross-profit-
        # divergence-investigation.md): the EastMoney AKShare HK feed
        # delivers CNY-converted values for EVERY issuer regardless of its
        # reporting currency (6 CNY reporters digit-identical to Yahoo;
        # 00001 HKD reporter at exactly the CNY/HKD rate 0.9032 on two
        # independent metrics; 09987 USD reporter at CNY/USD 7.10). The
        # issuer financial-currency map applies to the YAHOO path only.
        ("01810", "CNY"),   # Xiaomi — RMB reporter
        ("06862", "CNY"),   # RMB reporter
        ("02498", "CNY"),   # RMB reporter
        ("00001", "CNY"),   # HK$ reporter — feed still CNY
        ("01113", "CNY"),   # HK$ reporter — feed still CNY
        ("09987", "CNY"),   # US$ reporter — feed still CNY
        ("99999", "CNY"),   # Unknown HK issuer — feed still CNY
    ],
)
def test_fetch_source_inventory_hk_akshare_stamps_feed_currency_cny(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    company: str,
    expected_currency: str,
) -> None:
    """AKShare HK records are stamped CNY — the feed's actual currency —
    not the issuer's reporting currency (supersedes Phase HK-B.5.1 for
    the AKShare path; the issuer map remains correct for Yahoo)."""
    from financial_report_llm_extractor.cli import _run_fetch_source_inventory
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        PeriodSpec,
        SourceInventoryArtifact,
    )

    captured: dict[str, object] = {}

    class FakeAkshareClient:
        def __init__(self, *, hk_default_currency: str) -> None:
            captured["hk_default_currency"] = hk_default_currency

    def fake_fetch_source_inventory(**kwargs: object) -> SourceInventoryArtifact:
        captured["akshare_client"] = kwargs["akshare_client"]
        return SourceInventoryArtifact(
            inventory_path=tmp_path / "source_inventory.jsonl",
            summary_path=tmp_path / "source_inventory_summary.json",
            record_count=0,
        )

    monkeypatch.setattr(
        "financial_report_llm_extractor.structured_sources.real_source_validation."
        "PandasAkshareClient",
        FakeAkshareClient,
    )
    monkeypatch.setattr(
        "financial_report_llm_extractor.structured_sources.source_inventory_fetch."
        "fetch_source_inventory",
        fake_fetch_source_inventory,
    )

    _run_fetch_source_inventory(
        company=company,
        period=PeriodSpec.from_year(2024),
        market="HK",
        providers=("akshare",),
        out_dir=tmp_path,
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
    )

    assert captured["hk_default_currency"] == expected_currency
    assert isinstance(captured["akshare_client"], FakeAkshareClient)


def test_evaluate_company_subcommand_dispatches_correctly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from financial_report_llm_extractor.cli import main

    captured: dict[str, object] = {}

    def fake_runner(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        "financial_report_llm_extractor.cli._run_evaluate_company",
        fake_runner,
    )

    inv = tmp_path / "source_inventory.jsonl"
    inv.write_text("")
    inv_summary = tmp_path / "source_inventory_summary.json"
    inv_summary.write_text("{}")

    main([
        "evaluate-company",
        "--company", "600519",
        "--year", "2024",
        "--market", "CN",
        "--inventory", str(inv),
        "--inventory-summary", str(inv_summary),
        "--catalog", "field_catalog/turtle_v015_source_mapping_minimal.json",
        "--taxonomy", "field_catalog/turtle_v015_field_taxonomy.json",
        "--out", str(tmp_path),
    ])

    assert captured["company"] == "600519"
    assert captured["market"] == "CN"
    assert captured["pdf_path"] is None


def test_extract_llm_help_lists_required_args() -> None:
    """Verify the extract-llm subcommand is registered."""
    import argparse
    from financial_report_llm_extractor.cli import build_parser
    parser = build_parser()
    sub = next(
        a for a in parser._actions
        if a.__class__.__name__ == "_SubParsersAction"
    )
    choices: dict[str, argparse.ArgumentParser] = dict(sub.choices or {})
    assert "extract-llm" in choices
    extract_llm = choices["extract-llm"]
    args_required = {
        action.dest for action in extract_llm._actions
        if action.required
    }
    assert {"pdf", "company_id", "catalog", "taxonomy",
            "llm_config", "out"} <= args_required


def test_cli_index_command_scans_runs_dir(
    tmp_path: Path, capsys: "pytest.CaptureFixture[str]"
) -> None:
    """`index` subcommand walks runs dir + writes DB; builds priority_map from
    the taxonomy file; uses taxonomy version as default catalog_version."""
    import json as _json
    from financial_report_llm_extractor.cli import main

    # Reuse the realistic two-file fixture.
    src_eval = (
        Path(__file__).parent / "fixtures" / "cache_sample_run"
        / "evaluation.json"
    )
    src_supp = (
        Path(__file__).parent / "fixtures" / "cache_sample_run"
        / "llm_evidence_supplement.json"
    )
    run_dir = tmp_path / "runs" / "600519_2024-12-31"
    run_dir.mkdir(parents=True)
    (run_dir / "evaluation.json").write_text(
        src_eval.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (run_dir / "llm_evidence_supplement.json").write_text(
        src_supp.read_text(encoding="utf-8"), encoding="utf-8"
    )

    # Tiny taxonomy: version + 3 fields with priorities.
    tax_path = tmp_path / "tax.json"
    tax_path.write_text(_json.dumps({
        "catalog_id": "tiny",
        "version": "test-1",
        "source_priority_catalog": "tiny",
        "fields": {
            "revenue": {"priority": "P0", "domain": "x", "statement_type": "x",
                        "value_type": "money", "source_mode": "direct",
                        "period_type": "x", "scope_expectation": "x",
                        "currency_requirement": "applicable",
                        "unit_requirement": "applicable",
                        "evidence_requirement": "x", "fallback_policy": "x",
                        "description": "x"},
            "audit_opinion": {"priority": "P4", "domain": "x",
                              "statement_type": "x", "value_type": "text",
                              "source_mode": "pdf_only", "period_type": "x",
                              "scope_expectation": "x",
                              "currency_requirement": "not_applicable",
                              "unit_requirement": "not_applicable",
                              "evidence_requirement": "x",
                              "fallback_policy": "x", "description": "x"},
            "fix_assets": {"priority": "P0", "domain": "x",
                           "statement_type": "x", "value_type": "money",
                           "source_mode": "direct", "period_type": "x",
                           "scope_expectation": "x",
                           "currency_requirement": "applicable",
                           "unit_requirement": "applicable",
                           "evidence_requirement": "x",
                           "fallback_policy": "x", "description": "x"},
        },
    }), encoding="utf-8")
    db_path = tmp_path / "out.db"
    exit_code = main([
        "index",
        "--runs", str(tmp_path / "runs"),
        "--db", str(db_path),
        "--taxonomy", str(tax_path),
    ])
    assert exit_code == 0
    assert db_path.exists()

    from financial_report_llm_extractor.cache.db_query import (
        list_companies,
        query_field,
    )
    assert ("600519", "2024-12-31", "CN", "test-1") in list_companies(
        db_path=db_path
    )
    audit_row = query_field(
        db_path=db_path, company="600519",
        period_end="2024-12-31", market="CN", field_id="audit_opinion",
    )
    assert audit_row is not None
    assert audit_row["priority"] == "P4"
    assert audit_row["value"].startswith("标准无保留意见")


def test_cli_index_command_explicit_catalog_version_overrides_taxonomy(
    tmp_path: Path,
) -> None:
    """`--catalog-version` override beats taxonomy version field."""
    import json as _json
    from financial_report_llm_extractor.cli import main

    src_eval = (Path(__file__).parent / "fixtures" / "cache_sample_run"
                / "evaluation.json")
    run_dir = tmp_path / "runs" / "600519_2024-12-31"
    run_dir.mkdir(parents=True)
    (run_dir / "evaluation.json").write_text(
        src_eval.read_text(encoding="utf-8"), encoding="utf-8"
    )

    tax_path = tmp_path / "tax.json"
    tax_path.write_text(_json.dumps({
        "catalog_id": "x", "version": "should-not-be-used",
        "source_priority_catalog": "x", "fields": {},
    }), encoding="utf-8")
    db_path = tmp_path / "out.db"
    main([
        "index",
        "--runs", str(tmp_path / "runs"),
        "--db", str(db_path),
        "--taxonomy", str(tax_path),
        "--catalog-version", "historical-snapshot",
    ])

    from financial_report_llm_extractor.cache.db_query import list_companies
    assert ("600519", "2024-12-31", "CN", "historical-snapshot") in (
        list_companies(db_path=db_path)
    )


def test_cli_query_command_returns_field_json(
    tmp_path: Path, capsys: "pytest.CaptureFixture[str]"
) -> None:
    """`query --field` outputs single field row as JSON."""
    import json as _json
    from financial_report_llm_extractor.cli import main

    src_eval = (Path(__file__).parent / "fixtures" / "cache_sample_run"
                / "evaluation.json")
    src_supp = (Path(__file__).parent / "fixtures" / "cache_sample_run"
                / "llm_evidence_supplement.json")
    run_dir = tmp_path / "runs" / "600519_2024-12-31"
    run_dir.mkdir(parents=True)
    (run_dir / "evaluation.json").write_text(
        src_eval.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (run_dir / "llm_evidence_supplement.json").write_text(
        src_supp.read_text(encoding="utf-8"), encoding="utf-8"
    )
    tax_path = tmp_path / "tax.json"
    tax_path.write_text(_json.dumps({
        "catalog_id": "x", "version": "v1",
        "source_priority_catalog": "x",
        "fields": {"audit_opinion": {
            "priority": "P4", "domain": "x", "statement_type": "x",
            "value_type": "text", "source_mode": "pdf_only",
            "period_type": "x", "scope_expectation": "x",
            "currency_requirement": "not_applicable",
            "unit_requirement": "not_applicable",
            "evidence_requirement": "x", "fallback_policy": "x",
            "description": "x"}},
    }), encoding="utf-8")
    db_path = tmp_path / "out.db"
    main([
        "index", "--runs", str(tmp_path / "runs"),
        "--db", str(db_path), "--taxonomy", str(tax_path),
    ])
    capsys.readouterr()  # discard index output

    exit_code = main([
        "query",
        "--db", str(db_path),
        "--company", "600519",
        "--period", "2024-12-31",
        "--market", "CN",
        "--field", "audit_opinion",
    ])
    assert exit_code == 0
    body = _json.loads(capsys.readouterr().out)
    assert body["field_id"] == "audit_opinion"
    assert body["value"].startswith("标准无保留意见")
    assert body["evidence_page"] == 55
    assert body["priority"] == "P4"


def test_cli_query_command_without_field_returns_full_extraction(
    tmp_path: Path, capsys: "pytest.CaptureFixture[str]"
) -> None:
    import json as _json
    from financial_report_llm_extractor.cli import main

    src_eval = (Path(__file__).parent / "fixtures" / "cache_sample_run"
                / "evaluation.json")
    src_supp = (Path(__file__).parent / "fixtures" / "cache_sample_run"
                / "llm_evidence_supplement.json")
    run_dir = tmp_path / "runs" / "600519_2024-12-31"
    run_dir.mkdir(parents=True)
    (run_dir / "evaluation.json").write_text(
        src_eval.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (run_dir / "llm_evidence_supplement.json").write_text(
        src_supp.read_text(encoding="utf-8"), encoding="utf-8"
    )
    tax_path = tmp_path / "tax.json"
    tax_path.write_text(_json.dumps({
        "catalog_id": "x", "version": "v1",
        "source_priority_catalog": "x", "fields": {},
    }), encoding="utf-8")
    db_path = tmp_path / "out.db"
    main(["index", "--runs", str(tmp_path / "runs"),
          "--db", str(db_path), "--taxonomy", str(tax_path)])
    capsys.readouterr()

    main([
        "query", "--db", str(db_path),
        "--company", "600519", "--period", "2024-12-31",
        "--market", "CN",
    ])
    body = _json.loads(capsys.readouterr().out)
    assert body["company"] == "600519"
    assert set(body["fields"]) == {"revenue", "audit_opinion", "fix_assets"}


def test_cli_query_command_miss_returns_exit_1(
    tmp_path: Path, capsys: "pytest.CaptureFixture[str]"
) -> None:
    from financial_report_llm_extractor.cli import main
    from financial_report_llm_extractor.cache.db import init_db

    db_path = tmp_path / "out.db"
    init_db(db_path)
    exit_code = main([
        "query", "--db", str(db_path),
        "--company", "nope", "--period", "2024-12-31",
        "--market", "CN", "--field", "x",
    ])
    assert exit_code == 1


def test_cli_query_command_db_not_initialized_returns_exit_2(
    tmp_path: Path, capsys: "pytest.CaptureFixture[str]"
) -> None:
    """If the DB file is missing or has no schema, query returns
    exit code 2 with a structured {miss, reason=db_not_initialized}
    response instead of a Python traceback."""
    import json as _json
    from financial_report_llm_extractor.cli import main

    nonexistent_db = tmp_path / "does_not_exist.db"
    exit_code = main([
        "query", "--db", str(nonexistent_db),
        "--company", "600519", "--period", "2024-12-31",
        "--market", "CN", "--field", "revenue",
    ])
    assert exit_code == 2
    body = _json.loads(capsys.readouterr().out)
    assert body["miss"] is True
    assert body["reason"] == "db_not_initialized"


def test_cli_query_command_market_is_required(tmp_path: Path) -> None:
    """`query` without --market must fail at argparse layer (exit 2)."""
    from financial_report_llm_extractor.cli import main
    db_path = tmp_path / "x.db"
    with pytest.raises(SystemExit) as excinfo:
        main([
            "query", "--db", str(db_path),
            "--company", "600519", "--period", "2024-12-31",
            "--field", "revenue",
        ])
    assert excinfo.value.code == 2


# ---------------------------------------------------------------------------
# R2 Task 3: --cache-ttl-hours / --no-cache / --skip-if-cached flags
# ---------------------------------------------------------------------------

def test_cli_fetch_source_inventory_default_ttl_is_24h(
    tmp_path: Path,
) -> None:
    """Default --cache-ttl-hours is 24."""
    from financial_report_llm_extractor.cli import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "fetch-source-inventory",
        "--company", "600519",
        "--year", "2024",
        "--market", "CN",
        "--providers", "akshare",
        "--out", str(tmp_path / "out"),
        "--catalog", "field_catalog/turtle_v015_source_mapping_minimal.json",
    ])
    assert args.cache_ttl_hours == 24
    assert args.no_cache is False
    assert args.skip_if_cached is False


def test_cli_fetch_source_inventory_no_cache_flag(tmp_path: Path) -> None:
    """--no-cache sets args.no_cache to True."""
    from financial_report_llm_extractor.cli import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "fetch-source-inventory",
        "--company", "600519",
        "--year", "2024",
        "--market", "CN",
        "--providers", "akshare",
        "--out", str(tmp_path / "out"),
        "--catalog", "field_catalog/turtle_v015_source_mapping_minimal.json",
        "--no-cache",
    ])
    assert args.no_cache is True


def test_cli_fetch_source_inventory_skip_if_cached_flag(tmp_path: Path) -> None:
    """--skip-if-cached sets args.skip_if_cached to True."""
    from financial_report_llm_extractor.cli import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "fetch-source-inventory",
        "--company", "600519",
        "--year", "2024",
        "--market", "CN",
        "--providers", "akshare",
        "--out", str(tmp_path / "out"),
        "--catalog", "field_catalog/turtle_v015_source_mapping_minimal.json",
        "--skip-if-cached",
    ])
    assert args.skip_if_cached is True


def test_cli_extract_llm_no_llm_cache_flag(tmp_path: Path) -> None:
    """`extract-llm --no-llm-cache` sets args.no_llm_cache to True."""
    from financial_report_llm_extractor.cli import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "extract-llm",
        "--pdf", str(tmp_path / "report.pdf"),
        "--company-id", "600519",
        "--catalog", "field_catalog/turtle_v015_source_mapping_minimal.json",
        "--taxonomy", "field_catalog/turtle_v015_field_taxonomy.json",
        "--llm-config", str(tmp_path / "llm.json"),
        "--out", str(tmp_path / "out"),
        "--no-llm-cache",
    ])
    assert args.no_llm_cache is True


def test_cli_extract_llm_batch_no_llm_cache_flag(tmp_path: Path) -> None:
    """`extract-llm-batch --no-llm-cache` sets args.no_llm_cache to True."""
    from financial_report_llm_extractor.cli import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "extract-llm-batch",
        "--manifest", str(tmp_path / "manifest.json"),
        "--catalog", "field_catalog/turtle_v015_source_mapping_minimal.json",
        "--taxonomy", "field_catalog/turtle_v015_field_taxonomy.json",
        "--llm-config", str(tmp_path / "llm.json"),
        "--out", str(tmp_path / "out"),
        "--no-llm-cache",
    ])
    assert args.no_llm_cache is True


def test_cli_evaluate_company_no_llm_cache_flag(tmp_path: Path) -> None:
    """`evaluate-company --no-llm-cache` sets args.no_llm_cache to True."""
    from financial_report_llm_extractor.cli import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "evaluate-company",
        "--company", "600519",
        "--year", "2024",
        "--market", "CN",
        "--inventory", str(tmp_path / "inv.jsonl"),
        "--catalog", "field_catalog/turtle_v015_source_mapping_minimal.json",
        "--taxonomy", "field_catalog/turtle_v015_field_taxonomy.json",
        "--out", str(tmp_path / "out"),
        "--no-llm-cache",
    ])
    assert args.no_llm_cache is True
