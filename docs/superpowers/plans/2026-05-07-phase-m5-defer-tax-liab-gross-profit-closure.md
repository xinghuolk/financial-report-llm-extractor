# Phase M5: defer_tax_liab Yahoo 语义证明 + gross_profit 终态降级 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 将 `defer_tax_liab` 推到 clean present（HK 11/15 → 12/15），并将 `gross_profit` 的 HK 终态原因从模糊的 "not yet proven" 更新为明确的 "HK 利润表格式不兼容"。

**架构：** 纯数据层改动——更新三个 field_catalog JSON 文件（provider_raw_semantics_hk.json、hk_yahoo_trust_policy.json、turtle_v015_source_mapping_minimal.json），不修改 Python 逻辑代码。测试更新已有断言以反映新状态。

**技术栈：** Python 3.11, pytest, frozen JSON catalog fixtures

---

### Task 1: defer_tax_liab — provider raw semantics rule

**文件：**
- 修改: `field_catalog/provider_raw_semantics_hk.json`
- 测试: `tests/test_provider_semantics.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_provider_semantics.py` 末尾添加：

```python
def test_defer_tax_liab_yahoo_hk_is_verified_primary() -> None:
    catalog = load_provider_semantics_catalog(CATALOG)

    rule = catalog.require_rule(
        provider="yahoo",
        market="HK",
        turtle_field_id="defer_tax_liab",
        raw_field_name="Non Current Deferred Taxes Liabilities",
    )

    assert rule.allowed_as_primary is True
    assert rule.classification == "provider_semantics_sample_verified"
    assert rule.proof_origin == "sampled_pdf_policy_proof"
    assert rule.trusted_currency == "HKD"
    assert rule.trusted_unit == "raw"
    assert rule.trusted_unit_multiplier == 1
    assert "Current Deferred Taxes Liabilities" in rule.negative_examples
    assert len(rule.samples) == 2
```

- [ ] **Step 2: 运行测试确认失败**

运行: `uv run pytest tests/test_provider_semantics.py::test_defer_tax_liab_yahoo_hk_is_verified_primary -v`
预期: FAIL（rule 不存在）

- [ ] **Step 3: 在 provider_raw_semantics_hk.json 添加 rule**

在 `field_catalog/provider_raw_semantics_hk.json` 的 `rules` 数组末尾（闭合 `]` 之前）添加：

```json
    {
      "allowed_as_primary": true,
      "classification": "provider_semantics_sample_verified",
      "market": "HK",
      "negative_examples": [
        "Current Deferred Taxes Liabilities"
      ],
      "proof_origin": "sampled_pdf_policy_proof",
      "provider": "yahoo",
      "raw_field_code": null,
      "raw_field_name": "Non Current Deferred Taxes Liabilities",
      "related_only_fields": [],
      "required_proof": [],
      "samples": [
        {
          "company_id": "00001",
          "expected_provider_raw_value": "17275000000",
          "pdf_page": 136,
          "pdf_value": "17275",
          "provider_ticker": "0001.HK",
          "reported_currency": "HKD",
          "reported_unit": "million",
          "reported_unit_multiplier": 1000000,
          "statement_line": "Deferred tax liabilities",
          "statement_name": "Consolidated Statement of Financial Position"
        },
        {
          "company_id": "01113",
          "expected_provider_raw_value": "14889000000",
          "pdf_page": 71,
          "pdf_value": "14889",
          "provider_ticker": "1113.HK",
          "reported_currency": "HKD",
          "reported_unit": "million",
          "reported_unit_multiplier": 1000000,
          "statement_line": "Deferred tax liabilities",
          "statement_name": "Consolidated Statement of Financial Position"
        }
      ],
      "semantic_claim": "non-current deferred tax liabilities as reported on balance sheet",
      "trusted_currency": "HKD",
      "trusted_unit": "raw",
      "trusted_unit_multiplier": 1,
      "turtle_field_id": "defer_tax_liab"
    }
```

- [ ] **Step 4: 运行测试确认通过**

运行: `uv run pytest tests/test_provider_semantics.py -v`
预期: 全部 PASS（包括新增和已有测试）

- [ ] **Step 5: 提交**

```bash
git add field_catalog/provider_raw_semantics_hk.json tests/test_provider_semantics.py
git commit -m "feat: add defer_tax_liab yahoo hk provider semantics rule"
```

