# 别名生命周期三件套（Alias Lifecycle）设计

日期：2026-06-10（rev 2，经双 subagent review 修订）
状态：已与 owner 确认方案 A；rev 2 吸收可行性 + 方向两路 review 的修正
背景文档：`docs/company-analysis/00001-missing-fields-source-exploration-20260610.md`
Review 记录：可行性 review（8 findings，2 MAJOR）+ 方向 review（11 findings，1 DIRECTION-CHANGE）均已合入本版

## 问题

新公司 PDF 接入时的三个连锁痛点（owner 确认全部命中）：

1. **匹配太脆**：`pdf_aliases` 是精确 substring（lowercase + 空白归一化）。
   00001 实测 5 个字段因 "of **the** trade"（多冠词）、"related **parties**"
   （复数）、"one-time" vs "one-off"（连字符/同义）这类琐碎差异 retrieval 全
   miss。别名靠枚举加不完。
2. **跑完才知道 miss**：发现缺口需要一次完整（付费 LLM）run，定位原因靠人肉
   `pdftotext + grep`（现行 workflow Step 0/5 即如此）。
3. **命中知识不沉淀**：哪家公司哪个措辞在哪页命中过，散落在 run 目录，无法
   反哺 catalog 演进，也无法识别死别名。

另有 review 确认的第 4 类失败模式（00001 §② 实证 4/9 可修字段）：
4. **错页命中**：别名精确命中了 MD&A 散文而非报表行（`taxes paid` 命中 p56
   散文，真实行是 p141 "Tax paid"）——单纯三态 hit/miss 分类无法暴露。

## 方案总览

```
组件1 alias_matching.py（归一化纯函数）
        │ 被调用
组件2 audit-pdf-aliases (CLI) ── 必须调用生产版 select_chunks /
        │                        select_statement_section_chunks 做选块仿真，
        │                        别名级诊断只是其上的附加层
        v 输出 alias_audit.json
组件3 index-alias-matches (CLI) ── 台账（derived view）+ 治理信号
PR 顺序：PR-1（组件1+2）→ PR-3（接入 retrieval，gated）→ PR-2（组件3，缩水版）
```

交付顺序调整理由（review #8）：覆盖率收益集中在 PR-1 + PR-3；台账治理信号在
n=8 公司时低频，降级为最后交付且范围缩水。

## 组件 1：归一化匹配器

**位置**：`src/financial_report_llm_extractor/structured_sources/alias_matching.py`

**接口**（纯函数，零外部依赖）：

```python
@dataclass(frozen=True)
class AliasMatch:
    alias: str
    kind: Literal["exact", "normalized"]
    matched_text: str   # token 对齐反查的原文窗口（禁止 string-offset 反查）
    count: int

def match_alias(alias: str, text: str) -> AliasMatch | None: ...
def normalize_phrase(s: str) -> str: ...
```

**归一化规则（按序，对 alias 与 text 两侧对称应用）**：
1. lowercase
2. 空白折叠（与 `llm_extraction_runner._normalize_whitespace` 共享同一实现，
   消除第三套匹配逻辑；`retrieval.py` 的 stage-3 `_matched_aliases` 显式
   **不在本设计范围**，后续单独收敛）
3. 撇号折叠：`'` / `'` 移除（`auditor's` → `auditors`）
4. 连字符折叠：`-` → 空格
5. 复数折叠（token 级）：尾 `ies`→`y`；其余尾 `s` 剥离
6. 停用词折叠：移除 token 级 `the/a/an`
   （**顺序注意**：复数折叠在停用词之前，否则 `as`→`a` 残留与已删除的冠词
   `a` 不对称——review 可行性 #7 的 ordering bug）

**exact 判定**：现行逻辑（规则 1-2 后 substring）。
**normalized 判定**：规则 3-6 全部应用后 substring 命中且 exact 未命中。

**已知风险（进 PR-3 gate fixture）**：规则 5 引入跨字段碰撞
`inventories`→`inventory` ⊂ `change in inventories` 归一化结果（BS 别名误计
CF chunk 分数）。软性失败（影响排序非过滤），由 PR-3 的 section-aware 排序
键缓解 + gate fixture 显式断言。

**中文别名**：规则 3-6 对无空格 CJK 串是 no-op，直通安全（review 双方一致
确认）；单测固化"中文别名直通"。

**不做**：编辑距离、embedding（YAGNI）。注意本规则集**不**覆盖所有所有格变
体（`auditors' report` 类由规则 3 部分覆盖），不宣称穷尽。

## 组件 2：CLI `audit-pdf-aliases`

```bash
financial-report-llm-extractor audit-pdf-aliases \
  --pdf <path> \
  [--catalog field_catalog/turtle_v015_source_mapping_minimal.json] \
  [--priorities P0,P1,P2,P3,P4] \
  [--emit-catalog-patch] \
  --out <dir>
```

