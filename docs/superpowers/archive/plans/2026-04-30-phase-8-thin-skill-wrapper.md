# Phase 8 Thin Skill Wrapper Implementation Plan

> **For agentic workers:** Phase 8 has started with a repo-contained optional skill wrapper. It is not installed automatically; copy or install it only when needed.

**Goal:** Make Codex/Claude usage ergonomic without moving business logic into a skill.

**Architecture:** Keep the skill wrapper in `docs/skills/financial-report-extractor/`. It must call the CLI/API and must not parse PDFs, normalize money, validate extraction contracts, or store final facts.

**Tech Stack:** Markdown skill instructions, references, pytest checks.

---

### Task 1: Skill Wrapper Contract

**Files:**
- Create: `docs/skills/financial-report-extractor/SKILL.md`
- Create: `tests/test_skill_wrapper.py`

- [x] **Step 1: Write failing tests**

Cover required frontmatter and CLI commands.

- [x] **Step 2: Implement minimal code**

Add a concise `SKILL.md` with workflow commands for ingest, chunk, retrieve, extract-fake, extract, and evaluate.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_skill_wrapper.py -v`

Expected: skill wrapper exists and calls CLI commands.

### Task 2: Guardrails

**Files:**
- Modify: `docs/skills/financial-report-extractor/SKILL.md`
- Modify: `tests/test_skill_wrapper.py`

- [x] **Step 1: Write failing tests**

Cover that the skill explicitly avoids reimplementing PDF parsing and money normalization.

- [x] **Step 2: Implement minimal code**

Add guardrails stating that the skill must not parse PDFs, normalize money, validate contracts, or store final facts.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_skill_wrapper.py -v`

Expected: guardrails are present.

### Task 3: Review Checklist

**Files:**
- Create: `docs/skills/financial-report-extractor/references/review-checklist.md`
- Modify: `docs/skills/financial-report-extractor/SKILL.md`
- Modify: `tests/test_skill_wrapper.py`

- [x] **Step 1: Write failing tests**

Cover the review checklist link and required evidence fields.

- [x] **Step 2: Implement minimal code**

Add a concise review checklist for extraction outputs.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_skill_wrapper.py -v`

Expected: checklist exists and names `page`, `chunk_id`, `block_id`, and present monetary item checks.

### Follow-Up Work

- [ ] Decide whether to install this repo-contained skill into `$CODEX_HOME/skills`.
- [ ] Add `agents/openai.yaml` only if the skill is meant to be installed as a first-class Codex skill.
- [ ] Keep the wrapper in sync when CLI arguments change.
- [ ] Add example prompts after real Phase 7 evaluation artifacts exist.

