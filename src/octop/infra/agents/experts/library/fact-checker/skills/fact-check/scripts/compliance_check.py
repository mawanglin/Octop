#!/usr/bin/env python3
"""内容合规自查：广告法极限用语、医疗和金融承诺、诱导分享、标题党、个人信息、未标注的推广。

Usage:
    python scripts/compliance_check.py 文章包.md [--commercial] [--json]
    python scripts/compliance_check.py 稿子.md   [--commercial] [--json]    # 也可直接检查一个文本文件

文章包时检查标题和正文（去掉 [S1] 这类标记）。--commercial 表示这是商业推广内容，极限用语从“请确认”升为“必须处理”。
只是关键词和格式提示：命中不等于违规（比如在引用官方原文时），没命中也不等于合规，最终以平台规则和法律意见为准。
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

MARK_RE = re.compile(r"\[(?:S\d+(?:\s*[,，、]\s*S\d+)*|推算)\]")
MUST, CONFIRM = "必须处理", "请确认"

# category -> (reason, level, patterns)
RULES: dict[str, tuple[str, str, list[str]]] = {
    "广告法极限用语": (
        "《广告法》禁止“国家级、最高级、最佳”等用语；商业推广内容尤其要避免。引用官方原文时可以保留，但要加引号并标来源",
        "极限",
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
            r"永久",
        ],
    ),
    "医疗健康功效": (
        "非医疗广告不得涉及疾病治疗功能；保健食品不得宣称疗效",
        MUST,
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
        MUST,
        [
            r"稳赚",
            r"保本",
            r"零风险",
            r"无风险",
            r"(?:保证|稳定)收益",
            r"翻倍",
            r"躺赚",
            r"内幕消息",
        ],
    ),
    "诱导分享/关注": (
        "平台规范禁止以奖励或胁迫方式诱导分享、关注、点赞",
        MUST,
        [
            r"转发(?:到|至)?朋友圈.{0,8}(?:领|送|抽)",
            r"集赞",
            r"不转不是",
            r"分享到.{0,6}群.{0,8}(?:领|送)",
            r"关注.{0,6}(?:即可|才能).{0,6}(?:领|看|下载)",
            r"点赞.{0,6}(?:抽奖|领取)",
        ],
    ),
    "夸大/绝对化表达": (
        "非广告内容也建议避免，影响可信度",
        CONFIRM,
        [r"所有人都", r"100%", r"一定(?:能|会)", r"彻底解决", r"刷屏了"],
    ),
    "个人信息": (
        "不得公开手机号、身份证号、邮箱、银行卡号等个人信息；确需展示要打码",
        MUST,
        [
            r"(?<!\d)1[3-9]\d{9}(?!\d)",
            r"(?<!\d)\d{17}[\dXx](?!\d)",
            r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
            r"(?<!\d)\d{16,19}(?!\d)",
        ],
    ),
}
TITLE_RULES: tuple[str, list[str]] = (
    "标题党：标题要和正文相符，不制造恐慌、不吊胃口",
    [
        r"震惊",
        r"速看",
        r"速转",
        r"删前",
        r"不看后悔",
        r"\d{2,3}%的人",
        r"你绝对想不到",
        r"太可怕了",
        r"细思极恐",
        r"惊天",
        r"炸了",
        r"疯传",
    ],
)
PROMO_RE = re.compile(r"(?:点击|扫码|下单|购买|领券|限时|优惠|折扣|下载|立即抢|加入购物车|链接在)")
DISCLOSE_RE = re.compile(r"广告|推广|赞助|商务合作|合作|软文")
SENSITIVE_TOPICS = (
    (
        "医疗用药建议",
        r"(?:建议|应该|可以|需要).{0,6}(?:服用|吃|停用)(?:药|\w{1,6}片|\w{1,6}胶囊)|诊断为|处方",
    ),
    ("投资买卖建议", r"建议(?:买入|卖出|加仓|抄底|清仓)|目标价|必涨|必跌"),
    ("法律结论", r"一定(?:构成|违法|犯罪)|必然(?:违法|犯罪)|肯定(?:违法|犯罪)"),
    ("涉及未成年人", r"未成年|儿童|小学生|中学生"),
)


@dataclass
class Hit:
    level: str
    category: str
    word: str
    context: str


def clean(text: str) -> str:
    return MARK_RE.sub("", text)


def scan(title: str, body: str, commercial: bool) -> list[Hit]:
    hits: list[Hit] = []
    seen: set[tuple[str, int, int]] = set()

    def run(text: str, where: str, category: str, level: str, patterns: list[str]) -> None:
        for pat in patterns:
            for m in re.finditer(pat, text):
                key = (where + category, m.start(), m.end())
                if key in seen:
                    continue
                seen.add(key)
                ctx = text[max(0, m.start() - 10) : m.end() + 10].replace("\n", " ")
                hits.append(Hit(level, category, m.group(), f"{where}…{ctx}…"))

    for category, (_, level, patterns) in RULES.items():
        lvl = (MUST if commercial else CONFIRM) if level == "极限" else level
        run(body, "正文：", category, lvl, patterns)
        if title:
            run(title, "标题：", category, lvl, patterns)
    if title:
        run(title, "标题：", "标题党", CONFIRM, TITLE_RULES[1])
    for category, pat in SENSITIVE_TOPICS:
        run(body, "正文：", f"需人工把关：{category}", CONFIRM, [pat])
    if PROMO_RE.search(body) and not DISCLOSE_RE.search(title + body):
        m = PROMO_RE.search(body)
        assert m is not None
        hits.append(
            Hit(
                CONFIRM,
                "推广未标注",
                m.group(),
                "出现了下单、购买、优惠一类的推广用语，但全文没有“广告/推广/合作”之类的标注",
            )
        )
    rank = {MUST: 0, CONFIRM: 1}
    hits.sort(key=lambda h: (rank[h.level], h.category))
    return hits


def load(path: Path) -> tuple[str, str]:
    """(title, body) of the draft in an article pack, or of a plain text file."""
    text = path.read_text(encoding="utf-8-sig")
    pack = ap.parse_pack(text)
    if pack.front.get(ap.FRONT_KEY):
        text = pack.draft()
    m = re.search(r"(?m)^#\s+(.+)$", text)
    title = m.group(1).strip() if m else ""
    body = re.sub(r"(?m)^#\s+.+$", "", text, count=1) if m else text
    return title, clean(body)


def render(hits: list[Hit], commercial: bool) -> str:
    if not hits:
        return "未命中高风险表达（只是关键词提示，仍需人工判断）"
    out = [f"命中 {len(hits)} 处{'（按商业推广内容判定）' if commercial else ''}："]
    for level in (MUST, CONFIRM):
        rows = [h for h in hits if h.level == level]
        if not rows:
            continue
        out.append(f"\n## {level}")
        by_cat: dict[str, list[Hit]] = {}
        for h in rows:
            by_cat.setdefault(h.category, []).append(h)
        for cat, items in by_cat.items():
            reason = RULES.get(cat, (TITLE_RULES[0] if cat == "标题党" else "", "", []))[0]
            out.append(f"【{cat}】{reason}")
            for h in items:
                out.append(f"- “{h.word}”：{h.context}")
    out.append(
        "\n说明：关键词提示，命中不等于违规（如引用官方原文），没命中也不等于合规；最终以平台规则和法律意见为准。"
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="内容合规自查")
    parser.add_argument("input")
    parser.add_argument("--commercial", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        title, body = load(Path(args.input))
    except OSError as exc:
        print(f"无法读取：{exc}", file=sys.stderr)
        return 1
    except UnicodeDecodeError:
        print("文件不是 UTF-8 编码", file=sys.stderr)
        return 1
    hits = scan(title, body, args.commercial)
    if args.json:
        print(json.dumps([h.__dict__ for h in hits], ensure_ascii=False, indent=2))
    else:
        print(render(hits, args.commercial))
    return 3 if any(h.level == MUST for h in hits) else 0


if __name__ == "__main__":
    sys.exit(main())
