# Alias Lifecycle PR-1 (matcher + audit CLI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship spec PR-1 — `alias_matching.py` (normalization matcher, diagnostic-only) + `audit-pdf-aliases` CLI (zero-LLM pre-flight PDF audit with production chunk-selection simulation, four-state classification, catalog patch emission).

**Architecture:** A pure-function matcher module feeds an audit module that calls the PRODUCTION `derive_targets`/`select_chunks`/`select_statement_section_chunks` for selection simulation, scans `record_type=="block"` chunks for alias diagnostics, classifies each field into exact_hit / prose_only_hit / normalized_only_hit / no_hit using `_STATEMENT_SECTION_ANCHORS` section pages, and writes JSON+MD+optional catalog patch. A thin CLI subcommand wires it up reusing the extract-llm ingest/chunk pattern.

**Tech Stack:** Python 3.11 stdlib only (project rule), pytest, frozen dataclasses, mypy strict, ruff line-length 88.

**Spec:** `docs/superpowers/specs/2026-06-10-alias-lifecycle-design.md` (rev 2). PR-3/PR-2 are separate plans.

**Verification gate for every commit:** `uv run pytest -q && uv run ruff check . && uv run mypy src tests`

---

## File structure

| File | Responsibility |
|---|---|
| Create `src/financial_report_llm_extractor/structured_sources/alias_matching.py` | normalize/fold + exact/normalized matching, token-aligned matched_text. Pure functions, zero project imports. |
| Create `src/financial_report_llm_extractor/structured_sources/alias_audit.py` | audit_chunks() core, dataclasses, JSON/MD/patch writers. Imports matcher + llm_extraction_runner selection functions. |
| Modify `src/financial_report_llm_extractor/cli.py` | `audit-pdf-aliases` subcommand (parser ~line 346 area, handler near extract-llm handler ~line 655). |
| Create `tests/test_alias_matching.py` | Task 1-2 unit tests. |
| Create `tests/test_alias_audit.py` | Task 3-6 tests incl. mini-fixture acceptance. |
| Create `tests/fixtures/pdf_chunks/alias_audit_mini_00001.jsonl` | Hand-built block records using real 00001 FY2025 phrasings (the big `00001_2025_chunks.jsonl` fixture is truncated and does NOT contain them — verified). |

Existing call targets (do not reimplement):
- `llm_extraction_runner.derive_targets(catalog, taxonomy, priorities)` → `list[LlmExtractionTarget]` (fields without pdf_aliases are skipped there)
- `llm_extraction_runner.select_chunks(chunks, target)` / `select_statement_section_chunks(chunks, target)` / `_STATEMENT_SECTION_ANCHORS` / `load_chunks_jsonl(path)`
- `catalog.load_source_mapping_catalog(path, priorities=...)`, `field_metadata.load_field_taxonomy(path)`
- `ingestion.ingest_pdf(pdf_path, output_dir)`, `chunking.build_chunk_store(pages_path, metadata_path, chunks_path=...)` — compose exactly as `cli.py:662-674` does

---

### Task 1: `normalize_phrase` token folding

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/alias_matching.py`
- Test: `tests/test_alias_matching.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for alias_matching (spec rev 2 component 1)."""
from __future__ import annotations

from financial_report_llm_extractor.structured_sources.alias_matching import (
    normalize_phrase,
)


def test_normalize_lowercases_and_folds_whitespace() -> None:
    assert normalize_phrase("Tax  Paid\n today") == "tax paid today"


def test_normalize_folds_apostrophes() -> None:
    # ASCII and U+2019; apostrophe fold happens before plural fold,
    # so auditor's -> auditors -> auditor.
    assert normalize_phrase("auditor's opinion") == "auditor opinion"
    assert normalize_phrase("auditor’s opinion") == "auditor opinion"


def test_normalize_folds_hyphens_to_spaces() -> None:
    assert normalize_phrase("one-time loss") == "one time los"


def test_normalize_plural_ies_to_y() -> None:
    assert normalize_phrase("related parties") == "related party"


def test_normalize_strips_trailing_s_only_for_long_tokens() -> None:
    # len > 3 guard: 'as'/'is' untouched (this guard supersedes the
    # rule-ordering concern from spec review: no 'as'->'a' asymmetry).
    assert normalize_phrase("payments as is") == "payment as is"


def test_normalize_drops_stop_tokens() -> None:
    assert (
        normalize_phrase("ageing analysis of the trade receivables")
        == "ageing analysi of trade receivable"
    )


def test_normalize_chinese_passthrough() -> None:
    # CJK aliases have no whitespace tokens / hyphens / trailing s.
    assert normalize_phrase("应收账款账龄") == "应收账款账龄"
    assert normalize_phrase("非经常性损益") == "非经常性损益"


def test_normalize_does_not_mangle_numbers_or_units() -> None:
    assert normalize_phrase("HK$ 5,571 million") == "hk$ 5,571 million"


def test_normalize_strips_edge_punctuation_before_plural_fold() -> None:
    # PDF tokens carry punctuation: "receivables," must still fold.
    assert normalize_phrase("trade receivables,") == "trade receivable"
    assert normalize_phrase("(5,571)") == "5,571"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_alias_matching.py -q`
Expected: FAIL — `ModuleNotFoundError`/`ImportError: cannot import name 'normalize_phrase'`

- [ ] **Step 3: Write the implementation**

```python
"""Normalization matcher for PDF alias auditing (spec PR-1, component 1).

