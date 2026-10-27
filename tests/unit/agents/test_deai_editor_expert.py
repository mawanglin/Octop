"""Contract tests for the bundled 去AI味专家 (deai-editor) expert."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from deepagents.backends.local_shell import LocalShellBackend
from octop_harness.backends.workspace import BackendWorkspace

from octop.infra.agents.experts.catalog import (
    WORKSPACE_MANIFEST_PATH,
    ExpertCatalog,
    default_library_root,
    discover_seed_paths,
    seed_expert_directory,
)
from octop.infra.agents.experts.skillhub_market import _SCENE_ORDER

LIBRARY = default_library_root()
EXPERT_DIR = LIBRARY / "deai-editor"
SKILLS = {"deai-rules", "ai-tone-check", "voice-calibration", "english-humanize"}
CHECK = EXPERT_DIR / "skills" / "ai-tone-check" / "scripts" / "ai_tone_check.py"
REFS = EXPERT_DIR / "skills" / "ai-tone-check" / "references"

AUTHOR = (
    "我写东西有个毛病——总爱用破折号。改不掉，也不想改。\n\n"
    "那年冬天我在杭州——不是西湖边，是城北一个老小区——租了间十二平米的屋子。"
    "房东是个退休的数学老师，每天早上六点准时在楼下打太极。\n\n"
    "我问他为什么是六点。他说六点人少——这话我记了很多年。\n\n"
    "后来搬走那天，他送了我一本旧的《几何原本》。扉页上写着：别算得太清楚。\n"
)
DRAFT = (
    "周末去了趟千岛湖——说实话比想象中好。湖水很清，早上的雾一直到九点才散。\n\n"
    "我们住在一个叫汾口的小镇——镇上只有两家像样的饭馆。第二天下午下了一场雨，我们就在民宿里打了三个小时的牌。\n\n"
    "回来的路上堵了两个小时——但没人抱怨。大家都说明年还要去，下次带上孩子。\n"
)


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


def test_expert_catalog_manifest_and_skills() -> None:
    catalog = ExpertCatalog(LIBRARY)
    catalog.refresh()
    expert = catalog.get("deai-editor")
    assert expert is not None
    assert expert.summary.label_zh == "去AI味专家"
    assert expert.summary.icon_url == "/experts/avatars/deai-editor.svg"
    assert expert.summary.scene in _SCENE_ORDER

    manifest = json.loads((EXPERT_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "deai-editor"
    for rel in manifest["prompt_files"]:
        assert (EXPERT_DIR / rel).is_file()
    assert len(manifest["quick_prompts"]) == 6
    assert len(manifest["task_examples"]["zh"]) == len(manifest["task_examples"]["en"]) == 6

    assert {p.name for p in (EXPERT_DIR / "skills").iterdir() if p.is_dir()} == SKILLS
    soul = (EXPERT_DIR / "SOUL.md").read_text(encoding="utf-8")
    for name in SKILLS:
        raw = (EXPERT_DIR / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert raw.startswith(f"---\nname: {name}\n")
        assert "\ndescription:" in raw.split("---", 2)[1]
        assert f"`{name}`" in soul
        for rel in re.findall(r"`((?:scripts|references)/[\w.-]+)`", raw):
            assert (EXPERT_DIR / "skills" / name / rel).is_file(), f"{name}: {rel}"


async def test_expert_seeds_into_workspace(tmp_path: Path) -> None:
    workspace = BackendWorkspace(
        LocalShellBackend(root_dir=str(tmp_path), virtual_mode=False), tmp_path
    )
    paths = discover_seed_paths(EXPERT_DIR)
    assert not [p for p in paths if "__pycache__" in p]
    copied = await seed_expert_directory(expert_dir=EXPERT_DIR, workspace=workspace)
    assert copied == len(paths) + 1
    assert (
        await workspace.adownload_bytes(WORKSPACE_MANIFEST_PATH)
        == (EXPERT_DIR / "manifest.json").read_bytes()
    )


def test_sources_credit_every_mit_project() -> None:
    sources = (EXPERT_DIR / "skills" / "deai-rules" / "references" / "sources.md").read_text(
        encoding="utf-8"
    )
    for repo in (
        "baibanbao/qu-ai-wei",
        "larashero3-dotcom/lieflat-less-ai-tone",
        "op7418/Humanizer-zh",
        "blader/humanizer",
        "hardikpandya/stop-slop",
    ):
        assert f"https://github.com/{repo}" in sources
    assert sources.count("Copyright (c)") == 5
    assert "The above copyright notice and this permission notice" in sources


# ---------------------------------------------------------------------- scan


def test_scan_flags_ai_draft() -> None:
    proc = _run(CHECK, "scan", REFS / "example-ai.md", "--json")
    assert proc.returncode == 3, proc.stderr
    res = json.loads(proc.stdout)
    rules = {r["规则"]: r for r in res["规则"]}
    assert set(res["偏高"]) == {"翻案腔", "顿号罗列过密", "序数词当小标题"}
    for rid in ("Z4", "Z5", "Z8", "Z9", "Z10", "Z12", "Z13", "Z14", "Z15"):
        assert rules[rid]["命中"] >= 1, rid
    assert rules["Z1"]["人类均值"] == 0.22 and rules["Z1"]["命中"] == 2
    assert [p["命中"] for p in rules["Z7"]["位置"]] == ["一、背景", "二、过程", "三、结论"]
    assert {g["项"] for g in res["门槛"]} == {"惊叹号"}
    assert res["聊天残留"][0]["命中"] == "希望以上内容对你有所帮助"
    assert res["黑名单词"] == {"总而言之": 1, "值得注意的是": 1}

    text = _run(CHECK, "scan", REFS / "example-ai.md").stdout
    assert "[偏高] Z1 翻案腔：2 处" in text and "人类均值 0.22" in text
    assert "不能证明作者身份" in text


def test_scan_cleaned_draft_passes() -> None:
    proc = _run(CHECK, "scan", REFS / "example-humanized.md", "--json")
    assert proc.returncode == 0, proc.stdout
    res = json.loads(proc.stdout)
    assert res["偏高"] == [] and res["门槛"] == [] and res["聊天残留"] == []


def test_scan_ignores_code_urls_and_tables(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text(
        "---\ntitle: 不是A而是B\n---\n# 说明\n\n"
        "这是一段很普通的说明文字，用来凑够检查需要的长度，内容本身没有什么特别的地方。"
        "我们先把配置写好，再启动服务，最后看日志里有没有报错。\n\n"
        "```python\n# 不是 bug，而是特性——真的！\nprint('hello, world!')\n```\n\n"
        "| 项 | 值 |\n|---|---|\n| 核心是：| A、B、C、D |\n\n"
        "参考 `a,b` 和 https://example.com/a,b?x=1 这两处。\n",
        encoding="utf-8",
    )
    proc = _run(CHECK, "scan", doc, "--json")
    res = json.loads(proc.stdout)
    assert proc.returncode == 0, proc.stdout
    assert all(r["命中"] == 0 for r in res["规则"])


def test_profile_marks_author_habit(tmp_path: Path) -> None:
    author, draft = tmp_path / "author.md", tmp_path / "draft.md"
    author.write_text(AUTHOR, encoding="utf-8")
    draft.write_text(DRAFT, encoding="utf-8")
    plain = json.loads(_run(CHECK, "scan", draft, "--json").stdout)
    assert plain["偏高"] == ["破折号"]
    calibrated = _run(CHECK, "scan", draft, "--profile", author, "--json")
    assert calibrated.returncode == 0
    dash = next(r for r in json.loads(calibrated.stdout)["规则"] if r["规则"] == "Z4")
    assert dash["判断"] == "作者习惯"

    prof = _run(CHECK, "profile", author)
    assert prof.returncode == 0
    assert "作者本人常用（改稿时不当作 AI 痕迹）：破折号" in prof.stdout
    data = json.loads(_run(CHECK, "profile", author, "--json").stdout)
    assert data["每千字标点"]["破折号"] > 20 and data["每千字标点"]["感叹号"] == 0


def test_scan_english_and_input_errors(tmp_path: Path) -> None:
    en = tmp_path / "en.md"
    en.write_text(
        "# Notes\n\n"
        + "In today's ever-evolving landscape, our platform is not just a tool, but a partner. "
        "It serves as a testament to our commitment — and it plays a pivotal role in helping teams "
        "unlock value. Let's dive into the details. I hope this helps!\n\n" * 3,
        encoding="utf-8",
    )
    res = json.loads(_run(CHECK, "scan", en, "--json").stdout)
    assert res["语言"] == "英文"
    assert {"not just X but Y", "em dash", "AI vocabulary", "chatbot residue"} <= set(res["偏高"])
    short = tmp_path / "short.md"
    short.write_text("你好。", encoding="utf-8")
    assert _run(CHECK, "scan", short).returncode == 1
    assert _run(CHECK, "scan", tmp_path / "missing.md").returncode == 1


# ---------------------------------------------------------------------- diff


def test_diff_accepts_faithful_rewrite() -> None:
    proc = _run(CHECK, "diff", REFS / "example-ai.md", REFS / "example-humanized.md", "--json")
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["变动"] == {}


def test_diff_catches_changed_facts(tmp_path: Path) -> None:
    good = (REFS / "example-humanized.md").read_text(encoding="utf-8")
    bad = (
        good.replace("从 6 小时缩短到 2 分钟", "从 6 小时缩短到 30 秒")
        .replace("有不少疑虑", "没有疑虑")
        .replace("越来越多的企业", "所有企业")
        .replace("## 过程", "## 实施")
        .replace("先把最常见的 20 个问题", "先把最常见的 20 个问题（据《客服白皮书》）")
    )
    path = tmp_path / "bad.md"
    path.write_text(bad, encoding="utf-8")
    proc = _run(CHECK, "diff", REFS / "example-ai.md", path, "--json")
    assert proc.returncode == 3
    changes = json.loads(proc.stdout)["变动"]
    assert changes["数字"] == {"新增": ["30"], "丢失": ["2"]}
    assert changes["引语和书名"]["新增"] == ["《客服白皮书》"]
    assert changes["否定词"]["改稿"] > changes["否定词"]["原稿"]
    assert changes["绝对化"]["新增"] == ["所有"]
    assert "标题" in changes["结构"]

    text = _run(CHECK, "diff", REFS / "example-ai.md", path).stdout
    assert "[必须处理·数字]" in text and "[请确认·绝对化]" in text
