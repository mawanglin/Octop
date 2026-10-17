---
name: contract-annotate
description: "把审阅意见写回合同：review_docx.py extract 导出带段落编号的合同全文；annotate 根据审阅意见表在合同副本上逐条添加 Word 批注（精确标在原文片段上，不改合同正文），并可输出按风险等级排序的风险清单 Excel。需要批注版合同、风险清单时使用。"
metadata:
  octop:
    emoji: "🖊️"
    label:
      zh: "合同批注"
      en: "Contract Comments"
    summary:
      zh: "在合同副本上逐条加批注，输出风险清单。"
      en: "Add review comments to a contract copy and export a risk list."
---

# 合同批注

> `scripts/` 和 `references/` 路径相对于本技能目录；审阅意见示例：`references/example-review.md`。

## 1. 导出全文

```bash
python scripts/review_docx.py extract inbound/合同.docx
```

输出 `[P12] 段落文字` 格式的全文（包括表格中的文字），段落编号用于定位。

## 2. 写审阅意见表

保存为 `outputs/contracts/<合同名>-审阅意见.md`：

```markdown
| 段落 | 原文片段 | 风险等级 | 问题 | 修改建议 |
|------|----------|----------|------|----------|
| P5 | 合同签订后 3 日内一次性支付全部款项 | 高 | 预付全款，甲方失去付款制约 | 改为分期付款：签约付 30%，验收合格付 60%，质保期满付 10% |
```

- **原文片段**必须从 extract 输出中原样复制（10–40 字），批注会精确标在这段文字上；
- **段落**可以填写，用于加快定位和处理重复文字；
- **风险等级**：高 / 中 / 低。
- 合同缺少的条款（如没有保密条款）：在"原文片段"填最相关位置的文字（如合同标题或"其他约定"条款），在"问题"写明缺少什么，在"修改建议"写出建议补充的完整条款。

## 3. 生成批注版合同

```bash
python scripts/review_docx.py annotate inbound/合同.docx outputs/contracts/<合同名>-审阅意见.md \
  -o outputs/contracts/<合同名>-审阅版.docx --report outputs/contracts/<合同名>-风险清单.xlsx [--author 审阅人]
```

- 每条批注内容为"【高风险】问题 + 建议：修改条款"，在 Word / WPS 的审阅窗格中查看；
- 原合同不会被修改，输出路径与原合同相同时直接拒绝；
- 片段与原文的空格或标点不完全一致时，退回为整段批注并提示；完全找不到时输出"未标注"并返回退出码 3——从 extract 结果重新复制片段后重跑；
- 风险清单 Excel 按高、中、低排序，适合发给业务和法务同事讨论。

批注是审阅意见，用户确认后需要在 Word 中自行修改条款或用修订模式改写，再发给对方。
