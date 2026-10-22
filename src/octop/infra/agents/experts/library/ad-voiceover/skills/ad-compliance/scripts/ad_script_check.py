#!/usr/bin/env python3
"""投流口播稿检查：逐个版本核对时长、开头钩子、行动引导、口播易读性，以及广告合规和 AI 产品特有的风险表达。

Usage:
    python scripts/ad_script_check.py 口播稿.md [--rate 4.5] [--target 30] [--json]

稿件格式（每个 "## " 标题是一个版本 / 一条素材，见 ad-script-writing 的 references/example-scripts.md）：
    ---
    产品: 某某 AI 助手
    平台: 抖音
    时长: 30
    数字人: 否
    ---
    ## A｜痛点开场
    口播：……
    画面：……
"口播/台词/旁白/配音" 开头的行计入口播；没有任何前缀时，除 "画面/字幕/备注" 外的正文都算口播。
检查项：
  时长   口播字数 ÷ 语速（默认 4.5 字/秒，投流口播通常偏快）与目标时长对比
  钩子   第一句是否在约 4 秒内说完，是否有提问、数字、"你"、痛点、反常识等抓人要素
  引导   结尾是否有明确的行动引导（点击、下方链接、免费试用、预约、私信、下载……）
  易读   一口气超过 18 字没有停顿的句子、未解释的英文术语（Agent、RAG、MCP、Workflow……）
  合规   广告法极限用语、效果和收益承诺、"取代人工"等夸大、冒用大模型或名人、虚假紧迫、
         隐私绝对承诺；数字人口播提醒标注 AI 生成
命中只是提示，不等于一定违规或一定能过审；以平台审核规则和法律意见为准。
Exit codes: 0 没有问题, 3 有需要修改的地方, 1 输入错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

SPOKEN = re.compile(r"^(?:[-*]\s*)?(口播|台词|旁白|解说|配音)[:：]\s*(.*)$")
NOT_SPOKEN = re.compile(r"^(?:[-*]\s*)?(画面|字幕|镜头|备注|音乐|BGM|素材|标题|封面)[:：]", re.I)

RULES: dict[str, tuple[str, list[str]]] = {
    "广告法极限用语": (
        "《广告法》第九条禁止使用“最高级”“最佳”等用语，审核最常见的拒审原因",
        [
            r"最(?:佳|好|高级|优|强|大|低价|便宜|先进|聪明|智能|专业|全|快)",
            r"第一(?:品牌|名|家|款)?(?![次天步个句条])",
            r"(?<!之)唯一",
            r"首(?:个|家|选|款)",
            r"顶(?:级|尖)",
            r"国家级",
            r"世界级",
            r"全网(?:最|第一|独家)",
            r"(?i)no\.?\s*1\b",
            r"遥遥领先",
            r"吊打",
            r"秒杀(?:所有|一切|同行)",
            r"万能",
            r"绝对",
        ],
    ),
    "效果和收益承诺": (
        "不得对效果、收益作保证性承诺（《广告法》第二十五条等），AI 工具“帮你赚钱”类说法极易拒审",
        [
            r"保证(?:涨粉|赚钱|收入|出单|成交|效果|获客|上岸|通过)",
            r"(?:稳赚|躺赚|稳定收益|轻松月入|日入|月入)\s*(?:\d+|[一二三四五六七八九十百千万]+)?",
            r"(?:自动|睡后)(?:赚钱|收入|变现)",
            r"(?:\d+|[一二三四五六七八九十])\s*天(?:回本|见效|涨粉|起号)",
            r"无效退款",
            r"包(?:过|会|教会|成交|出单)",
        ],
    ),
    "AI 能力夸大": (
        "AI 产品常见的夸大表述，需要改成可证实、有边界的说法",
        [
            r"(?:完全|彻底)?(?:取代|替代)(?:你的|所有|全部|整个)?.{0,3}(?:员工|人工|人类|团队|程序员|设计师|客服|运营|销售|财务)",
            r"(?:100|百分之百)\s*%?\s*(?:准确|正确|成功|自动)",
            r"零(?:失误|错误|出错)",
            r"永不出错",
            r"(?:全|完全)自动(?:化)?.{0,6}(?:不用管|不需要人|躺着)",
            r"无所不能",
            r"什么都(?:能|会)",
            r"一键(?:搞定|解决)(?:所有|一切)",
        ],
    ),
    "冒用品牌或名人": (
        "冒用知名大模型、企业或名人做背书属于虚假宣传或侵权；只有真实接入且有授权时才能如实表述",
        [
            r"(?i)(?:openai|chatgpt|gpt-?\d|claude|gemini|deepseek|文心|通义|豆包|kimi|智谱).{0,4}(?:官方|同款|亲自|内部)",
            r"(?:官方|独家)(?:合作|认证|授权)",
            r"国家(?:认证|推荐|指定)",
            r"(?:马斯克|雷军|马化腾|李彦宏|周鸿祎|黄仁勋|奥特曼).{0,6}(?:推荐|都在用|力荐|背书)",
        ],
    ),
    "虚假紧迫和诱导": (
        "不实的限时、限量、涨价说法可能构成虚假宣传；如属实需能举证",
        [
            r"(?:最后|仅剩|只剩)\s*\d+\s*(?:个|位|名|天)",
            r"(?:马上|明天|即将)(?:涨价|恢复原价|下架)",
            r"错过(?:再等|就没|拍大腿)",
            r"不(?:看|用)(?:就|会)(?:亏|落后|被淘汰)",
        ],
    ),
    "隐私和安全承诺": (
        "数据安全只能说采取了哪些措施，不能作绝对承诺；收集手机号等信息要告知用途",
        [
            r"(?:绝不|永不|不会|零)(?:泄露|泄漏)",
            r"(?:100|百分之百)\s*%?\s*安全",
            r"绝对安全",
        ],
    ),
}
HOOK_SIGNALS = {
    "提问": re.compile(r"[？?]|吗|呢|为什么|怎么|是不是|有没有"),
    "数字": re.compile(r"\d|[一二三四五六七八九十百千万]+(?:个|分钟|秒|倍|小时|天|件)"),
    "对话感": re.compile(r"你|老板|打工人|朋友们"),
    "痛点": re.compile(r"还在|每天|加班|熬夜|累|烦|头疼|焦虑|浪费|搞不定|来不及|没人|招不到|亏"),
    "反常识": re.compile(r"别再|千万别|不用|没想到|居然|其实|真相|90%的人|大多数人"),
}
CTA = re.compile(
    r"点击|点(?:一)?下|左下角|下方|链接|评论区|私信|预约|报名|领取|免费(?:试用|体验|用)|"
    r"下载|注册|安装|关注|加(?:我|微信)|扫码|填写|咨询|立即|马上(?:试|用|体验)|直播间"
)
JARGON = re.compile(
    r"(?i)\b(?:agent|agents|rag|mcp|workflow|llm|prompt|token|api|sdk|saas|copilot|"
    r"multi-?agent|fine-?tun\w*|embedding|langchain|n8n|dify|coze)\b"
)
EXPLAIN_NEAR = re.compile(r"也就是|就是|简单说|说白了|相当于|叫做|[（(：:]")


@dataclass
class Variant:
    name: str
    spoken: str = ""
    units: int = 0
    seconds: float = 0.0
    hook: str = ""
    hook_signals: list[str] = field(default_factory=list)
    has_cta: bool = False
    issues: list[str] = field(default_factory=list)
    compliance: list[dict[str, str]] = field(default_factory=list)


def spoken_units(text: str) -> int:
    cjk = len(re.findall(r"[一-鿿]", text))
    digits = sum(len(m) for m in re.findall(r"\d+", text))
    words = len(re.findall(r"[A-Za-z]+", text))
    return cjk + digits + round(words * 1.5)


def parse(source: str) -> tuple[dict[str, str], list[tuple[str, list[str]]]]:
    lines = source.replace("\r\n", "\n").split("\n")
    meta: dict[str, str] = {}
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                for raw in lines[1:i]:
                    key, sep, value = raw.replace("：", ":", 1).partition(":")
                    if sep:
                        meta[key.strip()] = value.strip()
                lines = lines[i + 1 :]
                break
    blocks: list[tuple[str, list[str]]] = []
    for line in lines:
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            blocks.append((m.group(1).strip(), []))
        elif blocks:
            blocks[-1][1].append(line)
        elif line.strip() and not line.startswith("#"):
            blocks.append(("全文", [line]))
    return meta, blocks


def spoken_text(lines: list[str]) -> str:
    tagged = [m.group(2) for ln in lines if (m := SPOKEN.match(ln.strip()))]
    if tagged:
        return "\n".join(tagged)
    return "\n".join(
        ln.strip()
        for ln in lines
        if ln.strip() and not NOT_SPOKEN.match(ln.strip()) and not ln.startswith("#")
    )


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[。！？!?\n；;]+", text) if s.strip()]


def compliance_hits(text: str) -> list[dict[str, str]]:
    hits: list[tuple[int, dict[str, str]]] = []
    seen: set[tuple[int, int]] = set()
    for category, (_, patterns) in RULES.items():
        for pattern in patterns:
            for m in re.finditer(pattern, text):
                if any(m.start() < e and s < m.end() for s, e in seen):
                    continue
                seen.add((m.start(), m.end()))
                ctx = text[max(0, m.start() - 8) : m.end() + 8].replace("\n", " ")
                hits.append((m.start(), {"类别": category, "命中": m.group(), "上下文": ctx}))
    return [h for _, h in sorted(hits, key=lambda x: x[0])]


def check_variant(name: str, lines: list[str], rate: float, target: float | None) -> Variant:
    v = Variant(name=name, spoken=spoken_text(lines))
    v.units = spoken_units(v.spoken)
    v.seconds = round(v.units / rate, 1)
    if not v.spoken:
        v.issues.append("没有找到口播内容（用“口播：”开头标注）")
        return v
    sents = sentences(v.spoken)
    v.hook = sents[0] if sents else ""
    hook_secs = spoken_units(v.hook) / rate
    v.hook_signals = [k for k, rx in HOOK_SIGNALS.items() if rx.search(v.hook)]
    if hook_secs > 4.5:
        v.issues.append(
            f"开头第一句约 {hook_secs:.1f} 秒，超过 4 秒：前 3 秒决定是否划走，拆短或直接说结论"
        )
    if not v.hook_signals:
        v.issues.append(
            "开头缺少抓人要素：试试提问、具体数字、直接喊人群（你/老板）、点出痛点或反常识"
        )
    tail = v.spoken[-max(30, len(v.spoken) // 4) :]
    v.has_cta = bool(CTA.search(tail))
    if not v.has_cta:
        v.issues.append(
            "结尾没有明确的行动引导：告诉用户下一步做什么（点击下方链接免费试用 / 预约演示 / 私信领取）"
        )
    if target:
        if v.seconds > target * 1.1:
            v.issues.append(
                f"预计 {v.seconds} 秒，超过目标 {target:g} 秒：删减到约 {int(target * rate)} 字"
            )
        elif v.seconds < target * 0.6:
            v.issues.append(
                f"预计 {v.seconds} 秒，明显短于目标 {target:g} 秒：可以补一个演示画面或用户场景"
            )
    clauses = [c.strip() for c in re.split(r"[。！？!?\n；;，,、：:]+", v.spoken) if c.strip()]
    long_ones = [c for c in clauses if spoken_units(c) > 18]
    if long_ones:
        v.issues.append(
            f"{len(long_ones)} 处一口气超过 18 字没有停顿，口播念不顺：如“{long_ones[0][:20]}…”"
        )
    for m in JARGON.finditer(v.spoken):
        around = v.spoken[max(0, m.start() - 8) : m.start()] + v.spoken[m.end() : m.end() + 12]
        if not EXPLAIN_NEAR.search(around):
            v.issues.append(f"术语“{m.group()}”没有解释：投流面向大众，换成大白话或紧跟一句解释")
            break
    v.compliance = compliance_hits(v.spoken)
    return v


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("input")
    parser.add_argument("--rate", type=float, default=4.5, help="语速，字/秒")
    parser.add_argument("--target", type=float, help="目标时长（秒），默认读稿件的“时长”")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        source = Path(args.input).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"失败：无法读取 {args.input}：{exc}", file=sys.stderr)
        return 1
    if args.rate <= 0:
        print("失败：--rate 必须大于 0", file=sys.stderr)
        return 1
    meta, blocks = parse(source)
    if not blocks:
        print("失败：稿件里没有内容", file=sys.stderr)
        return 1
    target = args.target
    meta_secs = re.match(r"^\d+(?:\.\d+)?", meta.get("时长", ""))
    if target is None and meta_secs:
        target = float(meta_secs.group())
    variants = [check_variant(name, lines, args.rate, target) for name, lines in blocks]
    notes = []
    if meta.get("数字人", "").strip() in {"是", "yes", "Yes", "true", "1"} or "AI配音" in meta.get(
        "配音", ""
    ):
        notes.append(
            "使用数字人或 AI 配音：按《人工智能生成合成内容标识办法》在画面中显著标注“AI 生成”，并确认数字人形象和声音已获授权"
        )
    notes.append(
        "投放前确认：素材中的数据、案例、截图真实可证；落地页信息与口播一致；收集手机号等信息时告知用途"
    )

    if args.json:
        print(
            json.dumps(
                {"meta": meta, "variants": [asdict(v) for v in variants], "notes": notes},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        head = "，".join(f"{k} {v}" for k, v in meta.items() if v)
        print(
            f"共 {len(variants)} 个版本"
            + (f"（{head}）" if head else "")
            + f"，语速 {args.rate:g} 字/秒"
        )
        for v in variants:
            mark = "✓" if not v.issues and not v.compliance else "✗"
            print(
                f"\n{mark} {v.name}：{v.units} 字，约 {v.seconds} 秒；钩子要素：{('、'.join(v.hook_signals) or '无')}；行动引导：{'有' if v.has_cta else '无'}"
            )
            for issue in v.issues:
                print(f"  - [调整] {issue}")
            for hit in v.compliance:
                reason = RULES[hit["类别"]][0]
                print(f"  - [合规·{hit['类别']}] “{hit['命中']}”：…{hit['上下文']}… —— {reason}")
        print()
        for n in notes:
            print(f"提醒：{n}")
        print("说明：关键词检查只是提示，命中不等于违规，未命中也不代表一定过审。")
    return 3 if any(v.issues or v.compliance for v in variants) else 0


if __name__ == "__main__":
    sys.exit(main())
