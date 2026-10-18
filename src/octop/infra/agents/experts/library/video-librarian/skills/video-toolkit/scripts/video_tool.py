#!/usr/bin/env python3
"""本地影视库整理：识别电影/剧集文件名，体检、查重，生成符合 Jellyfin / Emby / Plex / 飞牛影视刮削规范的整理方案。

Usage:
    python scripts/video_tool.py parse "流浪地球2.The.Wandering.Earth.II.2023.2160p.WEB-DL.mkv"
    python scripts/video_tool.py scan 影视目录 [--probe] [--json]
    python scripts/video_tool.py dupes 影视目录 -o 重复方案.csv [--full-hash]
    python scripts/video_tool.py plan 影视目录 --movies 电影目录 --shows 剧集目录 -o 整理方案.csv

整理规则：
    电影：电影目录/片名 (年份)/片名 (年份).mkv
    剧集：剧集目录/剧名/Season 01/剧名 S01E01.mkv
    字幕、NFO、海报跟随视频改名，字幕加语言后缀（.zh / .zh-TW / .en）。
方案用同目录的 media_ops.py 执行：python scripts/media_ops.py apply 整理方案.csv --root 根目录
本工具只读文件、只生成方案，不移动也不修改任何文件。
Exit codes: 0 ok, 1 输入错误。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
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

VIDEO_EXTS = (
    ".mkv",
    ".mp4",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".ts",
    ".m2ts",
    ".rmvb",
    ".rm",
    ".webm",
    ".m4v",
    ".mpg",
    ".mpeg",
)
SUB_EXTS = (".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx", ".sup")
SIDE_EXTS = (".nfo", ".jpg", ".jpeg", ".png")
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
RES = re.compile(r"(?i)(?<![a-z0-9])(2160p|4k|uhd|1080p|1080i|720p|576p|480p)(?![a-z0-9])")
NOISE = re.compile(
    r"(?i)(?<![a-z0-9])(web-?dl|web-?rip|bluray|blu-ray|bdrip|brrip|hdtv|hdrip|dvdrip|remux|x26[45]|h\.?26[45]|"
    r"hevc|avc|aac\d?(\.\d)?|ac3|dts(-hd)?|ddp?\d?(\.\d)?|atmos|truehd|flac|hdr10\+?|hdr|dv|dovi|10bit|8bit|"
    r"60fps|proper|repack|extended|unrated|imax|complete|multi|sdr|nf|amzn|dsnp|hmax)(?![a-z0-9])"
)
CN_NOISE = re.compile(
    r"(国语|粤语|国粤双语|国英双语|中英双字|中英字幕|中文字幕|中字|简繁|简体|繁体|双语|内封|内嵌|特效字幕|未删减|完整版|高清|超清|蓝光|无水印)"
)
SE_PATTERNS = (
    re.compile(r"(?i)(?<![a-z0-9])s(\d{1,2})[ ._-]?e(\d{1,3})(?![0-9])"),
    re.compile(r"(?<![0-9])(\d{1,2})x(\d{2,3})(?![0-9])"),
)
CN_SEASON = re.compile(r"第\s*([0-9]{1,2}|[一二三四五六七八九十]{1,2})\s*季")
CN_EPISODE = re.compile(r"第\s*([0-9]{1,3})\s*[集话話]")
EP_ONLY = re.compile(r"(?i)(?<![a-z0-9])(?:ep?|episode)[ ._-]?(\d{1,3})(?![0-9])")
ANIME_EP = re.compile(r"\s-\s(\d{1,3})(?:v\d)?(?=\s*(?:\[|\(|$|\.))")
YEAR = re.compile(r"(?<![0-9])(19[3-9]\d|20[0-4]\d)(?![0-9p])")
SEASON_DIR = re.compile(
    r"(?i)^(season\s*\d+|s\d{1,2}|第\s*[0-9一二三四五六七八九十]+\s*季|specials?)$"
)
LANG_TOKENS = (
    ("zh-TW", re.compile(r"(?i)(?<![a-z])(cht|tc|big5|zh[-_]?(tw|hk|hant))(?![a-z])|繁")),
    (
        "zh",
        re.compile(r"(?i)(?<![a-z])(chs|sc|gb|chi|zho|zh[-_]?(cn|hans)?|chinese)(?![a-z])|简|中"),
    ),
    ("en", re.compile(r"(?i)(?<![a-z])(en|eng|english)(?![a-z])|英")),
    ("ja", re.compile(r"(?i)(?<![a-z])(ja|jp|jpn|japanese)(?![a-z])|日")),
)


def cn_int(text: str) -> int:
    if text.isdigit():
        return int(text)
    if text.startswith("十"):
        return 10 + CN_NUM.get(text[1:], 0)
    if "十" in text:
        tens, _, ones = text.partition("十")
        return CN_NUM.get(tens, 1) * 10 + CN_NUM.get(ones, 0)
    return CN_NUM.get(text, 0)


def clean_title(raw: str) -> str:
    text = re.sub(r"【[^】]*】|\[[^\]]*\]|「[^」]*」", " ", raw)
    text = re.sub(r"(?i)www\.[a-z0-9-]+\.[a-z]{2,}", " ", text)
    text = CN_NOISE.sub(" ", NOISE.sub(" ", text))
    text = re.sub(r"[._]+", " ", text)
    text = re.sub(r"\(\s*\)|（\s*）", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -–—_.()（）")
    # 中英双名：保留中文名（含紧跟的数字），去掉后面的英文名。
    m = re.match(r"^([一-鿿][一-鿿0-9：:·！!？?，, ]*?)\s+[A-Za-z][A-Za-z'’&]+(\s|$)", text)
    if m:
        text = m.group(1)
    return text.strip(" -–—:：")


def parse_name(stem: str, parent: str = "", grandparent: str = "") -> dict[str, Any]:
    """Guess movie/episode info from a file name (and its folders)."""
    info: dict[str, Any] = {
        "kind": "movie",
        "title": "",
        "year": None,
        "season": None,
        "episode": None,
        "resolution": None,
    }
    res = RES.search(stem)
    if res:
        r = res.group(1).lower()
        info["resolution"] = "2160p" if r in ("4k", "uhd") else r
    cut = len(stem)
    for rx in SE_PATTERNS:
        m = rx.search(stem)
        if m:
            info["season"], info["episode"] = int(m.group(1)), int(m.group(2))
            cut = min(cut, m.start())
            break
    if info["episode"] is None:
        ms, me = CN_SEASON.search(stem), CN_EPISODE.search(stem)
        if me:
            info["episode"] = int(me.group(1))
            cut = min(cut, me.start())
        if ms:
            info["season"] = cn_int(ms.group(1))
            cut = min(cut, ms.start())
    if info["episode"] is None:
        m = EP_ONLY.search(stem) or ANIME_EP.search(stem)
        if m:
            info["episode"] = int(m.group(1))
            cut = min(cut, m.start())
    if info["episode"] is not None:
        info["kind"] = "episode"
    years = [m for m in YEAR.finditer(stem) if m.start() > 0]
    if years and info["kind"] == "movie":
        info["year"] = int(years[-1].group(1))
        cut = min(cut, years[-1].start())
    for rx in (RES, NOISE):
        m = rx.search(stem)
        if m:
            cut = min(cut, m.start())
    title = clean_title(stem[:cut])
    if info["kind"] == "episode":
        if info["season"] is None:
            info["season"] = 1
            info["season_guessed"] = True
        folder = parent if not SEASON_DIR.match(parent.strip()) else grandparent
        folder_info = parse_name(folder) if folder else {"title": ""}
        if not title or re.fullmatch(r"[\d\s]+", title):
            title = folder_info["title"]
        if folder and not CN_SEASON.search(stem):
            m = CN_SEASON.search(parent)
            if m:
                info["season"] = cn_int(m.group(1))
                info.pop("season_guessed", None)
            m = re.search(r"(?i)season\s*(\d+)|^s(\d{1,2})$", parent.strip())
            if m:
                info["season"] = int(m.group(1) or m.group(2))
                info.pop("season_guessed", None)
    elif not title and parent:
        title = parse_name(parent)["title"]
    info["title"] = title
    return info


def sub_language(sub: Path, video_stem: str) -> str:
    extra = sub.stem[len(video_stem) :] if sub.stem.startswith(video_stem) else sub.stem
    langs = [code for code, rx in LANG_TOKENS if rx.search(extra)]
    if "zh" in langs and "en" in langs:
        return "zh"  # 中英双语字幕按中文字幕处理
    return langs[0] if langs else ""


def probe(path: Path) -> dict[str, Any]:
    exe = os.environ.get("OCTOP_FFPROBE") or shutil.which("ffprobe")
    if not exe:
        return {}
    try:
        out = subprocess.run(
            [exe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30,
        )  # fmt: skip
        data = json.loads(out.stdout or "{}")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}
    stream = (data.get("streams") or [{}])[0]
    return {"width": stream.get("width"), "height": stream.get("height"),
            "duration": float((data.get("format") or {}).get("duration") or 0)}  # fmt: skip


def collect(root: Path, exclude: list[Path] | None = None) -> list[dict[str, Any]]:
    excluded = [p.resolve() for p in (exclude or [])]
    items = []
    for p in iter_files(root, VIDEO_EXTS):
        if any(str(p.resolve()).startswith(str(e) + os.sep) for e in excluded):
            continue
        info = parse_name(p.stem, p.parent.name, p.parent.parent.name)
        info.update(
            path=p, size=p.stat().st_size, sample="sample" in p.stem.lower() or "预告" in p.stem
        )
        items.append(info)
    return items


def find_sidecars(video: Path, info: dict[str, Any]) -> list[Path]:
    """Subtitles / nfo / posters that belong to *video* (same stem prefix or same SxxExx)."""
    out = []
    for f in video.parent.iterdir():
        if f == video or not f.is_file() or f.suffix.lower() not in SUB_EXTS + SIDE_EXTS:
            continue
        if (
            f.stem == video.stem
            or f.stem.startswith(video.stem + ".")
            or f.stem.startswith(video.stem + "-")
        ):
            out.append(f)
        elif f.suffix.lower() in SUB_EXTS and info["kind"] == "episode":
            other = parse_name(f.stem, f.parent.name, f.parent.parent.name)
            if other.get("episode") == info["episode"] and other.get("season") == info["season"]:
                out.append(f)
    return sorted(out)


# --------------------------------------------------------------------- scan


def cmd_scan(root: Path, do_probe: bool, as_json: bool) -> int:
    items = collect(root)
    if not items:
        print(f"{root} 下没有找到视频文件")
        return 0
    movies = [i for i in items if i["kind"] == "movie" and not i["sample"]]
    episodes = [i for i in items if i["kind"] == "episode"]
    unknown = [i for i in items if not i["title"]]
    no_year = [i for i in movies if not i["year"]]
    subs_all = list(iter_files(root, SUB_EXTS))
    attached = {s for i in items for s in find_sidecars(i["path"], i)}
    orphans = [s for s in subs_all if s not in attached]
    no_subs = [
        i
        for i in items
        if not any(s.suffix.lower() in SUB_EXTS for s in find_sidecars(i["path"], i))
    ]
    keys = Counter(
        (i["title"].lower(), i["year"], i["season"], i["episode"]) for i in items if i["title"]
    )
    multi = [k for k, n in keys.items() if n > 1]
    shows = Counter(i["title"] for i in episodes)
    if do_probe:
        for i in items:
            i.update(probe(i["path"]))
    report = {
        "目录": str(root),
        "视频文件": len(items),
        "总大小": human_size(sum(i["size"] for i in items)),
        "电影": len(movies),
        "剧集": f"{len(shows)} 部，{len(episodes)} 集",
        "分辨率": dict(Counter(i["resolution"] or "未标注" for i in items).most_common()),
        "无法识别片名": [str(i["path"].relative_to(root)) for i in unknown],
        "电影缺年份": [str(i["path"].relative_to(root)) for i in no_year],
        "无字幕": len(no_subs),
        "孤立字幕": [str(s.relative_to(root)) for s in orphans],
        "疑似重复（同片多版本）": len(multi),
        "预告/样片": [str(i["path"].relative_to(root)) for i in items if i["sample"]],
    }
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"# 影视库体检：{root}\n")
    print(
        f"- 视频 {len(items)} 个，{report['总大小']}；电影 {len(movies)} 部，剧集 {report['剧集']}"
    )
    print(f"- 分辨率：{'、'.join(f'{k} {v}' for k, v in report['分辨率'].items())}")
    print(f"- 无字幕 {len(no_subs)} 个；孤立字幕 {len(orphans)} 个；疑似同片多版本 {len(multi)} 组")
    for label in ("无法识别片名", "电影缺年份", "孤立字幕", "预告/样片"):
        if report[label]:
            print(f"\n## {label}")
            for line in report[label][:8]:
                print(f"- {line}")
    if shows:
        print("\n## 剧集")
        for show, n in shows.most_common(10):
            seasons = sorted({i["season"] for i in episodes if i["title"] == show})
            print(f"- {show}：{n} 集，第 {'、'.join(map(str, seasons))} 季")
    if do_probe and not (os.environ.get("OCTOP_FFPROBE") or shutil.which("ffprobe")):
        print("\n提示：未找到 ffprobe，未读取实际分辨率和时长")
    return 0


# -------------------------------------------------------------------- dupes


def cmd_dupes(root: Path, out: Path, full_hash: bool) -> int:
    paths = [i["path"] for i in collect(root)]
    rows = []
    for group in find_duplicates(paths, full=full_hash):
        keep = group[0]
        for p in group[1:]:
            rows.append(
                (
                    str(p),
                    str(root / DUPES_DIR / p.relative_to(root)),
                    f"完全相同的文件，保留 {keep.relative_to(root)}",
                )
            )
    write_plan(rows, out)
    how = "完整哈希" if full_hash else "大小 + 首尾片段哈希"
    print(
        f"已生成 {out}：{len(rows)} 个重复文件（比对方式：{how}）建议移到 {root / DUPES_DIR}，不会删除任何文件"
    )
    print("同一部影片的不同版本（如 1080p 和 2160p）不会自动归为重复，见 scan 的“疑似重复”")
    return 0


# --------------------------------------------------------------------- plan


def cmd_plan(root: Path, movies_dir: Path, shows_dir: Path, out: Path) -> int:
    items = [i for i in collect(root, exclude=[movies_dir, shows_dir]) if not i["sample"]]
    rows: list[tuple[str, str, str]] = []
    used: set[str] = set()
    for i in sorted(items, key=lambda x: str(x["path"])):
        p, notes = i["path"], []
        if not i["title"]:
            rows.append((str(p), "", "无法识别片名，请在“目标路径”中手动填写"))
            continue
        title = safe_name(i["title"])
        if i["kind"] == "movie":
            name = f"{title} ({i['year']})" if i["year"] else title
            if not i["year"]:
                notes.append("缺少年份，刮削可能匹配错误，建议补上")
            folder = movies_dir / name
            stem = name
        else:
            s, e = i["season"], i["episode"]
            if i.get("season_guessed"):
                notes.append("文件名没有季号，按第 1 季处理")
            folder = shows_dir / title / f"Season {s:02d}"
            stem = f"{title} S{s:02d}E{e:02d}"
        target = folder / f"{stem}{p.suffix.lower()}"
        if str(target).lower() in used:
            suffix = f" - {i['resolution']}" if i["resolution"] else " - 版本2"
            stem = f"{stem}{suffix}"
            target = folder / f"{stem}{p.suffix.lower()}"
            notes.append("同一影片已有其他文件，按多版本命名")
            n = 2
            while str(target).lower() in used:
                n += 1
                target = folder / f"{stem} ({n}){p.suffix.lower()}"
        used.add(str(target).lower())
        rows.append((str(p), str(target), "；".join(notes)))
        for side in find_sidecars(p, i):
            ext = side.suffix.lower()
            if ext in SUB_EXTS:
                lang = sub_language(side, p.stem)
                side_stem = f"{stem}.{lang}" if lang else stem
                side_target = folder / f"{side_stem}{ext}"
                n = 2
                while str(side_target).lower() in used:
                    side_target = folder / f"{side_stem}.{n}{ext}"
                    n += 1
                note = f"字幕跟随（语言：{lang or '未识别'}）"
            else:
                tail = side.stem[len(p.stem) :] if side.stem.startswith(p.stem) else ""
                side_target = folder / f"{stem}{tail}{ext}"
                note = "附属文件跟随"
            used.add(str(side_target).lower())
            rows.append((str(side), str(side_target), note))
    write_plan(rows, out)
    n_movies = sum(1 for i in items if i["kind"] == "movie")
    print(
        f"已生成 {out}：{len(rows)} 行（电影 {n_movies} 个，剧集 {len(items) - n_movies} 集，含字幕等附属文件）"
    )
    blank = sum(1 for r in rows if not r[1])
    if blank:
        print(f"提示：{blank} 个文件无法识别，目标路径留空，执行时会跳过")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    pa = sub.add_parser("parse", help="识别单个文件名")
    pa.add_argument("name")
    s = sub.add_parser("scan")
    s.add_argument("root")
    s.add_argument("--probe", action="store_true", help="用 ffprobe 读取实际分辨率（较慢）")
    s.add_argument("--json", action="store_true")
    d = sub.add_parser("dupes")
    d.add_argument("root")
    d.add_argument("-o", "--output", required=True)
    d.add_argument("--full-hash", action="store_true", help="计算完整哈希（大文件很慢）")
    p = sub.add_parser("plan")
    p.add_argument("root")
    p.add_argument("--movies", required=True, help="电影整理目标目录")
    p.add_argument("--shows", required=True, help="剧集整理目标目录")
    p.add_argument("-o", "--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "parse":
            path = Path(args.name)
            info = parse_name(
                path.stem if path.suffix else args.name, path.parent.name, path.parent.parent.name
            )
            print(json.dumps(info, ensure_ascii=False))
            return 0
        root = Path(args.root)
        if not root.is_dir():
            raise OpsError(f"目录不存在：{root}")
        if args.cmd == "scan":
            return cmd_scan(root, args.probe, args.json)
        if args.cmd == "dupes":
            return cmd_dupes(root, Path(args.output), args.full_hash)
        return cmd_plan(root, Path(args.movies), Path(args.shows), Path(args.output))
    except (OSError, OpsError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
