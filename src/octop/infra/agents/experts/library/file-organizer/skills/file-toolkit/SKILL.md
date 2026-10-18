---
name: file-toolkit
description: "文件整理工具：file_tool.py scan 体检目录（类别分布、最大文件、一年以上未修改、临时和系统文件、大小相同的疑似重复、空文件夹、超长路径）；dupes 按内容找出完全相同的文件，每组保留一个，其余移到 _重复文件待确认/；plan 按类型（文档/表格/演示/PDF/图片/视频/音频/压缩包/安装包/代码/电子书）、日期或类型+日期生成整理方案，可只整理 N 天前的文件，同名自动加序号；media_ops.py apply 执行方案并写撤销日志，undo 还原。整理下载目录、桌面、共享盘时使用。"
metadata:
  octop:
    emoji: "🗃️"
    label:
      zh: "文件整理工具"
      en: "File Toolkit"
    summary:
      zh: "体检、查重、按类型日期整理，可撤销。"
      en: "Scan, dedupe and organize by type or date, with undo."
---

# 文件整理工具

> `scripts/` 路径相对于本技能目录。两个脚本放在同一目录，`file_tool.py` 依赖 `media_ops.py`。

## 1. 体检

```bash
python scripts/file_tool.py scan /vol1/下载 [--top 20] [--json]
```

输出：文件数和总大小、各类别数量和大小、最大的 N 个文件、一年以上没修改的文件、临时和系统文件（`~$` 开头的 Office 临时文件、`.tmp`、`Thumbs.db`、`.DS_Store`、未下载完的 `.crdownload` 等）、大小相同可能重复的文件数、空文件夹、超过 200 字符的路径。

## 2. 查重

```bash
python scripts/file_tool.py dupes /vol1/下载 -o outputs/files/重复方案.csv [--keep shortest|newest|oldest]
```

按"大小 → 首尾哈希 → 全文哈希"比对，只有内容完全相同才算重复。每组保留一个（默认保留路径最短的），其余移到 `/vol1/下载/_重复文件待确认/` 下的原相对路径。

## 3. 整理方案

```bash
python scripts/file_tool.py plan /vol1/下载 --dest /vol1/下载/已整理 -o outputs/files/整理方案.csv --by type
python scripts/file_tool.py plan /vol1/下载 --dest /vol1/归档 -o outputs/files/整理方案.csv --by type-date --older-than 90
```

- `--by type`：`已整理/文档/`、`已整理/图片/`……；`date`：`归档/2026/2026-10/`；`type-date`：`归档/文档/2026/`。
- `--older-than 90`：只整理 90 天以前修改的文件，最近的留在原处。
- 目标目录在源目录里面时自动排除，不会重复整理；同名文件加 ` (2)`；扩展名统一为小写；临时和系统文件不整理。
- 方案 CSV 四列：操作、源路径、目标路径、说明。可以在 Excel 里改目标路径或删行。

## 4. 执行与撤销

```bash
python scripts/media_ops.py apply outputs/files/整理方案.csv --root /vol1/下载 [--prune-empty]
python scripts/media_ops.py undo /vol1/下载/.octop-media-undo/20261018-153000-01.csv
```

- 源和目标都必须在 `--root` 内；目标已存在则跳过，绝不覆盖；`--prune-empty` 清理移动后留下的空文件夹。
- 撤销日志写在 `--root/.octop-media-undo/`，按时间命名；undo 按相反顺序还原。
