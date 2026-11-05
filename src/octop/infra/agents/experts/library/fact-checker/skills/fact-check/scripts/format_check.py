#!/usr/bin/env python3
"""格式检查：按目标平台的限制检查标题、摘要、正文长度、图片、小标题层级和没处理完的占位符。

Usage:
    python scripts/format_check.py 文章包.md [--platform wechat|xiaohongshu|toutiao|generic]
                                   [--title-max N] [--digest-max N] [--body-min N] [--body-max N]
                                   [--base-dir 图片所在目录] [--json]

平台限制是常见经验值，以平台后台实际提示为准；不对的可以用参数覆盖：
    wechat       标题 5–64，摘要 ≤120，正文 300–20000 字
    xiaohongshu  标题 ≤20，正文 ≤1000 字，至少 1 个 #话题
    toutiao      标题 5–30，正文 ≥300 字
    generic      只检查结构和占位符
检查的是初稿原文（含 [S1] 来源标记），字数按去掉标记和空白后统计。
Exit codes: 0 没有“必须处理”项, 3 有, 1 输入错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import article_pack as ap  # noqa: E402

MUST, CONFIRM = "必须处理", "请确认"
MARK_RE = re.compile(r"\[(?:S\d+(?:\s*[,，、]\s*S\d+)*|推算)\]")
IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
PLACEHOLDER_RE = re.compile(
    r"〔待核实〕|\[待核实\]|待核实|TODO|待补充|XXX|＿{2,}|_{3,}|［[^］\n]{1,30}］|<此处[^>]*>|（此处[^）]*）"
)
PRESETS: dict[str, dict[str, int | None]] = {
    "wechat": {
        "title_min": 5,
        "title_max": 64,
        "digest_max": 120,
        "body_min": 300,
        "body_max": 20000,
    },
    "xiaohongshu": {
        "title_min": 1,
        "title_max": 20,
        "digest_max": None,
        "body_min": 1,
        "body_max": 1000,
    },
    "toutiao": {
        "title_min": 5,
        "title_max": 30,
        "digest_max": None,
        "body_min": 300,
        "body_max": None,
    },
    "generic": {
        "title_min": 1,
        "title_max": None,
        "digest_max": None,
        "body_min": 1,
        "body_max": None,
    },
}
LONG_PARAGRAPH = 300


@dataclass
class Finding:
    level: str
    where: str
    message: str


def parse_draft(draft: str) -> tuple[str, str, list[str]]:
    title, digest, lines = "", "", []
    for line in draft.splitlines():
        s = line.rstrip()
        if not title and re.match(r"^#\s+\S", s.strip()):
            title = s.strip().lstrip("# ").strip()
            continue
        m = re.match(r"^(?:摘要|导语)\s*[：:]\s*(.*)$", s.strip())
        if m and not digest:
            digest = m.group(1).strip()
            continue
        lines.append(s)
    return title, digest, lines


def count(text: str) -> int:
    return len(re.sub(r"\s", "", MARK_RE.sub("", text)))


def check(
    pack: ap.Pack, platform: str, limits: dict[str, int | None], base_dir: Path
) -> list[Finding]:
    out: list[Finding] = []

    def add(level: str, where: str, msg: str) -> None:
        out.append(Finding(level, where, msg))

    title, digest, lines = parse_draft(pack.draft())
    if not title:
        add(MUST, "标题", "没有一级标题（以“# ”开头的一行）")
    else:
        n = count(title)
        if limits["title_min"] and n < limits["title_min"]:
            add(MUST, "标题", f"标题只有 {n} 字，{platform} 至少 {limits['title_min']} 字")
        if limits["title_max"] and n > limits["title_max"]:
            add(MUST, "标题", f"标题 {n} 字，超过 {platform} 的 {limits['title_max']} 字上限")
        if re.search(r"[！!]{2,}|[？?]{2,}", title):
            add(CONFIRM, "标题", "标题里有连续的叹号或问号")
    if platform == "wechat" and not digest:
        add(CONFIRM, "摘要", "没有“摘要：”行；不写摘要时公众号会截取正文开头，可能不好看")
    if digest and limits["digest_max"] and count(digest) > limits["digest_max"]:
        add(MUST, "摘要", f"摘要 {count(digest)} 字，超过 {limits['digest_max']} 字上限")

    body = "\n".join(lines)
    in_refs = False
    paragraphs: list[tuple[int, str]] = []
    headings: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines, 1):
        s = line.strip()
        h = re.match(r"^(#{2,6})\s*(.*)$", s)
        if h:
            level, text = len(h.group(1)), h.group(2).strip()
            in_refs = bool(re.match(r"参考(?:来源|资料|链接)", text))
            headings.append((idx, level, text))
            if not text:
                add(MUST, f"第 {idx} 行", "有空的小标题")
            continue
        if s and not in_refs and not s.startswith(("![", ">", "-", "*", "|", "```")):
            paragraphs.append((idx, s))
    prev = 1
    for idx, level, _text in headings:
        if level > prev + 1:
            add(
                CONFIRM, f"第 {idx} 行", f"小标题从 {'#' * prev} 直接跳到 {'#' * level}，层级不连续"
            )
        prev = level

    n_body = count("\n".join(p for _, p in paragraphs))
    if limits["body_min"] and n_body < limits["body_min"]:
        add(MUST, "正文", f"正文 {n_body} 字，{platform} 至少 {limits['body_min']} 字")
    if limits["body_max"] and n_body > limits["body_max"]:
        add(MUST, "正文", f"正文 {n_body} 字，超过 {platform} 的 {limits['body_max']} 字上限")
    for idx, p in paragraphs:
        if count(p) > LONG_PARAGRAPH:
            add(CONFIRM, f"第 {idx} 行", f"一段有 {count(p)} 字，手机上读起来太长，建议拆段")

    for m in IMG_RE.finditer(body):
        alt, src = m.group(1).strip(), m.group(2)
        if not alt:
            add(CONFIRM, "图片", f"图片 {src} 没有说明文字（无障碍和排版都需要）")
        if src.startswith("http://"):
            add(MUST, "图片", f"图片 {src} 是 http 地址，平台要求 https")
        elif not re.match(r"^(?:https://|data:)", src) and not (base_dir / src).is_file():
            add(MUST, "图片", f"本地图片 {src} 找不到（相对于 {base_dir}）")
    if platform == "xiaohongshu" and not re.search(
        r"(?<![#\w])#[^\s#]+", re.sub(r"(?m)^#{1,6}(?:\s.*)?$", "", body)
    ):
        add(CONFIRM, "话题", "小红书笔记建议至少带 1 个 #话题")

    for idx, line in enumerate(lines, 1):
        for m in PLACEHOLDER_RE.finditer(line):
            add(MUST, f"第 {idx} 行", f"还有没处理完的占位符“{m.group()}”")
    if re.search(r"[！!]{3,}", body):
        add(CONFIRM, "正文", "有连续 3 个以上的叹号")
    rank = {MUST: 0, CONFIRM: 1}
    return sorted(out, key=lambda f: rank[f.level])


def render(findings: list[Finding], platform: str, limits: dict[str, int | None]) -> str:
    shown = "，".join(f"{k}={v}" for k, v in limits.items() if v)
    out = [f"格式检查（{platform}：{shown or '无限制'}）"]
    if not findings:
        out.append("没有发现问题。")
    for level in (MUST, CONFIRM):
        rows = [f for f in findings if f.level == level]
        if rows:
            out.append(f"\n## {level}")
            out += [f"- {f.where}：{f.message}" for f in rows]
    out.append("\n说明：平台限制是常见经验值，以平台后台实际提示为准。")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="格式检查")
    parser.add_argument("pack")
    parser.add_argument("--platform", default="wechat", choices=sorted(PRESETS))
    for name in ("title-max", "digest-max", "body-min", "body-max"):
        parser.add_argument(f"--{name}", type=int)
    parser.add_argument("--base-dir", help="本地图片的相对路径从这里找，默认是文章包所在目录")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        pack = ap.read_pack(Path(args.pack))
    except SystemExit as exc:
        print(exc.code, file=sys.stderr)
        return 1
    if "初稿" not in pack.sections:
        print("文章包里还没有初稿", file=sys.stderr)
        return 1
    limits = dict(PRESETS[args.platform])
    for key in ("title_max", "digest_max", "body_min", "body_max"):
        value = getattr(args, key)
        if value is not None:
            limits[key] = value
    base = Path(args.base_dir) if args.base_dir else Path(args.pack).resolve().parent
    findings = check(pack, args.platform, limits, base)
    if args.json:
        print(json.dumps([f.__dict__ for f in findings], ensure_ascii=False, indent=2))
    else:
        print(render(findings, args.platform, limits))
    return 3 if any(f.level == MUST for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
