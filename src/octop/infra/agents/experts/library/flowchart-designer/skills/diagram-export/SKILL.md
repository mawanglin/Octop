---
name: diagram-export
description: "校验 Mermaid 语法，并用无头 Chromium 把 .mmd 导出为 PNG / SVG / PDF（中文字体、主题、透明背景、高清倍率）。需要发到 IM 渠道、插入 Word/PPT、下载图片，或在交付前检查语法时使用。"
metadata:
  octop:
    emoji: "🖼️"
    label:
      zh: "图表导出"
      en: "Diagram Export"
    summary:
      zh: "校验 Mermaid 语法并导出 PNG、SVG、PDF。"
      en: "Validate Mermaid syntax and export PNG, SVG, or PDF."
---

# 图表导出

> `scripts/render_mermaid.py` 相对于本技能目录。运行方式：`cd {本技能目录} && python scripts/...`，或用 shell 工具的 `cwd` 参数。

## 用法

```bash
# 只校验语法（交付前必做）
python scripts/render_mermaid.py outputs/diagrams/报销流程.mmd --check

# 导出 PNG（IM 渠道、Word/PPT 插图；默认 2 倍高清、白底）
python scripts/render_mermaid.py outputs/diagrams/报销流程.mmd -o outputs/diagrams/报销流程.png

# 导出 SVG（矢量，可无损缩放；已内联样式，PowerPoint/WPS 可直接插入）
python scripts/render_mermaid.py outputs/diagrams/报销流程.mmd -o outputs/diagrams/报销流程.svg

# 导出 PDF（打印、归档）
python scripts/render_mermaid.py outputs/diagrams/报销流程.mmd -o outputs/diagrams/报销流程.pdf
```

常用参数：

| 参数 | 说明 |
|------|------|
| `--theme` | `default`（默认）/ `neutral`（黑白，适合打印）/ `dark` / `forest` / `base` |
| `--bg transparent` | 透明背景（放进有底色的 PPT 时用） |
| `--scale 3` | PNG 像素倍率，默认 2 |
| `--mermaid-js 路径` | 离线环境指定本地 `mermaid.min.js` |

## 退出码

| 码 | 含义 | 处理 |
|----|------|------|
| 0 | 成功 | 把文件路径告诉用户；IM 渠道直接发送 PNG |
| 1 | Mermaid 语法错误 | 按报错的行号修正 `.mmd`（常见原因见 `mermaid-diagram` 技能的 cheatsheet），再试 |
| 2 | 渲染环境不可用 | 见下 |

## 环境说明

- 依赖 Playwright 和 Chromium。退出码 2 且提示"Chromium 未安装"时，告诉用户在 Octop **设置 → 浏览器** 中安装 Chromium（或由管理员执行 `playwright install chromium`）；在此之前，网页端直接给 ```mermaid 代码块（界面会渲染），或改用 `drawio-diagram` 生成 `.drawio` 文件。
- 第一次运行会从公共 CDN 下载 Mermaid 库（约 3 MB，之后缓存）。**只下载库文件，图的内容不会发出本机。** 无法联网时提示用户提供 `mermaid.min.js`，用 `--mermaid-js` 或环境变量 `OCTOP_MERMAID_JS` 指定。
- 中文字体使用系统中的 Noto Sans CJK / 苹方 / 微软雅黑；Docker 镜像已内置 Noto CJK。
