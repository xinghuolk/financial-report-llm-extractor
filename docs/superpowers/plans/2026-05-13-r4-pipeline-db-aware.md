# R4 DB-Aware `pipeline` Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** Add a new `pipeline` CLI subcommand that runs fetch + evaluate end-to-end while consulting + updating the R1 SQLite DB. Pre-check: if (company, period_end, market, catalog_version=current) is already indexed, return the cached artifact_path without re-running. Otherwise: run fetch (R2 cache), run evaluate (R3 cache), auto-index into DB. Adds `--force` flag to bypass pre-check. Embeds catalog_version into evaluation.json for downstream R1 indexing accuracy.

**Architecture:** New `pipeline` subcommand orchestrates 4 steps:
1. Read catalog_version from taxonomy
2. Check R1 DB for existing extraction at (company, period_end, market, catalog_version)
3. If miss or --force: invoke fetch-source-inventory (uses R2 cache) + evaluate-company (uses R3 cache)
4. Auto-index resulting evaluation.json into DB

Plus: `company_evaluation.py` writes `catalog_version` field into `evaluation.json` so indexer no longer needs the warning-fallback path.

**Tech Stack:** Existing modules only. No new deps.

---

## File Structure

| File | Role |
|---|---|
| `src/financial_report_llm_extractor/cli.py` | Modified: new `pipeline` subcommand + dispatch |
| `src/financial_report_llm_extractor/structured_sources/company_evaluation.py` | Modified: write `catalog_version` into evaluation.json |
| `tests/test_cli_pipeline.py` | New: integration tests for `pipeline` command |
| `tests/test_cli.py` (extend) | `pipeline` arg parsing tests |
| `tests/test_company_evaluation.py` (or analogous) | Verify catalog_version embed |

---

## Key Design Decisions

1. **Pre-check before any work.** First DB hit avoids fetch + evaluate entirely. `--force` bypasses for re-validation.
2. **Auto-index after evaluate.** Same `_index_run` from R1 with current catalog_version. Idempotent UPSERT.
3. **Catalog version embedded in evaluation.json.** Forward-compat hook that R1's indexer already prefers (`payload.get("catalog_version") or catalog_version`). After R4 lands, `--catalog-version` warnings disappear for fresh runs.
4. **Pre-check key = (company, period_end, market, catalog_version).** Same as R1 extractions PK.
5. **DB path is required** (not optional). Pipeline = "DB-aware end-to-end runner"; without DB there's no pre-check.
6. **No artifact-path adoption shortcut.** Pre-check returns the cached artifact_path; user can read evaluation.json from it. Pipeline does NOT copy/symlink to a new out_dir; that's the operator's choice.

---

## Task 1: Embed `catalog_version` into evaluation.json

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/company_evaluation.py`
- Test: extend existing evaluation tests

### Step 1.1: Locate the evaluation.json write site

Search `company_evaluation.py` for where `evaluation.json` is written. Should be near the end of `run_company_evaluation` — look for `(out_dir / "evaluation.json").write_text(...)` or similar.

### Step 1.2: Add `catalog_version` reading + embedding

`run_company_evaluation` already takes `taxonomy_path: Path`. Read its `version` field and include it in the payload.

```python
def run_company_evaluation(
    *,
    ...,
    taxonomy_path: Path,
    ...,
) -> CompanyEvaluation:
    ...
    # Near the start, read catalog_version
    taxonomy_doc = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    catalog_version = str(taxonomy_doc.get("version", "unknown"))

    # Near the end, when building the evaluation payload
    evaluation_payload = {
        "company": company,
        "period_end": period_end_str,
        "market": market,
        "report_type": report_type_str,
        "generated_at": generated_at,
        "schema_version": "evaluation_v1",
        "catalog_version": catalog_version,  # NEW
        "summary": {...},
        "fields": {...},
    }
