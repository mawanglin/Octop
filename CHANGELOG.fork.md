# Fork Changelog

本文件只记录 fork（mawanglin/Octop）相对官方 [TencentCloud/Octop](https://github.com/TencentCloud/Octop) 的改动，官方改动见 `CHANGELOG.md`。

版本号规则：`<官方版本>.postN`，例如基于官方 1.0.2b9 的第 1 个 fork 版本是 `1.0.2b9.post1`。打 `v<版本号>` 标签后，`.github/workflows/fork-release.yml` 会构建 wheel 和飞牛原生版 FPK，并发布到 GitHub Release；本文件中同名版本小节会作为 Release 说明。

## [1.0.2b9.post1] - 2026-10-17

基于官方 develop（1.0.2b9 之后）。

### 新增
- 「PPT 设计专家」模板：先策划故事线和逐页大纲，再生成风格统一的 .pptx（5 套主题、13 种版式、原生可编辑图表与表格、讲稿备注），自动检查文字溢出；也能读取并修改已有 PPT。
- 「流程图设计专家」模板：把流程描述、制度文档或代码逻辑画成流程图、泳道图、时序图、状态图、思维导图、甘特图，校验语法并导出 PNG / SVG / PDF；还能生成可在 draw.io 中编辑的 .drawio 文件。

### 发布
- 新增 fork 专用发布流水线：wheel + sdist + 飞牛原生版 FPK（x86_64 / arm64）。
- 飞牛商店版本编码支持 `.postN`（如 1.0.2b9.post1 → 1.0.2091）。
