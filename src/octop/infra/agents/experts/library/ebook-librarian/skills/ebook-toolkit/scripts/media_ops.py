#!/usr/bin/env python3
"""媒体整理的公共安全机制：执行整理方案（移动/重命名）、撤销、查重、安全文件名。

Usage:
    python scripts/media_ops.py apply plan.csv --root /媒体根目录 [--prune-empty]
    python scripts/media_ops.py undo /媒体根目录/.octop-media-undo/20261018-153000.csv

方案 CSV（由 music_tool.py / video_tool.py / photo_tool.py 的 plan、dupes 命令生成）列为：
    操作, 源路径, 目标路径, 说明
"操作"只支持 move；"目标路径"留空的行会被跳过（无法识别、需要人工填写的文件）。
用户可以在 Excel 里修改目标路径或删除不想处理的行后再执行。

安全规则：
  - 源路径和目标路径都必须在 --root 之内；
  - 目标已存在时跳过，绝不覆盖；本工具从不删除文件（重复文件只会被移到待确认目录）；
  - 每次执行都在 <root>/.octop-media-undo/ 写撤销日志，undo 按相反顺序还原。
Exit codes: 0 全部成功, 3 有跳过的行, 1 输入错误。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import os
import re
import shutil
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path

PLAN_HEADER = ["操作", "源路径", "目标路径", "说明"]
UNDO_DIR = ".octop-media-undo"
DUPES_DIR = "_重复文件待确认"
# Parked duplicates and NAS/OS housekeeping folders are never scanned again.
SKIP_DIRS = {
    UNDO_DIR,
    DUPES_DIR,
    "@eaDir",
    ".@__thumb",
    "#recycle",
    ".Trash-1000",
    "$RECYCLE.BIN",
    "System Volume Information",
}
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class OpsError(ValueError):
    pass


# ------------------------------------------------------------------ helpers


def safe_name(text: str, limit: int = 120) -> str:
    """A file/folder name that works on Windows, macOS, Linux and NAS shares."""
    name = _ILLEGAL.sub(" ", str(text)).strip()
    name = re.sub(r"\s+", " ", name).strip(" .")
    if len(name) > limit:
        name = name[:limit].rstrip(" .")
    return name or "未命名"


def iter_files(root: Path, exts: Iterable[str], exclude: Path | None = None) -> Iterator[Path]:
    """Media files under *root*, skipping housekeeping folders and *exclude* (e.g. the destination)."""
    wanted = {e.lower() for e in exts}
    skip = exclude.resolve() if exclude is not None else None
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in SKIP_DIRS
            and not d.startswith(".")
            and (skip is None or (Path(dirpath) / d).resolve() != skip)
        )
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            path = Path(dirpath) / name
            if path.suffix.lower() in wanted:
                yield path


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def _hash(path: Path, quick: bool) -> str:
    h = hashlib.sha1()
    size = path.stat().st_size
    with path.open("rb") as f:
        if quick and size > 4 * 1024 * 1024:
            h.update(f.read(1024 * 1024))
            f.seek(size - 1024 * 1024)
            h.update(f.read(1024 * 1024))
            h.update(str(size).encode())
        else:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    return h.hexdigest()


def find_duplicates(paths: Iterable[Path], full: bool = True) -> list[list[Path]]:
    """Groups of byte-identical files: size → head/tail hash → (optionally) full hash."""
    by_size: dict[int, list[Path]] = defaultdict(list)
    for p in paths:
        by_size[p.stat().st_size].append(p)
    groups: list[list[Path]] = []
    for same_size in by_size.values():
        if len(same_size) < 2:
            continue
        by_quick: dict[str, list[Path]] = defaultdict(list)
        for p in same_size:
            by_quick[_hash(p, quick=True)].append(p)
        for candidates in by_quick.values():
            if len(candidates) < 2:
                continue
            if not full:
                groups.append(sorted(candidates))
                continue
            by_full: dict[str, list[Path]] = defaultdict(list)
            for p in candidates:
                by_full[_hash(p, quick=False)].append(p)
            groups.extend(sorted(g) for g in by_full.values() if len(g) > 1)
    return sorted(groups, key=lambda g: str(g[0]))


def write_plan(rows: list[tuple[str, str, str]], out: Path) -> None:
    """rows: (source, target, note). Target may be '' for files needing manual input."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(PLAN_HEADER)
        for src, dst, note in rows:
            w.writerow(["move", src, dst, note])


