#!/usr/bin/env python3
"""电子书整理：读取 epub / pdf / mobi / azw3 / txt 的书名作者，统一命名、查重，生成书单。

Usage:
    python scripts/ebook_tool.py scan 书库目录 [--json]
    python scripts/ebook_tool.py plan 书库目录 --dest 整理后目录 -o 整理方案.csv [--layout "{author}/{author} - {title}"]
    python scripts/ebook_tool.py dupes 书库目录 -o 重复方案.csv
    python scripts/ebook_tool.py catalog 书库目录 -o 书单.xlsx

书名作者来源（按优先级）：书内元数据（epub 的 OPF、mobi/azw3 的 EXTH、pdf 的文档信息）→ 文件名
（“书名 - 作者”“作者 - 书名”“《书名》作者”“[作者]书名”“书名(作者)”等常见写法）。
元数据里“Microsoft Word - xxx”“Administrator”“未命名”这类无意义的值会被忽略。
layout 可用 {author} {title} {year} {lang} {format}；同一本书的不同格式（epub + pdf）会放在一起。
方案用同目录的 media_ops.py 执行：python scripts/media_ops.py apply 整理方案.csv --root 根目录
本工具只读文件、只生成方案。Exit codes: 0 ok, 1 输入错误。
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from media_ops import (
    DUPES_DIR,
    OpsError,
    find_duplicates,
    human_size,
    iter_files,
    safe_name,
    write_plan,
)

EXTS = (".epub", ".pdf", ".mobi", ".azw3", ".azw", ".txt", ".djvu", ".fb2")
JUNK_META = re.compile(r"^(microsoft word|untitled|未命名|无标题|unknown|administrator|admin|user|作者|pdf|"
                       r"calibre|www\.|http|\d+$|[a-z]:\\\\)", re.I)  # fmt: skip
DC = "{http://purl.org/dc/elements/1.1/}"


class BookError(ValueError):
    pass


@dataclass
class Book:
    path: str
    format: str
    title: str
    author: str
    lang: str = ""
    publisher: str = ""
    year: str = ""
    isbn: str = ""
    source: str = "文件名"
    size: int = 0


def clean(value: str | None) -> str:
    v = re.sub(r"\s+", " ", (value or "").replace("\x00", "")).strip(" .-_")
    return "" if not v or JUNK_META.match(v) else v


def norm_author(a: str) -> str:
    """Drop nationality brackets, role suffixes and translators: "[美] 张三 著；李四 译" → "张三"."""
    a = re.split(r"[;；]|\s+译|\s+翻译", a)[0]
    a = re.sub(r"^[\[［【〔(（]\s*[一-鿿]{1,3}\s*[\]］】〕)）]\s*", "", a.strip())
    a = re.sub(r"\s*(?:编著|主编|著|编|撰|等著|等)$", "", a)
    parts = [p.strip() for p in re.split(r"\s*[，、&]\s*|\s+and\s+", a) if p.strip()]
    if not parts:
        return ""
    first = parts[0]
    if first.count(",") == 1 and not re.search(r"[\u4e00-\u9fff]", first):
        last, given = (x.strip() for x in first.split(","))
        first = f"{given} {last}".strip()  # calibre style "Harari, Yuval Noah"
    elif "," in first:
        names = [x.strip() for x in first.split(",") if x.strip()]
        first, parts = names[0], names
    return first + (" 等" if len(parts) > 1 else "")


def read_epub(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as z:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        rootfile = next(
            el.get("full-path") for el in container.iter() if el.tag.endswith("rootfile")
        )
        opf = ET.fromstring(z.read(str(rootfile)))
    meta: dict[str, str] = {}
    for key, tag in (("title", "title"), ("author", "creator"), ("lang", "language"), ("publisher", "publisher"),
                     ("year", "date")):  # fmt: skip
        el = opf.find(f".//{DC}{tag}")
        if el is not None and el.text:
            meta[key] = el.text
    for el in opf.iter(f"{DC}identifier"):
        digits = re.sub(r"[^\dXx]", "", el.text or "")
        if len(digits) in (10, 13) and (
            "isbn" in (el.text or "").lower()
            or digits.startswith(("978", "979"))
            or len(digits) == 10
        ):
            meta["isbn"] = digits
            break
    return meta


def read_mobi(path: Path) -> dict[str, str]:
    data = path.read_bytes()
    if len(data) < 86 or data[60:68] not in (b"BOOKMOBI", b"TEXtREAd"):
        return {}
    rec0 = struct.unpack(">I", data[78:82])[0]
    r = data[rec0:]
    meta: dict[str, str] = {}
    if r[16:20] != b"MOBI":
        return meta
    header_len, encoding = struct.unpack(">II", r[20:28])[0], struct.unpack(">I", r[28:32])[0]
    codec = "utf-8" if encoding == 65001 else "cp1252"
    name_off, name_len = struct.unpack(">II", r[84:92])
    meta["title"] = r[name_off : name_off + name_len].decode(codec, "replace")
    exth_flag = struct.unpack(">I", r[128:132])[0]
    if exth_flag & 0x40:
        pos = 16 + header_len
        if r[pos : pos + 4] == b"EXTH":
            count = struct.unpack(">I", r[pos + 8 : pos + 12])[0]
            p = pos + 12
            for _ in range(count):
                typ, ln = struct.unpack(">II", r[p : p + 8])
                val = r[p + 8 : p + ln].decode(codec, "replace")
                key = {
                    100: "author",
                    101: "publisher",
                    104: "isbn",
                    106: "year",
                    503: "title",
                    524: "lang",
                }.get(typ)
                if key == "title" or (key and key not in meta):
                    meta[key] = (
                        val  # EXTH 503 (updated title) beats the PalmDB full name; first author wins
                    )
                p += ln
    return meta


def read_pdf(path: Path) -> dict[str, str]:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - environment check
        return {}
    try:
        info = PdfReader(str(path)).metadata or {}
    except Exception:  # noqa: BLE001 - damaged PDFs fall back to the file name
        return {}
    return {"title": str(info.get("/Title") or ""), "author": str(info.get("/Author") or "")}


FILENAME_PATTERNS = [
    re.compile(r"^《(?P<title>[^》]+)》\s*[-_ ]*\s*(?P<author>.*)$"),
    re.compile(r"^[\[【](?P<author>[^\]】]+)[\]】]\s*(?P<title>.+)$"),
    re.compile(r"^(?P<title>.+?)\s*[（(](?P<author>[^()（）]+?)(?:\s*著)?[)）]$"),
    re.compile(r"^(?P<a>.+?)\s+[-–—]\s+(?P<b>.+)$"),
]


SURNAMES = set(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾"
    "夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤常温康施文牛樊葛邢安齐易乔伍庞颜倪庄聂章鲁岳翟殷詹"
    "申欧耿关兰焦俞左柳甘祝包宁尚符舒阮柯纪梅童凌毕单季裴霍涂成苗谷盛曲翁冉骆蓝路游辛靳管柴蒙鲍华喻祁蒲房滕屈饶解牟艾尤阳时穆农司"
    "卓古吉缪简车项连芦麦褚娄窦戚岑景党宫费卜冷晏席卫米柏宗瞿桂全佟应臧闵苟邬边卞姬师和仇栾隋商刁沙荣巫寇桑郎甄丛仲虞敖巩明佘池查麻苑迟邝"
)
COMPOUND_SURNAMES = (
    "欧阳",
    "司马",
    "诸葛",
    "上官",
    "东方",
    "皇甫",
    "尉迟",
    "公孙",
    "慕容",
    "令狐",
    "长孙",
    "宇文",
    "夏侯",
    "端木",
)


def looks_like_cn_name(text: str) -> bool:
    if "·" in text and re.fullmatch(r"[\u4e00-\u9fff·]{3,12}", text):
        return True  # transliterated foreign names: 尤瓦尔·赫拉利
    if not re.fullmatch(r"[\u4e00-\u9fff]{2,4}", text):
        return False
    return text.startswith(COMPOUND_SURNAMES) or (text[0] in SURNAMES and len(text) <= 3)


def from_filename(stem: str) -> tuple[str, str]:
    stem = re.sub(
        r"[（(\[]?(?:z-lib\.org|epub|mobi|azw3|pdf|txt|精排版|完整版|高清|校对版|全本)[)）\]]?",
        "",
        stem,
        flags=re.I,
    ).strip(" ._-")
    for i, rx in enumerate(FILENAME_PATTERNS):
        m = rx.match(stem)
        if not m:
            continue
        if i < 3:
            return m.group("title").strip(), m.group("author").strip()
        a, b = m.group("a").strip(), m.group("b").strip()
        # "作者 - 书名" only when the first part looks like a person's name and the second doesn't.
        if looks_like_cn_name(a) and not looks_like_cn_name(b):
            return b, a
        if re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z]\.?)*(?:\s+[A-Z][a-z]+)+", a) and not re.fullmatch(
            r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", b
        ):
            return b, a
        return a, b
    return stem, ""


def read_book(path: Path) -> Book:
    fmt = path.suffix.lower().lstrip(".")
    meta: dict[str, str] = {}
    try:
        if fmt == "epub":
            meta = read_epub(path)
        elif fmt in ("mobi", "azw3", "azw"):
            meta = read_mobi(path)
        elif fmt == "pdf":
            meta = read_pdf(path)
    except (
        OSError,
        KeyError,
        ValueError,
        StopIteration,
        zipfile.BadZipFile,
        ET.ParseError,
        struct.error,
    ):
        meta = {}
    title, author = clean(meta.get("title")), norm_author(clean(meta.get("author")))
    ft, fa = from_filename(path.stem)
    source = "元数据" if title else "文件名"
    if not title:
        title = ft
    if not author:
        author = norm_author(fa)
        if author and source == "元数据":
            source = "元数据+文件名"
    year = re.search(r"(19|20)\d{2}", meta.get("year", ""))
    return Book(str(path), fmt, title.strip(), author, clean(meta.get("lang"))[:5], clean(meta.get("publisher")),
                year.group(0) if year else "", meta.get("isbn", ""), source, path.stat().st_size)  # fmt: skip


def key_of(b: Book) -> str:
    return re.sub(r"[\W_]+", "", (b.title + "|" + b.author).lower())


def scan(root: Path) -> list[Book]:
    books = [read_book(p) for p in iter_files(root, EXTS)]
    if not books:
        raise BookError(f"{root} 里没有电子书（{'/'.join(EXTS)}）")
    return books


def txt_encoding(path: Path) -> str:
    raw = path.read_bytes()[:65536]
    try:
        raw.decode("utf-8")
        return "UTF-8"
    except UnicodeDecodeError:
        pass
    try:
        raw.decode("gb18030")
        return "GBK"
    except UnicodeDecodeError:
        return "未知"


def cmd_scan(root: Path, as_json: bool) -> int:
    books = scan(root)
    fmts = Counter(b.format for b in books)
    no_author = [b for b in books if not b.author]
    groups: dict[str, list[Book]] = defaultdict(list)
    for b in books:
        groups[key_of(b)].append(b)
    same_fmt = [g for g in groups.values() if len(g) > 1 and len({b.format for b in g}) < len(g)]
    multi_fmt = [g for g in groups.values() if len({b.format for b in g}) > 1]
    gbk = [b for b in books if b.format == "txt" and txt_encoding(Path(b.path)) == "GBK"]
    if as_json:
        print(
            json.dumps(
                {"总数": len(books), "格式": dict(fmts), "书": [asdict(b) for b in books]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(
        f"{root}：{len(books)} 本，{human_size(sum(b.size for b in books))}；"
        + "、".join(f"{k} {v}" for k, v in fmts.most_common())
    )
    print(
        f"书名来自元数据 {sum(1 for b in books if b.source.startswith('元数据'))} 本，来自文件名 {sum(1 for b in books if b.source == '文件名')} 本"
    )
    if no_author:
        print(
            f"没有识别出作者 {len(no_author)} 本（整理时放在“未知作者”）："
            + "、".join(Path(b.path).name for b in no_author[:8])
        )
    if same_fmt:
        print(f"同一本书同一格式有多个文件 {len(same_fmt)} 组（可能是不同版本，请确认）：")
        for g in same_fmt[:10]:
            print("- " + " | ".join(f"{Path(b.path).name}（{human_size(b.size)}）" for b in g))
    if multi_fmt:
        print(f"同一本书有多种格式 {len(multi_fmt)} 本（整理时会放在一起）")
    if gbk:
        print(f"GBK 编码的 txt {len(gbk)} 本，部分阅读器（Kindle、手机）可能乱码，可另存为 UTF-8")
    return 0


def render(layout: str, b: Book) -> Path:
    values = {"author": safe_name(b.author or "未知作者", 60), "title": safe_name(b.title or "未命名", 100),
              "year": b.year or "未知年份", "lang": b.lang or "未知语言", "format": b.format}  # fmt: skip
    try:
        rel = layout.format(**values)
    except KeyError as exc:
        raise BookError(
            f"layout 不支持 {exc}，可用 {{author}} {{title}} {{year}} {{lang}} {{format}}"
        ) from None
    parts = [safe_name(p) for p in rel.split("/") if p.strip()]
    return Path(*parts)


def cmd_plan(root: Path, dest: Path, out: Path, layout: str) -> int:
    books = [read_book(p) for p in iter_files(root, EXTS, exclude=dest)]
    if not books:
        raise BookError(f"{root} 里没有电子书")
    rows: list[tuple[str, str, str]] = []
    taken: set[str] = set()
    for b in sorted(books, key=lambda x: x.path):
        src = Path(b.path)
        rel = render(layout, b)
        target = dest / rel.parent / f"{rel.name}.{b.format}"
        n = 2
        while str(target).lower() in taken or (
            target.exists() and target.resolve() != src.resolve()
        ):
            target = dest / rel.parent / f"{rel.name} ({n}).{b.format}"
            n += 1
        taken.add(str(target).lower())
        if target.resolve() == src.resolve():
            continue
        note = f"{b.source}：{b.title} / {b.author or '未知作者'}"
        rows.append((str(src), str(target), note))
    write_plan(rows, out)
    unknown = sum(1 for b in books if not b.author)
    print(
        f"已生成 {out}：{len(rows)} 本待整理到 {dest}"
        + (f"，其中 {unknown} 本没有识别出作者" if unknown else "")
    )
    print("请先检查“说明”列中来自文件名的书名作者是否正确，可在表格中直接修改目标路径。")
    return 0


def cmd_dupes(root: Path, out: Path) -> int:
    files = list(iter_files(root, EXTS))
    groups = find_duplicates(files)
    rows = []
    for g in groups:
        keeper = min(g, key=lambda p: (len(str(p)), str(p)))
        for p in g:
            if p != keeper:
                rows.append(
                    (
                        str(p),
                        str(root / DUPES_DIR / p.relative_to(root)),
                        f"与 {keeper.relative_to(root)} 完全相同",
                    )
                )
    write_plan(rows, out)
    print(f"已生成 {out}：{len(groups)} 组完全相同的文件，{len(rows)} 个将移到 {DUPES_DIR}/")
    print(
        "书名相同但内容不同的文件（不同版本、不同排版）不会自动处理，见 scan 的“同一本书同一格式有多个文件”。"
    )
    return 0


def cmd_catalog(root: Path, out: Path) -> int:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except ImportError:  # pragma: no cover - environment check
        print("缺少依赖 openpyxl：请运行 `pip install openpyxl`", file=sys.stderr)
        return 2
    books = scan(root)
    wb = Workbook()
    ws = wb.active
    ws.title = "书单"
    header = [
        "书名",
        "作者",
        "格式",
        "大小",
        "语言",
        "出版社",
        "出版年",
        "ISBN",
        "来源",
        "相对路径",
        "已读",
        "评分",
        "笔记",
    ]
    ws.append(header)
    for b in sorted(books, key=lambda x: (x.author or "~", x.title)):
        ws.append([b.title, b.author, b.format, human_size(b.size), b.lang, b.publisher, b.year, b.isbn, b.source,
                   str(Path(b.path).relative_to(root)), "", "", ""])  # fmt: skip
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="92400E")
    for col, w in zip("ABCDEFGHIJKLM", (32, 16, 7, 9, 7, 16, 8, 15, 10, 40, 6, 6, 30), strict=True):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:M{ws.max_row}"
    stats = wb.create_sheet("统计")
    stats.append(["作者", "数量"])
    for a, n in Counter(b.author or "未知作者" for b in books).most_common():
        stats.append([a, n])
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    print(f"已生成 {out}：{len(books)} 本，{len({b.author for b in books if b.author})} 位作者")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("root")
    s.add_argument("--json", action="store_true")
    p = sub.add_parser("plan")
    p.add_argument("root")
    p.add_argument("--dest", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--layout", default="{author}/{author} - {title}")
    d = sub.add_parser("dupes")
    d.add_argument("root")
    d.add_argument("-o", "--output", required=True)
    c = sub.add_parser("catalog")
    c.add_argument("root")
    c.add_argument("-o", "--output", required=True)
    args = parser.parse_args(argv)
    try:
        root = Path(args.root)
        if not root.is_dir():
            raise BookError(f"{root} 不是目录")
        if args.cmd == "scan":
            return cmd_scan(root, args.json)
        if args.cmd == "plan":
            return cmd_plan(root, Path(args.dest), Path(args.output), args.layout)
        if args.cmd == "dupes":
            return cmd_dupes(root, Path(args.output))
        return cmd_catalog(root, Path(args.output))
    except (OSError, BookError, OpsError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
