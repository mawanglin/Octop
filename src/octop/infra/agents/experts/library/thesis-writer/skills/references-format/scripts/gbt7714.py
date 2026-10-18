#!/usr/bin/env python3
"""参考文献：BibTeX / CSV → GB/T 7714-2015 顺序编码制著录格式；检查已有参考文献列表的常见格式问题。

Usage:
    python scripts/gbt7714.py format 文献.bib [-o 参考文献.txt]
    python scripts/gbt7714.py format 文献.csv [-o 参考文献.txt]
    python scripts/gbt7714.py check 参考文献.txt

BibTeX：知网、万方、Google Scholar、Zotero、EndNote 都能导出；按文件中的顺序编号（即正文首次引用的顺序）。
CSV 列：类型,作者,题名,刊名,年,卷,期,页码,出版地,出版者,网址,发布日期,引用日期,DOI,编号
    类型用文献类型标识：J 期刊、M 图书、D 学位论文、C 会议论文、R 报告、S 标准、P 专利、N 报纸、EB/OL 网页；作者用 ; 分隔。
规则要点：作者超过 3 人只列前 3 人，后加“, 等”或“, et al.”；外文作者姓在前、全大写，名缩写不加点；
页码用“-”连接；中文文献也使用英文标点（GB/T 7714-2015 示例写法）。具体以学校或期刊的要求为准。
Exit codes: 0 ok, 1 输入错误或 check 发现问题。
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path

TYPE_MAP = {
    "article": "J", "book": "M", "inbook": "M", "phdthesis": "D", "mastersthesis": "D", "thesis": "D",
    "inproceedings": "C", "conference": "C", "proceedings": "C", "techreport": "R", "report": "R",
    "standard": "S", "patent": "P", "newspaper": "N", "online": "EB/OL", "webpage": "EB/OL", "misc": "Z",
}  # fmt: skip
CODES = {"J", "M", "D", "C", "R", "S", "P", "N", "EB/OL", "Z", "G", "A", "DB", "CP"}
CJK = re.compile(r"[一-鿿]")


class RefError(ValueError):
    pass


# ----------------------------------------------------------------------------------------------- parsing


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise RefError("文件编码无法识别")


def _bib_value(s: str, i: int) -> tuple[str, int]:
    """Read a BibTeX value starting at s[i] (brace-, quote- or bare-delimited)."""
    if s[i] == "{":
        depth, j = 0, i
        while j < len(s):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    return s[i + 1 : j], j + 1
            j += 1
        raise RefError("BibTeX 花括号不匹配")
    if s[i] == '"':
        j = s.index('"', i + 1)
        return s[i + 1 : j], j + 1
    m = re.match(r"[^,}\s]+", s[i:])
    return (m.group(0), i + m.end()) if m else ("", i)


def parse_bib(text: str) -> list[dict[str, str]]:
    out = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]*)\s*,", text):
        kind = m.group(1).lower()
        if kind in ("comment", "preamble", "string"):
            continue
        rec = {"_type": kind, "_key": m.group(2)}
        i = m.end()
        while i < len(text):
            fm = re.compile(r"\s*([A-Za-z_-]+)\s*=\s*").match(text, i)
            if not fm:
                break
            val, i = _bib_value(text, fm.end())
            rec[fm.group(1).lower()] = re.sub(
                r"\s+", " ", val.replace("{", "").replace("}", "")
            ).strip()
            sep = re.compile(r"\s*,?\s*").match(text, i)
            i = sep.end() if sep else i
            if i < len(text) and text[i] == "}":
                break
        out.append(rec)
    if not out:
        raise RefError("没有找到 BibTeX 条目（@article{…}）")
    return out


def bib_to_entry(r: dict[str, str]) -> dict[str, str]:
    code = TYPE_MAP.get(r["_type"], "Z")
    if code == "Z" and r.get("url"):
        code = "EB/OL"
    return {
        "类型": code,
        "作者": ";".join(
            a.strip()
            for a in re.split(r"\s+and\s+", r.get("author", "") or r.get("editor", ""))
            if a.strip()
        ),
        "题名": r.get("title", ""),
        "刊名": r.get("journal", "") or r.get("booktitle", "") or r.get("journaltitle", ""),
        "年": r.get("year", "") or r.get("date", "")[:4],
        "卷": r.get("volume", ""),
        "期": r.get("number", "") or r.get("issue", ""),
        "页码": r.get("pages", ""),
        "出版地": r.get("address", "") or r.get("location", ""),
        "出版者": r.get("publisher", "")
        or r.get("school", "")
        or r.get("institution", "")
        or r.get("organization", ""),
        "版本": r.get("edition", ""),
        "网址": r.get("url", ""),
        "发布日期": r.get("date", "") if len(r.get("date", "")) > 4 else "",
        "引用日期": r.get("urldate", ""),
        "DOI": r.get("doi", ""),
        "编号": r.get("number", "") if code in ("S", "P", "R") else "",
    }


def parse_csv(text: str) -> list[dict[str, str]]:
    rows = [
        {k.strip(): (v or "").strip() for k, v in row.items() if k}
        for row in csv.DictReader(io.StringIO(text))
    ]
    if not rows or "题名" not in rows[0]:
        raise RefError(
            "CSV 需要表头：类型,作者,题名,刊名,年,卷,期,页码,出版地,出版者,网址,发布日期,引用日期,DOI,编号"
        )
    for r in rows:
        r["类型"] = r.get("类型", "").strip("[]").upper() or "Z"
        r["作者"] = re.sub(r"[；;]", ";", r.get("作者", ""))
    return rows


# --------------------------------------------------------------------------------------------- formatting


def format_author(name: str) -> str:
    name = name.strip()
    if not name or CJK.search(name):
        return name.replace(" ", "")
    if "," in name:
        last, first = (x.strip() for x in name.split(",", 1))
    else:
        parts = name.split()
        if len(parts) == 1:
            return parts[0].upper()
        last, first = parts[-1], " ".join(parts[:-1])
    initials = " ".join(p[0].upper() for p in re.split(r"[\s.\-]+", first) if p)
    return f"{last.upper()} {initials}".strip()


def authors(field: str, chinese: bool) -> str:
    names = [format_author(a) for a in field.split(";") if a.strip()]
    if not names:
        return ""
    if len(names) > 3:
        return ", ".join(names[:3]) + (", 等" if chinese else ", et al")
    return ", ".join(names)


def pages(p: str) -> str:
    return re.sub(r"\s*(?:--|–|—|~|－)\s*", "-", p.strip())


def edition_text(edition: str, chinese: bool) -> str:
    """GB/T 7714: first editions are omitted; "2" → "2版" / "2nd ed"."""
    m = re.fullmatch(
        r"第?\s*(\d+)\s*(?:版|ed\.?|edition|nd|rd|th|st)?\s*(?:ed\.?)?", edition.strip(), re.I
    )
    if not m:
        return edition.strip()
    n = int(m.group(1))
    if n <= 1:
        return ""
    if chinese:
        return f"{n}版"
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix} ed"


def format_entry(e: dict[str, str]) -> str:
    code = e.get("类型", "Z") or "Z"
    chinese = bool(CJK.search(e.get("题名", "") + e.get("作者", "")))
    au = authors(e.get("作者", ""), chinese)
    title = e.get("题名", "").rstrip(".")
    year, vol, no, pg = e.get("年", ""), e.get("卷", ""), e.get("期", ""), pages(e.get("页码", ""))
    place, pub = e.get("出版地", ""), e.get("出版者", "")
    url, doi = e.get("网址", ""), e.get("DOI", "")
    online = bool(url) and code not in ("EB/OL",)
    tag = f"[{code}/OL]" if online and code in ("J", "M", "D", "C", "N") else f"[{code}]"
    head = f"{au}. " if au else ""

    def pubinfo() -> str:
        loc = ": ".join(x for x in (place, pub) if x)
        return ", ".join(x for x in (loc, year) if x)

    if code == "J":
        body = f"{head}{title}{tag}. {e.get('刊名', '')}, {year}"
        if vol:
            body += f", {vol}"
        if no:
            body += f"({no})" if vol else f", ({no})"
        if pg:
            body += f": {pg}"
    elif code in ("M", "R"):
        ed = edition_text(e.get("版本", ""), chinese)
        ed = f". {ed}" if ed else ""
        body = f"{head}{title}{tag}{ed}. {pubinfo()}"
        if pg:
            body += f": {pg}"
    elif code == "D":
        body = f"{head}{title}{tag}. {pubinfo()}"
    elif code == "C":
        book = e.get("刊名", "")
        body = (
            f"{head}{title}{tag}//{book}. {pubinfo()}"
            if book
            else f"{head}{title}{tag}. {pubinfo()}"
        )
        if pg:
            body += f": {pg}"
    elif code == "S":
        num = e.get("编号", "")
        body = f"{head}{title}{': ' + num if num else ''}{tag}. {pubinfo()}"
    elif code == "P":
        num = e.get("编号", "")
        body = f"{head}{title}{': ' + num if num else ''}{tag}. {e.get('发布日期', '') or year}"
    elif code == "N":
        body = f"{head}{title}{tag}. {e.get('刊名', '')}, {e.get('发布日期', '') or year}"
        if no:
            body += f"({no})"
    elif code == "EB/OL":
        pubd, cite = e.get("发布日期", ""), e.get("引用日期", "")
        body = (
            f"{head}{title}{tag}. " + (f"({pubd})" if pubd else "") + (f"[{cite}]" if cite else "")
        )
        body = body.rstrip(". ").rstrip()
        url_part = f". {url}" if url else ""
        return f"{body}{url_part}" + (f". DOI:{doi}." if doi else ("" if url else "."))
    else:
        body = f"{head}{title}{tag}. {pubinfo()}"
    body = re.sub(r"\s+,", ",", body).rstrip(", .")
    if online:
        cite = e.get("引用日期", "")
        body += (f"[{cite}]" if cite else "") + f". {url}"
    if doi:
        body += f". DOI:{doi}"
    return body + "."


def missing_fields(e: dict[str, str]) -> list[str]:
    need = {"J": ["作者", "题名", "刊名", "年"], "M": ["作者", "题名", "出版者", "年"], "D": ["作者", "题名", "出版者", "年"],
            "C": ["作者", "题名", "年"], "S": ["题名", "编号"], "P": ["题名", "编号"], "EB/OL": ["题名", "网址"]}  # fmt: skip
    lack = [f for f in need.get(e.get("类型", ""), ["题名"]) if not e.get(f)]
    if e.get("类型") in ("M", "D") and not e.get("出版地"):
        lack.append("出版地")
    if e.get("类型") == "J" and not e.get("页码"):
        lack.append("页码")
    if e.get("类型") == "EB/OL" and not e.get("引用日期"):
        lack.append("引用日期")
    return lack


def cmd_format(src: Path, out: Path | None) -> int:
    text = _decode(src.read_bytes())
    entries = (
        [bib_to_entry(r) for r in parse_bib(text)]
        if src.suffix.lower() == ".bib"
        else parse_csv(text)
    )
    lines, warns = [], []
    for i, e in enumerate(entries, start=1):
        if e.get("类型", "") not in CODES:
            raise RefError(f"第 {i} 条的类型「{e.get('类型')}」不是 GB/T 7714 文献类型标识")
        lines.append(f"[{i}] {format_entry(e)}")
        lack = missing_fields(e)
        if lack:
            warns.append(f"[{i}] 缺少：{'、'.join(lack)}（{e.get('题名', '')[:20]}）")
    result = "\n".join(lines) + "\n"
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result, encoding="utf-8")
        print(f"已生成 {out}：{len(lines)} 条参考文献")
    else:
        print(result, end="")
    if warns:
        print(
            "需要补充信息（请对照原文献，不要编造）：", file=sys.stderr if not out else sys.stdout
        )
        for w in warns:
            print(f"- {w}", file=sys.stderr if not out else sys.stdout)
    return 0


# -------------------------------------------------------------------------------------------------- check


def check_lines(text: str) -> list[str]:
    issues: list[str] = []
    refs = [ln.strip() for ln in text.splitlines() if ln.strip()]
    seen: dict[str, int] = {}
    expect = 1
    for ln in refs:
        m = re.match(r"^\[(\d+)\]\s*(.*)$", ln)
        if not m:
            issues.append(f"「{ln[:30]}」没有以 [序号] 开头")
            continue
        n, body = int(m.group(1)), m.group(2)
        if n != expect:
            issues.append(f"[{n}] 序号不连续（应为 [{expect}]）")
        expect = n + 1
        code = re.search(r"\[(J|M|D|C|R|S|P|N|EB/OL|Z|G|A|DB|CP)(?:/OL)?\]", body)
        if not code:
            issues.append(f"[{n}] 缺少文献类型标识，如 [J] [M] [D] [EB/OL]")
        if not re.search(r"(?:19|20)\d{2}", body):
            issues.append(f"[{n}] 没有出版年份")
        chinese = bool(CJK.search(body))
        if not chinese and re.search(r"[，。：；（）]", body):
            issues.append(f"[{n}] 外文文献中使用了中文标点")
        if chinese and re.search(r"[，：；]", body):
            issues.append(f"[{n}] 使用了中文标点（，：；），GB/T 7714 示例使用英文标点加空格")
        if re.search(r"\d\s*(?:--|–|—|~)\s*\d", body):
            issues.append(f"[{n}] 页码范围请用“-”连接")
        if chinese and re.search(r"et al", body):
            issues.append(f"[{n}] 中文文献作者省略应写“等”")
        if not chinese and "等" in body:
            issues.append(f"[{n}] 外文文献作者省略应写“et al”")
        au = body.split(". ", 1)[0]
        if au.count(",") >= 3 and "等" not in au and "et al" not in au:
            issues.append(f"[{n}] 作者超过 3 人时只列前 3 人，后加“, 等”或“, et al”")
        if (
            code
            and code.group(1) == "J"
            and not re.search(r"\d{4}\s*,\s*\d+|\d{4}\s*,\s*\(\d+\)|\d{4}\s*\(\d+\)", body)
        ):
            issues.append(f"[{n}] 期刊文献请写“年, 卷(期): 页码”")
        if code and code.group(1) == "EB/OL" and not re.search(r"https?://", body):
            issues.append(f"[{n}] 网络文献缺少网址")
        key = re.sub(r"\W", "", body.lower())[:60]
        if key in seen:
            issues.append(f"[{n}] 与 [{seen[key]}] 重复")
        seen[key] = n
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("format")
    f.add_argument("input")
    f.add_argument("-o", "--output")
    c = sub.add_parser("check")
    c.add_argument("input")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "format":
            return cmd_format(Path(args.input), Path(args.output) if args.output else None)
        issues = check_lines(_decode(Path(args.input).read_bytes()))
    except (OSError, RefError, ValueError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    print(f"检查完成：发现 {len(issues)} 个问题")
    for i in issues:
        print(f"- {i}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