---

### Task 2: defer_tax_liab — HK Yahoo trust policy rule

**文件：**
- 修改: `field_catalog/hk_yahoo_trust_policy.json`
- 测试: `tests/test_hk_yahoo_trust_policy.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_hk_yahoo_trust_policy.py` 末尾添加：

```python
def test_hk_yahoo_trust_policy_defer_tax_liab_is_pdf_verified() -> None:
    policy = load_hk_yahoo_trust_policy(POLICY_PATH)

    assert policy.is_pdf_verified("defer_tax_liab") is True

    rule = policy.rule_for_field("defer_tax_liab")
    assert rule is not None
    assert rule.classification == "yahoo_pdf_verified"
    assert rule.allowed_yahoo_raw_fields == (
        "Non Current Deferred Taxes Liabilities",
    )

    evidence = policy.build_policy_evidence("defer_tax_liab")
    assert evidence["sample_companies"] == ["00001", "01113"]
    assert evidence["sample_count"] == 2
```

- [ ] **Step 2: 运行测试确认失败**

运行: `uv run pytest tests/test_hk_yahoo_trust_policy.py::test_hk_yahoo_trust_policy_defer_tax_liab_is_pdf_verified -v`
预期: FAIL（rule 不存在）

- [ ] **Step 3: 在 hk_yahoo_trust_policy.json 添加 rule**

在 `field_catalog/hk_yahoo_trust_policy.json` 的 `rules` 数组中，在 `gross_profit` rule 之前添加：

```json
    {
      "policy_id": "hk_yahoo_raw_hkd_pdf_verified:defer_tax_liab",
      "field_id": "defer_tax_liab",
      "classification": "yahoo_pdf_verified",
      "trusted_currency": "HKD",
      "trusted_unit": "raw",
      "trusted_unit_multiplier": 1,
      "allowed_yahoo_raw_fields": [
        "Non Current Deferred Taxes Liabilities"
      ],
      "samples": [
        {
          "company_id": "00001",
          "provider_ticker": "0001.HK",
          "report_ref": "downloads/hk_stocks/00001/annual/2025_annual_en.pdf",
          "pdf_page": 136,
          "statement_name": "Consolidated Statement of Financial Position",
          "statement_line": "Deferred tax liabilities",
          "reported_currency": "HKD",
          "reported_unit": "million",
          "pdf_value": "17275",
          "pdf_unit_multiplier": 1000000,
          "expected_yahoo_raw_value": "17275000000",
          "yahoo_raw_field": "Non Current Deferred Taxes Liabilities",
          "match_basis": "pdf_value * pdf_unit_multiplier equals expected_yahoo_raw_value"
        },
        {
          "company_id": "01113",
          "provider_ticker": "1113.HK",
          "report_ref": "downloads/hk_stocks/01113/annual/2025_annual_en.pdf",
          "pdf_page": 71,
          "statement_name": "Consolidated Statement of Financial Position",
          "statement_line": "Deferred tax liabilities",
          "reported_currency": "HKD",
          "reported_unit": "million",
          "pdf_value": "14889",
          "pdf_unit_multiplier": 1000000,
          "expected_yahoo_raw_value": "14889000000",
          "yahoo_raw_field": "Non Current Deferred Taxes Liabilities",
          "match_basis": "pdf_value * pdf_unit_multiplier equals expected_yahoo_raw_value"
        }
      ]
    },
```

- [ ] **Step 4: 更新已有 sample count 断言**

在 `test_load_hk_yahoo_trust_policy_validates_samples` 中，verified samples 数量从 10 增加到 12：

```python
    assert len(verified_samples) == 12
```

- [ ] **Step 5: 运行测试确认通过**

运行: `uv run pytest tests/test_hk_yahoo_trust_policy.py -v`
预期: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add field_catalog/hk_yahoo_trust_policy.json tests/test_hk_yahoo_trust_policy.py
git commit -m "feat: add defer_tax_liab hk yahoo trust policy rule"
```

---

### Task 3: defer_tax_liab — source mapping catalog 扩展

**文件：**
- 修改: `field_catalog/turtle_v015_source_mapping_minimal.json`
- 测试: `tests/test_source_mapping_catalog.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_source_mapping_catalog.py` 末尾添加：

```python
def test_minimal_source_mapping_defer_tax_liab_has_yahoo_alias_and_hk_policy() -> None:
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    entry = catalog.entries["defer_tax_liab"]

    assert "Non Current Deferred Taxes Liabilities" in entry.source_aliases["yahoo"]
    assert entry.verification_status == "verified"
    assert entry.source_policy is not None
    assert entry.source_policy.market_policies["HK"].primary_route == "yahoo_direct"
