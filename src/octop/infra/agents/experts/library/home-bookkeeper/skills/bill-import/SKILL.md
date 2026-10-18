---
name: bill-import
description: "账单导入与收支报告：ledger.py 读取支付宝、微信、银行导出的 CSV/Excel，自动识别表头和编码，跳过不计收支和已关闭的交易，去重、自动分类（可加自定义规则），生成统一账本；report 生成月度汇总、分类×月份、Top 商户、疑似订阅、大额支出、预算对比，带图表。用户发来账单或要看收支时使用。"
metadata:
  octop:
    emoji: "🧾"
    label:
      zh: "账单导入"
      en: "Bill Import"
    summary:
      zh: "合并支付宝、微信、银行账单，生成账本和收支报告。"
      en: "Merge Alipay, WeChat and bank statements into a ledger and report."
---

# 账单导入

> `scripts/` 和 `references/` 路径相对于本技能目录。示例（虚构数据）：`references/example-alipay.csv`、`references/example-wechat.csv`、`references/example-rules.csv`、`references/example-budget.csv`。

## 1. 账单怎么导出

| 来源 | 导出路径（以 App 当前版本为准） | 文件 |
|------|------|------|
| 支付宝 | 我的 → 账单 → 右上角 ··· → 开具交易流水证明 → 用于个人对账 | CSV（GBK 编码，表头前有说明行） |
| 微信 | 我 → 服务 → 钱包 → 账单 → 常见问题 → 下载账单 → 用于个人对账 | Excel 或 CSV |
| 银行 | 网银或手机银行的「交易明细 → 导出」 | Excel 或 CSV |

文件放到 `inbound/`；压缩包有密码时请用户先解压。

## 2. 导入

```bash
python scripts/ledger.py import inbound/支付宝.csv inbound/微信.xlsx -o outputs/ledger/账本.xlsx
python scripts/ledger.py import inbound/10月.csv -o outputs/ledger/账本.xlsx --merge outputs/ledger/账本.xlsx --rules outputs/ledger/分类规则.csv
```

- 自动识别表头（交易时间、收/支、金额、收入/支出、交易对方、商品说明、交易状态、订单号等写法）和编码（UTF-8 / GBK）。
- 跳过「不计收支」、交易关闭、失败、退款中、已全额退款的记录。
- 去重：同一来源的同一订单号只记一次；没有订单号时按时间 + 金额 + 对方 + 收支去重。
- 分类：先匹配 `--rules`（两列：`关键词,类别`），再匹配内置关键词（餐饮、买菜、交通、购物、居住、通讯、娱乐、医疗、教育、运动、保险、个人护理等）；转账、红包、理财、退款、报销、工资单独归类，**不计入消费**。
- 账本列：日期、时间、来源、收支、金额、类别、对方、说明、支付方式、订单号。用户可以直接在 Excel 里改类别，下次 `--merge` 时保留。

## 3. 收支报告

```bash
python scripts/ledger.py report outputs/ledger/账本.xlsx -o outputs/ledger/收支报告.xlsx [--budget outputs/ledger/预算.csv] [--month 2026-09]
```

输出工作表：月度汇总（收入、消费支出、结余、储蓄率，带柱形图）、分类×月份（带饼图）、Top 商户、疑似订阅（同一对方、同一金额连续 3 个月以上，且像会员/话费/健身等订阅）、大额支出（超过该类中位数 5 倍且不低于 200 元）、预算对比（`--budget` 两列：`类别,月预算`）。

脚本在终端打印关键数字，回复用户时引用这些数字。

## 4. 常见问题

- **「其他」太多**：按对方汇总「其他」类，请用户确认后写进规则文件重新导入。
- **信用卡还款重复**：银行卡的「信用卡还款」和信用卡账单里的消费是同一笔钱，建议只导入信用卡消费明细，或把还款规则设为「转账」。
- **表头识别失败**：脚本会提示找不到哪一列；请用户确认文件是否为原始导出文件。
