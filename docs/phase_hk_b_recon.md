# Phase HK-B Recon: 6 HK Conflict Shape

> Date: 2026-05-10
> Scope: `fix_assets`, `accounts_receiv`, `acct_payable`, `gross_profit`
> Inputs: 6 HK source-first baselines after the HK LLM 6 fixture extension.
> Status: HK-B.1 regression lock for `acct_payable` is implemented in
> `tests/test_phase_hk_b_acct_payable.py`; HK-B.2 regression lock for
> `fix_assets` is implemented in `tests/test_phase_hk_b_fix_assets.py`;
> HK-B.3 regression lock for `accounts_receiv` is implemented in
> `tests/test_phase_hk_b_accounts_receiv.py`; HK-B.4 conservative lock for
> `gross_profit` is implemented in `tests/test_phase_hk_b_gross_profit.py`.

## Summary

The fixture-extension prerequisite for HK-B is now satisfied: 4 new HK
issuer fixtures (`01810`, `02498`, `06862`, `09987`) were captured from live
AKShare HK + Yahoo HK and added alongside existing `00001` / `01113`
baselines.

The recon does not support a broad alias-gap phase. All four HK-B fields have
provider candidates in the relevant samples; the remaining work is source
policy / provider-semantics proof, not candidate discovery.

## Bucket Counts

| Field | 6-HK bucket shape | Current implication |
|---|---:|---|
| `fix_assets` | 3 clean, 3 unresolved conflict | Candidate semantics vary by issuer; needs sample-verified policy, not global blind promotion. |
| `accounts_receiv` | 6 unresolved conflict | AKShare `应收帐款` and Yahoo `Accounts Receivable` systematically disagree; likely combined-line / scope mismatch. |
| `acct_payable` | 3 clean, 3 unresolved conflict | Some issuers match exactly, but CK-style issuers diverge; policy must be market/sample scoped. |
| `gross_profit` | 4 unresolved conflict, 2 terminal unverified | Still no clean HK promotion. Keep conservative unless provider raw semantics proof is established. |

## Per-Company Evidence Shape

