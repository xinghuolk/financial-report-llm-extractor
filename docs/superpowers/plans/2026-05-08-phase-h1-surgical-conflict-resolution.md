# Phase H1: Surgical Conflict Resolution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Resolve 7 conflict fields via source_mapping JSON adjustments + provider_semantics rules, no full PDF pipeline.

**Architecture:** Use existing `market_policies.cross_check_routes` to disable noisy cross-source checks for CN. Add provider_semantics rules (M5-style) for HK fields where Yahoo proven against PDF. Lock irreducible cases as terminal.

---

### Task 1: CN revenue/operating_profit — disable noisy Yahoo cross-check

**Files:**
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`

For `revenue` and `operating_profit`, find `source_policy.market_policies.CN`. Currently has Yahoo as cross_check. Change to:

```json
"CN": {
  "primary_route": "akshare_direct",
  "cross_check_routes": [],
  "on_conflict": "preserve_conflict",
  "single_source_requires_pdf": false
}
```

Why: For CN A-shares, Yahoo's `Total Revenue` and `Operating Income` represent different Turtle concepts than AKShare's `营业收入` / `营业利润`. Yahoo data is informative but not a meaningful cross-check for these CN fields. Removing it eliminates spurious semantic_mismatch flags.

HK market_policies stays unchanged.

- [ ] **Step 1: Run replay before, note current state**
  ```bash
  uv run financial-report-llm-extractor replay-provider-baseline \
    --inventory tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz \
    --inventory-summary tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json \
    --catalog field_catalog/turtle_v015_source_mapping_minimal.json \
    --out tmp/runs/h1_before
  ```
  Verify 600519 currently has revenue/operating_profit as ambiguous or verification_required.

- [ ] **Step 2: Update CN market policy for both fields**

- [ ] **Step 3: Run replay after**
  ```bash
  uv run financial-report-llm-extractor replay-provider-baseline ... --out tmp/runs/h1_after
  ```
  Expect 600519 revenue/operating_profit clean_present.

- [ ] **Step 4: Update tests**
  In `tests/test_provider_baseline_replay.py`, find 600519 expected_clean and add `revenue`, `operating_profit`. Update count.

- [ ] **Step 5: Run pytest**
  ```bash
  uv run pytest -v
  ```

- [ ] **Step 6: Commit**
  ```bash
  git commit -m "fix: disable yahoo cross-check for cn revenue and operating_profit"
  ```

---

### Task 2: CN SGA — switch primary to Yahoo

**Files:**
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`

For `selling_general_administrative`:
- AKShare CN reports MANAGE_EXPENSE and SELLING_EXPENSE separately. Single MANAGE_EXPENSE alias is incomplete (8,320M ≠ Turtle SGA total).
- Yahoo `Selling General And Administration` = 11,787M correctly aggregates.

Change CN market policy:
```json
"CN": {
  "primary_route": "yahoo_direct",
  "cross_check_routes": ["akshare_direct"],
  "on_conflict": "preserve_conflict",
  "single_source_requires_pdf": false
}
```

Add this new market_policies block if it doesn't exist on the field. If `source_policy` doesn't exist on SGA, create a minimal one.

- [ ] **Step 1: Update SGA mapping**

- [ ] **Step 2: Run replay**
  Verify 600519 SGA = clean_present, selected_source=yahoo.

- [ ] **Step 3: Update tests**

- [ ] **Step 4: Commit**

---

### Task 3: HK fix_assets — lock as terminal