Pure functions, no project imports. Diagnostic-only in PR-1: NOT wired
into live retrieval (that is PR-3, gated).

Fold pipeline (applied symmetrically to alias and text):
  1. lowercase            2. whitespace fold
  3. apostrophe removal   4. hyphen -> space
  5. edge-punctuation strip (PDF tokens carry ",.;:()" — must strip
     BEFORE plural fold or "receivables," never folds)
  6. plural fold (token: ies->y; strip trailing s when len > 3)
  7. stop-token drop (the/a/an)

The len>3 guard on s-stripping keeps short tokens (as/is) stable, which
resolves the rule-ordering asymmetry flagged in spec review.
"""
from __future__ import annotations

_STOP_TOKENS = frozenset({"the", "a", "an"})
_APOSTROPHES = ("'", "’")
_EDGE_PUNCT = ",.;:()\"“”"


def _fold_token(token: str) -> list[str]:
    """Fold one whitespace token; may split (hyphen) or drop (stop word)."""
    t = token.lower()
    for ch in _APOSTROPHES:
        t = t.replace(ch, "")
    out: list[str] = []
    for part in t.split("-"):
        part = part.strip(_EDGE_PUNCT)
        if not part:
            continue
        if part.endswith("ies") and len(part) > 3:
            part = part[:-3] + "y"
        elif part.endswith("s") and len(part) > 3:
            part = part[:-1]
        if part in _STOP_TOKENS:
            continue
        out.append(part)
    return out


def normalize_phrase(s: str) -> str:
    return " ".join(t for tok in s.split() for t in _fold_token(tok))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_alias_matching.py -q`
Expected: 9 passed

- [ ] **Step 5: Gate + commit**

```bash
uv run pytest -q && uv run ruff check . && uv run mypy src tests
git add src/financial_report_llm_extractor/structured_sources/alias_matching.py tests/test_alias_matching.py
git commit -m "feat: alias normalization fold pipeline (PR-1 task 1)"
```

---

### Task 2: `match_alias` with token-aligned matched_text

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/alias_matching.py`
- Test: `tests/test_alias_matching.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_alias_matching.py`)

```python
from financial_report_llm_extractor.structured_sources.alias_matching import (
    AliasMatch,
    match_alias,
)


def test_match_exact_is_whitespace_folded_substring() -> None:
    m = match_alias("tax paid", "Income taxes.  Tax  paid (5,571)")
    assert m is not None
    assert m.kind == "exact"
    assert m.count == 1


def test_match_exact_counts_occurrences() -> None:
    m = match_alias("revenue", "Revenue 280,036  total revenue note")
    assert m is not None and m.kind == "exact" and m.count == 2


def test_match_normalized_recovers_original_phrasing() -> None:
    # The motivating 00001 case: alias misses on inserted "the".
    text = (
        "The ageing analysis of the trade receivables, presented based "
        "on the invoice date, is as follows"
    )
    m = match_alias("ageing analysis of trade receivables", text)
    assert m is not None
    assert m.kind == "normalized"
    assert m.matched_text == "ageing analysis of the trade receivables,"


def test_match_normalized_plural_and_hyphen() -> None:
    m = match_alias("related party transactions", "39 Related parties transactions Except")
    assert m is not None and m.kind == "normalized"
    m2 = match_alias("one-off items", "certain one-time items in the year")
    # 'one-off' vs 'one-time' differ in tokens -> still no match (synonyms
    # are out of scope; catalog gains 'one-time' via suggested_aliases of
    # OTHER aliases or manual addition).
    assert m2 is None


def test_match_chinese_exact() -> None:
    m = match_alias("应收账款账龄", "本期 应收账款账龄 分析如下")
    assert m is not None and m.kind == "exact"


def test_match_none_when_absent() -> None:
    assert match_alias("research and development", "no such topic here") is None


def test_exact_preempts_normalized() -> None:
    # When the literal alias is present, kind must be exact even though
    # the normalized form also matches.
    m = match_alias("treasury shares", "did not hold any treasury shares")
    assert m is not None and m.kind == "exact"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_alias_matching.py -q`
Expected: FAIL — `ImportError: cannot import name 'AliasMatch'`

- [ ] **Step 3: Write the implementation** (append to `alias_matching.py`)

```python
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AliasMatch:
    alias: str
    kind: Literal["exact", "normalized"]
    matched_text: str
    count: int


def _ws_fold(s: str) -> str:
    return " ".join(s.lower().split())


def _norm_tokens_with_origin(text: str) -> tuple[list[str], list[int]]:
    """Normalized tokens + parallel index of the ORIGINAL whitespace token
    each came from (hyphen splits map several norm tokens to one origin)."""
    norm: list[str] = []
    origin: list[int] = []
    for i, tok in enumerate(text.split()):
        for folded in _fold_token(tok):
            norm.append(folded)
            origin.append(i)
    return norm, origin


def match_alias(alias: str, text: str) -> AliasMatch | None:
    """Exact (current select_chunks semantics) else normalized (fold
    pipeline, token-window match with original-text recovery)."""
    alias_ws = _ws_fold(alias)
    text_ws = _ws_fold(text)
    if alias_ws and alias_ws in text_ws:
        return AliasMatch(
            alias=alias, kind="exact",
            matched_text=alias_ws, count=text_ws.count(alias_ws),
        )

    alias_norm = [t for tok in alias.split() for t in _fold_token(tok)]
    if not alias_norm:
        return None
    text_norm, origin = _norm_tokens_with_origin(text)
    orig_tokens = text.split()
    n, count, first_span = len(alias_norm), 0, None
    for i in range(len(text_norm) - n + 1):
        if text_norm[i:i + n] == alias_norm:
            count += 1
            if first_span is None:
                first_span = (origin[i], origin[i + n - 1])
    if count == 0:
        return None
    assert first_span is not None
    matched = " ".join(orig_tokens[first_span[0]:first_span[1] + 1])
    return AliasMatch(
        alias=alias, kind="normalized", matched_text=matched, count=count,
    )
```

Note: `matched_text` spans original tokens, so the ageing case yields
`"ageing analysis of the trade receivables,"` WITH the trailing comma —
the PDF's literal phrasing. The Task 2 test asserts exactly that; the
suggested-alias writer strips edge punctuation later (Task 3's
`_SUGGESTION_STRIP`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_alias_matching.py -q`
Expected: 16 passed

- [ ] **Step 5: Gate + commit**

```bash
uv run pytest -q && uv run ruff check . && uv run mypy src tests
git add -u && git add tests/test_alias_matching.py
git commit -m "feat: match_alias exact/normalized with token-aligned recovery (PR-1 task 2)"
```

---

### Task 3: audit core `audit_chunks`

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/alias_audit.py`
- Test: `tests/test_alias_audit.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for alias_audit (spec PR-1, component 2)."""
from __future__ import annotations

