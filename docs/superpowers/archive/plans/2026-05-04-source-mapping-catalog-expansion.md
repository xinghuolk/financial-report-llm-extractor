# Source Mapping Catalog Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the first strong provider candidates into the Turtle P0/P1 source mapping catalog and keep all weaker candidates reviewable.

**Architecture:** Add a small review helper beside `field_candidate_discovery.py` that reads the offline candidate report, applies a strict promotion policy, and writes JSON/Markdown review artifacts. Then update `field_catalog/turtle_v015_source_mapping_minimal.json` for the approved strong promotion set only. No provider, PDF, or LLM code is called.

**Tech Stack:** Python 3.11 standard library, existing JSON catalog loaders, existing provider candidate report, `pytest`, `ruff`, `mypy`.

---

## File Structure

- Create: `src/financial_report_llm_extractor/structured_sources/source_mapping_expansion.py`
  - Selects promoted/deferred candidates from `provider_field_candidate_report.json`.
  - Writes `source_mapping_expansion_review.json` and `.md`.
- Create: `tests/test_source_mapping_expansion.py`
  - Covers promotion policy, conflict blocking, and review writer output.
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`
  - Adds only the initial strong promotion set.
- Modify: `tests/test_source_mapping_catalog.py`
  - Updates minimal catalog expectations.
- Modify: `tests/test_field_candidate_discovery.py`
  - Adds after-expansion expectations for fewer catalog gaps.
- Modify: `src/financial_report_llm_extractor/cli.py` and `tests/test_cli.py`
  - Adds a thin `review-source-mapping-expansion` command.

## Task 1: Promotion Policy Helper

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/source_mapping_expansion.py`
- Create: `tests/test_source_mapping_expansion.py`

- [ ] **Step 1: Write failing promotion policy tests**

Add `tests/test_source_mapping_expansion.py`:

```python
from financial_report_llm_extractor.structured_sources.source_mapping_expansion import (
    CandidateDecision,
    decide_candidate_promotion,
)


def _candidate(
    *,
    field_id: str = "bond_payable",
    source: str = "akshare",
    raw_field_name: str = "BOND_PAYABLE",
    raw_field_code: str | None = "BOND_PAYABLE",
    strength: str = "strong",
    signals: tuple[str, ...] = ("exact_text", "statement_match", "period_support"),
) -> dict[str, object]:
    return {
        "field_id": field_id,
        "source": source,
        "raw_field_name": raw_field_name,
        "raw_field_code": raw_field_code,
        "score": 90,
        "strength": strength,
        "signals": list(signals),
        "target_count": 1,
        "period_count": 5,
        "record_count": 5,
    }


def test_decide_candidate_promotion_promotes_strong_exact_text_candidate() -> None:
    assert decide_candidate_promotion(
        _candidate(),
        existing_aliases_by_source={"akshare": {}},
    ) == CandidateDecision(
        field_id="bond_payable",
        source="akshare",
        raw_field_name="BOND_PAYABLE",
        raw_field_code="BOND_PAYABLE",
        action="promote",
        reason="strong deterministic candidate",
        aliases=("BOND_PAYABLE",),
    )


def test_decide_candidate_promotion_defers_keyword_overlap_candidate() -> None:
    decision = decide_candidate_promotion(
        _candidate(
            raw_field_name="Accounts Receivable",
            raw_field_code=None,
            strength="medium",
            signals=("keyword_overlap", "statement_match", "period_support"),
        ),
        existing_aliases_by_source={"yahoo": {}},
    )

    assert decision.action == "defer"
    assert decision.reason == "candidate is not strong"
    assert decision.aliases == ()


def test_decide_candidate_promotion_blocks_alias_conflict() -> None:
    decision = decide_candidate_promotion(
        _candidate(raw_field_name="BOND_PAYABLE", raw_field_code="BOND_PAYABLE"),
        existing_aliases_by_source={"akshare": {"BOND_PAYABLE": "other_field"}},
    )

    assert decision.action == "block"
    assert decision.reason == "alias already belongs to other_field"


def test_decide_candidate_promotion_defers_already_mapped_alias() -> None:
    decision = decide_candidate_promotion(
        _candidate(raw_field_name="BOND_PAYABLE", raw_field_code="BOND_PAYABLE"),
        existing_aliases_by_source={"akshare": {"BOND_PAYABLE": "bond_payable"}},
    )

    assert decision.action == "defer"
    assert decision.reason == "candidate already mapped"
    assert decision.aliases == ()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run pytest tests/test_source_mapping_expansion.py -v
```

