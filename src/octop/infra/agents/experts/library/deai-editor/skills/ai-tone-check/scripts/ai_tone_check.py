#!/usr/bin/env python3
"""AI 味检查：逐行标出中文（兼顾英文）文稿里有语料实测依据的 AI 写作痕迹，核对改稿是否守住信息，
统计作者本人的写作习惯。

Usage:
    python scripts/ai_tone_check.py scan 文稿.md [--profile 作者旧稿.md ...] [--json]
    python scripts/ai_tone_check.py diff 原稿.md 改稿.md [--json]
    python scripts/ai_tone_check.py profile 作者旧稿.md [更多旧稿 ...] [--json]

scan     门槛（半角标点、粗体、惊叹号、emoji）、聊天残留（“希望对你有帮助”等）、
         十六条实测规则（翻案腔、顿号罗列、相邻句同构、破折号、提示性冒号、序数小标题、
         拟人化喻体、概括盖掉具体、起手式、五种翻译腔、段首零主语评论），黑名单词。
         每条规则给出本文频率和人类写作均值，频率达到人类均值 2 倍以上标为“偏高”。
         --profile 传入作者自己的旧稿：作者本来就常用的写法（如破折号）降级为“作者习惯”。
         英文为主的文稿改用英文规则（not just X but Y、delve/tapestry 等高频词、套话结尾等）。
diff     信息守恒核对：改稿是否新增或丢失数字、日期、英文专名、引语、书名、链接，
         否定词数量是否变化，“可能、约”等限定词是否减少、“所有、一定”等绝对化词是否增加，
         标题（忽略序号）、段落、列表、代码块、表格是否变动。
profile  作者习惯：平均句长和段长、各类标点每千字用量、粗体、常用句首词和连接词。
代码块、行内代码、网址、YAML front matter、表格不参与规则检查。
频率均值来自 lieflat-less-ai-tone 的公开语料实测（AI 300 篇 / 人类 329 篇），只说明写法的频率差异，
不能证明文稿由谁写成，也不保证通过任何 AI 检测器。
Exit codes: scan 0 没有偏高项 / 3 有偏高项或门槛问题；diff 0 一致 / 3 有信息变动；1 输入错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CJK = re.compile(r"[一-鿿]")


@dataclass
class Rule:
    id: str
    name: str
    ai: float | None  # AI corpus rate
    human: float | None  # human corpus rate
    unit: str
    fix: str
    pattern: re.Pattern[str] | None = None


RULES = [
    Rule(
        "Z1",
        "翻案腔",
        0.73,
        0.22,
        "每千字",
        "先立一个读者没有的误解再推翻：直接从正面下判断",
        re.compile(
            r"(?:不是|并非|不在于)[^。！？\n]{1,25}?[，,]?\s*而(?:是|在于)|与其说[^。！？\n]{1,25}不如说|"
            r"看似[^。！？\n]{1,20}实则|表面上?[^。！？\n]{1,20}实际上|你以为[^。！？\n]{1,25}其实|说到底|答案恰恰相反"
        ),
    ),
    Rule(
        "Z2",
        "顿号罗列过密",
        3.21,
        1.78,
        "每千字",
        "一个分句里连列三项以上：能概括就概括，必须保留时换其中一项的句法",
    ),
    Rule(
        "Z3",
        "相邻句结构同款",
        9.41,
        4.81,
        "每百段",
        "相邻几句逗号数、长度、句式都一样：合并、拆分或换语序打散其中一句",
    ),
    Rule(
        "Z4",
        "破折号",
        2.38,
        0.80,
        "每千字",
        "制造揭晓式停顿或可有可无的补充就删；承担解释、插入、转折的保留",
        re.compile(r"——|--"),
    ),
    Rule(
        "Z5",
        "提示性冒号",
        0.29,
        0.08,
        "每千字",
        "“核心是：”“关键在于：”这类提示语不承担信息：删提示语，直接说",
        re.compile(
            r"(?:一句话(?:总结|说|概括)|简单说|说白了|总结|小结|结论|核心(?:是|在于|观点)?|关键(?:是|在于)?|"
            r"重点(?:是)?|本质(?:是|上)?|换句话说|也就是说|答案(?:是)?|我的(?:观点|判断|结论))[：:]"
        ),
    ),
    Rule(
        "Z6",
        "空转句引出列表",
        0.29,
        0.03,
        "每千字",
        "以冒号收尾、去掉也不损失信息的引导句：改成完整的一句或直接删",
    ),
    Rule(
        "Z7",
        "序数词当小标题",
        0.19,
        0.06,
        "每千字",
        "连续三个以上“一、二、三 / 第一、第二”小标题：删编号，保留标题文字",
    ),
    Rule(
        "Z8",
        "拟人化喻体",
        0.018,
        0.002,
        "每千字",
        "“像一位智慧的导师”：换成这东西实际做了什么",
        re.compile(
            r"(?:像|就像|如同|好比|相当于|仿佛)(?:是)?(?:一个|一位|一名|一座|一盏)[^，。！？\n]{0,8}"
            r"(?:导师|老师|管家|助手|伙伴|向导|守护者|指挥家|工匠|灯塔|朋友|大脑|引擎|桥梁|钥匙|指南针|宝库)"
        ),
    ),
    Rule(
        "Z9",
        "概括盖掉已有的具体",
        None,
        None,
        "每千字",
        "同段已经有具体数字：把数字提到“显著提升”的位置；没有数字就只恢复动词，不许编",
        re.compile(
            r"(?:显著|大幅|明显|极大地?|大大|有效)(?:地)?(?:提升|提高|增长|改善|降低|减少|增强|优化)|"
            r"实现了[^，。！？\n]{0,10}的(?:提升|增长|突破)|进行了[^，。！？\n]{0,10}的?(?:优化|调整|升级)"
        ),
    ),
    Rule(
        "Z10",
        "起手式",
        0.025,
        0.008,
        "每千字",
        "“说白了 / 先说结论”：删掉，直接给判断",
        re.compile(r"说白了|说穿了|先说结论|直接说结论"),
    ),
    Rule(
        "Z11",
        "过长前置定语",
        0.42,
        None,
        "每千字",
        "中心词前修饰太长：拆成两个分句",
        re.compile(r"(?:一个|一种|一套|这种|这个)[^，。、；：！？\n]{15,}的[一-鿿]{2,5}"),
    ),
    Rule(
        "Z12",
        "“当……时”前置",
        0.26,
        None,
        "每千字",
        "删掉“当”和“时”",
        re.compile(r"当[^，。！？\n]{2,20}(?:的时候|时)，"),
    ),
    Rule(
        "Z13",
        "前置话题壳",
        0.22,
        None,
        "每千字",
        "“对于……来说 / 就……而言”：把对象放到主语位",
        re.compile(
            r"对于[^，。！？\n]{2,15}来说|对[^，。！？\n]{2,15}而言|就[^，。！？\n]{2,15}而言"
        ),
    ),
    Rule(
        "Z14",
        "句首连接词当路标",
        0.18,
        0.03,
        "每千字",
        "“然而 / 因此 / 此外”顶在句首：移到主语后，或换“不过、也”",
        re.compile(r"(?:^|[。！？]\s*)(?:然而|因此|此外|与此同时|换言之|总而言之|综上所述)[，、]"),
    ),
    Rule(
        "Z15",
        "“这意味着”式复述",
        0.15,
        None,
        "每千字",
        "和前句同义的复述：并入前句",
        re.compile(r"这意味着|这表明|这说明|换句话说"),
    ),
    Rule(
        "Z16",
        "段首零主语评论",
        0.61,
        0.14,
        "占非首段%",
        "非首段以“值得注意的是 / 更重要的是”开头且没有回指：补一个“这”，或整句删",
    ),
]
COMMENT = re.compile(
    r"^(?:听起来|看起来|看上去|听上去|说到底|换句话说|意味着|值得注意|不难看出|问题在于|原因在于|"
    r"有意思的是|更重要的是|关键在于|真正的|需要指出的是|值得一提的是)"
)
ANAPHOR = re.compile(
    r"^(?:这|那|其|此|上面|前面|以上|该|它|他|她|同样|类似|相比|反过来|但|不过|所以|因此|于是|而|另)"
)
RESIDUE = re.compile(
    r"希望(?:这|以上|这些)?(?:内容|回答|信息)?(?:对你|对您|能)(?:有所)?(?:帮助|有帮助)|如果(?:你|您)?(?:还)?有(?:任何|其他)?(?:问题|疑问)|"
    r"作为(?:一个|一款)?(?:AI|人工智能)(?:语言模型|助手)?|好的[，,！!]\s*(?:以下|下面)是|以下是(?:为你|为您)|"
    r"截至我的知识|知识截止|我无法(?:访问|浏览)|当然可以[！!，,]|很高兴(?:为你|为您)"
)
BLACKLIST = [
    "众所周知",
    "总而言之",
    "综上所述",
    "值得注意的是",
    "不可否认",
    "在当今时代",
    "赋能",
    "至关重要",
    "深入探讨",
    "无缝",
    "闭环",
    "底层逻辑",
    "抓手",
    "对齐",
    "打透",
    "跑通",
    "颠覆",
    "重塑",
    "生态",
    "砥砺",
    "打造",
    "扎实推进",
    "令人深思",
    "不禁让人",
    "令人动容",
    "一言难尽",
    "前景广阔",
    "助力",
    "赛道",
]
EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿⭐✅]")
HALF_PUNCT = re.compile(r"(?<=[一-鿿])[,;:?!](?!\d)|[,;:?!](?=[一-鿿])")

EN_RULES = [
    (
        "E1",
        "not just X but Y",
        r"\bnot (?:just|only|merely) [^.?!]{1,40}?,? but\b|\bisn't just\b|\bit's not about\b",
        "state the point directly",
    ),
    (
        "E2",
        "em dash",
        r"—|\s--\s",
        "replace with a comma, period or parentheses unless it carries meaning",
    ),
    (
        "E3",
        "AI vocabulary",
        r"\b(?:delve|delves|tapestry|testament|pivotal|crucial|landscape|realm|seamless(?:ly)?|robust|leverage|foster|underscore[sd]?|showcas(?:e|es|ing)|intricate|vibrant|meticulous(?:ly)?|navigat(?:e|ing) the|ever-evolving|game-changer|unlock)\b",
        "use the plain word",
    ),
    (
        "E4",
        "inflated significance",
        r"\b(?:stands as|serves as a|plays a (?:vital|crucial|pivotal) role|marks a (?:significant|pivotal)|a testament to|rich (?:cultural )?heritage)\b",
        "say what it does",
    ),
    (
        "E5",
        "signposting",
        r"\b(?:it(?:'s| is) (?:important|worth) (?:to note|noting)|in conclusion|in summary|overall,|ultimately,|let's dive|let's explore|here's (?:the thing|what you need to know))\b",
        "cut the signpost",
    ),
    (
        "E6",
        "chatbot residue",
        r"\b(?:i hope this helps|let me know if|great question|certainly!|as an ai|as of my (?:last )?knowledge)\b",
        "delete",
    ),
    ("E7", "forced triad", r"\b\w+, \w+, and \w+\b", "check whether three items are really needed"),
]


class CheckError(ValueError):
    pass


# ------------------------------------------------------------------ text prep


def strip_front_matter(lines: list[str]) -> list[str]:
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return [""] * (i + 1) + lines[i + 1 :]
    return lines


def prose_lines(text: str) -> list[tuple[int, str, str]]:
    """(line number, kind, cleaned text); kind: heading / list / para / table / code."""
    lines = strip_front_matter(text.replace("\r\n", "\n").split("\n"))
    out: list[tuple[int, str, str]] = []
    in_code = False
    for no, raw in enumerate(lines, 1):
        s = raw.strip()
        if s.startswith("```"):
            in_code = not in_code
            out.append((no, "code", ""))
            continue
        if in_code:
            out.append((no, "code", ""))
            continue
        cleaned = re.sub(r"`[^`]*`|https?://\S+|!\[[^\]]*\]\([^)]*\)", " ", s)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", cleaned)
        if s.startswith("|"):
            kind = "table"
        elif s.startswith("#"):
            kind, cleaned = "heading", cleaned.lstrip("#").strip()
        elif re.match(r"^(?:[-*+]|\d+[.、)])\s+", s):
            kind = "list"
        elif s.startswith(">"):
            kind, cleaned = "para", cleaned.lstrip("> ").strip()
        else:
            kind = "para"
        out.append((no, kind, cleaned))
    return out


def count_cjk(lines: list[tuple[int, str, str]]) -> int:
    return sum(len(CJK.findall(t)) for _, k, t in lines if k != "code")


def paragraphs(lines: list[tuple[int, str, str]]) -> list[tuple[int, str]]:
    return [(no, t) for no, k, t in lines if k == "para" and len(t) >= 8]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[。！？!?；;]", text) if len(s.strip()) >= 4]


# ----------------------------------------------------------------------- scan


def find_hits(lines: list[tuple[int, str, str]]) -> dict[str, list[dict[str, Any]]]:
    hits: dict[str, list[dict[str, Any]]] = {r.id: [] for r in RULES}

    def add(rid: str, no: int, text: str) -> None:
        hits[rid].append({"行": no, "命中": text[:60]})

    body = [(no, k, t) for no, k, t in lines if k in {"para", "list"}]
    for rule in RULES:
        if rule.pattern is None:
            continue
        for no, _, t in body:
            for m in rule.pattern.finditer(t):
                if rule.id == "Z9" and not re.search(r"\d", t):
                    continue  # only when a concrete number already sits in the same line
                add(rule.id, no, t[max(0, m.start() - 6) : m.end() + 10])
    for no, k, t in body:
        if k != "para":
            continue
        for clause in re.split(r"[，。；！？：,;!?:]", t):
            if clause.count("、") >= 2:
                add("Z2", no, clause)
    paras = paragraphs(lines)
    for no, p in paras:
        sents = [s for s in re.split(r"[。！？]", p) if len(s.strip()) > 10]

        def sig(s: str) -> tuple[int, bool, bool, int]:
            return (s.count("，"), "：" in s, "（" in s or "(" in s, len(s) // 15)

        for i in range(len(sents) - 1):
            a, b = sig(sents[i]), sig(sents[i + 1])
            if a == b and a[0] >= 1:
                add("Z3", no, f"{sents[i].strip()[:24]}／{sents[i + 1].strip()[:24]}")
    for i, (no, p) in enumerate(paras):
        if i and COMMENT.match(p) and not ANAPHOR.match(p):
            add("Z16", no, p[:30])
    for i, (no, k, t) in enumerate(lines):
        if k == "para" and len(t) <= 30 and re.search(r"[：:]\s*$", t):
            nxt = next((kk for _, kk, tt in lines[i + 1 :] if tt or kk == "list"), "")
            if nxt == "list":
                add("Z6", no, t)
    heads = [(no, t) for no, k, t in lines if k == "heading"]
    run: list[tuple[int, str]] = []
    for no, t in [*heads, (0, "")]:
        if re.match(
            r"^(?:[一二三四五六七八九十]+、|第[一二三四五六七八九十]+[、，,：:\s]|\d+[.、]\s*)", t
        ):
            run.append((no, t))
            continue
        if len(run) >= 3:
            for rno, rt in run:
                add("Z7", rno, rt)
        run = []
    return hits


def gates(text: str, lines: list[tuple[int, str, str]]) -> list[dict[str, Any]]:
    out = []
    body = [(no, t) for no, k, t in lines if k in {"para", "list", "heading"}]
    half = [(no, m.group()) for no, t in body for m in HALF_PUNCT.finditer(t)]
    if half:
        out.append(
            {
                "项": "半角标点",
                "数量": len(half),
                "位置": sorted({n for n, _ in half})[:10],
                "改法": "中文正文用全角标点；数字、英文专名、网址、代码里的除外",
            }
        )
    bold = len(re.findall(r"\*\*[^*\n]+\*\*", "\n".join(t for _, k, t in lines if k != "code")))
    if bold > 2:
        out.append(
            {
                "项": "粗体",
                "数量": bold,
                "位置": [],
                "改法": "去掉粗体通读一遍，论点还浮得出来就删；只保留警告和长文定位用的一两处",
            }
        )
    excl = [no for no, t in body if "！" in t or re.search(r"[一-鿿]!", t)]
    if excl:
        out.append(
            {"项": "惊叹号", "数量": len(excl), "位置": excl[:10], "改法": "惊叹号留给作者自己加"}
        )
    emoji = [no for no, t in body if EMOJI.search(t)]
    if emoji:
        out.append(
            {"项": "emoji / 装饰符号", "数量": len(emoji), "位置": emoji[:10], "改法": "正文里删掉"}
        )
    return out


def profile_rates(text: str) -> dict[str, float]:
    lines = prose_lines(text)
    chars = max(count_cjk(lines), 1)
    hits = find_hits(lines)
    paras = max(len(paragraphs(lines)), 1)
    rates = {}
    for r in RULES:
        n = len(hits[r.id])
        rates[r.id] = n / paras * 100 if r.unit != "每千字" else n / chars * 1000
    return rates


def scan(text: str, author_samples: list[str]) -> dict[str, Any]:
    lines = prose_lines(text)
    chars = count_cjk(lines)
    latin_words = len(re.findall(r"[A-Za-z]+", " ".join(t for _, k, t in lines if k != "code")))
    if chars < 50 and latin_words > 80:
        return scan_english(lines, latin_words)
    if chars < 50:
        raise CheckError("中文正文太短（少于 50 字），规则需要一定篇幅才有意义")
    hits = find_hits(lines)
    paras = paragraphs(lines)
    non_first = max(len(paras) - 1, 1)
    author: dict[str, float] = {}
    if author_samples:
        rates = [profile_rates(s) for s in author_samples]
        author = {rid: sum(r[rid] for r in rates) / len(rates) for rid in rates[0]}
    report = []
    for r in RULES:
        n = len(hits[r.id])
        if r.unit == "每千字":
            rate = n / chars * 1000
        elif r.unit == "每百段":
            rate = n / max(len(paras), 1) * 100
        else:
            rate = n / non_first * 100
        level = "正常"
        if n:
            if (
                r.human
                and rate >= 2 * r.human
                and n >= 2
                or (r.human is None and r.ai and rate >= r.ai and n >= 2)
            ):
                level = "偏高"
            else:
                level = "留意"
            if author and r.ai and author.get(r.id, 0) >= (r.ai or 0) * 0.8:
                level = "作者习惯"
        report.append(
            {
                "规则": r.id,
                "名称": r.name,
                "命中": n,
                "频率": round(rate, 2),
                "单位": r.unit,
                "人类均值": r.human,
                "AI均值": r.ai,
                "判断": level,
                "改法": r.fix,
                "位置": hits[r.id][:12],
            }
        )
    residue = [
        {"行": no, "命中": m.group()}
        for no, k, t in lines
        if k in {"para", "list"}
        for m in RESIDUE.finditer(t)
    ]
    joined = "\n".join(t for _, k, t in lines if k in {"para", "list", "heading"})
    black = {w: joined.count(w) for w in BLACKLIST if w in joined}
    return {
        "语言": "中文",
        "汉字数": chars,
        "段落数": len(paras),
        "门槛": gates(text, lines),
        "聊天残留": residue,
        "规则": report,
        "黑名单词": black,
        "偏高": [x["名称"] for x in report if x["判断"] == "偏高"],
    }


def scan_english(lines: list[tuple[int, str, str]], words: int) -> dict[str, Any]:
    report = []
    body = [(no, t) for no, k, t in lines if k in {"para", "list", "heading"}]
    for rid, name, pattern, fix in EN_RULES:
        rx = re.compile(pattern, re.I)
        pos = [{"行": no, "命中": m.group()} for no, t in body for m in rx.finditer(t)]
        rate = len(pos) / max(words, 1) * 1000
        level = "正常" if not pos else ("偏高" if rate >= 2 and len(pos) >= 2 else "留意")
        if rid == "E7":
            level = "留意" if pos else "正常"  # triads are only a prompt to check
        report.append(
            {
                "规则": rid,
                "名称": name,
                "命中": len(pos),
                "频率": round(rate, 2),
                "单位": "每千词",
                "判断": level,
                "改法": fix,
                "位置": pos[:12],
            }
        )
    bold = len(re.findall(r"\*\*[^*\n]+\*\*", "\n".join(t for _, t in body)))
    gates_ = (
        [{"项": "粗体", "数量": bold, "位置": [], "改法": "remove decorative bold"}]
        if bold > 2
        else []
    )
    return {
        "语言": "英文",
        "词数": words,
        "门槛": gates_,
        "聊天残留": [],
        "规则": report,
        "黑名单词": {},
        "偏高": [x["名称"] for x in report if x["判断"] == "偏高"],
    }


# ----------------------------------------------------------------------- diff

NUM = re.compile(
    r"\d+(?:[.,:：/-]\d+)*\s*(?:%|％)?|[零〇一二两三四五六七八九十百千万亿]+(?:个|位|名|次|年|月|日|号|天|周|小时|分钟|秒|倍|成|岁|元|块|万|亿|项|条|篇|人|家|款)"
)
QUOTE = re.compile(r"“[^”]{1,80}”|「[^」]{1,80}」|《[^》]{1,40}》|\"[^\"]{1,80}\"")
LATIN = re.compile(r"\b[A-Za-z][A-Za-z0-9.+#&-]{1,}\b")
NEG = re.compile(
    r"不是|并不|不会|不能|不要|不该|不用|不必|不再|不可|不需要|不行|没有|没|未|无(?=[人法需须关从])|并非|别|勿|"
    r"不(?=[\u4e00-\u9fff])(?![断少同仅只止过但然久妨错如住禁觉])"
)
# Rhetorical "不是…而是 / 不仅…更" frames are rewritten on purpose (rule Z1); they are not facts.
FRAMES = re.compile(
    r"(?:并?不是|并非|不在于)[^。！？\n]{1,25}?[，,]?\s*而(?:是|在于)|不仅|不只|不止"
)
SOFT_CHECKS = {"否定词", "限定词", "绝对化"}
ABSOLUTES = re.compile(r"所有|全部|一切|每一?个|任何|总是|从不|永远|必然|一定|完全|绝对|都会")
ORDINAL = re.compile(
    r"^(?:[一二三四五六七八九十]+、|第[一二三四五六七八九十]+[、，,：:\s]|\d+[.、]\s*)"
)
HEDGE = re.compile(
    r"可能|也许|或许|大概|大约|约|左右|似乎|估计|预计|应该|往往|通常|一般|部分|有些|一些|多数|少数|之一|尚未|暂"
)


def structure(text: str) -> dict[str, Any]:
    lines = prose_lines(text)
    raw = text.replace("\r\n", "\n")
    return {
        "标题": [ORDINAL.sub("", t) for _, k, t in lines if k == "heading"],
        "段落数": sum(1 for _, k, t in lines if k == "para" and t),
        "列表项数": sum(1 for _, k, _ in lines if k == "list"),
        "代码块": re.findall(r"```.*?```", raw, re.S),
        "表格行": [ln.strip() for ln in raw.split("\n") if ln.strip().startswith("|")],
        "链接": sorted(re.findall(r"https?://[^\s)>\]]+", raw)),
    }


def diff(old: str, new: str) -> dict[str, Any]:
    def bag(rx: re.Pattern[str], text: str) -> Counter[str]:
        items = (re.sub(r"\s+", "", m.group()) for m in rx.finditer(text))
        # "一位 / 一家" is an article-like measure word, not a number worth guarding.
        return Counter(x for x in items if not re.fullmatch(r"[一两][\u4e00-\u9fff]", x))

    def prose(text: str) -> str:
        return "\n".join(t for _, k, t in prose_lines(text) if k != "code")

    po, pn = prose(old), prose(new)
    changes: dict[str, Any] = {}
    for name, rx, text_o, text_n in (
        ("数字", NUM, po, pn),
        ("引语和书名", QUOTE, po, pn),
        ("英文和专名", LATIN, po, pn),
    ):
        a, b = bag(rx, text_o), bag(rx, text_n)
        added, removed = sorted((b - a).elements()), sorted((a - b).elements())
        if added or removed:
            changes[name] = {"新增": added[:20], "丢失": removed[:20]}
    neg_o, neg_n = len(NEG.findall(FRAMES.sub("", po))), len(NEG.findall(FRAMES.sub("", pn)))
    hedge_o, hedge_n = Counter(HEDGE.findall(po)), Counter(HEDGE.findall(pn))
    weaker = sorted((hedge_o - hedge_n).elements())
    if neg_n != neg_o:
        changes["否定词"] = {
            "原稿": neg_o,
            "改稿": neg_n,
            "说明": "否定词数量变了，检查有没有把否定改成肯定、肯定改成否定，或删掉了否定句",
        }
    stronger = sorted((Counter(ABSOLUTES.findall(pn)) - Counter(ABSOLUTES.findall(po))).elements())
    if stronger:
        changes["绝对化"] = {
            "新增": stronger[:20],
            "说明": "新增“所有、一定、总是”等词，范围或确定程度可能被改强",
        }
    if weaker:
        changes["限定词"] = {
            "减少": weaker[:20],
            "说明": "“可能、约、部分”等限定减少，确定程度可能被改强",
        }
    so, sn = structure(old), structure(new)
    struct = {}
    for key in ("标题", "段落数", "列表项数", "代码块", "表格行", "链接"):
        if so[key] != sn[key]:
            struct[key] = {
                "原稿": so[key] if not isinstance(so[key], list) else len(so[key]),
                "改稿": sn[key] if not isinstance(sn[key], list) else len(sn[key]),
            }
            if key == "标题":
                struct[key]["变化"] = [h for h in so[key] if h not in sn[key]][:5] + [
                    f"+{h}" for h in sn[key] if h not in so[key]
                ][:5]
    if struct:
        changes["结构"] = struct
    old_chars, new_chars = len(CJK.findall(po)), len(CJK.findall(pn))
    return {"原稿字数": old_chars, "改稿字数": new_chars, "变动": changes}


# -------------------------------------------------------------------- profile


def profile(texts: list[str]) -> dict[str, Any]:
    joined = "\n\n".join(texts)
    lines = prose_lines(joined)
    prose = "\n".join(t for _, k, t in lines if k in {"para", "list"})
    chars = max(len(CJK.findall(prose)), 1)
    sents = sentences(prose)
    paras = paragraphs(lines)
    per_k = lambda n: round(n / chars * 1000, 2)  # noqa: E731
    starts = Counter(
        re.match(r"[一-鿿]{1,2}", s).group() for s in sents if re.match(r"[一-鿿]{1,2}", s)
    )
    connectives = Counter(
        m.group()
        for m in re.finditer(
            r"不过|但是|但|所以|因此|然而|其实|而且|于是|反倒|可是|总之|另外|此外", prose
        )
    )
    rates = profile_rates(joined)
    return {
        "汉字数": chars,
        "句数": len(sents),
        "平均句长": round(sum(len(s) for s in sents) / max(len(sents), 1), 1),
        "平均段长": round(sum(len(p) for _, p in paras) / max(len(paras), 1), 1),
        "每千字标点": {
            "破折号": per_k(prose.count("——")),
            "冒号": per_k(prose.count("：")),
            "顿号": per_k(prose.count("、")),
            "问号": per_k(prose.count("？")),
            "感叹号": per_k(prose.count("！")),
            "省略号": per_k(prose.count("……")),
            "括号": per_k(prose.count("（")),
        },
        "粗体": len(re.findall(r"\*\*[^*\n]+\*\*", joined)),
        "常用句首": starts.most_common(10),
        "常用连接词": connectives.most_common(10),
        "规则频率": {r.id: round(rates[r.id], 2) for r in RULES},
    }


# ----------------------------------------------------------------------- main


def read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise CheckError(f"无法读取 {path}：{exc}") from None


def print_scan(res: dict[str, Any]) -> None:
    size = (
        f"{res['汉字数']} 字，{res['段落数']} 段" if res["语言"] == "中文" else f"{res['词数']} 词"
    )
    print(f"{res['语言']}文稿，{size}")
    for g in res["门槛"]:
        where = f"（行 {', '.join(map(str, g['位置']))}）" if g["位置"] else ""
        print(f"- [门槛] {g['项']} {g['数量']} 处{where}：{g['改法']}")
    for r in res["聊天残留"]:
        print(f"- [聊天残留] 行 {r['行']}：“{r['命中']}”——删掉")
    for r in res["规则"]:
        if not r["命中"]:
            continue
        base = f"，人类均值 {r['人类均值']}" if r.get("人类均值") is not None else ""
        print(
            f"\n[{r['判断']}] {r['规则']} {r['名称']}：{r['命中']} 处，{r['频率']} {r['单位']}{base}"
        )
        print(f"  改法：{r['改法']}")
        for p in r["位置"][:6]:
            print(f"  - 行 {p['行']}：{p['命中']}")
    if res["黑名单词"]:
        print(
            "\n黑名单词（命中不等于该删，看是否空泛、重复、不准）："
            + "、".join(f"{w}×{n}" for w, n in res["黑名单词"].items())
        )
    print(
        "\n结论："
        + ("偏高 " + "、".join(res["偏高"]) if res["偏高"] else "没有明显高于人类写作的项")
    )
    print(
        "说明：频率只反映写法差异，不能证明作者身份，也不保证通过 AI 检测；改稿后用 diff 核对信息有没有变。"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("input")
    s.add_argument("--profile", nargs="+", default=[], help="作者自己的旧稿，用于识别作者习惯")
    d = sub.add_parser("diff")
    d.add_argument("old")
    d.add_argument("new")
    p = sub.add_parser("profile")
    p.add_argument("inputs", nargs="+")
    for sp in (s, d, p):
        sp.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "scan":
            res = scan(read(args.input), [read(x) for x in args.profile])
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print_scan(res)
            return 3 if res["偏高"] or res["门槛"] or res["聊天残留"] else 0
        if args.cmd == "diff":
            res = diff(read(args.old), read(args.new))
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print(f"原稿 {res['原稿字数']} 字 → 改稿 {res['改稿字数']} 字")
                if not res["变动"]:
                    print("信息核对通过：数字、引语、专名、链接、否定和限定、结构都没有变化。")
                for k, v in res["变动"].items():
                    group = "请确认" if k in SOFT_CHECKS else "必须处理"
                    print(f"- [{group}·{k}] {json.dumps(v, ensure_ascii=False)}")
                if res["变动"]:
                    print(
                        "必须处理：新增的信息撤回，丢失的补回（确是重复内容除外）；请确认：按词频统计，同义改写也会触发，逐处看语义是否变了。"
                    )
            return 3 if res["变动"] else 0
        res = profile([read(x) for x in args.inputs])
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(
                f"样本 {res['汉字数']} 字，{res['句数']} 句；平均句长 {res['平均句长']} 字，平均段长 {res['平均段长']} 字"
            )
            print("每千字标点：" + "，".join(f"{k} {v}" for k, v in res["每千字标点"].items()))
            print(f"粗体 {res['粗体']} 处")
            print("常用句首：" + "、".join(f"{w}({n})" for w, n in res["常用句首"]))
            print("常用连接词：" + "、".join(f"{w}({n})" for w, n in res["常用连接词"]))
            habits = [r.name for r in RULES if r.ai and res["规则频率"][r.id] >= r.ai * 0.8]
            if habits:
                print("作者本人常用（改稿时不当作 AI 痕迹）：" + "、".join(habits))
        return 0
    except CheckError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
