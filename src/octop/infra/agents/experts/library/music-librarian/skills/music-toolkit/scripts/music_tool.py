#!/usr/bin/env python3
"""本地音乐库整理：体检、查重、按文件名补标签、生成整理方案、生成歌单。

Usage:
    python scripts/music_tool.py scan 音乐目录 [--json]
    python scripts/music_tool.py dupes 音乐目录 -o 重复方案.csv
    python scripts/music_tool.py tags-from-name 音乐目录 --pattern "{artist} - {title}" -o 标签方案.csv [--all]
    python scripts/music_tool.py write-tags 标签方案.csv --root 音乐目录
    python scripts/music_tool.py undo-tags 音乐目录/.octop-media-undo/tags-20261018-153000.csv
    python scripts/music_tool.py plan 音乐目录 --dest 整理后目录 -o 整理方案.csv [--layout "{albumartist}/{album} ({year})/{track} - {title}"]
    python scripts/music_tool.py playlist 音乐目录 --by artist -o 歌单目录

整理方案用同目录的 media_ops.py 执行：python scripts/media_ops.py apply 整理方案.csv --root 根目录
只有 write-tags 会修改音频文件（只改标签，执行前把原值写进撤销日志）；其余命令只读或只生成方案。
Exit codes: 0 ok, 1 输入错误, 2 缺少 mutagen。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from media_ops import (
    DUPES_DIR,
    UNDO_DIR,
    OpsError,
    find_duplicates,
    human_size,
    iter_files,
    next_log,
    safe_name,
    write_plan,
)

try:
    import mutagen
    import mutagen.id3
except ImportError:  # pragma: no cover - environment check
    print("缺少依赖 mutagen：请运行 `pip install mutagen`", file=sys.stderr)
    sys.exit(2)

AUDIO_EXTS = (
    ".mp3",
    ".flac",
    ".m4a",
    ".aac",
    ".ogg",
    ".opus",
    ".wav",
    ".ape",
    ".wma",
    ".aiff",
    ".aif",
    ".dsf",
    ".wv",
)
LOSSLESS_EXTS = {".flac", ".wav", ".ape", ".aiff", ".aif", ".dsf", ".wv"}
COVER_NAMES = ("cover", "folder", "front", "album", "封面")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
TAG_FIELDS = ("title", "artist", "album", "albumartist", "tracknumber", "date", "genre")
FIELD_ZH = {"title": "标题", "artist": "艺术家", "album": "专辑", "albumartist": "专辑艺术家",
            "tracknumber": "音轨号", "date": "年份", "genre": "流派"}  # fmt: skip
DEFAULT_LAYOUT = "{albumartist}/{album} ({year})/{track} - {title}"
TAG_HEADER = ["文件", "字段", "原值", "新值"]
# WAV / AIFF / DSF carry plain ID3 tags without mutagen's "easy" field names.
ID3_FRAMES = {"title": "TIT2", "artist": "TPE1", "album": "TALB", "albumartist": "TPE2",
              "tracknumber": "TRCK", "date": "TDRC", "genre": "TCON"}  # fmt: skip


def get_tag(audio: Any, field: str) -> str:
    tags = getattr(audio, "tags", None)
    if tags is None:
        return ""
    if isinstance(tags, mutagen.id3.ID3):
        frame = tags.get(ID3_FRAMES[field])
        return str(frame.text[0]).strip() if frame is not None and frame.text else ""
    try:
        value = audio.get(field)
    except Exception:  # noqa: BLE001 - some formats reject unknown keys
        return ""
    return str(value[0]).strip() if value else ""


def set_tag(audio: Any, field: str, value: str) -> None:
    if isinstance(audio.tags, mutagen.id3.ID3):
        key = ID3_FRAMES[field]
        audio.tags.delall(key)
        if value:
            audio.tags.add(getattr(mutagen.id3, key)(encoding=3, text=[value]))
    elif value:
        audio[field] = [value]
    elif field in audio:
        del audio[field]


class ToolError(ValueError):
    pass


# ------------------------------------------------------------------ reading


def read_track(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"path": path, "ext": path.suffix.lower(), "size": path.stat().st_size}
    try:
        easy = mutagen.File(path, easy=True)
        raw = mutagen.File(path)
    except Exception as exc:  # noqa: BLE001 - mutagen raises many types for broken files
        info["error"] = str(exc) or type(exc).__name__
        return info
    if easy is None:
        info["error"] = "无法识别的音频格式"
        return info
    for field in TAG_FIELDS:
        info[field] = get_tag(easy, field)
    stream = getattr(easy, "info", None)
    info["length"] = float(getattr(stream, "length", 0) or 0)
    info["bitrate"] = int(getattr(stream, "bitrate", 0) or 0)
    info["lossless"] = (
        info["ext"] in LOSSLESS_EXTS or "alac" in str(getattr(stream, "codec", "")).lower()
    )
    info["cover"] = _has_embedded_cover(raw) or _folder_cover(path) is not None
    info["lyrics"] = path.with_suffix(".lrc").exists() or _has_embedded_lyrics(raw)
    return info


def _has_embedded_cover(raw: Any) -> bool:
    if raw is None:
        return False
    if getattr(raw, "pictures", None):
        return True
    tags = getattr(raw, "tags", None)
    if not tags:
        return False
    keys = [str(k) for k in tags.keys()]  # noqa: SIM118 - Vorbis comments iterate as (key, value) pairs
    return any(
        k.startswith("APIC") or k in ("covr", "METADATA_BLOCK_PICTURE", "WM/Picture") for k in keys
    )


def _has_embedded_lyrics(raw: Any) -> bool:
    tags = getattr(raw, "tags", None)
    if not tags:
        return False
    keys = [str(k).upper() for k in tags.keys()]  # noqa: SIM118 - Vorbis comments iterate as (key, value) pairs
    return any(k.startswith("USLT") or k in ("LYRICS", "UNSYNCEDLYRICS", "©LYR") for k in keys)


def _folder_cover(path: Path) -> Path | None:
    for child in path.parent.iterdir():
        if child.suffix.lower() in IMAGE_EXTS and child.stem.lower() in COVER_NAMES:
            return child
    return None


def looks_garbled(text: str) -> bool:
    """GBK tags decoded as Latin-1 show up as runs of accented Latin letters."""
    if not text:
        return False
    latin = sum(1 for ch in text if "À" <= ch <= "ÿ")
    return latin >= 2 and latin / len(text) > 0.3 or "�" in text


def normalize(text: str) -> str:
    text = re.sub(r"[\(\（\[【].*?[\)\）\]】]", "", text.lower())
    return re.sub(r"[\s\-_.,，、·'\"!！?？]+", "", text)


# --------------------------------------------------------------------- scan


def cmd_scan(root: Path, as_json: bool) -> int:
    tracks = [read_track(p) for p in iter_files(root, AUDIO_EXTS)]
    if not tracks:
        print(f"{root} 下没有找到音频文件")
        return 0
    ok = [t for t in tracks if "error" not in t]
    formats = Counter(t["ext"] for t in tracks)
    missing = {
        f: [t for t in ok if not t.get(f)] for f in ("title", "artist", "album", "tracknumber")
    }
    garbled = [
        t for t in ok if any(looks_garbled(t.get(f, "")) for f in ("title", "artist", "album"))
    ]
    low = [t for t in ok if not t["lossless"] and 0 < t["bitrate"] < 192_000]
    no_cover = [t for t in ok if not t["cover"]]
    no_lyrics = [t for t in ok if not t["lyrics"]]
    report = {
        "目录": str(root),
        "文件数": len(tracks),
        "总大小": human_size(sum(t["size"] for t in tracks)),
        "总时长（小时）": round(sum(t.get("length", 0) for t in ok) / 3600, 1),
        "格式": dict(formats.most_common()),
        "无损": sum(1 for t in ok if t["lossless"]),
        "低码率（<192kbps）": len(low),
        "缺少标签": {FIELD_ZH[f]: len(v) for f, v in missing.items()},
        "标签疑似乱码": len(garbled),
        "无封面": len(no_cover),
        "无歌词": len(no_lyrics),
        "无法读取": [f"{t['path']}：{t['error']}" for t in tracks if "error" in t],
    }
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"# 音乐库体检：{root}\n")
    print(f"- 文件 {report['文件数']} 个，{report['总大小']}，约 {report['总时长（小时）']} 小时")
    print(f"- 格式：{'、'.join(f'{k} {v}' for k, v in formats.most_common())}")
    print(f"- 无损 {report['无损']} 首；低码率（<192kbps）{len(low)} 首")
    print(f"- 缺少标签：{'、'.join(f'{k} {v}' for k, v in report['缺少标签'].items())}")
    print(
        f"- 标签疑似乱码 {len(garbled)} 首；无封面 {len(no_cover)} 首；无歌词 {len(no_lyrics)} 首"
    )
    for label, group in (
        ("缺少艺术家", missing["artist"]),
        ("标签疑似乱码", garbled),
        ("低码率", low),
    ):
        if group:
            print(f"\n## {label}（示例）")
            for t in group[:5]:
                print(f"- {t['path'].relative_to(root)}")
    if report["无法读取"]:
        print("\n## 无法读取")
        for line in report["无法读取"][:10]:
            print(f"- {line}")
    return 0


# -------------------------------------------------------------------- dupes


def _quality(t: dict[str, Any]) -> tuple[int, int, int]:
    return (1 if t.get("lossless") else 0, t.get("bitrate", 0), t["size"])


def cmd_dupes(root: Path, out: Path, same_song: bool) -> int:
    paths = list(iter_files(root, AUDIO_EXTS))
    tracks = {p: read_track(p) for p in paths}
    rows: list[tuple[str, str, str]] = []
    seen: set[Path] = set()

    def park(group: list[Path], why: str) -> None:
        keep = max(group, key=lambda p: _quality(tracks[p]))
        for p in group:
            if p == keep or p in seen:
                continue
            seen.add(p)
            target = root / DUPES_DIR / p.relative_to(root)
            rows.append((str(p), str(target), f"{why}，保留 {keep.relative_to(root)}"))

    for group in find_duplicates(paths):
        park(group, "完全相同的文件")
    if same_song:
        songs: dict[tuple[str, str], list[Path]] = defaultdict(list)
        for p, t in tracks.items():
            if "error" not in t and t.get("artist") and t.get("title") and p not in seen:
                songs[(normalize(t["artist"]), normalize(t["title"]))].append(p)
        for group in songs.values():
            if len(group) < 2:
                continue
            lengths = [tracks[p].get("length", 0) for p in group]
            if max(lengths) - min(lengths) <= 3:
                park(group, "同一首歌的不同文件（艺术家、标题相同，时长相差 ≤3 秒）")
    write_plan(rows, out)
    print(f"已生成 {out}：{len(rows)} 个重复文件建议移到 {root / DUPES_DIR}（不会删除任何文件）")
    return 0


# --------------------------------------------------------------------- tags


def pattern_regex(pattern: str) -> re.Pattern[str]:
    fields = {"artist": r"(?P<artist>.+?)", "title": r"(?P<title>.+?)", "album": r"(?P<album>.+?)",
              "track": r"(?P<track>\d{1,3})", "year": r"(?P<year>(?:19|20)\d{2})"}  # fmt: skip
    out, pos = "", 0
    for m in re.finditer(r"\{(\w+)\}", pattern):
        out += re.escape(pattern[pos : m.start()]).replace(r"\ ", r"\s*")
        if m.group(1) not in fields:
            raise ToolError(f"模式中的 {{{m.group(1)}}} 不支持，可用：{', '.join(fields)}")
        out += fields[m.group(1)]
        pos = m.end()
    out += re.escape(pattern[pos:]).replace(r"\ ", r"\s*")
    return re.compile(rf"^\s*{out}\s*$")


def cmd_tags_from_name(root: Path, pattern: str, out: Path, overwrite_all: bool) -> int:
    rx = pattern_regex(pattern)
    key_map = {
        "artist": "artist",
        "title": "title",
        "album": "album",
        "track": "tracknumber",
        "year": "date",
    }
    rows: list[list[str]] = []
    unmatched: list[Path] = []
    for p in iter_files(root, AUDIO_EXTS):
        t = read_track(p)
        if "error" in t:
            continue
        stem = (
            re.sub(r"^\d{1,3}[\s.\-_、]+(?=\D)", "", p.stem) if "{track}" not in pattern else p.stem
        )
        m = rx.match(stem)
        if not m:
            unmatched.append(p)
            continue
        for key, value in m.groupdict().items():
            field = key_map[key]
            value = value.strip()
            old = t.get(field, "")
            if value and value != old and (overwrite_all or not old or looks_garbled(old)):
                rows.append([str(p), field, old, value])
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(TAG_HEADER)
        w.writerows(rows)
    print(f"已生成 {out}：{len(rows)} 处标签修改，涉及 {len({r[0] for r in rows})} 个文件")
    if unmatched:
        print(f"提示：{len(unmatched)} 个文件名不符合模式「{pattern}」，未处理，例如：")
        for p in unmatched[:5]:
            print(f"- {p.name}")
    return 0


def _set_tags(path: Path, changes: dict[str, str]) -> dict[str, str]:
    audio = mutagen.File(path, easy=True)
    if audio is None:
        raise ToolError(f"无法写入：{path}")
    if audio.tags is None:
        audio.add_tags()
    old = {}
    for field, value in changes.items():
        old[field] = get_tag(audio, field)
        set_tag(audio, field, value)
    audio.save()
    return old


def cmd_write_tags(plan: Path, root: Path) -> int:
    with plan.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not set(TAG_HEADER) <= set(reader.fieldnames):
            raise ToolError(f"标签方案表头应为：{','.join(TAG_HEADER)}")
        rows = list(reader)
    by_file: dict[str, dict[str, str]] = defaultdict(dict)
    for r in rows:
        if r["字段"] not in TAG_FIELDS:
            raise ToolError(f"字段「{r['字段']}」不支持，可用：{', '.join(TAG_FIELDS)}")
        by_file[r["文件"]][r["字段"]] = r["新值"]
    log_dir = root / UNDO_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log = next_log(log_dir, "tags-")
    written, failed = 0, []
    with log.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(TAG_HEADER)
        for file, changes in by_file.items():
            path = Path(file)
            try:
                path.resolve().relative_to(root.resolve())
            except ValueError:
                failed.append(f"{file} 不在根目录内，未处理")
                continue
            try:
                old = _set_tags(path, changes)
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{file}：{exc}")
                continue
            for field, value in changes.items():
                w.writerow([file, field, value, old.get(field, "")])  # undo writes 原值 back
            written += 1
    print(f"已写入 {written} 个文件的标签，撤销日志：{log}")
    for msg in failed:
        print(f"失败：{msg}")
    return 3 if failed else 0


def moved_locations(undo_dir: Path) -> dict[str, str]:
    """old path → current path, following every (not undone) move log in order."""
    where: dict[str, str] = {}
    for move_log in sorted(undo_dir.glob("*.csv")):
        if move_log.name.startswith("tags-") or move_log.name.endswith(".undone.csv"):
            continue
        with move_log.open(encoding="utf-8-sig", newline="") as f:
            for old, new in list(csv.reader(f))[1:]:
                for origin, current in list(where.items()):
                    if current == old:
                        where[origin] = new
                where.setdefault(old, new)
    return where


def cmd_undo_tags(log: Path) -> int:
    with log.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    by_file: dict[str, dict[str, str]] = defaultdict(dict)
    for r in rows:
        by_file[r["文件"]][r["字段"]] = r["新值"]
    moves = moved_locations(log.parent)
    restored, failed = 0, []
    for file, changes in by_file.items():
        path = Path(file) if Path(file).exists() else Path(moves.get(file, file))
        if not path.exists():
            failed.append(f"{file} 已不存在（可能被移动或删除），未还原")
            continue
        try:
            _set_tags(path, changes)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{path}：{exc}")
            continue
        restored += 1
    if not failed:
        log.rename(log.with_suffix(".undone.csv"))
    print(f"已还原 {restored} 个文件的标签")
    for msg in failed:
        print(f"未还原：{msg}")
    return 3 if failed else 0


# --------------------------------------------------------------------- plan


def target_for(t: dict[str, Any], layout: str) -> tuple[str, list[str]]:
    notes = []
    artist = t.get("albumartist") or t.get("artist") or ""
    if not artist:
        notes.append("缺少艺术家")
    if not t.get("album"):
        notes.append("缺少专辑")
    if not t.get("title"):
        notes.append("缺少标题，沿用文件名")
    track_raw = (t.get("tracknumber") or "").split("/")[0]
    track = f"{int(track_raw):02d}" if track_raw.isdigit() else ""
    year = (re.search(r"(19|20)\d{2}", t.get("date") or "") or [""])[0]
    values = {
        "albumartist": safe_name(artist or "未知艺术家"),
        "artist": safe_name(t.get("artist") or artist or "未知艺术家"),
        "album": safe_name(t.get("album") or "未知专辑"),
        "title": safe_name(t.get("title") or t["path"].stem),
        "track": track,
        "year": year,
        "genre": safe_name(t.get("genre") or "未分类"),
    }
    text = layout.format(**values)
    text = re.sub(r"\s*\(\s*\)", "", text)  # drop "()" when year is empty
    text = re.sub(r"(^|/)\s*-\s*", r"\1", text)  # drop leading " - " when track is empty
    parts = [safe_name(p) for p in text.split("/") if p.strip()]
    return "/".join(parts) + t["ext"], notes


def cmd_plan(root: Path, dest: Path, out: Path, layout: str) -> int:
    rows: list[tuple[str, str, str]] = []
    targets: dict[str, Path] = {}
    folder_targets: dict[Path, set[Path]] = defaultdict(set)
    for p in iter_files(root, AUDIO_EXTS, exclude=dest):
        t = read_track(p)
        if "error" in t:
            rows.append((str(p), "", f"无法读取：{t['error']}"))
            continue
        rel, notes = target_for(t, layout)
        target = dest / rel
        key = str(target).lower()
        if key in targets:
            stem, n = target.stem, 2
            while str(target).lower() in targets:
                target = target.with_name(f"{stem} ({n}){target.suffix}")
                n += 1
            notes.append("与其他文件目标重名，已加序号；可能是重复文件，建议先查重")
        targets[str(target).lower()] = p
        rows.append((str(p), str(target), "；".join(notes)))
        lrc = p.with_suffix(".lrc")
        if lrc.exists():
            rows.append((str(lrc), str(target.with_suffix(".lrc")), "歌词跟随歌曲"))
        folder_targets[p.parent].add(target.parent)
    for folder, dests in folder_targets.items():
        cover = _folder_cover(folder / "x")
        if cover and len(dests) == 1:
            rows.append((str(cover), str(next(iter(dests)) / cover.name), "专辑封面跟随"))
    write_plan(rows, out)
    flagged = sum(1 for r in rows if r[2] and "跟随" not in r[2])
    print(f"已生成 {out}：{len(rows)} 行（其中 {flagged} 行需要留意，见“说明”列）")
    print(f"目录结构：{layout}{'{扩展名}'}")
    return 0


# ----------------------------------------------------------------- playlist


def cmd_playlist(root: Path, by: str, out_dir: Path) -> int:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in iter_files(root, AUDIO_EXTS):
        t = read_track(p)
        if "error" in t:
            continue
        if by == "folder":
            key = str(p.parent.relative_to(root)) or root.name
        elif by == "year":
            key = (re.search(r"(19|20)\d{2}", t.get("date") or "") or ["未知年份"])[0]
        else:
            key = (
                t.get(by)
                or t.get("artist" if by == "albumartist" else by)
                or f"未知{FIELD_ZH.get(by, by)}"
            )
        groups[key].append(t)
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, tracks in sorted(groups.items()):
        tracks.sort(
            key=lambda t: (
                t.get("album", ""),
                (t.get("tracknumber") or "0").split("/")[0].zfill(3),
                t["path"].name,
            )
        )
        playlist = out_dir / f"{safe_name(key.replace('/', ' '))}.m3u8"
        lines = ["#EXTM3U"]
        for t in tracks:
            try:
                rel = Path(os.path.relpath(t["path"].resolve(), out_dir.resolve())).as_posix()
            except ValueError:  # different drives on Windows
                rel = t["path"].resolve().as_posix()
            lines.append(
                f"#EXTINF:{int(t.get('length', 0))},{t.get('artist') or ''} - {t.get('title') or t['path'].stem}"
            )
            lines.append(rel)
        playlist.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已在 {out_dir} 生成 {len(groups)} 个歌单（.m3u8，UTF-8）")
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
    d.add_argument("--exact-only", action="store_true", help="只找完全相同的文件")
    t = sub.add_parser("tags-from-name")
    t.add_argument("root")
    t.add_argument("--pattern", required=True, help='如 "{artist} - {title}"、"{track}. {title}"')
    t.add_argument("-o", "--output", required=True)
    t.add_argument("--all", action="store_true", help="已有标签也按文件名覆盖")
    w = sub.add_parser("write-tags")
    w.add_argument("plan")
    w.add_argument("--root", required=True)
    u = sub.add_parser("undo-tags")
    u.add_argument("log")
    p = sub.add_parser("plan")
    p.add_argument("root")
    p.add_argument("--dest", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--layout", default=DEFAULT_LAYOUT)
    pl = sub.add_parser("playlist")
    pl.add_argument("root")
    pl.add_argument(
        "--by",
        choices=["artist", "albumartist", "album", "genre", "year", "folder"],
        default="artist",
    )
    pl.add_argument("-o", "--output", required=True)
    args = parser.parse_args(argv)
    try:
        root = Path(getattr(args, "root", ".") or ".")
        if (
            args.cmd in ("scan", "dupes", "tags-from-name", "plan", "playlist")
            and not root.is_dir()
        ):
            raise ToolError(f"目录不存在：{root}")
        if args.cmd == "scan":
            return cmd_scan(root, args.json)
        if args.cmd == "dupes":
            return cmd_dupes(root, Path(args.output), not args.exact_only)
        if args.cmd == "tags-from-name":
            return cmd_tags_from_name(root, args.pattern, Path(args.output), args.all)
        if args.cmd == "write-tags":
            return cmd_write_tags(Path(args.plan), root)
        if args.cmd == "undo-tags":
            return cmd_undo_tags(Path(args.log))
        if args.cmd == "plan":
            return cmd_plan(root, Path(args.dest), Path(args.output), args.layout)
        return cmd_playlist(root, args.by, Path(args.output))
    except (OSError, ToolError, OpsError, KeyError, csv.Error) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
