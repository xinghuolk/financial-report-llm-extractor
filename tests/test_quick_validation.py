from pathlib import Path

from financial_report_llm_extractor.quick_validation import (
    prepare_quick_validation_layout,
)


def test_quick_validation_layout_creates_expected_paths(tmp_path: Path) -> None:
    layout = prepare_quick_validation_layout(tmp_path, "00001_2025_en")

    assert (
        layout.run_dir
        == tmp_path / "tmp" / "runs" / "quick_validation" / "00001_2025_en"
    )
    assert layout.pages_path == layout.run_dir / "pages.jsonl"
    assert layout.chunks_path == layout.run_dir / "chunks.jsonl"
    assert layout.retrieval_probe_path == layout.run_dir / "retrieval_probe.json"
    assert layout.extraction_result_path == layout.run_dir / "extraction_result.json"
    assert layout.metadata_path == layout.run_dir / "run_metadata.json"
    assert layout.prompt_payloads_dir.is_dir()
    assert layout.raw_llm_responses_dir.is_dir()
    assert layout.parsed_llm_responses_dir.is_dir()