from pathlib import Path
from typing import cast

from financial_report_llm_extractor.field_metadata import (
    FieldDomain,
    FieldTaxonomyCatalog,
    FieldTaxonomyEntry,
    FieldValueType,
    Priority,
)
from financial_report_llm_extractor.structured_sources.alias_audit import (
    AuditReport,
    audit_chunks,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
    SourceMappingEntry,
    SourceValueType,
    StatementType,
)


def _entry(field_id: str, *, pdf_aliases: tuple[str, ...],
           statement_type: str = "balance_sheet",
           value_type: str = "money") -> SourceMappingEntry:
    return SourceMappingEntry(
        field_id=field_id, priority="P0",
        value_type=cast(SourceValueType, value_type),
        statement_type=cast(StatementType, statement_type),
        currency_requirement="required", unit_requirement="required",
        source_aliases={"yahoo": ("X",)}, pdf_aliases=pdf_aliases,
    )


def _tax(field_id: str, *, statement_type: str = "balance_sheet",
         value_type: str = "money") -> FieldTaxonomyEntry:
    return FieldTaxonomyEntry(
        field_id=field_id, priority=cast(Priority, "P0"),
        domain=cast(FieldDomain, statement_type),
        statement_type=cast(StatementType, statement_type),
        value_type=cast(FieldValueType, value_type),
        source_mode="direct", period_type="duration",
        scope_expectation="unknown", currency_requirement="required",
        unit_requirement="required",
        evidence_requirement="source_only_allowed",
        fallback_policy="pdf_allowed", description="d",
    )


def _catalog(entries: list[SourceMappingEntry]) -> SourceMappingCatalog:
    return SourceMappingCatalog(
        catalog_id="t", version="1",
        entries={e.field_id: e for e in entries},
    )


def _taxonomy(entries: list[FieldTaxonomyEntry]) -> FieldTaxonomyCatalog:
    return FieldTaxonomyCatalog(
        catalog_id="tt", version="1", source_priority_catalog="p",
        fields={e.field_id: e for e in entries},
    )


def _block(chunk_id: str, page: int, text: str) -> dict[str, object]:
    return {"block_id": chunk_id, "chunk_id": chunk_id, "page": str(page),
            "record_type": "block", "text": text}


_CHUNKS: list[dict[str, object]] = [
    # cash-flow section page (anchor: "statement of cash flows")
    _block("c1", 141,
           "Consolidated statement of cash flows. Tax paid (5,571). "
           "Net cash from operating activities"),
    # MD&A prose page (NOT a cash-flow section page)
    _block("c2", 56, "partly offset by higher taxes paid in the year"),
    # notes page for the normalized-only case
    _block("c3", 229,
           "The ageing analysis of the trade receivables, presented "
           "based on the invoice date"),
    # income-statement section page for the clean exact case
    _block("c4", 134, "Consolidated income statement. Revenue 280,036"),
    # a non-block record that must be IGNORED by alias diagnostics
    {"chunk_id": "p134", "page": "134", "record_type": "page_text",
     "text": "Revenue Revenue Revenue"},
]