```

- [ ] **Step 2: 运行测试确认失败**

运行: `uv run pytest tests/test_source_mapping_catalog.py::test_minimal_source_mapping_defer_tax_liab_has_yahoo_alias_and_hk_policy -v`
预期: FAIL（没有 yahoo alias）

- [ ] **Step 3: 更新 turtle_v015_source_mapping_minimal.json**

找到 `defer_tax_liab` 条目，将其从：

```json
"defer_tax_liab": {
  "value_type": "money",
  "statement_type": "balance_sheet",
  "domain": "balance_sheet",
  "source_mode": "direct",
  "primary_route": "akshare_direct",
  "verification_status": "expected",
  "currency_requirement": "required",
  "unit_requirement": "required",
  "fallback_policy": "pdf_allowed",
  "source_aliases": {
    "akshare": [
      "DEFER_TAX_LIAB"
    ]
  },
  "pdf_aliases": [
    "deferred tax liabilities"
  ]
}
```

替换为：

```json
"defer_tax_liab": {
  "value_type": "money",
  "statement_type": "balance_sheet",
  "domain": "balance_sheet",
  "source_mode": "direct",
  "primary_route": "yahoo_direct",
  "verification_status": "verified",
  "currency_requirement": "required",
  "unit_requirement": "required",
  "fallback_policy": "pdf_allowed",
  "source_aliases": {
    "akshare": [
      "DEFER_TAX_LIAB"
    ],
    "yahoo": [
      "Non Current Deferred Taxes Liabilities"
    ]
  },
  "source_policy": {
    "semantic_concept": "reported statement line",
    "semantic_variants": {},
    "market_policies": {
      "HK": {
        "primary_route": "yahoo_direct",
        "cross_check_routes": [
          "akshare_direct"
        ],
        "on_conflict": "select_primary_require_pdf",
        "single_source_requires_pdf": false
      }
    },
    "verification_requirement": "pdf_required_on_conflict"
  },
  "pdf_aliases": [
    "deferred tax liabilities"
  ]
}
```

- [ ] **Step 4: 运行测试确认通过**

运行: `uv run pytest tests/test_source_mapping_catalog.py -v`
预期: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add field_catalog/turtle_v015_source_mapping_minimal.json tests/test_source_mapping_catalog.py
git commit -m "feat: expand defer_tax_liab source mapping with yahoo alias and hk policy"
```

---

### Task 4: gross_profit — provider raw semantics 降级

**文件：**
- 修改: `field_catalog/provider_raw_semantics_hk.json`
- 测试: `tests/test_provider_semantics.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_provider_semantics.py` 末尾添加：

```python
def test_gross_profit_yahoo_hk_has_statement_format_incompatible_reason() -> None:
    catalog = load_provider_semantics_catalog(CATALOG)

    rule = catalog.require_rule(
        provider="yahoo",
        market="HK",
        turtle_field_id="gross_profit",
        raw_field_name="Gross Profit",
    )

    assert rule.allowed_as_primary is False
    assert rule.classification == "provider_semantics_unverified"
    assert rule.proof_origin == "hk_statement_format_incompatible"


def test_gross_profit_akshare_hk_has_statement_format_incompatible_reason() -> None:
    catalog = load_provider_semantics_catalog(CATALOG)

    rule = catalog.require_rule(
        provider="akshare",
        market="HK",
        turtle_field_id="gross_profit",
        raw_field_name="毛利",
    )

    assert rule.allowed_as_primary is False
    assert rule.classification == "provider_semantics_unverified"
    assert rule.proof_origin == "hk_statement_format_incompatible"
```

- [ ] **Step 2: 运行测试确认失败**

运行: `uv run pytest tests/test_provider_semantics.py::test_gross_profit_yahoo_hk_has_statement_format_incompatible_reason -v`
预期: FAIL（proof_origin 当前是 `provider_semantics_missing`）

