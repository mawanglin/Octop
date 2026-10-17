#!/usr/bin/env python3
"""估算讲话稿的朗读时长，并按 ## 小标题分段统计。

Usage:
    python scripts/speech_timer.py speech.md [--rate 230] [--target 10]

--rate    每分钟字数。正式讲话约 200–230，致辞/主持约 230–250，演讲比赛约 250–280。
--target  目标分钟数；给出需要增删的大致字数。
Exit codes: 0 ok, 1 读取失败。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def spoken_units(text: str) -> int:
    """Characters as read aloud: CJK chars + each number/word counts by its syllables (rough)."""
    text = re.sub(r"<!--.*?-->|\[[^\]]*\]\([^)]*\)|[#>*`|]", "", text)
    cjk = len(re.findall(r"[一-鿿]", text))
    # 一个数字串大约读作 len 个音节（"2026" → 二零二六），英文单词约 1.5 个音节。
    digits = sum(len(m) for m in re.findall(r"\d+", text))
    words = len(re.findall(r"[A-Za-z]+", text))
    return cjk + digits + round(words * 1.5)


def strip_front_matter(source: str) -> str:
    lines = source.replace("\r\n", "\n").split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1 :])
    return source


def fmt(seconds: float) -> str:
    m, s = divmod(round(seconds), 60)
    return f"{m} 分 {s:02d} 秒"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("input")
    parser.add_argument("--rate", type=int, default=230, help="每分钟字数，默认 230")
    parser.add_argument("--target", type=float, help="目标时长（分钟）")
    args = parser.parse_args(argv)
    try:
        text = strip_front_matter(Path(args.input).read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"无法读取：{exc}", file=sys.stderr)
        return 1

    sections: list[tuple[str, str]] = []
    current, buf = "开场", []
    for line in text.split("\n"):
        if line.startswith("# "):
            continue  # 标题不念
        if line.startswith("## "):
            sections.append((current, "\n".join(buf)))
            current, buf = line[3:].strip(), [line[3:]]
        else:
            buf.append(line)
    sections.append((current, "\n".join(buf)))

    total = 0
    print(f"语速 {args.rate} 字/分钟")
    for name, body in sections:
        units = spoken_units(body)
        if not units:
            continue
        total += units
        print(f"- {name[:24]}：{units} 字，约 {fmt(units / args.rate * 60)}")
    print(f"合计：{total} 字，约 {fmt(total / args.rate * 60)}")
    if args.target:
        want = round(args.target * args.rate)
        diff = want - total
        if abs(diff) <= want * 0.05:
            print(f"与目标 {args.target:g} 分钟基本吻合")
        elif diff > 0:
            print(f"比目标 {args.target:g} 分钟短，约需增加 {diff} 字")
        else:
            print(f"比目标 {args.target:g} 分钟长，约需删减 {-diff} 字")
    return 0


if __name__ == "__main__":
    sys.exit(main())
