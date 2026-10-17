# Deck spec 格式

`build_deck.py` 的输入是一个 JSON 文件。完整示例见同目录 `example-deck.json`（覆盖全部版式）。

## 顶层字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `title` | 否 | 文档属性标题 |
| `theme` | 否 | `business-blue`（默认）/ `tech-dark` / `fresh-green` / `warm-orange` / `minimal-gray` |
| `size` | 否 | `16:9`（默认）或 `4:3` |
| `footer` | 否 | 每个内容页左下角的页脚文字 |
| `font` | 否 | `{"latin": "Arial", "ea": "Microsoft YaHei"}`，`ea` 为中文字体 |
| `colors` | 否 | 覆盖主题色，如 `{"primary": "#C8102E", "chart": ["#C8102E", "#333333"]}`；可用键：`bg surface text muted primary secondary accent cover_bg cover_text cover_muted chart` |
| `slides` | 是 | 页面数组，见下 |

每页都可以带 `notes`（演讲者备注）。正文类版式（bullets / two-column / cards / kpi / chart / table / timeline / image）都可以带 `takeaway`：页底强调条，写这一页的结论。

## 版式

| layout | 必填字段 | 可选字段 | 适用 |
|--------|----------|----------|------|
| `cover` | `title` | `subtitle`, `meta` | 封面 |
| `agenda` | `items`（字符串数组） | `title`（默认"目录"） | 目录，>5 项自动两栏 |
| `section` | `title` | `index`（如 "01"）, `subtitle` | 章节过渡页 |
| `bullets` | `title`, `bullets` | `takeaway` | 要点列表；`bullets` 项可以是字符串或 `{"text": "...", "level": 1}`（最多 2 级缩进） |
| `two-column` | `title`, `left`, `right` | `takeaway` | 对比、问题/方案；`left`/`right` = `{"heading": "...", "bullets": [...]}` |
| `cards` | `title`, `cards`（2–4 张） | `takeaway` | 并列要点；卡片 = `{"title", "body", "icon"}`，`icon` 用短编号或 emoji |
| `kpi` | `title`, `metrics`（1–4 个） | `takeaway` | 关键数字；指标 = `{"value", "label", "note"}` |
| `chart` | `title`, `chart` | `caption`, `takeaway` | 原生可编辑图表，见下 |
| `table` | `title`, `columns`, `rows` | `caption`, `takeaway` | 表格；每行列数必须等于表头 |
| `timeline` | `title`, `steps`（2–6 个） | `takeaway` | 里程碑/阶段；节点 = `{"label", "title", "body"}` |
| `image` | `title`, `image` | `caption`, `takeaway` | 图片（等比缩放居中）；路径相对 spec 文件 |
| `quote` | `quote` | `author` | 金句、客户原话 |
| `closing` | — | `title`（默认"谢谢"）, `subtitle`, `contact` | 结束页 |

### chart

```json
{
  "type": "column",
  "categories": ["Q1", "Q2", "Q3"],
  "series": [{"name": "营收", "values": [120, 150, 180]}],
  "unit": "万"
}
```

`type`：`column`、`stacked-column`、`bar`、`line`、`pie`、`doughnut`。饼图/环形图只用第一个系列，自动显示百分比；单系列柱/条/线图自动显示数值，`unit` 会附在数值后。

## 错误与警告

- spec 错误（缺字段、列数不符、图片不存在）以退出码 1 结束，并给出页码和字段名，按提示修改后重跑。
- 警告（某页文字在最小字号下仍可能溢出、表格行数过多）不阻止生成，但交付前应处理：精简文字、拆页或换版式。