**核心语义（review 方向 #1，DIRECTION-CHANGE 已采纳）**：审计的第一公民输出
是**选块仿真**——对每个字段调用生产版 `derive_targets` + `select_chunks`
（+ `select_statement_section_chunks` 兜底路径），报告"这个字段在这本 PDF 上
真实会送给 LLM 的 chunk 集合（chunk_ids + pages）"。别名级 exact/normalized
诊断是其上的附加层。禁止重实现选块逻辑。

**行为**：
- 复用既有 ingestion + chunking（in-process；`pdftotext` 不在 PATH → 退出码 2；
  `--out` 下已有 `chunks.jsonl` 时直接复用，同 extract-llm 模式）。
- 别名扫描**只针对 `record_type == "block"` 记录**（chunks.jsonl 同一文本有
  block/page_text/statement_table 三重表示，否则计数虚高 2-3 倍且
  statement_table 无单页页码——review 可行性 #2）。
- 每个命中页用 `_STATEMENT_SECTION_ANCHORS`（刚 merge 的双语锚点）判定
  `in_statement_section: bool`。
- 同时审计锚点本身：每个 statement_type 必须在本 PDF 解析出 ≥1 页，否则报
  warning（absence_means_zero 兜底在该 PDF 上静默失效）。
- `--emit-catalog-patch`：把 suggested_aliases 输出为可人工 review 的 catalog
  JSON diff（不直接写 catalog——与项目 review-gated 惯例一致）。

**字段四态**：

| 状态 | 含义 |
|---|---|
| `exact_hit` | ≥1 别名精确命中且 ≥1 命中页在对应报表 section 内 |
| `prose_only_hit` | 有精确命中但全部落在 section 外（错页——`c_paid_for_taxes` 模式） |
| `normalized_only_hit` | 仅归一化命中；附 PDF 原文措辞作 suggested_aliases |
| `no_hit` | 全 miss（大概率 issuer 不披露） |

**schema**（`alias_audit.json`，v1）：

```json
{
  "schema_version": "alias_audit_v1",
  "pdf_path": "...", "catalog_version": "...", "generated_at": "...",
  "section_anchor_coverage": {"cash_flow": [141, 192], "balance_sheet": [136], "...": []},
  "fields": {
    "<field_id>": {
      "status": "exact_hit | prose_only_hit | normalized_only_hit | no_hit",
      "selected_chunks": [{"chunk_id": "...", "page": 141, "via": "alias_top_k|broad_keyword|section_fallback"}],
      "hits": [{"alias": "...", "kind": "exact|normalized", "page": 229,
                 "count": 2, "in_statement_section": true, "matched_text": "..."}],
      "suggested_aliases": ["ageing analysis of the trade receivables"]
    }
  },
  "summary": {"exact_hit": 38, "prose_only_hit": 3, "normalized_only_hit": 5, "no_hit": 22}
}
```

**退出码**：0 正常；2 输入/环境失败（含 pdftotext 缺失）。

## PR-3：归一化接入 select_chunks（gated，先于组件 3 交付）

- `alias_top_k` 路径排序键改为 **`(exact_score, in_statement_section,
  normalized_score)`**（review 方向 #3：复数折叠恰好抹掉"Tax paid"行 vs
  "taxes paid"散文的区分，必须 section-aware 否则散文 chunk 挤占 top-8）。
- `broad_keyword` 路径（<3 别名的 19 个字段）不改动——归一化对 token 匹配无
  增益，显式 out of scope。
- **开关 plumbing（review 双方 #6a/#10）**：catalog 顶层
  `"alias_normalization": true` → `SourceMappingCatalog` 新增 frozen 字段 →
  `derive_targets` 把它 stamp 进 `LlmExtractionTarget`（新字段）→
  `select_chunks` 唯一消费点。N0 `test_catalog_consistency` 增加断言：flag
  值与 rollout 状态一致。
- **与 absence_means_zero 兜底的交互**：normalized 命中会使 `selected` 非空、
  preempt section 兜底——gate fixture 必须含 `repurchase_of_stock` 在"无该行
  PDF"上的行为断言（兜底仍可达或 normalized 选块质量不低于 section 兜底）。
- **Gate（review 双方一致，原 gate 是恒真式已废弃）**：
  1. 8-cohort（600519/300750/00001/01113/01810/02498/06862/09987）基于既有
     chunks fixture 跑**选块集合 diff**（确定性、零成本）：输出每字段
     selected_chunks 变化清单；
  2. 仅对发生 diff 的字段做付费 LLM 复验（DeepSeek），对比
     `fields_present` + 值；无新增 FP / 无丢失既有 present 才默认开启；
  3. `inventories` 跨字段碰撞 fixture 断言。

## 组件 3：CLI `index-alias-matches` + 台账（缩水版，最后交付）

```bash
financial-report-llm-extractor index-alias-matches \
  --runs tmp/runs --audits <dirs> \
  [--ledger field_catalog/alias_match_ledger.json] \
  [--emit-promotion-review]
```

