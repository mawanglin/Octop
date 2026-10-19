---
name: web-tool-patterns
description: "单文件网页小工具写法：HTML 骨架（lang、charset、viewport、title），CSS 变量配色和 prefers-color-scheme 深色模式，移动优先的响应式布局（max-width 容器、flex/grid、16px 边距），表单和按钮的可用性（label、键盘回车提交、44px 点击区域），localStorage 读写的容错，JSON / CSV 导入导出和打印样式，数字和金额格式化（Intl.NumberFormat）、日期处理，常见小工具（计算器、换算器、抽签、倒计时、清单、简易看板）的实现要点，外部库的固定版本 CDN 用法。制作或修改网页小工具时使用。"
metadata:
  octop:
    emoji: "🧰"
    label:
      zh: "小工具写法"
      en: "Web Tool Patterns"
    summary:
      zh: "单文件结构、深色模式、本地存储和导入导出。"
      en: "Single-file structure, dark mode, storage and export."
---

# 单文件网页小工具写法

## 1. 骨架

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>工具名称</title>
<style>
  :root { --bg: #f8fafc; --card: #fff; --text: #0f172a; --muted: #64748b; --accent: #2563eb; --border: #e2e8f0; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #0f172a; --card: #1e293b; --text: #e2e8f0; --muted: #94a3b8; --accent: #60a5fa; --border: #334155; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 24px 16px; background: var(--bg); color: var(--text);
         font: 16px/1.6 system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }
  main { max-width: 640px; margin: 0 auto; }
</style>
</head>
<body>
<main>…</main>
<script>/* 逻辑放在 body 末尾 */</script>
</body>
</html>
```

完整示例见 html-check 技能的示例文件 example-tool.html。

## 2. 布局与可用性

- 移动优先：容器 `max-width` + 两侧 16px 边距，不写固定宽度；多列用 `display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr))`。
- 输入框都有 `<label>`；表单用 `<form>`，回车即可提交；按钮写清动作（"计算""导出"）。
- 手机上点击区域至少 44×44 像素；数字输入用 `inputmode="decimal"` 调出数字键盘。

## 3. 本地存储

```js
const KEY = "tool-name-v1";
const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) ?? []; } catch { return []; } };
const save = (data) => { try { localStorage.setItem(KEY, JSON.stringify(data)); } catch {} };
```

隐私模式或存储被禁用时 localStorage 可能抛错，所以读写都要 try/catch，页面在没有存储时也要能用。提醒用户：数据只存在当前浏览器，换浏览器或清缓存会丢失，重要数据用导出备份。

## 4. 导入导出和打印

```js
function download(name, text, type = "application/json") {
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([text], { type })), download: name });
  a.click(); URL.revokeObjectURL(a.href);
}
// CSV 加 BOM，Excel 打开中文不乱码
download("数据.csv", "\ufeff" + rows.map(r => r.join(",")).join("\n"), "text/csv");
```

导入用 `<input type="file" accept=".json,.csv">` + `FileReader`。打印样式用 `@media print { button { display: none; } }`。

## 5. 数字和日期

- 金额：`new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(x)`；
- 浮点误差：金额计算先转成"分"的整数再算；
- 日期：`<input type="date">` 返回 `YYYY-MM-DD` 字符串，计算天数差时用 `new Date(s + "T00:00:00")` 避免时区偏移。

## 6. 外部库

确需图表等库时，用固定版本号的 CDN，例如 `https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js`，不要用 `@latest`；告诉用户断网时该功能不可用，需要离线使用时把库文件下载到同目录。