Expected: fail with `ModuleNotFoundError` for `source_mapping_expansion`.

- [ ] **Step 3: Implement promotion policy helper**

Create `src/financial_report_llm_extractor/structured_sources/source_mapping_expansion.py`:

```python
"""Review-gated source mapping expansion from provider candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

ExpansionAction = Literal["promote", "defer", "block"]


@dataclass(frozen=True)
class CandidateDecision:
    field_id: str
    source: str
    raw_field_name: str
    raw_field_code: str | None
    action: ExpansionAction
    reason: str
    aliases: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def decide_candidate_promotion(
    candidate: dict[str, object],
    *,
    existing_aliases_by_source: dict[str, dict[str, str]],
) -> CandidateDecision:
    field_id = str(candidate["field_id"])
    source = str(candidate["source"])
    raw_field_name = str(candidate["raw_field_name"])
    raw_field_code = candidate.get("raw_field_code")
    code = raw_field_code if isinstance(raw_field_code, str) and raw_field_code else None
    signals = tuple(str(signal) for signal in candidate.get("signals", ()))
    strength = str(candidate["strength"])
    aliases = tuple(dict.fromkeys(value for value in (raw_field_name, code) if value))

    if strength != "strong":
        return CandidateDecision(
            field_id=field_id,
            source=source,
            raw_field_name=raw_field_name,
            raw_field_code=code,
            action="defer",
            reason="candidate is not strong",
            aliases=(),
        )
    if "statement_match" not in signals or "period_support" not in signals:
        return CandidateDecision(
            field_id=field_id,
            source=source,
            raw_field_name=raw_field_name,
            raw_field_code=code,
            action="defer",
            reason="candidate lacks required support signals",
            aliases=(),
        )
    if "existing_alias" not in signals and "exact_text" not in signals:
        return CandidateDecision(
            field_id=field_id,
            source=source,
            raw_field_name=raw_field_name,
            raw_field_code=code,
            action="defer",
            reason="candidate is not deterministic",
            aliases=(),
        )

    for alias in aliases:
        owner = existing_aliases_by_source.get(source, {}).get(alias)
        if owner == field_id:
            return CandidateDecision(
                field_id=field_id,
                source=source,
                raw_field_name=raw_field_name,
                raw_field_code=code,
                action="defer",
                reason="candidate already mapped",
                aliases=(),
            )
        if owner is not None and owner != field_id:
            return CandidateDecision(
                field_id=field_id,
                source=source,
                raw_field_name=raw_field_name,
                raw_field_code=code,
                action="block",
                reason=f"alias already belongs to {owner}",
                aliases=(),
            )

    return CandidateDecision(
        field_id=field_id,
        source=source,
        raw_field_name=raw_field_name,
        raw_field_code=code,
        action="promote",
        reason="strong deterministic candidate",
        aliases=aliases,
    )
```

- [ ] **Step 4: Run promotion policy tests**

Run:

```bash
uv run pytest tests/test_source_mapping_expansion.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/financial_report_llm_extractor/structured_sources/source_mapping_expansion.py tests/test_source_mapping_expansion.py
git commit -m "feat: decide source mapping candidate promotion"
```

## Task 2: Review Artifact Writer

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/source_mapping_expansion.py`
- Modify: `tests/test_source_mapping_expansion.py`

- [ ] **Step 1: Write failing review writer test**

Append to `tests/test_source_mapping_expansion.py`:

```python
import json
from pathlib import Path

from financial_report_llm_extractor.structured_sources.source_mapping_expansion import (
    write_source_mapping_expansion_review,
)
from financial_report_llm_extractor.structured_sources.field_candidate_discovery import (
    write_provider_field_candidate_report,
)


