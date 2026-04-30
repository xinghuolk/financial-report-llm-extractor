"""Repository-local quick validation run layout helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class QuickValidationLayout:
    run_dir: Path
    pages_path: Path
    chunks_path: Path
    retrieval_probe_path: Path
    extraction_result_path: Path
    metadata_path: Path
    prompt_payloads_dir: Path
    raw_llm_responses_dir: Path
    parsed_llm_responses_dir: Path


def prepare_quick_validation_layout(
    root_dir: Path,
    report_id: str,
) -> QuickValidationLayout:
    run_dir = root_dir / "tmp" / "runs" / "quick_validation" / report_id
    prompt_payloads_dir = run_dir / "prompt_payloads"
    raw_llm_responses_dir = run_dir / "raw_llm_responses"
    parsed_llm_responses_dir = run_dir / "parsed_llm_responses"

    for directory in (
        run_dir,
        prompt_payloads_dir,
        raw_llm_responses_dir,
        parsed_llm_responses_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    return QuickValidationLayout(
        run_dir=run_dir,
        pages_path=run_dir / "pages.jsonl",
        chunks_path=run_dir / "chunks.jsonl",
        retrieval_probe_path=run_dir / "retrieval_probe.json",
        extraction_result_path=run_dir / "extraction_result.json",
        metadata_path=run_dir / "run_metadata.json",
        prompt_payloads_dir=prompt_payloads_dir,
        raw_llm_responses_dir=raw_llm_responses_dir,
        parsed_llm_responses_dir=parsed_llm_responses_dir,
    )
