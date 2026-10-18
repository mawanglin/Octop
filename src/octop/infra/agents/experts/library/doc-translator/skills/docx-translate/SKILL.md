---
name: docx-translate
description: "Word 保留格式翻译：docx_segments.py extract 把正文、表格、文本框、页眉页脚的段落抽成 JSON 片段（特殊格式文字用 <n>…</n> 标签，重复段落标 dup_of），翻译后 fill 按译文语序重建文字并保留加粗、颜色、样式、编号、表格和图片，check 检查漏译、原文数字缺失、标签不一致、术语表未遵守和同一原文多种译法。翻译 Word 文档时使用。"
metadata:
  octop:
    emoji: "🌐"
    label:
      zh: "Word 文档翻译"
      en: "Word Translation"
    summary:
      zh: "抽取—翻译—回填，保留原文排版，自动自查。"
      en: "Extract, translate and refill Word files with layout intact."
---

# Word 文档翻译

> `scripts/` 和 `references/` 路径相对于本技能目录；术语表示例：`references/example-glossary.csv`。

## 1. 抽取

```bash
python scripts/docx_segments.py extract inbound/原文.docx -o outputs/translate/段落.json
```

每个片段：

```json
{"id": "p2", "where": "正文", "text": "本季度<2>数据中心</2>可用率达到 99.95%。", "translation": ""}
```

- `where`：正文 / 正文·表格 / 正文·文本框 / 页眉 / 页脚。
- `<n>…</n>`：这段文字的格式和段落主体不同（加粗、斜体、颜色、字号等）。译文中保留同号标签包住对应的译文，语序可以调整：
  `"This quarter, <2>data center</2> availability reached 99.95%."`
- `dup_of`：与前面某个片段完全相同（如重复的表头），回填时自动使用那个片段的译文，不用填。
- 只含数字和符号的段落不抽取，保持原样。

## 2. 翻译

- 按顺序分批填写 `translation`，保持 JSON 格式有效（引号转义）。
- 标题、表头、页眉页脚简短一致；同一术语按术语表翻译。
- 段落内的换行、制表符不需要处理，回填时由原格式保留。

## 3. 自查

```bash
python scripts/docx_segments.py check outputs/translate/段落.json --glossary outputs/translate/术语表.csv
```

检查：未翻译片段、原文中的数字在译文中没有出现（如金额、日期、编号）、格式标签与原文不一致、术语表中的原文出现但译文没有使用约定译法、同一原文出现多种译法。确认无误的提示（如数字按目标语言习惯改写了格式）可以忽略，但要在交付说明中写明。

## 4. 回填

```bash
python scripts/docx_segments.py fill inbound/原文.docx outputs/translate/段落.json -o outputs/translate/译文.docx
```

- 段落样式、编号、表格结构、图片、页眉页脚原样保留，只替换文字。
- 必须使用 extract 时的同一份原文；原文改过会报错，需要重新抽取。
- 未翻译的片段保留原文并列出。

## 5. 限制

脚注、尾注、批注、修订、图片和图表里的文字、SmartArt、域代码（目录、交叉引用）不在处理范围内。目录需要在 Word 中右键"更新域"。中译英后篇幅通常变长，提醒用户检查表格和分页。
