# Phase 9 Contract Fixes And Quick Validation Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix known evidence/artifact contract bugs and add the minimal quick-validation run skeleton needed before document-map and row-discovery demos.

**Architecture:** Keep the fixes narrow. Retrieval remains field-scoped, but evidence selection becomes block-aware. Chunk and LLM artifact writers become consistent about nested directories and raw-response preservation. A small quick-validation helper defines run paths without implementing Phase 10 document-map behavior.

**Tech Stack:** Python 3.12, dataclasses, JSON/JSONL artifacts, pytest, ruff, mypy, existing CLI patterns.

---

## File Structure

- Modify: `src/financial_report_llm_extractor/retrieval.py`
  - Responsibility: retrieval scoring and evidence construction.
- Modify: `tests/test_retrieval.py`
  - Responsibility: focused regression for block-aware evidence selection.
- Modify: `src/financial_report_llm_extractor/chunking.py`
  - Responsibility: chunk artifact writing and metadata update.
- Modify: `tests/test_chunking.py`
  - Responsibility: nested output directory regression.
- Modify: `src/financial_report_llm_extractor/llm_transport.py`
  - Responsibility: OpenAI-compatible transport parsing and raw response archival.
- Modify: `tests/test_llm_transport.py`
  - Responsibility: malformed response archival regression.
- Create: `src/financial_report_llm_extractor/quick_validation.py`
  - Responsibility: conventional quick-validation run layout helpers.
- Create: `tests/test_quick_validation.py`
  - Responsibility: quick-validation path and directory behavior.
- Modify: `src/financial_report_llm_extractor/cli.py`
  - Responsibility: expose a tiny helper command only if needed for the skeleton.
- Modify: `tests/test_cli.py`
  - Responsibility: CLI delegation test only if a command is added.

---

### Task 1: Fix Retrieval Evidence Block Selection

**Files:**
- Modify: `tests/test_retrieval.py`
- Modify: `src/financial_report_llm_extractor/retrieval.py`

- [x] **Step 1: Write the failing test**

Add or keep a regression test where the candidate chunk contains multiple blocks and the matched alias appears in the second block.

```python
def test_retrieve_candidates_uses_matching_block_for_evidence(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    records = [
        {
            "record_type": "block",
            "source_pdf_hash": "hash",
            "block_id": "p0001_b0001",
            "page": 1,
            "kind": "layout_line",
            "text": "Revenue 100",
        },
        {
            "record_type": "block",
            "source_pdf_hash": "hash",
            "block_id": "p0001_b0002",
            "page": 1,
            "kind": "layout_line",
            "text": "Cash and cash equivalents 200",
        },
        {
            "record_type": "chunk",
            "source_pdf_hash": "hash",
            "chunk_id": "stmt_balance_sheet_p0001_p0001",
            "kind": "statement_table",
            "statement_kind": "balance_sheet",
            "page_start": 1,
            "page_end": 1,
            "block_ids": ["p0001_b0001", "p0001_b0002"],
            "block_texts": {
                "p0001_b0001": "Revenue 100",
                "p0001_b0002": "Cash and cash equivalents 200",
            },
            "text": "Revenue 100\nCash and cash equivalents 200",
        },
    ]
    chunks_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    fields = [
        FieldSpec(
            field_id="cash_and_cash_equivalents",
            priority="P0",
            aliases=("cash and cash equivalents",),
            statement_hints=("balance_sheet",),
        )
    ]

    result = retrieve_candidates(chunks_path, fields)

    evidence = result["fields"][0]["candidates"][0]["evidence"][0]
    assert evidence["block_id"] == "p0001_b0002"
    assert "Cash and cash equivalents" in evidence["snippet"]
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```powershell
uv run pytest tests/test_retrieval.py::test_retrieve_candidates_uses_matching_block_for_evidence -v
```

Expected before the fix: failure showing `block_id` is the first block or snippet does not match the cash block.

- [x] **Step 3: Implement block-aware evidence selection**

Update evidence construction so it inspects `block_texts` and chooses the block containing the strongest alias/snippet match. Keep the public retrieval output shape stable.

Implementation shape:

```python
def _select_evidence_block(
    candidate: RetrievalCandidate,
    field: FieldSpec,
) -> tuple[str, str]:
    block_texts = candidate.chunk.get("block_texts", {})
    aliases = tuple(alias.lower() for alias in field.aliases)

    for block_id, text in block_texts.items():
        normalized = text.lower()
        if any(alias in normalized for alias in aliases):
            return block_id, text

    block_ids = candidate.chunk.get("block_ids", [])
    if block_ids:
        first_block_id = block_ids[0]
        return first_block_id, block_texts.get(first_block_id, candidate.chunk["text"])

    return "", candidate.chunk["text"]
