# alias_normalization 全 cohort 复验证据（PR-3 gate）

日期：2026-06-10。本文件与同目录 verdict JSON 一起构成 PR #14 flag 翻转的
可审阅证据（re-review finding 3：原证据只在 commit message + 本地 tmp）。

## 方法

1. 8-cohort（00001/01113/01810/02498/06862/09987/600519/300750）同一份
   chunks 上跑 `audit-pdf-aliases --alias-normalization off|on`，
   per-field diff `selected_chunks`（含 anchored-range 连续页修复后的
   section 语义）。
2. **全部** diff 字段（共 82 个）逐公司用 DeepSeek `extract-llm`
   flag-off vs flag-on 复验，比较 supplement 的 status/value/page。
3. 原始 verdict：`2026-06-10-alias-normalization-full-reval-verdict.json`
   （脚本 `tmp/pr3_full_reval.py`，artifacts 在 `tmp/runs/pr3_gate2/`）。

## 结果

| 公司 | diff 字段 | 丢失 present | 新增 present | 值/页变化 |
|---|---|---|---|---|
| 00001 | 15 | 0 | 2 | 0 |
| 01113 | 8 | 0 | 0 | 1 |
| 01810 | 7 | 0 | 1 | 2 |
| 02498 | 13 | 0 | 3 | 2 |
| 06862 | 10 | 0 | 3 | 2 |
| 09987 | 11 | 0 | 4 | 2 |
| 600519 | 9 | 0 | 0 | 1 |
| 300750 | 9 | 0 | 0 | 5 |
| **合计** | **82** | **0** | **13** | **15** |

## 变化裁决

- 值/页变化中 9 个为同值换更优证据页（CN 摘要页 → 报表/附注页），
  2 个文本更完整，2 个格式等价。
- 仅 2 个真实值分歧，均已 PDF 裁决：
  - **06862 `minority_int`**：PDF 原文 `(16,298)`（括号负数）。flag-off
    返回 +16298（与其自身 reasoning 矛盾）；flag-on 返回 -16298 **正确**
    —— flag-on 修复了一个符号错误。
  - **01113 `invest_income`**：flag-on 对利润表两条投资收益行做出带透明
    推理的聚合（936+1,905=2,841）vs flag-off 单行 1,905；解释差异非回归，
    该字段属 B-tier 单源 LLM，本就标记 review。

## 验收口径

全 diff 字段全覆盖 + 0 丢失 present + 0 值回归 → flag 保留开启。