| Company | Field | Bucket | Reason | Selected | Candidates |
|---|---|---|---|---|---|
| 00001 | `fix_assets` | unresolved_conflict | normalized_value_conflict |  | akshare `固定资产` = 90,394,257,600; yahoo `Net PPE` = 159,240,000,000 |
| 00001 | `accounts_receiv` | unresolved_conflict | normalized_value_conflict |  | akshare `应收帐款` = 38,212,528,540; yahoo `Accounts Receivable` = 14,952,000,000 |
| 00001 | `acct_payable` | unresolved_conflict | normalized_value_conflict |  | akshare `应付帐款` = 73,227,658,280; yahoo `Accounts Payable` = 22,632,000,000 |
| 00001 | `gross_profit` | unresolved_conflict | normalized_value_conflict | yahoo | akshare `毛利` = 141,671,863,440; yahoo `Gross Profit` = 139,204,000,000 |
| 01113 | `fix_assets` | unresolved_conflict | normalized_value_conflict |  | akshare `固定资产` = 65,815,834,960; yahoo `Net PPE` = 72,868,000,000 |
| 01113 | `accounts_receiv` | unresolved_conflict | normalized_value_conflict |  | akshare `应收帐款` = 6,755,182,380; yahoo `Accounts Receivable` = 2,028,000,000 |
| 01113 | `acct_payable` | unresolved_conflict | normalized_value_conflict |  | akshare `应付帐款` = 17,079,890,200; yahoo `Accounts Payable` = 3,607,000,000 |
| 01113 | `gross_profit` | unresolved_conflict | normalized_value_conflict | yahoo | akshare `毛利` = 23,084,496,760; yahoo `Gross Profit` = 25,558,000,000 |
| 01810 | `fix_assets` | clean_present |  | yahoo | yahoo `Net PPE` = 24,588,261,000 |
| 01810 | `accounts_receiv` | unresolved_conflict | normalized_value_conflict |  | akshare `应收帐款` = 14,588,579,000; yahoo `Accounts Receivable` = 12,662,060,000 |
| 01810 | `acct_payable` | clean_present |  | akshare | akshare `应付帐款` = 98,280,585,000; yahoo `Accounts Payable` = 98,280,585,000 |
| 01810 | `gross_profit` | terminal_unverified | yahoo_definition_unverified | yahoo | akshare `毛利` = 76,560,194,000; yahoo `Gross Profit` = 76,560,194,000 |
| 02498 | `fix_assets` | clean_present |  | yahoo | yahoo `Net PPE` = 321,863,000 |
| 02498 | `accounts_receiv` | unresolved_conflict | normalized_value_conflict |  | akshare `应收帐款` = 462,189,000; yahoo `Accounts Receivable` = 410,611,000 |
| 02498 | `acct_payable` | clean_present |  | akshare | akshare `应付帐款` = 475,825,000; yahoo `Accounts Payable` = 475,825,000 |
| 02498 | `gross_profit` | terminal_unverified | yahoo_definition_unverified | yahoo | akshare `毛利` = 283,553,000; yahoo `Gross Profit` = 283,553,000 |
| 06862 | `fix_assets` | clean_present |  | yahoo | yahoo `Net PPE` = 6,338,547,000 |
| 06862 | `accounts_receiv` | unresolved_conflict | normalized_value_conflict |  | akshare `应收帐款` = 1,517,431,000; yahoo `Accounts Receivable` = 346,347,000 |
| 06862 | `acct_payable` | clean_present |  | akshare | akshare `应付帐款` = 1,796,362,000; yahoo `Accounts Payable` = 1,796,362,000 |
| 06862 | `gross_profit` | unresolved_conflict | normalized_value_conflict | yahoo | akshare `毛利` = 26,543,610,000; yahoo `Gross Profit` = 12,108,412,000 |
| 09987 | `fix_assets` | unresolved_conflict | normalized_value_conflict |  | akshare `固定资产` = 17,302,478,800; yahoo `Net PPE` = 4,580,000,000 |
| 09987 | `accounts_receiv` | unresolved_conflict | normalized_value_conflict |  | akshare `应收帐款` = 567,883,600; yahoo `Accounts Receivable` = 79,000,000 |
| 09987 | `acct_payable` | unresolved_conflict | normalized_value_conflict |  | akshare `应付帐款` = 14,951,872,000; yahoo `Accounts Payable` = 801,000,000 |
| 09987 | `gross_profit` | unresolved_conflict | normalized_value_conflict | yahoo | akshare `毛利` = 16,756,160,400; yahoo `Gross Profit` = 1,890,000,000 |

## Recommended HK-B Work Order

1. `acct_payable`: three exact AKShare/Yahoo matches provide a narrow,
   lower-risk path for a sample-scoped rule, while the three conflicts define
   the exclusion shape. HK-B.1 now locks this shape and deliberately does not
   promote the three conflict cases.
2. `fix_assets`: three clean Yahoo `Net PPE` cases exist, but the three
   conflicts confirm prior right-of-use / fixed-asset scope divergence. Any
   promotion must be guarded by explicit sample proof or issuer-pattern policy.
   HK-B.2 now locks the current 3 clean / 3 conflict shape.
3. `accounts_receiv`: all six are conflicts; likely requires terminal or
   PDF-required semantics rather than a provider promotion. HK-B.3 now locks
   the all-conflict shape.
4. `gross_profit`: keep non-clean. Even exact AKShare/Yahoo agreement in two
   companies proves provider-provider agreement only; it does not prove HK
   annual-report gross-profit semantics. HK-B.4 now locks the 4 conflict /
   2 terminal-unverified shape and asserts no HK sample is clean-present.

## Guardrails

- Do not use per-company PDF value matching as final evidence.
- Do not promote `gross_profit` from provider-provider agreement alone.
- Keep `source_evidence`, `trust_policy_evidence`, and `pdf_evidence`
  separate in any subsequent policy changes.
- Prefer adding provider-semantics / trust-policy rules with explicit sample
  counts and negative cases over broad alias changes.
