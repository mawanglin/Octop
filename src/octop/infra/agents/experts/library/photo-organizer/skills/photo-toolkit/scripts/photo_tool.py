#!/usr/bin/env python3
"""照片整理：按拍摄时间归档、按日期重命名、区分截图和微信图片、查重。

Usage:
    python scripts/photo_tool.py scan 照片目录 [--json]
    python scripts/photo_tool.py dupes 照片目录 -o 重复方案.csv
    python scripts/photo_tool.py plan 照片目录 --dest 整理后目录 -o 整理方案.csv [--layout "{year}/{year}-{month}"] [--rename] [--split-sources]

拍摄时间来源（按优先级）：EXIF 拍摄时间 → 文件名中的日期（相机、截图、微信、安卓等常见命名）→ 文件修改时间。
报告和方案的“说明”列会写明每个文件用的是哪种来源；按修改时间归档的要特别留意。
实况照片（同名 .HEIC/.JPG + .MOV）、同名 RAW 原片和编辑记录（.AAE/.XMP）会跟随照片一起移动、改名。
方案用同目录的 media_ops.py 执行：python scripts/media_ops.py apply 整理方案.csv --root 根目录
本工具只读文件、只生成方案。Exit codes: 0 ok, 1 输入错误。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from media_ops import (
    DUPES_DIR,
    OpsError,
    find_duplicates,
    human_size,
    iter_files,
    safe_name,
    write_plan,
)

try:
    from PIL import Image
except ImportError:  # pragma: no cover - environment check
    Image = None  # type: ignore[assignment]

PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".bmp", ".tif", ".tiff",
              ".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".rw2")  # fmt: skip
VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".3gp")
SIDECAR_EXTS = (".aae", ".xmp")
RAW_EXTS = (".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".rw2")
PIL_READABLE = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
EXIF_IFD, DATE_ORIGINAL, DATE_TIME, MAKE, MODEL = 0x8769, 36867, 306, 271, 272

NAME_PATTERNS = (
    # 20240512_143005 / IMG_20240512_143005 / PXL_20240512_143005123 / Screenshot_20240512-143005
    re.compile(r"(?<!\d)(20\d{2}|19\d{2})(\d{2})(\d{2})[_\-\s]?(\d{2})(\d{2})(\d{2})(?!\d{3,})"),
    # Screenshot_2024-05-12-14-30-05 / 屏幕截图 2024-05-12 143005 / 2024-05-12 14.30.05
    re.compile(
        r"(?<!\d)(20\d{2}|19\d{2})[-_.](\d{2})[-_.](\d{2})[\s_\-]+(\d{2})[-_.:]?(\d{2})[-_.:]?(\d{2})"
    ),
    # IMG-20240512-WA0001（WhatsApp，只有日期）/ 2024-05-12
    re.compile(r"(?<!\d)(20\d{2}|19\d{2})[-_.]?(\d{2})[-_.]?(\d{2})(?!\d)"),
)
EPOCH_MS = re.compile(r"(?:mmexport|wx_camera_|microMsg\.|_)(1[3-9]\d{11})(?!\d)")
SCREENSHOT = re.compile(r"(?i)screenshot|screen shot|screen_shot|截屏|截图|屏幕截图|snipaste")
WECHAT = re.compile(r"(?i)mmexport|wx_camera|微信图片|microMsg|wechat")


def _valid(y: int, mo: int, d: int, h: int = 0, mi: int = 0, s: int = 0) -> dt.datetime | None:
    try:
        when = dt.datetime(y, mo, d, h, mi, s)
    except ValueError:
        return None
    return (
        when
        if dt.datetime(1990, 1, 1) <= when <= dt.datetime.now() + dt.timedelta(days=1)
        else None
    )


def exif_info(path: Path) -> tuple[dt.datetime | None, str]:
    if Image is None or path.suffix.lower() not in PIL_READABLE:
        return None, ""
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            sub = exif.get_ifd(EXIF_IFD) if exif else {}
    except Exception:  # noqa: BLE001 - corrupt or unsupported images
        return None, ""
    camera = (
        " ".join(str(exif.get(k, "")).strip("\x00 ") for k in (MAKE, MODEL)).strip() if exif else ""
    )
    for raw in (sub.get(DATE_ORIGINAL) if sub else None, exif.get(DATE_TIME) if exif else None):
        if raw:
            m = re.match(
                r"(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", str(raw).strip("\x00 ")
            )
            if m:
                when = _valid(*map(int, m.groups()))
                if when:
                    return when, camera
    return None, camera


def name_date(stem: str) -> dt.datetime | None:
    m = EPOCH_MS.search(stem)
    if m:
        when = dt.datetime.fromtimestamp(int(m.group(1)) / 1000)
        if _valid(when.year, when.month, when.day):
            return when.replace(microsecond=0)
    for rx in NAME_PATTERNS:
        m = rx.search(stem)
        if m:
            when = _valid(*map(int, m.groups()))
            if when:
                return when
    return None


def photo_info(path: Path) -> dict[str, Any]:
    when, camera = exif_info(path)
    source = "EXIF"
    if when is None:
        when, source = name_date(path.stem), "文件名"
    if when is None:
        when, source = (
            dt.datetime.fromtimestamp(path.stat().st_mtime).replace(microsecond=0),
            "修改时间",
        )
    ext = path.suffix.lower()
    if SCREENSHOT.search(path.stem):
        kind = "截图"
    elif WECHAT.search(path.stem):
        kind = "微信"
    elif ext in VIDEO_EXTS:
        kind = "视频"
    elif camera:
        kind = "相机"
    else:
        kind = "其他"
    return {"path": path, "when": when, "source": source, "camera": camera, "kind": kind,
            "ext": ext, "size": path.stat().st_size}  # fmt: skip


def collect(root: Path, include_videos: bool, exclude: Path | None = None) -> list[dict[str, Any]]:
    exts = PHOTO_EXTS + (VIDEO_EXTS if include_videos else ())
    return [photo_info(p) for p in iter_files(root, exts, exclude=exclude)]


# --------------------------------------------------------------------- scan


def cmd_scan(root: Path, as_json: bool) -> int:
    items = collect(root, include_videos=True)
    if not items:
        print(f"{root} 下没有找到照片或视频")
        return 0
    years = Counter(i["when"].year for i in items)
    report = {
        "目录": str(root),
        "文件数": len(items),
        "总大小": human_size(sum(i["size"] for i in items)),
        "类型": dict(Counter(i["kind"] for i in items).most_common()),
        "时间来源": dict(Counter(i["source"] for i in items).most_common()),
        "年份": {str(k): v for k, v in sorted(years.items())},
        "格式": dict(Counter(i["ext"] for i in items).most_common()),
        "相机": dict(Counter(i["camera"] for i in items if i["camera"]).most_common(5)),
        "只能按修改时间归档": [
            str(i["path"].relative_to(root)) for i in items if i["source"] == "修改时间"
        ],
    }
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"# 照片库体检：{root}\n")
    print(f"- 文件 {len(items)} 个，{report['总大小']}")
    print(f"- 类型：{'、'.join(f'{k} {v}' for k, v in report['类型'].items())}")
    print(f"- 时间来源：{'、'.join(f'{k} {v}' for k, v in report['时间来源'].items())}")
    print(f"- 年份：{'、'.join(f'{k} 年 {v}' for k, v in report['年份'].items())}")
    print(f"- 格式：{'、'.join(f'{k} {v}' for k, v in report['格式'].items())}")
    if report["相机"]:
        print(f"- 相机：{'、'.join(f'{k} {v}' for k, v in report['相机'].items())}")
    heic = report["格式"].get(".heic", 0) + report["格式"].get(".heif", 0)
    if heic:
        print(f"- 提示：{heic} 个 HEIC 文件无法读取 EXIF，按文件名或修改时间判断日期")
    if report["只能按修改时间归档"]:
        print("\n## 只能按修改时间归档（日期可能不准，例如拷贝时被改过）")
        for line in report["只能按修改时间归档"][:10]:
            print(f"- {line}")
    return 0


# -------------------------------------------------------------------- dupes


def cmd_dupes(root: Path, out: Path) -> int:
    paths = [i["path"] for i in collect(root, include_videos=True)]
    rows = []
    for group in find_duplicates(paths):
        # 保留路径最短（通常是原始位置）的一份
        keep = min(group, key=lambda p: (len(p.parts), str(p)))
        for p in group:
            if p != keep:
                rows.append(
                    (
                        str(p),
                        str(root / DUPES_DIR / p.relative_to(root)),
                        f"完全相同的文件，保留 {keep.relative_to(root)}",
                    )
                )
    write_plan(rows, out)
    print(f"已生成 {out}：{len(rows)} 个重复文件建议移到 {root / DUPES_DIR}，不会删除任何文件")
    return 0


# --------------------------------------------------------------------- plan


def companions(path: Path) -> list[Path]:
    """Files that must stay with a photo of the same stem: Live Photo videos, RAW originals, edit sidecars."""
    out = []
    ext = path.suffix.lower()
    if ext in RAW_EXTS:
        return out  # RAW follows its JPG/HEIC, not the other way round
    for f in path.parent.iterdir():
        if f == path or not f.is_file() or f.stem.lower() != path.stem.lower():
            continue
        other = f.suffix.lower()
        if (
            other in SIDECAR_EXTS
            or (other in VIDEO_EXTS and ext in PHOTO_EXTS)
            or other in RAW_EXTS
        ):
            out.append(f)
    return out


def cmd_plan(
    root: Path, dest: Path, out: Path, layout: str, rename: bool, split: bool, include_videos: bool
) -> int:
    items = collect(root, include_videos, exclude=dest)
    attached: set[Path] = set()
    photos = [i for i in items if i["ext"] in PHOTO_EXTS]
    for i in photos:
        i["companions"] = companions(i["path"])
        attached.update(i["companions"])
    standalone = [i for i in items if i["path"] not in attached]
    rows: list[tuple[str, str, str]] = []
    used: set[str] = set()
    for i in sorted(standalone, key=lambda x: (x["when"], str(x["path"]))):
        when: dt.datetime = i["when"]
        folder_rel = layout.format(
            year=f"{when.year}", month=f"{when.month:02d}", day=f"{when.day:02d}"
        )
        base = dest
        if split and i["kind"] in ("截图", "微信"):
            base = dest / ("截图" if i["kind"] == "截图" else "微信图片")
        folder = base / Path(*[safe_name(p) for p in folder_rel.split("/") if p])
        stem = when.strftime("%Y%m%d_%H%M%S") if rename else i["path"].stem
        target = folder / f"{stem}{i['ext']}"
        n = 2
        while str(target).lower() in used:
            target = folder / f"{stem}_{n}{i['ext']}"
            n += 1
        used.add(str(target).lower())
        note = f"日期来源：{i['source']}" + ("（可能不准）" if i["source"] == "修改时间" else "")
        rows.append((str(i["path"]), str(target), note))
        for c in i.get("companions", []):
            c_target = target.with_suffix(c.suffix.lower())
            used.add(str(c_target).lower())
            kind = (
                "实况照片视频"
                if c.suffix.lower() in VIDEO_EXTS
                else "RAW 原片"
                if c.suffix.lower() in RAW_EXTS
                else "编辑记录"
            )
            rows.append((str(c), str(c_target), f"{kind}跟随"))
    write_plan(rows, out)
    by_source = Counter(i["source"] for i in standalone)
    print(
        f"已生成 {out}：{len(rows)} 行；日期来源 {'、'.join(f'{k} {v}' for k, v in by_source.most_common())}"
    )
    print(f"目录结构：{layout}" + ("，按拍摄时间重命名" if rename else "，保留原文件名"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("root")
    s.add_argument("--json", action="store_true")
    d = sub.add_parser("dupes")
    d.add_argument("root")
    d.add_argument("-o", "--output", required=True)
    p = sub.add_parser("plan")
    p.add_argument("root")
    p.add_argument("--dest", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--layout", default="{year}/{year}-{month}", help="可用 {year} {month} {day}")
    p.add_argument("--rename", action="store_true", help="按拍摄时间重命名为 20240512_143005.jpg")
    p.add_argument("--split-sources", action="store_true", help="截图、微信图片单独归档")
    p.add_argument("--no-videos", action="store_true", help="只整理照片，不动视频")
    args = parser.parse_args(argv)
    try:
        root = Path(args.root)
        if not root.is_dir():
            raise OpsError(f"目录不存在：{root}")
        if args.cmd == "scan":
            return cmd_scan(root, args.json)
        if args.cmd == "dupes":
            return cmd_dupes(root, Path(args.output))
        return cmd_plan(
            root,
            Path(args.dest),
            Path(args.output),
            args.layout,
            args.rename,
            args.split_sources,
            not args.no_videos,
        )
    except (OSError, OpsError, KeyError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
