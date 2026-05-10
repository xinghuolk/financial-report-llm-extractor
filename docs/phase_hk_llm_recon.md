# B-Recon: HK LLM Extraction Reality Check

> Date: 2026-05-10 (post-Phase H2.4)
> Question: why does HK LLM appear to produce 0 hits, blocking the LLM-orchestrator wire-in?
> Answer: **it doesn't — the prior 0-hit observation was a misread of a single-field smoke test. HK LLM produces meaningful hits at scale; the reason H2.2 evaluations show `llm_supplement_present=0` is simply that those runs didn't pass `--pdf` + `--llm-config`.**

## What I checked

Inventoried every `llm_evidence_supplement.json` under `tmp/runs/` across past phases. The "0 hits / 1 attempted" observation that triggered this recon was from `tmp/runs/phase_i_c_alias_iter_1/01113/`, which is a single-field experiment for `receivables_aging` only — not a representative HK LLM run.

The substantive HK runs are under `tmp/runs/phase_i_c_validation_v2/` (most recent comprehensive validation, 14 P3 fields × 6 HK companies).

## HK LLM hit rates (phase_i_c_validation_v2, 14 P3 fields per company)

| Company | Present / Attempted | Rate | Fields hit |
|---------|---------------------|------|------------|
| 00001 | 6/14 | 43% | bad_debt_provision, capitalized_interest, contingent_liabilities_commitments, dividend_plan, dps, segment_revenue_profit |
| 01113 | 4/14 | 29% | bad_debt_provision, contingent_liabilities_commitments, dividend_plan, dps |
| 01810 | 8/14 | 57% | + buyback_cancellation_progress, lease_liability_maturity, receivables_aging, restricted_cash, segment_revenue_profit |
| 02498 | 6/14 | 43% | + related_party_receivables_payables, restricted_cash, time_deposits_or_wealth_products |
| 06862 | 5/14 | 36% | + related_party_receivables_payables, time_deposits_or_wealth_products |
| 09987 | 4/14 | 29% | bad_debt_provision, lease_liability_maturity, segment_revenue_profit, time_deposits_or_wealth_products |

**Aggregate**: 33 hits / 84 attempts = **39% present rate** across 6 HK companies — matches the figure cited in CLAUDE.md ("HK LLM: 33/84 hits, 0 extraction_failed"). HK LLM is **working at design**.

## Why the H2.2 evals show `llm_supplement_present=0`

The H2.2 evaluations (`tmp/runs/h2_2_after/{00001,01113}/`) were run without `--pdf` + `--llm-config`:

```bash
$ ls tmp/runs/h2_2_after/01113/ | grep -i llm
# (empty)
```

No `llm_evidence_supplement.json` exists in those runs. The LLM-supplement step in `_run_llm_supplement_step` only triggers when both `pdf_provided` AND `llm_config_path` are set (company_evaluation.py:374). Without those args, the orchestrator skips LLM entirely → all P3 missing-candidate cells stay in `unresolved_conflict`.

## Coverage delta projections (if LLM supplement re-applied to H2.2 evals)

Counting how the 14-field LLM supplement would migrate cells from `unresolved_conflict` → `llm_supplement_present`:

| Company | Current clean | LLM hits | Projected clean | Delta |
|---------|---:|---:|---:|---:|
| 600519/2024 (CN) | 39/56 (70%) | 6 | 45/56 (80%) | +6 / +10 pp |
| 00001/2025 (HK) | 28/56 (50%) | 6 | 34/56 (61%) | +6 / +11 pp |
| 01113/2025 (HK) | 29/56 (52%) | 4 | 33/56 (59%) | +4 / +7 pp |
| 01810/2025 (HK) | n/a (no eval) | 8 | n/a | LLM-strongest in cohort |
| 02498/2025 (HK) | n/a | 6 | n/a | |
| 06862/2025 (HK) | n/a | 5 | n/a | |
| 09987/2025 (HK) | n/a | 4 | n/a | |

(These deltas assume LLM hits are net-additive — they target P3 fields that source-first evaluations classify as `unresolved_conflict / missing_source_candidate` so each hit moves a cell up the bucket cascade.)

## Why this matters for the next phase

1. **The "wire-in" framing was wrong.** The orchestrator wiring is complete (company_evaluation.py:374-379 + provider_baseline_replay.py:338+). HK LLM works. The observed gap was a process/UX issue, not an engineering issue.

2. **The actual leverage is enabling LLM by default in evaluate-company runs.** Either:
   - Auto-enable when `--pdf` + `--llm-config` are present (current behavior — works, just needs to be exercised)
   - Make `--llm-config` resolve to a default path (e.g., `tmp/llm_configs/deepseek.json`) so it doesn't have to be passed every time
   - Document the expected workflow in CLAUDE.md so future runs don't omit LLM args

3. **The default `derive_targets(priorities=("P0","P1"))` is too narrow.** The phase_i_c_validation_v2 runs used `priorities=("P3",)` explicitly — that's why they got P3 hits. A standard evaluate-company invocation with the default `--priorities P0,P1,P2,P3` will pass through to derive_targets which only attempts P0+P1. P3 fields with `pdf_aliases` would be silently skipped despite being the LLM's biggest delta.

## Recommendation

The actual `Phase HK-LLM` is now much smaller than originally framed. Three concrete sub-tasks:

| Sub-task | Scope | Effort | Impact |
|----------|-------|--------|--------|
| **HK-LLM-1**: change `derive_targets` default to all priorities (or align with the user-passed `--priorities`) | One line + test | XS (~30min) | Unblocks P3 LLM hits in default invocation |
| **HK-LLM-2**: re-run H2.2 evals (CN 600519 + HK 00001 + HK 01113) with `--pdf` + `--llm-config` to lock real coverage numbers; persist as fixture/baseline | Run + capture + commit | XS (~30min) | Replaces aspirational coverage figures in CLAUDE.md with measured ground truth |
| **HK-LLM-3** (optional): document the default LLM workflow in CLAUDE.md "常用命令" so the next session doesn't accidentally omit LLM args | Docs only | XS (~10min) | Prevents recurrence of the "0 supplement" surprise |

Total: ~1.5h for all three. No M-spec needed; original "M ~6h spec discussion" was based on the false premise that wiring was missing.

**HK-B (sample-verified conflict resolution for fix_assets/accounts_receiv/etc) remains the next macro phase** — but it should follow the LLM baseline establishment so we know the true source-first ceiling before investing in conflict-resolution machinery.
