---
name: nutrition
description: "健身饮食计算：fitness.py tdee 用 Mifflin-St Jeor 公式算基础代谢和每日消耗，按减脂 / 维持 / 增肌给出热量和蛋白质、脂肪、碳水建议，BMI 按中国成人标准分级；fitness.py meal 按常见中国食物营养数据估算一餐的热量和三大营养素；fitness.py plan 把训练计划 Markdown 导出为每周打卡 Excel。用户问每天吃多少、这顿多少热量、要打卡表时使用。"
metadata:
  octop:
    emoji: "🥗"
    label:
      zh: "饮食与打卡"
      en: "Nutrition"
    summary:
      zh: "热量需求、餐食估算和训练打卡表。"
      en: "Calorie targets, meal estimates and workout logs."
---

# 饮食与打卡

> `scripts/` 路径相对于本技能目录。所有结果都是估算，个体差异可达 ±10–20%。

## 1. 每日热量和营养素

```bash
python scripts/fitness.py tdee --sex f --age 32 --height 162 --weight 60 --activity light --goal lose
```

- `--activity`：sedentary（久坐）、light（每周轻度运动 1–3 次）、moderate（3–5 次）、active（6–7 次高强度）、very（体力劳动或一天两练）。
- `--goal`：lose（热量缺口约 20%，不低于基础代谢和安全下限）、maintain、gain（盈余约 10%）。
- 蛋白质：减脂 2.0、维持 1.6、增肌 1.8 克/千克体重；脂肪约占 25% 热量；其余为碳水。
- BMI 偏低时脚本会提示不建议减重。

## 2. 估算一餐

```bash
python scripts/fitness.py meal "米饭 1碗, 鸡胸肉 150g, 鸡蛋 2个, 西兰花 200g, 食用油 10g"
```

- 数量可写 克/g、毫升/ml、个、碗、杯、片、勺；常见食物有默认份量（如 1 碗米饭约 150 克）。
- 内置约 60 种常见食物（主食、肉蛋奶、豆制品、蔬菜水果、坚果、油和饮料）；不认识的食物会单独列出、不计入合计，请用户换成相近食物或给出包装上的营养成分。

## 3. 训练打卡表

```bash
python scripts/fitness.py plan outputs/fitness/训练计划.md -o outputs/fitness/训练打卡.xlsx --weeks 4
```

表头至少包含「动作」；每周一列，记录实际完成的 重量×次数×组数。

## 4. 饮食建议原则

- 每餐有一份蛋白质（一掌心肉 / 鱼 / 蛋 / 豆腐）、一拳主食、两拳蔬菜。
- 减脂期优先减少含糖饮料、油炸和零食，而不是不吃主食。
- 体重以每周同一时间（晨起空腹）测量的平均值看趋势。
- 糖尿病、肾病、孕期、哺乳期等人群不使用这些通用建议，请遵医嘱。
