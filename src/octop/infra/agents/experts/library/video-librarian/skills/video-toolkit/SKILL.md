---
name: video-toolkit
description: "本地影视整理工具：video_tool.py 识别电影和剧集文件名（片名、年份、S01E02/第2季第5集/EP05/动画“ - 05”、分辨率，中英双名取中文）、体检（数量、分辨率、缺年份、无字幕、孤立字幕、多版本、样片）、查重、生成“片名 (年份)/片名 (年份).mkv”和“剧名/Season 01/剧名 S01E01.mkv”整理方案（字幕加语言后缀跟随）；media_ops.py 执行和撤销。整理电影剧集时使用。"
metadata:
  octop:
    emoji: "🎞️"
    label:
      zh: "影视整理工具"
      en: "Video Toolkit"
    summary:
      zh: "识别片名季集，按刮削规范整理，可撤销。"
      en: "Parse titles and episodes, organize for scrapers, undoable."
---

# 影视整理工具

> `scripts/` 路径相对于本技能目录。`video_tool.py` 依赖同目录的 `media_ops.py`。

## 1. 识别单个文件名

```bash
python scripts/video_tool.py parse "流浪地球2.The.Wandering.Earth.II.2023.2160p.WEB-DL.mkv"
```

输出类型（movie / episode）、片名、年份、季、集、分辨率。支持：`S01E02`、`1x02`、`第2季 第3集`、`EP05`、`E05`、动画字幕组格式 `[组名] 片名 - 05 [1080p]`；会去掉网站水印、`【】[]` 中的发布组信息、WEB-DL / x265 / 国语中字等标记；中英双名保留中文名；剧集文件名里没有剧名时，从上级文件夹（跳过 `Season 01` / `第一季` 文件夹）取剧名和季号。

## 2. 体检（只读）

```bash
python scripts/video_tool.py scan /影视目录 [--probe] [--json]
```

`--probe` 用 ffprobe 读取实际分辨率和时长（较慢；没有 ffprobe 时跳过并提示，可用环境变量 `OCTOP_FFPROBE` 指定路径）。

## 3. 查重（生成方案）

```bash
python scripts/video_tool.py dupes /影视目录 -o outputs/video/重复方案.csv [--full-hash]
```

默认按"大小 + 首尾各 1MB 的哈希"比对，速度快；`--full-hash` 计算完整哈希，更严格但大文件很慢。只处理字节相同的文件；同一部影片的不同版本（1080p 与 2160p）不算重复，体检中会列为"疑似多版本"。

## 4. 整理（生成方案 → 确认 → 执行）

```bash
python scripts/video_tool.py plan /影视目录 --movies /影视目录/电影 --shows /影视目录/剧集 -o outputs/video/整理方案.csv
python scripts/media_ops.py apply outputs/video/整理方案.csv --root /影视目录 --prune-empty
python scripts/media_ops.py undo /影视目录/.octop-media-undo/<时间>.csv
```

- 电影：`电影/片名 (年份)/片名 (年份).mkv`；缺年份时只用片名并提示补充。
- 剧集：`剧集/剧名/Season 01/剧名 S01E01.mkv`；文件名没有季号时按第 1 季，并提示。
- 同一影片有多个文件时，后面的文件加 ` - 2160p` 之类的版本后缀（媒体服务器会识别为同一影片的多个版本）。
- 字幕（同名或同季集）跟随改名并加语言后缀：简体或中英双语 `.zh`、繁体 `.zh-TW`、英文 `.en`、日文 `.ja`，识别不了就不加；同名的 `.nfo`、海报图片也会跟随。
- 无法识别片名的文件目标留空，执行时跳过；样片和预告片不进入方案。
- `--root` 必须同时包含源文件和电影、剧集目录；`--movies` / `--shows` 目录里已有的文件不会被重复整理。
