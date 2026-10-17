---
name: video-processing
description: "用 ffmpeg 处理视频（需要环境中有 ffmpeg）：video_tools.py 支持素材体检（probe）、按时间段粗剪拼接（cut）、烧录 SRT 字幕（subtitle）、按抖音/视频号/小红书/B 站规格导出（export）、截取封面（cover）；所有命令可 --dry-run，只输出新文件不改原素材。用户要直接处理视频文件时使用。"
metadata:
  octop:
    emoji: "⚙️"
    label:
      zh: "视频处理"
      en: "Video Processing"
    summary:
      zh: "体检、粗剪、烧字幕、按平台导出、截封面。"
      en: "Probe, cut, burn subtitles, export presets, grab covers."
---

# 视频处理（ffmpeg）

> `scripts/video_tools.py` 相对于本技能目录。

## 0. 先确认 ffmpeg

```bash
python scripts/video_tools.py which
```

查找顺序：`--ffmpeg` 参数 → 环境变量 `OCTOP_FFMPEG` → 系统 PATH → 常见安装位置（包括部分 NAS 影视套件自带的 ffmpeg）。退出码 2 表示没找到，此时：
- 告诉用户可以安装 ffmpeg，或在 Octop 的环境变量里设置 `OCTOP_FFMPEG=/ffmpeg/路径`；
- 改用 `--dry-run` 输出命令，让用户在自己电脑上执行；或者给出剪映/PR 的手动步骤。

## 1. 命令

```bash
# 素材体检：时长、分辨率、横竖屏（含旋转元数据）、帧率、码率、音轨
python scripts/video_tools.py probe inbound/A001.mp4

# 粗剪：保留若干时间段并按顺序拼接（重新编码，切点精确）
python scripts/video_tools.py cut inbound/A001.mp4 -o outputs/video/粗剪.mp4 --keep 0:12-0:15 --keep 0:40-0:52

# 烧录字幕（SRT 来自 subtitle-srt 技能）
python scripts/video_tools.py subtitle outputs/video/粗剪.mp4 --srt outputs/video/字幕.srt -o outputs/video/带字幕.mp4 [--font-size 16] [--margin 40]

# 按平台规格导出：douyin / channels / xiaohongshu / bilibili / landscape / square
python scripts/video_tools.py export outputs/video/带字幕.mp4 --preset douyin -o outputs/video/成片-抖音.mp4 [--fit crop]

# 截取封面帧
python scripts/video_tools.py cover outputs/video/成片-抖音.mp4 --at 0:03 -o outputs/video/封面.jpg
```

通用选项（写在子命令前后都可以）：`--dry-run` 只打印命令；`--overwrite` 允许覆盖已存在的输出；`--ffmpeg` 指定路径。

## 2. 规则

- 原素材永远只读：输出路径和原素材相同时直接拒绝；输出已存在时默认拒绝覆盖。
- 执行前先 `--dry-run` 给用户看命令和预期结果；处理大文件前用 `df -h` 确认空间。
- `cut` 的素材没有音轨时加 `--no-audio`（先用 `probe` 确认）。
- `export --fit pad`（默认）加黑边保留完整画面；`--fit crop` 裁切铺满，横屏转竖屏时注意主体是否被裁掉。
- 字幕字体默认 Noto Sans CJK SC（Docker 镜像已内置）；用户电脑上执行时可改 `--font "Microsoft YaHei"` 或 `--font "PingFang SC"`。
- 处理失败时把 ffmpeg 报错的最后几行告诉用户，并给出可能原因（编码不支持、文件损坏、空间不足）。

调色、花字、特效、配乐卡点等创意性工作仍需在剪辑软件里完成，交付时列出手动步骤。
