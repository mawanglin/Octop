---
name: english-humanize
description: "英文去 AI 味：英文 AI 写作的常见模式（not just X but Y、单句金句收尾、戏剧化铺垫、强行三连、句首重复、em dash 滥用、限定词叠加、delve/tapestry/testament 等高频词、意义拔高、-ing 尾巴、销售腔、借来的权威、装饰性粗体和标题、聊天残留、知识截止声明）及改法，什么时候不该改。处理英文稿或中英混排稿时使用，scan 会自动对英文为主的文稿用英文规则。"
metadata:
  octop:
    emoji: "🔤"
    label:
      zh: "英文去味"
      en: "English Humanize"
    summary:
      zh: "英文 AI 写作模式和改法。"
      en: "English AI-writing patterns and fixes."
---

# English: remove AI writing patterns

> Adapted from blader/humanizer (MIT) and Wikipedia's *Signs of AI writing* (WikiProject AI Cleanup). Same hard limits as the Chinese rules: never add facts, names, numbers or quotes; keep claims, hedges and structure.

## 1. Patterns and fixes

| Group | Pattern | Fix |
|-------|---------|-----|
| Staging | "It's not X, it's Y" / "not just X but Y" | State Y directly |
| Staging | One-line dramatic closers, fortune-cookie sayings | Cut; end on a concrete point |
| Staging | Run-ups: "Here's the thing", "Let's dive in", "Let's break it down" | Start with the point |
| Rhythm | Forced triads ("fast, simple, and powerful") | Keep only the items that carry information |
| Rhythm | Several sentences opening the same way | Vary or merge |
| Rhythm | Em dashes as the universal connector | Comma, period or parentheses |
| Rhythm | Stacked qualifiers ("may potentially", "arguably somewhat") | One qualifier, same strength as the source |
| Inflation | delve, tapestry, testament, pivotal, crucial, landscape, realm, seamless, robust, leverage, foster, underscore, showcase, vibrant, meticulous, unlock | Plain word |
| Inflation | "stands as", "serves as a testament", "plays a pivotal role", "marks a significant shift" | Say what it does |
| Inflation | Trailing -ing clauses ("..., highlighting the importance of...") | Cut or make a separate claim |
| Inflation | Sales language ("cutting-edge", "game-changer") | Describe the feature |
| Inflation | Borrowed authority ("experts say", "studies show") without a source | Keep it vague if the source is vague — never invent the source |
| Formatting | Decorative bold, headings on every paragraph, emoji bullets | Remove |
| Residue | "I hope this helps", "Great question!", "As an AI", knowledge-cutoff notes | Delete |
| Residue | First sentence repeating the heading; writing about the document ("This section explores") | Cut |

## 2. When not to act

- Technical terms ("robust statistics", "landscape mode") are not tells;
- Passive voice, long sentences and lists are normal in many genres;
- Quotes, code, URLs and data stay untouched;
- Short replies rarely have enough signal — don't rewrite for the sake of it.

`ai_tone_check.py scan` reports E1–E7 for English-dominant text; E7 (triads) is only a prompt to check.