- [ ] **Step 3: 更新 provider_raw_semantics_hk.json 中两条 gross_profit rule**

找到 Yahoo `Gross Profit` rule（`turtle_field_id: "gross_profit"`, `provider: "yahoo"`），将 `proof_origin` 和 `required_proof` 更新：

```json
    {
      "allowed_as_primary": false,
      "classification": "provider_semantics_unverified",
      "market": "HK",
      "negative_examples": [],
      "proof_origin": "hk_statement_format_incompatible",
      "provider": "yahoo",
      "raw_field_code": null,
      "raw_field_name": "Gross Profit",
      "related_only_fields": [],
      "required_proof": [
        "HK formal income statements examined (00001 page 134, 01113 page 70) do not contain a gross profit row. Revenue-minus-COGS derivation is unreliable due to multi-line cost breakdown (00001) or bundled operating costs (01113). Proof requires either a different HK issuer with standard gross profit row, or a verified derivation formula."
      ],
      "samples": [],
      "semantic_claim": "gross profit as defined by Turtle field semantics",
      "trusted_currency": "HKD",
      "trusted_unit": "raw",
      "trusted_unit_multiplier": 1,
      "turtle_field_id": "gross_profit"
    }
```

找到 AKShare `毛利` rule（`turtle_field_id: "gross_profit"`, `provider: "akshare"`），同样更新：

```json
    {
      "allowed_as_primary": false,
      "classification": "provider_semantics_unverified",
      "market": "HK",
      "negative_examples": [],
      "proof_origin": "hk_statement_format_incompatible",
      "provider": "akshare",
      "raw_field_code": "GROSS_PROFIT",
      "raw_field_name": "毛利",
      "related_only_fields": [],
      "required_proof": [
        "HK formal income statements examined (00001 page 134, 01113 page 70) do not contain a gross profit row. AKShare HK gross profit raw field semantics cannot be verified against formal annual-report statement lines. Proof requires either a different HK issuer with standard gross profit row, or a verified derivation formula."
      ],
      "samples": [],
      "semantic_claim": "gross profit as defined by Turtle field semantics",
      "trusted_currency": "HKD",
      "trusted_unit": "raw",
      "trusted_unit_multiplier": 1,
      "turtle_field_id": "gross_profit"
    }
```

- [ ] **Step 4: 运行测试确认通过**

运行: `uv run pytest tests/test_provider_semantics.py -v`
预期: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add field_catalog/provider_raw_semantics_hk.json tests/test_provider_semantics.py
git commit -m "fix: update gross_profit hk proof origin to statement format incompatible"
```

---

### Task 5: gross_profit — trust policy reason 更新

**文件：**
- 修改: `field_catalog/hk_yahoo_trust_policy.json`
- 测试: `tests/test_hk_yahoo_trust_policy.py`

- [ ] **Step 1: 更新已有测试断言**

在 `tests/test_hk_yahoo_trust_policy.py` 的 `test_hk_yahoo_trust_policy_exposes_verified_and_unverified_classifications` 中，更新 `definition_status_reason` 和 `required_proof` 的断言：

```python
    assert gross_evidence["definition_status_reason"] == (
        "HK formal income statements do not contain a gross profit row; "
        "sampled 00001 (page 134) and 01113 (page 70) both use non-standard "
        "cost structures that prevent direct or derivation-based verification "
        "of Yahoo Gross Profit"
    )
    assert gross_evidence["required_proof"] == (
        "HK issuer with standard gross profit row, or verified "
        "revenue-minus-COGS derivation formula"
    )
```

- [ ] **Step 2: 运行测试确认失败**

运行: `uv run pytest tests/test_hk_yahoo_trust_policy.py::test_hk_yahoo_trust_policy_exposes_verified_and_unverified_classifications -v`
预期: FAIL（reason 文本不匹配）

- [ ] **Step 3: 更新 hk_yahoo_trust_policy.json 的 gross_profit rule**

找到 `gross_profit` rule，更新 `definition_status_reason` 和 `required_proof`：

```json
    {
      "policy_id": "hk_yahoo_raw_hkd_definition_unverified:gross_profit",
      "field_id": "gross_profit",
      "classification": "yahoo_definition_unverified",
      "trusted_currency": "HKD",
      "trusted_unit": "raw",
      "trusted_unit_multiplier": 1,
      "allowed_yahoo_raw_fields": [
        "Gross Profit"
      ],
      "definition_status_reason": "HK formal income statements do not contain a gross profit row; sampled 00001 (page 134) and 01113 (page 70) both use non-standard cost structures that prevent direct or derivation-based verification of Yahoo Gross Profit",
      "required_proof": "HK issuer with standard gross profit row, or verified revenue-minus-COGS derivation formula",
      "samples": []
    }
