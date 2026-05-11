# Turtle Field Coverage And Prompt Budget Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic pre-LLM validation that reports Turtle field coverage and prompt-budget cost on real PDF chunk artifacts.

**Architecture:** Add a focused `coverage_budget` module that reuses the existing field catalog, evidence index, and field-first retrieval. It writes JSON and Markdown reports, then exposes the workflow through a CLI command and a no-network script. The gate blocks downstream real LLM extraction when required fields are missing or prompt chars exceed configured limits.

**Tech Stack:** Python 3.11, pytest, argparse CLI, JSON/Markdown artifacts, existing `EvidenceIndex` and `retrieve_field_first`, Bash.

---

### Task 1: Catalog Field Set Loading

**Files:**
- Create: `src/financial_report_llm_extractor/coverage_budget.py`
- Create: `tests/test_coverage_budget.py`

- [ ] **Step 1: Write the failing tests**

Add:

```python
import json
from pathlib import Path

from financial_report_llm_extractor.coverage_budget import load_catalog_field_ids


def test_load_catalog_field_ids_reads_priorities(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "catalog_id": "demo",
                "version": "2026-04-30",
                "priorities": [
                    {"priority": "P0", "fields": ["revenue", "net_profit"]},
                    {"priority": "P1", "fields": ["cash"]},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert load_catalog_field_ids(catalog_path, priorities=("P0",)) == (
        "revenue",
        "net_profit",
    )
    assert load_catalog_field_ids(catalog_path, priorities=("P0", "P1")) == (
        "revenue",
        "net_profit",
        "cash",
    )


def test_load_catalog_field_ids_uses_explicit_fields(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps({"catalog_id": "demo", "version": "2026-04-30", "priorities": []}),
        encoding="utf-8",
    )

    assert load_catalog_field_ids(
        catalog_path,
        priorities=("P0",),
        explicit_fields=("cash", "revenue"),
    ) == ("cash", "revenue")
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```bash
uv run pytest tests/test_coverage_budget.py::test_load_catalog_field_ids_reads_priorities tests/test_coverage_budget.py::test_load_catalog_field_ids_uses_explicit_fields -v
```

Expected: import failure because `coverage_budget.py` does not exist.

- [ ] **Step 3: Implement catalog loading**

Add:

```python
"""Coverage and prompt-budget metrics for Turtle field retrieval."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_catalog_field_ids(
    catalog_path: Path,
    *,
    priorities: tuple[str, ...],
    explicit_fields: tuple[str, ...] = (),
) -> tuple[str, ...]:
    if explicit_fields:
        return _dedupe(explicit_fields)

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    wanted = set(priorities)
    fields: list[str] = []
    for group in catalog.get("priorities", []):
        if group.get("priority") not in wanted:
            continue
        fields.extend(str(field_id) for field_id in group.get("fields", []))
    return _dedupe(tuple(fields))


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)
```

- [ ] **Step 4: Run the focused tests and confirm pass**

Run:

```bash
uv run pytest tests/test_coverage_budget.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/coverage_budget.py tests/test_coverage_budget.py
git commit -m "test: add turtle coverage catalog loading"
```

### Task 2: Coverage Metrics From Chunks

**Files:**
- Modify: `src/financial_report_llm_extractor/coverage_budget.py`
- Modify: `tests/test_coverage_budget.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
from financial_report_llm_extractor.coverage_budget import build_coverage_metrics


def test_build_coverage_metrics_reports_missing_and_prompt_chars() -> None:
    records = [
        {
            "record_type": "chunk",
            "chunk_id": "page_p0001",
            "kind": "page_text",
            "statement_kind": None,
            "page_start": 1,
            "page_end": 1,
            "block_ids": ["p0001_b0001"],
            "block_texts": {"p0001_b0001": "Revenue 2025 HK$ million 100 2024 90"},
            "text": "Revenue 2025 HK$ million 100 2024 90",
        }
    ]

    metrics = build_coverage_metrics(
        records,
        selected_fields=("revenue", "net_profit"),
        top_k_values=(1, 3),
    )

    first = metrics[0]
    assert first["top_k"] == 1
    assert first["total_fields"] == 2
    assert first["covered_fields"] == 1
    assert first["missing_fields"] == ["net_profit"]
    assert first["coverage_ratio"] == 0.5
    assert first["total_candidate_text_chars"] > 0
    assert first["rough_token_estimate"] > 0
    fields = {field["field_id"]: field for field in first["fields"]}
    assert fields["revenue"]["status"] == "candidates_found"
    assert fields["revenue"]["candidate_count"] == 1
    assert fields["revenue"]["top_evidence"]["block_id"] == "p0001_b0001"
    assert fields["net_profit"]["status"] == "missing"
```

- [ ] **Step 2: Run the test and confirm failure**

Run:

```bash
uv run pytest tests/test_coverage_budget.py::test_build_coverage_metrics_reports_missing_and_prompt_chars -v
```

Expected: import failure for `build_coverage_metrics`.

- [ ] **Step 3: Implement metrics building**

Add imports:

```python
import math

from financial_report_llm_extractor.evidence_index import build_evidence_index
from financial_report_llm_extractor.field_first_retrieval import (
    estimate_prompt_budget,
    retrieve_field_first,
)
```

Add:

```python
def build_coverage_metrics(
    records: list[dict[str, Any]],
    *,
    selected_fields: tuple[str, ...],
    top_k_values: tuple[int, ...],
) -> list[dict[str, Any]]:
    index = build_evidence_index(records)
    metrics: list[dict[str, Any]] = []
    for top_k in top_k_values:
        retrieval = retrieve_field_first(index, selected_fields, top_k=top_k)
        budget = estimate_prompt_budget(retrieval)
        budget_by_field = {
            str(field["field_id"]): field for field in budget.get("fields", [])
        }
        field_metrics = [
            _field_metric(field, budget_by_field.get(str(field.get("field_id")), {}))
            for field in retrieval.get("fields", [])
        ]
        missing_fields = [
            str(field["field_id"])
            for field in field_metrics
            if field["status"] != "candidates_found"
        ]
        covered_fields = len(field_metrics) - len(missing_fields)
        total_chars = int(budget["total_candidate_text_chars"])
        total_fields = len(field_metrics)
        metrics.append(
            {
                "top_k": top_k,
                "total_fields": total_fields,
                "covered_fields": covered_fields,
                "missing_fields": missing_fields,
                "coverage_ratio": covered_fields / total_fields if total_fields else 0.0,
                "total_candidate_text_chars": total_chars,
                "rough_token_estimate": math.ceil(total_chars / 4),
                "fields": field_metrics,
            }
        )
    return metrics


def _field_metric(
    field: dict[str, Any],
    budget_field: dict[str, Any],
) -> dict[str, Any]:
    candidates = field.get("candidates", [])
    first_candidate = candidates[0] if candidates else {}
    evidence = first_candidate.get("evidence", {})
    return {
        "field_id": str(field.get("field_id", "")),
        "status": str(field.get("status", "missing")),
        "candidate_count": int(budget_field.get("candidate_count", len(candidates))),
        "candidate_text_chars": int(budget_field.get("candidate_text_chars", 0)),
        "top_score": first_candidate.get("score"),
        "top_evidence": {
            "page": evidence.get("page"),
            "chunk_id": evidence.get("chunk_id"),
            "block_id": evidence.get("block_id"),
            "snippet": evidence.get("snippet"),
        },
    }
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_coverage_budget.py -v
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/coverage_budget.py tests/test_coverage_budget.py
git commit -m "test: add turtle coverage budget metrics"
```

### Task 3: Go/No-Go Gate

**Files:**
- Modify: `src/financial_report_llm_extractor/coverage_budget.py`
- Modify: `tests/test_coverage_budget.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
from financial_report_llm_extractor.coverage_budget import evaluate_coverage_gate


def test_evaluate_coverage_gate_blocks_missing_fields() -> None:
    metrics = [
        {
            "top_k": 3,
            "missing_fields": ["net_profit"],
            "total_candidate_text_chars": 100,
            "fields": [
                {"field_id": "revenue", "candidate_text_chars": 100},
                {"field_id": "net_profit", "candidate_text_chars": 0},
            ],
        }
    ]

    gate = evaluate_coverage_gate(
        metrics,
        required_top_k=3,
        max_total_chars=40_000,
        max_field_chars=8_000,
    )

    assert gate["status"] == "blocked_by_missing_fields"
    assert gate["blockers"] == ["net_profit"]


def test_evaluate_coverage_gate_blocks_prompt_budget() -> None:
    metrics = [
        {
            "top_k": 3,
            "missing_fields": [],
            "total_candidate_text_chars": 50_000,
            "fields": [{"field_id": "revenue", "candidate_text_chars": 50_000}],
        }
    ]

    gate = evaluate_coverage_gate(
        metrics,
        required_top_k=3,
        max_total_chars=40_000,
        max_field_chars=8_000,
    )

    assert gate["status"] == "blocked_by_prompt_budget"
    assert gate["blockers"] == ["total_candidate_text_chars", "revenue"]


def test_evaluate_coverage_gate_allows_ready_metrics() -> None:
    metrics = [
        {
            "top_k": 3,
            "missing_fields": [],
            "total_candidate_text_chars": 10_000,
            "fields": [{"field_id": "revenue", "candidate_text_chars": 1_000}],
        }
    ]

    gate = evaluate_coverage_gate(
        metrics,
        required_top_k=3,
        max_total_chars=40_000,
        max_field_chars=8_000,
    )

    assert gate["status"] == "ready_for_field_scoped_llm_probe"
    assert gate["blockers"] == []
```

- [ ] **Step 2: Run the tests and confirm failure**

Run:

```bash
uv run pytest tests/test_coverage_budget.py::test_evaluate_coverage_gate_blocks_missing_fields tests/test_coverage_budget.py::test_evaluate_coverage_gate_blocks_prompt_budget tests/test_coverage_budget.py::test_evaluate_coverage_gate_allows_ready_metrics -v
```

Expected: import failure for `evaluate_coverage_gate`.

- [ ] **Step 3: Implement gate evaluation**

Add:

```python
def evaluate_coverage_gate(
    metrics: list[dict[str, Any]],
    *,
    required_top_k: int,
    max_total_chars: int,
    max_field_chars: int,
) -> dict[str, Any]:
    selected_metric = _metric_for_top_k(metrics, required_top_k)
    missing_fields = list(selected_metric.get("missing_fields", []))
    if missing_fields:
        return {
            "status": "blocked_by_missing_fields",
            "required_top_k": required_top_k,
            "max_total_chars": max_total_chars,
            "max_field_chars": max_field_chars,
            "blockers": missing_fields,
        }

    blockers: list[str] = []
    if int(selected_metric.get("total_candidate_text_chars", 0)) > max_total_chars:
        blockers.append("total_candidate_text_chars")
    for field in selected_metric.get("fields", []):
        if int(field.get("candidate_text_chars", 0)) > max_field_chars:
            blockers.append(str(field.get("field_id", "")))
    if blockers:
        return {
            "status": "blocked_by_prompt_budget",
            "required_top_k": required_top_k,
            "max_total_chars": max_total_chars,
            "max_field_chars": max_field_chars,
            "blockers": blockers,
        }

    return {
        "status": "ready_for_field_scoped_llm_probe",
        "required_top_k": required_top_k,
        "max_total_chars": max_total_chars,
        "max_field_chars": max_field_chars,
        "blockers": [],
    }


def _metric_for_top_k(metrics: list[dict[str, Any]], required_top_k: int) -> dict[str, Any]:
    for metric in metrics:
        if metric.get("top_k") == required_top_k:
            return metric
    raise ValueError(f"missing metrics for top_k={required_top_k}")
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_coverage_budget.py -v
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/coverage_budget.py tests/test_coverage_budget.py
git commit -m "test: add turtle coverage gate"
```

### Task 4: JSON And Markdown Reports

**Files:**
- Modify: `src/financial_report_llm_extractor/coverage_budget.py`
- Modify: `tests/test_coverage_budget.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
from financial_report_llm_extractor.coverage_budget import write_coverage_budget_report


def test_write_coverage_budget_report_writes_json_and_markdown(tmp_path: Path) -> None:
    metrics = [
        {
            "top_k": 3,
            "total_fields": 2,
            "covered_fields": 1,
            "missing_fields": ["net_profit"],
            "coverage_ratio": 0.5,
            "total_candidate_text_chars": 100,
            "rough_token_estimate": 25,
            "fields": [
                {
                    "field_id": "revenue",
                    "status": "candidates_found",
                    "candidate_count": 1,
                    "candidate_text_chars": 100,
                    "top_evidence": {
                        "page": 1,
                        "chunk_id": "page_p0001",
                        "block_id": "p0001_b0001",
                        "snippet": "Revenue 100",
                    },
                },
                {
                    "field_id": "net_profit",
                    "status": "missing",
                    "candidate_count": 0,
                    "candidate_text_chars": 0,
                    "top_evidence": {
                        "page": None,
                        "chunk_id": None,
                        "block_id": None,
                        "snippet": None,
                    },
                },
            ],
        }
    ]
    gate = {
        "status": "blocked_by_missing_fields",
        "required_top_k": 3,
        "max_total_chars": 40_000,
        "max_field_chars": 8_000,
        "blockers": ["net_profit"],
    }

    result = write_coverage_budget_report(
        output_dir=tmp_path,
        report_id="demo_report",
        catalog_id="demo_catalog",
        priorities=("P0", "P1"),
        selected_fields=("revenue", "net_profit"),
        top_k_values=(3,),
        metrics=metrics,
        gate=gate,
    )

    payload = json.loads(result["json"].read_text(encoding="utf-8"))
    assert payload["report_id"] == "demo_report"
    assert payload["gate"]["status"] == "blocked_by_missing_fields"
    markdown = result["markdown"].read_text(encoding="utf-8")
    assert "blocked_by_missing_fields" in markdown
    assert "net_profit" in markdown
    assert "Revenue 100" in markdown
```

- [ ] **Step 2: Run the test and confirm failure**

Run:

```bash
uv run pytest tests/test_coverage_budget.py::test_write_coverage_budget_report_writes_json_and_markdown -v
```

Expected: import failure for `write_coverage_budget_report`.

- [ ] **Step 3: Implement report writing**

Add:

```python
def write_coverage_budget_report(
    *,
    output_dir: Path,
    report_id: str,
    catalog_id: str,
    priorities: tuple[str, ...],
    selected_fields: tuple[str, ...],
    top_k_values: tuple[int, ...],
    metrics: list[dict[str, Any]],
    gate: dict[str, Any],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "coverage_budget.json"
    markdown_path = output_dir / "coverage_budget.md"
    payload = {
        "report_id": report_id,
        "catalog_id": catalog_id,
        "priorities": list(priorities),
        "selected_fields": list(selected_fields),
        "top_k_values": list(top_k_values),
        "gate": gate,
        "metrics": metrics,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_coverage_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def _coverage_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Coverage Budget: {payload['report_id']}",
        "",
        f"- gate: `{payload['gate']['status']}`",
        f"- priorities: `{','.join(payload['priorities'])}`",
        f"- blockers: `{', '.join(payload['gate'].get('blockers', []))}`",
        "",
        "| top_k | covered | total | coverage | chars | tokens_est |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for metric in payload["metrics"]:
        lines.append(
            "| {top_k} | {covered_fields} | {total_fields} | {coverage_ratio:.4f} | "
            "{total_candidate_text_chars} | {rough_token_estimate} |".format(**metric)
        )
    required_top_k = payload["gate"]["required_top_k"]
    selected = _metric_for_top_k(payload["metrics"], required_top_k)
    lines.extend(["", "## Missing Fields", ""])
    missing = selected.get("missing_fields", [])
    lines.extend(f"- `{field_id}`" for field_id in missing)
    lines.extend(["", "## Largest Fields", ""])
    largest = sorted(
        selected.get("fields", []),
        key=lambda field: int(field.get("candidate_text_chars", 0)),
        reverse=True,
    )[:20]
    lines.extend(
        f"- `{field['field_id']}`: {field['candidate_text_chars']} chars, "
        f"{field['candidate_count']} candidates"
        for field in largest
    )
    lines.extend(["", "## Evidence", ""])
    for field in selected.get("fields", []):
        evidence = field.get("top_evidence", {})
        lines.append(
            f"- `{field['field_id']}` {field['status']} page={evidence.get('page')} "
            f"block={evidence.get('block_id')} snippet={evidence.get('snippet')}"
        )
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_coverage_budget.py -v
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/coverage_budget.py tests/test_coverage_budget.py
git commit -m "test: write turtle coverage budget reports"
```

### Task 5: CLI And Real-PDF Script

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Create: `scripts/run-turtle-field-coverage-budget.sh`
- Modify: `tests/test_coverage_budget.py`

- [ ] **Step 1: Write CLI and script tests**

Append:

```python
from financial_report_llm_extractor.cli import build_parser


def test_cli_parses_coverage_budget_command() -> None:
    args = build_parser().parse_args(
        [
            "coverage-budget",
            "--chunks",
            "tmp/runs/quick_validation/demo/chunks.jsonl",
            "--catalog",
            "field_catalog/turtle_v015_priority_fields.json",
            "--report-id",
            "demo",
            "--priorities",
            "P0,P1",
            "--top-k-values",
            "1,3,5,8",
            "--required-top-k",
            "3",
            "--max-total-chars",
            "40000",
            "--max-field-chars",
            "8000",
            "--out-dir",
            "tmp/runs/coverage_budget/demo",
        ]
    )

    assert args.command == "coverage-budget"
    assert str(args.chunks).endswith("chunks.jsonl")
    assert args.priorities == "P0,P1"


def test_real_pdf_script_is_local_and_no_llm() -> None:
    script = Path("scripts/run-turtle-field-coverage-budget.sh").read_text(
        encoding="utf-8"
    )

    assert "quick-validate" in script
    assert "coverage-budget" in script
    assert "discover-rows-llm" not in script
    assert "extract --" not in script
```

- [ ] **Step 2: Run the tests and confirm failure**

Run:

```bash
uv run pytest tests/test_coverage_budget.py::test_cli_parses_coverage_budget_command tests/test_coverage_budget.py::test_real_pdf_script_is_local_and_no_llm -v
```

Expected: parser does not know `coverage-budget`, and script does not exist.

- [ ] **Step 3: Add CLI command**

In `src/financial_report_llm_extractor/cli.py`, import:

```python
import json
```

and:

```python
from financial_report_llm_extractor.coverage_budget import (
    build_coverage_metrics,
    evaluate_coverage_gate,
    load_catalog_field_ids,
    write_coverage_budget_report,
)
```

In `build_parser()`, add:

```python
    coverage_budget_parser = subparsers.add_parser("coverage-budget")
    coverage_budget_parser.add_argument("--chunks", required=True, type=Path)
    coverage_budget_parser.add_argument("--catalog", required=True, type=Path)
    coverage_budget_parser.add_argument("--report-id", required=True)
    coverage_budget_parser.add_argument("--priorities", default="P0,P1")
    coverage_budget_parser.add_argument("--fields", default="")
    coverage_budget_parser.add_argument("--top-k-values", default="1,3,5,8")
    coverage_budget_parser.add_argument("--required-top-k", default=3, type=int)
    coverage_budget_parser.add_argument("--max-total-chars", default=40_000, type=int)
    coverage_budget_parser.add_argument("--max-field-chars", default=8_000, type=int)
    coverage_budget_parser.add_argument("--out-dir", required=True, type=Path)
```

In `main()`, add before the final return:

```python
    if args.command == "coverage-budget":
        priorities = tuple(
            priority.strip() for priority in args.priorities.split(",") if priority.strip()
        )
        explicit_fields = tuple(
            field.strip() for field in args.fields.split(",") if field.strip()
        )
        top_k_values = tuple(
            int(value.strip()) for value in args.top_k_values.split(",") if value.strip()
        )
        selected_fields = load_catalog_field_ids(
            args.catalog,
            priorities=priorities,
            explicit_fields=explicit_fields,
        )
        records = [
            json.loads(line)
            for line in args.chunks.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        metrics = build_coverage_metrics(
            records,
            selected_fields=selected_fields,
            top_k_values=top_k_values,
        )
        gate = evaluate_coverage_gate(
            metrics,
            required_top_k=args.required_top_k,
            max_total_chars=args.max_total_chars,
            max_field_chars=args.max_field_chars,
        )
        report = write_coverage_budget_report(
            output_dir=args.out_dir,
            report_id=args.report_id,
            catalog_id=args.catalog.stem,
            priorities=priorities,
            selected_fields=selected_fields,
            top_k_values=top_k_values,
            metrics=metrics,
            gate=gate,
        )
        selected_metric = next(
            metric for metric in metrics if metric["top_k"] == args.required_top_k
        )
        print(f"fields={selected_metric['total_fields']}")
        print(f"covered={selected_metric['covered_fields']}")
        print(f"gate={gate['status']}")
        print(f"coverage_budget_json={report['json']}")
        print(f"coverage_budget_markdown={report['markdown']}")
        return 0
```

- [ ] **Step 4: Add real-PDF script**

Create `scripts/run-turtle-field-coverage-budget.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-.}"
CATALOG="${CATALOG:-field_catalog/turtle_v015_priority_fields.json}"
PRIORITIES="${PRIORITIES:-P0,P1}"
TOP_K_VALUES="${TOP_K_VALUES:-1,3,5,8}"
REQUIRED_TOP_K="${REQUIRED_TOP_K:-3}"
MAX_TOTAL_CHARS="${MAX_TOTAL_CHARS:-40000}"
MAX_FIELD_CHARS="${MAX_FIELD_CHARS:-8000}"
REPORTS="${REPORTS:-00001_2025_en=downloads/hk_stocks/00001/annual/2025_annual_en.pdf,01113_2025_en=downloads/hk_stocks/01113/annual/2025_annual_en.pdf}"

IFS=',' read -r -a report_specs <<< "${REPORTS}"
for report_spec in "${report_specs[@]}"; do
  report_id="${report_spec%%=*}"
  pdf="${report_spec#*=}"
  run_dir="${ROOT%/}/tmp/runs/quick_validation/${report_id}"
  chunks="${run_dir}/chunks.jsonl"
  out_dir="${ROOT%/}/tmp/runs/coverage_budget/${report_id}"

  if [[ ! -f "${pdf}" ]]; then
    echo "Missing PDF: ${pdf}" >&2
    exit 1
  fi

  uv run financial-report-llm-extractor quick-validate \
    --pdf "${pdf}" \
    --report-id "${report_id}" \
    --root "${ROOT}"

  uv run financial-report-llm-extractor coverage-budget \
    --chunks "${chunks}" \
    --catalog "${CATALOG}" \
    --report-id "${report_id}" \
    --priorities "${PRIORITIES}" \
    --top-k-values "${TOP_K_VALUES}" \
    --required-top-k "${REQUIRED_TOP_K}" \
    --max-total-chars "${MAX_TOTAL_CHARS}" \
    --max-field-chars "${MAX_FIELD_CHARS}" \
    --out-dir "${out_dir}"
done
```

- [ ] **Step 5: Make the script executable**

Run:

```bash
chmod +x scripts/run-turtle-field-coverage-budget.sh
```

- [ ] **Step 6: Run focused tests and shell syntax check**

Run:

```bash
uv run pytest tests/test_coverage_budget.py -v
bash -n scripts/run-turtle-field-coverage-budget.sh
```

Expected: tests pass and shell syntax check exits 0.

- [ ] **Step 7: Commit**

```bash
git add src/financial_report_llm_extractor/coverage_budget.py src/financial_report_llm_extractor/cli.py tests/test_coverage_budget.py scripts/run-turtle-field-coverage-budget.sh
git commit -m "test: add turtle coverage budget cli"
```

### Task 6: Documentation Gate Updates

**Files:**
- Modify: `docs/design/2026-04-30-llm-first-turtle-financial-extraction-design.md`
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`

- [ ] **Step 1: Update design document**

Add a section near the field-first retrieval discussion:

```markdown
### Turtle Field Coverage Budget Gate

Before broad real LLM extraction, run the Turtle field coverage and prompt
budget validation. The validation is local and deterministic: it loads the
configured Turtle field set, retrieves top-k evidence from the full-PDF evidence
index, and writes covered/missing fields plus prompt-character metrics.

If any required field is missing, downstream LLM extraction is blocked. If
coverage passes but total or per-field chars exceed the configured budget,
ranking/window reduction work comes first. This prevents later LLM, money
normalization, and review work from depending on a retrieval path that already
fails locally.
```

- [ ] **Step 2: Update roadmap**

In Phase 12, add:

```markdown
- Before field-scoped LLM extraction, run
  `scripts/run-turtle-field-coverage-budget.sh` for the required Turtle field
  set.
- Treat missing required fields or prompt-budget overflow as a roadmap blocker.
  Extend catalog aliases, evidence ranking, or window reduction before adding
  more real LLM extraction paths.
```

- [ ] **Step 3: Commit**

```bash
git add docs/design/2026-04-30-llm-first-turtle-financial-extraction-design.md docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md
git commit -m "docs: require turtle coverage budget gate"
```

### Task 7: Real Sample Validation

**Files:**
- Read: `downloads/hk_stocks/00001/annual/2025_annual_en.pdf`
- Read: `downloads/hk_stocks/01113/annual/2025_annual_en.pdf`
- Generated: `tmp/runs/coverage_budget/<report_id>/coverage_budget.json`
- Generated: `tmp/runs/coverage_budget/<report_id>/coverage_budget.md`

- [ ] **Step 1: Run the no-network real-PDF validation**

Run:

```bash
scripts/run-turtle-field-coverage-budget.sh
```

Expected: command exits 0 and prints `gate=...` for each report. The gate may
be blocked; blocked is a valid result for this validation.

- [ ] **Step 2: Inspect generated summaries**

Run:

```bash
uv run python - <<'PY'
import json
from pathlib import Path

for path in sorted(Path("tmp/runs/coverage_budget").glob("*/coverage_budget.json")):
    payload = json.loads(path.read_text(encoding="utf-8"))
    metric = next(
        item for item in payload["metrics"]
        if item["top_k"] == payload["gate"]["required_top_k"]
    )
    print(
        path.parent.name,
        "gate=" + payload["gate"]["status"],
        f"covered={metric['covered_fields']}/{metric['total_fields']}",
        f"chars={metric['total_candidate_text_chars']}",
        "blockers=" + ",".join(payload["gate"]["blockers"][:10]),
    )
PY
```

Expected: each configured report prints coverage, chars, and blockers.

- [ ] **Step 3: Commit only source/docs, not `tmp` artifacts**

Run:

```bash
git status --short
```

Expected: source/docs changes are already committed. `tmp/` artifacts may exist
locally and should stay untracked unless the user explicitly asks to commit
sample outputs.

### Task 8: Full Verification

- [ ] **Step 1: Run targeted tests**

```bash
uv run pytest tests/test_coverage_budget.py tests/test_field_first_retrieval.py -v
```

Expected: pass.

- [ ] **Step 2: Run all tests**

```bash
uv run pytest -v
```

Expected: pass.

- [ ] **Step 3: Run linters and typing**

```bash
uv run ruff check .
uv run mypy src tests
git diff --check
```

Expected: all pass.

- [ ] **Step 4: Final commit if verification required edits**

```bash
git add src/financial_report_llm_extractor/coverage_budget.py src/financial_report_llm_extractor/cli.py tests/test_coverage_budget.py scripts/run-turtle-field-coverage-budget.sh docs/design/2026-04-30-llm-first-turtle-financial-extraction-design.md docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md
git commit -m "test: validate turtle field coverage budget"
```

If there are no uncommitted changes, do not create an empty commit.

---

## Self-Review

- Spec coverage: the plan implements field-set loading, coverage metrics, prompt-budget metrics, gate decisions, JSON/Markdown reports, a CLI/script, documentation updates, and real sample validation.
- Placeholder scan: no placeholder markers or undefined later work are required to complete this plan.
- Type consistency: all planned public functions live in `coverage_budget.py` and use dict-shaped artifacts consistent with existing retrieval outputs.
