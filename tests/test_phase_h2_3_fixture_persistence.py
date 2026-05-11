"""Phase H2.3 #3: fixture-backed regression for sample-verified samples.

Locks in the H2.2 multi-company evidence so it is reproducible offline:
each sample claiming an `expected_provider_raw_value` must match the
corresponding raw record stored in the persisted fixtures.

Two fixtures cover the four CN sample companies:
- `provider_field_baseline/source_inventory.jsonl.gz`        — 600519 baseline
- `provider_field_baseline_h2_2_extension/source_inventory.jsonl.gz` — 300750/601919/688008

For derivation rules (e.g. SGA = MANAGE_EXPENSE + SALE_EXPENSE), the rule
must declare `derivation_legs: ["MANAGE_EXPENSE", "SALE_EXPENSE"]` and the
test sums those leg values from the fixture. Otherwise the test looks up
`raw_field_code` directly. (`related_only_fields` is documentation /
negative-example metadata; it MUST NOT be summed automatically — for the
revenue rule it contains `TOTAL_OPERATE_INCOME` as a *negative* example.)
"""

from __future__ import annotations

import gzip
import json
from decimal import Decimal
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SEMANTICS_CN = REPO_ROOT / "field_catalog" / "provider_raw_semantics_cn.json"
FIXTURE_BASELINE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "provider_captures"
    / "provider_field_baseline"
    / "source_inventory.jsonl.gz"
)
FIXTURE_EXTENSION = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "provider_captures"
    / "provider_field_baseline_h2_2_extension"
    / "source_inventory.jsonl.gz"
)
FIXTURE_HK_LLM_6_EXTENSION_ROOT = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "provider_captures"
    / "provider_field_baseline_hk_llm_6_extension"
)


def _load_fixture_records(*paths: Path) -> list[dict]:
    records: list[dict] = []
    for path in paths:
        assert path.exists(), f"fixture missing: {path}"
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def _find_record(
    records: list[dict],
    *,
    ticker: str,
    period_prefix: str,
    raw_field_code: str,
    source: str = "akshare",
) -> dict | None:
    for r in records:
        if (
            r.get("ticker") == ticker
            and (r.get("period") or "").startswith(period_prefix)
            and r.get("raw_field_code") == raw_field_code
            and r.get("source") == source
        ):
            return r
    return None


def _verifiable_samples() -> list[tuple[dict, dict]]:
    """Yield (rule, sample) pairs where the sample claims an
    `expected_provider_raw_value` and is keyed to a CN AKShare lookup."""
    payload = json.loads(SEMANTICS_CN.read_text(encoding="utf-8"))
    out: list[tuple[dict, dict]] = []
    for rule in payload.get("rules", []):
        if rule.get("provider") != "akshare" or rule.get("market") != "CN":
            continue
        for sample in rule.get("samples", []):
            if "expected_provider_raw_value" not in sample:
                continue
            out.append((rule, sample))
    return out


def test_h2_3_each_sample_with_expected_value_matches_fixture() -> None:
    """Every sample with `expected_provider_raw_value` must reconcile against
    the persisted fixture. Catches drift between catalog samples and the
    raw AKShare snapshot (e.g., upstream renaming, value changes)."""
    records = _load_fixture_records(FIXTURE_BASELINE, FIXTURE_EXTENSION)
    pairs = _verifiable_samples()
    assert pairs, "expected at least one CN AKShare sample with expected_provider_raw_value"

    failures: list[str] = []
    for rule, sample in pairs:
        company_id = sample.get("company_id")
        period_end = sample.get("period_end")
        expected_str = sample["expected_provider_raw_value"]
        if not (
            isinstance(company_id, str)
            and isinstance(period_end, str)
            and isinstance(expected_str, str)
        ):
            failures.append(
                f"rule {rule.get('turtle_field_id')!r} sample malformed: "
                f"company_id={company_id!r} period_end={period_end!r} "
                f"expected_provider_raw_value={expected_str!r}"
            )
            continue

        expected = Decimal(expected_str)
        # Derivation: explicit leg list. Otherwise single field lookup.
        derivation_legs = rule.get("derivation_legs")
        if derivation_legs:
            assert isinstance(derivation_legs, list)
            leg_codes = [str(c) for c in derivation_legs]
        else:
            leg_codes = [rule["raw_field_code"]]
        actual = Decimal("0")
        missing_codes: list[str] = []
        for code in leg_codes:
            rec = _find_record(
                records,
                ticker=company_id,
                period_prefix=period_end,
                raw_field_code=code,
            )
            if rec is None:
                missing_codes.append(code)
                continue
            raw_value = rec.get("raw_value")
            if raw_value is None:
                missing_codes.append(f"{code}(null)")
                continue
            actual += Decimal(str(raw_value))

        if missing_codes:
            failures.append(
                f"{rule['turtle_field_id']} / {company_id} / {period_end}: "
                f"fixture lookup missing for {missing_codes}"
            )
            continue
        if actual != expected:
            failures.append(
                f"{rule['turtle_field_id']} / {company_id} / {period_end}: "
                f"expected {expected}, got {actual} (legs={leg_codes})"
            )

    if failures:
        pytest.fail(
            "fixture-vs-sample mismatches:\n  - " + "\n  - ".join(failures)
        )


def test_h2_3_extension_fixture_covers_three_h2_2_companies() -> None:
    """Phase H2.2 Sub-A captured 300750/601919/688008 from live AKShare;
    fixture must include all three so future regression tests don't
    require network."""
    records = _load_fixture_records(FIXTURE_EXTENSION)
    tickers = {r.get("ticker") for r in records}
    assert {"300750", "601919", "688008"}.issubset(tickers), (
        f"H2.2 extension fixture must cover 300750/601919/688008; got {tickers}"
    )


def test_h2_3_extension_artifact_manifest_present() -> None:
    """Manifest documents which AKShare endpoints + dates produced the
    captured records — useful for traceability if upstream values shift."""
    manifest_path = (
        FIXTURE_EXTENSION.parent / "source_artifact_manifest.json"
    )
    assert manifest_path.exists(), (
        f"H2.2 extension fixture must ship manifest at {manifest_path}"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "artifacts" in payload and isinstance(payload["artifacts"], list)
    assert payload["artifacts"], "manifest must list at least one artifact"


def test_hk_llm_6_extension_fixture_covers_four_new_hk_companies() -> None:
    expected = {"01810", "02498", "06862", "09987"}
    for ticker in sorted(expected):
        fixture = FIXTURE_HK_LLM_6_EXTENSION_ROOT / ticker / "source_inventory.jsonl.gz"
        records = _load_fixture_records(fixture)
        tickers = {r.get("ticker") for r in records}
        sources = {r.get("source") for r in records}
        assert ticker in tickers or f"{int(ticker)}.HK" in tickers
        assert {"akshare", "yahoo"}.issubset(sources)


def test_hk_llm_6_extension_artifact_manifest_present() -> None:
    manifest_path = FIXTURE_HK_LLM_6_EXTENSION_ROOT / "source_artifact_manifest.json"
    assert manifest_path.exists(), (
        f"HK LLM 6 extension fixture must ship manifest at {manifest_path}"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload.get("companies") == ["01810", "02498", "06862", "09987"]
    assert "artifacts" in payload and isinstance(payload["artifacts"], list)
    assert len(payload["artifacts"]) == 24
