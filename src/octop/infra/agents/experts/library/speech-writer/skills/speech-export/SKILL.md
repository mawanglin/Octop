---
name: speech-export
description: "讲话稿时长估算和照读版导出：speech_timer.py 按语速估算总时长和分段时长、提示需要增删的字数；docx_build.py --style speech 导出仿宋小二大字号、1.8 倍行距、称呼顶格的照读版 Word。成稿后核对时长或要打印照读时使用。"
metadata:
  octop:
    emoji: "⏱️"
    label:
      zh: "时长与照读版"
      en: "Timing & Print"
    summary:
      zh: "估算讲话时长，导出大字号照读版 Word。"
      en: "Estimate speaking time and export large-print Word."
---

# 时长估算与照读版

> `scripts/` 路径相对于本技能目录。

## 1. 估算时长

```bash
python scripts/speech_timer.py outputs/speech/<标题>.md --target 10 [--rate 220]
```

- 按 `##` 小标题分段统计字数和时长；`# 标题` 不计入。
- `--rate` 每分钟字数：正式讲话 200–230，致辞/主持 230–250，演讲比赛 250–280；讲话人有偏好时按偏好设置。
- `--target` 目标分钟数，输出需要增加或删减的大致字数；偏差在 5% 内视为吻合。
- 数字按读音估算（"2026"约 4 个字）；实际时长还受停顿、掌声影响，重要场合建议预留 10% 余量。

## 2. 导出照读版 Word

```bash
python scripts/docx_build.py outputs/speech/<标题>.md -o outputs/speech/<标题>.docx --style speech
```

版式：A4，四边 25mm；标题 26 磅方正小标宋；正文仿宋_GB2312 小二（18 磅）、1.8 倍行距、首行缩进二字；"同志们：""尊敬的各位来宾："这类称呼行自动顶格；"一、""（一）"等层次序号自动使用黑体、楷体；页码居中。

- 每个非空行是一个段落；`<!-- pagebreak -->` 单独一行分页（如把结束语放到新的一页）。
- 讲话人要求更大字号或其他字体时：`--fonts '{"body": "黑体"}'`；字号目前固定，需要调整时告诉用户在 Word 中全选修改。
- 以正式文件印发的讲话（"在……会议上的讲话"作为文件印发）改用 `--style gov`，或交给「政务公文专家」。

## 3. 要点提词卡（可选）

用户需要脱稿时，在对话中额外给出提词卡：每个部分一行观点句 + 3–5 个关键词 + 必须准确念出的数字和人名。