def _make() -> AuditReport:
    catalog = _catalog([
        _entry("revenue", pdf_aliases=("revenue",),
               statement_type="income_statement"),
        _entry("c_paid_for_taxes", pdf_aliases=("taxes paid",),
               statement_type="cash_flow"),
        _entry("receivables_aging",
               pdf_aliases=("ageing analysis of trade receivables",),
               statement_type="notes", value_type="text"),
        _entry("rd_exp", pdf_aliases=("research and development",),
               statement_type="income_statement"),
    ])
    taxonomy = _taxonomy([
        _tax("revenue", statement_type="income_statement"),
        _tax("c_paid_for_taxes", statement_type="cash_flow"),
        _tax("receivables_aging", statement_type="notes",
             value_type="text"),
        _tax("rd_exp", statement_type="income_statement"),
    ])
    return audit_chunks(
        chunks=list(_CHUNKS), catalog=catalog, taxonomy=taxonomy,
        priorities=("P0",), pdf_path=Path("fake.pdf"),
    )


def test_four_state_classification() -> None:
    r = _make()
    assert r.fields["revenue"].status == "exact_hit"
    # exact alias hit exists (p56) but outside the cash-flow section pages
    assert r.fields["c_paid_for_taxes"].status == "prose_only_hit"
    assert r.fields["receivables_aging"].status == "normalized_only_hit"
    assert r.fields["rd_exp"].status == "no_hit"


def test_suggested_aliases_carry_pdf_phrasing() -> None:
    r = _make()
    s = r.fields["receivables_aging"].suggested_aliases
    assert s == ("ageing analysis of the trade receivables",)


def test_alias_diagnostics_skip_non_block_records() -> None:
    r = _make()
    hits = r.fields["revenue"].hits
    # one block hit on p134; the page_text record (3 occurrences) ignored
    assert len(hits) == 1 and hits[0].page == 134 and hits[0].count == 1


def test_in_statement_section_flags() -> None:
    r = _make()
    tax_hits = r.fields["c_paid_for_taxes"].hits
    assert [h.in_statement_section for h in tax_hits] == [False]
    # notes has no section anchors -> None (not applicable)
    aging = r.fields["receivables_aging"].hits
    assert aging[0].in_statement_section is None


def test_selected_chunks_use_production_selection() -> None:
    r = _make()
    sel = r.fields["revenue"].selected_chunks
    # broad_keyword path (single alias < 3 -> broad strategy per
    # derive_targets); chunk c4 contains the token 'revenue'
    assert any(c.chunk_id == "c4" for c in sel)
    assert all(c.via in ("alias_top_k", "broad_keyword",
                         "section_fallback") for c in sel)


def test_section_anchor_coverage_reported() -> None:
    r = _make()
    assert 141 in r.section_anchor_coverage["cash_flow"]
    assert 134 in r.section_anchor_coverage["income_statement"]
    assert r.section_anchor_coverage["balance_sheet"] == ()


