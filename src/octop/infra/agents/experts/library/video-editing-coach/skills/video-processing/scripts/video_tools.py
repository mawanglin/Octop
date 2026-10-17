#!/usr/bin/env python3
"""ffmpeg 小工具：素材体检、粗剪拼接、烧录字幕、按平台规格导出、截取封面。

Usage:
    python scripts/video_tools.py which                       # 找 ffmpeg
    python scripts/video_tools.py probe input.mp4             # 素材信息
    python scripts/video_tools.py cut input.mp4 -o out.mp4 --keep 0:05-0:12 --keep 0:30-0:41
    python scripts/video_tools.py subtitle input.mp4 --srt sub.srt -o out.mp4
    python scripts/video_tools.py export input.mp4 --preset douyin -o out.mp4
    python scripts/video_tools.py cover input.mp4 --at 0:03 -o cover.jpg

所有命令加 --dry-run 只打印将要执行的 ffmpeg 命令。原素材永远不会被修改；
输出文件已存在时拒绝覆盖（加 --overwrite 才覆盖）。

ffmpeg 查找顺序：--ffmpeg 参数 → 环境变量 OCTOP_FFMPEG → PATH → 常见安装位置。
Exit codes: 0 ok, 1 参数/处理错误, 2 找不到 ffmpeg（此时会打印可手动执行的命令）。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

COMMON_LOCATIONS = (
    "/usr/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/opt/homebrew/bin/ffmpeg",
    "/usr/lib/jellyfin-ffmpeg/ffmpeg",  # Jellyfin / 部分 NAS 影视套件自带
    "/var/apps/*/target/bin/ffmpeg",  # 飞牛应用目录（未逐一验证）
    "/usr/trim/bin/ffmpeg",  # 飞牛系统组件（未逐一验证）
    "C:/ffmpeg/bin/ffmpeg.exe",
)

PRESETS = {
    # name: (width, height, fps, video bitrate cap, label)
    "douyin": (1080, 1920, 30, "8M", "抖音 / 快手 竖屏 1080×1920"),
    "channels": (1080, 1920, 30, "8M", "视频号 竖屏 1080×1920"),
    "xiaohongshu": (1080, 1440, 30, "8M", "小红书 3:4 1080×1440"),
    "bilibili": (1920, 1080, 30, "10M", "B 站 / 横屏 1920×1080"),
    "landscape": (1920, 1080, 30, "10M", "通用横屏 1920×1080"),
    "square": (1080, 1080, 30, "6M", "方形 1080×1080"),
}


class ToolError(RuntimeError):
    pass


class NoFFmpeg(ToolError):
    pass


def find_binary(name: str, explicit: str | None) -> str | None:
    for candidate in (explicit, os.environ.get(f"OCTOP_{name.upper()}")):
        if candidate and Path(candidate).is_file():
            return candidate
    found = shutil.which(name)
    if found:
        return found
    for pattern in COMMON_LOCATIONS:
        head, _, base = pattern.rpartition("/")
        pattern = f"{head}/{base.replace('ffmpeg', name)}"
        for path in sorted(glob.glob(pattern)):
            if os.access(path, os.X_OK):
                return path
    return None


def parse_time(value: str) -> float:
    """'75', '1:15', '0:01:15.5' → seconds."""
    parts = value.strip().split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError as exc:
        raise ToolError(f"时间格式不对：{value!r}（用 秒、分:秒 或 时:分:秒）") from exc
    seconds = 0.0
    for n in nums:
        seconds = seconds * 60 + n
    return seconds


def parse_range(value: str) -> tuple[float, float]:
    start, sep, end = value.partition("-")
    if not sep:
        raise ToolError(f"片段格式应为 开始-结束，如 0:05-0:12，收到 {value!r}")
    a, b = parse_time(start), parse_time(end)
    if b <= a:
        raise ToolError(f"片段 {value} 的结束时间必须晚于开始时间")
    return a, b


def guard_output(path: Path, overwrite: bool, sources: list[Path]) -> None:
    if any(path.resolve() == s.resolve() for s in sources):
        raise ToolError("输出路径不能与原素材相同，原素材不会被修改")
    if path.exists() and not overwrite:
        raise ToolError(f"{path} 已存在；确认要覆盖时加 --overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)


def run(cmd: list[str], dry_run: bool, ffmpeg: str | None) -> None:
    shown = " ".join(shlex.quote(c) for c in cmd)
    if dry_run or ffmpeg is None:
        print(shown)
        if ffmpeg is None:
            raise NoFFmpeg("未找到 ffmpeg，以上命令可在装有 ffmpeg 的电脑上手动执行")
        return
    print(f"执行：{shown}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-8:])
        raise ToolError(f"ffmpeg 失败（退出码 {proc.returncode}）：\n{tail}")


def ff(ffmpeg: str | None) -> str:
    return ffmpeg or "ffmpeg"


# ----------------------------------------------------------------- commands


def cmd_probe(args: argparse.Namespace, ffmpeg: str | None) -> None:
    ffprobe = find_binary("ffprobe", None)
    if ffprobe is None and ffmpeg:
        sibling = Path(ffmpeg).with_name("ffprobe" + Path(ffmpeg).suffix)
        ffprobe = str(sibling) if sibling.is_file() else None
    cmd = [
        ffprobe or "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(args.input),
    ]  # fmt: skip
    if ffprobe is None or args.dry_run:
        print(" ".join(shlex.quote(c) for c in cmd))
        if ffprobe is None:
            raise NoFFmpeg("未找到 ffprobe")
        return
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ToolError(f"无法读取素材：{proc.stderr.strip()}")
    info = json.loads(proc.stdout)
    fmt = info.get("format", {})
    duration = float(fmt.get("duration", 0) or 0)
    size_mb = int(fmt.get("size", 0) or 0) / 1024 / 1024
    print(f"文件：{args.input}")
    print(f"时长：{int(duration // 60)}:{duration % 60:05.2f}，大小：{size_mb:.1f} MB，"
          f"容器：{fmt.get('format_name', '?')}")  # fmt: skip
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            rate = s.get("avg_frame_rate", "0/1")
            num, _, den = rate.partition("/")
            fps = float(num) / float(den or 1) if float(den or 1) else 0
            rotate = (s.get("tags") or {}).get("rotate") or next(
                (str(d.get("rotation")) for d in s.get("side_data_list", []) if "rotation" in d), ""
            )
            w, h = s.get("width"), s.get("height")
            orient = "竖屏" if (w or 0) < (h or 0) else "横屏"
            if rotate in ("90", "-90", "270"):
                orient = "竖屏（旋转元数据）" if orient == "横屏" else "横屏（旋转元数据）"
            print(f"视频：{s.get('codec_name')} {w}×{h} {orient}，{fps:.2f} fps，"
                  f"码率 {int(s.get('bit_rate', 0) or 0) // 1000} kbps")  # fmt: skip
        elif s.get("codec_type") == "audio":
            print(
                f"音频：{s.get('codec_name')} {s.get('sample_rate')} Hz，{s.get('channels')} 声道"
            )
    if not any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
        print("提示：素材没有音轨")


def cmd_cut(args: argparse.Namespace, ffmpeg: str | None) -> None:
    ranges = [parse_range(r) for r in args.keep]
    guard_output(args.output, args.overwrite, [args.input])
    parts, labels = [], []
    for i, (a, b) in enumerate(ranges):
        parts.append(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]")
        if not args.no_audio:
            parts.append(f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]")
            labels.append(f"[v{i}][a{i}]")
        else:
            labels.append(f"[v{i}]")
    audio = 0 if args.no_audio else 1
    out_labels = "[outv]" + ("" if args.no_audio else "[outa]")
    graph = (
        ";".join(parts)
        + ";"
        + "".join(labels)
        + f"concat=n={len(ranges)}:v=1:a={audio}{out_labels}"
    )
    cmd = [ff(ffmpeg), "-hide_banner", "-y", "-i", str(args.input), "-filter_complex", graph,
           "-map", "[outv]"]  # fmt: skip
    if not args.no_audio:
        cmd += ["-map", "[outa]", "-c:a", "aac", "-b:a", "128k"]
    cmd += ["-c:v", "libx264", "-crf", "20", "-preset", "medium", "-movflags", "+faststart",
            str(args.output)]  # fmt: skip
    run(cmd, args.dry_run, ffmpeg)
    total = sum(b - a for a, b in ranges)
    if not args.dry_run:
        print(f"已输出 {args.output}（{len(ranges)} 段，共 {total:.1f} 秒）")


def _filter_path(path: Path) -> str:
    """Escape a path for use inside an ffmpeg filter argument."""
    text = path.resolve().as_posix()
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def cmd_subtitle(args: argparse.Namespace, ffmpeg: str | None) -> None:
    if not args.srt.is_file():
        raise ToolError(f"字幕文件不存在：{args.srt}")
    guard_output(args.output, args.overwrite, [args.input])
    style = (
        f"FontName={args.font},FontSize={args.font_size},PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,MarginV={args.margin}"
    )
    vf = f"subtitles='{_filter_path(args.srt)}':force_style='{style}'"
    cmd = [ff(ffmpeg), "-hide_banner", "-y", "-i", str(args.input), "-vf", vf,
           "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-c:a", "copy",
           "-movflags", "+faststart", str(args.output)]  # fmt: skip
    run(cmd, args.dry_run, ffmpeg)
    if not args.dry_run:
        print(f"已输出 {args.output}")


def cmd_export(args: argparse.Namespace, ffmpeg: str | None) -> None:
    w, h, fps, maxrate, label = PRESETS[args.preset]
    guard_output(args.output, args.overwrite, [args.input])
    if args.fit == "pad":
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={fps}")  # fmt: skip
    else:  # crop: fill the frame, cut the overflow
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps}"
    cmd = [ff(ffmpeg), "-hide_banner", "-y", "-i", str(args.input), "-vf", vf,
           "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "20",
           "-maxrate", maxrate, "-bufsize", maxrate.replace("M", "") + "M",
           "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart",
           str(args.output)]  # fmt: skip
    run(cmd, args.dry_run, ffmpeg)
    if not args.dry_run:
        print(f"已按「{label}」导出 {args.output}")


def cmd_cover(args: argparse.Namespace, ffmpeg: str | None) -> None:
    guard_output(args.output, args.overwrite, [args.input])
    cmd = [ff(ffmpeg), "-hide_banner", "-y", "-ss", str(parse_time(args.at)), "-i", str(args.input),
           "-frames:v", "1", "-q:v", "2", str(args.output)]  # fmt: skip
    run(cmd, args.dry_run, ffmpeg)
    if not args.dry_run:
        print(f"已截取封面 {args.output}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    # 通用选项写在子命令前后都可以。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ffmpeg", help="ffmpeg 路径")
    common.add_argument("--dry-run", action="store_true", help="只打印命令，不执行")
    common.add_argument("--overwrite", action="store_true", help="允许覆盖已存在的输出文件")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("which", help="显示找到的 ffmpeg", parents=[common])
    p = sub.add_parser("probe", help="素材信息", parents=[common])
    p.add_argument("input", type=Path)
    c = sub.add_parser("cut", help="按时间段保留并拼接", parents=[common])
    c.add_argument("input", type=Path)
    c.add_argument("-o", "--output", type=Path, required=True)
    c.add_argument("--keep", action="append", required=True, help="保留片段，如 0:05-0:12，可多次")
    c.add_argument("--no-audio", action="store_true", help="素材没有音轨或不要音频")
    s = sub.add_parser("subtitle", help="烧录 SRT 字幕", parents=[common])
    s.add_argument("input", type=Path)
    s.add_argument("--srt", type=Path, required=True)
    s.add_argument("-o", "--output", type=Path, required=True)
    s.add_argument("--font", default="Noto Sans CJK SC")
    s.add_argument("--font-size", type=int, default=16, help="字幕字号（相对 288 行高的 ASS 单位）")
    s.add_argument("--margin", type=int, default=40, help="距底部边距")
    e = sub.add_parser("export", help="按平台规格导出", parents=[common])
    e.add_argument("input", type=Path)
    e.add_argument("--preset", choices=sorted(PRESETS), required=True)
    e.add_argument(
        "--fit", choices=["pad", "crop"], default="pad", help="pad 加黑边，crop 裁切铺满"
    )
    e.add_argument("-o", "--output", type=Path, required=True)
    v = sub.add_parser("cover", help="截取封面帧", parents=[common])
    v.add_argument("input", type=Path)
    v.add_argument("--at", default="0", help="时间点，如 0:03")
    v.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args(argv)

    ffmpeg = find_binary("ffmpeg", args.ffmpeg)
    if args.cmd == "which":
        if ffmpeg is None:
            print(
                "未找到 ffmpeg。可安装 ffmpeg，或设置环境变量 OCTOP_FFMPEG 指向 ffmpeg 可执行文件。"
            )
            return 2
        print(ffmpeg)
        return 0
    if not args.input.is_file():
        print(f"素材不存在：{args.input}", file=sys.stderr)
        return 1
    handlers = {
        "probe": cmd_probe,
        "cut": cmd_cut,
        "subtitle": cmd_subtitle,
        "export": cmd_export,
        "cover": cmd_cover,
    }
    try:
        handlers[args.cmd](args, ffmpeg)
    except NoFFmpeg as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ToolError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
