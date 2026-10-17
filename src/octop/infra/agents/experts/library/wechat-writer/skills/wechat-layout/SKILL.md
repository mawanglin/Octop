---
name: wechat-layout
description: "把 Markdown 文章排成公众号可直接粘贴的 HTML（全部内联样式、3 套主题、一键复制按钮），外链自动转为文末参考链接，并统计字数、阅读时长、段落长度和标题摘要字数。文章定稿后需要排版、预览或统计时使用。"
metadata:
  octop:
    emoji: "🎨"
    label:
      zh: "公众号排版"
      en: "WeChat Layout"
    summary:
      zh: "生成复制即用的公众号排版和字数统计。"
      en: "Generate paste-ready WeChat layouts and word counts."
---

# 公众号排版

> `scripts/wechat_layout.py` 相对于本技能目录；示例：`references/example-article.md`。

```bash
# 生成预览页（浏览器打开 → 点「复制正文」→ 到公众号编辑器粘贴）
python scripts/wechat_layout.py outputs/wechat/<标题>.md -o outputs/wechat/<标题>.html --theme green

# 只看统计：字数、预计阅读、段落数、最长段落、配图数、标题和摘要字数
python scripts/wechat_layout.py outputs/wechat/<标题>.md --stats

# 只要正文 HTML 片段（给其他工具使用）
python scripts/wechat_layout.py outputs/wechat/<标题>.md -o body.html --fragment
```

主题：`green` 清新绿（默认）、`blue` 商务蓝、`orange` 活力橙；按账号档案选择。

## Markdown 约定

```markdown
---
标题: 用 AI 写周报，我每周省下 2 小时
作者: 示例作者
摘要: 一套可直接复用的周报提示词和流程。
---
正文段落（每个非空行是一个段落）

## 小标题（左侧色条）
### 三级小标题
- 列表（转成带悬挂缩进的段落，编辑器兼容更好）
> 引用（浅色卡片）
| 表格 | 支持 |
![图注](图片地址)
**加粗**（主题色）、==高亮==、`代码`、[链接文字](https://…)
---（分割线）
```

## 交付说明（告诉用户）

1. 用浏览器打开生成的 `.html`，点顶部「复制正文」，到公众号后台编辑器里粘贴。
2. 标题、作者、摘要在公众号后台对应栏位单独填写（预览页顶部已显示）。
3. 本地图片无法随复制带过去；粘贴后检查每张图是否显示，未显示的在编辑器里重新上传。
4. 公众号正文的外链不可点击，已自动转成文末"参考链接"；公众号文章链接（mp.weixin.qq.com）会保留为可点击链接。
5. 预览页顶部的红色提示（标题超长、段落过长等）需要先处理。

需要自动发布时，把 Markdown 源稿交给「发文官」专家。
