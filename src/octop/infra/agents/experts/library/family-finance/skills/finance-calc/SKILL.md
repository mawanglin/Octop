---
name: finance-calc
description: "家庭财税计算：finance_calc.py mortgage 同时算等额本息和等额本金（首月、末月、递减额、总利息），--prepay 期数:金额:shorten/reduce 计算提前还款（缩短年限或减少月供）节省的利息，-o 导出逐月还款计划 Excel；tax 按累计预扣法逐月计算工资个税（专项附加扣除：子女教育、婴幼儿照护、赡养老人、房贷利息或租金、继续教育），比较年终奖单独计税和并入综合所得并提示临界点；insurance 按缴费基数上下限计算养老、医疗、失业和公积金。问房贷、个税、年终奖、五险一金时使用。"
metadata:
  octop:
    emoji: "💰"
    label:
      zh: "财税计算器"
      en: "Finance Calculator"
    summary:
      zh: "房贷、提前还款、个税、年终奖和五险一金。"
      en: "Mortgage, prepayment, income tax, bonus and insurance."
---

# 财税计算器

> `scripts/` 路径相对于本技能目录。所有结果为估算。

## 1. 房贷

```bash
python scripts/finance_calc.py mortgage --principal 1000000 --rate 3.1 --years 30
python scripts/finance_calc.py mortgage --principal 1000000 --rate 3.1 --years 30 --prepay 36:200000:shorten -o outputs/finance/还款计划.xlsx
```

- `--rate` 为执行年利率（%），如 LPR 3.5 − 0.4 = 3.1；`--years` 为期限（已还过的贷款用剩余本金和剩余年限）。
- `--prepay 36:200000:shorten`：第 36 期还款后提前还 20 万并缩短年限；`reduce` 为保持年限、降低月供。可以写多个 `--prepay`。
- 输出两种还款方式的首月月供、总利息，以及提前还款后的期数、月供和节省的利息；Excel 每个方案一张逐月明细表。

## 2. 工资个税

```bash
python scripts/finance_calc.py tax --salary 20000 --base 15000 --fund 7 --children 1 --elderly 3000 --loan --bonus 60000 [-o outputs/finance/个税.xlsx]
```

| 参数 | 含义 |
|------|------|
| `--salary` | 税前月薪（应发） |
| `--base` / `--fund` / `--min` / `--max` | 缴费基数、公积金比例、基数上下限，自动算个人社保公积金；或直接用 `--insurance` 填每月个人缴纳额 |
| `--children` / `--infants` | 子女教育（3 岁至博士）/ 3 岁以下婴幼儿照护的孩子数，每孩 2000/月 |
| `--elderly` | 赡养老人每月扣除额：独生子女 3000；非独生子女为分摊额，每人最多 1500 |
| `--loan` / `--rent` | 首套住房贷款利息 1000/月；或住房租金 1500 / 1100 / 800（二选一） |
| `--edu` / `--cert` | 学历继续教育 400/月；职业资格证书取证当年 3600 |
| `--other` | 其他每月扣除（如个人养老金每年最多 12000，填 1000） |
| `--bonus` | 年终奖，比较单独计税和并入综合所得 |

输出每月预扣个税和到手工资、全年个税；年终奖给出两种方式的税额和建议，落在临界点（如 36000 元多 1 元）时提示。

## 3. 五险一金

```bash
python scripts/finance_calc.py insurance --base 15000 --fund 7 --min 7384 --max 36921
```

个人部分默认：养老 8%、医疗 2%、失业 0.5%、公积金 5%–12%（单位同比例）。基数低于下限按下限、高于上限按上限。医疗保险的大病统筹、单位缴费比例各地不同，以当地社保局公布为准。