```

Adapt names to the existing code. Avoid rewriting the whole retrieval scorer.

- [x] **Step 4: Run retrieval tests**

Run:

```powershell
uv run pytest tests/test_retrieval.py -v
```

Expected: all retrieval tests pass.

- [x] **Step 5: Commit checkpoint**

Commit message:

```text
fix: select matching retrieval evidence block
```

---

### Task 2: Ensure Chunk Nested Output Directories

**Files:**
- Modify: `tests/test_chunking.py`
- Modify: `src/financial_report_llm_extractor/chunking.py`

- [x] **Step 1: Write or confirm the failing test**

Use a temp nested output path.

```python
def test_build_chunk_store_creates_nested_output_directory(tmp_path: Path) -> None:
    pages_path = tmp_path / "pages.jsonl"
    metadata_path = tmp_path / "run_metadata.json"
    chunks_path = tmp_path / "nested" / "chunks.jsonl"
    pages_path.write_text(
        json.dumps({"page": 1, "text": "Consolidated Income Statement\nRevenue 100"})
        + "\n",
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps({"source_pdf_hash": "hash", "artifacts": {}}),
        encoding="utf-8",
    )

    result = build_chunk_store(pages_path, metadata_path, chunks_path=chunks_path)

    assert result.chunks_path == chunks_path
    assert chunks_path.exists()
