---
name: html-check
description: "网页检查：html_check.py 用无头 Chromium 打开本地 HTML 文件或网址，收集脚本报错、console.error、加载失败或返回 4xx/5xx 的资源；检查手机宽度下是否出现横向滚动条、是否缺少 viewport meta 和 title、图片 alt、输入框是否有 label、是否通过 http:// 加载外部资源，列出外部脚本；按 desktop（1280×800）、tablet（820×1180）、mobile（390×844）整页截图。需要 playwright 和 Chromium。每次生成或修改网页后、交付前使用。"
metadata:
  octop:
    emoji: "🖥️"
    label:
      zh: "网页检查"
      en: "HTML Check"
    summary:
      zh: "报错、资源、手机适配检查和多尺寸截图。"
      en: "Errors, resources, mobile fit and multi-size screenshots."
---

# 网页检查

> `scripts/` 和 `references/` 路径相对于本技能目录；示例小工具：`references/example-tool.html`（待办清单，单文件、深色模式、本地存储、导出）。

## 1. 运行

```bash
python scripts/html_check.py outputs/web/工具名.html -o outputs/web/截图 [--viewports desktop,mobile] [--wait 500]
python scripts/html_check.py http://127.0.0.1:8080/
```

- `--viewports` 可选 desktop、tablet、mobile；
- `--wait` 页面加载后再等待的毫秒数，页面有异步渲染时调大；
- 有错误时退出码为 3。

## 2. 结果怎么处理

| 提示 | 处理 |
|------|------|
| 脚本报错 | 按报错信息修复；常见是变量未定义、元素还没渲染就去获取（把脚本放在 body 末尾或用 DOMContentLoaded） |
| 资源加载失败 | 检查相对路径和文件名大小写；CDN 地址固定版本 |
| 手机横向滚动 | 去掉固定宽度（width: 900px → max-width），长文本加 `overflow-wrap: anywhere`，表格外包一层可横向滚动的容器 |
| 缺少 viewport | 在 head 里加 `<meta name="viewport" content="width=device-width, initial-scale=1">` |
| 图片缺 alt、输入框缺 label | 补 alt 文字；输入框用 `<label for>` 或 `aria-label` |
| http:// 资源 | 改成 https:// 或下载到本地 |

## 3. 看截图

检查完一定要打开截图看：文字是否被截断、按钮是否太小（手机上至少 44×44 像素）、深色模式下文字是否看得清。需要检查深色模式时，在系统切换为深色后再截图，或在页面里临时加 `data-theme="dark"` 测试。

需要先安装：`pip install playwright && playwright install chromium`。
