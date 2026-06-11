# Alias Lifecycle PR-3 (normalization into retrieval, gated) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the PR-1 normalization matcher into live retrieval (`select_chunks` alias_top_k path) behind a catalog flag, with a section-aware sort key and a three-part rollout gate (8-cohort selection diff → paid revalidation of diffed fields only → flag flip).

**Architecture:** A catalog-level boolean `alias_normalization` flows `SourceMappingCatalog` → `derive_targets` → `LlmExtractionTarget` → `select_chunks` (single consumption point). When on, alias_top_k scoring becomes the spec's `(exact_score, in_statement_section, normalized_score)` key; normalized scores come from `match_alias` with a per-run `PreparedText` cache, section membership from anchor pages computed once per run in `extract_for_chunks`. Flag ships **false**; flipping to true happens only after the Task 6 gate passes.

**Tech Stack:** Python 3.11 stdlib, pytest, mypy strict, ruff 88. Branch: `feat/alias-lifecycle-pr3` stacked on `feat/alias-lifecycle-pr1`.

**Spec:** `docs/superpowers/specs/2026-06-10-alias-lifecycle-design.md` rev 2, section "PR-3". Out of scope: broad_keyword path (explicitly unchanged), the match ledger (PR-2).

**Verification gate per commit:** `uv run pytest -q && uv run ruff check . && uv run mypy src tests` (must be FULLY clean — branch has zero mypy debt).

---

## File structure

| File | Change |
|---|---|
| `structured_sources/catalog.py` | `SourceMappingCatalog.alias_normalization: bool = False` + loader reads top-level key |
| `structured_sources/llm_extraction_runner.py` | `LlmExtractionTarget.alias_normalization`; `derive_targets` stamps it; `statement_section_pages()` (moved from alias_audit); `select_chunks` new optional `section_pages`/`prepared_cache` params + flag-gated scoring; `extract_for_chunks` computes section pages + cache once when flag on |
| `structured_sources/alias_audit.py` | `_section_pages` replaced by import of `statement_section_pages`; `audit_chunks` gains `alias_normalization_override` |
| `cli.py` | `audit-pdf-aliases --alias-normalization {catalog,on,off}` |
| `tests/test_catalog_consistency.py` | N0 assertion: real catalog flag == rollout constant (False until gate) |
| `tests/test_llm_extraction_runner.py` | flag-behavior tests (off-identical, normalized pickup, sort key, collision, absence_means_zero interplay) |
| `tests/test_alias_audit.py` | override-param test |
| `field_catalog/turtle_v015_source_mapping_minimal.json` | Task 6 ONLY (gate-pass): add `"alias_normalization": true` |

---

### Task 1: catalog flag plumbing

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/catalog.py` (SourceMappingCatalog ~line 200; loader ~line 219+)
- Modify: `src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py` (LlmExtractionTarget ~line 46; derive_targets ~line 59)
- Test: `tests/test_source_mapping_catalog.py`, `tests/test_llm_extraction_runner.py`, `tests/test_catalog_consistency.py`

- [ ] **Step 1: Failing tests**

Append to `tests/test_source_mapping_catalog.py` (reuse its existing load helpers/fixture-writing style — read the file first and follow its pattern for constructing a temp catalog JSON):

```python
def test_alias_normalization_flag_defaults_false_and_loads(tmp_path: Path) -> None:
    # minimal catalog without the key -> False
    base = {
        "catalog_id": "t", "version": "1",
        "priorities": [{"priority": "P0", "fields": ["revenue"]}],
        "source_mappings": {
            "revenue": {
                "value_type": "money", "statement_type": "income_statement",
                "currency_requirement": "required",
                "unit_requirement": "required",
                "source_aliases": {"yahoo": ["Total Revenue"]},
                "pdf_aliases": ["revenue"],
            }
        },
    }
    p = tmp_path / "cat.json"
    p.write_text(json.dumps(base))
    cat = load_source_mapping_catalog(p, priorities=("P0",))
    assert cat.alias_normalization is False

    base["alias_normalization"] = True
    p.write_text(json.dumps(base))
    cat2 = load_source_mapping_catalog(p, priorities=("P0",))
    assert cat2.alias_normalization is True
