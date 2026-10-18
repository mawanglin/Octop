#!/usr/bin/env python3
"""生活法律计算：解除劳动合同经济补偿、加班费、常见法定期限。结果仅供参考，不构成法律意见。

Usage:
    python scripts/legal_calc.py severance --start 2019-03-01 --end 2026-10-31 --wage 12000 [--city-avg 12307] [--illegal] [--no-notice]
    python scripts/legal_calc.py overtime --wage 10000 [--weekday 20] [--restday 8] [--holiday 8] [--base 8000]
    python scripts/legal_calc.py deadline --type appeal-judgment --from 2026-10-18
    python scripts/legal_calc.py deadline --list

severance（《劳动合同法》第 47、87 条，第 40 条代通知金）：
    每满一年支付一个月工资；六个月以上不满一年按一年；不满六个月支付半个月工资。
    --wage 为解除前 12 个月的平均工资（含奖金、津贴、补贴，税前）；
    月工资高于当地上年度职工月平均工资 3 倍的，按 3 倍计算，且年限最多 12 年（需 --city-avg）；
    --illegal 违法解除按 2 倍（赔偿金，不再另付经济补偿）；--no-notice 未提前 30 天通知时加付 1 个月工资（代通知金）。
overtime（《劳动法》第 44 条）：日工资 = 月工资 ÷ 21.75，小时工资 = 日工资 ÷ 8；
    工作日延时 150%、休息日 200%（未安排补休时）、法定节假日 300%；--base 为合同约定的加班费计算基数（不得低于最低工资）。
deadline：从事件发生 / 知道之日的次日起算；期限最后一日是法定节假日的，顺延到节假日后第一个工作日（本工具只能识别周末，
    调休和法定节假日请对照当年国务院放假安排核对）。
Exit codes: 0 ok, 1 输入错误。
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import sys
from decimal import ROUND_HALF_UP, Decimal

# (类型, 名称, 期限, 单位, 依据, 说明)
DEADLINES: list[tuple[str, str, int, str, str, str]] = [
    ("labor-arbitration", "劳动争议申请仲裁", 1, "year", "《劳动争议调解仲裁法》第 27 条",
     "从知道或应当知道权利被侵害之日起算；劳动关系存续期间拖欠劳动报酬的，自劳动关系终止之日起算"),
    ("sue-after-arbitration", "不服劳动仲裁裁决起诉", 15, "day", "《劳动争议调解仲裁法》第 48、50 条", "自收到仲裁裁决书之日起"),
    ("civil-limitation", "民事诉讼时效（一般）", 3, "year", "《民法典》第 188 条", "自知道或应当知道权利受到损害以及义务人之日起；可因催告、起诉等中断"),
    ("appeal-judgment", "不服一审判决上诉", 15, "day", "《民事诉讼法》第 171 条", "自判决书送达之日起"),
    ("appeal-ruling", "不服一审裁定上诉", 10, "day", "《民事诉讼法》第 171 条", "自裁定书送达之日起"),
    ("retrial", "申请再审", 6, "month", "《民事诉讼法》第 216 条", "自判决、裁定发生法律效力后"),
    ("admin-review", "申请行政复议", 60, "day", "《行政复议法》第 20 条", "自知道或应当知道该行政行为之日起"),
    ("admin-suit", "提起行政诉讼", 6, "month", "《行政诉讼法》第 46 条", "自知道或应当知道作出行政行为之日起"),
    ("enforcement", "申请强制执行", 2, "year", "《民事诉讼法》第 250 条", "从法律文书规定履行期间的最后一日起计算"),
    ("online-return", "网购七日无理由退货", 7, "day", "《消费者权益保护法》第 25 条", "自收到商品之日起；定作、鲜活易腐、已拆封的音像制品等除外"),
    ("product-return", "三包商品 7 日内退货", 7, "day", "家用汽车、部分商品三包规定", "自开具发票之日起，出现性能故障的；具体以对应三包规定为准"),
    ("product-exchange", "三包商品 15 日内换货", 15, "day", "部分商品三包规定", "自开具发票之日起，出现性能故障的；具体以对应三包规定为准"),
    ("deposit-refund", "租房押金约定退还", 0, "day", "以租赁合同约定为准", "合同没有约定时，一般在退租并结清费用后及时退还"),
]  # fmt: skip
UNIT_CN = {"day": "日", "month": "个月", "year": "年"}


class LegalError(ValueError):
    pass


def money(x: Decimal) -> str:
    return f"{x.quantize(Decimal('0.01'), ROUND_HALF_UP):,}"


def add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return dt.date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def service_length(start: dt.date, end: dt.date) -> tuple[int, int, int]:
    """(full years, extra full months, extra days) between start and end."""
    years = 0
    while add_months(start, (years + 1) * 12) <= end:
        years += 1
    anchor = add_months(start, years * 12)
    months = 0
    while months < 11 and add_months(anchor, months + 1) <= end:
        months += 1
    return years, months, (end - add_months(anchor, months)).days


def cmd_severance(
    start: dt.date,
    end: dt.date,
    wage: Decimal,
    city_avg: Decimal | None,
    illegal: bool,
    no_notice: bool,
) -> int:
    if end <= start:
        raise LegalError("离职日期必须晚于入职日期")
    years, months, days = service_length(start, end)
    if months >= 6:
        n = Decimal(years + 1)  # six months or more counts as a full year
    elif months or days:
        n = Decimal(years) + Decimal("0.5")
    else:
        n = Decimal(years)
    base = wage
    notes = []
    if city_avg is not None and wage > city_avg * 3:
        base = city_avg * 3
        if n > 12:
            n = Decimal(12)
            notes.append("月工资超过当地社平工资 3 倍，补偿年限最多按 12 年计算")
        notes.append(f"月工资超过当地社平工资 3 倍，计算基数按 {money(base)} 元")
    elif city_avg is None:
        notes.append(
            "未提供当地上年度职工月平均工资（--city-avg）；月工资较高时可能受 3 倍封顶限制"
        )
    comp = base * n
    print(f"工作年限：{start} 至 {end}，{years} 年 {months} 个月 {days} 天 → 经济补偿 N = {n:g}")
    print(f"计算基数：{money(base)} 元/月（离职前 12 个月平均应发工资）")
    print(f"经济补偿（N）：{money(comp)} 元 —《劳动合同法》第 47 条")
    total = comp
    if illegal:
        total = comp * 2
        print(
            f"违法解除赔偿金（2N）：{money(total)} 元 —《劳动合同法》第 87 条（支付赔偿金的，不再支付经济补偿）"
        )
    if no_notice:
        total += wage
        print(
            f"代通知金（+1 个月）：{money(wage)} 元 —《劳动合同法》第 40 条，仅适用于该条规定的解除情形，按上一个月工资计算"
        )
    if illegal or no_notice:
        print(f"合计：{money(total)} 元")
    for n_ in notes:
        print(f"提示：{n_}")
    print(
        "提示：适用情形（协商解除、裁员、合同到期不续签、违法解除等）不同，结果不同；以上为估算，不构成法律意见。"
    )
    return 0


def cmd_overtime(
    wage: Decimal, base: Decimal | None, weekday: Decimal, restday: Decimal, holiday: Decimal
) -> int:
    b = base if base is not None else wage
    daily = b / Decimal("21.75")
    hourly = daily / 8
    parts = [
        ("工作日延时", weekday, Decimal("1.5")),
        ("休息日（未补休）", restday, Decimal("2")),
        ("法定节假日", holiday, Decimal("3")),
    ]
    print(
        f"计算基数 {money(b)} 元/月 → 日工资 {money(daily)} 元，小时工资 {money(hourly)} 元（月计薪天数 21.75）"
    )
    total = Decimal(0)
    for name, hours, rate in parts:
        if hours:
            pay = hourly * hours * rate
            total += pay
            print(f"- {name} {hours:g} 小时 × {rate * 100:g}%：{money(pay)} 元")
    print(f"加班费合计：{money(total)} 元")
    if weekday > 36:
        print("提示：每月延长工作时间一般不得超过 36 小时（《劳动法》第 41 条）")
    print(
        "提示：综合工时、不定时工时制度和实行计件工资的计算方式不同；以上为估算，不构成法律意见。"
    )
    return 0


def cmd_deadline(kind: str, start: dt.date) -> int:
    row = next((d for d in DEADLINES if d[0] == kind), None)
    if row is None:
        raise LegalError(f"不支持的期限类型「{kind}」，用 --list 查看")
    _k, name, amount, unit, basis, note = row
    if amount == 0:
        print(f"{name}：{note}（{basis}）")
        return 0
    if unit == "day":
        last = start + dt.timedelta(
            days=amount
        )  # counted from the next day, so day N lands on start + N
    elif unit == "month":
        last = add_months(start, amount)
    else:
        last = add_months(start, amount * 12)
    print(f"{name}：{amount}{UNIT_CN[unit]}，{basis}")
    print(f"起算：{start} 的次日；{note}")
    print(f"最后一日：{last}（{'一二三四五六日'[last.weekday()]}）")
    if last.weekday() >= 5:
        nxt = last + dt.timedelta(days=7 - last.weekday())
        print(f"最后一日是周末，一般顺延至 {nxt}；如遇法定节假日或调休，请按当年放假安排核对")
    print(
        "提示：期限可能因中止、中断、特别规定而不同，重要事项请尽早办理并咨询律师；不构成法律意见。"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("severance")
    s.add_argument("--start", required=True)
    s.add_argument("--end", required=True)
    s.add_argument("--wage", required=True, type=Decimal)
    s.add_argument("--city-avg", type=Decimal)
    s.add_argument("--illegal", action="store_true")
    s.add_argument("--no-notice", action="store_true")
    o = sub.add_parser("overtime")
    o.add_argument("--wage", required=True, type=Decimal)
    o.add_argument("--base", type=Decimal)
    o.add_argument("--weekday", type=Decimal, default=Decimal(0))
    o.add_argument("--restday", type=Decimal, default=Decimal(0))
    o.add_argument("--holiday", type=Decimal, default=Decimal(0))
    d = sub.add_parser("deadline")
    d.add_argument("--type")
    d.add_argument("--from", dest="start")
    d.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "severance":
            return cmd_severance(dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end), args.wage,
                                 args.city_avg, args.illegal, args.no_notice)  # fmt: skip
        if args.cmd == "overtime":
            if args.wage <= 0:
                raise LegalError("--wage 必须大于 0")
            return cmd_overtime(args.wage, args.base, args.weekday, args.restday, args.holiday)
        if args.list or not args.type:
            for k, name, amount, unit, basis, _n in DEADLINES:
                print(
                    f"{k:22s} {name}（{amount or '约定'}{UNIT_CN[unit] if amount else ''}，{basis}）"
                )
            return 0 if args.list else 1
        if not args.start:
            raise LegalError("请用 --from 指定起算事件的日期（如判决书送达日）")
        return cmd_deadline(args.type, dt.date.fromisoformat(args.start))
    except (LegalError, ValueError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
