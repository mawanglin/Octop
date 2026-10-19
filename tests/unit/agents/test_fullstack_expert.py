"""Contract tests for the bundled 全栈开发专家 (fullstack-dev) expert."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

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
EXPERT_DIR = LIBRARY / "fullstack-dev"
SKILLS = {"code-check", "project-scaffold", "dev-workflow"}
SCAFFOLD = EXPERT_DIR / "skills" / "project-scaffold" / "scripts" / "scaffold.py"
CHECK = EXPERT_DIR / "skills" / "code-check" / "scripts" / "code_check.py"

needs_node = pytest.mark.skipif(
    shutil.which("node") is None or shutil.which("npm") is None, reason="node/npm not installed"
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
        timeout=300,
    )


def _check_json(path: Path, *extra: str) -> tuple[int, dict[str, object]]:
    proc = _run(CHECK, "run", path, "--json", *extra)
    assert proc.stdout, proc.stderr
    return proc.returncode, json.loads(proc.stdout)


def _statuses(report: dict[str, object]) -> dict[str, str]:
    checks = report["checks"]
    assert isinstance(checks, list)
    return {c["name"]: c["status"] for c in checks}


def test_expert_catalog_manifest_and_skills() -> None:
    catalog = ExpertCatalog(LIBRARY)
    catalog.refresh()
    expert = catalog.get("fullstack-dev")
    assert expert is not None
    assert expert.summary.label_zh == "全栈开发专家"
    assert expert.summary.icon_url == "/experts/avatars/fullstack-dev.svg"

    manifest = json.loads((EXPERT_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "fullstack-dev"
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


# ----------------------------------------------------------------- scaffold


def test_scaffold_lists_templates() -> None:
    proc = _run(SCAFFOLD, "list")
    assert proc.returncode == 0, proc.stderr
    for name in ("python-cli", "fastapi", "node-api", "react-vite", "static-web"):
        assert f"- {name}：" in proc.stdout


def test_scaffold_refuses_bad_name_and_non_empty_target(tmp_path: Path) -> None:
    assert _run(SCAFFOLD, "new", "python-cli", "1bad", "-o", tmp_path).returncode == 1
    assert _run(SCAFFOLD, "new", "nope", "demo", "-o", tmp_path).returncode == 1
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "keep.txt").write_text("mine", encoding="utf-8")
    proc = _run(SCAFFOLD, "new", "python-cli", "demo", "-o", tmp_path)
    assert proc.returncode == 1
    assert "不会覆盖" in proc.stderr
    assert sorted(p.name for p in (tmp_path / "demo").iterdir()) == ["keep.txt"]


def test_scaffold_frontend_templates_are_well_formed(tmp_path: Path) -> None:
    assert (
        _run(SCAFFOLD, "new", "react-vite", "web", "-o", tmp_path, "--title", "看板").returncode
        == 0
    )
    pkg = json.loads((tmp_path / "web" / "package.json").read_text(encoding="utf-8"))
    assert pkg["name"] == "web"
    assert {"dev", "build", "typecheck"} <= set(pkg["scripts"])
    json.loads((tmp_path / "web" / "tsconfig.json").read_text(encoding="utf-8"))
    assert "<title>看板</title>" in (tmp_path / "web" / "index.html").read_text(encoding="utf-8")

    assert _run(SCAFFOLD, "new", "static-web", "site", "-o", tmp_path).returncode == 0
    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert 'name="viewport"' in html and 'src="app.js"' in html


@pytest.mark.parametrize("template", ["python-cli", "fastapi"])
def test_python_templates_pass_their_own_checks(tmp_path: Path, template: str) -> None:
    proc = _run(SCAFFOLD, "new", template, "demo-app", "-o", tmp_path, "--title", "演示")
    assert proc.returncode == 0, proc.stderr
    root = tmp_path / "demo-app"
    code, report = _check_json(root)
    statuses = _statuses(report)
    assert code == 0, statuses
    assert statuses["Python 语法检查"] == "通过"
    assert statuses["Python 测试（pytest）"] == "通过"
    # Checks must not leave caches behind in the user's project.
    assert not {".ruff_cache", ".mypy_cache", ".pytest_cache"} & {p.name for p in root.iterdir()}


@needs_node
def test_node_template_passes_its_own_tests(tmp_path: Path) -> None:
    assert _run(SCAFFOLD, "new", "node-api", "api", "-o", tmp_path).returncode == 0
    code, report = _check_json(tmp_path / "api")
    assert code == 0, report
    assert _statuses(report) == {"Node 测试（npm run test）": "通过"}


# --------------------------------------------------------------- code check


def _broken_python(root: Path) -> None:
    (root / "tests").mkdir(parents=True)
    (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (root / "oops.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    (root / "tests" / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npythonpath = ["."]\n', encoding="utf-8"
    )


def test_code_check_reports_failures(tmp_path: Path) -> None:
    _broken_python(tmp_path)
    proc = _run(CHECK, "run", tmp_path, "--tail", "10")
    assert proc.returncode == 3
    assert "[失败] Python 语法检查" in proc.stdout
    assert "oops.py:1" in proc.stdout
    assert "[失败] Python 测试（pytest）" in proc.stdout
    assert "test_add" in proc.stdout

    code, report = _check_json(tmp_path, "--only", "test")
    assert code == 3
    assert _statuses(report) == {"Python 测试（pytest）": "失败"}


def test_code_check_detect_and_input_errors(tmp_path: Path) -> None:
    _broken_python(tmp_path)
    proc = _run(CHECK, "detect", tmp_path)
    assert proc.returncode == 0
    assert "Python 语法检查：将运行" in proc.stdout
    assert not (tmp_path / "__pycache__").exists()

    assert _run(CHECK, "run", tmp_path, "--only", "nope").returncode == 1
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = _run(CHECK, "run", empty)
    assert proc.returncode == 1
    assert "没有识别到" in proc.stderr


def test_code_check_skips_node_without_installed_deps(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "w",
                "scripts": {"test": "vitest run", "build": "vite build"},
                "devDependencies": {"vite": "^5.4.0"},
            }
        ),
        encoding="utf-8",
    )
    code, report = _check_json(tmp_path)
    assert code == 0
    checks = report["checks"]
    assert isinstance(checks, list)
    assert {c["status"] for c in checks} == {"跳过"}
    assert all("install" in c["output"] or "Node.js" in c["output"] for c in checks)
