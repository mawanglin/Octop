#!/usr/bin/env python3
"""文稿 → SRT 字幕（按语速分配时间轴），或检查已有 SRT。不需要 ffmpeg。

Usage:
    python scripts/make_srt.py script.md -o subs.srt [--rate 4] [--max-chars 16] [--start 0]
    python scripts/make_srt.py --check subs.srt

输入可以是：
  - 普通文稿：每句按语速依次排时间；
  - 带时间段的视频脚本：用 "## [0:00-0:03] 段落名" 标出时间段，段内以
    "口播：" "台词：" "旁白：" 开头的行（或没有前缀的普通行）作为字幕文字，
    字幕会按字数分配在该时间段内。"画面：" "字幕：" "音效：" 等行不进字幕。
字幕约定：每条不超过 --max-chars 字（竖屏建议 12–16，横屏 18–22），去掉句末标点。
Exit codes: 0 ok, 3 --check 发现问题, 1 输入错误。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SPOKEN_PREFIX = re.compile(r"^(口播|台词|旁白|解说|配音|人声)[:：]\s*")
SKIP_PREFIX = re.compile(
    r"^(画面|字幕|音效|音乐|BGM|镜头|景别|运镜|备注|时长|道具|场景)[:：]", re.I
)
SEGMENT = re.compile(r"^#{2,3}\s*\[(\d+:\d{1,2}(?:\.\d+)?)\s*[-–~]\s*(\d+:\d{1,2}(?:\.\d+)?)\]")
BREAK = "。！？!?；;…"
SOFT = "，,、：:"
TRAIL = "。！？!?；;，,、：:…"


@dataclass
class Cue:
    start: float
    end: float
    text: str


def to_seconds(value: str) -> float:
    total = 0.0
    for part in value.split(":"):
        total = total * 60 + float(part)
    return total


def fmt_ts(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def units(text: str) -> float:
    """Display / reading length: CJK = 1, ASCII = 0.5."""
    return sum(1.0 if ord(ch) > 0x2E80 else 0.5 for ch in text if not ch.isspace())


def split_lines(text: str, max_chars: int) -> list[str]:
    """Split into subtitle-sized chunks at punctuation, then by length."""
    sentences: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in BREAK:
            sentences.append(buf)
            buf = ""
    if buf.strip():
        sentences.append(buf)
    chunks: list[str] = []
    for sentence in sentences:
        parts: list[str] = []
        cur = ""
        for ch in sentence:
            cur += ch
            if ch in SOFT and units(cur) >= max_chars * 0.5:
                parts.append(cur)
                cur = ""
        if cur.strip():
            parts.append(cur)
        for part in parts:
            part = part.strip()
            while units(part) > max_chars:
                cut, width = 0, 0.0
                for i, ch in enumerate(part):
                    width += 1.0 if ord(ch) > 0x2E80 else 0.5
                    if width > max_chars:
                        cut = i
                        break
                chunks.append(part[:cut])
                part = part[cut:].strip()
            if part:
                chunks.append(part)
    cleaned = []
    for c in chunks:
        c = c.strip().rstrip(TRAIL).replace("，", " ").replace(",", " ").strip()
        if c:
            cleaned.append(c)
    return cleaned


def parse_script(source: str) -> list[tuple[float | None, float | None, str]]:
    """Return (start, end, spoken_text) segments; times None for plain text."""
    lines = source.replace("\r\n", "\n").split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                lines = lines[i + 1 :]
                break
    segments: list[tuple[float | None, float | None, str]] = []
    start = end = None
    buf: list[str] = []

    def flush() -> None:
        if buf:
            segments.append((start, end, "".join(buf)))

    for raw in lines:
        line = raw.strip()
        m = SEGMENT.match(line)
        if m:
            flush()
            buf = []
            start, end = to_seconds(m.group(1)), to_seconds(m.group(2))
            continue
        if not line or line.startswith("#") or line.startswith("|") or SKIP_PREFIX.match(line):
            continue
        line = SPOKEN_PREFIX.sub("", line)
        line = re.sub(r"[*_`>]", "", line)
        if line:
            buf.append(line if line[-1] in TRAIL else line + "。")
    flush()
    return segments


def build_cues(source: str, rate: float, max_chars: int, start: float, gap: float) -> list[Cue]:
    cues: list[Cue] = []
    clock = start
    for seg_start, seg_end, text in parse_script(source):
        chunks = split_lines(text, max_chars)
        if not chunks:
            continue
        if seg_start is not None and seg_end is not None:
            window = seg_end - seg_start
            total = sum(units(c) for c in chunks) or 1
            t = seg_start + start
            for c in chunks:
                dur = window * units(c) / total
                cues.append(Cue(t, t + max(dur - gap, 0.3), c))
                t += dur
            clock = seg_end + start
        else:
            for c in chunks:
                dur = max(1.0, units(c) / rate)
                cues.append(Cue(clock, clock + dur, c))
                clock += dur + gap
    return cues


def write_srt(cues: list[Cue]) -> str:
    return "".join(
        f"{i}\n{fmt_ts(c.start)} --> {fmt_ts(c.end)}\n{c.text}\n\n"
        for i, c in enumerate(cues, start=1)
    )


def parse_srt(text: str) -> list[Cue]:
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        rows = block.strip().split("\n")
        if len(rows) < 2:
            continue
        idx = 1 if "-->" in rows[1] else 0
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", rows[idx])
        if not m:
            raise ValueError(f"无法解析时间轴：{rows[idx]!r}")
        g = [int(x) for x in m.groups()]
        a = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        b = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        cues.append(Cue(a, b, "\n".join(rows[idx + 1 :])))
    return cues


def check(cues: list[Cue], max_chars: int, max_cps: float) -> list[str]:
    issues = []
    for i, c in enumerate(cues, start=1):
        dur = c.end - c.start
        if dur <= 0:
            issues.append(f"第 {i} 条：结束时间早于开始时间")
            continue
        for line in c.text.split("\n"):
            if units(line) > max_chars:
                issues.append(f"第 {i} 条：单行 {units(line):g} 字，超过 {max_chars} 字")
        if dur < 0.7:
            issues.append(f"第 {i} 条：只显示 {dur:.2f} 秒，观众来不及看")
        cps = units(c.text) / dur
        if cps > max_cps:
            issues.append(f"第 {i} 条：每秒 {cps:.1f} 字，超过 {max_cps:g} 字/秒，阅读压力大")
        if i > 1 and c.start < cues[i - 2].end - 0.01:
            issues.append(f"第 {i} 条：与上一条时间重叠")
        if c.text.strip() and c.text.strip()[-1] in "。，,":
            issues.append(f"第 {i} 条：字幕末尾一般不加句号、逗号")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("input", nargs="?", help="文稿或视频脚本 Markdown")
    parser.add_argument("-o", "--output", help="输出 .srt")
    parser.add_argument("--rate", type=float, default=4.0, help="语速（字/秒），默认 4")
    parser.add_argument("--max-chars", type=int, default=16, help="每条字幕最多字数，默认 16")
    parser.add_argument("--start", type=float, default=0.0, help="整体偏移秒数")
    parser.add_argument("--gap", type=float, default=0.1, help="字幕间隔秒数")
    parser.add_argument("--check", metavar="SRT", help="检查已有 SRT 文件")
    parser.add_argument("--max-cps", type=float, default=7.0, help="检查用：每秒最多字数")
    args = parser.parse_args(argv)
    try:
        if args.check:
            cues = parse_srt(Path(args.check).read_text(encoding="utf-8-sig"))
            issues = check(cues, args.max_chars, args.max_cps)
            if not issues:
                print(f"共 {len(cues)} 条字幕，未发现问题")
                return 0
            print(f"共 {len(cues)} 条字幕，发现 {len(issues)} 处问题：")
            for issue in issues:
                print(f"- {issue}")
            return 3
        if not args.input or not args.output:
            parser.error("需要输入文件和 -o 输出路径，或使用 --check")
        cues = build_cues(
            Path(args.input).read_text(encoding="utf-8"),
            args.rate,
            args.max_chars,
            args.start,
            args.gap,
        )
    except (OSError, ValueError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    if not cues:
        print("没有找到可以做字幕的文字", file=sys.stderr)
        return 1
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(write_srt(cues), encoding="utf-8")
    print(f"已生成 {out}：{len(cues)} 条，时长 {cues[-1].end:.1f} 秒")
    for issue in check(cues, args.max_chars, args.max_cps):
        print(f"提示：{issue}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
