# 别名生命周期三件套（Alias Lifecycle）设计

日期：2026-06-10
状态：已与 owner 确认（方案 A，三阶段）
背景文档：`docs/company-analysis/00001-missing-fields-source-exploration-20260610.md`

## 问题

新公司 PDF 接入时的三个连锁痛点（owner 确认全部命中）：

1. **匹配太脆**：`pdf_aliases` 是精确 substring（lowercase + 空白归一化）。
   00001 实测 5 个字段因 "of **the** trade"（多冠词）、"related **parties**"
   （复数）、"one-time" vs "one-off"（连字符/同义）这类琐碎差异 retrieval 全
   miss（LLM reasoning 显示 `no chunks matched aliases`）。别名靠枚举加不完。
2. **跑完才知道 miss**：发现缺口需要一次完整（付费 LLM）run，定位原因靠人肉
   `pdftotext + grep`（现行 workflow Step 0/5 即如此）。
3. **命中知识不沉淀**：哪家公司哪个措辞在哪页命中过，只散落在 run 目录和人
   的记忆里，无法反哺 catalog 演进，也无法识别死别名。

## 方案总览

三个组件按依赖顺序交付，每个独立可用；归一化匹配第一阶段**只用于诊断**，
经 cohort 回归验证后才接入真实 retrieval。

```
组件1 alias_matching.py ──被调用──> 组件2 audit-pdf-aliases (CLI)
                                        │ 输出 alias_audit.json
                                        v
                          组件3 index-alias-matches (CLI)
                            ├─ 读 alias_audit.json（审计命中）
                            ├─ 读 tmp/runs/*/llm_evidence_supplement.json（LLM 实际命中）
                            └─ 写 field_catalog/alias_match_ledger.json + .md
PR-3（gated）：组件1 接入 select_chunks（flag 控制）
```

## 组件 1：归一化匹配器

**位置**：`src/financial_report_llm_extractor/structured_sources/alias_matching.py`（新模块）

**接口**（纯函数，零外部依赖）：

```python
@dataclass(frozen=True)
class AliasMatch:
    alias: str
    kind: Literal["exact", "normalized"]
    matched_text: str       # chunk 内命中的原文片段（normalized 时为反查回的原文）
    count: int

def match_alias(alias: str, text: str) -> AliasMatch | None: ...
def normalize_phrase(s: str) -> str: ...
```

**归一化规则（按序应用）**：
1. lowercase
2. 空白折叠（语义同现有 `llm_extraction_runner._normalize_whitespace`）
3. 连字符折叠：`-` → 空格（`one-time` → `one time`）
4. 停用词折叠：移除 token 级 `the/a/an`（`ageing analysis of the trade
   receivables` → `ageing analysis of trade receivables`）
5. 简单复数折叠：token 级两条规则——尾 `ies`→`y`（`parties`→`party`）、
   其余尾 `s` 剥离（`payments`→`payment`）；alias 与 text 两侧同时归一后比较，
   不引入词形库

**exact 判定**：现行逻辑（lowercase + 空白折叠后 substring）。
**normalized 判定**：规则 3-5 全部应用后 substring 命中且 exact 未命中。
matched_text 通过 token 对齐反查原文窗口，供审计报告展示"PDF 实际措辞"。

**不做**：模糊编辑距离、embedding 相似度（YAGNI；今天实测的 miss 全部被
规则 3-5 覆盖）。

## 组件 2：CLI `audit-pdf-aliases`

```bash
financial-report-llm-extractor audit-pdf-aliases \
  --pdf <path> \
  [--catalog field_catalog/turtle_v015_source_mapping_minimal.json] \
  [--priorities P0,P1,P2,P3,P4] \
  --out <dir>
```

**行为**：复用既有 ingestion + chunking 模块把 PDF 转 chunks（零 LLM 成本，
秒级），对 catalog 内全部 mapped 字段的 `pdf_aliases` 逐别名跑组件 1。

**输出** `alias_audit.json` + `alias_audit.md`，每字段归入三态：

| 状态 | 含义 | 报告内容 |
|---|---|---|
| `exact_hit` | ≥1 别名精确命中 | 命中别名、页码、次数 |
| `normalized_only_hit` | 仅归一化命中 | 命中别名、页码、**PDF 原文措辞（候选新别名）** |
| `no_hit` | 全部 miss | 别名清单（大概率 issuer 不披露或需新措辞） |

**退出码**：0 正常；2 输入/解析失败。审计是诊断工具，no_hit 多不算失败。

**schema**（`alias_audit.json`）：

