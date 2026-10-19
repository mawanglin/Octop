---
name: git-report
description: "Git 仓库报告：git_report.py stats 统计时间范围内的提交数、作者提交和增删行、按月分布、提交类型分布、改动最频繁的文件；changelog 按 Conventional Commits（feat/fix/perf/refactor/docs/test/build/ci/chore，支持 scope 和 !）把两个版本之间的提交分组为新增/修复/性能/重构/文档/测试/构建与 CI/其他，单列破坏性变更；branches 列出本地和远程分支的最后提交、是否已合并到 main/master/develop，标出长期未动的分支并给出清理命令建议；staged 列出已暂存文件的改动类型和增删行，建议提交类型。只读，需要本机安装 git。写提交说明、整理更新日志、统计和清理分支时使用。"
metadata:
  octop:
    emoji: "🌿"
    label:
      zh: "Git 报告"
      en: "Git Report"
    summary:
      zh: "提交统计、更新日志、分支清理和提交说明。"
      en: "Stats, changelogs, branch cleanup and commit messages."
---

# Git 报告

> `scripts/` 路径相对于本技能目录。只读取仓库，不做任何修改；`--repo` 指定仓库目录（默认当前目录）。

## 1. 提交说明

```bash
python scripts/git_report.py --repo 项目目录 staged
```

格式（Conventional Commits，可以用中文）：

```text
fix(login): 修复验证码过期后仍可登录的问题

验证码过期时间比较用了本地时区，改为统一用 UTC。
影响：所有使用短信验证码登录的用户。
Closes #123
```

类型：feat 新功能、fix 修复、perf 性能、refactor 重构、docs 文档、test 测试、build 构建、ci 持续集成、chore 杂项。不兼容的改动在类型后加 `!`，或在正文写 `BREAKING CHANGE:`。

## 2. 更新日志

```bash
python scripts/git_report.py --repo 项目目录 changelog --from v1.0.0 [--to HEAD] -o outputs/git/更新日志.md
```

按类型分组，破坏性变更单独置顶，保留短哈希和 `(#123)` 编号。没按规范写的提交归入“其他”，发版前改写成用户能看懂的描述。

## 3. 统计

```bash
python scripts/git_report.py --repo 项目目录 stats --since 2026-01-01 [--until 2026-06-30]
```

不含合并提交。改动最频繁的文件通常是热点或耦合点，适合重点评审和补测试。统计只反映提交行为，不要用来评价个人绩效。

## 4. 分支清理

```bash
python scripts/git_report.py --repo 项目目录 branches --days 90 [--base main]
```

列出所有分支的最后提交日期、作者、是否已合并。已合并的本地分支给出 `git branch -d` 命令（-d 会拒绝删除未合并分支，是安全的）；未合并但长期未动的分支只列出，由用户确认是否还需要。
