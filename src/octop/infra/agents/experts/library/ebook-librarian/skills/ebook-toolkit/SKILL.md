---
name: ebook-toolkit
description: "电子书整理工具：ebook_tool.py 读取 epub（OPF）、mobi/azw3（EXTH）、pdf（文档信息）的书名、作者、语言、出版社、年份、ISBN，过滤无意义元数据后用文件名兜底（识别“书名 - 作者”“作者 - 书名”“《书名》作者”“[作者]书名”“书名(作者 著)”，按常见姓氏判断哪边是人名），作者去掉国籍、著/译等后缀；scan 盘点格式、来源、缺作者、同书多文件、GBK 编码 txt；plan 按 layout 生成整理方案；dupes 移走完全相同的文件；catalog 生成书单 Excel。media_ops.py 执行和撤销。整理电子书时使用。"
metadata:
  octop:
    emoji: "📖"
    label:
      zh: "电子书工具"
      en: "Ebook Toolkit"
    summary:
      zh: "识别书名作者，统一命名，查重，生成书单。"
      en: "Read metadata, rename, dedupe and catalog ebooks."
---

# 电子书工具

> `scripts/` 路径相对于本技能目录。两个脚本放在同一目录，`ebook_tool.py` 依赖 `media_ops.py`。

## 1. 盘点

```bash
python scripts/ebook_tool.py scan /vol1/电子书 [--json]
```

输出：总数和格式分布、书名来自元数据 / 文件名的数量、没有识别出作者的书、同一本书同一格式有多个文件（可能是不同版本）、同一本书有多种格式、GBK 编码的 txt（Kindle 和手机阅读器可能乱码）。

## 2. 书名作者怎么识别

1. **书内元数据**：epub 的 OPF（dc:title / dc:creator）、mobi/azw3 的 EXTH（503 书名、100 作者）、pdf 的文档信息。"Microsoft Word - …""Untitled""Administrator"这类无意义的值会被忽略。
2. **文件名**：`活着 - 余华`、`余华 - 活着`、`《围城》钱钟书`、`[东野圭吾]白夜行`、`人类简史(尤瓦尔·赫拉利 著)`、`George Orwell - 1984`；会去掉 `z-lib.org`、`精排版`、`(epub)` 等后缀。"A - B"两边都可能是书名时，按常见姓氏和"·"判断哪边是人名，判断不了时按"书名 - 作者"处理。
3. **作者规范化**：`[美] 卡尔·萨根 著；李四 译` → `卡尔·萨根`；`Harari, Yuval Noah` → `Yuval Noah Harari`；多位作者写成"第一作者 等"。

## 3. 整理方案

```bash
python scripts/ebook_tool.py plan /vol1/电子书 --dest /vol1/书库 -o outputs/ebook/整理方案.csv [--layout "{author}/{author} - {title}"]
```

- layout 可用 `{author}` `{title}` `{year}` `{lang}` `{format}`，例如平铺 `"{author} - {title}"`、按语言 `"{lang}/{author}/{title}"`。
- 同一本书的 epub、pdf 会落在同一个文件夹；重名时加 ` (2)`；目标目录在源目录里面时自动排除。
- "说明"列写明来源（元数据 / 文件名）和识别出的书名作者，来自文件名的请重点检查。

## 4. 查重与书单

```bash
python scripts/ebook_tool.py dupes /vol1/电子书 -o outputs/ebook/重复方案.csv
python scripts/ebook_tool.py catalog /vol1/书库 -o outputs/ebook/书单.xlsx
```

- dupes 只处理内容完全相同的文件；同名不同版本见 scan 的提示，由用户决定保留哪个。
- 书单：书名、作者、格式、大小、语言、出版社、出版年、ISBN、来源、相对路径，以及"已读""评分""笔记"空列；"统计"表按作者汇总。

## 5. 执行与撤销

```bash
python scripts/media_ops.py apply outputs/ebook/整理方案.csv --root /vol1/电子书 [--prune-empty]
python scripts/media_ops.py undo /vol1/电子书/.octop-media-undo/20261018-153000-01.csv
```
