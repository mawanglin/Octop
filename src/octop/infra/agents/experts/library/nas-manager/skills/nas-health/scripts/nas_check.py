#!/usr/bin/env python3
"""NAS 体检：解读硬盘 SMART 报告并分级，统计容量并按历史记录预测多久会满。只读，不改任何系统设置。

Usage:
    python scripts/nas_check.py smart sda.txt sdb.json ...        （smartctl -a 或 smartctl -a -j 的输出）
    python scripts/nas_check.py smart --run                        （本机调用 smartctl，通常需要 root）
    python scripts/nas_check.py capacity /vol1 /vol2 [--history 容量记录.csv] [--record]

smart：机械盘看重映射扇区(5)、待映射扇区(197)、离线不可修复(198)、UDMA CRC 错误(199)、温度、通电时间；
       NVMe 看已用寿命(Percentage Used)、可用备用块、介质错误、严重警告。分级：正常 / 关注 / 警告 / 危险。
       序列号只显示后 4 位。
capacity：当前总量 / 已用 / 可用；--record 把今天的读数追加到历史 CSV；历史至少跨 7 天时按线性增长预测到 90% 和 100% 的天数。
Exit codes: 0 全部正常, 3 有关注/警告/危险项, 1 输入错误。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LEVELS = ["正常", "关注", "警告", "危险"]


class NasError(ValueError):
    pass


@dataclass
class Disk:
    name: str
    model: str = ""
    serial: str = ""
    capacity: str = ""
    kind: str = "ATA"
    passed: bool | None = None
    temp: int | None = None
    hours: int | None = None
    attrs: dict[int, int] = field(default_factory=dict)
    nvme: dict[str, int] = field(default_factory=dict)
    level: str = "正常"
    notes: list[str] = field(default_factory=list)


def _int(text: str) -> int | None:
    m = re.search(r"\d[\d,]*", text)
    return int(m.group(0).replace(",", "")) if m else None


def parse_text(name: str, text: str) -> Disk:
    d = Disk(name)
    for line in text.splitlines():
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if key in ("Device Model", "Model Number", "Product"):
            d.model = val
        elif key == "Serial Number":
            d.serial = val
        elif (
            key in ("User Capacity", "Total NVM Capacity", "Namespace 1 Size/Capacity")
            and not d.capacity
        ):
            m = re.search(r"\[([^\]]+)\]", val)
            d.capacity = m.group(1) if m else val
        elif "overall-health" in key or key == "SMART Health Status":
            d.passed = "PASSED" in val or val == "OK"
        elif key == "Temperature" and d.temp is None:
            d.temp = _int(val)
        elif key == "Power On Hours":
            d.hours = _int(val)
        elif key in ("Percentage Used", "Available Spare", "Available Spare Threshold", "Media and Data Integrity Errors",
                     "Critical Warning", "Unsafe Shutdowns"):  # fmt: skip
            d.kind = "NVMe"
            raw = val.split()[0] if val else "0"
            d.nvme[key] = int(raw, 16) if raw.startswith("0x") else (_int(raw) or 0)
    for m in re.finditer(
        r"^\s*(\d{1,3})\s+\S+\s+0x[0-9a-fA-F]{4}\s+\d+\s+\d+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+)",
        text,
        re.M,
    ):
        d.attrs[int(m.group(1))] = int(m.group(2))
    if d.hours is None and 9 in d.attrs:
        d.hours = d.attrs[9]
    if d.temp is None and (194 in d.attrs or 190 in d.attrs):
        d.temp = d.attrs.get(194, d.attrs.get(190))
    return d


def parse_json(name: str, data: dict[str, Any]) -> Disk:
    d = Disk(name, model=data.get("model_name", ""), serial=data.get("serial_number", ""))
    cap = data.get("user_capacity", {}).get("bytes")
    if cap:
        d.capacity = f"{cap / 1e12:.2f} TB" if cap >= 1e12 else f"{cap / 1e9:.0f} GB"
    if "smart_status" in data:
        d.passed = bool(data["smart_status"].get("passed"))
    d.temp = data.get("temperature", {}).get("current")
    d.hours = data.get("power_on_time", {}).get("hours")
    for row in data.get("ata_smart_attributes", {}).get("table", []):
        d.attrs[int(row["id"])] = int(row.get("raw", {}).get("value", 0))
    log = data.get("nvme_smart_health_information_log")
    if log:
        d.kind = "NVMe"
        d.nvme = {"Percentage Used": log.get("percentage_used", 0), "Available Spare": log.get("available_spare", 100),
                  "Available Spare Threshold": log.get("available_spare_threshold", 10),
                  "Media and Data Integrity Errors": log.get("media_errors", 0),
                  "Critical Warning": log.get("critical_warning", 0), "Unsafe Shutdowns": log.get("unsafe_shutdowns", 0)}  # fmt: skip
    return d


def grade(d: Disk) -> Disk:
    def bump(level: str, note: str) -> None:
        if LEVELS.index(level) > LEVELS.index(d.level):
            d.level = level
        d.notes.append(note)

    if d.passed is False:
        bump("危险", "SMART 整体自检未通过（FAILED），请立即备份数据并更换硬盘")
    a = d.attrs
    if a.get(5, 0) > 0:
        bump(
            "警告" if a[5] >= 100 else "关注",
            f"重映射扇区 {a[5]} 个：硬盘已出现坏道，数值持续增长时尽快更换",
        )
    if a.get(197, 0) > 0:
        bump("警告", f"待映射扇区 {a[197]} 个：有读不出的扇区，先备份再做一次完整扫描")
    if a.get(198, 0) > 0:
        bump("警告", f"离线不可修复扇区 {a[198]} 个：建议尽快更换")
    if a.get(199, 0) > 0:
        bump(
            "关注",
            f"UDMA CRC 错误 {a[199]} 次：多为数据线或背板接触问题，重新插拔或更换数据线后观察是否继续增长",
        )
    if d.temp is not None:
        if d.temp >= 60:
            bump("警告", f"温度 {d.temp}°C 过高：检查风扇、风道和机箱散热")
        elif d.temp >= 50:
            bump("关注", f"温度 {d.temp}°C 偏高：机械盘建议长期低于 45°C")
    if d.hours is not None and d.kind == "ATA" and d.hours >= 43800:
        bump(
            "关注",
            f"已通电 {d.hours} 小时（约 {d.hours / 8760:.1f} 年）：进入老化期，确认有备份并规划更换",
        )
    n = d.nvme
    if n:
        used = n.get("Percentage Used", 0)
        if used >= 100:
            bump("警告", f"已用寿命 {used}%：超过厂商标称写入寿命，尽快更换")
        elif used >= 80:
            bump("关注", f"已用寿命 {used}%：规划更换")
        if n.get("Available Spare", 100) <= n.get("Available Spare Threshold", 10):
            bump("危险", f"可用备用块 {n.get('Available Spare')}% 已低于阈值：立即备份并更换")
        if n.get("Media and Data Integrity Errors", 0) > 0:
            bump("警告", f"介质错误 {n['Media and Data Integrity Errors']} 次")
        if n.get("Critical Warning", 0):
            bump("警告", f"严重警告标志 0x{n['Critical Warning']:02x}")
    if d.passed is None and not d.attrs and not d.nvme:
        bump("关注", "没有读到 SMART 数据：确认 smartctl 有权限（root），USB 硬盘盒可能需要 -d sat")
    return d


def mask(serial: str) -> str:
    return ("****" + serial[-4:]) if len(serial) > 4 else serial


def load_disks(files: list[str], run: bool) -> list[Disk]:
    disks: list[Disk] = []
    if run:
        exe = shutil.which("smartctl")
        if not exe:
            raise NasError(
                "没有找到 smartctl：请先安装 smartmontools，或把 smartctl -a 的输出保存成文件再分析"
            )
        scan = subprocess.run([exe, "--scan", "-j"], capture_output=True, text=True, timeout=60)
        devices = [d["name"] for d in json.loads(scan.stdout or "{}").get("devices", [])]
        if not devices:
            raise NasError("smartctl --scan 没有发现硬盘（可能需要 root 权限）")
        for dev in devices:
            out = subprocess.run(
                [exe, "-a", "-j", dev], capture_output=True, text=True, timeout=120
            )
            disks.append(parse_json(dev, json.loads(out.stdout or "{}")))
    for f in files:
        text = Path(f).read_text(encoding="utf-8", errors="replace")
        name = Path(f).stem
        if text.lstrip().startswith("{"):
            disks.append(parse_json(name, json.loads(text)))
        else:
            disks.append(parse_text(name, text))
    if not disks:
        raise NasError("请提供 smartctl 输出文件，或加 --run 在本机读取")
    return [grade(d) for d in disks]


def cmd_smart(files: list[str], run: bool, as_json: bool) -> int:
    disks = load_disks(files, run)
    if as_json:
        print(
            json.dumps(
                [{**d.__dict__, "serial": mask(d.serial)} for d in disks],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(
            "| 硬盘 | 型号 | 容量 | 类型 | 温度 | 通电时间 | 状态 |\n|------|------|------|------|------|----------|------|"
        )
        for d in disks:
            hours = f"{d.hours} 小时" if d.hours is not None else "-"
            temp = f"{d.temp}°C" if d.temp is not None else "-"
            print(
                f"| {d.name} | {d.model or '-'}（{mask(d.serial)}） | {d.capacity or '-'} | {d.kind} | {temp} | {hours} | {d.level} |"
            )
        for d in disks:
            if d.notes:
                print(f"\n{d.name}（{d.level}）：")
                for n in d.notes:
                    print(f"- {n}")
        worst = max(disks, key=lambda d: LEVELS.index(d.level)).level
        print(
            f"\n结论：{len(disks)} 块硬盘，最差状态「{worst}」。SMART 只能提示风险，不能保证硬盘不坏，重要数据请保持备份。"
        )
    return 0 if all(d.level == "正常" for d in disks) else 3


HIST_HEADER = ["日期", "路径", "总量字节", "已用字节"]


def read_history(path: Path) -> list[tuple[dt.date, str, int, int]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        try:
            out.append(
                (
                    dt.date.fromisoformat(r["日期"]),
                    r["路径"],
                    int(r["总量字节"]),
                    int(r["已用字节"]),
                )
            )
        except (KeyError, ValueError):
            raise NasError(f"{path} 格式不对，表头应为：{','.join(HIST_HEADER)}") from None
    return out


def forecast(
    points: list[tuple[dt.date, int]], total: int
) -> tuple[float, int | None, int | None] | None:
    """Least-squares growth (bytes/day) and days until 90% / 100%; None when history is too short."""
    if len(points) < 2 or (points[-1][0] - points[0][0]).days < 7:
        return None
    xs = [(d - points[0][0]).days for d, _ in points]
    ys = [u for _, u in points]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    var = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / var if var else 0.0
    if slope <= 0:
        return slope, None, None
    now = ys[-1]
    d90 = max(0, int((total * 0.9 - now) / slope)) if now < total * 0.9 else 0
    d100 = max(0, int((total - now) / slope))
    return slope, d90, d100


def cmd_capacity(paths: list[str], history: Path | None, record: bool, today: dt.date) -> int:
    rows = read_history(history) if history else []
    warn = False
    new: list[list[str]] = []
    print("| 路径 | 总量 | 已用 | 可用 | 使用率 |\n|------|------|------|------|--------|")
    current: dict[str, tuple[int, int]] = {}
    for p in paths:
        try:
            usage = shutil.disk_usage(p)
        except OSError:
            raise NasError(f"无法读取 {p} 的容量（路径不存在或没有权限）") from None
        current[p] = (usage.total, usage.used)
        pct = usage.used / usage.total if usage.total else 0
        warn = warn or pct >= 0.8
        print(
            f"| {p} | {_h(usage.total)} | {_h(usage.used)} | {_h(usage.free)} | {pct:.0%}{' ⚠' if pct >= 0.8 else ''} |"
        )
        new.append([today.isoformat(), p, str(usage.total), str(usage.used)])
    for p, (total, used) in current.items():
        pts = sorted(
            {(d, u) for d, path, _t, u in rows if path == p and d < today} | {(today, used)}
        )
        fc = forecast(pts, total)
        if fc is None:
            print(f"- {p}：历史记录不足 7 天，暂时无法预测（每周 --record 一次即可）")
        elif fc[1] is None:
            print(f"- {p}：近期用量没有增长")
        else:
            slope, d90, d100 = fc
            print(f"- {p}：平均每天增长 {_h(slope)}，约 {d90} 天后到 90%，约 {d100} 天后写满")
            warn = warn or (d90 is not None and d90 <= 90)
    if record and history:
        exists = history.exists()
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("a", encoding="utf-8-sig" if not exists else "utf-8", newline="") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(HIST_HEADER)
            w.writerows(
                r for r in new if (today, r[1]) not in {(d, path) for d, path, _t, _u in rows}
            )
        print(f"已记录到 {history}")
    if warn:
        print(
            "建议：使用率超过 80% 或 90 天内会到 90% 时，先清理回收站、重复文件和下载目录，再规划扩容。"
        )
    return 3 if warn else 0


def _h(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024 or unit == "PB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} PB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("smart")
    s.add_argument("files", nargs="*")
    s.add_argument("--run", action="store_true")
    s.add_argument("--json", action="store_true")
    c = sub.add_parser("capacity")
    c.add_argument("paths", nargs="+")
    c.add_argument("--history")
    c.add_argument("--record", action="store_true")
    c.add_argument("--today")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "smart":
            return cmd_smart(args.files, args.run, args.json)
        today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
        return cmd_capacity(
            args.paths, Path(args.history) if args.history else None, args.record, today
        )
    except (OSError, NasError, ValueError, json.JSONDecodeError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
