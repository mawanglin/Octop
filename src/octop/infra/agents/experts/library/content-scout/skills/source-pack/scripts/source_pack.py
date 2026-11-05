#!/usr/bin/env python3
"""线索包工具：抓取网页并逐字摘录、登记来源、检查链接、去重、整理时间线。

Usage:
    python scripts/source_pack.py fetch URL [--match 关键词 ...] [--max 8] [--add-to 文章包.md --credibility B --status 可用]
    python scripts/source_pack.py add 文章包.md --title T --url U --credibility A|B|C|D [--publisher P] [--date 2026-11-01]
                                   [--status 可用|存疑|不可用] --excerpt "原文逐字摘录" [--excerpt ...] [--note 备注]
    python scripts/source_pack.py check 文章包.md [--timeout 10] [--write]
    python scripts/source_pack.py dedupe 文章包.md [--threshold 0.85] [--mark]
    python scripts/source_pack.py timeline 文章包.md
    python scripts/source_pack.py list 文章包.md

fetch 只做普通 HTTP 抓取：标题、发布日期（meta / time / JSON-LD）、发布方，以及含关键词的原句（作为“摘录”候选）。
摘录必须是原文逐字，所以 fetch 给出的句子就是页面里的原句，直接用，不要改写。
需要登录、要执行脚本才显示内容的页面抓不到，改用浏览器工具打开，把原文逐字粘到 add 的 --excerpt 里。
check 逐个访问来源链接，报告状态码和跳转；--write 把结果写进来源的“链接检查”字段。
Exit codes: 0 正常, 3 check 发现打不开的链接 / dedupe 发现重复, 1 输入错误。
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import article_pack as ap  # noqa: E402

UA = "Mozilla/5.0 (compatible; OctopContentScout/1.0)"
BLOCK_TAGS = {
    "p",
    "div",
    "br",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "tr",
    "section",
    "article",
    "blockquote",
}
SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg"}
DATE_META = (
    "article:published_time",
    "og:article:published_time",
    "datePublished",
    "pubdate",
    "publishdate",
    "date",
    "DC.date.issued",
)
TRACKING = re.compile(r"^(?:utm_\w+|spm|from|fbclid|gclid|share\w*)$")


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.times: list[str] = []
        self.lines: list[str] = []
        self.ld: list[str] = []
        self._skip = 0
        self._in_title = False
        self._in_ld = False
        self._buf: list[str] = []

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if text:
            self.lines.append(text)
        self._buf = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = a.get("property") or a.get("name") or a.get("itemprop") or ""
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"])
        elif tag == "time" and a.get("datetime"):
            self.times.append(a["datetime"])
        elif tag == "script" and "ld+json" in a.get("type", ""):
            self._in_ld = True
        if tag in SKIP_TAGS:
            self._skip += 1
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_ld = False
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif self._in_ld:
            self.ld.append(data)
        elif not self._skip:
            self._buf.append(data)

    def close(self) -> None:
        super().close()
        self._flush()


def decode(raw: bytes, content_type: str) -> str:
    m = re.search(r"charset=([\w-]+)", content_type, re.I) or re.search(
        rb"charset=[\"']?([\w-]+)", raw[:2048], re.I
    )
    names = [m.group(1) if isinstance(m.group(1), str) else m.group(1).decode()] if m else []
    for name in [*names, "utf-8", "gb18030"]:
        try:
            return raw.decode(name)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def http_get(url: str, timeout: float, method: str = "GET") -> tuple[int, str, str, bytes]:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - http(s) only, checked by callers
            return (
                resp.status,
                resp.geturl(),
                resp.headers.get("Content-Type", ""),
                resp.read(2_000_000) if method == "GET" else b"",
            )
    except urllib.error.HTTPError as exc:
        return exc.code, url, exc.headers.get("Content-Type", "") if exc.headers else "", b""


def need_http(url: str) -> None:
    if not re.match(r"^https?://", url):
        raise SystemExit("网址必须以 http:// 或 https:// 开头")


def publish_date(page: Page) -> str:
    candidates = [page.meta.get(k, "") for k in DATE_META] + page.times
    for blob in page.ld:
        try:
            data = json.loads(blob)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("datePublished"):
                candidates.append(str(item["datePublished"]))
    for c in candidates:
        m = re.search(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})", c)
        if m:
            return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return "未知"


def sentences(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        for part in re.split(r"(?<=[。！？!?；])", line):
            part = part.strip()
            if len(part) >= 8:
                out.append(part)
    return out


def fetch(url: str, matches: list[str], limit: int, timeout: float) -> dict[str, object]:
    need_http(url)
    status, final, ctype, raw = http_get(url, timeout)
    if status >= 400:
        raise SystemExit(f"抓取失败：HTTP {status}（{url}）")
    if "html" not in ctype.lower() and "xml" not in ctype.lower() and "text" not in ctype.lower():
        raise SystemExit(f"不是网页（Content-Type: {ctype or '未知'}），无法提取文字")
    page = Page()
    page.feed(decode(raw, ctype))
    page.close()
    title = (page.meta.get("og:title") or page.title).strip()
    sents = sentences(page.lines)
    chosen = [s for s in sents if any(k in s for k in matches)] if matches else sents
    return {
        "网址": final,
        "标题": re.sub(r"\s+", " ", title),
        "发布方": page.meta.get("og:site_name")
        or page.meta.get("author")
        or urllib.parse.urlparse(final).netloc,
        "发布日期": publish_date(page),
        "抓取时间": now(),
        "正文句数": len(sents),
        "摘录候选": chosen[:limit],
        "候选总数": len(chosen),
    }


def render_source(sid: str, f: dict[str, str], excerpts: list[str]) -> str:
    lines = [f"### {sid}"]
    for key in ("标题", "网址", "发布方", "发布日期", "抓取时间", "可信度", "状态"):
        lines.append(f"- {key}：{f[key]}")
    lines.append("- 摘录：")
    lines += [f"  > {e}" for e in excerpts]
    if f.get("备注"):
        lines.append(f"- 备注：{f['备注']}")
    return "\n".join(lines)


def append_source(path: Path, fields: dict[str, str], excerpts: list[str]) -> str:
    pack = ap.read_pack(path)
    if not pack.front:
        raise SystemExit("目标文件不是文章包，请先用 article_pack.py new 创建")
    existing = pack.sources()
    nxt = max((int(s.id[1:]) for s in existing), default=0) + 1
    sid = f"S{nxt}"
    block = render_source(sid, fields, excerpts)
    pack.sections["线索包"] = (pack.sections.get("线索包", "") + "\n\n" + block).strip()
    ap.write_pack(path, pack)
    return sid


def validated_fields(
    a: argparse.Namespace, title: str, url: str, publisher: str, date: str
) -> dict[str, str]:
    need_http(url)
    if a.credibility not in ap.CREDIBILITY:
        raise SystemExit(f"--credibility 只能是 {'、'.join(ap.CREDIBILITY)}")
    if a.status not in ap.SOURCE_STATUS:
        raise SystemExit(f"--status 只能是 {'、'.join(ap.SOURCE_STATUS)}")
    if date != "未知" and not ap.DATE_RE.match(date):
        raise SystemExit("--date 要写成 YYYY-MM-DD 或“未知”")
    return {
        "标题": title or "（无标题）",
        "网址": url,
        "发布方": publisher or urllib.parse.urlparse(url).netloc,
        "发布日期": date,
        "抓取时间": now(),
        "可信度": a.credibility,
        "状态": a.status,
        "备注": getattr(a, "note", "") or "",
    }


def cmd_fetch(a: argparse.Namespace) -> int:
    info = fetch(a.url, a.match or [], a.max, a.timeout)
    if a.add_to:
        if not info["摘录候选"]:
            print(
                "没有找到含关键词的原句，没有登记；换个关键词，或改用浏览器打开后手动 add",
                file=sys.stderr,
            )
            return 1
        if not a.credibility:
            print("--add-to 需要同时给 --credibility", file=sys.stderr)
            return 1
        f = validated_fields(
            a, str(info["标题"]), str(info["网址"]), str(info["发布方"]), str(info["发布日期"])
        )
        sid = append_source(Path(a.add_to), f, list(info["摘录候选"]))  # type: ignore[arg-type]
        print(f"已登记为 {sid}（{len(info['摘录候选'])} 条逐字摘录）")  # type: ignore[arg-type]
        return 0
    if a.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    print(
        f"标题：{info['标题']}\n网址：{info['网址']}\n发布方：{info['发布方']}\n发布日期：{info['发布日期']}"
    )
    print(f"摘录候选（共 {info['候选总数']} 句，显示 {len(info['摘录候选'])}）：")  # type: ignore[arg-type]
    for s in info["摘录候选"]:  # type: ignore[attr-defined]
        print(f"  > {s}")
    if info["发布日期"] == "未知":
        print("提示：页面里没找到发布日期，请到页面上确认后在 add 时手动填写。")
    return 0


def cmd_add(a: argparse.Namespace) -> int:
    if a.status != "不可用" and not [e for e in a.excerpt if e.strip()]:
        print("可用和存疑的来源必须至少有一条逐字摘录（--excerpt）", file=sys.stderr)
        return 1
    f = validated_fields(a, a.title, a.url, a.publisher or "", a.date)
    sid = append_source(Path(a.pack), f, [e.strip() for e in a.excerpt if e.strip()])
    print(f"已登记为 {sid}")
    return 0


def set_field(section: str, sid: str, key: str, value: str) -> str:
    """Set “- key：value” inside source *sid* of the 线索包 text (replace if present, else insert after 状态)."""
    lines = section.split("\n")
    start = next(
        (i for i, ln in enumerate(lines) if ap.SOURCE_HEAD_RE.match(ln) and ln.split()[1] == sid),
        None,
    )
    if start is None:
        return section
    end = next(
        (i for i in range(start + 1, len(lines)) if ap.SOURCE_HEAD_RE.match(lines[i])), len(lines)
    )
    new = f"- {key}：{value}"
    for i in range(start + 1, end):
        m = ap.FIELD_RE.match(lines[i])
        if m and m.group(1).strip() == key:
            lines[i] = new
            return "\n".join(lines)
    at = start
    for i in range(start + 1, end):
        m = ap.FIELD_RE.match(lines[i])
        if m and m.group(1).strip() == "状态":
            at = i
            break
    lines.insert(at + 1, new)
    return "\n".join(lines)


def cmd_check(a: argparse.Namespace) -> int:
    path = Path(a.pack)
    pack = ap.read_pack(path)
    rows: list[dict[str, object]] = []
    bad = 0
    for s in pack.sources():
        url = s.fields.get("网址", "")
        if s.status == "不可用" or not re.match(r"^https?://", url):
            continue
        try:
            status, final, _, _ = http_get(url, a.timeout, "GET")
            note = ""
            if status < 400 and final.rstrip("/") != url.rstrip("/"):
                note = f"跳转到 {final}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            status, note = 0, f"打不开：{getattr(exc, 'reason', exc)}"
        ok = 200 <= status < 400
        bad += 0 if ok else 1
        rows.append({"id": s.id, "网址": url, "状态码": status, "正常": ok, "说明": note})
        if a.write:
            stamp = f"{status or '失败'} @ {now()}" + (f"（{note}）" if note else "")
            pack.sections["线索包"] = set_field(pack.sections["线索包"], s.id, "链接检查", stamp)
    if a.write:
        ap.write_pack(path, pack)
    for r in rows:
        mark = "✓" if r["正常"] else "✗"
        print(
            f"{mark} {r['id']} {r['状态码'] or '失败'} {r['网址']}"
            + (f"  {r['说明']}" if r["说明"] else "")
        )
    print(f"共检查 {len(rows)} 条，{bad} 条打不开")
    return 3 if bad else 0


def norm_url(url: str) -> str:
    p = urllib.parse.urlparse(url.strip())
    query = sorted((k, v) for k, v in urllib.parse.parse_qsl(p.query) if not TRACKING.match(k))
    host = re.sub(r"^(?:www|m)\.", "", p.netloc.lower())
    return f"{host}{p.path.rstrip('/')}" + (f"?{urllib.parse.urlencode(query)}" if query else "")


def squash(text: str) -> str:
    return re.sub(r"[\W_]+", "", text)


def cmd_dedupe(a: argparse.Namespace) -> int:
    path = Path(a.pack)
    pack = ap.read_pack(path)
    sources = pack.sources()
    groups: list[tuple[str, str]] = []
    seen: dict[str, str] = {}
    pair_reason: dict[str, str] = {}
    for i, s in enumerate(sources):
        key = norm_url(s.fields.get("网址", ""))
        if key in seen:
            pair_reason[s.id] = f"网址与 {seen[key]} 相同"
        else:
            seen[key] = s.id
        for t in sources[:i]:
            if s.id in pair_reason:
                break
            ra, rb = squash(s.excerpt), squash(t.excerpt)
            if ra and rb and difflib.SequenceMatcher(None, ra, rb).ratio() >= a.threshold:
                pair_reason[s.id] = f"摘录与 {t.id} 高度相似（转载或同源）"
    for sid, why in pair_reason.items():
        groups.append((sid, why))
    if not groups:
        print("没有发现重复来源")
        return 0
    for sid, why in groups:
        print(f"- {sid}：{why}")
    if a.mark:
        for sid, why in groups:
            pack.sections["线索包"] = set_field(
                pack.sections["线索包"], sid, "备注", f"重复：{why}，计作同一来源，不增加可信度"
            )
        ap.write_pack(path, pack)
        print("已在重复来源的备注里标注")
    print("提示：转载和同源不是独立来源，核验“来源多样性”时只算一条。")
    return 3


def cmd_timeline(a: argparse.Namespace) -> int:
    rows = sorted(
        ap.read_pack(Path(a.pack)).sources(),
        key=lambda s: (s.fields.get("发布日期", "") in ("", "未知"), s.fields.get("发布日期", "")),
    )
    for s in rows:
        print(
            f"{s.fields.get('发布日期', '未知'):<11} {s.id:<4} [{s.credibility or '?'}/{s.status or '?'}] {s.fields.get('发布方', '')}：{s.fields.get('标题', '')}"
        )
    if not rows:
        print("线索包还是空的")
    return 0


def cmd_list(a: argparse.Namespace) -> int:
    pack = ap.read_pack(Path(a.pack))
    for s in pack.sources():
        n = len([ln for ln in s.excerpt.splitlines() if ln])
        print(
            f"{s.id}  [{s.credibility or '?'}/{s.status or '?'}] 摘录 {n} 条  {s.fields.get('标题', '')}  {s.fields.get('网址', '')}"
        )
    if not pack.sources():
        print("线索包还是空的")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap_ = argparse.ArgumentParser(description="线索包工具")
    sub = ap_.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("url")
    f.add_argument("--match", action="append", help="只取含这个关键词的句子，可多次给出")
    f.add_argument("--max", type=int, default=8)
    f.add_argument("--timeout", type=float, default=15)
    f.add_argument("--json", action="store_true")
    f.add_argument("--add-to", help="直接登记到这个文章包")
    f.add_argument("--credibility", default="")
    f.add_argument("--status", default="可用")
    f.add_argument("--note", default="")
    f.set_defaults(fn=cmd_fetch)
    ad = sub.add_parser("add")
    ad.add_argument("pack")
    ad.add_argument("--title", required=True)
    ad.add_argument("--url", required=True)
    ad.add_argument("--publisher", default="")
    ad.add_argument("--date", default="未知")
    ad.add_argument("--credibility", required=True)
    ad.add_argument("--status", default="可用")
    ad.add_argument("--excerpt", action="append", default=[])
    ad.add_argument("--note", default="")
    ad.set_defaults(fn=cmd_add)
    c = sub.add_parser("check")
    c.add_argument("pack")
    c.add_argument("--timeout", type=float, default=10)
    c.add_argument("--write", action="store_true")
    c.set_defaults(fn=cmd_check)
    d = sub.add_parser("dedupe")
    d.add_argument("pack")
    d.add_argument("--threshold", type=float, default=0.85)
    d.add_argument("--mark", action="store_true")
    d.set_defaults(fn=cmd_dedupe)
    for name, fn in (("timeline", cmd_timeline), ("list", cmd_list)):
        t = sub.add_parser(name)
        t.add_argument("pack")
        t.set_defaults(fn=fn)
    return ap_


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args))
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 1
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"网络错误：{getattr(exc, 'reason', exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