```

The exact location varies; read the function and slot it in where the JSON payload is constructed.

### Step 1.3: Test

Write a small test that asserts `evaluation.json["catalog_version"]` equals the taxonomy's version after a fresh evaluation. Likely belongs in `tests/test_company_evaluation.py` if that exists, or as a new test in `tests/test_cli_pipeline.py`.

### Step 1.4: Run tests + ruff + mypy
### Step 1.5: Commit

```bash
git commit -m "feat: r4 embed catalog_version into evaluation.json"
```

---

## Task 2: `pipeline` subcommand — pre-check + orchestrate + auto-index

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Test: `tests/test_cli_pipeline.py`

### Step 2.1: Add `pipeline` subparser

```python
pipeline_parser = subparsers.add_parser(
    "pipeline",
    help="DB-aware end-to-end: pre-check DB, fetch + evaluate if miss, auto-index.",
)
pipeline_parser.add_argument("--company", required=True, type=str)
pipeline_parser.add_argument("--year", type=int)
pipeline_parser.add_argument("--period-end", type=str)
pipeline_parser.add_argument(
    "--report-type", default="annual", type=str,
)
pipeline_parser.add_argument("--market", required=True, choices=["CN", "HK"])
pipeline_parser.add_argument("--pdf", type=Path)
pipeline_parser.add_argument(
    "--llm-config", type=Path,
    help="LLM transport config JSON. If omitted, LLM supplement step is skipped.",
)
pipeline_parser.add_argument(
    "--db", type=Path, default=Path("data/extracted.db"),
    help="SQLite cache DB path.",
)
pipeline_parser.add_argument(
    "--catalog", type=Path,
    default=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
)
pipeline_parser.add_argument(
    "--taxonomy", type=Path,
    default=Path("field_catalog/turtle_v015_field_taxonomy.json"),
)
pipeline_parser.add_argument(
    "--priorities", default="P0,P1,P2,P3,P4", type=str,
)
pipeline_parser.add_argument("--out", type=Path, required=True,
                             help="Output dir for fresh runs.")
