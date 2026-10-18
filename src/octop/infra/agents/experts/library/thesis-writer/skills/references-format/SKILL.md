---
name: references-format
description: "参考文献格式：gbt7714.py format 把 BibTeX（知网、Zotero、EndNote、Google Scholar 导出）或 CSV 整理成 GB/T 7714-2015 顺序编码制格式（期刊 J、图书 M、学位论文 D、会议 C、报告 R、标准 S、专利 P、报纸 N、网页 EB/OL；作者超过 3 人加“等/et al”，外文姓大写名缩写），并列出缺少的著录项；gbt7714.py check 检查已有列表的类型标识、年份、标点、页码、作者省略、序号和重复。整理或检查参考文献时使用。"
metadata:
  octop:
    emoji: "📚"
    label:
      zh: "参考文献格式"
      en: "References Format"
    summary:
      zh: "整理成 GB/T 7714 格式并检查常见错误。"
      en: "Format and check GB/T 7714 references."
---

# 参考文献格式

> `scripts/` 和 `references/` 路径相对于本技能目录；示例 BibTeX：`references/example.bib`（虚构）。

## 1. 导出文献

- 知网：勾选文献 → 导出与分析 → 导出文献 → 选择 BibTeX（或 EndNote 后再转）。
- Zotero / EndNote：选中条目 → 导出 → BibTeX。
- 按正文首次引用的顺序排列条目（顺序编码制）；使用著者-出版年制的学校请告诉用户手动调整。

也可以写 CSV，列：`类型,作者,题名,刊名,年,卷,期,页码,出版地,出版者,网址,发布日期,引用日期,DOI,编号`，作者用 `;` 分隔。

## 2. 生成

```bash
python scripts/gbt7714.py format inbound/文献.bib -o outputs/thesis/参考文献.txt
```

示例输出：

```text
[1] 王小明, 李华, 张伟, 等. 基于深度学习的城市交通流量预测方法研究[J]. 交通运输工程学报, 2023, 23(4): 112-125.
[2] SMITH J A, LEE M, BROWN D. Graph neural networks for traffic forecasting[J]. Transportation Research Part C, 2021, 125: 103-118. DOI:10.1016/j.trc.2021.000000.
```

脚本会列出每条缺少的著录项（如期刊缺页码、网页缺引用日期），**请用户查原文补充，不要猜测**。

## 3. 检查已有列表

```bash
python scripts/gbt7714.py check outputs/thesis/参考文献.txt
```

检查：序号是否连续、文献类型标识、出版年、中英文标点、页码连接符、作者超过 3 人未省略、中文用“等”外文用“et al”、期刊是否有“年, 卷(期): 页码”、网页是否有网址、重复条目。

## 4. 注意

- 学校模板有自己的细则（如中文文献用全角标点、作者全部列出），以学校要求为准，并告诉用户哪些地方与 GB/T 7714 默认不同。
- 正文引用与列表的对应关系用 `format-check` 技能检查。
