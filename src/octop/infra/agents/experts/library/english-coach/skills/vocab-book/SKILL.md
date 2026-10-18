---
name: vocab-book
description: "单词本：vocab.py build 把 Markdown 表格或 CSV 生词（单词、音标、释义、例句、来源）生成 Excel 单词本，按遗忘曲线在第 1、2、4、7、15、30 天安排复习，--merge 合并到已有单词本（不区分大小写去重，保留加入日期和已掌握标记）；due 列出今天要复习的词（漏掉一两天的也补上）；quiz 从未掌握或今天到期的词中随机出题（看英文写中文 / 看中文写英文 / 混合），导出带答案页的 Word 默写卷。整理生词、每日复习和测验时使用。"
metadata:
  octop:
    emoji: "🔤"
    label:
      zh: "单词本"
      en: "Vocabulary Book"
    summary:
      zh: "遗忘曲线复习和默写测验。"
      en: "Spaced review and printable quizzes."
---

# 单词本

> `scripts/` 和 `references/` 路径相对于本技能目录；示例：`references/example-words.md`。

## 1. 生词格式

```markdown
| 单词 | 音标 | 释义 | 例句 | 来源 |
|------|------|------|------|------|
| negotiate | /nɪˈɡəʊʃieɪt/ | v. 谈判，协商 | They negotiated a new contract. | 商务英语 |
```

- 单词和释义必填；释义选与原文语境相符的义项，标上词性。
- 例句优先用用户遇到这个词的原句；短语也可以作为一条（如 `meet the deadline`）。

## 2. 生成和合并

```bash
python scripts/vocab.py build outputs/english/生词.md -o outputs/english/单词本.xlsx
python scripts/vocab.py build outputs/english/新生词.md -o outputs/english/单词本.xlsx --merge outputs/english/单词本.xlsx
```

单词本每行有加入日期和第 1、2、4、7、15、30 天的复习日期；记住了就在"已掌握"列填"是"，之后不再复习，也不会出现在测验里。

## 3. 每日复习

```bash
python scripts/vocab.py due outputs/english/单词本.xlsx
```

列出复习日是今天的词，以及复习日在两天内被错过的词。复习方法：先看英文回忆中文和例句，再看中文拼写英文，读出声。

## 4. 默写测验

```bash
python scripts/vocab.py quiz outputs/english/单词本.xlsx -o outputs/english/默写.docx -n 20 --mode mixed [--due-only] [--seed 1]
```

`--mode`：en2zh（看英文写中文）、zh2en（看中文写英文）、mixed（混合）；`--due-only` 只从今天要复习的词中出题。答案在第 2 页，打印后可以自己批改。