pipeline_parser.add_argument(
    "--force", action="store_true",
    help="Bypass DB pre-check; always run fetch + evaluate.",
)
pipeline_parser.add_argument(
    "--no-cache", action="store_true",
    help="Bypass provider + LLM caches (R2 + R3 layer).",
)
```

### Step 2.2: Dispatch in `main()`

```python
if args.command == "pipeline":
    import json as _json
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.cache.db_query import query_extraction
    from financial_report_llm_extractor.cache.indexer import index_run
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        run_company_evaluation,
    )
    from financial_report_llm_extractor.structured_sources.source_inventory_fetch import (
        fetch_source_inventory,
    )

    # Resolve period
    if args.year is not None and args.period_end is not None:
        parser.error("--year and --period-end are mutually exclusive")
    if args.year is not None:
        period = PeriodSpec.from_year(args.year)
    elif args.period_end is not None:
        period = PeriodSpec.from_period_end(args.period_end, args.report_type)
    else:
        parser.error("one of --year or --period-end is required")

    # Read catalog_version from taxonomy
    taxonomy_doc = _json.loads(args.taxonomy.read_text(encoding="utf-8"))
    catalog_version = str(taxonomy_doc.get("version", "unknown"))
    period_end_str = period.period_end.isoformat()

    # Pre-check DB
    init_db(args.db)
    if not args.force:
        hit = query_extraction(
            db_path=args.db, company=args.company, period_end=period_end_str,
        )
        if hit is not None and hit.get("catalog_version") == catalog_version:
            print(_json.dumps({
                "status": "cache_hit",
                "company": args.company,
                "period_end": period_end_str,
                "catalog_version": catalog_version,
                "artifact_path": hit.get("artifact_path"),
                "field_count": len(hit.get("fields", {})),
            }, indent=2, sort_keys=True))
            return 0

    # Cache miss / force: run fetch + evaluate
    cache_root = None if args.no_cache else Path("tmp/.cache")
    priorities = tuple(p.strip() for p in args.priorities.split(",") if p.strip())

    # Fetch (R2 cache)
    # Build AKShare/Yahoo clients via existing _run_fetch_source_inventory helper,
    # OR inline. The cleanest path: extract a small helper from _run_fetch_source_inventory
    # that just builds the clients, then call fetch_source_inventory directly.
    #
    # For MVP, invoke _run_fetch_source_inventory programmatically by setting up an
    # argparse namespace stub. Or duplicate the client-construction logic. Pick
    # whichever is simpler.

    # Approach: directly call fetch_source_inventory + run_company_evaluation
    from financial_report_llm_extractor.structured_sources.akshare_adapter import (
        AkshareAdapter,
    )
    from financial_report_llm_extractor.structured_sources.yahoo_adapter import (
        YahooAdapter,
    )
    # Build clients — copy the pattern from _run_fetch_source_inventory
    akshare_client = ...  # see existing CLI helper
    yahoo_client = ...

    fetch_result = fetch_source_inventory(
        company=args.company, period=period, market=args.market,
        providers=("akshare", "yahoo"),
        akshare_client=akshare_client, yahoo_client=yahoo_client,
        out_dir=args.out, catalog_path=args.catalog,
        cache_root=cache_root, ttl_hours=24,
    )

    # Evaluate (R3 cache via cache_root inside run_company_evaluation)
    evaluation = run_company_evaluation(
        company=args.company, period=period, market=args.market,
        inventory_path=fetch_result.inventory_path,
        inventory_summary_path=fetch_result.summary_path,
        catalog_path=args.catalog, taxonomy_path=args.taxonomy,
        pdf_path=args.pdf, llm_config_path=args.llm_config,
        priorities=priorities, out_dir=args.out,
        cache_root=cache_root,
    )

    # Auto-index
    priority_map = {
        fid: str(info.get("priority", ""))
        for fid, info in taxonomy_doc.get("fields", {}).items()
    }
    n_fields = index_run(
        run_dir=args.out, db_path=args.db,
        catalog_version=catalog_version,
        priority_map=priority_map,
    )

    print(_json.dumps({
        "status": "fresh_run",
        "company": args.company,
        "period_end": period_end_str,
        "catalog_version": catalog_version,
        "artifact_path": str(args.out),
        "field_count": n_fields,
    }, indent=2, sort_keys=True))
    return 0
```

**NOTE:** The client construction logic (akshare_client, yahoo_client) is in `_run_fetch_source_inventory`. Best approach: refactor that into a small helper `_build_provider_clients(...)` so both `fetch-source-inventory` and `pipeline` can share it. If that's too invasive for the time budget, copy the construction inline with a TODO comment.

### Step 2.3: Tests

Create `tests/test_cli_pipeline.py`:

```python
"""pipeline command: pre-check DB, miss-then-hit, force flag."""

from pathlib import Path

import pytest


def test_cli_pipeline_subparser_parses_args(tmp_path: Path) -> None:
    from financial_report_llm_extractor.cli import build_parser
    parser = build_parser()
    args = parser.parse_args([
        "pipeline",
        "--company", "600519",
        "--year", "2024",
        "--market", "CN",
        "--out", str(tmp_path / "run1"),
    ])
    assert args.command == "pipeline"
    assert args.force is False
    assert args.no_cache is False


def test_cli_pipeline_force_flag(tmp_path: Path) -> None:
    from financial_report_llm_extractor.cli import build_parser
    parser = build_parser()
    args = parser.parse_args([
        "pipeline",
        "--company", "600519",
        "--year", "2024",
        "--market", "CN",
        "--out", str(tmp_path / "run1"),
        "--force",
    ])
    assert args.force is True


