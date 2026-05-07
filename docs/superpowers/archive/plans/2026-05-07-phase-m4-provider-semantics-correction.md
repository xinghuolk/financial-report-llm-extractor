# Phase M4 Provider Raw Semantics Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the HK proof drift by making provider raw field semantics an explicit source-policy contract before any 33-field expansion.

**Architecture:** Add a small provider-semantics layer beside the existing HK Yahoo trust policy, then make source mapping, trust policy reports, and closure tests distinguish trusted raw fields from related context fields. Keep PDF samples as policy proof only; final per-company PDF evidence remains a separate export concern.

**Tech Stack:** Python 3.11 standard library, JSON catalogs, pytest, existing structured source replay fixtures.

---

## File Structure

- Create: `field_catalog/provider_raw_semantics_hk.json`
  - Provider/market/raw-field semantics rules for the HK slice.
- Create: `src/financial_report_llm_extractor/structured_sources/provider_semantics.py`
  - Loader, dataclasses, validation, and query helpers for provider raw semantics rules.
- Create: `tests/test_provider_semantics.py`
  - Unit tests for loader validation, trusted-vs-related field roles, `net_profit`, and `gross_profit`.
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`
  - Split or mirror Yahoo raw fields into trusted/related roles for affected fields.
- Modify: `field_catalog/hk_yahoo_trust_policy.json`
  - Reword classification/proof metadata so samples are provider policy proof, not final PDF evidence.
- Modify: `src/financial_report_llm_extractor/structured_sources/hk_yahoo_trust_policy.py`
  - Add compatibility mapping from old `yahoo_pdf_verified` to provider-semantics proof wording, or consume the new semantics artifact.
- Modify: `src/financial_report_llm_extractor/structured_sources/source_policy.py`
  - Apply trust only when provider semantics says the raw field is allowed as primary.
- Modify: `src/financial_report_llm_extractor/structured_sources/hk_15_field_closure.py`
  - Report clean fields separately from sampled provider-semantics proof buckets.
- Modify: `tests/test_hk_yahoo_trust_policy.py`
  - Add page-text/sample validation expectations or explicit missing-fixture skip.
- Modify: `tests/test_source_mapping_catalog.py`
  - Add catalog consistency tests for trusted vs related fields.
- Modify: `tests/test_provider_baseline_replay.py`
  - Stop treating `net_profit` proof as final PDF evidence; keep raw-field selection assertions.
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
  - Mark Phase M4 as the required next phase before Phase N.
- Modify: `AGENTS.md`
  - Add guardrails for provider semantics proof and PDF sample usage.

## Task 1: Add Provider Semantics Loader

**Files:**

- Create: `tests/test_provider_semantics.py`
- Create: `src/financial_report_llm_extractor/structured_sources/provider_semantics.py`
- Create: `field_catalog/provider_raw_semantics_hk.json`

- [ ] **Step 1: Write failing loader tests**

Add tests:

```python
from pathlib import Path

import pytest

from financial_report_llm_extractor.structured_sources.provider_semantics import (
    load_provider_semantics_catalog,
)


CATALOG = Path("field_catalog/provider_raw_semantics_hk.json")


def test_loads_hk_yahoo_net_profit_semantics() -> None:
    catalog = load_provider_semantics_catalog(CATALOG)

    rule = catalog.require_rule(
        provider="yahoo",
        market="HK",
        turtle_field_id="net_profit",
        raw_field_name="Net Income Common Stockholders",
    )

    assert rule.allowed_as_primary is True
    assert rule.classification == "provider_semantics_sample_verified"
    assert rule.proof_origin == "sampled_pdf_policy_proof"
    assert rule.trusted_currency == "HKD"
    assert rule.trusted_unit == "raw"
    assert rule.trusted_unit_multiplier == 1
    assert "Net Income" in rule.related_only_fields
    assert "Net Income From Continuing Operation Net Minority Interest" in rule.related_only_fields


def test_gross_profit_is_not_primary_without_semantics_proof() -> None:
    catalog = load_provider_semantics_catalog(CATALOG)

    rule = catalog.require_rule(
        provider="yahoo",
        market="HK",
        turtle_field_id="gross_profit",
        raw_field_name="Gross Profit",
    )

    assert rule.allowed_as_primary is False
    assert rule.classification == "provider_semantics_unverified"
    assert rule.required_proof


