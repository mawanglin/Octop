#!/usr/bin/env python3
"""错题本：Markdown 错题记录 → Excel（按遗忘曲线排复习日期、按学科知识点统计），并列出今天该复习的题。

Usage:
    python scripts/mistakes.py build 错题.md -o 错题本.xlsx [--merge 旧错题本.xlsx]
    python scripts/mistakes.py due 错题本.xlsx [--today 2026-10-18]

错题 Markdown 表头：
    | 日期 | 学科 | 知识点 | 题目 | 错误答案 | 正确答案 | 错因 | 来源 |
（日期、学科、知识点、题目 必填；错因建议写：概念不清 / 计算失误 / 审题不清 / 粗心 / 不会做 / 方法不对。）
复习按艾宾浩斯遗忘曲线安排在错题日期后的第 1、2、4、7、15 天。用户在 Excel 的“已掌握”列填“是”后，该题不再出现在待复习中。
Exit codes: 0 ok, 1 输入错误, 2 缺少 openpyxl。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from collections import Counter
from pathlib import Path

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill
except ImportError:  # pragma: no cover - environment check
    print("缺少依赖 openpyxl：请运行 `pip install openpyxl`", file=sys.stderr)
    sys.exit(2)

FIELDS = ["日期", "学科", "知识点", "题目", "错误答案", "正确答案", "错因", "来源"]
INTERVALS = (1, 2, 4, 7, 15)
REVIEW_COLS = [f"复习{i + 1}" for i in range(len(INTERVALS))]
HEADER_FILL = PatternFill("solid", fgColor="2563EB")
DUE_FILL = PatternFill("solid", fgColor="FEF3C7")


class BookError(ValueError):
    pass


def parse_date(text: object) -> dt.date:
    if isinstance(text, dt.datetime):
        return text.date()
    if isinstance(text, dt.date):
        return text
    s = str(text).strip().replace("/", "-").replace(".", "-")
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s) or re.fullmatch(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日", s
    )
    if not m:
        raise BookError(f"日期「{text}」应写成 2026-10-18")
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def read_markdown(path: Path) -> list[dict[str, object]]:
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")]
            for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip().startswith("|")]  # fmt: skip
    rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
    if len(rows) < 2:
        raise BookError("没有找到错题表格")
    header = rows[0]
    for need in ("日期", "学科", "知识点", "题目"):
        if need not in header:
            raise BookError(f"错题表缺少「{need}」列")
    items: list[dict[str, object]] = []
    for i, r in enumerate(rows[1:], start=1):
        if len(r) != len(header):
            raise BookError(f"第 {i} 行有 {len(r)} 列，表头有 {len(header)} 列")
        rec: dict[str, object] = dict.fromkeys(FIELDS, "")
        rec.update(dict(zip(header, r, strict=True)))
        rec["日期"] = parse_date(rec["日期"])
        rec["已掌握"] = ""
        items.append(rec)
    return items


def read_book(path: Path) -> list[dict[str, object]]:
    ws = load_workbook(path, data_only=True)["错题"]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(h) for h in rows[0]]
    items = []
    for r in rows[1:]:
        if not r or r[1] is None:
            continue
        rec = dict(zip(header, r, strict=False))
        rec["日期"] = parse_date(rec["日期"])
        items.append({k: ("" if v is None else v) for k, v in rec.items()})
    return items


def write_book(items: list[dict[str, object]], out: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "错题"
    header = ["序号", *FIELDS, *REVIEW_COLS, "已掌握"]
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = HEADER_FILL
    for i, rec in enumerate(sorted(items, key=lambda x: (str(x["日期"]), str(x["学科"]))), start=1):
        day = rec["日期"]
        assert isinstance(day, dt.date)
        reviews = [day + dt.timedelta(days=n) for n in INTERVALS]
        ws.append([i, *[rec.get(f, "") for f in FIELDS], *reviews, rec.get("已掌握", "")])
        for j in [2, *range(len(FIELDS) + 2, len(FIELDS) + 2 + len(INTERVALS))]:
            ws.cell(ws.max_row, j).number_format = "mm-dd" if j > 2 else "yyyy-mm-dd"
        for j in (5, 6, 7):
            ws.cell(ws.max_row, j).alignment = Alignment(wrap_text=True, vertical="top")
    widths = [6, 12, 8, 14, 36, 14, 14, 12, 12, *([8] * len(INTERVALS)), 8]
    for j, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(1, j).column_letter].width = w
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{ws.cell(1, len(header)).column_letter}{ws.max_row}"

    st = wb.create_sheet("统计")
    st.append(["学科", "知识点", "错题数", "已掌握"])
    pairs = Counter((str(r["学科"]), str(r["知识点"])) for r in items)
    mastered = Counter(
        (str(r["学科"]), str(r["知识点"]))
        for r in items
        if str(r.get("已掌握", "")).strip() in ("是", "Y", "y", "✓")
    )
    for (subject, point), n in pairs.most_common():
        st.append([subject, point, n, mastered[(subject, point)]])
    st.append([])
    st.append(["错因", "次数"])
    for cause, n in Counter(str(r["错因"]) or "未填写" for r in items).most_common():
        st.append([cause, n])
    for c in st[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = HEADER_FILL
    st.column_dimensions["A"].width = 12
    st.column_dimensions["B"].width = 20
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))


def cmd_build(src: Path, out: Path, merge: Path | None) -> int:
    items = read_book(merge) if merge else []
    seen = {(r["日期"], str(r["学科"]), str(r["题目"])) for r in items}
    added = 0
    for rec in read_markdown(src):
        key = (rec["日期"], str(rec["学科"]), str(rec["题目"]))
        if key not in seen:
            items.append(rec)
            seen.add(key)
            added += 1
    write_book(items, out)
    top = Counter(str(r["知识点"]) for r in items).most_common(3)
    print(f"已生成 {out}：共 {len(items)} 道错题（本次新增 {added} 道）")
    print("错得最多的知识点：" + "、".join(f"{k} {v} 道" for k, v in top))
    return 0


def cmd_due(book: Path, today: dt.date) -> int:
    items = read_book(book)
    due = []
    for r in items:
        if str(r.get("已掌握", "")).strip() in ("是", "Y", "y", "✓"):
            continue
        day = r["日期"]
        assert isinstance(day, dt.date)
        stages = [day + dt.timedelta(days=n) for n in INTERVALS]
        passed = [i for i, d in enumerate(stages) if d <= today]
        # 最近一轮复习日在今天或两天内（漏了一两天也补上）；五轮都过完的题看“统计”表
        if passed and stages[passed[-1]] >= today - dt.timedelta(days=2):
            due.append((r, passed[-1] + 1, stages[passed[-1]]))
    print(f"{today:%Y-%m-%d} 待复习 {len(due)} 道（按遗忘曲线第 1/2/4/7/15 天）")
    for r, stage, when in sorted(due, key=lambda x: (str(x[0]["学科"]), str(x[0]["知识点"]))):
        late = "" if when == today else f"（已过 {(today - when).days} 天）"
        print(f"- [{r['学科']}·{r['知识点']}] 第 {stage} 轮{late}：{str(r['题目'])[:40]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("input")
    b.add_argument("-o", "--output", required=True)
    b.add_argument("--merge")
    d = sub.add_parser("due")
    d.add_argument("book")
    d.add_argument("--today")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "build":
            return cmd_build(
                Path(args.input), Path(args.output), Path(args.merge) if args.merge else None
            )
        today = parse_date(args.today) if args.today else dt.date.today()
        return cmd_due(Path(args.book), today)
    except (OSError, BookError, KeyError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