```

- [ ] **Step 4: 运行测试确认通过**

运行: `uv run pytest tests/test_hk_yahoo_trust_policy.py -v`
预期: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add field_catalog/hk_yahoo_trust_policy.json tests/test_hk_yahoo_trust_policy.py
git commit -m "fix: update gross_profit hk trust policy reason to statement format incompatible"
```

---

### Task 6: 更新 warning classification 和 closure 测试 fixtures

**文件：**
- 修改: `tests/test_warning_classification.py`
- 修改: `tests/test_hk_15_field_closure.py`

- [ ] **Step 1: 更新 warning classification 中 defer_tax_liab 的 policy fixture**

在 `tests/test_warning_classification.py` 的 `_hk_yahoo_policy()` 函数中添加 defer_tax_liab rule：

```python
def _hk_yahoo_policy() -> HkYahooTrustPolicy:
    return HkYahooTrustPolicy(
        version=1,
        market="HK",
        provider="yahoo",
        rules=(
            HkYahooTrustRule(
                policy_id="hk_yahoo_raw_hkd_pdf_verified:revenue",
                field_id="revenue",
                classification="yahoo_pdf_verified",
                trusted_currency="HKD",
                trusted_unit="raw",
                trusted_unit_multiplier=Decimal("1"),
                allowed_yahoo_raw_fields=("Total Revenue",),
            ),
            HkYahooTrustRule(
                policy_id="hk_yahoo_raw_hkd_pdf_verified:defer_tax_liab",
                field_id="defer_tax_liab",
                classification="yahoo_pdf_verified",
                trusted_currency="HKD",
                trusted_unit="raw",
                trusted_unit_multiplier=Decimal("1"),
                allowed_yahoo_raw_fields=("Non Current Deferred Taxes Liabilities",),
            ),
            HkYahooTrustRule(
                policy_id="hk_yahoo_raw_hkd_definition_unverified:gross_profit",
                field_id="gross_profit",
                classification="yahoo_definition_unverified",
                trusted_currency="HKD",
                trusted_unit="raw",
                trusted_unit_multiplier=Decimal("1"),
                allowed_yahoo_raw_fields=("Gross Profit",),
            ),
        ),
    )
```

- [ ] **Step 2: 更新 `test_warning_classification_keeps_unavailable_fields_unavailable`**

当 defer_tax_liab 有 trust policy 且 selected_source=yahoo 时，它应该变成 `yahoo_pdf_verified` 而不是 `mapping_expansion_required`。但当前测试中 defer_tax_liab 是 missing status（没有 selected_source），所以仍然走 mapping_expansion_required。

确认当前测试断言不受影响——defer_tax_liab 在该测试中是 `_item("defer_tax_liab")`（status=missing），没有 selected_source=yahoo，所以 trust policy 不会触发。断言应保持不变。

运行: `uv run pytest tests/test_warning_classification.py -v`
预期: 全部 PASS（fixture 扩展不影响现有测试逻辑）

- [ ] **Step 3: 更新 closure 测试的 policy fixture**

在 `tests/test_hk_15_field_closure.py` 的 `_policy()` 函数中添加 defer_tax_liab rule：

