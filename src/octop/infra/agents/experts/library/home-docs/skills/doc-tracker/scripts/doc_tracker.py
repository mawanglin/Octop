#!/usr/bin/env python3
"""家庭证件与重要文件到期提醒：Markdown 清单 → Excel 台账（按到期时间排序、标色），列出即将到期的项目，导出手机日历提醒。

Usage:
    python scripts/doc_tracker.py build 家庭证件.md -o 家庭证件台账.xlsx [--today 2026-10-18]
    python scripts/doc_tracker.py due 家庭证件台账.xlsx [--days 30] [--today 2026-10-18]
    python scripts/doc_tracker.py ics 家庭证件台账.xlsx -o 到期提醒.ics

清单 Markdown 表格：
    | 名称 | 类型 | 持有人 | 编号 | 到期日 | 提前提醒天数 | 存放位置 | 备注 |
"类型"如 证件 / 保险 / 合同 / 保修 / 车辆 / 会员 / 其他；"到期日"写 2027-03-15，长期有效写 长期；
"提前提醒天数"不写时按类型默认（护照、身份证 180 天，保险、车辆 30 天，其他 30 天）；
"编号"只需写后 4 位：写了完整身份证号、护照号等长编号时，台账里会自动只保留后 4 位。
Exit codes: 0 ok, 1 输入错误, 2 缺少 openpyxl。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import uuid
from pathlib import Path

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill
except ImportError:  # pragma: no cover - environment check
    print("缺少依赖 openpyxl：请运行 `pip install openpyxl`", file=sys.stderr)
    sys.exit(2)

FIELDS = ["名称", "类型", "持有人", "编号", "到期日", "提前提醒天数", "存放位置", "备注"]
COLUMNS = [*FIELDS, "剩余天数", "状态"]
DEFAULT_LEAD = {
    "护照": 180,
    "身份证": 180,
    "港澳": 90,
    "签证": 90,
    "驾驶证": 90,
    "保险": 30,
    "车辆": 30,
    "合同": 60,
}
FILLS = {"已过期": "FECACA", "即将到期": "FED7AA", "注意": "FEF3C7", "正常": None, "长期": None}
LONG_TERM = ("长期", "永久", "无", "-")


class TrackError(ValueError):
    pass


def parse_date(text: object) -> dt.date | None:
    if isinstance(text, dt.datetime):
        return text.date()
    if isinstance(text, dt.date):
        return text
    s = str(text or "").strip()
    if not s or s in LONG_TERM:
        return None
    m = re.fullmatch(r"(\d{4})\s*[-./年]\s*(\d{1,2})\s*[-./月]\s*(\d{1,2})\s*日?", s)
    if not m:
        raise TrackError(f"到期日「{s}」应写成 2027-03-15 或 长期")
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def mask(no: str) -> str:
    digits = re.sub(r"\s", "", no)
    return f"****{digits[-4:]}" if len(digits) > 6 else digits


def lead_days(name: str, kind: str, given: str) -> int:
    if str(given).strip():
        try:
            return int(str(given).strip())
        except ValueError:
            raise TrackError(f"「{name}」的提前提醒天数「{given}」不是整数") from None
    for key, days in DEFAULT_LEAD.items():
        if key in name or key in kind:
            return days
    return 30


def status(expiry: dt.date | None, lead: int, today: dt.date) -> tuple[int | None, str]:
    if expiry is None:
        return None, "长期"
    left = (expiry - today).days
    if left < 0:
        return left, "已过期"
    if left <= lead:
        return left, "即将到期"
    if left <= lead * 2:
        return left, "注意"
    return left, "正常"


def read_markdown(path: Path) -> list[dict[str, object]]:
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")]
            for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip().startswith("|")]  # fmt: skip
    rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
    if len(rows) < 2 or "名称" not in rows[0] or "到期日" not in rows[0]:
        raise TrackError("清单需要一张表格，表头至少包含「名称」「到期日」")
    header = rows[0]
    out = []
    for r in rows[1:]:
        if len(r) != len(header):
            raise TrackError(f"「{' | '.join(r)}」的列数和表头不一致")
        rec: dict[str, object] = dict.fromkeys(FIELDS, "")
        rec.update(dict(zip(header, r, strict=True)))
        out.append(rec)
    return out


def read_book(path: Path) -> list[dict[str, object]]:
    ws = load_workbook(path)["台账"]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(h) for h in rows[0]]
    return [
        {k: ("" if v is None else v) for k, v in zip(header, r, strict=False)}
        for r in rows[1:]
        if r and r[0]
    ]


def evaluate(items: list[dict[str, object]], today: dt.date) -> list[dict[str, object]]:
    for rec in items:
        name, kind = str(rec["名称"]), str(rec["类型"])
        rec["到期日"] = parse_date(rec["到期日"]) or "长期"
        lead = lead_days(name, kind, str(rec.get("提前提醒天数", "")))
        rec["提前提醒天数"] = lead
        rec["编号"] = mask(str(rec.get("编号", "")))
        expiry = rec["到期日"] if isinstance(rec["到期日"], dt.date) else None
        rec["剩余天数"], rec["状态"] = status(expiry, lead, today)
    return sorted(
        items,
        key=lambda r: (r["剩余天数"] is None, r["剩余天数"] if r["剩余天数"] is not None else 0),
    )


def write_book(items: list[dict[str, object]], out: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "台账"
    ws.append(COLUMNS)
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="0369A1")
    for rec in items:
        ws.append([rec.get(c, "") for c in COLUMNS])
        fill = FILLS.get(str(rec["状态"]))
        if fill:
            for c in ws[ws.max_row]:
                c.fill = PatternFill("solid", fgColor=fill)
        ws.cell(ws.max_row, 5).number_format = "yyyy-mm-dd"
    for col, w in zip("ABCDEFGHIJ", (22, 8, 8, 10, 12, 8, 16, 24, 8, 8), strict=True):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:J{ws.max_row}"
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))


def summary(items: list[dict[str, object]], days: int | None) -> None:
    def show(rec: dict[str, object]) -> str:
        who = f"（{rec['持有人']}）" if rec.get("持有人") else ""
        left = rec["剩余天数"]
        when = f"已过期 {-left} 天" if isinstance(left, int) and left < 0 else f"还剩 {left} 天"
        where = f"，存放：{rec['存放位置']}" if rec.get("存放位置") else ""
        return f"- {rec['名称']}{who}：{rec['到期日']}，{when}{where}"

    expired = [r for r in items if r["状态"] == "已过期"]
    soon = [
        r
        for r in items
        if r["状态"] == "即将到期"
        or (days is not None and isinstance(r["剩余天数"], int) and 0 <= r["剩余天数"] <= days)
    ]
    print(
        f"共 {len(items)} 项：已过期 {len(expired)}，即将到期 {len(soon)}，长期有效 {sum(1 for r in items if r['状态'] == '长期')}"
    )
    for title, group in (("已过期", expired), ("即将到期", soon)):
        if group:
            print(f"## {title}")
            for r in group:
                print(show(r))


def write_ics(items: list[dict[str, object]], out: Path, today: dt.date) -> int:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Octop//home-docs//CN",
        "CALSCALE:GREGORIAN",
    ]
    n = 0
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    for rec in items:
        expiry = rec["到期日"]
        if not isinstance(expiry, dt.date) or expiry < today:
            continue  # long-term and already-expired items get no calendar entry
        lead = int(rec["提前提醒天数"])
        remind = max(expiry - dt.timedelta(days=lead), today)
        who = f"（{rec['持有人']}）" if rec.get("持有人") else ""
        name, where = rec["名称"], rec.get("存放位置") or "未填写"
        uid = uuid.uuid5(
            uuid.NAMESPACE_URL, f"octop-home-docs/{name}/{rec.get('持有人', '')}/{expiry}"
        )
        lines += [
            "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{remind:%Y%m%d}", f"DTEND;VALUE=DATE:{remind + dt.timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_esc(f'{name}{who} {expiry} 到期')}",
            f"DESCRIPTION:{_esc(f'到期日 {expiry}；存放：{where}')}",
            "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:到期提醒", "TRIGGER:PT9H", "END:VALARM",
            "END:VEVENT",
        ]  # fmt: skip
        n += 1
    lines.append("END:VCALENDAR")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return n


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("input")
    b.add_argument("-o", "--output", required=True)
    b.add_argument("--today")
    d = sub.add_parser("due")
    d.add_argument("book")
    d.add_argument("--days", type=int)
    d.add_argument("--today")
    i = sub.add_parser("ics")
    i.add_argument("book")
    i.add_argument("-o", "--output", required=True)
    i.add_argument("--today")
    args = parser.parse_args(argv)
    try:
        today = (
            dt.date.fromisoformat(args.today) if getattr(args, "today", None) else dt.date.today()
        )
        if args.cmd == "build":
            items = evaluate(read_markdown(Path(args.input)), today)
            write_book(items, Path(args.output))
            print(f"已生成 {args.output}")
            summary(items, None)
            return 0
        items = evaluate(read_book(Path(args.book)), today)
        if args.cmd == "due":
            summary(items, args.days)
            return 0
        n = write_ics(items, Path(args.output), today)
        print(
            f"已生成 {args.output}：{n} 个提醒（到期日前按“提前提醒天数”提醒，已过期和长期有效的不导出），可导入手机或电脑日历"
        )
        return 0
    except (OSError, TrackError, ValueError, KeyError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
