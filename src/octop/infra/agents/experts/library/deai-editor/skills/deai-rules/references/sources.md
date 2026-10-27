# 来源与致谢

本专家的去 AI 味规则参考了以下开源项目，按各自 MIT 许可证使用：规则用我们自己的话重写并重新组织，示例为新写，频率数据注明出处。

| 项目 | 作者 | 借鉴内容 |
|------|------|----------|
| [qu-ai-wei](https://github.com/baibanbao/qu-ai-wei) | 王佩（baibanbao） | 合并三家规则的整体框架、两种改稿模式、三个病根、规则冲突的裁决思路、分文体加戏位置、交付前核对 |
| [lieflat-less-ai-tone](https://github.com/larashero3-dotcom/lieflat-less-ai-tone) | shiujan | 中文 AI 写作特征的语料实测（AI 300 篇、人类 329 篇）、收录门槛、各规则的人机频率、“实测不是 AI 痕迹”的清单、检测方法（分句、分母、同构指纹） |
| [Humanizer-zh](https://github.com/op7418/Humanizer-zh) | 歸藏 | 信息守恒、保留边界、交付前核对 |
| [humanizer](https://github.com/blader/humanizer) | Siqi Chen | 英文 AI 写作模式分类（基于维基百科 WikiProject AI Cleanup 的 *Signs of AI writing*） |
| [stop-slop](https://github.com/hardikpandya/stop-slop) | Hardik Pandya | 英文去套话的补充规则 |

`ai_tone_check.py` 中的人类 / AI 均值引用自 lieflat-less-ai-tone 的 RESEARCH.md。该研究的语料未公开，数字无法第三方复核；频率只说明写法差异，不能证明作者身份。

## 许可声明

上述项目均为 MIT License，版权分别归：

- Copyright (c) 2026 王佩 (baibanbao)
- Copyright (c) 2026 shiujan
- Copyright (c) 2026 歸藏
- Copyright (c) 2025 Siqi Chen
- Copyright (c) 2025 Hardik Pandya

MIT License 全文：

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