```

(Adapt the minimal-catalog dict to whatever shape the file's existing tests use — if a helper exists for building catalog JSON, reuse it; the assertion pair is the contract.)

Append to `tests/test_llm_extraction_runner.py` (helpers `_entry/_taxonomy/_catalog` exist; `_catalog` builds `SourceMappingCatalog` directly — extend the helper call with the new field):

```python
def test_derive_targets_stamps_alias_normalization() -> None:
    catalog = _catalog([_entry("revenue", pdf_aliases=("a", "b", "c"))])
    taxonomy = _taxonomy([_tax_entry("revenue")])

    off = derive_targets(catalog, taxonomy, priorities=("P0",))[0]
    assert off.alias_normalization is False

    from dataclasses import replace
    on_catalog = replace(catalog, alias_normalization=True)
    on = derive_targets(on_catalog, taxonomy, priorities=("P0",))[0]
    assert on.alias_normalization is True
```

Append to `tests/test_catalog_consistency.py` (follow its loading style):

```python
def test_alias_normalization_rollout_state() -> None:
    """N0 gate: the live catalog's alias_normalization flag must match the
    gated rollout state. Flip BOTH together after the PR-3 cohort gate
    (selection diff + paid revalidation) passes."""
    ALIAS_NORMALIZATION_ROLLED_OUT = False
    catalog = load_source_mapping_catalog(
        REPO_ROOT / "field_catalog/turtle_v015_source_mapping_minimal.json",
        priorities=("P0", "P1", "P2", "P3", "P4"),
    )
    assert catalog.alias_normalization is ALIAS_NORMALIZATION_ROLLED_OUT
```

(Reuse the file's existing repo-root/path constants; if it loads the catalog already, piggyback.)

- [ ] **Step 2: Run — expect FAIL** (`AttributeError`/`TypeError: unexpected keyword`)

`uv run pytest tests/test_source_mapping_catalog.py tests/test_llm_extraction_runner.py tests/test_catalog_consistency.py -q`

- [ ] **Step 3: Implement**

`catalog.py` — `SourceMappingCatalog` gains a field (keep frozen):

```python
@dataclass(frozen=True)
class SourceMappingCatalog:
    catalog_id: str
    version: str
    entries: dict[str, SourceMappingEntry]
    alias_normalization: bool = False
```

In `load_source_mapping_catalog`, where the catalog object is constructed, add:

```python
        alias_normalization=bool(raw.get("alias_normalization", False)),
```

`llm_extraction_runner.py` — `LlmExtractionTarget` gains:

```python
    alias_normalization: bool = False
```

`derive_targets` stamps it in the `LlmExtractionTarget(...)` construction:

```python
            alias_normalization=catalog.alias_normalization,
```

- [ ] **Step 4: Run tests — expect PASS**, then full gate

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "feat: alias_normalization catalog flag plumbing (PR-3 task 1)"
```

---

### Task 2: move section-pages helper to the runner (refactor, no behavior change)

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py` (add `statement_section_pages` next to `_STATEMENT_SECTION_ANCHORS`)
- Modify: `src/financial_report_llm_extractor/structured_sources/alias_audit.py` (delete `_section_pages`, import the runner version; also move `_page_of` if it is only used by the helper — keep `alias_audit._page_of` since SelectedChunk uses it; the runner gets its own copy named `_chunk_page`)
- Test: `tests/test_llm_extraction_runner.py`

Rationale: `extract_for_chunks` (Task 3) needs section pages; the dependency direction must be runner ← audit, never runner → audit.

- [ ] **Step 1: Failing test** (append to `tests/test_llm_extraction_runner.py`):

```python
def test_statement_section_pages_maps_anchor_pages() -> None:
    from financial_report_llm_extractor.structured_sources.llm_extraction_runner import (
        statement_section_pages,
    )
    chunks = [
        _chunk("a", 141, "Consolidated statement of cash flows ..."),
        _chunk("b", 134, "Consolidated income statement. Revenue"),
        _chunk("c", 10, "no anchors here"),
    ]
    pages = statement_section_pages(chunks)
    assert 141 in pages["cash_flow"]
    assert 134 in pages["income_statement"]
    assert pages["balance_sheet"] == ()
