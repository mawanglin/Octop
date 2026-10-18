---
name: menu-plan
description: "菜单与买菜清单：menu_plan.py plan 从菜谱库（references/recipes.csv，30 道家常菜，每人份食材）按天数、人数、餐次排出每餐 1 荤 1 素（4 人以上或 --soup 加汤）、一周不重复、相邻两餐不用同一主料的菜单，--avoid 按标签或食材排除忌口，合并各餐食材按人数换算成分类买菜清单（蔬菜水果、肉禽、水产、蛋奶豆制品、主食干货），-o 导出带“已买”勾选列的 Excel；shopping 从任意菜单 Markdown 汇总食材；list 按类型和标签列出菜谱。排一周菜单、生成买菜清单时使用。"
metadata:
  octop:
    emoji: "🛒"
    label:
      zh: "菜单与买菜清单"
      en: "Menu & Shopping"
    summary:
      zh: "一周荤素搭配菜单，自动合并买菜清单。"
      en: "Balanced weekly menus with merged shopping lists."
---

# 菜单与买菜清单

> `scripts/` 和 `references/` 路径相对于本技能目录；菜谱库：`references/recipes.csv`。

## 1. 排菜单

```bash
python scripts/menu_plan.py plan --days 7 --people 3 --meals lunch,dinner --avoid 辣,海鲜 -o outputs/kitchen/本周菜单.xlsx
```

- `--meals`：breakfast / lunch / dinner，逗号分隔；早餐建议另外安排（粥、面点、鸡蛋、牛奶）。
- `--avoid`：标签（辣、海鲜、花生、费时）或食材名（羊肉、虾）；`--soup` 每餐加汤（4 人以上自动加）。
- `--seed`：固定随机种子，重复生成同一份菜单；不满意就换一个种子。
- 输出每餐菜品和分类买菜清单；Excel 有「菜单」「买菜清单」两张表。主食米饭按需另备。

## 2. 按自己的菜单生成清单

```bash
python scripts/menu_plan.py shopping outputs/kitchen/我的菜单.md --people 2
```

Markdown 里出现的菜谱库菜名都会计入（出现几次算几次）；不在菜谱库里的菜会列出来，由你按 `cooking-guide` 补充食材。

## 3. 查菜谱

```bash
python scripts/menu_plan.py list [--tag 快手]
```

标签：快手、儿童、清淡、下饭、费时、辣、海鲜、花生、凉菜。

## 4. 扩充菜谱库

复制 `references/recipes.csv` 到 `outputs/kitchen/我的菜谱.csv` 添加菜品，运行时加 `--recipes outputs/kitchen/我的菜谱.csv`（放在子命令之前）。食材写成 `名称:每人份数量:单位`，用 `;` 分隔，第一个食材作为"主料"用于避免相邻两餐重复。
