---
name: report-export
description: "把 Markdown 汇报导出为排好版的 Word：黑体标题、宋体小四正文、1.5 倍行距、带底色表头的表格、引用块和页码。用户要 Word 版、要打印、要发邮件附件时使用。"
metadata:
  octop:
    emoji: "📝"
    label:
      zh: "汇报导出 Word"
      en: "Export to Word"
    summary:
      zh: "把汇报排成可直接打印和发送的 Word。"
      en: "Export reports as print-ready Word documents."
---

# 导出 Word

> `scripts/docx_build.py` 相对于本技能目录；示例源稿：`references/example-report.md`。

```bash
python scripts/docx_build.py outputs/reports/<名称>.md -o outputs/reports/<名称>.docx --style report
```

## 源稿约定

```markdown
---
副标题: 2026 年第三季度
署名行: 运营中心 · 2026 年 10 月 17 日
---
# 运营中心季度工作汇报

## 一、总体情况
本季度营收 4.2 亿元，同比增长 **18%**……

### （一）渠道结构优化
| 渠道 | Q2 | Q3 |
|------|----|----|

- 要点列表
> 需要强调的结论（灰底引用块）
```

- `#` 标题（黑体 22 磅居中）；`##` 一级标题（黑体 16 磅）；`###` 二级（黑体 14 磅）；`####` 三级（宋体加粗）。
- 正文宋体小四、首行缩进二字、1.5 倍行距；`**加粗**` 用于关键数据。
- front matter 可选：`副标题`（标题下居中）、`署名行`（标题下居中一行）、`署名`和`日期`（文末右对齐）。
- 每个非空行是一个段落；`<!-- pagebreak -->` 单独一行分页。
- 单位有字体要求时：`--fonts '{"body": "仿宋", "title": "方正小标宋简体"}'`。
- 机关单位的正式汇报材料改用 `--style gov`（国标公文版式），或交给「政务公文专家」。

导出后告诉用户文件路径；字体按名称写入，打开文档的电脑没有对应字体时 Word/WPS 会自动替换。
