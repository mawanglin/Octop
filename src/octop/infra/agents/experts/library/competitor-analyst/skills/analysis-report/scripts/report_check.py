#!/usr/bin/env python3
"""竞品分析报告质量检查：结构、证据、时效、竞品覆盖、建议可执行性，按高质量报告的标准逐项把关。

Usage:
    python scripts/report_check.py 报告.md [--competitors Kimi,豆包,DeepSeek] [--json]

检查项：
  结构   开头有核心结论/摘要；有建议（行动）部分且至少 3 条；有信息来源或研究方法说明
  证据   含数字的段落和表格是否标注来源（链接、[1] 角标、“来源：”）；“第一、最大、领先”等
         判断是否有依据；“据说、网传”等低可信表述；全文引用数量
  时效   是否写明数据截至时间 / 获取日期
  覆盖   --competitors 中的每个竞品是否都被分析到（至少出现 3 次）
  可读   超长段落（超过 300 字）、全文过短
只检查形式，不判断结论对错；命中项需要作者确认或补充。
Exit codes: 0 通过, 3 有需要补充的地方, 1 输入错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SUMMARY = re.compile(
    r"核心结论|结论摘要|执行摘要|摘要|一页速览|关键发现|Executive Summary|TL;?DR", re.I
)
ADVICE = re.compile(r"建议|行动|对策|策略|下一步|启示|机会|Recommendation", re.I)
METHOD = re.compile(
    r"信息来源|数据来源|资料来源|参考资料|参考文献|方法|数据说明|附录|Sources?|References?",
    re.I,
)
CITATION = re.compile(
    r"\]\(https?://|https?://\S+|\[\^?\d+\]|来源[:：]|数据来源[:：]|出处[:：]|据[^，。\s]{2,20}(?:数据|报告|统计|显示|公告|财报)"
)
FACT_NUMBER = re.compile(
    r"\d[\d,.]*\s*(?:%|％|万|亿|千|元|美元|人|次|个|款|家|倍|分|星|小时|天|月|MAU|DAU|GMV|ARR)",
    re.I,
)
ABSOLUTE = re.compile(r"第一|最大|最多|最强|最好|唯一|领先|遥遥|碾压|垄断|绝对|全网最")
HEARSAY = re.compile(r"据说|听说|网传|传闻|坊间|据悉(?!.{0,10}(?:公告|财报|官方))")
DATED = re.compile(
    r"(?:截至|截止|获取(?:时间|日期)?|数据时间|统计时间|更新于|查询于)[^\n]{0,12}?\d{4}\s*[年\-/.]\s*\d{1,2}"
)


def parse(text: str) -> list[dict[str, Any]]:
    """Sections: heading, level, paragraphs (list of (kind, text)) where kind is para/table/list."""
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                lines = lines[i + 1 :]
                break
    sections: list[dict[str, Any]] = [{"heading": "（开头）", "level": 0, "blocks": []}]
    table: list[str] = []
    for raw in [*lines, ""]:
        line = raw.strip()
        if line.startswith("|"):
            table.append(line)
            continue
        if table:
            sections[-1]["blocks"].append(("table", "\n".join(table)))
            table = []
        m = re.match(r"^(#{1,4})\s+(.+)$", line)
        if m:
            sections.append({"heading": m.group(2).strip(), "level": len(m.group(1)), "blocks": []})
        elif line and not line.startswith("<!--"):
            kind = "list" if re.match(r"^(?:[-*+]|\d+[.、)])\s+", line) else "para"
            sections[-1]["blocks"].append((kind, line))
    return sections


def check(text: str, competitors: list[str]) -> dict[str, Any]:
    sections = parse(text)
    body = "\n".join(t for s in sections for _, t in s["blocks"])
    chars = len(re.sub(r"\s", "", body))
    headings = [s["heading"] for s in sections[1:]]
    issues: list[str] = []
    notes: list[dict[str, str]] = []

    early = [s for s in sections[1:] if s["level"] >= 2][:3]
    if not any(SUMMARY.search(s["heading"]) for s in early):
        issues.append(
            "开头三个小节里没有“核心结论 / 摘要”：高质量报告结论先行，读者 1 分钟内要能拿到答案"
        )
    advice = [s for s in sections if ADVICE.search(s["heading"])]
    if not advice:
        issues.append("没有“建议 / 行动”部分：分析要落到“我们该怎么做”")
    else:
        items = sum(1 for s in advice for k, _ in s["blocks"] if k == "list") or sum(
            len(s["blocks"]) for s in advice
        )
        if items < 3:
            issues.append(
                f"建议部分只有 {items} 条：至少 3 条，每条写清做什么、为什么（对应哪个发现）、优先级"
            )
    if not any(METHOD.search(h) for h in headings):
        issues.append("没有“信息来源 / 研究方法”部分：列出数据来源、获取时间、样本范围和局限")
    if not DATED.search(text):
        issues.append(
            "没有写明数据截至时间或获取日期（如“数据截至 2026 年 10 月”）：互联网产品变化快，没有时间的数据无法判断是否过时"
        )

    citations = len(CITATION.findall(text))
    for s in sections:
        if METHOD.search(s["heading"]):
            continue  # the sources section itself
        blocks = s["blocks"]
        # Recommendations carry targets and plans, not facts that need a source.
        planning = bool(ADVICE.search(s["heading"]))
        for i, (kind, t) in enumerate(blocks):
            nxt = blocks[i + 1][1] if i + 1 < len(blocks) else ""
            cited = bool(CITATION.search(t)) or (kind == "table" and bool(CITATION.search(nxt)))
            if kind == "table":
                if FACT_NUMBER.search(t) and not cited:
                    notes.append(
                        {"类型": "表格无来源", "位置": s["heading"], "内容": t.split("\n")[0][:40]}
                    )
                continue
            if FACT_NUMBER.search(t) and not cited and not planning:
                notes.append({"类型": "数据无来源", "位置": s["heading"], "内容": t[:50]})
            if ABSOLUTE.search(t) and not cited:
                word = ABSOLUTE.search(t).group()  # type: ignore[union-attr]
                notes.append(
                    {"类型": "判断无依据", "位置": s["heading"], "内容": f"“{word}”：{t[:40]}"}
                )
            if HEARSAY.search(t):
                notes.append({"类型": "低可信表述", "位置": s["heading"], "内容": t[:50]})
            if kind == "para" and len(re.sub(r"\s", "", t)) > 300:
                notes.append({"类型": "段落过长", "位置": s["heading"], "内容": t[:30]})
    if citations == 0:
        issues.append(
            "全文没有任何来源标注：每个关键数据和判断都要能追溯（链接、[1] 角标或“来源：”）"
        )

    coverage = {}
    for name in competitors:
        coverage[name] = len(re.findall(re.escape(name), body, re.I))
        if coverage[name] < 3:
            issues.append(f"竞品“{name}”只出现 {coverage[name]} 次，分析可能不充分")
    if chars < 1500:
        issues.append(f"正文约 {chars} 字，偏短：深度竞品分析通常 3000 字以上（速览可忽略）")

    return {
        "字数": chars,
        "小节": len(headings),
        "表格": sum(1 for s in sections for k, _ in s["blocks"] if k == "table"),
        "引用": citations,
        "竞品出现次数": coverage,
        "问题": issues,
        "待确认": notes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("input")
    parser.add_argument("--competitors", default="", help="逗号分隔的竞品名称")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        text = Path(args.input).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"失败：无法读取 {args.input}：{exc}", file=sys.stderr)
        return 1
    names = [x.strip() for x in args.competitors.replace("，", ",").split(",") if x.strip()]
    res = check(text, names)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(
            f"约 {res['字数']} 字，{res['小节']} 个小节，{res['表格']} 张表，{res['引用']} 处来源标注"
        )
        if res["竞品出现次数"]:
            print("竞品覆盖：" + "，".join(f"{k} {v} 次" for k, v in res["竞品出现次数"].items()))
        for issue in res["问题"]:
            print(f"- [需补充] {issue}")
        if res["待确认"]:
            print(
                f"\n逐段提示 {len(res['待确认'])} 处（补来源、改成有依据的表述，或确认无误后保留）："
            )
            for n in res["待确认"][:40]:
                print(f"- [{n['类型']}] {n['位置']}：{n['内容']}")
        if not res["问题"] and not res["待确认"]:
            print("结构、证据和时效检查都通过。")
    return 3 if res["问题"] or res["待确认"] else 0


if __name__ == "__main__":
    sys.exit(main())
