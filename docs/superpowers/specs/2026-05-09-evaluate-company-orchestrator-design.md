# evaluate-company Orchestrator Design Spec

> Date: 2026-05-09
> Status: Draft
> Predecessor phases: Phase I-A/I-A.2 (LLM extraction), Phase N4 (P2/P3 expansion), Phase I-C/I-C.1 (text-mode + whitespace fix)
> Roadmap follow-up: §"Status (2026-05-09)" branch closure prep — orchestrator becomes the regular local-validation and regression-gate command for source-first + LLM evaluation per (company, period).

## Goal

A reusable, env- or args-driven validation module that takes a single
(company, period) and produces a complete reviewable artifact bundle:
provider source-first export, optional LLM PDF supplement, evaluation
result with bucket classification and coverage counts. Becomes the
regular regression check for catalog/source-policy/LLM-prompt changes.

## Non-Goals

- Multi-company batch (`extract-llm-batch` already covers the LLM batch
  use case). Future batch wrapper can iterate evaluate-company.
- New retrieval / chunking / mapping / reconciliation logic. The
  orchestrator only wires existing modules.
- New provider adapters or new field semantics proof. Reuses
  `AKShareSourceAdapter`, `YahooSourceAdapter`, `provider_baseline_replay`,
  `extract-llm` as-is.
- Real-time monitoring or scheduled runs.
- Persistent run history / database. Each run is a self-contained dir
  under `tmp/runs/<company>_<period_end>/`.

## Architecture Overview

Two-step CLI separates network calls from deterministic evaluation:

```
fetch-source-inventory     →   live AKShare/Yahoo fetch       →   tmp/runs/<id>/source_inventory.jsonl
                                                                    + source_inventory_summary.json

evaluate-company           →   replay + (optional) LLM        →   tmp/runs/<id>/source_first_export.json
  reads source_inventory                                           + llm_evidence_supplement.json (if PDF set)
                                                                   + evaluation.json
                                                                   + evaluation.md
```

Each step is independently invokable. Step 1 hits network and is
opt-in. Step 2 is fully deterministic and CI-friendly.

## CLI Surface

### Subcommand `fetch-source-inventory`

```
uv run financial-report-llm-extractor fetch-source-inventory \
  --company 600519 \
  --period-end 2024-12-31 \
  --market CN \
  --providers akshare,yahoo \
  --out tmp/runs/600519_2024-12-31/
```

Optional shortcut: `--year 2024` expands to `--period-end 2024-12-31
--report-type annual`. `--year` and `--period-end` are mutually
exclusive; specifying both errors out.

### Subcommand `evaluate-company`

```
uv run financial-report-llm-extractor evaluate-company \
  --company 600519 \
  --period-end 2024-12-31 \
  --market CN \
  --inventory tmp/runs/600519_2024-12-31/source_inventory.jsonl \
  --inventory-summary tmp/runs/600519_2024-12-31/source_inventory_summary.json \
  --catalog field_catalog/turtle_v015_source_mapping_minimal.json \
  --taxonomy field_catalog/turtle_v015_field_taxonomy.json \
  --pdf downloads/cn_stocks/600519/annual/2024_年度报告.pdf \
  --llm-config tmp/llm_configs/deepseek.json \
  --priorities P0,P1,P2,P3 \
  --out tmp/runs/600519_2024-12-31/
```

LLM step runs only if `--pdf` AND `--llm-config` are both set; otherwise
skipped. The orchestrator merges any present `llm_evidence_supplement.json`
when building the source-first export, regardless of whether this run
created it (so users can also pre-supply a supplement from a separate
`extract-llm` run).

### Shell wrappers

```bash
# scripts/run-fetch-source-inventory.sh
COMPANY=600519 PERIOD_END=2024-12-31 MARKET=CN \
  PROVIDERS=akshare,yahoo \
  scripts/run-fetch-source-inventory.sh
```

```bash
# scripts/run-evaluate-company.sh
COMPANY=600519 PERIOD_END=2024-12-31 MARKET=CN \
  PDF_PATH=downloads/cn_stocks/600519/annual/2024_年度报告.pdf \
  LLM_CONFIG=tmp/llm_configs/deepseek.json \
  scripts/run-evaluate-company.sh
```

