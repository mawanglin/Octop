---
name: ppt-build
description: "把逐页大纲生成为风格统一的 .pptx：写 deck spec JSON → build_deck.py 生成（13 种版式、5 套主题、原生可编辑图表和表格）→ inspect_deck.py 检查溢出 → render_preview.py 渲染总览图。新建 PPT、按大纲出稿、换主题重做时使用。只依赖 python-pptx，不需要 Node 或 PowerPoint。"
metadata:
  octop:
    emoji: "🎨"
    label:
      zh: "PPT 生成"
      en: "Deck Builder"
    summary:
      zh: "按大纲生成带主题、图表和讲稿备注的 .pptx，并做溢出检查与预览。"
      en: "Build themed .pptx decks with charts and notes from an outline, then lint and preview."
---

# PPT 生成

> 所有 `scripts/`、`references/` 路径都相对于本技能目录。运行方式：`cd {本技能目录} && python scripts/...`，或用 shell 工具的 `cwd` 参数。

## 流程

1. **写 spec**：按 `references/deck-spec.md` 把大纲写成 JSON，保存为 `outputs/ppt/<名称>.json`。第一次使用先读 `references/example-deck.json` 看完整示例。
2. **生成**：
   ```bash
   python scripts/build_deck.py outputs/ppt/<名称>.json -o outputs/ppt/<名称>.pptx
   ```
   - 退出码 1 = spec 错误，按报错里的页码和字段修正后重跑。
   - 输出里的「警告」= 文字可能溢出或表格过长，必须处理（精简、拆页或换版式）后重新生成。
3. **检查**：
   ```bash
   python scripts/inspect_deck.py outputs/ppt/<名称>.pptx --issues-only
   ```
   退出码 3 表示仍有问题，修改 spec 后重来。
4. **预览**（可选，需要 LibreOffice）：
   ```bash
   python scripts/render_preview.py outputs/ppt/<名称>.pptx
   ```
   生成 `<名称>_preview/grid.png` 总览图和逐页 PNG；用读图工具查看总览图，检查对齐、留白、颜色对比和中文换行。退出码 2 表示环境没有 LibreOffice，跳过即可，并在交付时说明"未做视觉预览"。

`python scripts/build_deck.py --list-themes` 列出全部主题。

## 选版式

| 内容 | 版式 |
|------|------|
| 3–6 条并列观点 | `bullets`；只有 2–4 个且各有说明时用 `cards` |
| 两方对比、现状 vs 目标、问题 vs 方案 | `two-column` |
| 1–4 个关键数字 | `kpi` |
| 趋势、构成、对比数据 | `chart`（趋势用 line，构成用 pie/doughnut，分类对比用 column/bar） |
| 多维度明细（≤ 8 行） | `table` |
| 阶段、里程碑、路线图 | `timeline` |
| 截图、产品图、照片 | `image` |
| 章节切换（> 8 页时） | `section` |

同一版式不要连续用 3 页以上；数据页尽量配 `takeaway` 写结论。

## 主题选择

| 场景 | 主题 |
|------|------|
| 工作汇报、方案、路演（默认） | `business-blue` |
| 技术分享、产品发布 | `tech-dark` |
| 培训、教育、公益、健康 | `fresh-green` |
| 营销、活动、品牌 | `warm-orange` |
| 咨询报告、学术答辩、需要打印 | `minimal-gray` |

用户给了品牌色时，用 spec 的 `colors` 覆盖 `primary`/`secondary`/`accent`/`cover_bg`/`chart`，其余保持主题默认值。

## 写 spec 的要点

- 标题写结论句，单行能放下（≈ 24 个汉字以内）。
- 要点每条 ≤ 30 字；超过 6 条就拆页。
- 数字带单位；图表 `values` 只放数字，单位写进 `unit` 或标题。
- 讲稿写进 `notes`：每页 2–4 句口语化说明，用户要求"带讲稿"时必须写。
- 缺失的数据写成"〔待补充：xx〕"，不要编造。

## 限制

- 不支持动画、切换效果、嵌入视频和自定义母版；需要时说明，并建议用户在 PowerPoint/WPS 里补。
- 文字溢出检查是估算；有 LibreOffice 时以预览图为准。
- 默认中文字体为「微软雅黑」，未安装该字体的电脑会自动替换为本机中文字体。