def read_plan(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not set(PLAN_HEADER) <= set(reader.fieldnames):
            raise OpsError(f"方案文件表头应为：{','.join(PLAN_HEADER)}")
        return list(reader)


def next_log(log_dir: Path, prefix: str) -> Path:
    """<prefix>YYYYmmdd-HHMMSS-NN.csv — fixed-width so name order is time order, never overwritten."""
    stamp = f"{dt.datetime.now():%Y%m%d-%H%M%S}"
    n = 1
    while True:
        log = log_dir / f"{prefix}{stamp}-{n:02d}.csv"
        if not log.exists() and not log.with_suffix(".undone.csv").exists():
            return log
        n += 1


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


# ------------------------------------------------------------- apply / undo


def apply_plan(
    plan: Path, root: Path, prune_empty: bool = False
) -> tuple[int, list[str], Path | None]:
    if not root.is_dir():
        raise OpsError(f"根目录不存在：{root}")
    rows = read_plan(plan)
    done: list[tuple[str, str]] = []
    skipped: list[str] = []
    planned_targets: set[str] = set()
    for i, row in enumerate(rows, start=2):
        op = (row.get("操作") or "").strip().lower()
        src = Path((row.get("源路径") or "").strip())
        dst_text = (row.get("目标路径") or "").strip()
        if op != "move":
            skipped.append(f"第 {i} 行：不支持的操作「{op}」")
            continue
        if not dst_text:
            skipped.append(f"第 {i} 行：目标路径为空（{src.name}），未处理")
            continue
        dst = Path(dst_text)
        if src.resolve() == dst.resolve():
            continue
        if not (_inside(src, root) and _inside(dst, root)):
            skipped.append(f"第 {i} 行：路径不在根目录 {root} 内，拒绝处理")
            continue
        if not src.is_file():
            skipped.append(f"第 {i} 行：源文件不存在 {src}")
            continue
        key = str(dst.resolve()).lower()
        if dst.exists() or key in planned_targets:
            skipped.append(f"第 {i} 行：目标已存在 {dst}，未覆盖")
            continue
        planned_targets.add(key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        done.append((str(src), str(dst)))
    log: Path | None = None
    if done:
        log_dir = root / UNDO_DIR
        log_dir.mkdir(exist_ok=True)
        log = next_log(log_dir, "")
        with log.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["原路径", "新路径"])
            w.writerows(done)
    if prune_empty:
        prune_empty_dirs(root, {Path(s).parent for s, _ in done})
    return len(done), skipped, log


def undo(log: Path) -> tuple[int, list[str]]:
    with log.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))[1:]
    restored, skipped = 0, []
    for old, new in reversed(rows):
        src, dst = Path(new), Path(old)
        if not src.is_file():
            skipped.append(f"{src} 已不存在，无法还原")
            continue
        if dst.exists():
            skipped.append(f"{dst} 已被占用，未覆盖")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        restored += 1
    root = log.parent.parent
    prune_empty_dirs(root, {Path(new).parent for _, new in rows})
    if not skipped:
        log.rename(log.with_suffix(".undone.csv"))
    return restored, skipped


def prune_empty_dirs(root: Path, candidates: set[Path]) -> None:
    """Remove now-empty folders (only folders, never files) up to *root*."""
    for start in sorted(candidates, key=lambda p: len(p.parts), reverse=True):
        d = start
        while _inside(d, root) and d.resolve() != root.resolve() and d.is_dir():
            try:
                d.rmdir()
            except OSError:
                break
            d = d.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apply", help="按方案执行移动/重命名")
    a.add_argument("plan")
    a.add_argument("--root", required=True, help="媒体根目录，所有路径必须在其内")
    a.add_argument("--prune-empty", action="store_true", help="删除整理后留下的空文件夹")
    u = sub.add_parser("undo", help="按撤销日志还原")
    u.add_argument("log")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "apply":
            moved, skipped, log = apply_plan(Path(args.plan), Path(args.root), args.prune_empty)
            print(f"已移动 {moved} 个文件" + (f"，撤销日志：{log}" if log else ""))
            for s in skipped:
                print(f"跳过：{s}")
            return 3 if skipped else 0
        restored, skipped = undo(Path(args.log))
        print(f"已还原 {restored} 个文件")
        for s in skipped:
            print(f"未还原：{s}")
        return 3 if skipped else 0
    except (OSError, OpsError, csv.Error) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
