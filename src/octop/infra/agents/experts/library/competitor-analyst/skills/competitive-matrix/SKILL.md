---
name: competitive-matrix
description: "竞品对比矩阵：compare_matrix.py template 按产品类型（internet 互联网产品、saas 企业软件、ai AI 产品、hardware 硬件、consumer 消费品）生成带权重的评分模板和证据表；score 计算加权得分和排名（未评维度不计入并显示覆盖率）、各维度领先者、我方与最强竞品的差距（按加权影响排序），列出缺分、缺证据、缺来源的评分，输出带雷达图和柱状图的 Excel。需要多维度量化对比竞品时使用。"
metadata:
  octop:
    emoji: "📐"
    label:
      zh: "对比矩阵"
      en: "Comparison Matrix"
    summary:
      zh: "加权评分、雷达图、差距分析，每个分数都有证据。"
      en: "Weighted scores, radar chart, gap analysis, evidence-backed."
---

# 竞品对比矩阵

> `scripts/` 路径相对于本技能目录。

## 1. 生成模板

```bash
python scripts/compare_matrix.py template --type ai --competitors 小记,速笔,云签 --self 小记 -o outputs/竞品/竞品矩阵.xlsx
```

- `--type` 选维度预设：`internet`、`saas`、`ai`、`hardware`、`consumer`；
- 模板里的维度和权重可以按决策目的调整，增删行列都可以；
- "评分"表填 1–5 分（1 很差 · 3 一般 · 5 很好），没评估的留空，不要猜；
- "证据"表逐条写结论、来源链接、获取日期、可信度（高 / 中 / 低）。

## 2. 计算

```bash
python scripts/compare_matrix.py score outputs/竞品/竞品矩阵.xlsx --self 小记 -o outputs/竞品/评分结果.xlsx
```

输出：
- **排名**：加权得分（只按已评维度计算并显示覆盖率，覆盖低于 80% 时排名仅供参考）；
- **各维度领先者**；
- **我方差距**：与每个维度最强竞品的分差，按加权影响排序（优先补哪块）；
- **待补充**：缺分、缺证据、缺来源的评分。有待补充项时退出码为 3；
- Excel 里有排名柱状图和能力雷达图，可以直接复制到报告或 PPT。

## 3. 打分纪律

- 同一个维度给所有竞品打分时**用同一把尺子**：先写清 1 分和 5 分分别是什么样，再打分；
- 能实测的维度（效果、速度、步骤数）用实测结果打分；
- 分数差 1 分以内不要过度解读，报告里写"接近"；
- 权重要在打分前定好，不要打完分再调权重让结果好看。
