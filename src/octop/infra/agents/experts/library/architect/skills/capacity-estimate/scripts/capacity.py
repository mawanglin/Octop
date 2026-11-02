#!/usr/bin/env python3
"""容量和可用性估算：由用户量推算 QPS、带宽、存储、节点数和缓存，换算可用性（几个九）对应的停机时间，计算串联和并联后的整体可用性。

Usage:
    python scripts/capacity.py estimate --dau 100000 [--requests-per-user 20] [--peak-factor 3] [--read-ratio 0.9]
                               [--payload-kb 5] [--writes-per-user N] [--record-kb 2] [--retention-days 365]
                               [--replicas 3] [--qps-per-node 500] [--headroom 0.3] [--hot-ratio 0.2]
                               [--growth 0.5] [--json]
    python scripts/capacity.py sla [99.9 99.99 ...]
    python scripts/capacity.py compose --serial 99.9,99.95 [--parallel 99.0,99.0]

这是量级估算，不是容量规划结论：每个假设都会列在结果里，换成你自己的数再算；真实容量要靠压测。
Exit codes: 0 正常, 1 参数错误。
"""

from __future__ import annotations

import argparse
import json
import math
import sys

DAY = 86400


def positive(name: str, value: float, allow_zero: bool = False) -> None:
    if value < 0 or (value == 0 and not allow_zero):
        raise SystemExit(f"--{name} 必须{'不小于' if allow_zero else '大于'} 0")


def human_bytes_gb(gb: float) -> str:
    if gb >= 1000:
        return f"{gb / 1000:,.1f} TB"
    if gb >= 1:
        return f"{gb:,.1f} GB"
    return f"{gb * 1000:,.1f} MB"


def estimate(a: argparse.Namespace) -> dict[str, object]:
    for name in (
        "dau",
        "requests_per_user",
        "peak_factor",
        "payload_kb",
        "record_kb",
        "retention_days",
        "replicas",
        "qps_per_node",
    ):
        positive(name.replace("_", "-"), getattr(a, name))
    if not 0 <= a.read_ratio <= 1:
        raise SystemExit("--read-ratio 要在 0 到 1 之间")
    if not 0 <= a.headroom < 1:
        raise SystemExit("--headroom 要在 0（含）到 1（不含）之间")
    if not 0 <= a.hot_ratio <= 1:
        raise SystemExit("--hot-ratio 要在 0 到 1 之间")
    positive("growth", a.growth, allow_zero=True)

    writes = (
        a.writes_per_user
        if a.writes_per_user is not None
        else a.requests_per_user * (1 - a.read_ratio)
    )
    positive("writes-per-user", writes, allow_zero=True)

    def calc(dau: float) -> dict[str, float]:
        avg = dau * a.requests_per_user / DAY
        peak = avg * a.peak_factor
        read_peak = peak * a.read_ratio
        daily_gb = dau * writes * a.record_kb / 1e6
        total_gb = daily_gb * a.retention_days
        usable = a.qps_per_node * (1 - a.headroom)
        nodes = max(math.ceil(peak / usable), 1)
        return {
            "日活": dau,
            "平均 QPS": avg,
            "峰值 QPS": peak,
            "读峰值 QPS": read_peak,
            "写峰值 QPS": peak - read_peak,
            "出口带宽峰值 Mbps": read_peak * a.payload_kb * 8 / 1000,
            "每天新增数据": daily_gb,
            "保留期内数据（单副本）": total_gb,
            "保留期内数据（含副本）": total_gb * a.replicas,
            "应用节点数（满足峰值）": nodes,
            "应用节点数（含 N+1 冗余）": max(nodes + 1, 2),
            "热数据缓存": daily_gb * a.hot_ratio,
        }

    res: dict[str, object] = {
        "假设": {
            "日活 DAU": a.dau,
            "人均每天请求数": a.requests_per_user,
            "峰值系数（峰值 QPS ÷ 平均 QPS）": a.peak_factor,
            "读请求占比": a.read_ratio,
            "平均响应大小 KB": a.payload_kb,
            "人均每天写入条数": round(writes, 2),
            "单条记录大小 KB": a.record_kb,
            "数据保留天数": a.retention_days,
            "存储副本数": a.replicas,
            "单节点能扛的 QPS": a.qps_per_node,
            "预留余量": a.headroom,
            "热数据占每天新增的比例": a.hot_ratio,
        },
        "结果": calc(a.dau),
    }
    if a.growth:
        res[f"一年后（日活增长 {a.growth:.0%}）"] = calc(a.dau * (1 + a.growth))
    return res


