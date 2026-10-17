#!/usr/bin/env python3
"""公文规范检查：读取 docx_build.py 使用的 Markdown 稿，列出不合规之处。

Usage:
    python scripts/gov_lint.py draft.md [--doc-type 请示]

检查项：层次序数是否连续、日期写法、中文语境中的半角标点、标题标点和长度、
发文字号格式、文种专用要求（请示结尾、报告不得夹带请示事项、函的结语）、附件说明。
这是辅助检查，不替代人工审核。Exit codes: 0 无问题, 3 有问题, 1 输入错误。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from docx_build import InputError, parse_markdown

DOC_TYPES = (
    "决议", "决定", "命令", "公报", "公告", "通告", "意见", "通知", "通报",
    "报告", "请示", "批复", "议案", "函", "纪要",
    "方案", "规划", "计划", "要点", "办法", "规定", "细则", "汇报", "讲话", "总结",
)  # fmt: skip
CN_DIGITS = "零一二三四五六七八九"
LEVELS = (
    ("一、", re.compile(r"^([一二三四五六七八九十百]+)、")),
    ("（一）", re.compile(r"^（([一二三四五六七八九十百]+)）")),
    ("1.", re.compile(r"^(\d+)[．.]")),
    ("（1）", re.compile(r"^（(\d+)）")),
)
CJK = r"[一-鿿]"


def cn_to_int(text: str) -> int:
    """一 → 1, 十二 → 12, 二十 → 20 (enough for heading numbers)."""
    if text.isdigit():
        return int(text)
    if "百" in text:
        return -1
    if "十" in text:
        tens, _, ones = text.partition("十")
        return (CN_DIGITS.index(tens) if tens else 1) * 10 + (CN_DIGITS.index(ones) if ones else 0)
    return CN_DIGITS.index(text) if len(text) == 1 and text in CN_DIGITS else -1


def int_to_cn(n: int) -> str:
    """1 → 一, 12 → 十二, 20 → 二十 (heading numbers only)."""
    if n < 10:
        return CN_DIGITS[n]
    tens, ones = divmod(n, 10)
    return (CN_DIGITS[tens] if tens > 1 else "") + "十" + (CN_DIGITS[ones] if ones else "")


def lint(source: str, doc_type: str | None = None) -> list[str]:
    meta, blocks = parse_markdown(source)
    issues: list[str] = []
    title = next((b.text for b in blocks if b.kind == "title"), meta.get("标题", ""))
    lines = [b.text for b in blocks if b.kind not in ("title", "table", "pagebreak")]
    body = "\n".join(lines)

    # 标题
    if not title:
        issues.append("缺少标题（第一行写“# 标题”）")
    else:
        plain = title.replace("\\n", "")
        if re.search(r"[，。；！？,.;!?]", re.sub(r"《[^》]*》", "", plain)):
            issues.append("标题中除书名号等必要标点外一般不用标点符号")
        if len(plain) > 20 and "\\n" not in title:
            issues.append(
                f"标题 {len(plain)} 字，2 号字每行约 20 字，会自动回行；"
                "建议在词意完整处用“\\n”手动分行，使各行对称"
            )
        stem = plain.rstrip("。.，,；;！!？? ")
        guessed = next((t for t in DOC_TYPES if stem.endswith(t)), None)
        doc_type = doc_type or guessed
        if guessed is None and not doc_type:
            issues.append("标题未以文种结尾（如“……的通知”“……的请示”），请确认文种")

    # 层次序数连续性
    counters = [0, 0, 0, 0]
    for text in lines:
        for level, (label, pattern) in enumerate(LEVELS):
            m = pattern.match(text)
            if not m:
                continue
            n = cn_to_int(m.group(1))
            expected = counters[level] + 1
            if n != expected:
                want = label.replace("一", int_to_cn(expected)).replace("1", str(expected))
                issues.append(f"层次序数不连续：“{text[:12]}…”此处应为“{want}”")
            counters[level] = n
            for deeper in range(level + 1, 4):
                counters[deeper] = 0
            break
        if re.match(r"^第[一二三四五六七八九十]+[，、,]", text):
            issues.append(f"“{text[:8]}…”：结构层次序数应使用“一、（一）1.（1）”")

    # 日期
    for m in re.finditer(r"(?<!\d)\d{4}[./-]\d{1,2}[./-]\d{1,2}(?!\d)", body):
        issues.append(f"日期“{m.group()}”应写作“××××年×月×日”")
    date = meta.get("日期", "")
    if date and not re.fullmatch(r"\d{4}年[1-9]\d?月[1-9]\d?日", date):
        issues.append(
            f"成文日期“{date}”应用阿拉伯数字写全年月日，月、日不编虚位（如 2026年1月5日）"
        )

    # 半角标点
    for m in re.finditer(rf"(?<={CJK})[,;:?!()]|[,;:?!()](?={CJK})", body):
        context = body[max(0, m.start() - 4) : m.end() + 4].replace("\n", " ")
        issues.append(f"中文语境使用了半角标点“{m.group()}”：…{context}…，应改为全角")
        if len(issues) > 40:
            break

    # 发文字号
    number = meta.get("发文字号", "")
    if number:
        if re.search(r"[\[\]【】()（）]\s*\d{4}", number):
            issues.append(f"发文字号“{number}”年份应使用六角括号〔〕")
        elif not re.fullmatch(r".+〔\d{4}〕\d+号", number):
            issues.append(f"发文字号“{number}”格式应为“机关代字〔年份〕序号号”，序号不编虚位")
        if re.search(r"〕0\d", number):
            issues.append("发文字号序号不编虚位（如 1 号不写成 01 号）")
    if meta.get("发文机关标志") and not meta.get("发文字号"):
        issues.append("有版头时应填写发文字号")
    if meta.get("签发人") and doc_type not in ("请示", "报告", None):
        issues.append("签发人只用于上行文（请示、报告）")

    # 文种要求
    tail = "".join(lines[-3:])
    if doc_type == "请示":
        if not re.search(
            r"(妥否|当否|是否可行).{0,3}请.{0,2}(批示|审批|批复)|请.{0,2}(批准|审批|批示)", tail
        ):
            issues.append("请示结尾通常为“妥否，请批示”或“特此请示，请予审批”")
        if not meta.get("主送"):
            issues.append("请示应只主送一个上级机关")
        elif re.search(r"[，、,]", meta["主送"]):
            issues.append("请示一般只主送一个上级机关，不多头主送")
    if doc_type == "报告" and re.search(r"妥否|请批示|请批准|请审批|请予批复", body):
        issues.append("报告中不得夹带请示事项")
    if doc_type == "函" and not re.search(r"函复|函告|盼复|请予支持|为盼", tail):
        issues.append("函的结尾通常为“请函复”“特此函告”或“盼复”")
    if doc_type == "通知" and doc_type and "印发" in title and not meta.get("附件"):
        issues.append("印发类通知应附所印发的文件（填写 附件）")

    # 附件说明
    if re.search(r"见附件|附件\d", body) and not meta.get("附件"):
        issues.append("正文提到附件，但未填写附件说明（front matter 中的 附件）")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("input")
    parser.add_argument("--doc-type", help="文种（默认从标题末尾推断）")
    args = parser.parse_args(argv)
    try:
        issues = lint(Path(args.input).read_text(encoding="utf-8"), args.doc_type)
    except (OSError, InputError) as exc:
        print(f"检查失败：{exc}", file=sys.stderr)
        return 1
    if not issues:
        print("未发现格式问题（辅助检查，仍需人工审核内容）")
        return 0
    print(f"发现 {len(issues)} 处问题：")
    for i, issue in enumerate(dict.fromkeys(issues), start=1):
        print(f"{i}. {issue}")
    return 3


if __name__ == "__main__":
    sys.exit(main())