def test_related_fields_cannot_also_be_primary(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        """
{
  "rules": [
    {
      "provider": "yahoo",
      "market": "HK",
      "raw_field_name": "Net Income Common Stockholders",
      "raw_field_code": null,
      "turtle_field_id": "net_profit",
      "semantic_claim": "profit attributable to ordinary shareholders",
      "classification": "provider_semantics_sample_verified",
      "trusted_currency": "HKD",
      "trusted_unit": "raw",
      "trusted_unit_multiplier": 1,
      "allowed_as_primary": true,
      "related_only_fields": ["Net Income Common Stockholders"],
      "negative_examples": [],
      "proof_origin": "sampled_pdf_policy_proof",
      "samples": [],
      "required_proof": []
    }
  ]
}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="related_only_fields must not include raw_field_name"):
        load_provider_semantics_catalog(path)
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_provider_semantics.py -q
```

Expected: fail because `provider_semantics.py` does not exist.

- [ ] **Step 3: Implement minimal loader**

Create `provider_semantics.py` with frozen dataclasses:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProviderSemanticsRule:
    provider: str
    market: str
    raw_field_name: str
    raw_field_code: str | None
    turtle_field_id: str
    semantic_claim: str
    classification: str
    trusted_currency: str | None
    trusted_unit: str | None
    trusted_unit_multiplier: int | None
    allowed_as_primary: bool
    related_only_fields: tuple[str, ...]
    negative_examples: tuple[str, ...]
    proof_origin: str
    samples: tuple[dict[str, Any], ...]
    required_proof: tuple[str, ...]

    @classmethod
    def from_dict(cls, raw: dict[str, Any], index: int) -> "ProviderSemanticsRule":
        required = (
            "provider",
            "market",
            "raw_field_name",
            "raw_field_code",
            "turtle_field_id",
            "semantic_claim",
            "classification",
            "trusted_currency",
            "trusted_unit",
            "trusted_unit_multiplier",
            "allowed_as_primary",
            "related_only_fields",
            "negative_examples",
            "proof_origin",
            "samples",
            "required_proof",
        )
        missing = [name for name in required if name not in raw]
        if missing:
            raise ValueError(f"provider semantics rule {index} missing keys: {missing}")
        rule = cls(
            provider=_required_str(raw, "provider", index),
            market=_required_str(raw, "market", index),
            raw_field_name=_required_str(raw, "raw_field_name", index),
            raw_field_code=_optional_str(raw, "raw_field_code", index),
            turtle_field_id=_required_str(raw, "turtle_field_id", index),
            semantic_claim=_required_str(raw, "semantic_claim", index),
            classification=_required_str(raw, "classification", index),
            trusted_currency=_optional_str(raw, "trusted_currency", index),
            trusted_unit=_optional_str(raw, "trusted_unit", index),
            trusted_unit_multiplier=_optional_int(raw, "trusted_unit_multiplier", index),
            allowed_as_primary=_required_bool(raw, "allowed_as_primary", index),
            related_only_fields=_str_tuple(raw, "related_only_fields", index),
            negative_examples=_str_tuple(raw, "negative_examples", index),
            proof_origin=_required_str(raw, "proof_origin", index),
            samples=_dict_tuple(raw, "samples", index),
            required_proof=_str_tuple(raw, "required_proof", index),
        )
        rule.validate()
        return rule

    def validate(self) -> None:
        if self.raw_field_name in self.related_only_fields:
            raise ValueError("related_only_fields must not include raw_field_name")
        if self.allowed_as_primary and not self.semantic_claim:
            raise ValueError("primary provider semantics rules require semantic_claim")
        if self.allowed_as_primary and self.classification == "provider_semantics_unverified":
            raise ValueError("unverified provider semantics rule cannot be primary")


@dataclass(frozen=True)
class ProviderSemanticsCatalog:
    rules: tuple[ProviderSemanticsRule, ...]

    def require_rule(
        self,
        *,
        provider: str,
        market: str,
        turtle_field_id: str,
        raw_field_name: str,
    ) -> ProviderSemanticsRule:
        for rule in self.rules:
            if (
                rule.provider == provider
                and rule.market == market
                and rule.turtle_field_id == turtle_field_id
                and rule.raw_field_name == raw_field_name
            ):
                return rule
        raise ValueError(
            "provider semantics rule not found: "
            f"{provider}/{market}/{turtle_field_id}/{raw_field_name}"
        )


def load_provider_semantics_catalog(path: Path | str) -> ProviderSemanticsCatalog:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("rules"), list):
        raise ValueError("provider semantics catalog must contain a rules list")
    return ProviderSemanticsCatalog(
        rules=tuple(
            ProviderSemanticsRule.from_dict(rule, index)
            for index, rule in enumerate(raw["rules"])
            if isinstance(rule, dict)
        )
    )


def _required_str(raw: dict[str, Any], key: str, index: int) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"provider semantics rule {index} key {key} must be a non-empty string")
    return value


def _optional_str(raw: dict[str, Any], key: str, index: int) -> str | None:
    value = raw[key]
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"provider semantics rule {index} key {key} must be null or a non-empty string")
    return value


def _optional_int(raw: dict[str, Any], key: str, index: int) -> int | None:
    value = raw[key]
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(f"provider semantics rule {index} key {key} must be null or an integer")
    return value


def _required_bool(raw: dict[str, Any], key: str, index: int) -> bool:
    value = raw[key]
    if not isinstance(value, bool):
        raise ValueError(f"provider semantics rule {index} key {key} must be a boolean")
    return value


def _str_tuple(raw: dict[str, Any], key: str, index: int) -> tuple[str, ...]:
    value = raw[key]
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"provider semantics rule {index} key {key} must be a list of strings")
    return tuple(value)


def _dict_tuple(raw: dict[str, Any], key: str, index: int) -> tuple[dict[str, Any], ...]:
    value = raw[key]
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"provider semantics rule {index} key {key} must be a list of objects")
    return tuple(value)
```

- [ ] **Step 4: Add the initial JSON artifact**

Create `field_catalog/provider_raw_semantics_hk.json` with at least:

- Yahoo HK `net_profit` / `Net Income Common Stockholders` as `provider_semantics_sample_verified`.
- Yahoo HK `gross_profit` / `Gross Profit` as `provider_semantics_unverified`.
- AKShare HK `gross_profit` / `毛利` as `provider_semantics_unverified`.

- [ ] **Step 5: Run tests**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_provider_semantics.py -q
```

Expected: pass.

## Task 2: Guard Source Policy With Provider Semantics

**Files:**

- Modify: `tests/test_source_policy.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/source_policy.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/hk_yahoo_trust_policy.py`

- [ ] **Step 1: Add failing policy tests**

Add assertions that:

- HK Yahoo `net_profit` can only be trusted when raw field is `Net Income Common Stockholders`.
- HK Yahoo `Net Income` remains untrusted even if value/currency/unit match.
- HK Yahoo `gross_profit` remains `verification_required`.

Use existing source-policy fixture builders from `tests/test_source_policy.py` rather than new real artifacts.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_source_policy.py -q
```

Expected: at least one new assertion fails until source policy consults provider semantics.

- [ ] **Step 3: Wire provider semantics into trust checks**

Update the HK Yahoo trust decision so it requires both:

- existing HK Yahoo trust policy metadata checks
- provider semantics rule `allowed_as_primary is True`

Keep backward compatibility with existing `hk_yahoo_trust_policy.json` while Phase M4 is being introduced.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_provider_semantics.py tests/test_source_policy.py tests/test_hk_yahoo_trust_policy.py -q
```

Expected: pass.

## Task 3: Fix Mapping Catalog Semantics

**Files:**

- Modify: `tests/test_source_mapping_catalog.py`
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`

- [ ] **Step 1: Add catalog consistency tests**

Add tests that fail when:

- a field has `verification_status: verified` while provider semantics says the selected HK raw field is unverified.
- `gross_profit` has a trusted HK primary route without provider semantics proof.
- `net_profit` related Yahoo fields appear in a role that source policy may promote.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_source_mapping_catalog.py tests/test_provider_semantics.py -q
```

Expected: fail on current `gross_profit` route/status mismatch.

- [ ] **Step 3: Update catalog**

Update `gross_profit` to make the unresolved status explicit:

- keep Yahoo `Gross Profit` and AKShare `毛利` as candidates
- set HK policy to non-clean/unverified
- remove wording that implies verified direct HK primary
- keep fallback as selected PDF/provider semantics review, not broad PDF extraction

Update `net_profit` to preserve:

- trusted Yahoo primary = `Net Income Common Stockholders`
- related context = broader Yahoo net income rows

- [ ] **Step 4: Run tests**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_source_mapping_catalog.py tests/test_provider_semantics.py -q
```

Expected: pass.

## Task 4: Correct Replay And Closure Reporting

**Files:**

- Modify: `tests/test_provider_baseline_replay.py`
- Modify: `tests/test_hk_15_field_closure.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/hk_15_field_closure.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`

- [ ] **Step 1: Add replay expectation tests**

Assert that HK replay reports:

- `net_profit` has provider semantics proof evidence.
- `net_profit` proof is not final `pdf_evidence`.
- `gross_profit` remains non-clean.
- clean-present counts do not hide review notes or conflict classifications.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_provider_baseline_replay.py tests/test_hk_15_field_closure.py -q
```

Expected: fail where reports still use ambiguous proof wording or closure clean predicates are too weak.

- [ ] **Step 3: Update reporting**

Update reports to include separate fields:

- `provider_semantics_verified_fields`
- `sampled_pdf_policy_proof_fields`
- `final_pdf_evidence_fields`
- `provider_semantics_unverified_fields`

If `yahoo_pdf_verified_fields` remains for compatibility, mark it as deprecated in the JSON/Markdown report and mirror the values into `sampled_pdf_policy_proof_fields`.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_provider_baseline_replay.py tests/test_hk_15_field_closure.py tests/test_warning_classification.py -q
```

Expected: pass.

## Task 5: Validate PDF Policy Samples Against Page Text

**Files:**

- Modify: `tests/test_hk_yahoo_trust_policy.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/hk_yahoo_trust_policy.py`

- [ ] **Step 1: Add sample text validation test**

Add a test that constructs a resolver returning captured page text containing:

- statement line
- reported unit
- reported value

Assert validation passes. Add another resolver that omits the statement line and assert validation fails with a stable `ValueError`.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_hk_yahoo_trust_policy.py -q
```

Expected: fail until loader/test path uses page-text validation.

- [ ] **Step 3: Implement page-text validation path**

Keep default catalog loading offline. Add an explicit validation helper, for example:

```python
def validate_hk_yahoo_trust_policy_samples(
    policy: HkYahooTrustPolicy,
    page_text_resolver: Callable[[HkYahooTrustSample], str | None],
) -> None:
    policy.validate(page_text_resolver=page_text_resolver)
```

Do not make ordinary unit tests depend on real PDF parsing.

- [ ] **Step 4: Run tests**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_hk_yahoo_trust_policy.py -q
```

Expected: pass.

## Task 6: Update Docs And Roadmap

**Files:**

- Modify: `AGENTS.md`
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
- Modify: `docs/superpowers/specs/2026-05-07-phase-m3-hk-net-profit-pdf-proof.md`
- Modify: `docs/superpowers/plans/2026-05-07-phase-m3-hk-net-profit-pdf-proof.md`

- [ ] **Step 1: Update terminology**

Replace wording that implies M3 produced final PDF evidence with wording that says:

- M3 selected and sampled Yahoo raw semantics for `net_profit`.
- PDF samples support provider policy proof.
- Final per-export PDF evidence is separate.

- [ ] **Step 2: Mark Phase N as blocked by Phase M4**

Roadmap must say Phase N starts only after:

- provider raw semantics artifact exists
- `gross_profit` is terminal/non-clean with stable reason
- `net_profit` sampled proof wording is corrected
- replay reports distinguish sampled policy proof from final PDF evidence

- [ ] **Step 3: Run documentation checks**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); Select-String -Path AGENTS.md,docs\roadmap\2026-04-30-llm-first-financial-report-extractor-roadmap.md,docs\superpowers\specs\2026-05-07-phase-m3-hk-net-profit-pdf-proof.md,docs\superpowers\plans\2026-05-07-phase-m3-hk-net-profit-pdf-proof.md -Pattern 'per-company PDF value matching|final PDF evidence|provider semantics|sampled PDF policy proof'
```

Expected: enough matches to show the new guardrails are visible.

## Task 7: Final Verification

**Files:**

- All files touched in Tasks 1-6.

- [ ] **Step 1: Run focused suite**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '.venv\Scripts\pytest.exe' tests/test_provider_semantics.py tests/test_hk_yahoo_trust_policy.py tests/test_source_mapping_catalog.py tests/test_source_policy.py tests/test_provider_baseline_replay.py tests/test_hk_15_field_closure.py tests/test_warning_classification.py -q
```

Expected: pass.

- [ ] **Step 2: Run lint**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); uv run ruff check .
```

Expected: pass.

- [ ] **Step 3: Run diff check**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 4: Commit**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); git add field_catalog src tests docs AGENTS.md
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); git commit -m "fix: clarify provider semantics proof boundary"
```

Expected: commit succeeds.

## Execution Notes

- Do not promote `gross_profit` in this phase.
- Do not expand to 33 P0/P1 fields in this phase.
- Do not run broad PDF retrieval.
- Treat PDF samples as provider policy proof, not final export evidence.
- Keep the `net_profit` raw field decision; correct its proof semantics.

