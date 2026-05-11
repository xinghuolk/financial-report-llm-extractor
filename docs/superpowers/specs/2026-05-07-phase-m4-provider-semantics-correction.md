# Phase M4: Provider Raw Semantics Correction Spec

> Date: 2026-05-07
> Status: Draft
> Roadmap phase: Phase M4

## Goal

Correct the drift introduced by HK PDF proof work by making provider raw field semantics the explicit trust boundary.

The system must prove what a provider raw field means before it can promote that raw field to a clean Turtle value. PDF samples may support that provider-level proof, but they must not become a per-company value-matching workflow.

## Problem

Recent HK work correctly moved the project toward source-first replay, source policy, and terminal buckets. However, the `yahoo_pdf_verified` terminology and Phase M3 `net_profit` acceptance criteria are too strong.

They can be misread as:

```text
For every company and every field, find a matching value in the PDF.
```

That is not the intended architecture. The intended architecture is:

```text
Provider raw field
-> provider/market/field semantic proof
-> source policy trust decision
-> optional final PDF evidence supplement
```

## Required Vocabulary

The implementation and documents must distinguish these concepts:

- `source_evidence`: evidence that a value came from a provider artifact.
- `provider_semantics_proof`: evidence that a provider raw field maps to a Turtle semantic concept.
- `sampled_pdf_policy_proof`: annual-report samples used to support provider semantics proof.
- `pdf_evidence`: final per-export page/block/snippet evidence for a specific company/field.

`sampled_pdf_policy_proof` must not be treated as `pdf_evidence`.

## Required Behavior

1. Add a provider raw semantics artifact or equivalent loader contract.
2. Model provider raw field trust by provider, market, raw field, Turtle field, semantic claim, trusted metadata, and proof status.
3. Split direct trusted raw fields from related context fields.
4. Preserve M3's useful `net_profit` judgment:
   - Yahoo HK `Net Income Common Stockholders` may be the trusted raw field for Turtle `net_profit`.
   - Yahoo HK `Net Income` and `Net Income From Continuing Operation Net Minority Interest` must remain related-only or negative context.
5. Reframe M3 as sampled provider semantics proof, not final per-company PDF evidence.
6. Keep `gross_profit` non-clean until Yahoo or AKShare raw semantics are proven by provider-level proof.
7. Block Phase N 33-field expansion until catalog semantics, trust policy naming, and replay expectations no longer confuse sampled proof with final PDF evidence.

## Provider Semantics Artifact

The minimal artifact shape should be reviewable JSON. It may initially wrap or coexist with `field_catalog/hk_yahoo_trust_policy.json`, but the contract must be explicit.

Required fields per rule:

```json
{
  "provider": "yahoo",
  "market": "HK",
  "raw_field_name": "Net Income Common Stockholders",
  "raw_field_code": null,
  "turtle_field_id": "net_profit",
  "semantic_claim": "profit attributable to ordinary/common shareholders",
  "classification": "provider_semantics_sample_verified",
  "trusted_currency": "HKD",
  "trusted_unit": "raw",
  "trusted_unit_multiplier": 1,
  "allowed_as_primary": true,
  "related_only_fields": [
    "Net Income",
    "Net Income From Continuing Operation Net Minority Interest"
  ],
  "negative_examples": [],
  "proof_origin": "sampled_pdf_policy_proof",
  "samples": [],
  "required_proof": []
}
```

## PDF Sample Requirements

PDF samples may be used only as policy-level proof. Each sample must record:

- company id
- ticker
- report path or artifact id
- PDF page
- statement title
- statement line
- reported currency
- reported unit label
- reported unit multiplier
- PDF value
- expected provider raw value
- matched provider raw field

At least one focused test must verify that sample text exists in captured PDF page text, not only that `pdf_value * multiplier == provider_raw_value`.

## gross_profit Policy

`gross_profit` must remain unresolved for HK until the provider raw field semantics are proven.

Allowed states:

- `yahoo_definition_unverified`
- `provider_semantics_unverified`
- `pdf_required`

Disallowed states:

- clean present solely because Yahoo has `Gross Profit`
- clean present solely because AKShare has `毛利`
- clean present solely because one company PDF has a value that can be matched or derived

## net_profit Policy

`net_profit` may retain the M3 raw field selection, but the proof classification must be interpreted as provider-level sampled semantics proof.

Acceptance must prove:

- only `Net Income Common Stockholders` can be promoted as HK Yahoo primary
- broader Yahoo rows are related-only or negative context
- sampled proof is exposed as trust policy evidence
- sampled proof is not exported as final `pdf_evidence`

## Acceptance Criteria

1. Docs and roadmap explicitly state that provider raw semantics proof precedes PDF fallback.
2. AGENTS.md tells future agents not to solve provider semantics by chasing per-company PDF values.
3. Catalog or loader tests fail if a trusted field is mixed with related-only raw fields without explicit roles.
4. `gross_profit` remains non-clean in HK replay.
5. `net_profit` source selection still prefers `Net Income Common Stockholders`, but reports proof as provider semantics policy proof.
6. Trust policy sample tests include page-text validation or an explicit skip reason for missing captured page text.
7. Phase N is documented as blocked until Phase M4 is complete.

## Non-Goals

- Do not expand from 15 fields to 33 fields in this phase.
- Do not add new real provider calls.
- Do not run broad PDF retrieval.
- Do not introduce canonical fact promotion.
- Do not force `gross_profit` to become clean.