**Files:**
- Modify: `field_catalog/provider_raw_semantics_hk.json`
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`

Reason: Yahoo Net PPE includes ROU assets for some HK issuers (00001) but matches Fixed assets for others (01113). Format-incompatible, similar to gross_profit.

Add to `provider_raw_semantics_hk.json`:

```json
{
  "allowed_as_primary": false,
  "classification": "provider_semantics_unverified",
  "market": "HK",
  "negative_examples": [],
  "proof_origin": "hk_statement_format_incompatible",
  "provider": "yahoo",
  "raw_field_code": null,
  "raw_field_name": "Net PPE",
  "related_only_fields": [],
  "required_proof": [
    "HK Yahoo Net PPE includes Right-of-use assets for some issuers (00001 Fixed assets 100,080 + ROU 59,160 = Yahoo 159,240) and matches Fixed assets directly for others (01113 Fixed assets 72,868 = Yahoo 72,868). Per-issuer divergence prevents primary promotion."
  ],
  "samples": [],
  "semantic_claim": "fixed assets per Turtle field semantics (excludes right-of-use)",
  "trusted_currency": "HKD",
  "trusted_unit": "raw",
  "trusted_unit_multiplier": 1,
  "turtle_field_id": "fix_assets"
}
```

And for AKShare 固定资产 HK:

```json
{
  "allowed_as_primary": false,
  "classification": "provider_semantics_unverified",
  "market": "HK",
  "negative_examples": [],
  "proof_origin": "hk_statement_format_incompatible",
  "provider": "akshare",
  "raw_field_code": null,
  "raw_field_name": "固定资产",
  "related_only_fields": [],
  "required_proof": [
    "AKShare HK 固定资产 returns values that don't match PDF Fixed assets line for sampled issuers (00001: AKShare 90,394 ≠ PDF 100,080; 01113: AKShare 65,816 ≠ PDF 72,868). Provider semantics unverified."
  ],
  "samples": [],
  "semantic_claim": "fixed assets per Turtle field semantics",
  "trusted_currency": "HKD",
  "trusted_unit": "raw",
  "trusted_unit_multiplier": 1,
  "turtle_field_id": "fix_assets"
}
```

Update `fix_assets` HK market policy if it exists, or add note in coverage_matrix.

- [ ] **Step 1: Add 2 provider_semantics rules**

- [ ] **Step 2: Run replay**
  HK fix_assets should now show as `provider_semantics_unverified` similar to gross_profit, not as clean.

- [ ] **Step 3: Update tests**
  Add `fix_assets` to HK warning classification expected (likely `pdf_verification_required` or similar).

- [ ] **Step 4: Commit**

---

### Task 4: HK 00001 inventories — Yahoo proof + drop AKShare HK alias

**Files:**
- Modify: `field_catalog/provider_raw_semantics_hk.json`
- Modify: `field_catalog/hk_yahoo_trust_policy.json`
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`

For HK inventories, add Yahoo Inventory as provider_semantics_sample_verified with PDF samples (M5 pattern).

PDF samples:
- 00001 page 136 "Inventories" 26,688 HK$ million → Yahoo Inventory 26,688,000,000 ✓
- 01113 page 71 "Properties for sale" 122,799 $ Million → Yahoo Inventory 122,799,000,000 ✓ (per IAS 2, properties for sale is inventory for real estate developer)

Add provider_semantics rule for Yahoo Inventory HK + trust policy rule.

Optionally: drop AKShare HK 存货 alias for HK market via market_policies.HK or via removing the Chinese alias from yahoo aliases.

- [ ] **Step 1: Add provider_semantics rule**

- [ ] **Step 2: Add trust_policy rule**

- [ ] **Step 3: Add HK market_policies to inventories source_mapping**

- [ ] **Step 4: Run replay**
  Verify 00001/01113 inventories clean_present.

- [ ] **Step 5: Update tests**

- [ ] **Step 6: Commit**

---

### Task 5: Verification + roadmap update

- [ ] **Step 1: Full pytest pass**

- [ ] **Step 2: Update roadmap with H1 result**

- [ ] **Step 3: Commit**

## Expected Coverage After H1

| Company | After H0 | After H1 |
|---------|----------|----------|
| 600519 | 30/33 | 33/33 (all clean) |
| 00001 | 20/33 | 21/33 (inventories) |
| 01113 | 21/33 | 22/33 (inventories was clean before; net_change might be -1 since fix_assets locks as non-clean) |

Wait — re-check 01113 inventories. Was it already clean? Yes, 01113 Yahoo Inventory matches its "Properties for sale" line. So 01113 is already 21/33 clean for inventories.

But after H1 fix_assets HK terminal lock: 01113 fix_assets was clean (Yahoo Net PPE = 72,868 = PDF). After lock, it becomes non-clean. So 01113 might drop from 21 to 20 net.

Hmm. Need to think about this. If fix_assets is locked as `provider_semantics_unverified` for HK, then:
- 00001 fix_assets: was conflict, now provider_semantics_unverified — still non-clean (same)
- 01113 fix_assets: was conflict, now provider_semantics_unverified — was non-clean, still non-clean

Wait the original replay showed 01113 fix_assets as conflict (non-clean). So locking as terminal doesn't change clean count, just changes the bucket.

Let me re-verify before assuming. After replay before H1 began (h0_verification):
- 00001 fix_assets: pdf_verification_required (non-clean)
- 01113 fix_assets: pdf_verification_required (non-clean)

After H1 lock terminal:
- Both become `yahoo_definition_unverified` or `pdf_required` — still non-clean. Net: 0 change.

So actual expected changes:
- 600519: +3 (revenue, operating_profit, SGA) → 33/33
- 00001: +1 (inventories) → 21/33  
- 01113: 0 change for fix_assets, +0 net → 21/33

Let me proceed with this plan.
