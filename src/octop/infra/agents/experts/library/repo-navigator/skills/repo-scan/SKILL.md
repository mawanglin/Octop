---
name: repo-scan
description: "代码仓库扫描：repo_scan.py scan 统计各语言文件数、代码行、注释行、空行，列出最大的文件、TODO/FIXME 数量，解析 package.json、pyproject.toml、requirements、go.mod、Cargo.toml、pom.xml、composer.json 的依赖和脚本，识别入口文件、常用框架、测试文件和 CI 配置；tree 输出带文件数的目录树；graph 用 ast 解析 Python import、解析 JS/TS 相对路径 import/require，按目录层级汇总成 Mermaid 依赖图并找出相互引用的模块。自动跳过 .git、node_modules、虚拟环境和构建产物。接手或评估一个代码仓库时首先使用。"
metadata:
  octop:
    emoji: "🔭"
    label:
      zh: "仓库扫描"
      en: "Repo Scan"
    summary:
      zh: "代码量、依赖、入口、框架和模块依赖图。"
      en: "Size, dependencies, entry points and module graphs."
---

# 仓库扫描

> `scripts/` 路径相对于本技能目录。只读，不修改仓库。

## 1. 全貌

```bash
python scripts/repo_scan.py scan 项目目录 [--top 15] [--json]
```

输出：文件总数和代码行、各语言统计、框架和主要库、入口和构建文件（main.py、manage.py、index.ts、main.go、Dockerfile、Makefile 等）、测试文件数、CI 配置、README / LICENSE、TODO/FIXME 数量、代码行最多的文件、每个依赖清单的依赖和脚本。

解读要点：
- 代码行最多的文件往往是核心或"上帝文件"，阅读和重构都从这里开始关注；
- 测试文件为 0 或 CI 缺失，说明改动风险高，提醒用户；
- `package.json` 的 scripts、`pyproject.toml` 的 scripts、`Makefile` 是最快的"怎么运行"线索。

## 2. 目录树

```bash
python scripts/repo_scan.py tree 项目目录 --depth 2
```

每个目录后标出文件数，单层文件多于 8 个时折叠。

## 3. 模块依赖图

```bash
python scripts/repo_scan.py graph 项目目录 [--lang python|js] [--depth 2] [--max-nodes 40] -o outputs/repo/模块关系.mmd
```

- Python：解析 import（含相对导入）；目录本身是包时会自动补全上层包名。
- JS / TS：解析 `import … from './x'`、`require('./x')`、`import('./x')` 的相对路径。
- `--depth` 控制汇总层级（2 = `pkg.sub`）；节点太多时用 `--max-nodes` 只保留引用最多的模块。
- 输出"被引用最多"的核心模块和"相互引用"的模块对（可能存在循环依赖）。
- 生成的是 Mermaid 文本，可以直接贴进支持 Mermaid 的文档，或交给「流程图设计专家」导出图片。