```python
def _policy() -> HkYahooTrustPolicy:
    return HkYahooTrustPolicy(
        version=1,
        market="HK",
        provider="yahoo",
        rules=(
            HkYahooTrustRule(
                policy_id="hk_yahoo_raw_hkd_pdf_verified:revenue",
                field_id="revenue",
                classification="yahoo_pdf_verified",
                trusted_currency="HKD",
                trusted_unit="raw",
                trusted_unit_multiplier=Decimal("1"),
                allowed_yahoo_raw_fields=("Total Revenue",),
            ),
            HkYahooTrustRule(
                policy_id="hk_yahoo_raw_hkd_pdf_verified:net_profit",
                field_id="net_profit",
                classification="yahoo_pdf_verified",
                trusted_currency="HKD",
                trusted_unit="raw",
                trusted_unit_multiplier=Decimal("1"),
                allowed_yahoo_raw_fields=("Net Income Common Stockholders",),
            ),
            HkYahooTrustRule(
                policy_id="hk_yahoo_raw_hkd_pdf_verified:defer_tax_liab",
                field_id="defer_tax_liab",
                classification="yahoo_pdf_verified",
                trusted_currency="HKD",
                trusted_unit="raw",
                trusted_unit_multiplier=Decimal("1"),
                allowed_yahoo_raw_fields=("Non Current Deferred Taxes Liabilities",),
            ),
        ),
    )
```

- [ ] **Step 4: 运行 closure 测试确认通过**

运行: `uv run pytest tests/test_hk_15_field_closure.py -v`
预期: 全部 PASS（closure 测试中 defer_tax_liab 是 missing status，trust policy 不影响其 mapping_expansion_required 分类）

- [ ] **Step 5: 提交**

```bash
git add tests/test_warning_classification.py tests/test_hk_15_field_closure.py
git commit -m "test: update warning and closure test fixtures with defer_tax_liab trust policy"
```

---

### Task 7: 全量验证 + roadmap 更新

**文件：**
- 修改: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`

- [ ] **Step 1: 运行全量测试**

运行: `uv run pytest -v`
预期: 全部 PASS（433+ passed）

- [ ] **Step 2: 运行 lint 和类型检查**

运行: `uv run ruff check . && uv run mypy src tests`
预期: 全部通过

- [ ] **Step 3: 运行 provider baseline replay 确认覆盖率提升**

运行:
```bash
uv run financial-report-llm-extractor replay-provider-baseline \
  --inventory tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz \
  --inventory-summary tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json \
  --catalog field_catalog/turtle_v015_source_mapping_minimal.json \
  --out tmp/runs/phase_m5_verification
```

预期:
- `600519` clean present: 13/15（不变）
- `00001` clean present: 11/15（从 10/15 提升）
- `01113` clean present: 11/15（从 10/15 提升）
- `defer_tax_liab` 出现在 HK clean present 列表中
- `gross_profit` 仍为 `yahoo_definition_unverified`

- [ ] **Step 4: 在 roadmap 中记录 Phase M5 状态**

在 `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md` 的 Phase M4 段落之后、Phase N 段落之前添加：

```markdown
### Phase M5: defer_tax_liab Yahoo Semantics Proof And gross_profit Terminal Closure

Status: implemented on 2026-05-07. See:

- `docs/superpowers/specs/2026-05-07-phase-m5-defer-tax-liab-gross-profit-closure.md`
- `docs/superpowers/plans/2026-05-07-phase-m5-defer-tax-liab-gross-profit-closure.md`

Goal: resolve the two remaining actionable HK 15-field gaps before Phase N expansion.

Implementation result:

- `defer_tax_liab` promoted to clean present via Yahoo `Non Current Deferred Taxes Liabilities` provider semantics proof.
  - 00001: page 136, Deferred tax liabilities = 17,275 HK$ million, Yahoo raw = 17,275,000,000 HKD.
  - 01113: page 71, Deferred tax liabilities = 14,889 $ Million, Yahoo raw = 14,889,000,000 HKD.
  - `Current Deferred Taxes Liabilities` excluded as negative context.
- `gross_profit` terminal reason updated from "not yet proven" to "HK formal income statements do not contain a gross profit row".
  - 00001 page 134: Revenue → 6 cost line items → EBIT-like subtotal, no gross profit row.
  - 01113 page 70: Group revenue → bundled operating costs → profit before tax, no gross profit row.
  - Derivation unreliable due to non-standard cost structures.
  - Terminal bucket remains `yahoo_definition_unverified` with explicit incompatibility reason.
- HK 15-field clean present: 10/15 → 11/15.
- Remaining HK non-clean fields:
  - `gross_profit`: `yahoo_definition_unverified` (HK statement format incompatible).
  - `bond_payable`, `cip`, `invest_income`: `source_unavailable`.
```

- [ ] **Step 5: 提交**

```bash
git add docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md
git commit -m "docs: record phase m5 defer_tax_liab proof and gross_profit closure"
```
