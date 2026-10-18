---
name: mistake-book
description: "错题本：把错题记录成 Markdown 表格，mistakes.py build 生成 Excel 错题本（按艾宾浩斯遗忘曲线在第 1、2、4、7、15 天排复习日期，按学科、知识点、错因统计），--merge 合并到已有错题本并去重、保留已掌握标记；mistakes.py due 列出今天该复习的题。孩子做错题、要复习或要看薄弱点时使用。"
metadata:
  octop:
    emoji: "📒"
    label:
      zh: "错题本"
      en: "Mistake Book"
    summary:
      zh: "整理错题，按遗忘曲线安排复习，找出薄弱点。"
      en: "Log mistakes, schedule spaced reviews, find weak spots."
---

# 错题本

> `scripts/` 和 `references/` 路径相对于本技能目录；示例：`references/example-mistakes.md`（虚构）。

## 1. 记录格式

错题追加到 `outputs/tutor/错题.md`：

```markdown
| 日期 | 学科 | 知识点 | 题目 | 错误答案 | 正确答案 | 错因 | 来源 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-17 | 数学 | 周长 | 长 8 宽 5 的长方形周长 | 40 | 26 | 审题不清 | 作业 |
```

- 日期、学科、知识点、题目为必填；知识点用教材里的说法，同一个知识点写法保持一致。
- 错因从这几类中选：概念不清 / 计算失误 / 审题不清 / 方法不对 / 粗心 / 不会做。
- 题目中有 `|` 时改成"或"，避免破坏表格。

## 2. 生成错题本

```bash
python scripts/mistakes.py build outputs/tutor/错题.md -o outputs/tutor/错题本.xlsx
# 之后新增错题：合并到已有错题本（同一天、同学科、同题目只记一次）
python scripts/mistakes.py build outputs/tutor/错题.md -o outputs/tutor/错题本.xlsx --merge outputs/tutor/错题本.xlsx
```

- 「错题」表：每道题的复习 1–5 日期（错题日期后第 1、2、4、7、15 天），最后一列「已掌握」。
- 「统计」表：各学科、知识点的错题数和已掌握数，各错因的次数。
- 孩子复习时能独立做对，就在「已掌握」填"是"；合并时保留这个标记。

## 3. 今天复习什么

```bash
python scripts/mistakes.py due outputs/tutor/错题本.xlsx [--today 2026-10-18]
```

列出复习日是今天的题，以及复习日在两天内被错过的题；已掌握的题不再出现。

## 4. 用统计找薄弱点

- 某个知识点错题 ≥3 道：用 `step-by-step` 重新讲概念，再用 `practice-sheets` 出专项练习。
- 「计算失误」「粗心」占比高：练习时要求每题验算，限时口算训练。
- 「审题不清」多：读题时圈出关键词和单位。