`YEAR=2024` is supported as shortcut on both wrappers (mutually exclusive
with `PERIOD_END`).

Default values where unset:
- `MARKET`: inferred from ticker pattern (`6\d{5}` / `[03]\d{5}` → CN, `\d{4,5}` → HK with `.HK` suffix); fail if ambiguous.
- `PROVIDERS`: `akshare,yahoo`.
- `REPORT_TYPE`: `annual`.
- `OUT_DIR`: `tmp/runs/${COMPANY}_${PERIOD_END}/`.
- `CATALOG`: `field_catalog/turtle_v015_source_mapping_minimal.json`.
- `TAXONOMY`: `field_catalog/turtle_v015_field_taxonomy.json`.
- `PRIORITIES`: `P0,P1,P2,P3`.

## Output Artifacts

```
tmp/runs/<COMPANY>_<PERIOD_END>/
├── source_inventory.jsonl                    # fetch-source-inventory writes
├── source_inventory_summary.json             # fetch-source-inventory writes
├── source_first_export.json                  # evaluate-company writes
├── llm_evidence_supplement.json              # evaluate-company writes if PDF + llm-config set
├── evaluation.json                           # evaluate-company writes
└── evaluation.md                             # evaluate-company writes
```

### evaluation.json schema

```json
{
  "schema_version": "company-evaluation-v1",
  "company": "600519",
  "period_end": "2024-12-31",
  "report_type": "annual",
  "market": "CN",
  "generated_at": "2026-05-09T...",
  "summary": {
    "total_fields": 56,
    "by_bucket": {
      "clean_present": 30,
      "unresolved_conflict": 3,
      "llm_supplement_present": 4,
      "source_unavailable": 12,
      "terminal_locked": 5,
      "not_in_scope": 2
    },
    "by_priority": {
      "P0": {"clean_present": 22, "total": 22},
      "P1": {"clean_present": 8,  "total": 11},
      "P2": {"clean_present": 0,  "total": 9},
      "P3": {"clean_present": 0,  "total": 14}
    }
  },
  "fields": {
    "revenue": {
      "bucket": "clean_present",
      "selected_source": "akshare",
      "value": "168838700000",
      "currency": "CNY",
      "unit": "raw"
    },
    "gross_profit": {
      "bucket": "terminal_locked",
      "reason": "yahoo_definition_unverified",
      "selected_source": null
    },
    ...
  }
}
```

### evaluation.md format

Human-readable summary with three sections:
1. Header: company / period / market / generated_at
2. Coverage table: priority × bucket grid
3. Per-field detail table (collapsed for clean_present, expanded for
   conflict / supplement / terminal)

Used for visual inspection and PR review attachments.

## Bucket Classification

`classify_field` is a pure function over `(SourceFirstExportItem,
LlmEvidenceSupplementItem | None, SourceMappingEntry,
FieldTaxonomyEntry, *, pdf_provided: bool)`. Buckets are mutually
exclusive; cascade evaluates in the order below and the first match wins.

| # | Bucket | Trigger |
|---|--------|---------|
| 1 | `terminal_locked` | catalog `verification_status` in `{"yahoo_definition_unverified", "provider_semantics_unverified"}` OR field is in the roadmap "Locked Terminal States" cohort defined as `gross_profit, cip, non_oper_income, non_oper_exp, other_cur_assets`. (List sourced from `docs/2026-05-08-roadmap-evaluation.zh.md` §0 bucket 4; encoded as a constant `TERMINAL_LOCKED_FIELDS` in `company_evaluation.py` so the source is traceable.) |
| 2 | `unresolved_conflict` | `export.conflict_classifications` non-empty |
| 3 | `clean_present` | `export.status == "present"` AND no review_notes AND no conflicts |
| 4 | `llm_supplement_present` | `export.status != "present"` AND `supplement is not None` AND `supplement.status == "present"` |
| 5 | `not_in_scope` | catalog `source_mode == "pdf_only"` AND `pdf_provided is False` (we did not even attempt the LLM path) |
| 6 | `source_unavailable` | everything else (export missing, no provider candidate, LLM either not attempted by source_mode or attempted-and-not-found) |

