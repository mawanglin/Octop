---
name: data-toolkit
description: "数据处理工具：profile_data.py 对 Excel/CSV 做数据画像（字段类型、缺失率、唯一值、数值分布、IQR 异常值、Top 值、写法不一致、重复行）；pivot_chart.py 做分组汇总（求和/计数/平均）、按月季年汇总并计算环比同比、占比、Top N 合并，输出带 Excel 原生图表的汇总表。只依赖 openpyxl，不需要 pandas。拿到数据先画像、需要汇总和图表时使用。"
metadata:
  octop:
    emoji: "🧮"
    label:
      zh: "数据工具箱"
      en: "Data Toolkit"
    summary:
      zh: "数据画像、透视汇总、同比环比和 Excel 图表。"
      en: "Profiling, pivots, period comparisons, and Excel charts."
---

# 数据工具箱

> `scripts/` 和 `references/` 路径相对于本技能目录；示例数据：`references/example-sales.csv`。

## 1. 数据画像（每次分析的第一步）

```bash
python scripts/profile_data.py inbound/数据.xlsx [--sheet 工作表名] [--header-row 1] [--json]
```

输出每个字段的类型（数值/日期/文本）、缺失率、唯一值数和概况，以及「数据质量提示」：
- 数值字段：范围、均值、中位数、IQR 异常值个数、混入的非数字值；
- 日期字段：起止日期、无法识别的值；
- 文本字段：Top 值、大小写或空格不同但内容相同的写法（如"华东"和" 华东"）；
- 可能是唯一标识的字段（订单号、编号）、完全重复的行、缺失率超过 20% 的字段。

CSV 自动识别 UTF-8 和 GB18030 编码；表头不在第一行时用 `--header-row`。

## 2. 透视汇总与图表

```bash
# 按类别汇总（自动计算占比，默认降序）
python scripts/pivot_chart.py 数据.xlsx -o outputs/analysis/区域汇总.xlsx --rows 区域 --values 销售额

# 按时间汇总（month / quarter / year），自动计算环比；跨年数据同时计算同比
python scripts/pivot_chart.py 数据.xlsx -o outputs/analysis/季度趋势.xlsx --date 日期 --period quarter --values 销售额

# 交叉汇总（二维透视），计数
python scripts/pivot_chart.py 数据.xlsx -o outputs/analysis/产品x区域.xlsx --rows 产品 --columns 区域 --agg count

# 只看前 5 名，其余合并为"其他"；指定图表类型
python scripts/pivot_chart.py 数据.xlsx -o top5.xlsx --rows 客户 --values 销售额 --top 5 --chart bar
```

- `--agg`：sum（默认）、count、mean；`--chart`：auto（默认：时间→折线，类别≤6→饼图，其余→柱形）、column、bar、line、pie、none。
- 输出 Excel：「汇总」表（带合计行，占比/环比/同比为百分比格式）+ 原生图表（可在 Excel 里直接改样式）+「原始数据」副本。
- 终端同时打印 Markdown 汇总表，写报告时直接引用其中的数字。
- 文本分组会自动去掉首尾空格；日期或数值无法识别的行不计入，并提示行数——报告里要说明。

## 3. 数据清洗

脚本只读不改原始数据。需要清洗时（统一写法、删除重复、剔除异常值），把清洗规则告诉用户，确认后用 Python（openpyxl）另存一份新文件，再对新文件做分析；也可以交给「小办 · 办公自动化」专家处理复杂的表格操作。