def fmt_value(key: str, v: float) -> str:
    if "数据" in key or "缓存" in key:
        return human_bytes_gb(v)
    if "QPS" in key or "Mbps" in key:
        return f"{v:,.1f}"
    return f"{v:,.0f}"


def render_estimate(res: dict[str, object]) -> str:
    out = ["# 容量估算", "", "## 假设（换成你自己的数再算）", ""]
    for k, v in res["假设"].items():  # type: ignore[attr-defined]
        out.append(f"- {k}：{int(v) if isinstance(v, float) and v == int(v) else v}")
    for title in [k for k in res if k != "假设"]:
        out += ["", f"## {title}", "", "| 项目 | 数值 |", "|---|---|"]
        for k, v in res[title].items():  # type: ignore[attr-defined]
            out.append(f"| {k} | {fmt_value(k, v)} |")
    out += [
        "",
        "## 怎么算的",
        "",
        "- 平均 QPS = 日活 × 人均请求数 ÷ 86400；峰值 QPS = 平均 QPS × 峰值系数",
        "- 出口带宽 = 读峰值 QPS × 平均响应大小 × 8 ÷ 1000（Mbps，没算协议开销和压缩）",
        "- 每天新增数据 = 日活 × 人均写入 × 单条大小；总量 = 每天新增 × 保留天数 × 副本数（没算索引和备份，通常再加 30%～100%）",
        "- 节点数 = 峰值 QPS ÷（单节点 QPS × (1 − 余量)）向上取整；冗余至少再加 1 台，保证坏一台不影响峰值",
        "",
        "## 注意",
        "",
        "- 这是量级估算：峰值系数、单节点 QPS、响应大小都要用真实数据校准，单节点 QPS 要靠压测，不要照抄。",
        "- 数据库、缓存、消息队列的容量和并发要单独评估；这里只算了应用层和存储总量。",
        "- 活动、促销、整点推送会让峰值系数远高于平时，按最大的场景估。",
    ]
    return "\n".join(out)


def downtime(avail_pct: float) -> dict[str, str]:
    miss = 1 - avail_pct / 100

    def fmt(sec: float) -> str:
        if sec >= 3600:
            return f"{sec / 3600:.1f} 小时"
        if sec >= 60:
            return f"{sec / 60:.1f} 分钟"
        return f"{sec:.1f} 秒"

    return {
        "每天": fmt(miss * DAY),
        "每月（30 天）": fmt(miss * 30 * DAY),
        "每年": fmt(miss * 365 * DAY),
    }


def parse_avail(text: str) -> list[float]:
    try:
        vals = [float(x) for x in text.replace("，", ",").split(",") if x.strip()]
    except ValueError:
        raise SystemExit(f"可用性要写成百分数，如 99.9，收到：{text}") from None
    if not vals or any(not 0 < v <= 100 for v in vals):
        raise SystemExit("可用性要在 0 到 100 之间（百分数）")
    return vals


