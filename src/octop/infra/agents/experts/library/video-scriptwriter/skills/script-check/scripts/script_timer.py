#!/usr/bin/env python3
"""短视频脚本时长核对：每段口播字数是否装得进标注的时间段，开头钩子是否够快。

Usage:
    python scripts/script_timer.py script.md [--rate 4] [--target 60]

脚本格式（见 platform-scripts 技能的 references/example-script.md）：
    ## [0:00-0:03] 钩子
    画面：……
    口播：……
时间段写成 "## [开始-结束] 段落名"；"口播：" "台词：" "旁白：" 行计入字数。
front matter 里的 "时长: 60" 会作为目标时长（--target 优先）。
Exit codes: 0 ok, 3 有需要调整的段落, 1 输入错误。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SEGMENT = re.compile(
    r"^#{2,3}\s*\[(\d+:\d{1,2}(?:\.\d+)?)\s*[-–~]\s*(\d+:\d{1,2}(?:\.\d+)?)\]\s*(.*)$"
)
SPOKEN = re.compile(r"^(口播|台词|旁白|解说|配音)[:：]\s*(.*)$")


@dataclass
class Segment:
    start: float
    end: float
    name: str
    spoken: str = ""
    has_visual: bool = False


def to_seconds(value: str) -> float:
    total = 0.0
    for part in value.split(":"):
        total = total * 60 + float(part)
    return total


def spoken_units(text: str) -> int:
    cjk = len(re.findall(r"[一-鿿]", text))
    digits = sum(len(m) for m in re.findall(r"\d+", text))
    words = len(re.findall(r"[A-Za-z]+", text))
    return cjk + digits + round(words * 1.5)


def parse(source: str) -> tuple[dict[str, str], list[Segment]]:
    lines = source.replace("\r\n", "\n").split("\n")
    meta: dict[str, str] = {}
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                for raw in lines[1:i]:
                    key, sep, value = raw.replace("：", ":", 1).partition(":")
                    if sep:
                        meta[key.strip()] = value.strip()
                lines = lines[i + 1 :]
                break
    segments: list[Segment] = []
    for raw in lines:
        line = raw.strip()
        m = SEGMENT.match(line)
        if m:
            name = m.group(3).strip() or f"第 {len(segments) + 1} 段"
            segments.append(Segment(to_seconds(m.group(1)), to_seconds(m.group(2)), name))
            continue
        if not segments:
            continue
        seg = segments[-1]
        sm = SPOKEN.match(line)
        if sm:
            seg.spoken += sm.group(2)
        elif line.startswith(("画面", "镜头")):
            seg.has_visual = True
    return meta, segments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("input")
    parser.add_argument("--rate", type=float, default=4.0, help="口播语速（字/秒），默认 4")
    parser.add_argument("--target", type=float, help="目标总时长（秒）")
    args = parser.parse_args(argv)
    try:
        meta, segments = parse(Path(args.input).read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"无法读取：{exc}", file=sys.stderr)
        return 1
    if not segments:
        print("没有找到 “## [0:00-0:03] 段落名” 格式的时间段", file=sys.stderr)
        return 1

    issues: list[str] = []
    print(f"语速 {args.rate:g} 字/秒")
    print("| 段落 | 时间段 | 时长 | 口播字数 | 需要 | 状态 |")
    print("|------|--------|------|----------|------|------|")
    prev_end = 0.0
    for seg in segments:
        start, end = seg.start, seg.end
        dur = end - start
        n = spoken_units(seg.spoken)
        need = n / args.rate
        if dur <= 0:
            status = "时间段无效"
            issues.append(f"{seg.name}：结束时间不晚于开始时间")
        elif need > dur * 1.1:
            status = f"超出 {need - dur:.1f} 秒"
            issues.append(
                f"{seg.name}：口播 {n} 字约需 {need:.1f} 秒，时间段只有 {dur:.1f} 秒，删减约 {round((need - dur) * args.rate)} 字"
            )
        elif n and need < dur * 0.5:
            status = "偏空"
        else:
            status = "OK"
        if abs(start - prev_end) > 0.05:
            issues.append(f"{seg.name}：与上一段之间有 {start - prev_end:+.1f} 秒的空档或重叠")
        if not seg.has_visual:
            issues.append(f"{seg.name}：没有写“画面：”，拍摄和剪辑无从下手")
        prev_end = end
        span = f"{int(start // 60)}:{start % 60:04.1f}-{int(end // 60)}:{end % 60:04.1f}"
        print(f"| {seg.name} | {span} | {dur:.1f}s | {n} | {need:.1f}s | {status} |")

    first = segments[0]
    hook_units = spoken_units(first.spoken)
    if first.end > 3.5:
        issues.append("开头钩子超过 3 秒：前 3 秒要抛出结论、冲突或问题")
    if hook_units > 16:
        issues.append(f"开头钩子 {hook_units} 字，偏长；前 3 秒口播建议 8–14 字")

    total = segments[-1].end
    target = args.target or (
        float(meta["时长"]) if meta.get("时长", "").replace(".", "").isdigit() else None
    )
    print(f"\n总时长 {total:.1f} 秒，口播共 {sum(spoken_units(s.spoken) for s in segments)} 字")
    if target and abs(total - target) > max(2.0, target * 0.1):
        issues.append(f"总时长 {total:.0f} 秒，与目标 {target:.0f} 秒相差较大")
    if issues:
        print("\n需要调整：")
        for issue in issues:
            print(f"- {issue}")
        return 3
    print("各段时长与口播匹配")
    return 0


if __name__ == "__main__":
    sys.exit(main())
