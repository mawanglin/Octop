"""Contract tests for the bundled ppt-designer and flowchart-designer experts."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from octop_harness.backends.workspace import BackendWorkspace

from octop.infra.agents.experts.catalog import (
    WORKSPACE_MANIFEST_PATH,
    ExpertCatalog,
    default_library_root,
    discover_seed_paths,
    seed_expert_directory,
)

LIBRARY = default_library_root()
PPT_DIR = LIBRARY / "ppt-designer"
FLOW_DIR = LIBRARY / "flowchart-designer"
PPT_SCRIPTS = PPT_DIR / "skills" / "ppt-build" / "scripts"
EDIT_SCRIPT = PPT_DIR / "skills" / "ppt-edit" / "scripts" / "edit_deck.py"
DRAWIO_SCRIPT = FLOW_DIR / "skills" / "drawio-diagram" / "scripts" / "drawio_from_spec.py"
MERMAID_SCRIPT = FLOW_DIR / "skills" / "diagram-export" / "scripts" / "render_mermaid.py"

EXPERTS = {
    "ppt-designer": ("PPT 设计专家", {"ppt-outline", "ppt-build", "ppt-edit"}),
    "flowchart-designer": (
        "流程图设计专家",
        {"mermaid-diagram", "diagram-export", "drawio-diagram"},
    ),
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


def _load(script: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_test_{script.stem}", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


@pytest.mark.parametrize("expert_id", sorted(EXPERTS))
def test_expert_catalog_and_manifest(expert_id: str) -> None:
    label_zh, _ = EXPERTS[expert_id]
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
    assert all(
        q["title"]["zh"] and q["title"]["en"] and q["prompt"]["zh"] and q["prompt"]["en"]
        for q in manifest["quick_prompts"]
    )
    assert len(manifest["task_examples"]["zh"]) == len(manifest["task_examples"]["en"]) == 6


@pytest.mark.parametrize("expert_id", sorted(EXPERTS))
def test_expert_skills_frontmatter_and_soul_references(expert_id: str) -> None:
    _, skills = EXPERTS[expert_id]
    expert_dir = LIBRARY / expert_id
    assert {p.name for p in (expert_dir / "skills").iterdir() if p.is_dir()} == skills
    soul = (expert_dir / "SOUL.md").read_text(encoding="utf-8")
    for name in skills:
        raw = (expert_dir / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert raw.startswith(f"---\nname: {name}\n")
        assert "\ndescription:" in raw.split("---", 2)[1]
        assert f"`{name}`" in soul


@pytest.mark.parametrize("expert_id", sorted(EXPERTS))
async def test_expert_seeds_into_workspace(tmp_path: Path, expert_id: str) -> None:
    expert_dir = LIBRARY / expert_id
    workspace = BackendWorkspace(
        LocalShellBackend(root_dir=str(tmp_path), virtual_mode=False), tmp_path
    )
    paths = discover_seed_paths(expert_dir)
    copied = await seed_expert_directory(expert_dir=expert_dir, workspace=workspace)
    assert copied == len(paths) + 1
    for rel in paths:
        assert await workspace.adownload_bytes(rel) == (expert_dir / rel).read_bytes()
    assert (
        await workspace.adownload_bytes(WORKSPACE_MANIFEST_PATH)
        == (expert_dir / "manifest.json").read_bytes()
    )


def test_build_deck_example_has_no_warnings_or_issues(tmp_path: Path) -> None:
    example = PPT_DIR / "skills" / "ppt-build" / "references" / "example-deck.json"
    out = tmp_path / "deck.pptx"
    result = _run(PPT_SCRIPTS / "build_deck.py", example, "-o", out)
    assert result.returncode == 0, result.stderr
    assert "警告" not in result.stdout

    inspected = _run(PPT_SCRIPTS / "inspect_deck.py", out, "--json")
    assert inspected.returncode == 0, inspected.stdout
    report = json.loads(inspected.stdout)
    expected = json.loads(example.read_text(encoding="utf-8"))
    assert report["slide_count"] == len(expected["slides"])
    assert report["slides"][0]["title"] == expected["slides"][0]["title"]
    assert report["slides"][0]["notes"] == expected["slides"][0]["notes"]


@pytest.mark.parametrize("theme", ["tech-dark", "fresh-green", "warm-orange", "minimal-gray"])
def test_build_deck_all_themes(tmp_path: Path, theme: str) -> None:
    example = PPT_DIR / "skills" / "ppt-build" / "references" / "example-deck.json"
    result = _run(
        PPT_SCRIPTS / "build_deck.py", example, "-o", tmp_path / "d.pptx", "--theme", theme
    )
    assert result.returncode == 0, result.stderr


def test_build_deck_reports_spec_errors_and_overflow(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"slides": [{"layout": "nope"}]}), encoding="utf-8")
    result = _run(PPT_SCRIPTS / "build_deck.py", bad, "-o", tmp_path / "bad.pptx")
    assert result.returncode == 1
    assert "第 1 页" in result.stderr
    assert not (tmp_path / "bad.pptx").exists()

    crowded = tmp_path / "crowded.json"
    bullets = ["这是一条非常长的要点，用来测试文字溢出检查是否能够正常给出警告信息" * 2] * 12
    crowded.write_text(
        json.dumps(
            {
                "colors": {"primary": "#C8102E"},
                "slides": [{"layout": "bullets", "title": "要点过多", "bullets": bullets}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = _run(PPT_SCRIPTS / "build_deck.py", crowded, "-o", tmp_path / "crowded.pptx")
    assert result.returncode == 0, result.stderr
    assert "溢出" in result.stdout


def test_edit_deck_round_trip(tmp_path: Path) -> None:
    example = PPT_DIR / "skills" / "ppt-build" / "references" / "example-deck.json"
    src = tmp_path / "src.pptx"
    assert _run(PPT_SCRIPTS / "build_deck.py", example, "-o", src).returncode == 0
    out = tmp_path / "out.pptx"
    steps = [
        ("-o", out, "replace", "--find", "Q4", "--with", "第四季度"),
        ("--in-place", "duplicate", "--slide", "6"),
        ("--in-place", "delete", "--slides", "1"),
        ("--in-place", "notes", "--slide", "1", "--text", "新备注"),
    ]
    for i, step in enumerate(steps):
        result = _run(EDIT_SCRIPT, src if i == 0 else out, *step)
        assert result.returncode == 0, result.stderr
    missing = _run(
        EDIT_SCRIPT, out, "--in-place", "replace", "--find", "不存在的文字", "--with", "x"
    )
    assert missing.returncode == 1

    report = json.loads(_run(PPT_SCRIPTS / "inspect_deck.py", out, "--json").stdout)
    original = json.loads(example.read_text(encoding="utf-8"))
    assert report["slide_count"] == len(original["slides"])  # +1 duplicate, -1 delete
    assert report["slides"][0]["notes"] == "新备注"
    all_text = json.dumps(report, ensure_ascii=False)
    assert "第四季度" in all_text
    assert "Q4" not in all_text


def test_drawio_from_spec_example(tmp_path: Path) -> None:
    example = FLOW_DIR / "skills" / "drawio-diagram" / "references" / "example-flow.json"
    out = tmp_path / "flow.drawio"
    mmd = tmp_path / "flow.mmd"
    result = _run(DRAWIO_SCRIPT, example, "-o", out, "--mermaid", mmd)
    assert result.returncode == 0, result.stderr

    spec = json.loads(example.read_text(encoding="utf-8"))
    cells = ET.parse(out).getroot().findall(".//mxCell")
    vertices = [c for c in cells if c.get("vertex") == "1"]
    edges = [c for c in cells if c.get("edge") == "1"]
    assert len(vertices) == len(spec["nodes"]) + len(spec["lanes"])
    assert len(edges) == len(spec["edges"])
    # The loop-back edge gets explicit waypoints so it routes around nodes.
    back = next(c for c in edges if c.get("value") == "否，退回补充")
    assert back.find("mxGeometry/Array") is not None

    source = mmd.read_text(encoding="utf-8")
    assert source.startswith("flowchart LR\n")
    assert "subgraph lane1" in source
    # Spec ids such as "end" are Mermaid keywords and must not leak into the source.
    assert "  end([" not in source
    assert "-.->" in source


def test_drawio_from_spec_rejects_dangling_edges(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"nodes": [{"id": "a"}], "edges": [{"from": "a", "to": "zzz"}]}),
        encoding="utf-8",
    )
    result = _run(DRAWIO_SCRIPT, bad, "-o", tmp_path / "bad.drawio")
    assert result.returncode == 1
    assert "zzz" in result.stderr


def test_render_mermaid_uses_local_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load(MERMAID_SCRIPT)
    local = tmp_path / "mermaid.min.js"
    local.write_text("// stub", encoding="utf-8")
    monkeypatch.setenv("OCTOP_MERMAID_JS", str(local))
    assert module.resolve_mermaid_js(None) == local
    with pytest.raises(FileNotFoundError):
        module.resolve_mermaid_js(str(tmp_path / "missing.js"))


def test_render_mermaid_requires_output_or_check(tmp_path: Path) -> None:
    src = tmp_path / "a.mmd"
    src.write_text("flowchart TD\n  a --> b\n", encoding="utf-8")
    result = _run(MERMAID_SCRIPT, src)
    assert result.returncode == 2  # argparse usage error
    assert "--check" in result.stderr
