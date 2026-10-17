---
name: drawio-diagram
description: "从 JSON 流程描述生成可编辑的 draw.io（diagrams.net）文件：自动分层布局、泳道、标准流程图形状和配色、回退线绕行，并可同时输出等价的 Mermaid 源码。用户要能二次编辑的流程图、泳道图、.drawio 文件，或要导入 Confluence/飞书/语雀等支持 draw.io 的工具时使用。"
metadata:
  octop:
    emoji: "📐"
    label:
      zh: "draw.io 文件"
      en: "draw.io Files"
    summary:
      zh: "生成可在 draw.io 中继续编辑的流程图和泳道图。"
      en: "Generate editable draw.io flowcharts and swimlane diagrams."
---

# draw.io 可编辑流程图

> `scripts/`、`references/` 路径相对于本技能目录。完整示例：`references/example-flow.json`（三泳道报销流程）。

## 用法

```bash
python scripts/drawio_from_spec.py outputs/diagrams/报销流程.json \
  -o outputs/diagrams/报销流程.drawio \
  --mermaid outputs/diagrams/报销流程.mmd
```

- `.drawio` 可用 draw.io 桌面版、https://app.diagrams.net 、VS Code 插件，以及 Confluence/飞书/语雀等支持 draw.io 的工具打开编辑。
- 加 `--mermaid` 会同时生成等价的 Mermaid 源码，可再交给 `diagram-export` 导出 PNG 预览（建议导出后用读图工具检查一遍）。
- 退出码 1 = spec 错误（重复 id、连线指向不存在的节点、泳道不存在等），按提示修正。

## Spec 格式

```json
{
  "title": "报销流程",
  "direction": "LR",
  "lanes": [{"id": "emp", "label": "员工"}, {"id": "fin", "label": "财务"}],
  "nodes": [
    {"id": "start", "label": "开始", "type": "start", "lane": "emp"},
    {"id": "check", "label": "票据齐全？", "type": "decision", "lane": "fin"}
  ],
  "edges": [
    {"from": "start", "to": "check"},
    {"from": "check", "to": "start", "label": "否，退回", "dashed": true}
  ]
}
```

| 字段 | 说明 |
|------|------|
| `direction` | `TB` 上→下（默认）或 `LR` 左→右；泳道图推荐 `LR` |
| `lanes` | 可选；有泳道时每个节点都必须写 `lane` |
| `nodes[].type` | `start` 开始、`end` 结束、`process` 步骤（默认）、`decision` 判断、`io` 输入输出、`document` 文档、`database` 数据/系统、`subprocess` 子流程、`note` 备注 |
| `nodes[].label` | 节点文字，可用 `\n` 换行 |
| `edges[].label` | 连线文字（判断出口必须写） |
| `edges[].dashed` | 虚线，用于回退、异常、可选路径 |

## 布局规则（自动）

- 按最长路径分层，主流程沿 `direction` 方向展开；同层多个节点并排。
- 指向前面步骤的回退线自动从外侧绕行（TB 走右侧，LR 走下方）。
- 节点按类型使用标准配色：开始绿、结束红、步骤蓝、判断黄、输入输出紫、数据库灰。

自动布局适合 ≤ 25 个节点的图；更复杂的图建议拆分，或交付后提示用户在 draw.io 中用「排列 → 布局」微调。

## 与 Mermaid 的分工

| 需求 | 用哪个 |
|------|--------|
| 快速看图、对话里展示、发 IM 图片 | `mermaid-diagram` + `diagram-export` |
| 用户要自己拖拽修改、团队协作维护 | 本技能（`.drawio`） |
| 两者都要 | 先写本技能的 spec，`--mermaid` 一次生成两份 |