def test_cli_pipeline_db_pre_check_returns_cache_hit(
    tmp_path: Path, capsys: "pytest.CaptureFixture[str]",
    monkeypatch,
) -> None:
    """If DB has a matching (company, period, catalog_version) row, pipeline
    returns cache_hit JSON without invoking fetch/evaluate."""
    import json as _json
    from financial_report_llm_extractor.cli import main
    from financial_report_llm_extractor.cache.db import init_db
    from financial_report_llm_extractor.cache.indexer import index_run

    # Seed DB by indexing an existing fixture run
    fixture_dir = Path(__file__).parent / "fixtures" / "cache_sample_run"
    db_path = tmp_path / "out.db"
    init_db(db_path)
    # Use the taxonomy file's current version as catalog_version
    tax_path = Path("field_catalog/turtle_v015_field_taxonomy.json")
    taxonomy_doc = _json.loads(tax_path.read_text(encoding="utf-8"))
    catalog_version = taxonomy_doc.get("version", "unknown")
    priority_map = {
        fid: info.get("priority", "")
        for fid, info in taxonomy_doc.get("fields", {}).items()
    }
    index_run(
        run_dir=fixture_dir, db_path=db_path,
        catalog_version=catalog_version, priority_map=priority_map,
    )

    # Now run pipeline — should hit cache and exit fast
    capsys.readouterr()
    exit_code = main([
        "pipeline",
        "--company", "600519",
        "--year", "2024",
        "--market", "CN",
        "--db", str(db_path),
        "--out", str(tmp_path / "fresh_run"),
        # No --pdf, no --llm-config — would normally fail at evaluate step;
        # but cache hit skips that.
    ])
    assert exit_code == 0
    body = _json.loads(capsys.readouterr().out)
    assert body["status"] == "cache_hit"
    assert body["company"] == "600519"
    assert body["catalog_version"] == catalog_version
```

The third test verifies the DB pre-check pathway with a pre-seeded DB. Fresh-run path (cache miss + actual fetch/evaluate/index) requires network or mock fixtures and may be out of scope for MVP — add a TODO and rely on R1+R2+R3 individual coverage.

### Step 2.4: Run tests + ruff + mypy
### Step 2.5: Commit

```bash
git commit -m "feat: r4 pipeline subcommand — db pre-check + auto-index + force flag"
```

---

## Task 3: CLAUDE.md + phase-summary R4 pointer

```markdown
| R4 | `cli.py` pipeline subcommand + `company_evaluation.py` catalog_version embed | Two-level extraction cache layer-2 (orchestration): new `pipeline` CLI command runs fetch + evaluate + auto-index end-to-end with DB pre-check. If (company, period, catalog_version) already indexed → return cache_hit JSON, skip work. `--force` to bypass; `--no-cache` to bypass R2+R3 caches. `evaluation.json` now embeds `catalog_version` field (closes R1 indexer's stderr warning for fresh runs). |
```

```markdown
| **R4 DB-aware `pipeline` command** | **已落地 (2026-05-13)** | R4 plan | New `pipeline` subcommand: pre-check R1 DB for (company, period, catalog_version) → return cache_hit if present; else run fetch (R2 cache) + evaluate (R3 cache) + auto-index. `--force` bypass. `evaluation.json` embeds `catalog_version` for accurate R1 indexer labels (no more stderr warning on fresh runs). Phase R complete: 4 stages, two-level extraction cache shipped. |
```

```bash
git commit -m "docs: r4 pipeline command pointer in claude.md + phase-summary"
```

---

## Acceptance Criteria

- 3+ new tests passing (pipeline subparser, force flag, DB pre-check)
- Full suite no regressions
- ruff + mypy clean
- `evaluation.json` includes `catalog_version` field after Task 1
- Live verification: `pipeline --company 600519 --year 2024 --market CN --db data/extracted.db --out tmp/runs/600519_pipeline` runs fetch+evaluate+index on first call; second call returns `{"status": "cache_hit", ...}` instantly

## Self-Review

- [x] DB pre-check uses same PK as R1 (`extractions` table)
- [x] Auto-index uses same `index_run` from R1
- [x] catalog_version embedded — R1 indexer's warning path becomes legacy
- [x] `--force` bypass + `--no-cache` work independently
- [x] No new dependencies