```

- [ ] **Step 2: Run — expect ImportError FAIL**

- [ ] **Step 3: Implement.** In `llm_extraction_runner.py`, directly after `_STATEMENT_SECTION_ANCHORS`:

```python
def _chunk_page(chunk: dict[str, object]) -> int | None:
    try:
        return int(str(chunk.get("page")))
    except (TypeError, ValueError):
        return None


def statement_section_pages(
    chunks: list[dict[str, object]],
) -> dict[str, tuple[int, ...]]:
    """Pages whose text matches a statement-type anchor phrase.

    Operates on whatever records it is given; callers that need page
    precision should pass block records only (chunks.jsonl stores each
    text three ways).
    """
    out: dict[str, set[int]] = {k: set() for k in _STATEMENT_SECTION_ANCHORS}
    for chunk in chunks:
        text = " ".join(str(chunk.get("text", "") or "").lower().split())
        page = _chunk_page(chunk)
        if page is None:
            continue
        for stype, anchors in _STATEMENT_SECTION_ANCHORS.items():
            if any(" ".join(a.split()) in text for a in anchors):
                out[stype].add(page)
    return {k: tuple(sorted(v)) for k, v in out.items()}
```

In `alias_audit.py`: delete the now-duplicated `_section_pages`, import `statement_section_pages` from the runner (extend the existing runner import block), and replace the one call site `_section_pages(blocks)` → `statement_section_pages(blocks)`. Keep `alias_audit._page_of` (used by SelectedChunk/AliasHit serialization).

- [ ] **Step 4: Run full audit + runner test files; then full gate.** All existing alias_audit tests must pass unchanged (pure refactor).

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "refactor: statement_section_pages lives in the runner (PR-3 task 2)"
```

---

### Task 3: flag-gated section-aware scoring in select_chunks

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/llm_extraction_runner.py` (`select_chunks` + `extract_for_chunks`)
- Test: `tests/test_llm_extraction_runner.py`

- [ ] **Step 1: Failing tests** (append; `_chunk` helper exists — it takes optional `statement_type` but pages are positional):

```python
def _norm_target(aliases: tuple[str, ...],
                 statement_type: str = "balance_sheet",
                 alias_normalization: bool = True) -> LlmExtractionTarget:
    return LlmExtractionTarget(
        field_id="f", field_description="d",
        statement_type=cast(StatementType, statement_type),
        value_type="money", aliases=aliases,
        chunk_strategy="alias_top_k",
        alias_normalization=alias_normalization,
    )


def test_select_chunks_flag_off_ignores_normalized_matches() -> None:
    target = _norm_target(
        ("ageing analysis of trade receivables", "x1", "x2"),
        alias_normalization=False,
    )
    chunks = [_chunk("c1", 229,
                     "The ageing analysis of the trade receivables, presented")]
    assert select_chunks(chunks, target) == []


def test_select_chunks_flag_on_picks_up_normalized_only_chunk() -> None:
    target = _norm_target(("ageing analysis of trade receivables", "x1", "x2"))
    chunks = [_chunk("c1", 229,
                     "The ageing analysis of the trade receivables, presented")]
    selected = select_chunks(chunks, target)
    assert [c["chunk_id"] for c in selected] == ["c1"]


def test_select_chunks_exact_dominates_normalized() -> None:
    target = _norm_target(("related party transactions", "x1", "x2"))
    chunks = [
        _chunk("norm", 269, "Related parties transactions Except"),
        _chunk("exact", 87, "related party transactions of the Group"),
    ]
    selected = select_chunks(chunks, target)
    assert [c["chunk_id"] for c in selected][0] == "exact"


def test_select_chunks_in_section_breaks_exact_ties() -> None:
    target = _norm_target(("tax paid", "x1", "x2"),
                          statement_type="cash_flow")
    chunks = [
        _chunk("prose", 56, "higher tax paid this year"),
        _chunk("stmt", 141, "tax paid (5,571)"),
    ]
    section_pages = {"cash_flow": (141,)}
    selected = select_chunks(chunks, target, section_pages=section_pages)
    assert [c["chunk_id"] for c in selected][0] == "stmt"