def test_summary_counts() -> None:
    r = _make()
    assert r.summary == {"exact_hit": 1, "prose_only_hit": 1,
                         "normalized_only_hit": 1, "no_hit": 1}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_alias_audit.py -q`
Expected: FAIL — `ModuleNotFoundError` for alias_audit

- [ ] **Step 3: Write the implementation**

```python
"""Pre-flight PDF alias audit (spec PR-1, component 2).

Zero-LLM diagnostic: simulates what the production retrieval would feed
the LLM (calls the REAL derive_targets / select_chunks /
select_statement_section_chunks — never reimplements selection) and adds
alias-level exact/normalized diagnostics over record_type=="block"
chunks only (chunks.jsonl stores each text 3 ways; blocks carry exact
pages and avoid double counting).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from financial_report_llm_extractor.field_metadata import FieldTaxonomyCatalog
from financial_report_llm_extractor.structured_sources.alias_matching import (
    match_alias,
)
from financial_report_llm_extractor.structured_sources.catalog import (
    SourceMappingCatalog,
)
from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
    _STATEMENT_SECTION_ANCHORS,
    LlmExtractionTarget,
    derive_targets,
    select_chunks,
    select_statement_section_chunks,
)

FieldAuditStatus = Literal[
    "exact_hit", "prose_only_hit", "normalized_only_hit", "no_hit"
]


@dataclass(frozen=True)
class AliasHit:
    alias: str
    kind: Literal["exact", "normalized"]
    page: int | None
    count: int
    in_statement_section: bool | None
    matched_text: str


@dataclass(frozen=True)
class SelectedChunk:
    chunk_id: str
    page: int | None
    via: Literal["alias_top_k", "broad_keyword", "section_fallback"]


@dataclass(frozen=True)
class FieldAuditResult:
    field_id: str
    status: FieldAuditStatus
    hits: tuple[AliasHit, ...] = ()
    selected_chunks: tuple[SelectedChunk, ...] = ()
    suggested_aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditReport:
    pdf_path: str
    catalog_version: str
    generated_at: str
    section_anchor_coverage: dict[str, tuple[int, ...]]
    fields: dict[str, FieldAuditResult] = field(default_factory=dict)

    @property
    def summary(self) -> dict[str, int]:
        out = {"exact_hit": 0, "prose_only_hit": 0,
               "normalized_only_hit": 0, "no_hit": 0}
        for r in self.fields.values():
            out[r.status] += 1
        return out


def _page_of(chunk: dict[str, object]) -> int | None:
    raw = chunk.get("page")
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return None


def _chunk_id_of(chunk: dict[str, object]) -> str:
    return str(chunk.get("chunk_id") or chunk.get("block_id") or "")


def _section_pages(
    blocks: list[dict[str, object]],
) -> dict[str, tuple[int, ...]]:
    """Pages whose block text matches a statement-type anchor phrase."""
    out: dict[str, set[int]] = {k: set() for k in _STATEMENT_SECTION_ANCHORS}
    for chunk in blocks:
        text = " ".join(str(chunk.get("text", "") or "").lower().split())
        page = _page_of(chunk)
        if page is None:
            continue
        for stype, anchors in _STATEMENT_SECTION_ANCHORS.items():
            if any(" ".join(a.split()) in text for a in anchors):
                out[stype].add(page)
    return {k: tuple(sorted(v)) for k, v in out.items()}


_SUGGESTION_STRIP = ",.;:"


def _audit_field(
    target: LlmExtractionTarget,
    blocks: list[dict[str, object]],
    all_chunks: list[dict[str, object]],
    section_pages: dict[str, tuple[int, ...]],
) -> FieldAuditResult:
    hits: list[AliasHit] = []
    in_section_pages = section_pages.get(target.statement_type)
    for alias in target.aliases:
        for chunk in blocks:
            m = match_alias(alias, str(chunk.get("text", "") or ""))
            if m is None:
                continue
            page = _page_of(chunk)
            in_section: bool | None = None
            if in_section_pages is not None:
                in_section = page in in_section_pages
            hits.append(AliasHit(
                alias=alias, kind=m.kind, page=page, count=m.count,
                in_statement_section=in_section,
                matched_text=m.matched_text,
            ))

    exact = [h for h in hits if h.kind == "exact"]
    normalized = [h for h in hits if h.kind == "normalized"]
    if exact and any(h.in_statement_section in (True, None) for h in exact):
        status: FieldAuditStatus = "exact_hit"
    elif exact:
        status = "prose_only_hit"
    elif normalized:
        status = "normalized_only_hit"
    else:
        status = "no_hit"

    suggested = tuple(dict.fromkeys(
        h.matched_text.strip(_SUGGESTION_STRIP).lower()
        for h in normalized
    ))

    selected = select_chunks(all_chunks, target)
    via: Literal["alias_top_k", "broad_keyword", "section_fallback"]
    via = target.chunk_strategy
    if not selected and target.absence_means_zero:
        selected = select_statement_section_chunks(all_chunks, target)
        via = "section_fallback"
    selected_chunks = tuple(
        SelectedChunk(chunk_id=_chunk_id_of(c), page=_page_of(c), via=via)
        for c in selected
    )

    return FieldAuditResult(
        field_id=target.field_id, status=status, hits=tuple(hits),
        selected_chunks=selected_chunks, suggested_aliases=suggested,
    )


def audit_chunks(
    *,
    chunks: list[dict[str, object]],
    catalog: SourceMappingCatalog,
    taxonomy: FieldTaxonomyCatalog,
    priorities: tuple[str, ...],
    pdf_path: Path,
) -> AuditReport:
    blocks = [c for c in chunks if c.get("record_type") == "block"]
    section_pages = _section_pages(blocks)
    targets = derive_targets(catalog, taxonomy, priorities=priorities)
    fields = {
        t.field_id: _audit_field(t, blocks, chunks, section_pages)
        for t in targets
    }
    return AuditReport(
        pdf_path=str(pdf_path),
        catalog_version=catalog.version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        section_anchor_coverage=section_pages,
        fields=fields,
    )
```

Implementation note: `via` for the non-fallback case is just
`target.chunk_strategy`, whose Literal type already matches
`"alias_top_k" | "broad_keyword"` — check `LlmExtractionTarget` and add a
`cast` only if mypy complains.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_alias_audit.py -q`
Expected: 7 passed

- [ ] **Step 5: Gate + commit**

```bash
uv run pytest -q && uv run ruff check . && uv run mypy src tests
git add src/financial_report_llm_extractor/structured_sources/alias_audit.py tests/test_alias_audit.py
git commit -m "feat: audit_chunks four-state field audit core (PR-1 task 3)"
```

---

### Task 4: writers — `alias_audit.json` / `.md` / catalog patch

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/alias_audit.py`
- Test: `tests/test_alias_audit.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
import json as _json

from financial_report_llm_extractor.structured_sources.alias_audit import (
    emit_catalog_patch,
    write_alias_audit,
)


def test_write_alias_audit_json_and_md(tmp_path: Path) -> None:
    r = _make()
    write_alias_audit(r, tmp_path)
    data = _json.loads((tmp_path / "alias_audit.json").read_text())
    assert data["schema_version"] == "alias_audit_v1"
    assert data["fields"]["c_paid_for_taxes"]["status"] == "prose_only_hit"
    assert data["summary"]["no_hit"] == 1
    md = (tmp_path / "alias_audit.md").read_text()
    assert "prose_only_hit" in md and "receivables_aging" in md


def test_emit_catalog_patch_lists_suggested_adds(tmp_path: Path) -> None:
    r = _make()
    emit_catalog_patch(r, tmp_path)
    patch = _json.loads((tmp_path / "catalog_patch.json").read_text())
    assert patch == {
        "schema_version": "alias_catalog_patch_v1",
        "note": "review-gated suggestions; apply manually to "
                "field_catalog/turtle_v015_source_mapping_minimal.json",
        "add_pdf_aliases": {
            "receivables_aging": [
                "ageing analysis of the trade receivables"
            ],
        },
    }
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_alias_audit.py -q`
Expected: FAIL — ImportError on `write_alias_audit`

- [ ] **Step 3: Implementation** (append to `alias_audit.py`)

```python
def write_alias_audit(report: AuditReport, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "alias_audit_v1",
        "pdf_path": report.pdf_path,
        "catalog_version": report.catalog_version,
        "generated_at": report.generated_at,
        "section_anchor_coverage": {
            k: list(v) for k, v in report.section_anchor_coverage.items()
        },
        "fields": {
            fid: {
                "status": r.status,
                "selected_chunks": [
                    {"chunk_id": c.chunk_id, "page": c.page, "via": c.via}
                    for c in r.selected_chunks
                ],
                "hits": [
                    {"alias": h.alias, "kind": h.kind, "page": h.page,
                     "count": h.count,
                     "in_statement_section": h.in_statement_section,
                     "matched_text": h.matched_text}
                    for h in r.hits
                ],
                "suggested_aliases": list(r.suggested_aliases),
            }
            for fid, r in sorted(report.fields.items())
        },
        "summary": report.summary,
    }
    (out_dir / "alias_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# PDF Alias Audit", "",
        f"- PDF: `{report.pdf_path}`",
        f"- Catalog: {report.catalog_version}",
        f"- Summary: {report.summary}", "",
        "| Field | Status | Hits (alias@page) | Suggested |",
        "|---|---|---|---|",
    ]
    for fid, r in sorted(report.fields.items()):
        hits = "; ".join(f"{h.alias}@p{h.page}[{h.kind}]" for h in r.hits)
        sugg = "; ".join(r.suggested_aliases)
        lines.append(f"| `{fid}` | {r.status} | {hits} | {sugg} |")
    (out_dir / "alias_audit.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8",
    )


def emit_catalog_patch(report: AuditReport, out_dir: Path) -> None:
    adds = {
        fid: list(r.suggested_aliases)
        for fid, r in sorted(report.fields.items())
        if r.suggested_aliases
    }
    payload = {
        "schema_version": "alias_catalog_patch_v1",
        "note": "review-gated suggestions; apply manually to "
                "field_catalog/turtle_v015_source_mapping_minimal.json",
        "add_pdf_aliases": adds,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "catalog_patch.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_alias_audit.py -q`
Expected: 9 passed

- [ ] **Step 5: Gate + commit**

```bash
uv run pytest -q && uv run ruff check . && uv run mypy src tests
git add -u
git commit -m "feat: alias audit JSON/MD writers + catalog patch emitter (PR-1 task 4)"
```

---

### Task 5: CLI subcommand `audit-pdf-aliases`

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py` (parser block after the `pipeline` parser ~line 388; handler placed near the extract-llm handler)
- Test: `tests/test_alias_audit.py`

- [ ] **Step 1: Write the failing test** (append; uses the chunks-reuse path so no PDF/pdftotext needed — mirror how `cli.py:662-674` skips ingest when `<out>/ingest/chunks.jsonl` exists)

```python
def test_cli_audit_pdf_aliases_reuses_existing_chunks(tmp_path: Path) -> None:
    from financial_report_llm_extractor.cli import main

    out = tmp_path / "audit"
    ingest = out / "ingest"
    ingest.mkdir(parents=True)
    with (ingest / "chunks.jsonl").open("w") as f:
        for c in _CHUNKS:
            f.write(_json.dumps(c) + "\n")

    rc = main([
        "audit-pdf-aliases",
        "--pdf", "does-not-exist.pdf",  # unused: chunks.jsonl present
        "--out", str(out),
        "--priorities", "P0,P1,P2,P3,P4",
    ])
    assert rc == 0
    assert (out / "alias_audit.json").exists()
    assert (out / "alias_audit.md").exists()
    # default real catalog: revenue must be a key in the output
    data = _json.loads((out / "alias_audit.json").read_text())
    assert "revenue" in data["fields"]


def test_cli_audit_emits_catalog_patch_when_flagged(tmp_path: Path) -> None:
    from financial_report_llm_extractor.cli import main

    out = tmp_path / "audit2"
    ingest = out / "ingest"
    ingest.mkdir(parents=True)
    with (ingest / "chunks.jsonl").open("w") as f:
        for c in _CHUNKS:
            f.write(_json.dumps(c) + "\n")

    rc = main([
        "audit-pdf-aliases", "--pdf", "x.pdf", "--out", str(out),
        "--emit-catalog-patch",
    ])
    assert rc == 0
    assert (out / "catalog_patch.json").exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_alias_audit.py -q -k cli_audit`
Expected: FAIL — argparse error `invalid choice: 'audit-pdf-aliases'` (surfaces as SystemExit)

- [ ] **Step 3: Implementation**

In `build_parser()` after the `pipeline` parser block:

```python
    audit_parser = subparsers.add_parser(
        "audit-pdf-aliases",
        help="Zero-LLM pre-flight: audit catalog pdf_aliases against a PDF.",
    )
    audit_parser.add_argument("--pdf", type=Path, required=True)
    audit_parser.add_argument(
        "--catalog", type=Path,
        default=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
    )
    audit_parser.add_argument(
        "--taxonomy", type=Path,
        default=Path("field_catalog/turtle_v015_field_taxonomy.json"),
    )
    audit_parser.add_argument("--priorities", default="P0,P1,P2,P3,P4")
    audit_parser.add_argument("--emit-catalog-patch", action="store_true")
    audit_parser.add_argument("--out", type=Path, required=True)
```

In `main()` dispatch (alongside the other `if args.command == ...` blocks):

```python
    if args.command == "audit-pdf-aliases":
        from financial_report_llm_extractor.structured_sources.alias_audit import (
            audit_chunks,
            emit_catalog_patch,
            write_alias_audit,
        )

        priorities = tuple(
            p.strip() for p in args.priorities.split(",") if p.strip()
        )
        ingest_dir = args.out / "ingest"
        chunks_path = ingest_dir / "chunks.jsonl"
        if not chunks_path.exists():
            try:
                ingest_dir.mkdir(parents=True, exist_ok=True)
                ingest_result = ingest_pdf(args.pdf, ingest_dir)
            except RuntimeError as exc:  # pdftotext missing / parse failure
                print(f"error: {exc}", file=sys.stderr)
                return 2
            build_chunk_store(
                ingest_result.pages_path,
                ingest_result.metadata_path,
                chunks_path=chunks_path,
            )
        chunks = load_chunks_jsonl(chunks_path)
        catalog = load_source_mapping_catalog(
            args.catalog, priorities=priorities
        )
        taxonomy = load_field_taxonomy(args.taxonomy)
        report = audit_chunks(
            chunks=chunks, catalog=catalog, taxonomy=taxonomy,
            priorities=priorities, pdf_path=args.pdf,
        )
        write_alias_audit(report, args.out)
        if args.emit_catalog_patch:
            emit_catalog_patch(report, args.out)
        print(json.dumps(
            {"out": str(args.out), "summary": report.summary},
            ensure_ascii=False, indent=2,
        ))
        return 0
```

Reuse the imports already present at the top of `cli.py` (`ingest_pdf`,
`build_chunk_store`, `load_chunks_jsonl`, `load_source_mapping_catalog`,
`load_field_taxonomy`, `json`, `sys`) — verify each exists at module top
before adding duplicates.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_alias_audit.py -q`
Expected: 11 passed

- [ ] **Step 5: Gate + commit**

```bash
uv run pytest -q && uv run ruff check . && uv run mypy src tests
git add -u
git commit -m "feat: audit-pdf-aliases CLI subcommand (PR-1 task 5)"
```

---

### Task 6: acceptance mini-fixture (real 00001 FY2025 phrasings)

**Files:**
- Create: `tests/fixtures/pdf_chunks/alias_audit_mini_00001.jsonl`
- Test: `tests/test_alias_audit.py`

Rationale: the existing `tests/fixtures/pdf_chunks/00001_2025_chunks.jsonl`
is truncated — it contains NONE of the motivating phrases ("ageing
analysis", "Tax paid", "treasury shares"; verified by grep). Build a
purpose-made mini fixture with the REAL phrasings from the FY2025 annual
report (sources: pages.jsonl exploration recorded in
`docs/company-analysis/00001-missing-fields-source-exploration-20260610.md`).

- [ ] **Step 1: Create the fixture file** (one JSON object per line)

```json
{"block_id": "p0134_b0001", "chunk_id": "p0134_b0001", "page": "134", "record_type": "block", "text": "Consolidated income statement. Revenue 280,036 Other income and gains 8 976 Staff costs (43,688)"}
{"block_id": "p0141_b0001", "chunk_id": "p0141_b0001", "page": "141", "record_type": "block", "text": "Consolidated statement of cash flows. Operating profit before working capital changes (714) Tax paid (5,571) Net cash from operating activities"}
{"block_id": "p0056_b0001", "chunk_id": "p0056_b0001", "page": "56", "record_type": "block", "text": "lower interest paid, partly offset by higher taxes paid. The Group's capital expenditures"}
{"block_id": "p0229_b0001", "chunk_id": "p0229_b0001", "page": "229", "record_type": "block", "text": "The ageing analysis of the trade receivables, presented based on the invoice date, is as follows"}
{"block_id": "p0059_b0001", "chunk_id": "p0059_b0001", "page": "59", "record_type": "block", "text": "assets of the Group totalling HK$1,571 million were pledged as security for bank loans"}
{"block_id": "p0076_b0001", "chunk_id": "p0076_b0001", "page": "76", "record_type": "block", "text": "as at 31 December 2025, the Company did not hold any treasury shares"}
{"block_id": "p0269_b0001", "chunk_id": "p0269_b0001", "page": "269", "record_type": "block", "text": "39 Related parties transactions Except as disclosed elsewhere in these financial statements"}
{"block_id": "p0007_b0001", "chunk_id": "p0007_b0001", "page": "7", "record_type": "block", "text": "year ended 31 December 2025 represents one-time non-cash loss arising from the UK merger of HK$10,465 million"}
```

- [ ] **Step 2: Write the acceptance test** (append to `tests/test_alias_audit.py`)

```python
_REPO_ROOT = Path(__file__).resolve().parents[1]
_MINI_FIXTURE = (
    _REPO_ROOT / "tests/fixtures/pdf_chunks/alias_audit_mini_00001.jsonl"
)


def test_acceptance_00001_known_states_with_real_catalog() -> None:
    """Spec PR-1 acceptance: real catalog + real FY2025 phrasings must
    reproduce the four documented failure classes."""
    from financial_report_llm_extractor.field_metadata import (
        load_field_taxonomy,
    )
    from financial_report_llm_extractor.structured_sources.catalog import (
        load_source_mapping_catalog,
    )
    from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
        load_chunks_jsonl,
    )

    chunks = load_chunks_jsonl(_MINI_FIXTURE)
    catalog = load_source_mapping_catalog(
        _REPO_ROOT / "field_catalog/turtle_v015_source_mapping_minimal.json",
        priorities=("P0", "P1", "P2", "P3", "P4"),
    )
    taxonomy = load_field_taxonomy(
        _REPO_ROOT / "field_catalog/turtle_v015_field_taxonomy.json",
    )
    r = audit_chunks(
        chunks=chunks, catalog=catalog, taxonomy=taxonomy,
        priorities=("P0", "P1", "P2", "P3", "P4"),
        pdf_path=Path("00001_2025_mini.pdf"),
    )

    # class ② wrong-page: 'taxes paid' hits p56 prose, statement line
    # 'Tax paid' p141 is NOT an exact alias match
    assert r.fields["c_paid_for_taxes"].status == "prose_only_hit"
    # class ① alias gap healed by normalization, suggestion recovered
    aging = r.fields["receivables_aging"]
    assert aging.status == "normalized_only_hit"
    assert any(
        "ageing analysis of the trade receivables" in s
        for s in aging.suggested_aliases
    )
    related = r.fields["related_party_receivables_payables"]
    assert related.status == "normalized_only_hit"
    # class ⑤ genuinely absent
    assert r.fields["rd_exp"].status == "no_hit"
    assert r.fields["time_deposits_or_wealth_products"].status == "no_hit"
    # healthy field stays exact
    assert r.fields["revenue"].status == "exact_hit"
```

- [ ] **Step 3: Run the test**

Run: `uv run pytest tests/test_alias_audit.py::test_acceptance_00001_known_states_with_real_catalog -v`
Expected: PASS. If a status assertion fails, the audit logic — not the
fixture — is wrong relative to the documented evidence
(`docs/company-analysis/00001-missing-fields-source-exploration-20260610.md`
§1); debug there before touching assertions. One legitimate exception:
`restricted_cash` has alias "pledged deposits" and the fixture text says
"pledged as security" with no shared full-token window — it is expected
`no_hit` here (synonym, not normalization-reachable); do NOT assert it
normalized.

- [ ] **Step 4: Gate + commit**

```bash
uv run pytest -q && uv run ruff check . && uv run mypy src tests
git add tests/fixtures/pdf_chunks/alias_audit_mini_00001.jsonl tests/test_alias_audit.py
git commit -m "test: 00001 real-phrasing acceptance fixture for alias audit (PR-1 task 6)"
```

---

### Task 7: live smoke + wrap-up

- [ ] **Step 1: Live smoke against the real 00001 FY2025 PDF** (operator machine has pdftotext + the PDF; this is a smoke, not a test)

```bash
uv run financial-report-llm-extractor audit-pdf-aliases \
  --pdf downloads/hk_stocks/00001/annual/2025_annual_en.pdf \
  --emit-catalog-patch \
  --out tmp/runs/00001_2025_alias_audit
```

Expected stdout: JSON with `summary`. Cross-check `alias_audit.md` against
the exploration doc: `receivables_aging`/`related_party_receivables_payables`
→ normalized_only_hit; `c_paid_for_taxes` → prose_only_hit; `rd_exp`,
`receiv_tax_refund`, `capitalized_rd`, `time_deposits_or_wealth_products` →
no_hit. Differences from the doc are findings to report, not necessarily
bugs (the doc searched pages.jsonl; the audit scans block records).

- [ ] **Step 2: Full gate**

```bash
uv run pytest -v && uv run ruff check . && uv run mypy src tests
```

Expected: all pass (the 2 pre-existing mypy errors in
`tests/test_subscription_token_threading.py` are known legacy — if still
present they predate this plan; do not fix here).

- [ ] **Step 3: Final commit if anything uncommitted**

```bash
git status --short
git add -u && git commit -m "chore: alias audit PR-1 wrap-up" || true
```

---

## Self-review notes (already applied)

- Spec coverage: component 1 rules 1-6 → Task 1; AliasMatch/match_alias →
  Task 2; selection-simulation + block-only + four states + anchor
  coverage → Task 3; writers + patch → Task 4; CLI + exit 2 + chunk reuse
  → Task 5; acceptance (00001 documented states) → Task 6; live smoke →
  Task 7. PR-3/PR-2 intentionally out of scope (separate plans).
- The spec's "00001 审计复现：5 normalized_only" applies to the FULL PDF
  (Task 7 smoke); the deterministic Task 6 fixture covers 2 normalized_only
  + 1 prose_only + 2 no_hit + 1 exact — the subset representable without
  the full 350-page text.
- Type consistency: `chunk_strategy` Literal on `LlmExtractionTarget` is
  reused as `via`; `select_statement_section_chunks` signature
  `(chunks, target, *, top_k=8)` confirmed in llm_extraction_runner.
