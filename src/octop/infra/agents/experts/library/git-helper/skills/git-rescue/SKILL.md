---
name: git-rescue
description: "Git 救援与规范：动手前的备份（备份分支、stash），用 reflog 找回丢失的提交和误删的分支，撤销提交（reset --soft/--mixed/--hard 的区别、已推送用 revert），改最近一次提交说明，提交到了错误的分支，合并冲突的处理流程，推送被拒（non-fast-forward、权限、大文件），误提交密钥或大文件后清理历史（git filter-repo / BFG，并先作废密钥），.gitignore 不生效，分支模型（GitHub Flow、Git Flow、主干开发）选择。Git 出问题需要恢复、或要定分支规范时使用。"
metadata:
  octop:
    emoji: "🛟"
    label:
      zh: "Git 救援"
      en: "Git Rescue"
    summary:
      zh: "误操作恢复、冲突处理和分支规范。"
      en: "Recover from mistakes, resolve conflicts, set conventions."
---

# Git 救援与规范

## 0. 动手前先备份

```bash
git status                     # 看清现场
git branch backup/$(date +%Y%m%d-%H%M)   # 给当前位置建备份分支（Windows PowerShell 直接写日期）
git stash push -u -m "救援前备份"        # 有未提交改动时
```

`git reflog` 记录了 HEAD 的每一次移动，默认保留 90 天，绝大多数"丢了"的提交都能从这里找回。

## 1. 常见场景

| 场景 | 安全做法 |
|------|----------|
| 提交说明写错（未推送） | `git commit --amend` |
| 撤销最近一次提交，保留改动 | `git reset --soft HEAD~1` |
| 已推送的提交要撤销 | `git revert <提交>`（生成反向提交，不改历史） |
| 提交到了错误的分支 | 在正确分支 `git cherry-pick <提交>`，再回错误分支 `git reset --soft HEAD~1` |
| reset --hard 后后悔了 | `git reflog` 找到之前的位置，`git reset --hard <位置>` 或 `git branch 找回 <位置>` |
| 误删分支 | `git reflog` 找到分支最后的提交，`git branch 分支名 <提交>` |
| 本地改乱了想丢弃 | 先 `git stash -u` 留底，确认不要后再 `git stash drop` |

## 2. 合并冲突

1. `git status` 列出冲突文件；
2. 打开文件，`<<<<<<<` 到 `=======` 是当前分支，`=======` 到 `>>>>>>>` 是合入的分支；
3. 按业务含义保留或合并两边内容，删除标记；
4. 跑测试，`git add` 冲突文件，`git commit`（rebase 时是 `git rebase --continue`）；
5. 想放弃：`git merge --abort` / `git rebase --abort`。

## 3. 推送被拒

- `non-fast-forward`：远程有你没有的提交，先 `git pull --rebase` 再推；不要直接 `--force`。确需强推用 `git push --force-with-lease`，它会在别人推过新提交时拒绝。
- 权限不足：检查远程地址和凭证；受保护分支需要走合并请求。
- 文件过大：GitHub 单文件超过 100MB 会被拒，改用 Git LFS，并从历史中移除大文件。

## 4. 误提交密钥或大文件

1. **先作废密钥**：到对应平台重新生成，旧的立即失效——只删历史不换密钥没有用；
2. 用 `git filter-repo --path 文件 --invert-paths` 或 BFG 清理历史；
3. 通知协作者重新克隆；涉及公开仓库时假定密钥已经泄露。

## 5. .gitignore 不生效

已经被跟踪的文件不受 .gitignore 影响：`git rm --cached 文件` 后再提交。

## 6. 分支模型怎么选

| 模型 | 适合 | 要点 |
|------|------|------|
| GitHub Flow | 小团队、持续部署 | main 永远可发布，功能分支 → 合并请求 → 合入 main |
| Git Flow | 有版本节奏的产品 | develop 日常集成，release 分支冻结发版，hotfix 修线上 |
| 主干开发 | 有完善自动化测试 | 小步提交直接进主干，用功能开关控制未完成功能 |
