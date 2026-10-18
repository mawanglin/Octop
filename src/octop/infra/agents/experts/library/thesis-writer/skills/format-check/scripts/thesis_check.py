#!/usr/bin/env python3
"""论文格式检查（.docx）：章节编号、图表编号与引用、参考文献引用对应关系、摘要关键词、字数。

Usage:
    python scripts/thesis_check.py 论文.docx [--json]

检查项：
  - 章节标题：第一章/第1章/1、1.1、1.1.1 编号是否连续、是否跳级；
  - 图表：图 2-1 / 表 3.2 / 图1 的编号是否按章连续、是否重复，正文中是否提到（如“如图 2-1 所示”）；
  - 参考文献（顺序编码制）：正文中的 [1] [2-4] [1,3] 是否都在参考文献表中、表中每条是否被引用、首次引用是否按顺序；
  - 中英文摘要和关键词是否齐全，关键词数量（一般 3–8 个）；
  - 正文字数（中文字符 + 英文单词，不含参考文献）。
只读原文件，不修改。字体、字号、页边距等版式请对照学校模板人工确认。Exit codes: 0 无问题, 1 发现问题或输入错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CN_NUM = {c: i for i, c in enumerate("零一二三四五六七八九十", start=0)}
CAPTION = re.compile(r"^\s*(图|表)\s*(\d+)(?:\s*[-.．—]\s*(\d+))?(?=\s|$|[一-鿿A-Za-z（(])")
MENTION = re.compile(r"(图|表)\s*(\d+(?:\s*[-.．—]\s*\d+)?)")
CITE = re.compile(r"\[(\d+(?:\s*[-–,，]\s*\d+)*)\]")
REF_HEAD = re.compile(r"^\s*(参考文献|References|REFERENCES|Bibliography)\s*$")


class CheckError(ValueError):
    pass


def cn_to_int(s: str) -> int:
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + CN_NUM[s[1]]
    if s.endswith("十"):
        return CN_NUM[s[0]] * 10
    if "十" in s:
        a, b = s.split("十")
        return CN_NUM[a] * 10 + CN_NUM[b]
    return CN_NUM[s]


def heading_number(text: str, style: str) -> tuple[int, ...] | None:
    m = re.match(r"^\s*第\s*([0-9一二三四五六七八九十]+)\s*章", text)
    if m:
        return (cn_to_int(m.group(1)),)
    m = re.match(r"^\s*(\d+(?:\.\d+){0,3})(?:\s+|[一-鿿])", text)
    if m and (style.lower().startswith(("heading", "标题")) or len(text) <= 40):
        nums = tuple(int(x) for x in m.group(1).split("."))
        if len(nums) == 1 and not style.lower().startswith(("heading", "标题")):
            return None  # "1 引言" only counts when styled as a heading; plain numbered lists are ignored
        return nums
    return None


def expand(cite: str) -> list[int]:
    out: list[int] = []
    for part in re.split(r"\s*[,，]\s*", cite):
        if re.search(r"[-–]", part):
            a, b = (int(x) for x in re.split(r"\s*[-–]\s*", part))
            out.extend(range(a, b + 1))
        elif part.strip():
            out.append(int(part))
    return out


def analyze(path: Path) -> dict[str, object]:
    try:
        from docx import Document
    except ImportError:  # pragma: no cover - environment check
        raise CheckError("需要 python-docx：pip install python-docx") from None
    doc = Document(str(path))
    paras = [(p.text.strip(), p.style.name if p.style is not None else "") for p in doc.paragraphs]
    paras = [(t, s) for t, s in paras if t]
    issues: list[str] = []

    ref_idx = next((i for i, (t, _s) in enumerate(paras) if REF_HEAD.match(t)), None)
    body = paras if ref_idx is None else paras[:ref_idx]
    refs = [] if ref_idx is None else paras[ref_idx + 1 :]
    # Stop the reference list at the next heading (致谢 / 附录).
    for k, (t, s) in enumerate(refs):
        if re.match(r"^\s*(致\s*谢|附\s*录|Acknowledg)", t) or s.lower().startswith(
            ("heading 1", "标题 1")
        ):
            refs = refs[:k]
            break

    # ---- headings
    last: tuple[int, ...] = ()
    headings = 0
    for t, s in body:
        num = heading_number(t, s)
        if num is None:
            continue
        headings += 1
        level = len(num)
        if level > len(last) + 1:
            issues.append(
                f"章节「{t[:20]}」跳级（上一个标题是 {'.'.join(map(str, last)) or '无'}）"
            )
        elif last:
            prefix = last[: level - 1]
            expected = (*prefix, last[level - 1] + 1) if level <= len(last) else (*last, 1)
            if num[:-1] == prefix and num != expected:
                issues.append(f"章节编号「{t[:20]}」不连续，应为 {'.'.join(map(str, expected))}")
            elif num[:-1] != prefix:
                issues.append(f"章节编号「{t[:20]}」与上级标题 {'.'.join(map(str, prefix))} 不一致")
        elif num != (1,) * level:
            issues.append(f"第一个标题「{t[:20]}」编号不是从 1 开始")
        last = num

    # ---- figures and tables
    captions: dict[str, list[tuple[int, int]]] = {"图": [], "表": []}
    caption_texts: set[str] = set()
    for t, _s in body:
        m = CAPTION.match(t)
        if m and len(t) <= 60:
            kind, a, b = m.group(1), int(m.group(2)), m.group(3)
            key = (a, int(b)) if b else (0, a)
            if key in captions[kind]:
                issues.append(f"{kind} {a}{'-' + b if b else ''} 编号重复")
            captions[kind].append(key)
            caption_texts.add(t)
    for kind, keys in captions.items():
        for (c1, n1), (c2, n2) in zip(keys, keys[1:], strict=False):
            if c1 == c2 and n2 != n1 + 1:
                issues.append(f"{kind}编号不连续：{_fmt(kind, c1, n1)} 之后是 {_fmt(kind, c2, n2)}")
            elif c2 != c1 and c2 > 0 and n2 != 1:
                issues.append(
                    f"{kind}编号：第 {c2} 章的第一个{kind}应为 {_fmt(kind, c2, 1)}，实际为 {_fmt(kind, c2, n2)}"
                )
    text_body = "\n".join(t for t, _s in body if t not in caption_texts)
    mentioned = {(k, re.sub(r"\s*[-.．—]\s*", "-", n)) for k, n in MENTION.findall(text_body)}
    for kind, keys in captions.items():
        for c, n in keys:
            label = f"{c}-{n}" if c else str(n)
            if (kind, label) not in mentioned:
                issues.append(
                    f"{_fmt(kind, c, n)} 在正文中没有被提到（建议写“如{_fmt(kind, c, n)} 所示”）"
                )

    # ---- citations
    order: list[int] = []
    for t, _s in body:
        for m in CITE.finditer(t):
            for n in expand(m.group(1)):
                if n not in order:
                    order.append(n)
    ref_count = 0
    for t, _s in refs:
        if re.match(r"^\s*\[?\d+\]?[.、\s]", t) or len(t) > 15:
            ref_count += 1
    if ref_idx is None:
        issues.append("没有找到“参考文献”标题")
    else:
        for n in order:
            if n > ref_count or n < 1:
                issues.append(f"正文引用了 [{n}]，但参考文献只有 {ref_count} 条")
        uncited = [i for i in range(1, ref_count + 1) if i not in order]
        if uncited:
            issues.append("参考文献中未被正文引用：" + "、".join(f"[{i}]" for i in uncited[:20]))
        firsts = [n for n in order if n <= ref_count]
        for a, b in zip(firsts, firsts[1:], strict=False):
            if b < a:
                issues.append(f"顺序编码制要求按首次引用顺序编号：[{b}] 首次出现在 [{a}] 之后")
                break

    # ---- abstract & keywords
    alltext = "\n".join(t for t, _s in paras)
    for label, pat in (("中文摘要", r"摘\s*要"), ("中文关键词", r"关键词|关键字"), ("英文摘要", r"\bAbstract\b|\bABSTRACT\b"),
                       ("英文关键词", r"Key\s*words|Keywords|KEY\s*WORDS")):  # fmt: skip
        if not re.search(pat, alltext):
            issues.append(f"没有找到{label}")
    m = re.search(r"(?:关键词|关键字)\s*[:：]\s*(.+)", alltext)
    if m:
        n = len([k for k in re.split(r"[;；,，、\s]+", m.group(1).strip()) if k])
        if not 3 <= n <= 8:
            issues.append(f"中文关键词 {n} 个，一般为 3–8 个")

    words = len(re.findall(r"[一-鿿]", text_body)) + len(re.findall(r"[A-Za-z]+", text_body))
    return {
        "文件": path.name,
        "正文字数": words,
        "标题数": headings,
        "图": len(captions["图"]),
        "表": len(captions["表"]),
        "引用编号数": len(order),
        "参考文献条数": ref_count,
        "问题": issues,
    }


def _fmt(kind: str, c: int, n: int) -> str:
    return f"{kind} {c}-{n}" if c else f"{kind} {n}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("input")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        res = analyze(Path(args.input))
    except (OSError, CheckError, ValueError, KeyError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    issues = res["问题"]
    assert isinstance(issues, list)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"{res['文件']}：正文约 {res['正文字数']} 字，{res['标题数']} 个标题，图 {res['图']} 个，表 {res['表']} 个，"
              f"引用 {res['引用编号数']} 篇，参考文献 {res['参考文献条数']} 条")  # fmt: skip
        print(f"发现 {len(issues)} 个问题" + ("：" if issues else ""))
        for i in issues:
            print(f"- {i}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
