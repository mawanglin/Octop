#!/usr/bin/env python3
"""商品标题与文案检查：长度、广告法极限用语、功效和医疗宣称、诱导好评与站外引流、关键词堆砌、核心关键词覆盖、标题重复。

Usage:
    python scripts/listing_check.py "标题文字" [--platform taobao] [--keywords 连衣裙,夏季,显瘦] [--category 化妆品]
    python scripts/listing_check.py 商品.csv [--platform pdd] [--keywords-col 关键词] [-o 检查结果.xlsx]

商品 CSV 需要“标题”列，可选“卖点”“详情”“关键词”（用 , 或 | 分隔）“类目”列；文案列也会检查违规词。
--platform：taobao / tmall（60 字符，中文算 2）、jd（90 字符）、pdd（60 字符，中文算 2）、douyin（30 字）——
            标题长度规则各平台会调整，以平台后台提示为准。
--category：化妆品、食品、保健食品、医疗器械等类目会额外检查功效宣称（如化妆品“祛斑”“生发”属于特殊用途，需要相应资质）。
等级：违规（广告法禁用的极限词、医疗宣称、诱导好评、站外引流）/ 风险（需要证明材料的宣称）/ 建议（长度、堆砌、关键词）。
本工具只做关键词筛查，不能替代平台审核和法律意见。Exit codes: 0 无违规, 3 有违规或风险, 1 输入错误。
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from collections import Counter
from pathlib import Path

PLATFORMS = {
    "taobao": (60, True),
    "tmall": (60, True),
    "pdd": (60, True),
    "jd": (90, False),
    "douyin": (30, False),
}
ABSOLUTE = ["最高级", "最佳", "最好", "最低价", "最便宜", "最优", "最先进", "最受欢迎", "最新技术", "史上最", "全网最", "第一品牌", "销量第一",
            "排名第一", "NO.1", "No.1", "TOP1", "国家级", "世界级", "顶级", "极品", "顶尖", "独一无二", "唯一", "绝无仅有", "万能",
            "绝对", "首选", "领导品牌", "王牌", "冠军", "终极", "填补国内空白", "国家免检", "特供", "专供", "驰名商标"]  # fmt: skip
MEDICAL = ["治疗", "治愈", "根治", "药到病除", "消炎", "杀菌", "抗癌", "防癌", "降血压", "降血糖", "降血脂", "减肥", "瘦身", "排毒", "壮阳",
           "延年益寿", "抗衰老", "增强免疫力", "预防疾病", "无副作用", "疗效"]  # fmt: skip
CLAIM_NEEDS_PROOF = ["100%", "百分百", "纯天然", "无添加", "零添加", "有机", "进口", "原装", "专利", "国家认证", "医用级", "食品级", "孕妇可用", "婴儿可用",
                     "敏感肌可用", "0 添加", "无公害"]  # fmt: skip
INDUCE = [
    "好评返现",
    "晒图返现",
    "五星好评",
    "好评有礼",
    "加微信",
    "加 V",
    "加v",
    "vx",
    "VX",
    "微信号",
    "QQ群",
    "私聊",
    "淘口令",
    "拼多多同款",
]
COSMETIC_SPECIAL = [
    "祛斑",
    "美白",
    "防晒",
    "生发",
    "防脱",
    "脱毛",
    "祛痘",
    "除臭",
    "染发",
    "烫发",
    "丰胸",
    "健美",
]
FOOD_FORBIDDEN = ["保健", "药用", "食疗", "调理身体", "补肾", "养胃", "护肝"]


class ListingError(ValueError):
    pass


def split(s: str) -> list[str]:
    return [k.strip() for k in re.split(r"[,，|、]", s or "") if k.strip()]


def length(text: str, double_cjk: bool) -> int:
    return sum(2 if double_cjk and ord(ch) > 0x2E80 else 1 for ch in text)


def scan(text: str, words: list[str]) -> list[str]:
    low = text.lower()
    return [w for w in words if w.lower() in low]


def check(
    title: str, copy: str, platform: str, keywords: list[str], category: str
) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    limit, double = PLATFORMS[platform]
    n = length(title, double)
    if n > limit:
        issues.append(
            (
                "建议",
                f"标题长度 {n}/{limit}{'（中文算 2）' if double else ''}，超出部分会被截断或无法提交",
            )
        )
    elif n < limit * 0.6:
        issues.append(("建议", f"标题长度 {n}/{limit}，偏短，可补充属性词和使用场景提高搜索覆盖"))
    full = f"{title}\n{copy}"
    for w in scan(full, ABSOLUTE):
        issues.append(
            ("违规", f"极限用语「{w}」：《广告法》第九条禁止，删除或改为可证明的客观描述")
        )
    for w in scan(full, MEDICAL):
        issues.append(("违规", f"医疗 / 功效宣称「{w}」：普通商品不得宣传疾病预防和治疗功能"))
    for w in scan(full, INDUCE):
        issues.append(("违规", f"「{w}」：诱导好评或站外引流，违反平台规则"))
    for w in scan(full, CLAIM_NEEDS_PROOF):
        issues.append(("风险", f"「{w}」需要检测报告、认证或进口报关等证明材料，没有时不要使用"))
    if "化妆品" in category:
        for w in scan(full, COSMETIC_SPECIAL):
            issues.append(("风险", f"「{w}」属于特殊用途化妆品功效，需要有对应的特殊化妆品注册证"))
    if "食品" in category and "保健" not in category:
        for w in scan(full, FOOD_FORBIDDEN):
            issues.append(("违规", f"普通食品不得宣称「{w}」等保健或药用功能"))
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}", title)
    dup = [t for t, c in Counter(tokens).items() if c > 1]
    if dup:
        issues.append(("建议", f"标题中重复的词：{'、'.join(dup)}，重复不会增加搜索权重，浪费字数"))
    if re.search(r"(.)\1{3,}|[!！?？]{2,}|[★☆♥❤]+", title):
        issues.append(("建议", "标题中有连续重复字符或特殊符号，部分平台会降权或拒绝"))
    if keywords:
        miss = [k for k in keywords if k.lower() not in title.lower()]
        if miss:
            issues.append(("建议", f"核心关键词未出现在标题中：{'、'.join(miss)}"))
    return issues


def read_csv(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ListingError("文件编码无法识别")
    rows = [
        {(k or "").strip(): (v or "").strip() for k, v in r.items()}
        for r in csv.DictReader(io.StringIO(text))
    ]
    if not rows or "标题" not in rows[0]:
        raise ListingError("CSV 需要“标题”列")
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("source", help="标题文字或商品 CSV")
    parser.add_argument("--platform", choices=sorted(PLATFORMS), default="taobao")
    parser.add_argument("--keywords", default="")
    parser.add_argument("--keywords-col", default="关键词")
    parser.add_argument("--category", default="")
    parser.add_argument("-o", "--output")
    args = parser.parse_args(argv)
    try:
        src = Path(args.source)
        if src.suffix.lower() == ".csv" and src.is_file():
            rows = read_csv(src)
        else:
            rows = [{"标题": args.source}]
    except (OSError, ListingError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    results = []
    titles = Counter(r["标题"] for r in rows)
    for i, r in enumerate(rows, start=1):
        copy = "\n".join(r.get(k, "") for k in ("卖点", "详情", "文案"))
        kws = split(r.get(args.keywords_col, "")) or split(args.keywords)
        issues = check(r["标题"], copy, args.platform, kws, r.get("类目", "") or args.category)
        if titles[r["标题"]] > 1:
            issues.append(
                ("建议", f"与其他 {titles[r['标题']] - 1} 个商品标题完全相同，容易被判重复铺货")
            )
        results.append((i, r["标题"], issues))
    bad = 0
    for i, title, issues in results:
        levels = Counter(lv for lv, _ in issues)
        bad += 1 if levels["违规"] or levels["风险"] else 0
        prefix = f"{i}. " if len(results) > 1 else ""
        print(
            f"{prefix}{title}\n   违规 {levels['违规']}，风险 {levels['风险']}，建议 {levels['建议']}"
        )
        for lv, msg in issues:
            print(f"   - [{lv}] {msg}")
    if args.output:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill
        except ImportError:  # pragma: no cover - environment check
            print("缺少依赖 openpyxl：请运行 `pip install openpyxl`", file=sys.stderr)
            return 2
        wb = Workbook()
        ws = wb.active
        ws.title = "检查结果"
        ws.append(["序号", "标题", "等级", "问题"])
        for i, title, issues in results:
            for lv, msg in issues or [("通过", "")]:
                ws.append([i, title, lv, msg])
                if lv == "违规":
                    ws.cell(ws.max_row, 3).fill = PatternFill("solid", fgColor="FECACA")
        for c in ws[1]:
            c.font = Font(bold=True)
        ws.column_dimensions["B"].width = 50
        ws.column_dimensions["D"].width = 70
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        wb.save(args.output)
        print(f"已生成 {args.output}")
    print("提示：关键词筛查不能替代平台审核和法律意见；宣称的功效、产地、认证都要有证明材料。")
    return 3 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
