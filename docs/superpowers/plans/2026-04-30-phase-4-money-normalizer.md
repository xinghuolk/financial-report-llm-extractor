# Phase 4 Money Normalizer Implementation Plan

> **For agentic workers:** Phase 4 has started with deterministic money normalization. Continue from the follow-up items before using it inside extraction orchestration.

**Goal:** Normalize monetary values deterministically into the existing `MoneyAmount` contract.

**Architecture:** Keep money parsing and unit resolution in `src/financial_report_llm_extractor/money.py`. It should remain independent from retrieval and LLM behavior. Downstream extraction can call it after selecting a raw value and unit context.

**Tech Stack:** Python 3.11 standard library, `Decimal`, pytest.

---

### Task 1: Numeric Value Parser

**Files:**
- Create: `src/financial_report_llm_extractor/money.py`
- Create: `tests/test_money.py`

- [x] **Step 1: Write failing tests**

Cover commas, decimals, leading minus signs, parentheses negatives, and dash-like missing values.

- [x] **Step 2: Implement minimal code**

Add `MoneyNormalizationError` and `parse_numeric_value()`.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_money.py -v`

Expected: parser returns `Decimal` values and rejects missing dash values.

### Task 2: Currency And Unit Resolver

**Files:**
- Modify: `src/financial_report_llm_extractor/money.py`
- Modify: `tests/test_money.py`

- [x] **Step 1: Write failing tests**

Cover CNY/HKD/USD with common Chinese and English scale units.

- [x] **Step 2: Implement minimal code**

Add `resolve_money_unit()` with deterministic currency and multiplier detection.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_money.py -v`

Expected: common units such as `人民币百万元`, `HKD million`, and `US$ thousand` normalize correctly.

### Task 3: MoneyAmount Normalization

**Files:**
- Modify: `src/financial_report_llm_extractor/money.py`
- Modify: `tests/test_money.py`

- [x] **Step 1: Write failing tests**

Cover `normalize_money()` returning a valid `MoneyAmount`, including normalized value and normalized unit.

- [x] **Step 2: Implement minimal code**

Add `normalize_money()` using the existing `MoneyAmount.validate()` invariant.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_money.py -v`

Expected: normalized values equal `value * unit_multiplier`.

### Follow-Up Work

- [ ] Add more scale variants: yuan, RMB yuan, HK$'000, RMB'000, 万元, 亿元.
- [ ] Add structured ambiguity errors for multi-currency unit contexts.
- [ ] Add row/header/report metadata precedence for resolving currency and unit.
- [ ] Add derived value engine with evidence propagation.
- [ ] Integrate normalization into the fake extraction pipeline after retrieval.

