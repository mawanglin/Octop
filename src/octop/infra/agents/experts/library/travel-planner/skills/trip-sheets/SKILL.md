---
name: trip-sheets
description: "旅行表格工具：trip.py sheet 把行程 Markdown 导出为 Excel（行程表、每日费用、分类预算饼图），检查同一天时间重叠或倒序、多日行程缺住宿的晚上、超预算；trip.py packing 按天数、气候（hot/mild/cold/rain）和出行类型（city/beach/hiking/business/family/abroad）生成可勾选的行李清单。行程定好后需要表格或行李清单时使用。"
metadata:
  octop:
    emoji: "🧳"
    label:
      zh: "行程表与行李单"
      en: "Trip Sheets"
    summary:
      zh: "行程 Excel、费用预算、冲突检查和行李清单。"
      en: "Itinerary workbook, budget, conflict checks and packing list."
---

# 行程表与行李清单

> `scripts/` 和 `references/` 路径相对于本技能目录；示例行程：`references/example-trip.md`。

## 1. 行程 Markdown 格式

```markdown
---
行程: 成都 3 天 2 晚
出发: 2026-11-06
人数: 2
预算: 4000
---
| 日期 | 时间 | 地点 | 活动 | 类别 | 交通 | 费用 | 备注 |
|------|------|------|------|------|------|------|------|
| D1 | 08:00-10:30 | 上海虹桥 → 成都东 | 高铁 | 交通 | 高铁 | 1100 | |
| D1 | 11:30 | 春熙路 | 入住酒店 | 住宿 | 地铁 | 900 | 两晚 |
```

- **日期**：`D1`/`D2` 或 `2026-11-06`；写了「出发」时 D1 会换算成具体日期。
- **时间**：`09:00` 或 `09:00-11:30`。
- **类别**：交通 / 住宿 / 餐饮 / 门票 / 购物 / 其他；留空时按活动和备注猜测。
- **费用**：这一项的总费用（不是人均），没有就写 0。
- 住宿备注写"两晚""3 晚"时，后面几晚都算有住宿。

## 2. 导出行程 Excel

```bash
python scripts/trip.py sheet outputs/trip/行程.md -o outputs/trip/行程.xlsx
```

工作表：行程（横向适合打印，带合计公式）、每日费用、分类预算（带饼图）。终端会打印总费用、人均，以及：
- 同一天时间重叠或顺序倒置的条目；
- 多日行程中没有住宿安排的晚上；
- 超出预算多少。

把这些提示告诉用户并修改行程后重新导出。

## 3. 行李清单

```bash
python scripts/trip.py packing --days 5 --climate cold,rain --type city,abroad --people 2 -o outputs/trip/行李清单.xlsx
```

- `--climate`：hot（炎热）、mild（温和）、cold（寒冷）、rain（多雨），可多选；
- `--type`：city（城市）、beach（海边）、hiking（徒步）、business（商务）、family（亲子）、abroad（出境），可多选；
- 衣物数量按天数计算，内衣袜子最多带 7 套（超过一周建议中途洗衣）；Excel 带一列「已准备」用于勾选，不加 `-o` 时直接在终端输出勾选清单。