def test_select_chunks_inventories_collision_ranked_below_in_section() -> None:
    # Known rule-5 collision: alias 'inventories' normalized-matches
    # 'change in inventories' cash-flow text. Section-aware key keeps the
    # genuine balance-sheet chunk first.
    target = _norm_target(("inventories", "x1", "x2"),
                          statement_type="balance_sheet")
    chunks = [
        _chunk("bs", 136, "Inventories 26,690"),
        _chunk("cf", 141, "Decrease in inventories (685)"),
    ]
    section_pages = {"balance_sheet": (136,), "cash_flow": (141,)}
    selected = select_chunks(chunks, target, section_pages=section_pages)
    assert [c["chunk_id"] for c in selected][0] == "bs"


def test_extract_for_chunks_normalized_preempts_section_fallback(
    tmp_path: Path,
) -> None:
    """absence_means_zero interplay (spec gate fixture): when normalization
    finds candidate chunks, the section fallback is preempted — the LLM
    sees real candidates instead. Documented, deliberate."""
    catalog_entries = [
        _entry(
            "repurchase_of_stock",
            pdf_aliases=("repurchase of capital stock", "share buyback",
                          "stock repurchase"),
            statement_type="cash_flow",
            absence_means_zero=True,
        ),
    ]
    catalog = SourceMappingCatalog(
        catalog_id="test", version="1",
        entries={e.field_id: e for e in catalog_entries},
        alias_normalization=True,
    )
    taxonomy = _taxonomy([
        _tax_entry("repurchase_of_stock", statement_type="cash_flow"),
    ])
    # No exact alias; 'share buybacks' normalized-matches 'share buyback'.
    chunks = [
        _chunk("c1", 112, "Codes on Takeovers and Mergers and Share Buybacks"),
        _chunk("c2", 141, "Consolidated statement of cash flows financing"),
    ]
    captured: dict[str, object] = {}

    class _CapturingClient:
        def complete_json(
            self, *, system_prompt: str, user_payload: dict[str, object],
        ) -> dict[str, object]:
            captured.update(user_payload)
            return {"field_id": "repurchase_of_stock", "found": False}

    extract_for_chunks(
        chunks=chunks, catalog=catalog, taxonomy=taxonomy,
        client=_CapturingClient(), company_id="T",
        pdf_path=Path("t.pdf"), out_dir=tmp_path,
    )
    sent_ids = [c.get("chunk_id") for c in
                cast(list[dict[str, object]], captured["chunks"])]
    assert sent_ids == ["c1"]  # normalized candidate, NOT the c2 fallback
