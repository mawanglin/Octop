---
name: music-toolkit
description: "本地音乐整理工具：music_tool.py 体检（格式、码率、缺标签、GBK 乱码、封面、歌词）、查重（完全相同或同一首歌的不同文件，保留音质最好的）、按文件名补标签（可撤销）、生成“艺术家/专辑/音轨 - 标题”整理方案（歌词和封面跟随）、生成 m3u8 歌单；media_ops.py 执行方案、撤销。整理音乐库时使用。"
metadata:
  octop:
    emoji: "🎵"
    label:
      zh: "音乐整理工具"
      en: "Music Toolkit"
    summary:
      zh: "体检、查重、补标签、整理、歌单，可撤销。"
      en: "Scan, dedupe, tag, organize, and build playlists — undoable."
---

# 音乐整理工具

> `scripts/` 路径相对于本技能目录。两个脚本必须放在同一目录（`music_tool.py` 依赖 `media_ops.py`）。

## 1. 体检（只读）

```bash
python scripts/music_tool.py scan /音乐目录 [--json]
```

报告：文件数和总大小、格式、无损数量、低码率（<192kbps）、缺少标题/艺术家/专辑/音轨号、标签疑似乱码（GBK 被当成 Latin-1 读取）、无封面、无歌词、无法读取的文件。

## 2. 查重（生成方案）

```bash
python scripts/music_tool.py dupes /音乐目录 -o outputs/music/重复方案.csv [--exact-only]
```

两类重复：字节完全相同的文件；艺术家和标题相同、时长相差 ≤3 秒的同一首歌。每组保留音质最好的一份（无损 > 码率高 > 文件大），其余移到 `/音乐目录/_重复文件待确认/`（保留原相对路径）。**先查重再补标签**：补标签会改变文件内容，之后就无法按字节识别完全相同的副本了。

## 3. 补标签（生成方案 → 确认 → 写入）

```bash
python scripts/music_tool.py tags-from-name /音乐目录 --pattern "{artist} - {title}" -o outputs/music/标签方案.csv [--all]
python scripts/music_tool.py write-tags outputs/music/标签方案.csv --root /音乐目录
python scripts/music_tool.py undo-tags /音乐目录/.octop-media-undo/tags-<时间>.csv
```

- 模式字段：`{artist}` `{title}` `{album}` `{track}` `{year}`，按文件名的实际规律写（如 `{track}. {title}`、`{artist} - {album} - {title}`）；文件名开头的音轨号会自动忽略。
- 默认只补空缺或乱码的字段；`--all` 会覆盖已有标签。
- 标签方案是 CSV（文件、字段、原值、新值），用户可以直接在里面修正乱码标签的"新值"。
- `write-tags` 只修改标签，写入前把原值记入撤销日志；之后即使文件已按方案移动，`undo-tags` 也会根据移动日志找到文件的新位置。

## 4. 整理（生成方案 → 确认 → 执行）

```bash
python scripts/music_tool.py plan /音乐目录 --dest /音乐目录/整理后 -o outputs/music/整理方案.csv \
  [--layout "{albumartist}/{album} ({year})/{track} - {title}"]
python scripts/media_ops.py apply outputs/music/整理方案.csv --root /音乐目录 --prune-empty
python scripts/media_ops.py undo /音乐目录/.octop-media-undo/<时间>.csv
```

- 布局字段：`{albumartist}` `{artist}` `{album}` `{year}` `{track}` `{title}` `{genre}`；年份或音轨号为空时自动去掉对应的括号和分隔符；缺艺术家/专辑时归入"未知艺术家/未知专辑"，并在"说明"列提示。
- 同名的 `.lrc` 歌词跟随歌曲；文件夹里的 `cover.jpg / folder.jpg` 在整张专辑都去往同一目录时跟随。
- 目标重名时自动加序号，并提示可能是重复文件。
- `--root` 指定的根目录必须同时包含源文件和目标目录；方案中目标为空、目标已存在、路径越界的行会被跳过并报告（退出码 3）。
- `--prune-empty` 只删除整理后变空的文件夹，不删除任何文件。

## 5. 歌单

```bash
python scripts/music_tool.py playlist /音乐目录/整理后 --by artist -o /音乐目录/整理后/歌单
```

`--by`：artist、albumartist、album、genre、year、folder。生成 UTF-8 的 `.m3u8`，使用相对路径，音乐库整体搬到其他位置后歌单仍然可用。

## 6. 跳过的目录

扫描时自动跳过 `_重复文件待确认/`、`.octop-media-undo/`、以 `.` 开头的目录，以及群晖、飞牛等 NAS 的缩略图目录（`@eaDir` 等）和回收站目录；`plan` 还会跳过目标目录本身。