Notes:

- `not_in_scope` differs from `source_unavailable`: `not_in_scope` means
  the field could only come from PDF + LLM and we never ran the LLM
  step. `source_unavailable` means we did run all available paths and
  none returned a value. This distinction matters because adding a PDF
  to a future evaluate-company run can move fields from `not_in_scope`
  into a present or supplement bucket without it being a regression.
- `not_disclosed` (a stricter sub-bucket of `source_unavailable` for
  fields the LLM examined and confirmed absent) is deliberately deferred
  until disclosure-presence detection is reliable. Tracked in the
  Open Questions section.

## Module Boundaries

### `src/financial_report_llm_extractor/structured_sources/source_inventory_fetch.py` (~120 LoC)

```python
@dataclass(frozen=True)
class PeriodSpec:
    period_end: date          # canonical
    report_type: ReportType   # annual | half_year | quarterly | ttm

    @classmethod
    def from_year(cls, year: int) -> "PeriodSpec": ...
    @classmethod
    def from_period_end(cls, period_end: str, report_type: str = "annual") -> "PeriodSpec": ...


def fetch_source_inventory(
    *,
    company: str,
    period: PeriodSpec,
    market: Literal["CN", "HK"],
    providers: tuple[ProviderName, ...],
    akshare_client: AkShareClientProtocol | None = None,
    yahoo_client: YahooClientProtocol | None = None,
    out_dir: Path,
) -> SourceInventoryArtifact:
    """Live fetch from real (or injected fake) provider clients.
    Writes source_inventory.jsonl + source_inventory_summary.json.
    Reuses existing AKShareSourceAdapter / YahooSourceAdapter primitives
    from real_source_validation; new sample builder is per-(company, period)
    rather than the hardcoded list build_default_validation_samples uses.
    """
```

### `src/financial_report_llm_extractor/structured_sources/company_evaluation.py` (~180 LoC)

```python
BucketName = Literal[
    "clean_present", "unresolved_conflict", "llm_supplement_present",
    "source_unavailable", "terminal_locked", "not_in_scope",
]


@dataclass(frozen=True)
class CompanyFieldEvaluation:
    field_id: str
    bucket: BucketName
    selected_source: str | None
    value: str | None
    currency: str | None
    unit: str | None
    reason: str | None  # populated for non-clean buckets


@dataclass(frozen=True)
class CompanyEvaluation:
    company: str
    period: PeriodSpec
    market: str
    generated_at: str
    fields: tuple[CompanyFieldEvaluation, ...]
    by_bucket: Mapping[BucketName, int]
    by_priority: Mapping[str, Mapping[BucketName, int]]


def classify_field(
    export_item: SourceFirstExportItem,
    supplement_item: LlmEvidenceItem | None,
    mapping_entry: SourceMappingEntry,
    taxonomy_entry: FieldTaxonomyEntry,
    *,
    pdf_provided: bool,
) -> tuple[BucketName, str | None]: ...


def build_company_evaluation(
    *, company, period, market, export, supplement, catalog, taxonomy
) -> CompanyEvaluation: ...


def render_evaluation_markdown(evaluation: CompanyEvaluation) -> str: ...


def run_company_evaluation(
    *,
    company, period, market,
    inventory_path, inventory_summary_path,
    catalog_path, taxonomy_path,
    pdf_path: Path | None,
    llm_config_path: Path | None,
    priorities: tuple[str, ...],
    out_dir: Path,
    json_client: JsonClient | None = None,
) -> CompanyEvaluation:
    """Orchestrator: replay → optional LLM → classify → write artifacts."""
```

### CLI integration

`cli.py` adds two subparsers (`fetch-source-inventory`, `evaluate-company`)
that dispatch to the above functions. No business logic in `cli.py`.

### Reuse (no rewriting)

