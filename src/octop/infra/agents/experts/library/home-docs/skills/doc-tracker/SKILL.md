---
name: doc-tracker
description: "家庭证件台账与到期提醒：doc_tracker.py build 把 Markdown 清单（名称、类型、持有人、编号、到期日、提前提醒天数、存放位置、备注）生成按到期时间排序、分色标注（已过期 / 即将到期 / 注意 / 正常 / 长期）的 Excel 台账，编号自动只保留后 4 位，提醒天数按类型默认（护照身份证 180 天、合同 60 天、保险车辆 30 天）；due 列出已过期和指定天数内到期的项目；ics 导出可导入手机日历的提醒（已过期和长期有效的不导出）。建台账、查快到期的证件、要手机提醒时使用。"
metadata:
  octop:
    emoji: "🗂️"
    label:
      zh: "证件台账"
      en: "Document Tracker"
    summary:
      zh: "证件保单合同到期台账和日历提醒。"
      en: "Expiry ledger and calendar reminders."
---

# 证件台账

> `scripts/` 和 `references/` 路径相对于本技能目录；示例：`references/example-docs.md`（虚构）。

## 1. 清单格式

```markdown
| 名称 | 类型 | 持有人 | 编号 | 到期日 | 提前提醒天数 | 存放位置 | 备注 |
|------|------|--------|------|--------|--------------|----------|------|
| 护照 | 证件 | 爸爸 | 5678 | 2027-03-15 | | 书房保险柜 | 出国前确认有效期 6 个月以上 |
| 户口本 | 证件 | 家庭 | | 长期 | | 书房保险柜 | |
```

- 到期日写 `2027-03-15`，长期有效写 `长期`。
- 编号只写后 4 位；写了完整号码也会在台账中自动只保留后 4 位（但 Markdown 原文件里仍然有，请删除）。
- 提前提醒天数不写时：护照、身份证 180 天，港澳通行证、签证、驾驶证 90 天，合同 60 天，保险、车辆和其他 30 天。

## 2. 生成台账

```bash
python scripts/doc_tracker.py build outputs/home-docs/家庭证件.md -o outputs/home-docs/家庭证件台账.xlsx
```

台账按剩余天数排序：已过期（红）、即将到期（在提醒天数内，橙）、注意（在两倍提醒天数内，黄）、正常、长期。可以直接在 Excel 里修改到期日和存放位置，后面的命令都读取这个 Excel。

## 3. 查即将到期

```bash
python scripts/doc_tracker.py due outputs/home-docs/家庭证件台账.xlsx [--days 60]
```

## 4. 导出日历提醒

```bash
python scripts/doc_tracker.py ics outputs/home-docs/家庭证件台账.xlsx -o outputs/home-docs/到期提醒.ics
```

每项一个全天事件，日期为"到期日 − 提前提醒天数"（已进入提醒期的定在今天），当天 9 点弹出提醒。iPhone 用"文件"打开 .ics 添加到日历；安卓和电脑日历一般支持"导入"。