def cmd_sla(args: argparse.Namespace) -> int:
    targets = (
        [float(x) for x in args.targets] if args.targets else [99.0, 99.9, 99.95, 99.99, 99.999]
    )
    if any(not 0 < t < 100 for t in targets):
        print("可用性要大于 0、小于 100（百分数）", file=sys.stderr)
        return 1
    print("| 可用性 | 每天允许停机 | 每月（30 天） | 每年 |\n|---|---|---|---|")
    for t in targets:
        d = downtime(t)
        print(f"| {t}% | {d['每天']} | {d['每月（30 天）']} | {d['每年']} |")
    print(
        "\n提示：要先定义“可用”——哪些接口、哪个错误率算不可用——再谈几个九；计划内维护算不算也要写进 SLA。"
    )
    return 0


def cmd_compose(args: argparse.Namespace) -> int:
    if not args.serial and not args.parallel:
        print("至少给 --serial 或 --parallel", file=sys.stderr)
        return 1
    parts = []
    total = 1.0
    if args.serial:
        s = parse_avail(args.serial)
        ser = math.prod(v / 100 for v in s)
        parts.append(
            f"串联 {len(s)} 个部件（缺一不可）：{' × '.join(f'{v}%' for v in s)} = {ser * 100:.4f}%"
        )
        total *= ser
    if args.parallel:
        p = parse_avail(args.parallel)
        par = 1 - math.prod(1 - v / 100 for v in p)
        parts.append(
            f"并联 {len(p)} 个冗余部件（有一个活着就行）：1 − {' × '.join(f'(1−{v}%)' for v in p)} = {par * 100:.4f}%"
        )
        total *= par
    for line in parts:
        print(line)
    d = downtime(total * 100)
    print(
        f"\n整体可用性：{total * 100:.4f}%（每年停机约 {d['每年']}，每月约 {d['每月（30 天）']}）"
    )
    print(
        "\n提示：并联的公式假设两个部件的故障互相独立；共用机房、电源、网络、部署流水线、配置时，实际要低得多。"
    )
    return 0


def cmd_estimate(args: argparse.Namespace) -> int:
    try:
        res = estimate(args)
    except SystemExit as exc:
        print(exc.code, file=sys.stderr)
        return 1
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else render_estimate(res))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="容量和可用性估算")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estimate", help="容量估算")
    e.add_argument("--dau", type=float, required=True, help="日活用户数")
    e.add_argument("--requests-per-user", type=float, default=20, help="人均每天请求数")
    e.add_argument("--peak-factor", type=float, default=3, help="峰值 QPS 是平均 QPS 的几倍")
    e.add_argument("--read-ratio", type=float, default=0.9)
    e.add_argument("--payload-kb", type=float, default=5, help="平均响应大小 KB")
    e.add_argument(
        "--writes-per-user",
        type=float,
        default=None,
        help="人均每天写入条数，默认按请求数和读占比推算",
    )
    e.add_argument("--record-kb", type=float, default=2, help="单条记录大小 KB")
    e.add_argument("--retention-days", type=float, default=365)
    e.add_argument("--replicas", type=float, default=3)
    e.add_argument("--qps-per-node", type=float, default=500)
    e.add_argument("--headroom", type=float, default=0.3)
    e.add_argument("--hot-ratio", type=float, default=0.2)
    e.add_argument(
        "--growth", type=float, default=0, help="一年后日活增长比例，如 0.5 表示增长 50%%"
    )
    e.add_argument("--json", action="store_true")
    e.set_defaults(fn=cmd_estimate)
    s = sub.add_parser("sla", help="可用性对应的停机时间")
    s.add_argument("targets", nargs="*", help="如 99.9 99.99")
    s.set_defaults(fn=cmd_sla)
    c = sub.add_parser("compose", help="串联、并联后的整体可用性")
    c.add_argument("--serial", help="串联部件的可用性，逗号分隔，如 99.9,99.95")
    c.add_argument("--parallel", help="并联冗余部件的可用性，逗号分隔，如 99.0,99.0")
    c.set_defaults(fn=cmd_compose)
    args = ap.parse_args(argv)
    try:
        return int(args.fn(args))
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