| Existing | Used by |
|----------|---------|
| `AKShareSourceAdapter`, `YahooSourceAdapter` (real_source_validation.py) | source_inventory_fetch.fetch_source_inventory |
| `map_source_inventory` (mapping.py) | run_company_evaluation |
| `reconcile_mapped_fields` (reconciliation.py) | run_company_evaluation |
| `build_source_first_export` (export.py) | run_company_evaluation |
| `run_llm_extraction_for_company` (llm_extraction_runner.py) | run_company_evaluation when pdf_path + llm_config set |
| `load_source_mapping_catalog`, `load_field_taxonomy_catalog` | both subcommands |

## Test Strategy

| Test | Type | Coverage | Default-on |
|------|------|----------|-----------|
| `test_source_inventory_fetch.py::test_fetch_with_fake_clients` | Unit | Fake AKShare + Yahoo clients return canned records → write inventory artifacts | ✅ |
| `test_source_inventory_fetch.py::test_period_spec_year_shortcut_expands` | Unit | `PeriodSpec.from_year(2024)` → period_end=2024-12-31, report_type=annual | ✅ |
| `test_source_inventory_fetch.py::test_period_spec_rejects_both_year_and_period_end` | Unit | CLI parser raises if both --year and --period-end | ✅ |
| `test_source_inventory_fetch.py::test_real_fetch_smoke` | Integration | gated `REAL_SOURCE_VALIDATION=1`; fetches one CN ticker | ❌ opt-in |
| `test_company_evaluation.py::test_classify_field_buckets` | Unit | each bucket has at least one positive + one negative case | ✅ |
| `test_company_evaluation.py::test_orchestrator_with_fake_clients` | Unit | full evaluate-company flow with FakeAkShareClient + FakeYahooClient + FakeJsonClient + canned PDF chunks | ✅ |
| `test_company_evaluation.py::test_renders_evaluation_markdown` | Unit | snapshot-style assertion on markdown output | ✅ |
| `test_company_evaluation.py::test_orchestrator_skips_llm_without_pdf` | Unit | evaluation runs when pdf_path=None | ✅ |
| `test_cli.py::test_evaluate_company_subcommand_dispatches_correctly` | Unit | CLI argv parsing → run_company_evaluation invoked with correct args | ✅ |

CI gate adds 5 unit tests to default `pytest -v`. Real provider/LLM
tests stay opt-in behind env-gated guards.

## Implementation Phasing

Four independent commits:

| Commit | Subject | LoC | Notes |
|--------|---------|----:|-------|
| 1 | `feat: source_inventory_fetch + fetch-source-inventory subcommand` | ~200 | New module + CLI wiring + 4 unit tests + shell wrapper |
| 2 | `feat: company_evaluation pure-function bucket classifier + markdown` | ~250 | New module + 4 unit tests; no CLI yet |
| 3 | `feat: evaluate-company subcommand orchestrator + shell wrapper` | ~150 | Wires Commits 1+2; 1 orchestrator test + 1 CLI test |
| 4 | `docs: add evaluate-company to CLAUDE.md + roadmap §6 + sample run` | ~50 | Doc-only |

Each commit independently green: pytest + ruff + mypy.

## Open Questions / Out-of-Branch Follow-ups

- Multi-company batch wrapper (post-MVP). Likely a thin loop over
  evaluate-company invocations.
- Coverage delta vs prior run (compare two evaluation.json files).
  Useful for "did this catalog change regress anything?". Phase 2.
- Auto-resolve `--pdf` from a downloads directory by `<company>_<period>` convention. YAGNI for MVP.
- TTM calculation. PeriodSpec already accommodates `report_type=ttm`,
  but the actual derivation logic (sum 4 quarters) is not in scope here.
- `not_disclosed` terminal sub-bucket. Currently bundled into
  `source_unavailable`. Phase 2 if disclosure-presence detection becomes
  reliable.

## Acceptance Criteria

- `uv run pytest -v` shows ≥ 9 new unit tests pass.
- `uv run ruff check .` clean.
- `uv run mypy src tests` clean.
- One end-to-end demo run on 600519 / 2024 succeeds with all 4 artifacts
  produced (gated by `REAL_SOURCE_VALIDATION=1` and DeepSeek API key).
- `evaluation.md` is human-readable and matches the priority × bucket
  shape described above.
- The roadmap `## 6. Validation Commands` block lists the new CLI.
