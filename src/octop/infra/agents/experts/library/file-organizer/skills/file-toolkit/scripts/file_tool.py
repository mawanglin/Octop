#!/usr/bin/env python3
"""文件整理：目录体检（类型分布、大文件、长期未用、临时文件、长路径）、查重、按类型 / 日期生成整理方案。

Usage:
    python scripts/file_tool.py scan 目录 [--top 20] [--json]
    python scripts/file_tool.py dupes 目录 -o 重复方案.csv [--keep newest|oldest|shortest]
    python scripts/file_tool.py plan 目录 --dest 整理后目录 -o 整理方案.csv [--by type|date|type-date] [--older-than 天数]

plan：
  - type：按类别（文档、表格、演示、PDF、图片、视频、音频、压缩包、安装包、代码、电子书、其他）放到 dest/类别/；
  - date：按修改时间放到 dest/YYYY/YYYY-MM/；type-date：dest/类别/YYYY/；
  - --older-than 只整理多少天没修改过的文件（如下载目录里 90 天前的东西）；
  - 同名文件自动加 (2)、(3)，不会覆盖；Office 临时文件（~$开头）和系统文件不整理。
dupes：内容完全相同的文件每组保留一个（--keep），其余移到 目录/_重复文件待确认/，不删除。
方案用同目录的 media_ops.py 执行：python scripts/media_ops.py apply 整理方案.csv --root 根目录
本工具只读文件、只生成方案。Exit codes: 0 ok, 1 输入错误。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from media_ops import (
    DUPES_DIR,
    SKIP_DIRS,
    OpsError,
    find_duplicates,
    human_size,
    safe_name,
    write_plan,
)

CATEGORIES: dict[str, tuple[str, ...]] = {
    "文档": (".doc", ".docx", ".wps", ".odt", ".rtf", ".txt", ".md", ".pages"),
    "表格": (".xls", ".xlsx", ".et", ".ods", ".csv", ".numbers"),
    "演示": (".ppt", ".pptx", ".dps", ".odp", ".key"),
    "PDF": (".pdf", ".ofd"),
    "图片": (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".tif", ".tiff", ".svg", ".psd", ".raw", ".cr2", ".nef", ".arw", ".dng"),
    "视频": (".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".m4v", ".ts", ".rmvb", ".webm"),
    "音频": (".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".ape", ".wma", ".amr"),
    "压缩包": (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz"),
    "安装包": (".exe", ".msi", ".dmg", ".pkg", ".apk", ".deb", ".rpm", ".appimage", ".iso"),
    "代码": (".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".go", ".rs", ".sh", ".json", ".yaml", ".yml", ".html", ".css", ".sql", ".ipynb"),
    "电子书": (".epub", ".mobi", ".azw3", ".azw", ".djvu", ".fb2"),
}  # fmt: skip
BY_EXT = {ext: cat for cat, exts in CATEGORIES.items() for ext in exts}
JUNK_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
JUNK_SUFFIX = (".tmp", ".temp", ".crdownload", ".part", ".download", ".bak")


class FileError(ValueError):
    pass


def category(path: Path) -> str:
    return BY_EXT.get(path.suffix.lower(), "其他")


def is_junk(path: Path) -> bool:
    name = path.name.lower()
    return name in JUNK_NAMES or name.startswith("~$") or name.endswith(JUNK_SUFFIX)


def walk(root: Path, exclude: Path | None = None, include_hidden: bool = False) -> list[Path]:
    """All regular files under *root*, skipping NAS/OS housekeeping folders and *exclude*."""
    skip = exclude.resolve() if exclude else None
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS and (include_hidden or not d.startswith("."))
            and (skip is None or (Path(dirpath) / d).resolve() != skip)
        )  # fmt: skip
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if (
                (include_hidden or not name.startswith(".") or name.lower() in JUNK_NAMES)
                and p.is_file()
                and not p.is_symlink()
            ):
                out.append(p)
    return out


def mtime(p: Path) -> dt.datetime:
    return dt.datetime.fromtimestamp(p.stat().st_mtime)


def cmd_scan(root: Path, top: int, as_json: bool, today: dt.date) -> int:
    files = walk(root)
    if not files:
        raise FileError(f"{root} 里没有文件")
    by_cat: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    junk, old, long_paths = [], [], []
    for p in files:
        size = p.stat().st_size
        c = by_cat[category(p)]
        c[0] += 1
        c[1] += size
        if is_junk(p):
            junk.append(p)
        if (today - mtime(p).date()).days > 365:
            old.append((p, size))
        if len(str(p)) > 200:
            long_paths.append(p)
    sizes = Counter(p.stat().st_size for p in files if p.stat().st_size > 0)
    dup_candidates = sum(n for s, n in sizes.items() if n > 1)
    empty_dirs = [d for d, subdirs, fs in os.walk(root) if not subdirs and not fs and Path(d) != root
                  and not any(part in SKIP_DIRS for part in Path(d).parts)]  # fmt: skip
    biggest = sorted(files, key=lambda p: p.stat().st_size, reverse=True)[:top]
    total = sum(v[1] for v in by_cat.values())
    report: dict[str, Any] = {
        "目录": str(root),
        "文件数": len(files),
        "总大小": human_size(total),
        "类别": {
            k: {"数量": v[0], "大小": human_size(v[1])}
            for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1][1])
        },
        "最大文件": [
            {"路径": str(p.relative_to(root)), "大小": human_size(p.stat().st_size)}
            for p in biggest
        ],
        "一年以上未修改": {"数量": len(old), "大小": human_size(sum(s for _, s in old))},
        "临时或系统文件": [str(p.relative_to(root)) for p in junk[:50]],
        "可能重复的文件数（大小相同）": dup_candidates,
        "空文件夹": len(empty_dirs),
        "路径超过200字符": [str(p.relative_to(root)) for p in long_paths[:20]],
    }
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"{root}：{len(files)} 个文件，共 {report['总大小']}")
    print("| 类别 | 数量 | 大小 |\n|------|------|------|")
    for k, v in report["类别"].items():
        print(f"| {k} | {v['数量']} | {v['大小']} |")
    print(f"\n最大的 {len(biggest)} 个文件：")
    for item in report["最大文件"]:
        print(f"- {item['大小']}  {item['路径']}")
    print(f"\n一年以上未修改：{len(old)} 个，{report['一年以上未修改']['大小']}")
    print(f"临时或系统文件：{len(junk)} 个" + (f"（如 {junk[0].name}）" if junk else ""))
    print(f"大小相同、可能重复的文件：{dup_candidates} 个（用 dupes 精确比对）")
    print(
        f"空文件夹：{len(empty_dirs)} 个；路径超过 200 字符：{len(long_paths)} 个（Windows 下可能打不开）"
    )
    return 0


def cmd_dupes(root: Path, out: Path, keep: str) -> int:
    files = [p for p in walk(root) if not is_junk(p) and p.stat().st_size > 0]
    groups = find_duplicates(files)
    rows: list[tuple[str, str, str]] = []
    wasted = 0
    for g in groups:
        if keep == "newest":
            keeper = max(g, key=lambda p: (p.stat().st_mtime, -len(str(p))))
        elif keep == "oldest":
            keeper = min(g, key=lambda p: (p.stat().st_mtime, len(str(p))))
        else:
            keeper = min(g, key=lambda p: (len(str(p)), str(p)))
        for p in g:
            if p == keeper:
                continue
            target = root / DUPES_DIR / p.relative_to(root)
            rows.append((str(p), str(target), f"与 {keeper.relative_to(root)} 内容相同"))
            wasted += p.stat().st_size
    write_plan(rows, out)
    print(
        f"已生成 {out}：{len(groups)} 组重复，{len(rows)} 个文件将移到 {DUPES_DIR}/，可释放约 {human_size(wasted)}"
    )
    print("确认无误后执行 media_ops.py apply；确认可以删除后再由用户自己清空待确认目录。")
    return 0


def cmd_plan(
    root: Path, dest: Path, out: Path, by: str, older_than: int | None, today: dt.date
) -> int:
    dest_in_root = dest.resolve().is_relative_to(root.resolve())
    files = walk(root, exclude=dest if dest_in_root else None)
    rows: list[tuple[str, str, str]] = []
    taken: set[str] = set()
    skipped_recent = skipped_junk = 0
    for p in files:
        if is_junk(p):
            skipped_junk += 1
            continue
        when = mtime(p)
        if older_than is not None and (today - when.date()).days < older_than:
            skipped_recent += 1
            continue
        cat = category(p)
        if by == "type":
            folder = dest / cat
        elif by == "date":
            folder = dest / f"{when:%Y}" / f"{when:%Y-%m}"
        else:
            folder = dest / cat / f"{when:%Y}"
        stem, suffix = safe_name(p.stem), p.suffix.lower()
        target = folder / f"{stem}{suffix}"
        n = 2
        while str(target).lower() in taken or (target.exists() and target.resolve() != p.resolve()):
            target = folder / f"{stem} ({n}){suffix}"
            n += 1
        taken.add(str(target).lower())
        if target.resolve() == p.resolve():
            continue
        rows.append((str(p), str(target), f"{cat}，修改于 {when:%Y-%m-%d}"))
    write_plan(rows, out)
    counts = Counter(Path(r[1]).relative_to(dest).parts[0] for r in rows)
    print(f"已生成 {out}：{len(rows)} 个文件待整理到 {dest}")
    print("、".join(f"{k} {v}" for k, v in counts.most_common()))
    if skipped_recent:
        print(f"跳过 {skipped_recent} 个近 {older_than} 天修改过的文件")
    if skipped_junk:
        print(
            f"跳过 {skipped_junk} 个临时或系统文件（如 ~$ 开头的 Office 临时文件），可在确认后手动清理"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("root")
    s.add_argument("--top", type=int, default=20)
    s.add_argument("--json", action="store_true")
    s.add_argument("--today")
    d = sub.add_parser("dupes")
    d.add_argument("root")
    d.add_argument("-o", "--output", required=True)
    d.add_argument("--keep", choices=["newest", "oldest", "shortest"], default="shortest")
    p = sub.add_parser("plan")
    p.add_argument("root")
    p.add_argument("--dest", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--by", choices=["type", "date", "type-date"], default="type")
    p.add_argument("--older-than", type=int)
    p.add_argument("--today")
    args = parser.parse_args(argv)
    try:
        root = Path(args.root)
        if not root.is_dir():
            raise FileError(f"{root} 不是目录")
        today = (
            dt.date.fromisoformat(args.today) if getattr(args, "today", None) else dt.date.today()
        )
        if args.cmd == "scan":
            return cmd_scan(root, args.top, args.json, today)
        if args.cmd == "dupes":
            return cmd_dupes(root, Path(args.output), args.keep)
        return cmd_plan(root, Path(args.dest), Path(args.output), args.by, args.older_than, today)
    except (OSError, FileError, OpsError, ValueError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