def test_write_source_mapping_expansion_review_uses_real_candidate_report(
    tmp_path: Path,
) -> None:
    candidate_result = write_provider_field_candidate_report(
        taxonomy_path=Path("field_catalog/turtle_v015_field_taxonomy.json"),
        mapping_catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        inventory_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz"
        ),
        summary_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/"
            "provider_field_inventory_summary.json"
        ),
        output_dir=tmp_path / "candidate_report",
        priorities=("P0", "P1"),
    )

    result = write_source_mapping_expansion_review(
        candidate_report_path=candidate_result.json_path,
        mapping_catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path,
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    promoted = {(item["field_id"], item["source"]) for item in payload["promoted"]}
    assert ("bond_payable", "akshare") in promoted
    assert ("financing_cash_flow", "yahoo") in promoted
    assert payload["summary"]["promoted_count"] >= 6
    assert payload["summary"]["deferred_count"] > 0
    assert payload["summary"]["no_candidate_count"] >= 0
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "## Promoted" in markdown
    assert "`bond_payable`" in markdown
    assert "## Deferred" in markdown
    assert "## No Provider Candidates" in markdown
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
uv run pytest tests/test_source_mapping_expansion.py::test_write_source_mapping_expansion_review_uses_real_candidate_report -v
```

Expected: fail because `write_source_mapping_expansion_review` is missing.

- [ ] **Step 3: Implement review writer**

Append to `source_mapping_expansion.py`:

```python
import json
from pathlib import Path


@dataclass(frozen=True)
class SourceMappingExpansionReviewResult:
    json_path: Path
    markdown_path: Path
    promoted_count: int
    deferred_count: int
    blocked_count: int


def write_source_mapping_expansion_review(
    *,
    candidate_report_path: Path,
    mapping_catalog_path: Path,
    output_dir: Path,
) -> SourceMappingExpansionReviewResult:
    candidate_report = json.loads(candidate_report_path.read_text(encoding="utf-8"))
    mapping_catalog = json.loads(mapping_catalog_path.read_text(encoding="utf-8"))
    existing_aliases = _existing_aliases_by_source(mapping_catalog)
    decisions = _decisions_from_candidate_report(
        candidate_report,
        existing_aliases_by_source=existing_aliases,
    )
    promoted = [decision for decision in decisions if decision.action == "promote"]
    deferred = [decision for decision in decisions if decision.action == "defer"]
    blocked = [decision for decision in decisions if decision.action == "block"]
    no_candidates = _no_candidate_fields(candidate_report)

    payload = {
        "report_id": "source_mapping_expansion_review",
        "candidate_report": str(candidate_report_path),
        "mapping_catalog": str(mapping_catalog_path),
        "candidate_summary": candidate_report.get("summary", {}),
        "promoted": [decision.to_dict() for decision in promoted],
        "deferred": [decision.to_dict() for decision in deferred],
        "blocked": [decision.to_dict() for decision in blocked],
        "no_candidates": no_candidates,
        "summary": {
            "promoted_count": len(promoted),
            "deferred_count": len(deferred),
            "blocked_count": len(blocked),
            "no_candidate_count": len(no_candidates),
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "source_mapping_expansion_review.json"
    markdown_path = output_dir / "source_mapping_expansion_review.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        _review_markdown(promoted, deferred, blocked, no_candidates),
        encoding="utf-8",
    )
    return SourceMappingExpansionReviewResult(
        json_path=json_path,
        markdown_path=markdown_path,
        promoted_count=len(promoted),
        deferred_count=len(deferred),
        blocked_count=len(blocked),
    )


def _existing_aliases_by_source(mapping_catalog: dict[str, object]) -> dict[str, dict[str, str]]:
    aliases_by_source: dict[str, dict[str, str]] = {}
    source_mappings = mapping_catalog.get("source_mappings", {})
    if not isinstance(source_mappings, dict):
        return aliases_by_source
    for field_id, entry in source_mappings.items():
        if not isinstance(entry, dict):
            continue
        source_aliases = entry.get("source_aliases", {})
        if not isinstance(source_aliases, dict):
            continue
        for source, aliases in source_aliases.items():
            if not isinstance(aliases, list):
                continue
            source_bucket = aliases_by_source.setdefault(str(source), {})
            for alias in aliases:
                source_bucket[str(alias)] = str(field_id)
    return aliases_by_source


def _decisions_from_candidate_report(
    candidate_report: dict[str, object],
    *,
    existing_aliases_by_source: dict[str, dict[str, str]],
) -> tuple[CandidateDecision, ...]:
    decisions: list[CandidateDecision] = []
    fields = candidate_report.get("fields", {})
    if not isinstance(fields, dict):
        return ()
    for field_id, entry in sorted(fields.items()):
        if not isinstance(entry, dict):
            continue
        providers = entry.get("providers", {})
        if not isinstance(providers, dict):
            continue
        for source, group in sorted(providers.items()):
            if not isinstance(group, dict):
                continue
            candidates = group.get("candidates", [])
            if not isinstance(candidates, list) or not candidates:
                continue
            candidate = dict(candidates[0])
            candidate["field_id"] = str(field_id)
            candidate["source"] = str(source)
            decisions.append(
                decide_candidate_promotion(
                    candidate,
                    existing_aliases_by_source=existing_aliases_by_source,
                )
            )
    return tuple(decisions)


def _no_candidate_fields(candidate_report: dict[str, object]) -> list[dict[str, str]]:
    fields = candidate_report.get("fields", {})
    if not isinstance(fields, dict):
        return []
    result: list[dict[str, str]] = []
    for field_id, entry in sorted(fields.items()):
        if not isinstance(entry, dict):
            continue
        providers = entry.get("providers", {})
        status = str(entry.get("status", ""))
        if isinstance(providers, dict) and providers:
            continue
        if status == "not_applicable":
            continue
        result.append(
            {
                "field_id": str(field_id),
                "status": status,
                "statement_type": str(entry.get("statement_type", "")),
            }
        )
    return result


def _review_markdown(
    promoted: list[CandidateDecision],
    deferred: list[CandidateDecision],
    blocked: list[CandidateDecision],
    no_candidates: list[dict[str, str]],
) -> str:
    lines = ["# Source Mapping Expansion Review", ""]
    for title, decisions in (
        ("Promoted", promoted),
        ("Deferred", deferred),
        ("Blocked", blocked),
    ):
        lines.extend([f"## {title}", ""])
        if not decisions:
            lines.append("- None")
            lines.append("")
            continue
        for decision in decisions:
            aliases = ", ".join(f"`{alias}`" for alias in decision.aliases) or "-"
            lines.append(
                f"- `{decision.field_id}` `{decision.source}`: {decision.reason}; aliases: {aliases}"
            )
        lines.append("")
    lines.extend(["## No Provider Candidates", ""])
    if not no_candidates:
        lines.extend(["- None", ""])
    else:
        for item in no_candidates:
            lines.append(
                f"- `{item['field_id']}`: {item['status']}; statement: {item['statement_type']}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Run review writer test**

Run:

```bash
uv run pytest tests/test_source_mapping_expansion.py::test_write_source_mapping_expansion_review_uses_real_candidate_report -v
```

Expected: pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/financial_report_llm_extractor/structured_sources/source_mapping_expansion.py tests/test_source_mapping_expansion.py
git commit -m "feat: write source mapping expansion review"
```

## Task 3: Expand Minimal Source Mapping Catalog

**Files:**
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`
- Modify: `tests/test_source_mapping_catalog.py`

- [ ] **Step 1: Write failing catalog expectation test**

Add to `tests/test_source_mapping_catalog.py`:

```python
def test_minimal_source_mapping_includes_first_candidate_promotions() -> None:
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    expected_fields = {
        "bond_payable",
        "cip",
        "defer_tax_liab",
        "financing_cash_flow",
        "invest_income",
        "investing_cash_flow",
    }
    assert expected_fields.issubset(catalog.entries)
    assert catalog.entries["bond_payable"].source_aliases["akshare"] == ("BOND_PAYABLE",)
    assert catalog.entries["cip"].source_aliases["akshare"] == ("CIP",)
    assert catalog.entries["defer_tax_liab"].source_aliases["akshare"] == (
        "DEFER_TAX_LIAB",
    )
    assert catalog.entries["financing_cash_flow"].source_aliases["yahoo"] == (
        "Financing Cash Flow",
    )
    assert catalog.entries["invest_income"].source_aliases["akshare"] == (
        "INVEST_INCOME",
    )
    assert catalog.entries["investing_cash_flow"].source_aliases["yahoo"] == (
        "Investing Cash Flow",
    )
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
uv run pytest tests/test_source_mapping_catalog.py::test_minimal_source_mapping_includes_first_candidate_promotions -v
```

Expected: fail because the six promoted fields are not in the minimal mapping catalog.

- [ ] **Step 3: Edit source mapping catalog**

Modify `field_catalog/turtle_v015_source_mapping_minimal.json`:

- Add P0 fields: `bond_payable`, `cip`, `financing_cash_flow`, `invest_income`, `investing_cash_flow`.
- Add P1 field: `defer_tax_liab`.
- Add `source_mappings` entries:
  - `bond_payable`: akshare alias `BOND_PAYABLE`
  - `cip`: akshare alias `CIP`
  - `defer_tax_liab`: akshare alias `DEFER_TAX_LIAB`
  - `financing_cash_flow`: yahoo alias `Financing Cash Flow`
  - `invest_income`: akshare alias `INVEST_INCOME`
  - `investing_cash_flow`: yahoo alias `Investing Cash Flow`

Each new entry must copy `value_type`, `statement_type`, `domain`, `source_mode`, `currency_requirement`, `unit_requirement`, and `fallback_policy` from taxonomy. Use `verification_status: "expected"`. Use coverage matrix `primary_route` for AKShare entries; use `primary_route: "yahoo_direct"` for Yahoo-only promoted cash-flow entries because the promoted candidate source is Yahoo.

- [ ] **Step 4: Run catalog tests**

Run:

```bash
uv run pytest tests/test_source_mapping_catalog.py::test_minimal_source_mapping_includes_first_candidate_promotions tests/test_source_mapping_catalog.py::test_minimal_source_mapping_entries_match_taxonomy_and_coverage -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add field_catalog/turtle_v015_source_mapping_minimal.json tests/test_source_mapping_catalog.py
git commit -m "feat: promote strong source mapping candidates"
```

## Task 4: Candidate Discovery Regression After Expansion

**Files:**
- Modify: `tests/test_field_candidate_discovery.py`

- [ ] **Step 1: Add after-expansion fixture expectations**

Update `test_provider_field_candidate_report_fixture_summary_is_stable` in `tests/test_field_candidate_discovery.py`:

```python
    assert payload["summary"]["field_count"] == 33
    assert payload["summary"]["inventory_record_count"] == 6771
    assert payload["summary"]["fields_with_candidates"] >= 25
    assert payload["summary"]["catalog_gap_fields"] <= 18
    assert payload["fields"]["bond_payable"]["status"] == "has_candidates"
    assert payload["fields"]["financing_cash_flow"]["status"] == "has_candidates"
```

- [ ] **Step 2: Run candidate discovery fixture test**

Run:

```bash
uv run pytest tests/test_field_candidate_discovery.py::test_provider_field_candidate_report_fixture_summary_is_stable -v
```

Expected: pass after the catalog expansion.

- [ ] **Step 3: Regenerate local candidate report**

Run:

```bash
uv run financial-report-llm-extractor discover-provider-fields \
  --taxonomy field_catalog/turtle_v015_field_taxonomy.json \
  --mapping-catalog field_catalog/turtle_v015_source_mapping_minimal.json \
  --inventory tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz \
  --summary tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json \
  --out tmp/runs/provider_field_candidate_discovery \
  --priorities P0,P1
```

Expected: command prints `fields=33`.

- [ ] **Step 4: Inspect regenerated summary**

Run:

```bash
jq '.summary' tmp/runs/provider_field_candidate_discovery/provider_field_candidate_report.json
```

Expected: `field_count` is `33`, `fields_with_candidates` is at least `25`, and `catalog_gap_fields` is at most `18`.

- [ ] **Step 5: Commit Task 4**

```bash
git add tests/test_field_candidate_discovery.py
git commit -m "test: validate candidate discovery after mapping expansion"
```

## Task 5: CLI For Expansion Review

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add CLI delegation test**

Add a fake result dataclass in `tests/test_cli.py`:

```python
@dataclass(frozen=True)
class FakeSourceMappingExpansionReviewResult:
    json_path: Path
    markdown_path: Path
    promoted_count: int
    deferred_count: int
    blocked_count: int
```

Add test:

```python
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
```

- [ ] **Step 2: Run CLI test and verify it fails**

Run:

```bash
uv run pytest tests/test_cli.py::test_review_source_mapping_expansion_command_calls_review_layer -v
```

Expected: fail because the command is missing.

- [ ] **Step 3: Add CLI parser and dispatch**

Modify `src/financial_report_llm_extractor/cli.py`:

```python
from financial_report_llm_extractor.structured_sources.source_mapping_expansion import (
    write_source_mapping_expansion_review,
)
```

Add parser:

```python
    expansion_review_parser = subparsers.add_parser("review-source-mapping-expansion")
    expansion_review_parser.add_argument("--candidate-report", required=True, type=Path)
    expansion_review_parser.add_argument("--mapping-catalog", required=True, type=Path)
    expansion_review_parser.add_argument("--out", required=True, type=Path)
```

Add dispatch:

```python
    if args.command == "review-source-mapping-expansion":
        result = write_source_mapping_expansion_review(
            candidate_report_path=args.candidate_report,
            mapping_catalog_path=args.mapping_catalog,
            output_dir=args.out,
        )
        print(f"promoted={result.promoted_count}")
        print(f"deferred={result.deferred_count}")
        print(f"blocked={result.blocked_count}")
        print(f"source_mapping_expansion_json={result.json_path}")
        print(f"source_mapping_expansion_markdown={result.markdown_path}")
        return 0
```

- [ ] **Step 4: Run CLI test**

Run:

```bash
uv run pytest tests/test_cli.py::test_review_source_mapping_expansion_command_calls_review_layer -v
```

Expected: pass.

- [ ] **Step 5: Commit Task 5**

```bash
git add src/financial_report_llm_extractor/cli.py tests/test_cli.py
git commit -m "feat: add source mapping expansion review cli"
```

## Task 6: End-To-End Verification

**Files:**
- Generated but not committed: `tmp/runs/source_mapping_catalog_expansion/`

- [ ] **Step 1: Generate expansion review artifact**

Run:

```bash
uv run financial-report-llm-extractor review-source-mapping-expansion \
  --candidate-report tmp/runs/provider_field_candidate_discovery/provider_field_candidate_report.json \
  --mapping-catalog field_catalog/turtle_v015_source_mapping_minimal.json \
  --out tmp/runs/source_mapping_catalog_expansion
```

Expected output contains `promoted=0`, `blocked=0`, and a nonzero `deferred=` value after the catalog has already been expanded.

- [ ] **Step 2: Run focused tests**

Run:

```bash
uv run pytest tests/test_source_mapping_expansion.py tests/test_source_mapping_catalog.py tests/test_field_candidate_discovery.py -v
```

Expected: all selected tests pass.

- [ ] **Step 3: Run full verification**

Run:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
git diff --check
```

Expected: all pass.

- [ ] **Step 4: Confirm no generated artifacts are staged**

```bash
git status --short
```

Expected: `tmp/runs/source_mapping_catalog_expansion/` may exist as untracked generated output, and no generated artifact is staged. Do not commit generated `tmp/` artifacts.

## Final Review Checklist

- [ ] No provider API, PDF, or LLM calls were added to default tests.
- [ ] `turtle_v015_source_mapping_minimal.json` loads with `load_source_mapping_catalog()`.
- [ ] Only strong deterministic candidates were promoted.
- [ ] Medium/weak candidates remain visible in review artifacts.
- [ ] Candidate discovery shows fewer catalog gaps after expansion.
- [ ] Generated `tmp/runs/source_mapping_catalog_expansion/` artifacts are not committed.
- [ ] Full verification passes.