```

Check the actual prompt payload key for chunks (`build_field_extraction_prompt` puts chunks under a key — read `llm_field_extraction.py` and fix the `captured["chunks"]` access to the real payload path, e.g. `captured["evidence"]["chunks"]` — whatever the existing capturing tests in this file use; copy their access pattern).

- [ ] **Step 2: Run — expect FAIL** (unexpected `section_pages` kwarg; flag-on behaviors missing)

- [ ] **Step 3: Implement.**

`select_chunks` — replace the alias_top_k branch and extend the signature:

```python
def select_chunks(
    chunks: list[dict[str, object]],
    target: LlmExtractionTarget,
    *,
    top_k_standard: int = 8,
    broad_limit: int = 30,
    section_pages: Mapping[str, tuple[int, ...]] | None = None,
    prepared_cache: dict[str, PreparedText] | None = None,
) -> list[dict[str, object]]:
    """Select PDF chunks for an extraction target.

    alias_top_k: count alias occurrences (case-insensitive), keep top-k.
    With target.alias_normalization on, ranking becomes the spec PR-3 key
    (exact_score, in_statement_section, normalized_score) — normalized
    token-window matches let near-miss phrasings enter the candidate set,
    and section membership demotes prose pages. Flag off → byte-identical
    to the historical exact-only behavior.
    broad_keyword: unchanged (normalization out of scope per spec).
    """
    if target.chunk_strategy == "alias_top_k":
        aliases_norm = [_normalize_whitespace(a.lower()) for a in target.aliases]
        use_norm = target.alias_normalization
        type_pages: tuple[int, ...] = ()
        if use_norm and section_pages is not None:
            type_pages = section_pages.get(target.statement_type, ())
        ranked: list[tuple[tuple[int, int, int], dict[str, object]]] = []
        for chunk in chunks:
            text = str(chunk.get("text", "") or "")
            text_norm = _normalize_whitespace(text.lower())
            exact = sum(text_norm.count(a) for a in aliases_norm)
            norm_score = 0
            if use_norm:
                cid = str(chunk.get("chunk_id") or chunk.get("block_id") or "")
                prepared: PreparedText | None = None
                if prepared_cache is not None:
                    prepared = prepared_cache.get(cid)
                    if prepared is None:
                        prepared = prepare_text(text)
                        prepared_cache[cid] = prepared
                else:
                    prepared = prepare_text(text)
                for alias in target.aliases:
                    m = match_alias(alias, text, prepared=prepared)
                    if m is not None and m.kind == "normalized":
                        norm_score += m.count
            if exact > 0 or norm_score > 0:
                in_sec = 1 if (
                    use_norm and _chunk_page(chunk) in type_pages
                ) else 0
                ranked.append(((exact, in_sec, norm_score), chunk))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in ranked[:top_k_standard]]
    ...  # broad_keyword branch unchanged
```

Imports at module top: `from collections.abc import Mapping`, and from `alias_matching`: `PreparedText, match_alias, prepare_text`.

Flag-off identity argument (state in code comment): when `use_norm` is False, `norm_score` stays 0 and `in_sec` stays 0 for every chunk, so the key reduces to `(exact, 0, 0)` — same ordering as the historical `-score` sort, and the `exact > 0` filter is unchanged. Python's `sort` is stable, so equal-exact ties keep input order exactly as before.

`extract_for_chunks` — before the target loop:

```python
    section_pages: dict[str, tuple[int, ...]] | None = None
    prepared_cache: dict[str, PreparedText] | None = None
    if catalog.alias_normalization:
        block_records = [
            c for c in chunks if c.get("record_type") == "block"
        ]
        section_pages = statement_section_pages(block_records or chunks)
        prepared_cache = {}
```

and the call site becomes:

```python
        selected = select_chunks(
            chunks, target,
            section_pages=section_pages,
            prepared_cache=prepared_cache,
        )
```

(`block_records or chunks`: synthetic test chunks may lack record_type; fall back to all.)

- [ ] **Step 4: Run new tests + the ENTIRE existing runner/audit test files** (flag-off identity is load-bearing), then full gate.

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "feat: flag-gated section-aware normalized scoring in select_chunks (PR-3 task 3)"
```

---

### Task 4: audit CLI normalization override (gate tooling)

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/alias_audit.py` (`audit_chunks` param)
- Modify: `src/financial_report_llm_extractor/cli.py` (audit parser + handler)
- Test: `tests/test_alias_audit.py`

- [ ] **Step 1: Failing tests** (append to `tests/test_alias_audit.py`):

```python
def test_audit_chunks_normalization_override() -> None:
    catalog = _catalog([
        _entry("receivables_aging",
               pdf_aliases=("ageing analysis of trade receivables", "x", "y"),
               statement_type="notes", value_type="text"),
    ])
    taxonomy = _taxonomy([
        _tax("receivables_aging", statement_type="notes", value_type="text"),
    ])
    chunks = [_block("c3", 229,
                     "The ageing analysis of the trade receivables, presented")]
    off = audit_chunks(chunks=chunks, catalog=catalog, taxonomy=taxonomy,
                       priorities=("P0",), pdf_path=Path("f.pdf"))
    on = audit_chunks(chunks=chunks, catalog=catalog, taxonomy=taxonomy,
                      priorities=("P0",), pdf_path=Path("f.pdf"),
                      alias_normalization_override=True)
    # selection simulation differs: off -> no selected chunks (exact miss),
    # on -> the normalized chunk is selected
    assert off.fields["receivables_aging"].selected_chunks == ()
    assert [c.chunk_id for c in
            on.fields["receivables_aging"].selected_chunks] == ["c3"]
