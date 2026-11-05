#!/usr/bin/env python3
"""原创性检查：初稿有多少内容是从来源里原样搬过来的（防洗稿）。

Usage:
    python scripts/overlap_check.py 文章包.md [--min-run 18] [--extra 原文1.txt --extra 原文2.txt] [--json]

做法：去掉标点和空白后，找出初稿里和来源逐字相同、长度不少于 --min-run 的连续片段，
统计它们占初稿正文的比例。加引号的引语、标题、小标题和参考来源不算。
默认只和线索包里的“摘录”比对；摘录很短，想查得彻底，用 --extra 给出来源页面的完整正文。
≥50% 判为“必须处理”（大段搬运），25%–50% 为“请确认”。引用必须加引号并标来源，改写要换说法、换结构。
Exit codes: 0 没有“必须处理”项, 3 有, 1 输入错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import article_pack as ap  # noqa: E402

QUOTE_RE = re.compile(r"[“「『\"][^”」』\"\n]{6,}[”」』\"]")
MARK_RE = re.compile(r"\[(?:S\d+(?:\s*[,，、]\s*S\d+)*|推算)\]")
MUST_AT, CONFIRM_AT = 0.5, 0.25


def squash(text: str) -> str:
    return re.sub(r"[\W_]+", "", text)


def draft_body(draft: str) -> str:
    lines: list[str] = []
    for line in draft.splitlines():
        s = line.strip()
        if re.match(r"^#{2,6}\s*(?:参考来源|参考资料|参考链接)\s*$", s):
            break
        if (
            not s
            or s.startswith("#")
            or s.startswith("![")
            or re.match(r"^(?:摘要|导语)\s*[：:]", s)
        ):
            continue
        lines.append(s)
    return QUOTE_RE.sub("", MARK_RE.sub("", "\n".join(lines)))


def covered_runs(body: str, corpus: str, min_run: int) -> list[tuple[int, int]]:
    """Spans of *body* (indexes into the squashed text) that appear verbatim in *corpus* for >= min_run chars."""
    if len(body) < min_run or len(corpus) < min_run:
        return []
    grams = {corpus[i : i + min_run] for i in range(len(corpus) - min_run + 1)}
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for i in range(len(body) - min_run + 1):
        hit = body[i : i + min_run] in grams
        if hit:
            if start is None:
                start = i
            end = i + min_run
        elif start is not None:
            spans.append((start, end))
            start = None
    if start is not None:
        spans.append((start, end))
    return spans


def analyse(pack: ap.Pack, extras: dict[str, str], min_run: int) -> dict[str, object]:
    body = squash(draft_body(pack.draft()))
    corpora = {s.id: squash(s.excerpt) for s in pack.sources() if s.status != "不可用"}
    corpora.update({name: squash(text) for name, text in extras.items()})
    covered = [False] * len(body)
    per_source: dict[str, dict[str, object]] = {}
    longest = ("", "", 0)
    for name, corpus in corpora.items():
        spans = covered_runs(body, corpus, min_run)
        chars = sum(e - s for s, e in spans)
        for s, e in spans:
            for i in range(s, e):
                covered[i] = True
            if e - s > longest[2]:
                longest = (name, body[s:e], e - s)
        if chars:
            per_source[name] = {
                "重合字数": chars,
                "占正文": round(chars / max(len(body), 1), 3),
                "最长连续片段": max(e - s for s, e in spans),
            }
    total = sum(covered)
    ratio = total / len(body) if body else 0.0
    level = "必须处理" if ratio >= MUST_AT else "请确认" if ratio >= CONFIRM_AT else "正常"
    return {
        "正文字数": len(body),
        "逐字重合字数": total,
        "逐字重合比例": round(ratio, 3),
        "判断": level,
        "分来源": per_source,
        "最长连续片段": {"来源": longest[0], "长度": longest[2], "片段": longest[1][:80]}
        if longest[2]
        else None,
        "比对的来源": sorted(corpora),
        "最小片段": min_run,
    }


def render(res: dict[str, object]) -> str:
    out = [
        f"原创性：正文 {res['正文字数']} 字，与来源逐字相同的连续片段（≥{res['最小片段']} 字）共 {res['逐字重合字数']} 字，占 {float(res['逐字重合比例']):.0%}  → {res['判断']}",  # type: ignore[arg-type]
        f"比对的来源：{'、'.join(res['比对的来源'])}",  # type: ignore[arg-type]
    ]
    for name, info in res["分来源"].items():  # type: ignore[attr-defined]
        out.append(
            f"- {name}：{info['重合字数']} 字（{float(info['占正文']):.0%}），最长连续 {info['最长连续片段']} 字"
        )
    if res["最长连续片段"]:
        lg = res["最长连续片段"]
        out.append(f"最长的一段（来自 {lg['来源']}，{lg['长度']} 字，已去标点）：{lg['片段']}")  # type: ignore[index]
    if res["判断"] != "正常":
        out.append("处理：逐字相同的部分要么加引号并标来源，要么换成自己的说法和结构。")
    out.append(
        "说明：默认只比对线索包里的摘录；摘录很短，想查得彻底请用 --extra 提供来源页面的完整正文。"
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="原创性检查")
    parser.add_argument("pack")
    parser.add_argument("--min-run", type=int, default=18)
    parser.add_argument(
        "--extra", action="append", default=[], help="来源页面的完整正文（可多次给出）"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.min_run < 6:
        print("--min-run 不能小于 6，太短会把常用词也算进去", file=sys.stderr)
        return 1
    extras: dict[str, str] = {}
    for i, name in enumerate(args.extra, 1):
        try:
            extras[f"附加正文{i}"] = Path(name).read_text(encoding="utf-8-sig")
        except OSError as exc:
            print(f"读取 {name} 失败：{exc}", file=sys.stderr)
            return 1
    try:
        pack = ap.read_pack(Path(args.pack))
    except SystemExit as exc:
        print(exc.code, file=sys.stderr)
        return 1
    if "初稿" not in pack.sections:
        print("文章包里还没有初稿", file=sys.stderr)
        return 1
    res = analyse(pack, extras, args.min_run)
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else render(res))
    return 3 if res["判断"] == "必须处理" else 0


if __name__ == "__main__":
    sys.exit(main())
