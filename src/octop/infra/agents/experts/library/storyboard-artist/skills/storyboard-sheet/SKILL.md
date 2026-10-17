---
name: storyboard-sheet
description: "生成拍摄现场用的 Excel 分镜表：storyboard_xlsx.py 把 Markdown 分镜表转成带表头样式、累计时长公式、按场景分色的分镜表，以及场景汇总和按场景集中的拍摄顺序表；可追加 AI 绘图提示词列。拆完镜头需要出表、给摄影组或要 AI 出分镜草图时使用。"
metadata:
  octop:
    emoji: "📋"
    label:
      zh: "分镜表"
      en: "Storyboard Sheet"
    summary:
      zh: "生成分镜表 Excel、场景汇总和拍摄顺序。"
      en: "Export storyboard sheets with scene summary and shooting order."
---

# 分镜表 Excel

> `scripts/storyboard_xlsx.py` 相对于本技能目录；示例：`references/example-storyboard.md`。

```bash
python scripts/storyboard_xlsx.py outputs/storyboard/<项目>.md -o outputs/storyboard/<项目>.xlsx [--prompts]
```

## Markdown 格式

```markdown
---
项目: 3 个提示词写周报（抖音口播）
版本: v1
画幅: 9:16
风格: 明亮办公室，自然光，写实
---
| 镜号 | 场景 | 景别 | 运镜 | 画面 | 台词/旁白 | 字幕 | 音效/音乐 | 时长 | 道具 | 备注 |
|------|------|------|------|------|-----------|------|-----------|------|------|------|
| 1 | 工位 | 特写 | 固定 | 电脑屏幕上空白的周报文档 | 周报写了一小时还是一片空白？ | 周报写不出来？ | 键盘声 | 3 | 笔记本电脑 | 钩子 |
```

- 必须有「镜号」「画面」两列，其余列可按需要删减；列名用上面的写法才能被识别。
- 时长写秒数（3、3s、0:03 都可以）。
- 景别、运镜使用 `shot-design` 技能 references 中的术语，脚本会提示不常见的写法。

## 生成的 Excel

| 工作表 | 内容 |
|--------|------|
| 分镜表 | 深色表头、冻结首列和表头、自动换行、按场景交替底色、「累计」列为公式、合计行；打印设置为 A4 横向适应页宽 |
| 场景汇总 | 每个场景的镜头数、总时长、镜号列表——用于排期和报价 |
| 拍摄顺序 | 按场景集中排列的镜头顺序——同一场景一次拍完，减少转场和布光 |

`--prompts` 追加「AI 绘图提示词」列：由画面、景别（中英文）、场景、风格、画幅组合而成，可直接粘贴到即梦、可灵、Midjourney 等工具生成分镜草图或 AI 视频素材。生成结果需要人工挑选；涉及真人肖像和品牌标识时注意授权。

脚本输出的「提示」（景别/运镜写法、单镜头过长、时长无法识别）要逐条处理后重新生成。