```

- [ ] **Step 2: Run — expect FAIL** (unexpected kwarg)

- [ ] **Step 3: Implement.** `audit_chunks` gains `alias_normalization_override: bool | None = None`; before deriving targets:

```python
    if alias_normalization_override is not None:
        from dataclasses import replace
        catalog = replace(
            catalog, alias_normalization=alias_normalization_override,
        )
```

`audit_chunks` must also pass `section_pages` to its `select_chunks` calls so the simulation matches production: in `_audit_field`, the existing `select_chunks(all_chunks, target)` call becomes `select_chunks(all_chunks, target, section_pages=section_pages)` (the dict is already computed in `audit_chunks`; thread it through `_audit_field`'s existing `section_pages` parameter).

CLI: `audit_parser.add_argument("--alias-normalization", choices=["catalog", "on", "off"], default="catalog")`; handler maps `{"catalog": None, "on": True, "off": False}` into the new kwarg.

- [ ] **Step 4: Run audit tests + full gate.**

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "feat: audit normalization override for gate diffing (PR-3 task 4)"
```

---

### Task 5: cohort selection-diff harness run (operator step, no code)

Controller (not subagent) runs over the 8-cohort chunks already on disk under `tmp/runs/*/ingest/chunks.jsonl` (00001/01113/01810/02498/06862/09987/600519/300750 — postmerge + g3/g4c run dirs hold them; for any company missing chunks, ingest from `downloads/` first):

```bash
for dir in <cohort chunk dirs>; do
  financial-report-llm-extractor audit-pdf-aliases --pdf <pdf> \
    --out tmp/runs/pr3_gate/<co>_off --alias-normalization off
  financial-report-llm-extractor audit-pdf-aliases --pdf <pdf> \
    --out tmp/runs/pr3_gate/<co>_on  --alias-normalization on
done
# diff selected_chunks per field between off/on audits (python one-liner)
```

Deliverable: per-company list of fields whose `selected_chunks` set changed. Expect: changes concentrated in normalized_only/prose_only fields; any P0 provider-clean field changing selection is a red flag to investigate before proceeding.

- [ ] Diff report produced and reviewed
- [ ] Paid revalidation (DeepSeek) for **diffed fields only** on at least 00001 + one CN company: run `extract-llm` with `--fields <diffed>` flag-on vs flag-off out-dirs; compare `fields_present` + values. Acceptance: no lost present-fields, no new shallow-FP values (spot-check reasoning/pages).

### Task 6: flag flip (only if Task 5 green)

- [ ] Edit `field_catalog/turtle_v015_source_mapping_minimal.json`: add top-level `"alias_normalization": true`
- [ ] Flip `ALIAS_NORMALIZATION_ROLLED_OUT = True` in `tests/test_catalog_consistency.py`
- [ ] Full gate; commit `feat: enable alias_normalization (PR-3 gate passed)` with the diff/revalidation summary in the commit body. If Task 5 is NOT green, ship Tasks 1-4 with the flag false and document findings instead.

---

## Self-review notes

- Spec coverage: sort key `(exact, in_section, normalized)` → Task 3; broad_keyword untouched → Task 3 scope note; catalog flag + single consumption + N0 assertion → Task 1; absence_means_zero interplay fixture → Task 3 test; inventories collision fixture → Task 3 test; 8-cohort selection diff + paid revalidation for diffed fields → Task 5; flag default-off until gate → Tasks 1/6.
- Flag-off identity is enforced by keeping the historical code path semantics (key reduces to exact-only; stable sort preserves tie order) and by the full pre-existing test suite running unchanged.
- Type consistency: `PreparedText`/`match_alias`/`prepare_text` are PR-1 exports of `alias_matching`; `statement_section_pages`/`_chunk_page` introduced in Task 2 and consumed in Task 3; `alias_normalization` name identical across catalog/target/JSON/N0.
