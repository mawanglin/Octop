---
name: legal-calc
description: "生活法律计算：legal_calc.py severance 按《劳动合同法》第 47、87 条计算经济补偿 N（满一年一个月、六个月以上按一年、不满六个月半个月，社平工资 3 倍封顶且最多 12 年）、违法解除赔偿金 2N 和代通知金；overtime 按 21.75 天计薪计算工作日 150%、休息日 200%、法定节假日 300% 加班费；deadline 计算劳动仲裁、不服仲裁起诉、上诉、再审、行政复议、行政诉讼、诉讼时效、强制执行、七日无理由退货等期限的最后一日并提示周末顺延。被辞退、讨薪、算加班费、问还来不来得及时使用。"
metadata:
  octop:
    emoji: "🧮"
    label:
      zh: "法律计算"
      en: "Legal Calculators"
    summary:
      zh: "经济补偿、加班费和法定期限。"
      en: "Severance, overtime pay and legal deadlines."
---

# 法律计算

> `scripts/` 路径相对于本技能目录。所有结果为估算，不构成法律意见。

## 1. 经济补偿 / 赔偿金

```bash
python scripts/legal_calc.py severance --start 2019-03-01 --end 2026-10-31 --wage 12000 --city-avg 12307
python scripts/legal_calc.py severance --start 2024-06-10 --end 2026-09-01 --wage 40000 --city-avg 12000 --illegal
```

- `--wage`：离职前 12 个月的平均**应发**工资（含奖金、津贴、补贴）；不满 12 个月按实际月数平均。
- `--city-avg`：当地上年度职工月平均工资（统计局 / 人社局公布）；工资超过 3 倍时按 3 倍计算、年限最多 12 年。
- `--illegal`：违法解除或终止，赔偿金为 2N（不再另付 N）。
- `--no-notice`：依《劳动合同法》第 40 条解除且未提前 30 天书面通知，加付 1 个月工资。

**哪些情况有经济补偿**（第 46 条）：协商解除（单位提出）、单位违法在先劳动者被迫辞职（如欠薪、不缴社保）、第 40 条无过失性辞退、经济性裁员、合同到期单位不续签（或降低条件续签劳动者不同意）、单位破产注销等。劳动者主动辞职、严重违纪被辞退一般没有。

## 2. 加班费

```bash
python scripts/legal_calc.py overtime --wage 10000 --weekday 20 --restday 8 --holiday 8 [--base 8000]
```

- 计算基数：劳动合同约定的工资；约定不明时按实际工资，且不低于当地最低工资。
- 休息日加班先安排补休，不能补休的才付 200%；法定节假日必须付 300%，不能以补休代替。

## 3. 法定期限

```bash
python scripts/legal_calc.py deadline --list
python scripts/legal_calc.py deadline --type appeal-judgment --from 2026-10-18
```

- 期间开始的当日不算，从次日起算；最后一日是法定节假日的，顺延到节假日后第一日。脚本只识别周末，**法定节假日和调休需对照当年放假安排核对**。
- 时效可能中止、中断（如向对方书面催告、申请调解），重要期限宁早勿晚。
