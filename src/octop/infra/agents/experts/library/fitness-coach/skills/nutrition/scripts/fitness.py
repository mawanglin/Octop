#!/usr/bin/env python3
"""健身饮食计算：每日热量需求、餐食营养估算、训练计划打卡表。

Usage:
    python scripts/fitness.py tdee --sex m --age 30 --height 175 --weight 75 --activity light --goal lose
    python scripts/fitness.py meal "米饭 1碗, 鸡胸肉 150g, 鸡蛋 2个, 西兰花 200g, 食用油 10g"
    python scripts/fitness.py plan 训练计划.md -o 训练打卡.xlsx [--weeks 4]

tdee：Mifflin-St Jeor 公式算基础代谢，乘活动系数得每日消耗；按目标给出热量和三大营养素建议；BMI 按中国成人标准分级。
meal：按内置的常见中国食物营养数据（每 100 克可食部，参考《中国食物成分表》量级）估算，误差约 ±10–20%；
      数量可写 克/g、毫升/ml、个、碗、杯、片、勺；不认识的食物会列出，不计入合计。
所有结果都是估算，不能替代医生或注册营养师的建议。Exit codes: 0 ok, 1 输入错误, 2 缺少 openpyxl（仅 plan）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# name: (kcal, protein g, fat g, carb g) per 100 g edible portion — rounded reference values
FOODS: dict[str, tuple[float, float, float, float]] = {
    "米饭": (116, 2.6, 0.3, 25.9), "白粥": (46, 1.1, 0.3, 9.9), "小米粥": (46, 1.4, 0.7, 8.4),
    "馒头": (223, 7.0, 1.1, 47.0), "面条": (110, 3.9, 0.4, 24.0), "包子": (227, 7.3, 7.5, 33.0),
    "饺子": (240, 8.5, 10.0, 28.0), "白面包": (266, 8.5, 3.2, 50.0), "全麦面包": (246, 13.0, 3.4, 41.0),
    "燕麦片": (377, 15.0, 6.7, 66.9), "玉米": (112, 4.0, 1.2, 22.8), "红薯": (86, 1.6, 0.1, 20.1),
    "土豆": (77, 2.0, 0.2, 17.2), "山药": (57, 1.9, 0.2, 12.4),
    "鸡蛋": (144, 13.3, 8.8, 2.8), "鸡胸肉": (133, 24.6, 1.9, 0.6), "鸡腿": (181, 16.0, 13.0, 0.0),
    "牛肉": (106, 20.2, 2.3, 1.2), "猪里脊": (155, 20.2, 7.9, 0.7), "猪肉": (143, 20.3, 6.2, 1.5),
    "五花肉": (349, 13.2, 30.6, 2.4), "羊肉": (203, 19.0, 14.1, 0.0), "三文鱼": (139, 17.2, 7.8, 0.0),
    "鳕鱼": (88, 20.4, 0.5, 0.5), "带鱼": (127, 17.7, 4.9, 3.1), "虾": (93, 18.6, 0.8, 2.8),
    "牛奶": (54, 3.0, 3.2, 3.4), "脱脂牛奶": (33, 3.4, 0.1, 4.9), "酸奶": (72, 2.5, 2.7, 9.3),
    "无糖酸奶": (60, 3.5, 3.0, 4.5), "奶酪": (328, 25.7, 23.5, 3.5), "豆浆": (31, 3.0, 1.6, 1.2),
    "豆腐": (82, 8.1, 3.7, 4.2), "豆腐干": (140, 16.2, 3.6, 11.5), "毛豆": (131, 13.1, 5.0, 10.5),
    "花生": (574, 24.8, 44.3, 21.7), "核桃": (627, 14.9, 58.8, 19.1), "杏仁": (578, 22.5, 45.4, 23.9),
    "苹果": (53, 0.4, 0.2, 13.7), "香蕉": (93, 1.4, 0.2, 22.0), "橙子": (48, 0.8, 0.2, 11.1),
    "葡萄": (44, 0.5, 0.2, 10.3), "西瓜": (31, 0.5, 0.3, 6.8), "猕猴桃": (61, 0.8, 0.6, 14.5),
    "草莓": (32, 1.0, 0.2, 7.1), "蓝莓": (57, 0.7, 0.3, 14.5),
    "西兰花": (36, 4.1, 0.6, 4.3), "菠菜": (28, 2.6, 0.3, 4.5), "青菜": (17, 1.5, 0.3, 2.7),
    "生菜": (15, 1.3, 0.3, 2.0), "黄瓜": (16, 0.8, 0.2, 2.9), "番茄": (20, 0.9, 0.2, 4.0),
    "胡萝卜": (39, 1.0, 0.2, 8.8), "白菜": (20, 1.5, 0.1, 3.2), "芹菜": (17, 0.8, 0.1, 3.9),
    "茄子": (23, 1.1, 0.2, 4.9), "蘑菇": (24, 2.7, 0.1, 4.1), "南瓜": (23, 0.7, 0.1, 5.3),
    "食用油": (899, 0.0, 99.9, 0.0), "黄油": (888, 1.4, 98.0, 0.0), "白糖": (400, 0.0, 0.0, 99.9),
    "蜂蜜": (321, 0.4, 1.9, 75.6), "可乐": (43, 0.0, 0.0, 10.6), "啤酒": (32, 0.4, 0.0, 3.0),
    "蛋白粉": (380, 78.0, 3.0, 8.0),
}  # fmt: skip
ALIASES = {
    "大米饭": "米饭", "白米饭": "米饭", "粥": "白粥", "大米粥": "白粥", "面": "面条", "挂面": "面条",
    "面包": "白面包", "吐司": "白面包", "燕麦": "燕麦片", "地瓜": "红薯", "红苕": "红薯", "马铃薯": "土豆",
    "鸡蛋清": "鸡蛋", "鸡胸": "鸡胸肉", "牛腱": "牛肉", "瘦牛肉": "牛肉", "瘦肉": "猪肉", "里脊": "猪里脊",
    "大虾": "虾", "虾仁": "虾", "鲜奶": "牛奶", "纯牛奶": "牛奶", "希腊酸奶": "无糖酸奶", "北豆腐": "豆腐",
    "西红柿": "番茄", "小白菜": "青菜", "上海青": "青菜", "油菜": "青菜", "西蓝花": "西兰花", "花菜": "西兰花",
    "油": "食用油", "植物油": "食用油", "花生油": "食用油", "橄榄油": "食用油", "糖": "白糖",
}  # fmt: skip
# grams per common unit for specific foods; generic fallbacks below
UNIT_GRAMS = {
    ("鸡蛋", "个"): 50, ("香蕉", "根"): 120, ("香蕉", "个"): 120, ("苹果", "个"): 200, ("橙子", "个"): 180,
    ("猕猴桃", "个"): 80, ("馒头", "个"): 100, ("包子", "个"): 80, ("饺子", "个"): 20, ("玉米", "根"): 200,
    ("红薯", "个"): 200, ("土豆", "个"): 150, ("米饭", "碗"): 150, ("白粥", "碗"): 250, ("小米粥", "碗"): 250,
    ("面条", "碗"): 250, ("牛奶", "杯"): 250, ("牛奶", "盒"): 250, ("豆浆", "杯"): 250, ("酸奶", "杯"): 200,
    ("酸奶", "盒"): 100, ("白面包", "片"): 30, ("全麦面包", "片"): 35, ("奶酪", "片"): 20, ("食用油", "勺"): 10,
    ("白糖", "勺"): 10, ("蜂蜜", "勺"): 20, ("蛋白粉", "勺"): 30, ("可乐", "罐"): 330, ("啤酒", "罐"): 330,
}  # fmt: skip
GENERIC_UNITS = {"克": 1, "g": 1, "毫升": 1, "ml": 1, "两": 50, "斤": 500, "kg": 1000, "公斤": 1000}
ACTIVITY = {"sedentary": (1.2, "久坐不动"), "light": (1.375, "每周轻度运动 1–3 次"), "moderate": (1.55, "每周中等运动 3–5 次"),
            "active": (1.725, "每周高强度运动 6–7 次"), "very": (1.9, "体力劳动或一天两练")}  # fmt: skip


class FitError(ValueError):
    pass


def bmi_level(bmi: float) -> str:
    if bmi < 18.5:
        return "偏瘦"
    if bmi < 24:
        return "正常"
    if bmi < 28:
        return "超重"
    return "肥胖"


def cmd_tdee(sex: str, age: int, height: float, weight: float, activity: str, goal: str) -> int:
    if sex not in ("m", "f"):
        raise FitError("--sex 只能是 m（男）或 f（女）")
    if not (14 <= age <= 90 and 120 <= height <= 230 and 30 <= weight <= 250):
        raise FitError("年龄 14–90 岁、身高 120–230 cm、体重 30–250 kg 之外的情况请咨询医生")
    bmr = 10 * weight + 6.25 * height - 5 * age + (5 if sex == "m" else -161)
    factor, label = ACTIVITY[activity]
    tdee = bmr * factor
    floor = 1500 if sex == "m" else 1200
    if goal == "lose":
        target, protein_per_kg, note = (
            max(tdee * 0.8, floor, bmr),
            2.0,
            "热量缺口约 20%，每周约减 0.5 kg",
        )
    elif goal == "gain":
        target, protein_per_kg, note = (
            tdee * 1.1,
            1.8,
            "热量盈余约 10%，配合力量训练，每周增重 0.25–0.5 kg",
        )
    else:
        target, protein_per_kg, note = tdee, 1.6, "维持体重"
    protein = protein_per_kg * weight
    fat = target * 0.25 / 9
    carb = max(0.0, (target - protein * 4 - fat * 9) / 4)
    bmi = weight / (height / 100) ** 2
    print(
        f"BMI {bmi:.1f}（{bmi_level(bmi)}；中国成人标准：18.5–23.9 正常，24–27.9 超重，≥28 肥胖）"
    )
    if goal == "lose" and bmi < 20:
        print(
            "注意：BMI 已在正常偏低范围，不建议继续减重；更适合以增肌、改善体态为目标，如有进食困扰请咨询医生。"
        )
    print(
        f"基础代谢 约 {bmr:.0f} 千卡/天；活动水平：{label}（×{factor}）；每日总消耗 约 {tdee:.0f} 千卡"
    )
    print(f"建议每日摄入 约 {target:.0f} 千卡（{note}）")
    print(
        f"- 蛋白质 {protein:.0f} 克（{protein_per_kg} 克/千克体重，约 {protein * 4 / target:.0%} 热量）"
    )
    print(f"- 脂肪 {fat:.0f} 克（约 25% 热量）")
    print(f"- 碳水 {carb:.0f} 克（约 {carb * 4 / target:.0%} 热量）")
    if goal == "lose" and target <= floor + 1:
        print(f"提示：已按最低 {floor} 千卡/天兜底，不建议更低；如需更快减重请在医生指导下进行")
    print("以上为公式估算，个体差异可达 ±10%；孕期、哺乳期、慢性病人群请遵医嘱。")
    return 0


def parse_items(text: str) -> list[tuple[str, float, str]]:
    out = []
    for part in re.split(r"[,，、;；\n]+|\s+和\s+", text):
        part = part.strip()
        if not part:
            continue
        m = re.match(
            r"^(.+?)\s*([0-9]+(?:\.[0-9]+)?|半|一|两|二|三|四|五)\s*(克|g|毫升|ml|个|根|碗|杯|片|勺|盒|罐|两|斤|kg|公斤)?$",
            part,
            re.I,
        )
        if not m:
            raise FitError(f"看不懂「{part}」，请写成“食物 数量单位”，如“米饭 1碗”“鸡胸肉 150g”")
        name, qty_text, unit = m.group(1).strip(), m.group(2), (m.group(3) or "克").lower()
        qty = {"半": 0.5, "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5}.get(
            qty_text
        ) or float(qty_text)
        out.append((name, qty, unit))
    return out


def cmd_meal(text: str) -> int:
    items = parse_items(text)
    totals = [0.0, 0.0, 0.0, 0.0]
    unknown = []
    print("| 食物 | 估算重量 | 热量(千卡) | 蛋白质(g) | 脂肪(g) | 碳水(g) |")
    print("|------|----------|------------|-----------|---------|---------|")
    for name, qty, unit in items:
        key = name if name in FOODS else ALIASES.get(name)
        if key is None:
            unknown.append(name)
            continue
        if unit in GENERIC_UNITS:
            grams = qty * GENERIC_UNITS[unit]
        elif (key, unit) in UNIT_GRAMS:
            grams = qty * UNIT_GRAMS[(key, unit)]
        else:
            unknown.append(f"{name}（不知道“{unit}”有多重，请改用克）")
            continue
        values = [v * grams / 100 for v in FOODS[key]]
        totals = [a + b for a, b in zip(totals, values, strict=True)]
        print(
            f"| {name} | {grams:.0f} g | {values[0]:.0f} | {values[1]:.1f} | {values[2]:.1f} | {values[3]:.1f} |"
        )
    print(
        f"| **合计** | | **{totals[0]:.0f}** | **{totals[1]:.1f}** | **{totals[2]:.1f}** | **{totals[3]:.1f}** |"
    )
    energy = totals[1] * 4 + totals[2] * 9 + totals[3] * 4
    if energy:
        print(
            f"\n供能比：蛋白质 {totals[1] * 4 / energy:.0%}，脂肪 {totals[2] * 9 / energy:.0%}，碳水 {totals[3] * 4 / energy:.0%}"
        )
    if unknown:
        print(f"未计入（不在内置数据中）：{'、'.join(unknown)}——可按包装营养成分表补充")
    print("估算值，误差约 ±10–20%，烹饪用油和调料常被低估。")
    return 0


def cmd_plan(src: Path, out: Path, weeks: int) -> int:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:  # pragma: no cover - environment check
        print("缺少依赖 openpyxl：请运行 `pip install openpyxl`", file=sys.stderr)
        return 2
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")]
            for ln in src.read_text(encoding="utf-8").splitlines() if ln.strip().startswith("|")]  # fmt: skip
    rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
    if len(rows) < 2 or "动作" not in rows[0]:
        raise FitError(
            "训练计划需要一张表格，表头至少包含「动作」，建议：| 训练日 | 动作 | 组数 | 次数 | 重量 | 备注 |"
        )
    header, body = rows[0], rows[1:]
    wb = Workbook()
    ws = wb.active
    ws.title = "训练打卡"
    track = [f"第{w}周" for w in range(1, weeks + 1)]
    ws.append([*header, *track])
    fill = PatternFill("solid", fgColor="15803D")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = fill
        c.alignment = Alignment(horizontal="center")
    for r in body:
        ws.append([*r, *([""] * weeks)])
    for j in range(1, len(header) + weeks + 1):
        ws.column_dimensions[chr(64 + j) if j <= 26 else "Z"].width = 18 if j <= len(header) else 14
    note_row = ws.max_row + 2
    ws.cell(
        note_row,
        1,
        "打卡：每周在对应格子记录实际完成的 重量×次数×组数（如 40kg×10×3），感觉吃力可写 RPE。",
    ).font = Font(color="6B7280")
    ws.freeze_panes = ws.cell(2, len(header) + 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    print(f"已生成 {out}：{len(body)} 个动作，{weeks} 周打卡列")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tdee")
    t.add_argument("--sex", required=True, help="m 男 / f 女")
    t.add_argument("--age", type=int, required=True)
    t.add_argument("--height", type=float, required=True, help="厘米")
    t.add_argument("--weight", type=float, required=True, help="千克")
    t.add_argument("--activity", choices=sorted(ACTIVITY), default="light")
    t.add_argument("--goal", choices=["lose", "maintain", "gain"], default="maintain")
    m = sub.add_parser("meal")
    m.add_argument("items", help='如 "米饭 1碗, 鸡胸肉 150g, 鸡蛋 2个"')
    p = sub.add_parser("plan")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--weeks", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "tdee":
            return cmd_tdee(args.sex, args.age, args.height, args.weight, args.activity, args.goal)
        if args.cmd == "meal":
            return cmd_meal(args.items)
        return cmd_plan(Path(args.input), Path(args.output), args.weeks)
    except (OSError, FitError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
