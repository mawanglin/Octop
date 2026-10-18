"""Contract tests for the bundled media experts (音乐 / 影视 / 照片)."""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

import mutagen
import mutagen.id3
import pytest
from deepagents.backends.local_shell import LocalShellBackend
from mutagen.wave import WAVE
from octop_harness.backends.workspace import BackendWorkspace
from PIL import Image

from octop.infra.agents.experts.catalog import (
    WORKSPACE_MANIFEST_PATH,
    ExpertCatalog,
    default_library_root,
    discover_seed_paths,
    seed_expert_directory,
)

LIBRARY = default_library_root()
MUSIC = LIBRARY / "music-librarian" / "skills" / "music-toolkit" / "scripts"
VIDEO = LIBRARY / "video-librarian" / "skills" / "video-toolkit" / "scripts"
PHOTO = LIBRARY / "photo-organizer" / "skills" / "photo-toolkit" / "scripts"

EXPERTS = {
    "music-librarian": ("音乐整理专家", {"music-toolkit", "music-standards"}),
    "video-librarian": ("影视整理专家", {"video-toolkit", "video-standards"}),
    "photo-organizer": ("照片整理专家", {"photo-toolkit", "photo-standards"}),
}


def _run(script: Path, *args: str | Path) -> subprocess.CompletedProcess[str]:
    # No __pycache__ inside the template dir: seeding copies every file it finds.
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )


def _plan_rows(path: Path, root: Path) -> list[tuple[str, str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    def rel(p: str) -> str:
        return Path(p).relative_to(root).as_posix() if p else ""

    return [(rel(r["源路径"]), rel(r["目标路径"]), r["说明"]) for r in rows]


def _files(root: Path) -> list[str]:
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and ".octop-media-undo" not in p.parts
    )


def _wav(path: Path, seconds: float, tags: dict[str, str] | None = None, tone: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(bytes([tone % 256, 0]) * int(8000 * seconds))
    if tags:
        frames = {
            "title": "TIT2",
            "artist": "TPE1",
            "album": "TALB",
            "tracknumber": "TRCK",
            "date": "TDRC",
        }
        audio = WAVE(path)
        audio.add_tags()
        for key, value in tags.items():
            audio.tags.add(getattr(mutagen.id3, frames[key])(encoding=3, text=[value]))
        audio.save()


# ------------------------------------------------------------------- catalog


@pytest.mark.parametrize("expert_id", sorted(EXPERTS))
def test_expert_catalog_manifest_and_skills(expert_id: str) -> None:
    label_zh, skills = EXPERTS[expert_id]
    catalog = ExpertCatalog(LIBRARY)
    catalog.refresh()
    expert = catalog.get(expert_id)
    assert expert is not None
    assert expert.summary.label_zh == label_zh
    assert expert.summary.icon_url == f"/experts/avatars/{expert_id}.svg"

    expert_dir = LIBRARY / expert_id
    manifest = json.loads((expert_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == expert_id
    for rel in manifest["prompt_files"]:
        assert (expert_dir / rel).is_file()
    assert len(manifest["quick_prompts"]) == 6
    assert len(manifest["task_examples"]["zh"]) == len(manifest["task_examples"]["en"]) == 6

    assert {p.name for p in (expert_dir / "skills").iterdir() if p.is_dir()} == skills
    soul = (expert_dir / "SOUL.md").read_text(encoding="utf-8")
    assert "永不删除" in soul and "先方案后执行" in soul
    for name in skills:
        raw = (expert_dir / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert raw.startswith(f"---\nname: {name}\n")
        assert "\ndescription:" in raw.split("---", 2)[1]
        assert f"`{name}`" in soul
        for rel in re.findall(r"`((?:scripts|references)/[\w.-]+)`", raw):
            assert (expert_dir / "skills" / name / rel).is_file(), f"{name}: {rel}"


@pytest.mark.parametrize("expert_id", sorted(EXPERTS))
async def test_expert_seeds_into_workspace(tmp_path: Path, expert_id: str) -> None:
    expert_dir = LIBRARY / expert_id
    workspace = BackendWorkspace(
        LocalShellBackend(root_dir=str(tmp_path), virtual_mode=False), tmp_path
    )
    paths = discover_seed_paths(expert_dir)
    assert not [p for p in paths if "__pycache__" in p]
    copied = await seed_expert_directory(expert_dir=expert_dir, workspace=workspace)
    assert copied == len(paths) + 1
    assert (
        await workspace.adownload_bytes(WORKSPACE_MANIFEST_PATH)
        == (expert_dir / "manifest.json").read_bytes()
    )


def test_media_ops_copies_are_identical() -> None:
    copies = sorted(LIBRARY.glob("*/skills/*/scripts/media_ops.py"))
    assert len(copies) == 3
    assert len({c.read_bytes() for c in copies}) == 1


# --------------------------------------------------------------- media_ops


def test_media_ops_guards_never_overwrite_or_escape(tmp_path: Path) -> None:
    root = tmp_path / "lib"
    (root / "a").mkdir(parents=True)
    (root / "a" / "x.txt").write_text("x", encoding="utf-8")
    (root / "a" / "y.txt").write_text("y", encoding="utf-8")
    (root / "taken.txt").write_text("keep me", encoding="utf-8")
    plan = tmp_path / "plan.csv"
    with plan.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["操作", "源路径", "目标路径", "说明"])
        w.writerow(["move", root / "a" / "x.txt", root / "b" / "x.txt", ""])
        w.writerow(["move", root / "a" / "y.txt", root / "taken.txt", ""])  # would overwrite
        w.writerow(["move", root / "a" / "y.txt", tmp_path / "outside.txt", ""])  # escapes root
        w.writerow(["move", root / "a" / "y.txt", "", "无法识别"])  # left blank on purpose
        w.writerow(["delete", root / "a" / "y.txt", "", ""])  # unsupported op
    result = _run(MUSIC / "media_ops.py", "apply", plan, "--root", root, "--prune-empty")
    assert result.returncode == 3, result.stderr
    assert "已移动 1 个文件" in result.stdout
    for expected in ("未覆盖", "不在根目录", "目标路径为空", "不支持的操作"):
        assert expected in result.stdout, expected
    assert (root / "taken.txt").read_text(encoding="utf-8") == "keep me"
    assert not (tmp_path / "outside.txt").exists()
    assert _files(root) == ["a/y.txt", "b/x.txt", "taken.txt"]

    log = next((root / ".octop-media-undo").glob("*.csv"))
    undo = _run(MUSIC / "media_ops.py", "undo", log)
    assert undo.returncode == 0, undo.stdout + undo.stderr
    assert _files(root) == ["a/x.txt", "a/y.txt", "taken.txt"]
    assert not (root / "b").exists()  # emptied folder pruned, never files


# --------------------------------------------------------------------- music


def test_music_scan_dupes_tags_plan_playlist(tmp_path: Path) -> None:
    root = tmp_path / "music"
    _wav(root / "下载" / "周杰伦 - 晴天.wav", 2.0, tone=1)
    _wav(root / "下载" / "陈奕迅 - 十年.wav", 1.5, tone=2)
    _wav(
        root / "旧歌" / "后来.wav",
        1.0,
        {
            "title": "ºóÀ´",
            "artist": "刘若英",
            "album": "我等你",
            "tracknumber": "3",
            "date": "2000",
        },
        tone=3,
    )
    (root / "旧歌" / "晴天 副本.wav").write_bytes(
        (root / "下载" / "周杰伦 - 晴天.wav").read_bytes()
    )
    (root / "下载" / "周杰伦 - 晴天.lrc").write_text("[00:01.00]故事的小黄花", encoding="utf-8")
    tool = MUSIC / "music_tool.py"
    ops = MUSIC / "media_ops.py"

    scan = _run(tool, "scan", root)
    assert scan.returncode == 0, scan.stderr
    assert "文件 4 个" in scan.stdout and "无损 4 首" in scan.stdout
    assert "标签疑似乱码 1 首" in scan.stdout

    dupes = tmp_path / "dupes.csv"
    assert _run(tool, "dupes", root, "-o", dupes).returncode == 0
    rows = _plan_rows(dupes, root)
    assert len(rows) == 1 and rows[0][1].startswith("_重复文件待确认/")
    assert _run(ops, "apply", dupes, "--root", root).returncode == 0

    tags = tmp_path / "tags.csv"
    result = _run(tool, "tags-from-name", root, "--pattern", "{artist} - {title}", "-o", tags)
    assert result.returncode == 0, result.stderr
    assert "4 处标签修改，涉及 2 个文件" in result.stdout
    assert "后来.wav" in result.stdout  # does not match the pattern, reported
    assert _run(tool, "write-tags", tags, "--root", root).returncode == 0
    fix = tmp_path / "fix.csv"
    fix.write_text(
        f"文件,字段,原值,新值\n{root / '旧歌' / '后来.wav'},title,ºóÀ´,后来\n", encoding="utf-8-sig"
    )
    assert _run(tool, "write-tags", fix, "--root", root).returncode == 0
    logs = sorted((root / ".octop-media-undo").glob("tags-*.csv"))
    assert len(logs) == 2  # a second write in the same second must not overwrite the first log
    assert str(WAVE(root / "下载" / "周杰伦 - 晴天.wav").tags["TPE1"]) == "周杰伦"

    plan = tmp_path / "plan.csv"
    assert _run(tool, "plan", root, "--dest", root / "整理后", "-o", plan).returncode == 0
    rows = _plan_rows(plan, root)
    targets = {src: dst for src, dst, _ in rows}
    assert targets["旧歌/后来.wav"] == "整理后/刘若英/我等你 (2000)/03 - 后来.wav"
    assert targets["下载/周杰伦 - 晴天.wav"] == "整理后/周杰伦/未知专辑/晴天.wav"
    assert targets["下载/周杰伦 - 晴天.lrc"] == "整理后/周杰伦/未知专辑/晴天.lrc"
    assert not any(src.startswith("_重复文件待确认") for src in targets)

    applied = _run(ops, "apply", plan, "--root", root, "--prune-empty")
    assert applied.returncode == 0, applied.stdout
    assert not (root / "下载").exists() and not (root / "旧歌").exists()

    lists = root / "整理后" / "歌单"
    assert _run(tool, "playlist", root / "整理后", "--by", "artist", "-o", lists).returncode == 0
    m3u = (lists / "周杰伦.m3u8").read_text(encoding="utf-8").splitlines()
    assert m3u[0] == "#EXTM3U" and m3u[2] == "../周杰伦/未知专辑/晴天.wav"

    undo_tags = _run(tool, "undo-tags", logs[1])
    assert undo_tags.returncode == 0, undo_tags.stderr
    assert (
        str(WAVE(root / "整理后" / "刘若英" / "我等你 (2000)" / "03 - 后来.wav").tags["TIT2"])
        == "ºóÀ´"
    )
    assert isinstance(mutagen.File(root / "整理后" / "周杰伦" / "未知专辑" / "晴天.wav"), WAVE)


# --------------------------------------------------------------------- video


@pytest.mark.parametrize(
    ("name", "kind", "title", "year", "season", "episode", "resolution"),
    [
        (
            "流浪地球2.The.Wandering.Earth.II.2023.2160p.WEB-DL.H265.mkv",
            "movie",
            "流浪地球2",
            2023,
            None,
            None,
            "2160p",
        ),
        ("The.Matrix.1999.1080p.BluRay.x264.mkv", "movie", "The Matrix", 1999, None, None, "1080p"),
        (
            "[阳光电影www.ygdy8.com].让子弹飞.2010.BD.1080p.国语中字.mkv",
            "movie",
            "让子弹飞",
            2010,
            None,
            None,
            "1080p",
        ),
        ("1917.2019.1080p.mkv", "movie", "1917", 2019, None, None, "1080p"),
        ("Breaking.Bad.S02E05.720p.HDTV.mkv", "episode", "Breaking Bad", None, 2, 5, "720p"),
        ("狂飙/第05集.mp4", "episode", "狂飙", None, 1, 5, None),
        ("三体 第一季/三体.EP12.2160p.mp4", "episode", "三体", None, 1, 12, "2160p"),
        ("[SubsPlease] Frieren - 05 (1080p) [ABCD].mkv", "episode", "Frieren", None, 1, 5, "1080p"),
        ("我的团长我的团 第2季 第3集.rmvb", "episode", "我的团长我的团", None, 2, 3, None),
        ("Friends/Season 3/Friends.3x07.mkv", "episode", "Friends", None, 3, 7, None),
        ("Show/S01E01.mkv", "episode", "Show", None, 1, 1, None),
    ],
)
def test_video_parse_names(
    name: str,
    kind: str,
    title: str,
    year: int | None,
    season: int | None,
    episode: int | None,
    resolution: str | None,
) -> None:
    result = _run(VIDEO / "video_tool.py", "parse", name)
    assert result.returncode == 0, result.stderr
    info = json.loads(result.stdout)
    assert (info["kind"], info["title"], info["year"], info["season"], info["episode"], info["resolution"]) == (
        kind, title, year, season, episode, resolution,
    )  # fmt: skip


def test_video_plan_follows_media_server_layout(tmp_path: Path) -> None:
    root = tmp_path / "videos"
    dl = root / "下载"
    (dl / "三体 第一季").mkdir(parents=True)
    (dl / "流浪地球2.The.Wandering.Earth.II.2023.2160p.WEB-DL.mkv").write_bytes(b"a" * 300)
    (dl / "流浪地球2.2023.1080p.mkv").write_bytes(b"b" * 200)
    (dl / "流浪地球2.The.Wandering.Earth.II.2023.2160p.WEB-DL.chs.srt").write_text(
        "1", encoding="utf-8"
    )
    (dl / "流浪地球2.The.Wandering.Earth.II.2023.2160p.WEB-DL.eng.srt").write_text(
        "2", encoding="utf-8"
    )
    (dl / "三体 第一季" / "三体.EP02.2160p.mp4").write_bytes(b"c" * 100)
    (dl / "三体 第一季" / "三体.EP02.简体.ass").write_text("s", encoding="utf-8")
    (dl / "sample-trailer.mkv").write_bytes(b"d")
    (dl / "副本.mkv").write_bytes(b"c" * 100)  # duplicate of the episode
    tool, ops = VIDEO / "video_tool.py", VIDEO / "media_ops.py"

    scan = _run(tool, "scan", root)
    assert scan.returncode == 0, scan.stderr
    assert "三体：1 集，第 1 季" in scan.stdout and "sample-trailer.mkv" in scan.stdout

    dupes = tmp_path / "d.csv"
    assert _run(tool, "dupes", root, "-o", dupes).returncode == 0
    assert _run(ops, "apply", dupes, "--root", root).returncode == 0

    plan = tmp_path / "p.csv"
    assert (
        _run(
            tool, "plan", root, "--movies", root / "电影", "--shows", root / "剧集", "-o", plan
        ).returncode
        == 0
    )
    targets = {src: dst for src, dst, _ in _plan_rows(plan, root)}
    assert targets["下载/流浪地球2.2023.1080p.mkv"] == "电影/流浪地球2 (2023)/流浪地球2 (2023).mkv"
    assert (
        targets["下载/流浪地球2.The.Wandering.Earth.II.2023.2160p.WEB-DL.mkv"]
        == "电影/流浪地球2 (2023)/流浪地球2 (2023) - 2160p.mkv"
    )
    assert (
        targets["下载/流浪地球2.The.Wandering.Earth.II.2023.2160p.WEB-DL.chs.srt"]
        == "电影/流浪地球2 (2023)/流浪地球2 (2023) - 2160p.zh.srt"
    )
    assert (
        targets["下载/流浪地球2.The.Wandering.Earth.II.2023.2160p.WEB-DL.eng.srt"]
        == "电影/流浪地球2 (2023)/流浪地球2 (2023) - 2160p.en.srt"
    )
    assert targets["下载/三体 第一季/三体.EP02.2160p.mp4"] == "剧集/三体/Season 01/三体 S01E02.mp4"
    assert (
        targets["下载/三体 第一季/三体.EP02.简体.ass"] == "剧集/三体/Season 01/三体 S01E02.zh.ass"
    )
    assert "下载/sample-trailer.mkv" not in targets and "下载/副本.mkv" not in targets

    assert _run(ops, "apply", plan, "--root", root, "--prune-empty").returncode == 0
    assert "剧集/三体/Season 01/三体 S01E02.mp4" in _files(root)


# --------------------------------------------------------------------- photo


def _jpg(
    path: Path,
    taken: str | None = None,
    make: str | None = None,
    color: tuple[int, int, int] = (0, 0, 0),
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (16, 12), color)
    exif = Image.Exif()
    if make:
        exif[271] = make
    if taken:
        exif.get_ifd(0x8769)[36867] = taken
    img.save(path, exif=exif)


def test_photo_plan_by_date_with_companions(tmp_path: Path) -> None:
    root = tmp_path / "photos"
    _jpg(root / "手机" / "IMG_0002.JPG", "2023:12:31 23:59:59", "Apple", (1, 1, 1))
    (root / "手机" / "IMG_0002.MOV").write_bytes(b"live")
    (root / "手机" / "IMG_0002.AAE").write_bytes(b"<xml/>")
    _jpg(root / "相机" / "DSC_0100.JPG", "2024:07:01 08:00:00", "Nikon", (2, 2, 2))
    (root / "相机" / "DSC_0100.NEF").write_bytes(b"raw")
    _jpg(root / "杂" / "Screenshot_2024-05-12-09-15-00.jpg", color=(3, 3, 3))
    _jpg(root / "杂" / "微信图片_20230101120000.jpg", color=(4, 4, 4))
    _jpg(root / "杂" / "随便.jpg", color=(5, 5, 5))
    stamp = 1646370367  # 2022-03-04, used as the file modified time
    os.utime(root / "杂" / "随便.jpg", (stamp, stamp))
    (root / "杂" / "IMG_0002 副本.JPG").write_bytes((root / "手机" / "IMG_0002.JPG").read_bytes())
    tool, ops = PHOTO / "photo_tool.py", PHOTO / "media_ops.py"

    scan = _run(tool, "scan", root)
    assert scan.returncode == 0, scan.stderr
    assert "截图 1" in scan.stdout and "微信 1" in scan.stdout and "随便.jpg" in scan.stdout

    dupes = tmp_path / "d.csv"
    assert _run(tool, "dupes", root, "-o", dupes).returncode == 0
    rows = _plan_rows(dupes, root)
    assert [r[0] for r in rows] == ["杂/IMG_0002 副本.JPG"]
    assert _run(ops, "apply", dupes, "--root", root).returncode == 0

    plan = tmp_path / "p.csv"
    result = _run(
        tool, "plan", root, "--dest", root / "整理后", "-o", plan, "--rename", "--split-sources"
    )
    assert result.returncode == 0, result.stderr
    targets = {src: (dst, note) for src, dst, note in _plan_rows(plan, root)}
    assert targets["手机/IMG_0002.JPG"][0] == "整理后/2023/2023-12/20231231_235959.jpg"
    assert targets["手机/IMG_0002.MOV"] == (
        "整理后/2023/2023-12/20231231_235959.mov",
        "实况照片视频跟随",
    )
    assert targets["手机/IMG_0002.AAE"][0] == "整理后/2023/2023-12/20231231_235959.aae"
    assert targets["相机/DSC_0100.NEF"] == (
        "整理后/2024/2024-07/20240701_080000.nef",
        "RAW 原片跟随",
    )
    assert (
        targets["杂/Screenshot_2024-05-12-09-15-00.jpg"][0]
        == "整理后/截图/2024/2024-05/20240512_091500.jpg"
    )
    assert (
        targets["杂/微信图片_20230101120000.jpg"][0]
        == "整理后/微信图片/2023/2023-01/20230101_120000.jpg"
    )
    assert targets["杂/随便.jpg"][0].startswith("整理后/2022/2022-03/")
    assert "修改时间" in targets["杂/随便.jpg"][1]

    applied = _run(ops, "apply", plan, "--root", root, "--prune-empty")
    assert applied.returncode == 0, applied.stdout
    assert "整理后/2023/2023-12/20231231_235959.mov" in _files(root)
