---
name: plan-export
description: "方案导出：docx_build.py 把 Markdown 方案导出为排好版的 Word（工作汇报版式或国标公文版式）；budget_xlsx.py 把预算明细生成带公式的 Excel（分类小计、管理费、预备费、税费、总计）。方案定稿后需要 Word、预算表时使用。"
metadata:
  octop:
    emoji: "📦"
    label:
      zh: "方案导出"
      en: "Plan Export"
    summary:
      zh: "导出 Word 方案和带公式的预算表。"
      en: "Export Word plans and formula-driven budgets."
---

# 方案导出

> `scripts/` 和 `references/` 路径相对于本技能目录；预算示例：`references/example-budget.md`。

## 1. 方案 Word

```bash
python scripts/docx_build.py outputs/plans/<名称>-方案.md -o outputs/plans/<名称>-方案.docx --style report
```

- `#` 方案标题，`##` 一级章节，`###` 二级，表格用 Markdown 表格；`<!-- pagebreak -->` 分页（例如把预算附件放到新的一页）。
- front matter 可选：`副标题`、`署名行`（如"策划部 · 2026 年 10 月"）、`署名` 和 `日期`（文末右对齐）。
- 政府部门的工作方案用 `--style gov`（国标公文版式）。

## 2. 预算表 Excel

预算明细写成 Markdown 表格：

```markdown
---
项目: 2026 年度年会预算
币种: 元
预备费率: 5%
税率: 6%
---
| 类别 | 项目 | 单位 | 单价 | 数量 | 天数 | 备注 |
|------|------|------|------|------|------|------|
| 场地 | 宴会厅租赁 | 场 | 30000 | 1 | 1 | 含基础音响 |
```

```bash
python scripts/budget_xlsx.py outputs/plans/<名称>-预算.md -o outputs/plans/<名称>-预算.xlsx
```

- 按类别分组，每组小计；管理费、预备费、税费按 front matter 的费率计算，全部是 Excel 公式，用户修改单价或数量后自动重算。
- "天数"列可以省略（按 1 计算）。
- 没有报价的单价在备注中标"参考价，需询价"。

交付时在方案正文里写明预算总额和口径（是否含税、是否含预备费），与 Excel 的总计一致。
