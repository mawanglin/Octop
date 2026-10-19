#!/usr/bin/env python3
"""Git 仓库报告：提交统计、按提交类型生成更新日志、长期未合并的分支、暂存改动概况。只读，不修改仓库。

Usage:
    python scripts/git_report.py stats [--repo .] [--since 2026-01-01] [--until 2026-12-31]
    python scripts/git_report.py changelog --from v1.0.0 [--to HEAD] [--repo .] [-o 更新日志.md]
    python scripts/git_report.py branches [--repo .] [--days 90] [--base main]
    python scripts/git_report.py staged [--repo .]

changelog：按 Conventional Commits（feat / fix / perf / refactor / docs / test / build / ci / chore，可带 scope 和 !）
           分组为 新增 / 修复 / 性能 / 重构 / 文档 / 测试 / 构建与 CI / 其他，单独列出破坏性变更，保留 (#123) 编号；
           不符合规范的提交放在“其他”。
branches：列出本地和远程跟踪分支的最后提交时间、作者、是否已合并到基准分支（默认自动识别 main / master / develop），
          超过 --days 天没有提交的标为“长期未动”。只给出清理命令建议，不执行。
staged：已暂存改动的文件、增删行数和改动类型，辅助撰写提交说明。
需要本机安装 git。Exit codes: 0 ok, 1 输入错误或不是 git 仓库。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

TYPES = [("feat", "新增"), ("fix", "修复"), ("perf", "性能"), ("refactor", "重构"), ("docs", "文档"), ("test", "测试"),
         ("build", "构建与 CI"), ("ci", "构建与 CI"), ("style", "其他"), ("chore", "其他"), ("revert", "其他")]  # fmt: skip
TYPE_LABEL = dict(TYPES)
CC = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?:\s*(?P<subject>.+)$")
SEP = "\x1f"


class GitError(ValueError):
    pass


def git(repo: Path, *args: str) -> str:
    exe = shutil.which("git")
    if not exe:
        raise GitError("没有找到 git，请先安装 Git")
    r = subprocess.run(
        [exe, "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()
        raise GitError(msg[0] if msg else f"git {' '.join(args)} 失败")
    return r.stdout


def ensure_repo(repo: Path) -> None:
    try:
        inside = git(repo, "rev-parse", "--is-inside-work-tree").strip() == "true"
    except GitError:
        inside = False
    if not inside:
        raise GitError(f"{repo} 不是 git 仓库（用 --repo 指定仓库目录）")


def cmd_stats(repo: Path, since: str | None, until: str | None) -> int:
    args = [
        "log",
        "--no-merges",
        f"--format=%H{SEP}%an{SEP}%ad{SEP}%s",
        "--date=short",
        "--numstat",
    ]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    out = git(repo, *args)
    commits = 0
    authors: Counter[str] = Counter()
    months: Counter[str] = Counter()
    files: Counter[str] = Counter()
    types: Counter[str] = Counter()
    added = removed = 0
    lines_by_author: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    author = ""
    for line in out.splitlines():
        if SEP in line:
            _h, author, date, subject = line.split(SEP, 3)
            commits += 1
            authors[author] += 1
            months[date[:7]] += 1
            m = CC.match(subject)
            types[TYPE_LABEL.get(m.group("type"), "其他") if m else "未按规范"] += 1
        elif line.strip():
            parts = line.split("\t")
            if len(parts) == 3:
                a, d, path = parts
                if a.isdigit() and d.isdigit():
                    added += int(a)
                    removed += int(d)
                    lines_by_author[author][0] += int(a)
                    lines_by_author[author][1] += int(d)
                files[path] += 1
    if not commits:
        print("这个时间范围内没有提交")
        return 0
    rng = f"{since or '最早'} ~ {until or '现在'}"
    print(
        f"{rng}：{commits} 次提交（不含合并提交），新增 {added:,} 行，删除 {removed:,} 行，{len(authors)} 位作者"
    )
    print("\n| 作者 | 提交 | 新增行 | 删除行 |\n|------|------|--------|--------|")
    for a, n in authors.most_common(15):
        la, lr = lines_by_author[a]
        print(f"| {a} | {n} | {la:,} | {lr:,} |")
    print("\n按月：" + "、".join(f"{m} {n}" for m, n in sorted(months.items())))
    print("提交类型：" + "、".join(f"{t} {n}" for t, n in types.most_common()))
    print("\n改动最频繁的文件：")
    for f, n in files.most_common(10):
        print(f"- {n:>4} 次  {f}")
    return 0


def cmd_changelog(repo: Path, start: str, end: str, out: Path | None) -> int:
    git(repo, "rev-parse", "--verify", start)
    log = git(
        repo,
        "log",
        "--no-merges",
        f"--format=%h{SEP}%s{SEP}%b{SEP}%an{SEP}%ad\x1e",
        "--date=short",
        f"{start}..{end}",
    )
    groups: dict[str, list[str]] = defaultdict(list)
    breaking: list[str] = []
    count = 0
    for rec in log.split("\x1e"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        short, subject, body, _author, _date = rec.split(SEP, 4)
        count += 1
        m = CC.match(subject.strip())
        if m:
            label = TYPE_LABEL.get(m.group("type"), "其他")
            text = (f"**{m.group('scope')}**：" if m.group("scope") else "") + m.group(
                "subject"
            ).strip()
            if m.group("bang") or "BREAKING CHANGE" in body:
                breaking.append(f"- {text}（{short}）")
        else:
            label, text = "其他", subject.strip()
        groups[label].append(f"- {text}（{short}）")
    if not count:
        print(f"{start}..{end} 之间没有提交")
        return 0
    head = git(repo, "describe", "--tags", "--always", end).strip()
    lines = [f"## {head}（{dt.date.today().isoformat()}）", ""]
    if breaking:
        lines += ["### ⚠️ 破坏性变更", *breaking, ""]
    for label in dict.fromkeys(lab for _t, lab in TYPES):  # 新增 → 修复 → … → 其他
        if groups.get(label):
            lines += [f"### {label}", *groups[label], ""]
    text = "\n".join(lines).rstrip() + "\n"
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"已生成 {out}：{count} 次提交")
    else:
        print(text)
    nonconv = len(groups.get("其他", []))
    if nonconv:
        print(
            f"提示：{nonconv} 条提交没有按 type: subject 格式写或类型属于杂项，已归入“其他”，发布前建议人工改写成面向用户的描述。"
        )
    return 0


def default_base(repo: Path) -> str:
    branches = set(
        git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes").split()
    )
    for b in ("main", "master", "develop", "origin/main", "origin/master", "origin/develop"):
        if b in branches:
            return b
    return git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()


def cmd_branches(repo: Path, days: int, base: str | None) -> int:
    base = base or default_base(repo)
    merged = set(git(repo, "branch", "-a", "--format=%(refname:short)", "--merged", base).split())
    rows = git(repo, "for-each-ref", "--sort=-committerdate", f"--format=%(refname:short){SEP}%(committerdate:short){SEP}%(authorname){SEP}%(refname)",
               "refs/heads", "refs/remotes").splitlines()  # fmt: skip
    today = dt.date.today()
    stale_local, stale_remote, merged_local = [], [], []
    print(
        f"基准分支：{base}\n\n| 分支 | 最后提交 | 作者 | 已合并 | 状态 |\n|------|----------|------|--------|------|"
    )
    for row in rows:
        name, date, author, ref = row.split(SEP)
        if name.endswith("/HEAD") or name == base:
            continue
        age = (today - dt.date.fromisoformat(date)).days
        is_merged = name in merged
        state = f"长期未动（{age} 天）" if age > days else f"{age} 天前"
        print(f"| {name} | {date} | {author} | {'是' if is_merged else '否'} | {state} |")
        remote = ref.startswith("refs/remotes/")
        if is_merged and not remote:
            merged_local.append(name)
        elif age > days:
            (stale_remote if remote else stale_local).append(name)
    print()
    if merged_local:
        print(f"已合并到 {base} 的本地分支（可以安全删除）：")
        print("  git branch -d " + " ".join(merged_local))
    if stale_local:
        print(
            f"超过 {days} 天未动且未合并的本地分支（删除前确认没有需要的改动，-D 会丢弃未合并的提交）："
        )
        print("  " + "、".join(stale_local))
    if stale_remote:
        print(f"超过 {days} 天未动的远程分支（确认后可用 git push origin --delete 分支名 删除）：")
        print("  " + "、".join(stale_remote))
    if not (merged_local or stale_local or stale_remote):
        print("没有需要清理的分支。")
    return 0


def cmd_staged(repo: Path) -> int:
    stat = git(repo, "diff", "--cached", "--numstat")
    status = git(repo, "diff", "--cached", "--name-status")
    if not stat.strip():
        print("没有已暂存的改动（先 git add）")
        return 0
    kinds = {"A": "新增", "M": "修改", "D": "删除", "R": "重命名", "C": "复制"}
    st: dict[str, str] = {}
    for line in status.splitlines():
        parts = line.split("\t")
        st[parts[-1]] = kinds.get(parts[0][0], parts[0])
    total_a = total_d = 0
    cats: Counter[str] = Counter()
    print("| 文件 | 改动 | 新增 | 删除 |\n|------|------|------|------|")
    for line in stat.splitlines():
        a, d, path = line.split("\t", 2)
        path = path.split(" => ")[-1].strip("{}")
        total_a += int(a) if a.isdigit() else 0
        total_d += int(d) if d.isdigit() else 0
        print(f"| {path} | {st.get(path, '修改')} | {a} | {d} |")
        low = path.lower()
        if re.search(
            r"(^|/)(tests?|__tests__|spec)/|(_test|\.test|\.spec)\.\w+$|(^|/)test_[^/]+$", low
        ):
            cats["test"] += 1
        elif low.endswith((".md", ".rst", ".txt")) or low.startswith("docs/"):
            cats["docs"] += 1
        elif low.startswith((".github/", ".gitlab")) or low.endswith(
            (
                "dockerfile",
                "makefile",
                ".yml",
                ".yaml",
                "package.json",
                "pyproject.toml",
                "go.mod",
                "pom.xml",
            )
        ):
            cats["build"] += 1
        else:
            cats["code"] += 1
    n = sum(cats.values())
    guess = (
        "docs"
        if cats["docs"] == n
        else "test"
        if cats["test"] == n
        else "build"
        if cats["build"] == n
        else "feat / fix / refactor（看改动内容决定）"
    )
    print(f"\n共 {n} 个文件，+{total_a} / -{total_d}；建议类型：{guess}")
    print(
        "提交说明格式：<类型>(<范围>): <一句话说明改了什么>，正文写为什么改、影响范围，关联问题写 Closes #123。"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", default=".")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stats")
    s.add_argument("--since")
    s.add_argument("--until")
    c = sub.add_parser("changelog")
    c.add_argument("--from", dest="start", required=True)
    c.add_argument("--to", dest="end", default="HEAD")
    c.add_argument("-o", "--output")
    b = sub.add_parser("branches")
    b.add_argument("--days", type=int, default=90)
    b.add_argument("--base")
    sub.add_parser("staged")
    args = parser.parse_args(argv)
    try:
        repo = Path(args.repo)
        ensure_repo(repo)
        if args.cmd == "stats":
            return cmd_stats(repo, args.since, args.until)
        if args.cmd == "changelog":
            return cmd_changelog(
                repo, args.start, args.end, Path(args.output) if args.output else None
            )
        if args.cmd == "branches":
            return cmd_branches(repo, args.days, args.base)
        return cmd_staged(repo)
    except (OSError, GitError, subprocess.TimeoutExpired) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
