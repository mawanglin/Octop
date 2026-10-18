---
name: practice-sheets
description: "练习卷生成：math_drill.py 按题型批量出数学练习题（加减法可控制进位退位、乘法口诀、多位数乘除、有余数除法、三步混合运算、小数加减、分数加减、一元一次方程），答案由程序精确计算，导出可打印的 Word（姓名日期栏、多列排版、答案另起一页），--seed 可复现。需要口算练习、专项计算练习时使用。"
metadata:
  octop:
    emoji: "📝"
    label:
      zh: "练习卷"
      en: "Practice Sheets"
    summary:
      zh: "按题型出计算练习，答案准确，导出 Word 打印。"
      en: "Printable math drills by type with verified answers."
---

# 练习卷

> `scripts/` 路径相对于本技能目录。

## 1. 出题

```bash
python scripts/math_drill.py --list                                          # 列出题型
python scripts/math_drill.py --type add --max 100 --carry require -n 40 -o outputs/tutor/进位加法.docx
python scripts/math_drill.py --type mixed -n 20 --cols 2 --title "三年级混合运算" -o outputs/tutor/混合运算.docx
```

| 题型 | 说明 | 建议年级 |
|------|------|------|
| `add` / `sub` | 加法 / 减法；`--max` 数的上限，`--carry require/avoid/any` 是否进位（减法为退位） | 一、二年级 |
| `addsub` | 连加连减 | 二年级 |
| `table` | 乘法口诀 | 二年级 |
| `mul` | 多位数 × 一位数（`--max 999` 为三位数） | 三年级 |
| `mul2` | 两位数 × 两位数 | 三年级 |
| `div` / `divr` | 整除 / 有余数除法 | 二、三年级 |
| `mixed` | 三步混合运算（含括号，每一步结果都是正整数） | 三、四年级 |
| `decimal` | 一到两位小数加减 | 四年级 |
| `fraction` | 同分母、异分母分数加减，结果为最简分数 | 五年级 |
| `equation` | 一元一次方程 ax + b = c，整数解 | 五、六年级 |

- `-n` 题数（1–200），`--cols` 每行列数（1–5），`--seed` 固定种子可重新生成同一张卷子。
- 不加 `-o` 时在终端输出题目和答案，适合先预览。

## 2. 卷面

第 1 页：标题、姓名 / 日期 / 用时 / 得分栏、题目（按列从上到下排）；第 2 页：答案。A4 纵向，可以直接打印。

## 3. 使用建议

- 口算：每天 5–10 分钟、20–30 道，记录用时，看速度和正确率的变化。
- 专项：错题本里某类题错得多时，出 10–20 道同类题；错的题再记进错题本。
- 难度递进：先 `--carry avoid`，熟练后 `--carry require`，再 `any` 混合。
- 应用题、语文、英语练习由你根据教材内容编写，答案需逐题核对。
