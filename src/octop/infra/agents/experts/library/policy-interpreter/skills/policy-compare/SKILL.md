---
name: policy-compare
description: "新旧政策对比：text_diff.py 按段落对齐新旧版本（docx/md/txt），列出新增、删除、修改的条款，修改处用【+新增+】【-删除-】标出数字和字词变化，可输出带“解读”列的 Excel；再逐条说明变化含义（放宽、收紧、新增、取消）和影响。新版政策发布、修订稿对比时使用。"
metadata:
  octop:
    emoji: "🆚"
    label:
      zh: "新旧对比"
      en: "Version Compare"
    summary:
      zh: "对比新旧条文，标出变化并解读影响。"
      en: "Compare old and new versions and explain the changes."
---

# 新旧版本对比

> `scripts/text_diff.py` 和 `references/` 相对于本技能目录；示例：`references/example-old.md`、`references/example-new.md`。

## 1. 对比

```bash
python scripts/text_diff.py inbound/旧版.docx inbound/新版.docx -o outputs/policy/条文对比.md --xlsx outputs/policy/条文对比.xlsx
```

- 支持 .docx、.md、.txt；PDF 先提取文字另存为 .txt 再比较（扫描件需要 OCR，提醒用户提供文字版）。
- 按段落对齐：相似段落标为"修改"，并在新文中用【+…+】【-…-】标出变化；数字作为整体比较（"5000 → 8000"）。
- Excel 对比表多一列"解读（人工填写）"，便于团队分工解读。
- 脚本只比较文字。段落顺序大幅调整时，可能出现"删除 + 新增"成对出现，需要人工确认是否为同一条款移动。

## 2. 变化解读

对每处实质性变化写：

| 条款 | 变化 | 类型 | 影响 |
|------|------|------|------|
| 第一条 | 开办补贴 5000 元 → 8000 元 | 加大支持 | 新设企业多获 3000 元 |
| 第三条 | 纳税增长奖励 → 专精特新认定奖励 | 调整方向 | 原奖励取消，需关注专精特新认定 |

类型：放宽 / 收紧 / 加大支持 / 减少支持 / 新增 / 取消 / 调整方向 / 文字修改（不影响实质）。

## 3. 交付

一段话总结"这次修订最重要的 3 个变化"→ 变化解读表 → 对用户的影响和需要调整的事项（如旧政策的在办事项如何衔接、过渡期安排；原文未规定的标〔待确认〕）。
