---
name: ppt-edit
description: "读取和修改已有 .pptx：提取逐页文字和备注、检查溢出，替换文字（保留原格式）、删除/移动/复制页面、写讲稿备注。用户上传 PPT 要求总结、改字、调页序、加讲稿，或基于旧 PPT 做新版本时使用。"
metadata:
  octop:
    emoji: "✏️"
    label:
      zh: "PPT 修改"
      en: "Deck Editing"
    summary:
      zh: "读取已有 PPT，替换文字、调整页面顺序、补讲稿备注。"
      en: "Read existing decks, replace text, reorder slides, and add speaker notes."
---

# 读取与修改已有 PPT

> `scripts/edit_deck.py` 相对于本技能目录；读取用的 `inspect_deck.py` 在 `ppt-build` 技能的 `scripts/` 下（按技能目录给出的真实路径调用）。

## 1. 先读

```bash
python {ppt-build 目录}/scripts/inspect_deck.py inbound/原文件.pptx          # 逐页大纲 + 问题清单
python {ppt-build 目录}/scripts/inspect_deck.py inbound/原文件.pptx --json   # 结构化结果
```

页码以这里的输出为准（从 1 开始）。

## 2. 再改（默认另存为新文件）

```bash
python scripts/edit_deck.py in.pptx -o out.pptx replace --find "2025" --with "2026" [--slide 3]
python scripts/edit_deck.py in.pptx -o out.pptx delete --slides 4,7
python scripts/edit_deck.py in.pptx -o out.pptx move --slide 6 --to 2
python scripts/edit_deck.py in.pptx -o out.pptx duplicate --slide 3
python scripts/edit_deck.py in.pptx -o out.pptx notes --slide 2 --text "这一页先讲结论……"
```

- 多步修改时，第一步 `-o` 写到 `outputs/ppt/<名称>-修订.pptx`，之后对该文件用 `--in-place`。
- **不要**用 `--in-place` 改用户原文件，除非用户明确要求覆盖。
- `replace` 找不到文字时不会保存（退出码 1）；文字跨多段格式时会合并成第一段的格式，改完用 `inspect_deck.py` 复查。
- 删除、移动页面后，原 PPT 里写死的页码文字不会自动更新，需要时用 `replace` 修正或提醒用户。
- `duplicate` 复制出的图表与原页共享同一份数据，修改其中一个会影响另一个；需要不同数据时用 `ppt-build` 重建该页。

## 3. 何时改用重建

以下情况用 `inspect_deck.py --json` 提取内容 → 按 `ppt-outline`/`ppt-build` 重新生成，比逐处修改更可靠：

- 要换整体风格、配色或版式；
- 超过一半页面需要重写；
- 原文件排版混乱、溢出很多。

重建前告诉用户：新文件会使用内置主题，原有母版和自定义动画不会保留。

## 4. 只读类任务

总结、提炼要点、生成讲稿、转写成文档时，只读取不修改；引用原文时标注页码。