```

- [x] **Step 2: Run the test to verify behavior**

Run:

```powershell
uv run pytest tests/test_chunking.py::test_build_chunk_store_creates_nested_output_directory -v
```

Expected after implementation: PASS. If it already passes, keep it as the regression.

- [x] **Step 3: Implement if needed**

Ensure this line exists before opening `output_path`:

```python
output_path.parent.mkdir(parents=True, exist_ok=True)
```

- [x] **Step 4: Run chunking tests**

Run:

```powershell
uv run pytest tests/test_chunking.py -v
```

Expected: all chunking tests pass.

- [x] **Step 5: Commit checkpoint**

Commit message:

```text
fix: create nested chunk output directories
```

---

### Task 3: Archive Raw LLM Responses Before Parsing

**Files:**
- Modify: `tests/test_llm_transport.py`
- Modify: `src/financial_report_llm_extractor/llm_transport.py`

- [x] **Step 1: Write the failing test**

Inject an OpenAI-compatible response whose assistant content is not parseable JSON, then assert a raw artifact exists.

```python
def test_run_real_transport_probe_archives_unparseable_raw_response(
    tmp_path: Path,
) -> None:
    retrieval_probe_path = _write_retrieval_probe(tmp_path)
    config_path = _write_llm_config(tmp_path)
    output_path = tmp_path / "result.json"
    raw_dir = tmp_path / "raw"

    def transport(_request: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": "bad-response",
            "choices": [
                {
                    "message": {"content": "not json"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    with pytest.raises(LlmTransportError):
        run_real_transport_probe(
            retrieval_probe_path,
            config_path,
            output_path=output_path,
            raw_response_dir=raw_dir,
            transport=transport,
        )

    raw_files = list(raw_dir.glob("*.json"))
    assert raw_files
    raw_payload = json.loads(raw_files[0].read_text(encoding="utf-8"))
    assert raw_payload["raw_response"]["id"] == "bad-response"
```

Adapt helper names to the existing tests.

- [x] **Step 2: Run the test to verify it fails**

Run:

```powershell
uv run pytest tests/test_llm_transport.py::test_run_real_transport_probe_archives_unparseable_raw_response -v
```

Expected before fix: raw file missing or exception raised before archival.

- [x] **Step 3: Archive raw exchange before parsing**

Move raw exchange append/write before `_parse_openai_response()` or catch parse failures and write a raw/error artifact before re-raising.

Preferred behavior:

```python
raw_exchange = {
    "request": request_payload,
    "raw_response": raw_response,
    "provider": config.provider,
    "model": config.model,
    "base_url": config.base_url,
}
raw_exchanges.append(raw_exchange)
parsed = _parse_openai_response(raw_response)
```

If parsing raises, ensure `raw_exchanges` is still flushed to `raw_response_dir`.

- [x] **Step 4: Run LLM transport tests**

Run:

```powershell
uv run pytest tests/test_llm_transport.py -v
```

Expected: all LLM transport tests pass.

- [x] **Step 5: Commit checkpoint**

Commit message:

```text
fix: archive raw llm responses before parsing
```

---

### Task 4: Add Quick Validation Run Layout Helper

**Files:**
- Create: `src/financial_report_llm_extractor/quick_validation.py`
- Create: `tests/test_quick_validation.py`

- [x] **Step 1: Write the failing tests**

Test that a run layout is repository-local, report-id scoped, and creates nested artifact directories.

```python
def test_quick_validation_layout_creates_expected_paths(tmp_path: Path) -> None:
    layout = prepare_quick_validation_layout(tmp_path, "00001_2025_en")

    assert layout.run_dir == tmp_path / "tmp" / "runs" / "quick_validation" / "00001_2025_en"
    assert layout.pages_path == layout.run_dir / "pages.jsonl"
    assert layout.chunks_path == layout.run_dir / "chunks.jsonl"
    assert layout.retrieval_probe_path == layout.run_dir / "retrieval_probe.json"
    assert layout.extraction_result_path == layout.run_dir / "extraction_result.json"
    assert layout.metadata_path == layout.run_dir / "run_metadata.json"
    assert layout.prompt_payloads_dir.is_dir()
    assert layout.raw_llm_responses_dir.is_dir()
    assert layout.parsed_llm_responses_dir.is_dir()
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```powershell
uv run pytest tests/test_quick_validation.py -v
```

Expected before implementation: import error or missing function.

- [x] **Step 3: Implement the layout helper**

Create a small dataclass and helper.

```python
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


def prepare_quick_validation_layout(root_dir: Path, report_id: str) -> QuickValidationLayout:
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
```

- [x] **Step 4: Run quick-validation tests**

Run:

```powershell
uv run pytest tests/test_quick_validation.py -v
```

Expected: PASS.

- [x] **Step 5: Commit checkpoint**

Commit message:

```text
feat: add quick validation run layout helper
```

---

### Task 5: Optional CLI Delegation For Quick Validation Layout

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Decide if a command is needed**

If Phase 9 only needs a helper, skip this task and document command usage in Phase 10. If a command helps manual validation, add:

```powershell
financial-report-llm-extractor quick-layout --root . --report-id 00001_2025_en
```

- [x] **Step 2: Write a CLI delegation test if adding the command**

```python
def test_quick_layout_command_calls_quick_validation_layer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = {}

    def fake_prepare(root_dir: Path, report_id: str) -> Any:
        calls["root_dir"] = root_dir
        calls["report_id"] = report_id
        return SimpleNamespace(run_dir=tmp_path / "tmp" / "runs" / "quick_validation" / report_id)

    monkeypatch.setattr(cli.quick_validation, "prepare_quick_validation_layout", fake_prepare)

    exit_code = cli.main(["quick-layout", "--root", str(tmp_path), "--report-id", "00001_2025_en"])

    assert exit_code == 0
    assert calls == {"root_dir": tmp_path, "report_id": "00001_2025_en"}
```

- [x] **Step 3: Implement the minimal command if needed**

Add parser and handler following existing CLI delegation patterns.

- [x] **Step 4: Run CLI tests**

Run:

```powershell
uv run pytest tests/test_cli.py -v
```

Expected: PASS.

- [x] **Step 5: Commit checkpoint if implemented**

Commit message:

```text
feat: expose quick validation layout command
```

---

### Task 6: Full Verification

**Files:**
- No new files.

- [x] **Step 1: Run full tests**

Run:

```powershell
uv run pytest -v
```

Expected: all tests pass.

- [x] **Step 2: Run lint**

Run:

```powershell
uv run ruff check .
```

Expected: no ruff violations.

- [x] **Step 3: Run type check**

Run:

```powershell
uv run mypy src tests
```

Expected: no mypy errors.

- [x] **Step 4: Review final diff**

Run:

```powershell
git diff --stat
git status --short
```

Expected: only Phase 9 files changed.

- [x] **Step 5: Final commit if any task checkpoints were skipped**

Commit message:

```text
feat: prepare phase 9 quick validation skeleton
```

---

## Self-Review Checklist

- [x] Retrieval evidence points to the matched block.
- [x] Nested chunk output paths work.
- [x] Malformed LLM responses are archived.
- [x] Quick-validation layout stays under repository-local `tmp/`.
- [x] No tests require network or real PDF tooling.
- [x] Full pytest, ruff, and mypy verification results are recorded in the final response.
