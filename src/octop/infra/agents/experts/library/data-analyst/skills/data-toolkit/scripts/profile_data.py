#!/usr/bin/env python3
"""数据画像：快速了解一张表——字段类型、缺失、唯一值、数值分布、异常值、Top 值。

Usage:
    python scripts/profile_data.py data.xlsx [--sheet 名称] [--header-row 1]
    python scripts/profile_data.py data.csv [--json]

只依赖 openpyxl 和标准库（不需要 pandas）。大表只读取前 --max-rows 行（默认 200000）。
Exit codes: 0 ok, 1 读取失败, 2 缺少 openpyxl。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover - environment check
    print("缺少依赖 openpyxl：请运行 `pip install openpyxl`", file=sys.stderr)
    sys.exit(2)

DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y-%m",
    "%Y/%m",
    "%Y年%m月%d日",
    "%Y年%m月",
    "%Y-%m-%d %H:%M:%S",
)


def read_table(
    path: Path, sheet: str | None, header_row: int, max_rows: int
) -> tuple[list[str], list[list[Any]]]:
    if path.suffix.lower() in (".csv", ".txt"):
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "gb18030"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("无法识别 CSV 编码（试过 UTF-8 和 GB18030）")
        rows = list(csv.reader(text.splitlines()))
    else:
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb[sheet] if sheet else wb.worksheets[0]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
    rows = rows[header_row - 1 :]
    if not rows:
        raise ValueError("表格为空")
    header = [
        str(h).strip() if h not in (None, "") else f"列{i + 1}" for i, h in enumerate(rows[0])
    ]
    body = [r for r in rows[1 : max_rows + 1] if any(v not in (None, "") for v in r)]
    width = len(header)
    body = [(list(r) + [None] * width)[:width] for r in body]
    return header, body


def to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("，", "")
        pct = text.endswith("%")
        text = text.rstrip("%").lstrip("¥￥$")
        try:
            n = float(text)
        except ValueError:
            return None
        return n / 100 if pct else n
    return None


def to_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for fmt in DATE_FORMATS:
            try:
                return dt.datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    return None


def profile_column(name: str, values: list[Any]) -> dict[str, Any]:
    present = [v for v in values if v not in (None, "")]
    total = len(values)
    info: dict[str, Any] = {
        "字段": name,
        "非空": len(present),
        "缺失": total - len(present),
        "缺失率": round((total - len(present)) / total, 4) if total else 0,
        "唯一值": len({str(v) for v in present}),
    }
    if not present:
        info["类型"] = "空"
        return info
    numbers = [n for n in (to_number(v) for v in present) if n is not None]
    dates = [d for d in (to_date(v) for v in present) if d is not None]
    if len(numbers) >= 0.9 * len(present):
        info["类型"] = "数值"
        numbers.sort()
        q1, med, q3 = (
            statistics.quantiles(numbers, n=4)
            if len(numbers) >= 4
            else (numbers[0], statistics.median(numbers), numbers[-1])
        )
        iqr = q3 - q1
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outliers = [n for n in numbers if n < low or n > high]
        info.update(
            {
                "最小": numbers[0],
                "最大": numbers[-1],
                "合计": round(sum(numbers), 4),
                "平均": round(statistics.fmean(numbers), 4),
                "中位数": round(med, 4),
                "异常值个数": len(outliers),
                "异常值示例": [round(x, 4) for x in outliers[:5]],
                "非数字值": len(present) - len(numbers),
                "负数个数": sum(1 for n in numbers if n < 0),
            }
        )
    elif len(dates) >= 0.9 * len(present):
        info["类型"] = "日期"
        info.update({"最早": dates and min(dates).isoformat(), "最晚": dates and max(dates).isoformat(),
                     "无法识别": len(present) - len(dates)})  # fmt: skip
    else:
        info["类型"] = "文本"
        counts = Counter(str(v).strip() for v in present)
        info["Top值"] = counts.most_common(5)
        raw = {str(v) for v in present}
        variants = {str(v).strip().lower().replace(" ", "").replace("\u3000", "") for v in present}
        if len(variants) < len(raw):
            info["提示"] = "存在大小写/空格不同但内容相同的值，汇总前需要统一"
    integer_like = info["类型"] == "数值" and all(float(n).is_integer() for n in numbers)
    if (
        info["唯一值"] == len(present)
        and len(present) > 1
        and (info["类型"] == "文本" or integer_like)
    ):
        info["可能是"] = "唯一标识（ID/编号）"
    return info


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("input")
    parser.add_argument("--sheet")
    parser.add_argument("--header-row", type=int, default=1)
    parser.add_argument("--max-rows", type=int, default=200_000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        header, body = read_table(Path(args.input), args.sheet, args.header_row, args.max_rows)
    except (OSError, ValueError, KeyError) as exc:
        print(f"读取失败：{exc}", file=sys.stderr)
        return 1
    columns = [profile_column(name, [r[i] for r in body]) for i, name in enumerate(header)]
    duplicates = len(body) - len({tuple(map(str, r)) for r in body})
    report = {
        "文件": args.input,
        "行数": len(body),
        "列数": len(header),
        "完全重复行": duplicates,
        "字段": columns,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"# 数据画像：{Path(args.input).name}\n")
    print(f"- 行数 {len(body)}，列数 {len(header)}，完全重复行 {duplicates}\n")
    print("| 字段 | 类型 | 缺失率 | 唯一值 | 概况 |")
    print("|------|------|--------|--------|------|")
    for c in columns:
        if c["类型"] == "数值":
            brief = f"{c['最小']:g} ~ {c['最大']:g}，均值 {c['平均']:g}，中位数 {c['中位数']:g}"
            if c["异常值个数"]:
                brief += f"，异常值 {c['异常值个数']} 个"
            if c["非数字值"]:
                brief += f"，非数字 {c['非数字值']} 个"
        elif c["类型"] == "日期":
            brief = f"{c['最早']} ~ {c['最晚']}"
        elif c["类型"] == "文本":
            brief = "Top：" + "、".join(f"{k}({v})" for k, v in c["Top值"][:3])
        else:
            brief = "全部为空"
        if c.get("可能是"):
            brief += f"；{c['可能是']}"
        print(f"| {c['字段']} | {c['类型']} | {c['缺失率']:.1%} | {c['唯一值']} | {brief} |")
    notes = [f"「{c['字段']}」{c['提示']}" for c in columns if c.get("提示")]
    notes += [
        f"「{c['字段']}」缺失率 {c['缺失率']:.0%}，分析前确认缺失原因"
        for c in columns
        if c["缺失率"] > 0.2 and c["类型"] != "空"
    ]
    if duplicates:
        notes.append(f"有 {duplicates} 行完全重复，确认是否需要去重")
    if notes:
        print("\n## 数据质量提示")
        for n in notes:
            print(f"- {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
