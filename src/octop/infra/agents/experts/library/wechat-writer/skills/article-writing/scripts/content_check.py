#!/usr/bin/env python3
"""内容合规自查：广告法极限用语、医疗/金融承诺、诱导分享等高风险表达。

Usage:
    python scripts/content_check.py article.md

只做关键词提示，命中不等于违规，未命中也不等于合规；最终以平台规则和法律意见为准。
Exit codes: 0 未命中, 3 有命中, 1 读取失败。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RULES: dict[str, tuple[str, list[str]]] = {
    "广告法极限用语": (
        "《广告法》第九条禁止使用“国家级”“最高级”“最佳”等用语；商业推广内容尤其注意",
        [
            r"最(?:佳|好|高级|优|强|大|低价|便宜|先进|新科技|受欢迎|畅销|热销)",
            r"第一(?:品牌|名|家)?(?![次天步个])",
            r"(?<!之)唯一",
            r"首(?:个|家|选|款)",
            r"顶(?:级|尖)",
            r"极致",
            r"国家级",
            r"世界级",
            r"全网(?:最|第一|销量|独家)",
            r"\d{2,3}\s*%\s*(?:有效|好评|满意)",
            r"万能",
            r"绝对",
            r"史无前例",
            r"独家",
            r"销量冠军",
            r"(?i)no\.?\s*1\b",
            r"永久",
        ],
    ),
    "医疗健康功效": (
        "非医疗、药品、医疗器械广告不得涉及疾病治疗功能；保健食品不得宣称疗效",
        [
            r"根治",
            r"治愈",
            r"药到病除",
            r"包治",
            r"无(?:任何)?副作用",
            r"疗效",
            r"(?:降|治)(?:血压|血糖|血脂)",
            r"抗癌",
            r"排毒",
            r"减肥神器",
            r"7\s*天(?:瘦|见效)",
        ],
    ),
    "金融投资承诺": (
        "不得对未来收益作出保证性承诺，不得暗示保本、无风险",
        [r"稳赚", r"保本", r"零风险", r"无风险", r"(?:保证|稳定)收益", r"翻倍", r"躺赚"],
    ),
    "诱导分享/关注": (
        "公众号运营规范禁止以奖励或胁迫方式诱导分享、关注、点赞",
        [
            r"转发(?:到|至)?朋友圈.{0,8}(?:领|送|抽)",
            r"集赞",
            r"不转不是",
            r"分享到.{0,6}群.{0,8}(?:领|送)",
            r"关注.{0,6}(?:即可|才能).{0,6}(?:领|看|下载)",
        ],
    ),
    "夸大/绝对化表达": (
        "非广告内容也建议避免，影响可信度",
        [r"震惊", r"刷屏了", r"所有人都", r"100%", r"一定(?:能|会)", r"彻底解决"],
    ),
}


def check(text: str) -> list[tuple[str, str, str]]:
    """Return (category, match, context) for every hit, in text order."""
    hits: list[tuple[int, str, str, str]] = []
    for category, (_, patterns) in RULES.items():
        for pattern in patterns:
            for m in re.finditer(pattern, text):
                start, end = m.start(), m.end()
                context = text[max(0, start - 10) : end + 10].replace("\n", " ")
                hits.append((start, category, m.group(), context))
    hits.sort()
    seen: set[tuple[int, str]] = set()
    out: list[tuple[str, str, str]] = []
    for start, category, word, context in hits:
        if (start, word) in seen:
            continue
        seen.add((start, word))
        out.append((category, word, context))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("input")
    args = parser.parse_args(argv)
    try:
        text = Path(args.input).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"无法读取：{exc}", file=sys.stderr)
        return 1
    hits = check(text)
    if not hits:
        print("未命中高风险表达（关键词提示，仍需人工判断）")
        return 0
    print(f"命中 {len(hits)} 处需要留意的表达：")
    for category, (reason, _) in RULES.items():
        rows = [(w, c) for cat, w, c in hits if cat == category]
        if rows:
            print(f"\n【{category}】{reason}")
            for word, context in rows:
                print(f"- “{word}”：…{context}…")
    return 3


if __name__ == "__main__":
    sys.exit(main())
