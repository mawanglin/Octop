---
name: exam-builder
description: "题库与组卷：题库 CSV（题型、题目、选项、答案、分值、知识点、难度、解析）支持单选、多选、判断、填空、简答；exam.py check 检查缺字段、答案不在选项内、单选多答案、多选单答案、填空没有空、重复题目，并统计各题型和知识点数量；paper 按题型数量随机抽题（--topic 限定知识点），打乱选项顺序并同步调整答案（“以上都对”类选项保持原位），导出带姓名栏、分题型计分的 Word 试卷和答案页，--seed 可复现、换种子出 A/B 卷。建题库、出考试卷时使用。"
metadata:
  octop:
    emoji: "📝"
    label:
      zh: "题库与组卷"
      en: "Exam Builder"
    summary:
      zh: "检查题库，随机组卷，导出试卷和答案。"
      en: "Validate a bank, draw papers, export with answers."
---

# 题库与组卷

> `scripts/` 和 `references/` 路径相对于本技能目录；示例题库：`references/example-bank.csv`（安全生产培训）。

## 1. 题库格式

```csv
题型,题目,选项,答案,分值,知识点,难度,解析
单选,发现火灾时，首先应拨打的报警电话是,110|119|120|122,B,,消防,易,
多选,下列属于个人防护用品的有,安全帽|防护眼镜|绝缘手套|灭火器,ABC,,防护,易,
判断,可以用水扑灭所有类型的火灾。,,错,,消防,易,电气火灾和油类火灾不能用水
填空,灭火的基本方法有冷却法、窒息法、隔离法和 ___ 法。,,抑制,,消防,中,
```

- 选项用 `|` 分隔，A、B 前缀可写可不写；判断题答案写 对 / 错。
- 分值留空时：单选 2、多选 3、判断 1、填空 2、简答 10。
- 出题要点：每个学习目标至少 3 道题；题干完整、没有否定中的否定；干扰项看起来合理；答案位置分布均匀（组卷时会打乱）。

## 2. 检查

```bash
python scripts/exam.py check outputs/training/题库.csv
```

## 3. 组卷

```bash
python scripts/exam.py paper outputs/training/题库.csv -o outputs/training/试卷A.docx --single 10 --multi 5 --judge 10 --blank 2 --short 1 --title "安全生产培训考试" --seed 1
python scripts/exam.py paper outputs/training/题库.csv -o outputs/training/试卷B.docx --single 10 --multi 5 --judge 10 --seed 2
```

- 每种题型从题库随机抽取，`--topic 消防,用电` 只从指定知识点抽题；题库数量不够时会报错并说明差几道。
- 选项顺序随机打乱、答案同步调整（`--no-shuffle` 关闭）；含"以上都对 / 都不对"的题目保持原顺序。
- 试卷：标题、满分和考试时间、姓名部门日期得分栏、按题型分节并标注分值；最后一页是参考答案（含解析）。