**schema 修正（review 双方 #3/#5：原设计不可构造）**：
- `llm_evidence_supplement.json` **无别名归属**——LLM 命中挂在字段级保留键
  `"_llm"` 下（alias=null），携带 page/statement_line；不伪造别名归属。
- company/year **必须 join 同 run 目录的 `evaluation.json`**（同 R1 indexer
  模式）；无 evaluation.json 的 supplement-only run 目录跳过并 stderr 警告。

```json
{
  "schema_version": "alias_ledger_v1",
  "note": "derived view; regenerable from run artifacts + audits; rm + re-index is safe",
  "fields": {
    "<field_id>": {
      "<alias>": [{"company": "00001", "year": 2025, "page": 229,
                    "match_kind": "exact|normalized", "market": "HK",
                    "catalog_version": "..."}],
      "_llm": [{"company": "00001", "year": 2025, "page": 141, "market": "HK"}]
    }
  }
}
```

**定位（review 方向 #7）**：derived view，可随时 `rm` + 重建（同 R1 DB 哲学）；
不进 N0 consistency gate 语义；不含 `indexed_from` 之类 ephemeral 路径。
**打包**：`pyproject.toml` force-include `field_catalog/` 需排除
`alias_match_ledger.json`（避免 run 历史进 1a client wheel——review 可行性 #4）。

**治理信号（全部 market-scoped——中英别名混在一个 list，跨市场聚合会把中文
半区全部误报为死别名，review 方向 #6）**：
1. 死别名：同 market 内任何公司零命中 → 候选清理
2. 转正候选：normalized 措辞同 market ≥2 家命中 → 候选进 pdf_aliases
3. terminal 候选：同 market ≥N 家 no_hit → 候选标 not_applicable（对应 00001
   探索文档第二批第 6 项）

**Promotion 通道（review 方向 #6）**：`--emit-promotion-review` 输出与既有
`review-source-mapping-expansion` 相同格式的 review artifact——别名转正与
provider 字段扩展走**同一个 review gate**，不另设 markdown 旁路。

## 工作流文档适配（`docs/new-company-analysis-workflow.md`）

| 位置 | 改动 |
|---|---|
| TL;DR | Step 1 与 Step 2 之间插入 Step 1.5：`audit-pdf-aliases` |
| 新 Step 1.5 | 跑审计 → 按 prose_only/normalized_only 报告先补 catalog（用 `--emit-catalog-patch` 的 diff 人工 review）→ 再进付费 LLM 评估 |
| Step 5 | 人肉 `pdftotext + grep` 改为引用审计报告（provider 冲突对照仍人工） |
| Step 6 | 增加：run 后 `index-alias-matches`；catalog 加别名引用台账证据 |
| 常见陷阱 | 增加"不跑 Step 1.5 直接 LLM 评估 → 浪费一次付费 run" |

**Onboarding 收益量化（review 方向 #11）**：现状 = 2 次付费 run + ~21 字段人
肉 grep 根因分析；新流程 = 1 次免费审计预分类（class ①⑤ 共 13/21 提前定性）
+ 1 次付费 run + 读一份报告。

## 测试策略

- 组件 1：规则逐条/组合单测；中文直通；`inventories` 碰撞案例；token 对齐
  matched_text 反查。
- 组件 2：复用 `tests/fixtures/pdf_chunks/00001_2025_chunks.jsonl` 断言已知
  四态（`receivables_aging`→normalized_only 且 suggested 含 "the"；
  `c_paid_for_taxes`→prose_only_hit；`rd_exp`→no_hit）；record_type=block
  过滤断言；选块仿真与 `select_chunks` 直调结果一致性断言。
- PR-3：8-cohort 选块 diff 基线 fixture；absence_means_zero preempt 断言；
  N0 flag 一致性断言。
- 组件 3：台账 upsert 幂等；market-scoped 信号断言；promotion-review artifact
  格式兼容断言。

## 不在范围（显式）

- LLM 辅助别名发现（方案 C）
- 模糊/embedding 匹配
- `retrieval.py` stage-3 `_matched_aliases` 的收敛（声明 out of scope）
- provider 侧别名治理（已有工具）
- Step 0 币种检测自动化

## 交付划分（rev 2 顺序）

| PR | 内容 | 验收 |
|---|---|---|
| PR-1 | 组件 1 + 2（含选块仿真、四态、anchor 审计、--emit-catalog-patch） | 00001 审计复现：5 normalized_only + `c_paid_for_taxes` prose_only + 已知 no_hit 集合 |
| PR-3 | select_chunks 接入（catalog flag + section-aware 排序 + 三重 gate） | 8-cohort 选块 diff 报告 + diff 字段付费复验通过 + 全套 pytest/ruff/mypy |
| PR-2 | 组件 3 缩水版（field 级 `_llm`、market-scoped 信号、promotion-review 出口） | 台账幂等重跑无 diff；信号断言；wheel 排除验证 |