```json
{
  "schema_version": "alias_audit_v1",
  "pdf_path": "...", "catalog_version": "...", "generated_at": "...",
  "fields": {
    "<field_id>": {
      "status": "exact_hit | normalized_only_hit | no_hit",
      "hits": [{"alias": "...", "kind": "exact|normalized",
                 "page": 229, "count": 2, "matched_text": "..."}],
      "suggested_aliases": ["ageing analysis of the trade receivables"]
    }
  },
  "summary": {"exact_hit": 41, "normalized_only_hit": 5, "no_hit": 22}
}
```

## 组件 3：CLI `index-alias-matches` + 台账

```bash
financial-report-llm-extractor index-alias-matches \
  --runs tmp/runs \
  [--ledger field_catalog/alias_match_ledger.json]
```

**行为**：扫描 run 目录下的 `llm_evidence_supplement.json`（status=present 的
字段：company/year/page 即 LLM 实际命中证据）与 `alias_audit.json`（exact /
normalized 命中），聚合 upsert 进台账。幂等：同 (company, year, field, alias)
重复索引不产生重复条目。

**台账结构**（`field_catalog/alias_match_ledger.json`，进 git）：

```json
{
  "schema_version": "alias_ledger_v1",
  "fields": {
    "<field_id>": {
      "<alias>": [
        {"company": "00001", "year": 2025, "page": 229,
         "match_kind": "exact|normalized|llm_present", "indexed_from": "<run_dir>"}
      ]
    }
  }
}
```

伴随生成 `alias_match_ledger.md` 视图，突出两个治理信号：
- **死别名**：catalog 中存在但台账零命中 → 候选清理
- **转正候选**：normalized 措辞在 ≥2 家公司命中 → 候选加入 `pdf_aliases`

**进 git 理由**（owner 已确认）：台账指导 catalog 演进，性质同 trust policy
的 verified samples；体积可控（数百 KB 级）。

## PR-3（gated）：归一化接入 select_chunks

- `select_chunks` 的 `alias_top_k` 路径在 exact 计分为 0 时追加 normalized 计
  分（exact 命中优先级高于 normalized，排序键 `(exact_score, normalized_score)`）。
- 开关：catalog 顶层布尔字段 `"alias_normalization": true`（随 catalog 版本
  固化，测试可断言；不用 CLI flag）。
- **Gate**：8 家既有 cohort（600519/300750/00001/01113/01810/02498/06862/09987）
  重跑审计，全部既有 exact_hit 字段集合不变，且 LLM supplement 回归（与
  pinned merge 测试兼容）通过后才默认开启。

## 工作流文档适配（`docs/new-company-analysis-workflow.md`）

| 位置 | 改动 |
|---|---|
| TL;DR | Step 1 与 Step 2 之间插入 Step 1.5：`audit-pdf-aliases` |
| 新 Step 1.5 | 跑审计 → 按 `normalized_only_hit` 的 suggested_aliases 先补 catalog 明显缺口 → 再进付费 LLM 评估 |
| Step 5 | 人肉 `pdftotext + grep` 改为引用审计报告的 normalized_only/no_hit 清单（provider 冲突对照仍人工） |
| Step 6 | 增加：run 后跑 `index-alias-matches`；catalog 加别名时引用台账证据 |
| 常见陷阱 | 增加"不跑 Step 1.5 直接 LLM 评估 → 浪费一次付费 run 才发现别名缺口" |

## 测试策略

- 组件 1：纯函数单测（规则逐条 + 组合 + 中文别名直通 + 不误归一数字/单位）。
- 组件 2：fixture PDF chunks（复用 `tests/fixtures/pdf_chunks/00001_2025_chunks.jsonl`）
  跑审计，断言已知三态字段（如 `receivables_aging` 必须 normalized_only_hit 且
  suggested 含 "the"；`rd_exp` 必须 no_hit）。
- 组件 3：tmp run 目录 fixture → 台账 upsert 幂等性 + 治理信号断言。
- PR-3：8-cohort 审计基线 fixture 对比（exact_hit 集合冻结）。

## 不在范围（显式）

- LLM 辅助别名发现（方案 C）— 留作后续，复用 review-gated expansion 模式。
- 模糊/embedding 匹配 — YAGNI。
- provider 侧别名治理 — 已有 `discover-provider-fields` / `review-source-mapping-expansion`。
- Step 0 币种检测自动化 — 与别名无关，单独立项。

## 交付划分

| PR | 内容 | 验收 |
|---|---|---|
| PR-1 | 组件 1 + 2 + 单测/fixture 测试 | 00001 审计报告复现 5 个 normalized_only + 已知 no_hit 集合 |
| PR-2 | 组件 3 + 工作流文档更新 | 台账含 7-cohort 既有命中；幂等重跑无 diff |
| PR-3 | select_chunks 接入（flag + gate） | cohort exact_hit 集合不变 + 全套 pytest/ruff/mypy |
