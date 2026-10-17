---
name: subtitle-srt
description: "SRT 字幕制作与检查：make_srt.py 把文稿或带时间段的视频脚本按语速切分成 SRT（每条字数可控、去掉句末标点），也能检查已有字幕的重叠、单行过长、显示过短、阅读速度过快；还可做字幕校对和中英双语翻译。不需要 ffmpeg。"
metadata:
  octop:
    emoji: "💬"
    label:
      zh: "SRT 字幕"
      en: "SRT Subtitles"
    summary:
      zh: "文稿转 SRT 字幕，检查和校对已有字幕。"
      en: "Turn scripts into SRT files and check existing subtitles."
---

# SRT 字幕

> `scripts/make_srt.py` 相对于本技能目录，只用 Python 标准库。

## 1. 文稿或脚本生成 SRT

```bash
python scripts/make_srt.py outputs/video/<标题>.md -o outputs/video/<标题>.srt [--rate 4] [--max-chars 16]
```

- **带时间段的脚本**（`## [0:00-0:03] 段落名` + `口播：……`，即「短视频脚本专家」的格式）：每段口播切成字幕，按字数分配在该时间段内，和画面对得上。"画面：""字幕：""音效："等行不进字幕。
- **普通文稿**：按 `--rate`（字/秒，默认 4）依次排时间。
- `--max-chars`：每条最多字数；竖屏 12–16，横屏 18–22。
- `--start`：整体偏移（片头有 2 秒 Logo 就写 `--start 2`）。

生成的时间轴是按语速估算的。成片的实际语速不同时，告诉用户把 SRT 导入剪映/PR 后整体拖动或微调；或者用剪辑软件的"识别字幕"生成时间轴，再用本技能校对文字。

## 2. 检查已有字幕

```bash
python scripts/make_srt.py --check subs.srt [--max-chars 16] [--max-cps 7]
```

检查：时间倒置、与上一条重叠、单行超长、显示不足 0.7 秒、每秒字数超过 `--max-cps`、句末带句号逗号。退出码 3 表示有问题。

## 3. 校对与翻译

- **校对**：对照文稿修正错别字、同音字、专有名词、数字；只改文字，不改时间轴，并输出修改对照表（条号、原文、修改后）。
- **双语**：中文在上、英文在下，两行合为一条；英文按意思翻译，长度控制在一行内，必要时拆成两条。
- 保存时用 UTF-8 编码；部分老软件需要 UTF-8 with BOM，打不开时再转换。

字幕需要烧进画面时，交给 `video-processing` 的 `subtitle` 命令。
