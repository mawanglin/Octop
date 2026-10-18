---
name: photo-toolkit
description: "照片整理工具：photo_tool.py 体检（类型、日期来源、年份分布、格式、相机）、查重（完全相同的照片和视频）、按拍摄时间生成“年/年-月”整理方案（可按 20240512_143005 重命名、截图和微信图片单独归档、实况照片视频和编辑记录跟随）；media_ops.py 执行和撤销。整理手机备份、相机照片时使用。"
metadata:
  octop:
    emoji: "📷"
    label:
      zh: "照片整理工具"
      en: "Photo Toolkit"
    summary:
      zh: "按拍摄时间归档、重命名、查重，可撤销。"
      en: "Archive by date taken, rename, dedupe — undoable."
---

# 照片整理工具

> `scripts/` 路径相对于本技能目录。`photo_tool.py` 依赖同目录的 `media_ops.py`。

## 1. 体检（只读）

```bash
python scripts/photo_tool.py scan /照片目录 [--json]
```

报告：文件数和大小；类型（相机、截图、微信、视频、其他）；日期来源（EXIF、文件名、修改时间）；年份分布；格式；相机型号；只能按修改时间归档的文件清单。HEIC 文件读不了 EXIF，会按文件名或修改时间判断，报告中会提示。

## 2. 查重（生成方案）

```bash
python scripts/photo_tool.py dupes /照片目录 -o outputs/photos/重复方案.csv
```

只找字节完全相同的文件（同一张照片被备份了多次）；每组保留路径最短的一份（通常是原始位置），其余移到 `_重复文件待确认/`。连拍、相似照片不算重复。

## 3. 整理（生成方案 → 确认 → 执行）

```bash
python scripts/photo_tool.py plan /照片目录 --dest /照片目录/整理后 -o outputs/photos/整理方案.csv \
  [--layout "{year}/{year}-{month}"] [--rename] [--split-sources] [--no-videos]
python scripts/media_ops.py apply outputs/photos/整理方案.csv --root /照片目录 --prune-empty
python scripts/media_ops.py undo /照片目录/.octop-media-undo/<时间>.csv
```

- `--layout`：可用 `{year}` `{month}` `{day}`，如按天归档 `{year}/{year}-{month}-{day}`。
- `--rename`：重命名为拍摄时间 `20240512_143005.jpg`，同一秒的照片加 `_2`、`_3`；不加则保留原文件名。
- `--split-sources`：截图归到 `截图/年/年-月`，微信图片归到 `微信图片/年/年-月`。
- `--no-videos`：只整理照片；默认手机视频（.mp4/.mov）也按拍摄时间归档。
- 跟随文件：与照片同名的 `.MOV`（实况照片）、RAW 原片（`.CR3/.NEF/.ARW` 等）、`.AAE` / `.XMP` 编辑记录都跟随照片移动并改成同一文件名。
- 方案"说明"列标明每个文件的日期来源；"修改时间（可能不准）"的文件建议用户先抽查。

## 4. 日期识别的文件名格式

`IMG_20240512_143005`、`VID_20240601_101010`、`PXL_20240512_143005123`、`Screenshot_2024-05-12-14-30-05`、`Screenshot_20240512-143005`、`屏幕截图 2024-05-12 143005`、`微信图片_20230101120000`、`mmexport1715500000000`（毫秒时间戳）、`wx_camera_1715500000000`、`IMG-20240512-WA0001`（只有日期）。时间戳按服务器所在时区换算。
