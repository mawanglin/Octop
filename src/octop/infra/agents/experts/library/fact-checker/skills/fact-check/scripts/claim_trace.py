#!/usr/bin/env python3
"""事实溯源：把初稿里的数字、日期、引语逐句对到被引用来源的“摘录”上，找出对不上和没出处的断言。

Usage:
    python scripts/claim_trace.py 文章包.md [--json] [--strict]

规则：
  - 每个带事实的句子要在句末标 [S1] 这样的来源编号；核验只认线索包里“摘录”的原文，不认来源标题和备注。
  - 数字（含 % 万 亿 等换算）、日期、被引号框起来的引语（≥6 字）必须能在被引用的来源摘录里找到；
    引语必须逐字一致（忽略空白和标点）。
  - 在别的来源里找到、但引用的编号不对 → “引用错位”；没标编号但能在某条来源里找到 → “缺来源编号”；
    所标来源里找不到 → “对不上”；全文的摘录里都找不到 → “无出处”。
  - 由来源数字推算出来的句子，在句中加 [推算]，脚本只提示“需人工复算”，不会判为通过。
  - 引用“存疑”来源的句子必须带“有网友反映 / 据称 / 据传”这类限定语，否则判为把存疑内容写成了事实。
  - 来源摘录里没有、稿子里却出现的“最、第一、唯一、所有、首次”等绝对化词，列入“请确认”。
局限：只认阿拉伯数字，不识别“三百万”这类中文数字；只核对稿子和线索包是否一致，不能证明来源本身是真的。
Exit codes: 0 没有“必须处理”项, 3 有“必须处理”项（--strict 时“请确认”也算）, 1 输入错误。
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import article_pack as ap  # noqa: E402

MUST, CONFIRM = "必须处理", "请确认"
SPLIT_RE = re.compile(r"(?<=[。！？!?；;])|\n+")
INFER_RE = re.compile(r"\[推算\]")
STRIP_MARK_RE = re.compile(r"\[(?:S\d+(?:\s*[,，、]\s*S\d+)*|推算)\]")
DATE_PATTERNS = [
    re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?"),
    re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"),
    re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月"),
    re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]"),
    re.compile(r"(\d{4})\s*年"),
]
QUOTE_RE = re.compile(r"[“「『\"]([^”」』\"\n]{6,})[”」』\"]")
UNITS = (
    "%", "％", "个百分点", "万亿", "万", "亿", "千", "元", "美元", "欧元", "倍", "人", "家", "个", "台", "辆", "次",
    "年", "月", "日", "天", "小时", "分钟", "秒", "千瓦", "瓦", "度", "吨", "公里", "米", "平方米", "GB", "MB", "TB",
    "岁", "项", "条", "款", "套", "位", "所", "间", "栋", "座", "户", "亩", "页", "分", "期",
)  # fmt: skip
NUM_RE = re.compile(
    r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>"
    + "|".join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True))
    + ")?"
)
WEAK_UNITS = {
    "点",
    "项",
    "条",
    "款",
    "个",
    "位",
    "步",
    "种",
    "类",
}  # bare small integers with these are ordinals
MULTIPLIER = {"万亿": 1e12, "亿": 1e8, "万": 1e4, "千": 1e3}
ABSOLUTE_RE = re.compile(
    r"全国首[个家次]|史上|首个|首次|首家|唯一|第一|最(?:大|高|好|佳|强|早|新|多|少|低)|所有|全部|从未|必然|彻底|绝对"
)
HEDGE_RE = re.compile(
    r"有网友|网友(?:反映|称|表示)|据称|据传|据说|传闻|有人(?:称|说|认为)|个别说法|未经证实|尚无法核实|自称"
)
LATIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)+|[A-Z][A-Za-z0-9]{2,}")
BOOK_RE = re.compile(r"《([^》]{1,30})》")


@dataclass
class Finding:
    level: str
    kind: str
    sentence: str
    detail: str
    sources: list[str] = field(default_factory=list)


def squash(text: str) -> str:
    return re.sub(r"[\W_]+", "", text)


def extract_dates(text: str) -> tuple[list[tuple[int | None, int | None, int | None]], str]:
    """Dates found in *text* as (y, m, d) with None for missing parts, plus the text with dates blanked."""
    found: list[tuple[int | None, int | None, int | None]] = []
    for idx, pat in enumerate(DATE_PATTERNS):

        def grab(m: re.Match[str], idx: int = idx) -> str:
            g = [int(x) for x in m.groups()]
            if idx in (0, 1):
                found.append((g[0], g[1], g[2]))
            elif idx == 2:
                found.append((g[0], g[1], None))
            elif idx == 3:
                found.append((None, g[0], g[1]))
            else:
                found.append((g[0], None, None))
            return " " * len(m.group(0))

        text = pat.sub(grab, text)
    return found, text


def date_in(
    claim: tuple[int | None, int | None, int | None],
    pool: list[tuple[int | None, int | None, int | None]],
) -> bool:
    for cand in pool:
        if all(c is None or c == p for c, p in zip(claim, cand, strict=True)):
            return True
        # a full date in the source also supports a month-day or month claim
        if cand[0] is not None and claim[0] is None and (claim[1], claim[2]) == (cand[1], cand[2]):
            return True
    return False


def extract_numbers(text: str) -> list[tuple[float, str, str]]:
    """Numbers as (value, kind, shown). kind is 'pct' or 'num'; 万/亿 are expanded."""
    out: list[tuple[float, str, str]] = []
    for m in NUM_RE.finditer(text):
        raw, unit = m.group("num"), m.group("unit") or ""
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        kind = "num"
        if unit in ("%", "％", "个百分点"):
            kind = "pct"
        value *= MULTIPLIER.get(unit, 1)
        out.append((round(value, 4), kind, m.group(0).strip()))
    return out


def is_trivial(value: float, shown: str) -> bool:
    """Small bare integers (“3 点”“第 2 步”) are structure words, not facts."""
    unit = re.sub(r"[\d,.\s]", "", shown)
    return value < 10 and float(value).is_integer() and (unit == "" or unit in WEAK_UNITS)


def split_sentences(body: str) -> list[str]:
    parts = [p.strip() for p in SPLIT_RE.split(body) if p and p.strip()]
    merged: list[str] = []
    for p in parts:
        if merged and not STRIP_MARK_RE.sub("", p).strip(
            " 。！？!?；;，,"
        ):  # only a trailing marker
            merged[-1] += p
        else:
            merged.append(p)
    return merged


def body_lines(draft: str) -> tuple[str, str, str]:
    """(title, digest, body) with headings and the reference list removed from *body*."""
    title, digest, body = "", "", []
    for line in draft.splitlines():
        s = line.strip()
        if not title and re.match(r"^#\s+\S", s):
            title = s.lstrip("# ").strip()
            continue
        if re.match(r"^(?:摘要|导语)\s*[：:]", s):
            digest = re.sub(r"^(?:摘要|导语)\s*[：:]\s*", "", s)
            continue
        if re.match(r"^#{2,6}\s*(?:参考来源|参考资料|参考链接)\s*$", s):
            break
        if s.startswith("#") or s.startswith("![") or not s:
            continue
        body.append(s)
    return title, digest, "\n".join(body)


def hit_sources(sources: dict[str, ap.Source]) -> dict[str, str]:
    return {sid: s.excerpt for sid, s in sources.items()}


def trace(pack: ap.Pack) -> dict[str, object]:
    sources = {s.id: s for s in pack.sources()}
    excerpts = hit_sources(sources)
    squashed = {sid: squash(t) for sid, t in excerpts.items()}
    dates = {sid: extract_dates(t)[0] for sid, t in excerpts.items()}
    numbers = {
        sid: {(v, k) for v, k, _ in extract_numbers(extract_dates(t)[1])}
        for sid, t in excerpts.items()
    }
    draft = pack.draft()
    title, digest, body = body_lines(draft)
    all_cited = ap.citation_ids(draft)
    findings: list[Finding] = []

    def add(
        level: str, kind: str, sentence: str, detail: str, srcs: list[str] | None = None
    ) -> None:
        findings.append(Finding(level, kind, sentence.strip(), detail, srcs or []))

    def where_else(pred: Callable[[str], bool], cited: list[str]) -> list[str]:
        return [sid for sid in sources if sid not in cited and pred(sid)]

    claim_sentences = 0
    supported_sentences = 0
    units = [(title, all_cited, True), (digest, all_cited, True)] if title or digest else []
    units += [(s, ap.citation_ids(s), False) for s in split_sentences(body)]

    def miss(
        raw: str,
        pool: list[str],
        inferred: bool,
        kind_label: str,
        shown: str,
        pred: Callable[[str], bool],
        quote_hint: str = "",
    ) -> None:
        """Report a claim that none of the cited sources (*pool*) supports."""
        if inferred and kind_label != "引语":
            add(
                CONFIRM,
                "需人工复算",
                raw,
                f"{kind_label}“{shown}”标了 [推算]，请按来源数字复算",
                pool,
            )
            return
        elsewhere = where_else(pred, pool)
        if not pool:
            if elsewhere:
                add(
                    MUST,
                    "缺来源编号",
                    raw,
                    f"{kind_label}“{shown}”没标来源编号，它出现在 {'、'.join(elsewhere)} 的摘录里，请补上",
                    elsewhere,
                )
            else:
                add(
                    MUST,
                    "无出处",
                    raw,
                    f"{kind_label}“{shown}”没标来源，全文的来源摘录里也找不到",
                )
        elif elsewhere:
            add(
                MUST,
                "引用错位",
                raw,
                f"{kind_label}“{shown}”在 {'、'.join(elsewhere)} 的摘录里，不在所标的 {'、'.join(pool)} 里，请改引用编号",
                elsewhere,
            )
        else:
            add(
                MUST,
                "引语对不上" if kind_label == "引语" else "对不上",
                raw,
                f"{kind_label}“{shown}”在所标来源 {'、'.join(pool)} 的摘录里找不到{quote_hint}",
                pool,
            )

    for raw, cited, loose in units:
        if not raw:
            continue
        text = STRIP_MARK_RE.sub("", raw)
        inferred = bool(INFER_RE.search(raw))
        found_dates, rest = extract_dates(text)
        quotes = list(QUOTE_RE.findall(rest))
        rest_wo_quotes = QUOTE_RE.sub(" ", rest)
        nums = [
            (v, k, shown)
            for v, k, shown in extract_numbers(rest_wo_quotes)
            if not is_trivial(v, shown)
        ]
        absolutes = sorted(set(ABSOLUTE_RE.findall(text)))
        latin = sorted({w for w in LATIN_RE.findall(rest_wo_quotes) if not w.isdigit()})
        books = BOOK_RE.findall(text)
        has_fact = bool(found_dates or quotes or nums)
        weak = [sid for sid in cited if sources.get(sid) and sources[sid].status == "存疑"]
        if not (has_fact or absolutes or latin or books or weak):
            continue
        if has_fact:
            claim_sentences += 1
        pool = cited if cited else (all_cited if loose else [])
        unsupported_here = 0

        for q in quotes:
            sq = squash(q)
            if any(sq in squashed.get(sid, "") for sid in pool):
                continue
            unsupported_here += 1
            best, line = 0.0, ""
            for sid in pool or list(sources):
                for ln in excerpts.get(sid, "").splitlines():
                    r = difflib.SequenceMatcher(None, squash(ln), sq).ratio()
                    if r > best:
                        best, line = r, ln
            hint = (
                f"；最接近的原文：“{line}”（相似度 {best:.0%}），引语必须逐字一致"
                if best >= 0.5
                else ""
            )
            miss(raw, pool, inferred, "引语", q, lambda sid, sq=sq: sq in squashed[sid], hint)

        for d in found_dates:
            if any(date_in(d, dates.get(sid, [])) for sid in pool):
                continue
            unsupported_here += 1
            shown = "".join(
                f"{p}{u}" for p, u in zip(d, ("年", "月", "日"), strict=True) if p is not None
            )
            miss(raw, pool, inferred, "日期", shown, lambda sid, d=d: date_in(d, dates[sid]))

        for value, kind, shown in nums:
            if any((value, kind) in numbers.get(sid, set()) for sid in pool):
                continue
            unsupported_here += 1
            miss(
                raw,
                pool,
                inferred,
                "数字",
                shown,
                lambda sid, v=value, k=kind: (v, k) in numbers[sid],
            )

        for w in absolutes:
            if not any(w in excerpts.get(sid, "") for sid in pool):
                add(
                    CONFIRM,
                    "绝对化表述",
                    raw,
                    f"“{w}”在被引用的摘录里没有，确认来源是否真的这么说",
                    pool,
                )
        for w in latin:
            if not any(w.lower() in excerpts.get(sid, "").lower() for sid in pool):
                add(
                    CONFIRM,
                    "名称对不上",
                    raw,
                    f"“{w}”没有出现在被引用的摘录里，确认名称或型号拼写",
                    pool,
                )
        for b in books:
            if not any(b in excerpts.get(sid, "") for sid in pool):
                add(CONFIRM, "书名对不上", raw, f"《{b}》没有出现在被引用的摘录里", pool)

        if weak and not loose and not HEDGE_RE.search(text):
            add(
                MUST,
                "存疑写成事实",
                raw,
                f"{'、'.join(weak)} 状态是“存疑”，句子却没有“有网友反映/据称”这类限定语",
                weak,
            )
        shaky = [
            sid
            for sid in cited
            if sources.get(sid) and sources[sid].credibility in ("C", "D") and sid not in weak
        ]
        if shaky and not loose and has_fact and not HEDGE_RE.search(text):
            add(
                CONFIRM,
                "低可信来源",
                raw,
                f"{'、'.join(shaky)} 可信度为 {'/'.join(sources[s].credibility for s in shaky)}，确认是否需要限定语或换来源",
                shaky,
            )
        if has_fact and not unsupported_here and not loose:
            supported_sentences += 1

    unused = [sid for sid, s in sources.items() if sid not in all_cited and s.status != "不可用"]
    rank = {MUST: 0, CONFIRM: 1}
    findings.sort(key=lambda f: rank[f.level])
    return {
        "统计": {
            "带事实的句子": claim_sentences,
            "全部断言都对得上的句子": supported_sentences,
            "必须处理": sum(1 for f in findings if f.level == MUST),
            "请确认": sum(1 for f in findings if f.level == CONFIRM),
        },
        "没被引用的可用来源": unused,
        "发现": [f.__dict__ for f in findings],
    }


def render(res: dict[str, object]) -> str:
    st: dict[str, int] = res["统计"]  # type: ignore[assignment]
    out = [
        f"事实溯源：带事实的句子 {st['带事实的句子']} 句，其中全部断言都对得上的 {st['全部断言都对得上的句子']} 句",
        f"必须处理 {st['必须处理']} 条，请确认 {st['请确认']} 条",
        "",
    ]
    for level in (MUST, CONFIRM):
        rows = [f for f in res["发现"] if f["level"] == level]  # type: ignore[attr-defined]
        if not rows:
            continue
        out.append(f"## {level}")
        for f in rows:
            snippet = f["sentence"] if len(f["sentence"]) <= 60 else f["sentence"][:59] + "…"
            out.append(f"- [{f['kind']}] {f['detail']}")
            out.append(f"    句子：{snippet}")
        out.append("")
    if res["没被引用的可用来源"]:
        out.append(
            f"没被引用的可用来源：{'、'.join(res['没被引用的可用来源'])}（确认是有意舍弃还是漏用）"
        )  # type: ignore[arg-type]
    if not st["必须处理"] and not st["请确认"]:
        out.append("没有发现问题。")
    out.append("")
    out.append(
        "说明：只核对稿子和线索包是否一致，不能证明来源本身是真的；不识别中文数字；推算和绝对化表述需要人工判断。"
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="事实溯源")
    parser.add_argument("pack")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="“请确认”也让退出码变成 3")
    args = parser.parse_args(argv)
    try:
        pack = ap.read_pack(Path(args.pack))
    except SystemExit as exc:
        print(exc.code, file=sys.stderr)
        return 1
    if "初稿" not in pack.sections:
        print("文章包里还没有初稿", file=sys.stderr)
        return 1
    if "线索包" not in pack.sections:
        print("文章包里还没有线索包，没法溯源", file=sys.stderr)
        return 1
    res = trace(pack)
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else render(res))
    st: dict[str, int] = res["统计"]  # type: ignore[assignment]
    return 3 if st["必须处理"] or (args.strict and st["请确认"]) else 0


if __name__ == "__main__":
    sys.exit(main())
