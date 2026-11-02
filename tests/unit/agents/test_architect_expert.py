"""Contract tests for the bundled 架构师专家 (architect) expert."""

from __future__ import annotations

import json
import os
import re
import shutil
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
EXPERT_DIR = LIBRARY / "architect"
SKILLS = {"arch-design", "arch-review", "adr-writer", "capacity-estimate"}
SCAN = EXPERT_DIR / "skills" / "arch-review" / "scripts" / "arch_scan.py"
ADR = EXPERT_DIR / "skills" / "adr-writer" / "scripts" / "adr.py"
CAP = EXPERT_DIR / "skills" / "capacity-estimate" / "scripts" / "capacity.py"
EXAMPLE_ADR = EXPERT_DIR / "skills" / "adr-writer" / "references" / "example-adr.md"


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


def _write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _scan(project: Path, *extra: str) -> tuple[int, dict[str, object]]:
    proc = _run(SCAN, "scan", project, "--json", *extra)
    assert proc.stdout, proc.stderr
    return proc.returncode, json.loads(proc.stdout)


def _edge(res: dict[str, object], src: str, dst: str) -> dict[str, object]:
    return next(e for e in res["依赖"] if e["从"] == src and e["到"] == dst)  # type: ignore[attr-defined]


def test_expert_catalog_manifest_and_skills() -> None:
    catalog = ExpertCatalog(LIBRARY)
    catalog.refresh()
    expert = catalog.get("architect")
    assert expert is not None
    assert expert.summary.label_zh == "架构师专家"
    assert expert.summary.icon_url == "/experts/avatars/architect.svg"
    assert expert.summary.scene in _SCENE_ORDER

    manifest = json.loads((EXPERT_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "architect"
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


def test_avatar_is_bundled() -> None:
    svg = Path(__file__).resolve().parents[3] / "dashboard/public/experts/avatars/architect.svg"
    text = svg.read_text(encoding="utf-8")
    assert 'aria-label="架构师专家"' in text and "bg-architect" in text


def test_mermaid_templates_have_balanced_fences() -> None:
    text = (EXPERT_DIR / "skills/arch-design/references/diagram-templates.md").read_text(
        encoding="utf-8"
    )
    blocks = re.findall(r"```mermaid\n(.*?)```", text, re.DOTALL)
    assert len(blocks) == 6
    assert text.count("```") == 2 * len(blocks)
    assert all(b.lstrip().startswith(("flowchart", "sequenceDiagram")) for b in blocks)


# ---------------------------------------------------------------- arch_scan


PY_PROJECT = {
    "src/shop/__init__.py": "",
    "src/shop/api/__init__.py": "",
    "src/shop/api/routes.py": "from shop.core import orders\nfrom shop.util.text import slug\n",
    "src/shop/core/__init__.py": "",
    "src/shop/core/orders.py": (
        "from __future__ import annotations\n"
        "from typing import TYPE_CHECKING\n"
        "from shop.util import text\n"
        "if TYPE_CHECKING:\n    from shop.api.routes import Request\n"
    ),
    "src/shop/core/pricing.py": "from shop.util.cycle_b import b\n",
    "src/shop/util/__init__.py": "",
    "src/shop/util/text.py": "def slug(s): return s\n",
    "src/shop/util/cycle_b.py": "from shop.core import pricing\n\nb = 1\n",
    "src/shop/util/lazy.py": "def f():\n    from shop.api import routes\n    return routes\n",
    "src/shop/tools/__init__.py": "",
    "src/shop/tools/cli.py": "from . import helper\nfrom ..core import orders\n",
    "src/shop/tools/helper.py": "x = 1\n",
    "tests/test_orders.py": "from shop.core import orders\n",
}


def test_scan_python_components_edges_and_cycles(tmp_path: Path) -> None:
    project = _write(tmp_path / "proj", PY_PROJECT)
    code, res = _scan(project, "--depth", "1")
    assert code == 0
    assert res["包前缀"] == "shop" and res["分组深度"] == 1
    assert {r["组件"] for r in res["组件"]} == {"api", "core", "util", "tools", "(root)"}  # type: ignore[attr-defined]
    assert (
        res["语言"]["Python"]["文件数"] == 13
    )  # top-level tests/ is outside the source root  # type: ignore[index]

    api_core = _edge(res, "api", "core")
    assert api_core["运行时"] == 1 and api_core["仅类型"] == 0
    assert _edge(res, "core", "api")["仅类型"] == 1  # TYPE_CHECKING import
    assert _edge(res, "util", "api")["懒加载"] == 1  # import inside a function
    assert _edge(res, "tools", "core")["运行时"] == 1  # relative import with ..
    assert not any(e["从"] == "tools" and e["到"] == "tools" for e in res["依赖"])  # type: ignore[attr-defined]

    assert len(res["循环依赖"]) == 1  # type: ignore[arg-type]
    cycle = res["循环依赖"][0]  # type: ignore[index]
    assert cycle["文件"] == [
        "src/shop/core/pricing.py".removeprefix("src/shop/"),
        "util/cycle_b.py",
    ]
    assert cycle["涉及组件"] == ["core", "util"]
    assert any(m["组件"] == ["core", "util"] for m in res["双向依赖"])  # type: ignore[attr-defined]
    in_cycle = {r["组件"] for r in res["组件"] if r["在环里"]}  # type: ignore[attr-defined]
    assert in_cycle == {"core", "util"}
    # the lazy import only closes a cycle once lazy imports count
    assert res["仅懒加载才成环"] == [] or all(
        "util/lazy.py" in c["文件"] for c in res["仅懒加载才成环"]
    )  # type: ignore[attr-defined]


def test_scan_include_tests_and_exit_codes(tmp_path: Path) -> None:
    project = _write(
        tmp_path / "proj",
        {**PY_PROJECT, "src/shop/core/test_inline.py": "from shop.util import text\n"},
    )
    _, without = _scan(project, "--depth", "1")
    _, with_tests = _scan(project, "--depth", "1", "--include-tests")
    assert without["语言"]["Python"]["文件数"] == 13  # type: ignore[index]
    assert with_tests["语言"]["Python"]["文件数"] == 14  # type: ignore[index]

    assert _run(SCAN, "scan", project, "--depth", "1").returncode == 0
    assert _run(SCAN, "scan", project, "--depth", "1", "--fail-on-cycle").returncode == 3

    clean = _write(
        tmp_path / "clean",
        {
            "src/app/__init__.py": "",
            "src/app/a/x.py": "",
            "src/app/b/y.py": "from app.a import x\n",
        },
    )
    assert _run(SCAN, "scan", clean, "--depth", "1", "--fail-on-cycle").returncode == 0


def test_scan_layer_violations(tmp_path: Path) -> None:
    project = _write(tmp_path / "proj", PY_PROJECT)
    code, res = _scan(project, "--depth", "1", "--layers", "api,core,util")
    assert code == 3
    pairs = {(v["从"], v["到"]) for v in res["分层违规"]}  # type: ignore[attr-defined]
    assert ("util", "core") in pairs and ("util", "api") in pairs  # inner layer importing outer
    assert ("api", "core") not in pairs
    text = _run(SCAN, "scan", project, "--depth", "1", "--layers", "api,core,util").stdout
    assert "## 分层违规" in text and "util → core" in text

    _, ok = _scan(project, "--depth", "1", "--layers", "tools,api,core")
    assert ok["分层违规"] == []


def test_scan_javascript_and_typescript(tmp_path: Path) -> None:
    project = _write(
        tmp_path / "web",
        {
            "src/pages/home.tsx": "import { fmt } from '../utils/format';\nimport { api } from '@/api/client';\nimport './home.css';\nimport React from 'react';\n",
            "src/utils/format.ts": "import type { Page } from '../pages/home';\nexport const fmt = 1;\n",
            "src/utils/index.ts": "export * from './format';\n",
            "src/api/client.ts": "import { fmt } from '../utils';\nexport const api = () => import('../pages/home');\n",
            "src/hooks/use.ts": "const x = require('../utils/format');\n",
            "src/components/a.test.tsx": "import '../pages/home';\n",
        },
    )
    code, res = _scan(project, "--depth", "1")
    assert code == 0 and res["包前缀"] == ""
    assert _edge(res, "pages", "utils")["运行时"] == 1
    assert _edge(res, "pages", "api")["运行时"] == 1  # '@/' alias
    assert _edge(res, "utils", "pages")["仅类型"] == 1  # import type
    assert _edge(res, "api", "pages")["懒加载"] == 1  # dynamic import()
    assert _edge(res, "api", "utils")["运行时"] == 1  # directory import -> index.ts
    assert _edge(res, "hooks", "utils")["运行时"] == 1  # require()
    assert res["循环依赖"] == []  # the only back edges are type-only or lazy
    assert not any(
        r["组件"] == "components" for r in res["组件"]
    )  # test file skipped  # type: ignore[attr-defined]

    code, res2 = _scan(
        _write(tmp_path / "cyc", {"src/a/x.ts": "import { y } from '../b/y';\n", "src/b/y.ts": "import { x } from '../a/x';\n"}),
        "--depth", "1",
    )  # fmt: skip
    assert len(res2["循环依赖"]) == 1 and res2["循环依赖"][0]["涉及组件"] == ["a", "b"]  # type: ignore[index]


def test_scan_depth_auto_big_files_and_mermaid(tmp_path: Path) -> None:
    files = {f"src/{n}/m.py": "x = 1\n" for n in ("a", "b", "c", "d", "e")}
    files["src/a/big.py"] = "\n".join(f"v{i} = {i}" for i in range(900))
    files["src/a/m2.py"] = "from a import m\n"
    files["src/b/m2.py"] = "from a import m2\nfrom c import m\n"
    project = _write(tmp_path / "proj", files)
    out = tmp_path / "deps" / "graph.md"
    proc = _run(SCAN, "scan", project, "--mermaid", out, "--top", "3")
    assert proc.returncode == 0, proc.stderr
    assert "按前 1 层目录分组" in proc.stdout  # 5 top-level dirs -> auto picks depth 1
    assert "超大文件" in proc.stdout and "a/big.py：900 行" in proc.stdout
    graph = out.read_text(encoding="utf-8")
    assert "flowchart LR" in graph and "b -->|" in graph.replace("n_b ", "b ").replace("n_a", "a")
    assert "虚线" in graph


def test_scan_input_errors_and_skips(tmp_path: Path) -> None:
    assert _run(SCAN, "scan", tmp_path / "missing").returncode == 1
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = _run(SCAN, "scan", empty)
    assert proc.returncode == 1 and "没有找到源码文件" in proc.stderr
    assert _run(SCAN, "scan", empty, "--root", "nope").returncode == 1

    project = _write(
        tmp_path / "p",
        {
            "src/a/x.py": "import b.y\n",
            "src/b/y.py": "def broken(:\n",  # syntax error must not crash the scan
            "src/node_modules/z.js": "x",
            "src/a/gen.d.ts": "x",
            "src/c/main.go": "package c\n",
        },
    )
    code, res = _scan(project, "--depth", "1")
    assert code == 0
    assert res["未分析依赖"] == ["Go"]
    assert res["文件总数"] == 3
    shutil.rmtree(project)


# ---------------------------------------------------------------------- adr


def test_adr_new_numbers_slugs_and_template(tmp_path: Path) -> None:
    d = tmp_path / "adr"
    first = _run(ADR, "new", "用 PostgreSQL 还是 MySQL？", "--dir", d, "--deciders", "张三")
    assert first.returncode == 0, first.stderr
    path = Path(first.stdout.strip())
    assert path.name == "0001-用-postgresql-还是-mysql.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# 0001. 用 PostgreSQL 还是 MySQL？\n")
    assert "- 状态：提议中" in text and "- 决策人：张三" in text
    for section in ("## 背景", "## 备选方案", "## 决策", "### 代价和风险", "## 重新评审条件"):
        assert section in text
    second = Path(_run(ADR, "new", "缓存策略", "--dir", d, "--status", "accepted").stdout.strip())
    assert second.name == "0002-缓存策略.md" and "- 状态：已采纳" in second.read_text(
        encoding="utf-8"
    )

    listing = _run(ADR, "list", "--dir", d).stdout
    assert "| 0001 | 提议中 |" in listing and "| 0002 | 已采纳 |" in listing
    assert "还没有 ADR" in _run(ADR, "list", "--dir", tmp_path / "none").stdout
    assert _run(ADR, "new", "  ", "--dir", d).returncode == 1
    assert _run(ADR, "new", "x", "--dir", d, "--status", "weird").returncode == 1


def test_adr_check_template_vs_accepted_vs_example(tmp_path: Path) -> None:
    d = tmp_path / "adr"
    _run(ADR, "new", "选型", "--dir", d)
    proposed = _run(ADR, "check", "--dir", d)
    assert proposed.returncode == 0 and "还是模板" in proposed.stdout  # only a hint while proposed

    assert _run(ADR, "status", "1", "accepted", "--dir", d).returncode == 0
    accepted = _run(ADR, "check", "--dir", d, "--json")
    assert accepted.returncode == 3
    messages = [
        i["message"] for i in json.loads(accepted.stdout)["问题"] if i["level"] == "必须处理"
    ]
    assert any("背景" in m for m in messages) and any("决策" in m for m in messages)
    assert any("备选方案不足两个" in m for m in messages) and any(
        "代价和风险" in m for m in messages
    )

    good = tmp_path / "good"
    good.mkdir()
    shutil.copy(EXAMPLE_ADR, good / "0001-order-events.md")
    ok = _run(ADR, "check", "--dir", good)
    assert ok.returncode == 0 and "没有发现问题" in ok.stdout
    assert _run(ADR, "check", "--dir", tmp_path / "none").returncode == 1


def test_adr_supersede_status_and_link_checks(tmp_path: Path) -> None:
    d = tmp_path / "adr"
    d.mkdir()
    for n, name in (("0001", "old"), ("0002", "new")):
        shutil.copy(EXAMPLE_ADR, d / f"{n}-{name}.md")
        p = d / f"{n}-{name}.md"
        p.write_text(p.read_text(encoding="utf-8").replace("# 0001.", f"# {n}."), encoding="utf-8")
    assert _run(ADR, "supersede", "1", "2", "--dir", d).returncode == 0
    old = (d / "0001-old.md").read_text(encoding="utf-8")
    new = (d / "0002-new.md").read_text(encoding="utf-8")
    assert "- 状态：已被取代" in old and "- 被取代：0002" in old
    assert "- 取代：0001" in new and "- 状态：已采纳" in new
    assert _run(ADR, "check", "--dir", d).returncode == 0
    assert "请用 supersede" in _run(ADR, "status", "2", "已被取代", "--dir", d).stderr
    assert _run(ADR, "supersede", "1", "1", "--dir", d).returncode == 1
    assert _run(ADR, "supersede", "1", "9", "--dir", d).returncode == 1
    assert _run(ADR, "status", "7", "已采纳", "--dir", d).returncode == 1

    new_path = d / "0002-new.md"  # one-sided link: the replacing record forgets "取代"
    new_path.write_text(new.replace("- 取代：0001\n", ""), encoding="utf-8")
    one_sided = _run(ADR, "check", "--dir", d)
    assert one_sided.returncode == 0 and "取代关系只写了一边" in one_sided.stdout

    broken = old.replace("- 被取代：0002", "- 被取代：0009")
    (d / "0001-old.md").write_text(broken, encoding="utf-8")
    proc = _run(ADR, "check", "--dir", d)
    assert proc.returncode == 3 and "被取代：0009 不存在" in proc.stdout


def test_adr_check_numbering_and_status_errors(tmp_path: Path) -> None:
    d = tmp_path / "adr"
    d.mkdir()
    base = EXAMPLE_ADR.read_text(encoding="utf-8")
    (d / "0001-a.md").write_text(base, encoding="utf-8")
    (d / "0001-b.md").write_text(base, encoding="utf-8")  # duplicate number
    (d / "0004-c.md").write_text(
        base.replace("# 0001.", "# 0009.").replace("已采纳", "做完了"), encoding="utf-8"
    )
    (d / "notes.md").write_text("# 随手记\n", encoding="utf-8")
    (d / "README.md").write_text("# ADR 索引\n", encoding="utf-8")
    proc = _run(ADR, "check", "--dir", d)
    assert proc.returncode == 3
    assert "编号 0001 重复" in proc.stdout
    assert "编号不连续，缺：0002、0003" in proc.stdout
    assert "标题里的编号 0009 和文件名的 0004 不一致" in proc.stdout
    assert "状态“做完了”不合法" in proc.stdout
    assert "notes.md：文件名不符合" in proc.stdout and "README" not in proc.stdout


# ----------------------------------------------------------------- capacity


def test_capacity_estimate_numbers_and_growth() -> None:
    proc = _run(CAP, "estimate", "--dau", "86400", "--requests-per-user", "10", "--peak-factor", "4",
                "--read-ratio", "0.8", "--payload-kb", "10", "--record-kb", "5", "--retention-days", "100",
                "--replicas", "2", "--qps-per-node", "50", "--headroom", "0.2", "--growth", "1", "--json")  # fmt: skip
    assert proc.returncode == 0, proc.stderr
    res = json.loads(proc.stdout)
    now = res["结果"]
    assert now["平均 QPS"] == 10.0 and now["峰值 QPS"] == 40.0
    assert now["读峰值 QPS"] == 32.0 and now["写峰值 QPS"] == 8.0
    assert now["出口带宽峰值 Mbps"] == 2.56  # 32 qps * 10 KB * 8 / 1000
    assert round(now["每天新增数据"], 6) == 0.864  # 86400 users * 2 writes * 5 KB / 1e6 GB
    assert round(now["保留期内数据（含副本）"], 3) == 172.8  # 0.864 GB * 100 days * 2 replicas
    assert (
        now["应用节点数（满足峰值）"] == 1 and now["应用节点数（含 N+1 冗余）"] == 2
    )  # 40 / (50*0.8) = 1
    later = res["一年后（日活增长 100%）"]
    assert later["日活"] == 172800 and later["峰值 QPS"] == 80.0
    assert later["应用节点数（满足峰值）"] == 2 and later["应用节点数（含 N+1 冗余）"] == 3

    text = _run(CAP, "estimate", "--dau", "100000").stdout
    assert "## 假设（换成你自己的数再算）" in text and "- 日活 DAU：100000" in text
    assert "| 每天新增数据 | 400.0 MB |" in text and "要用真实数据校准" in text


def test_capacity_estimate_rejects_bad_inputs() -> None:
    for args in (["--dau", "0"], ["--dau", "10", "--read-ratio", "1.5"], ["--dau", "10", "--headroom", "1"],
                 ["--dau", "10", "--hot-ratio", "-1"], ["--dau", "10", "--growth", "-0.5"],
                 ["--dau", "10", "--qps-per-node", "0"]):  # fmt: skip
        proc = _run(CAP, "estimate", *args)
        assert proc.returncode == 1 and proc.stderr.strip(), args


def test_capacity_sla_and_compose() -> None:
    sla = _run(CAP, "sla", "99.9", "99.99").stdout
    assert "| 99.9% | 1.4 分钟 | 43.2 分钟 | 8.8 小时 |" in sla
    assert "| 99.99% | 8.6 秒 | 4.3 分钟 | 52.6 分钟 |" in sla
    assert "| 99.999% |" in _run(CAP, "sla").stdout
    assert _run(CAP, "sla", "100").returncode == 1

    serial = _run(CAP, "compose", "--serial", "99.9,99.9").stdout
    assert "= 99.8001%" in serial and "整体可用性：99.8001%" in serial
    parallel = _run(CAP, "compose", "--parallel", "99,99").stdout
    assert "= 99.9900%" in parallel and "故障互相独立" in parallel
    both = _run(CAP, "compose", "--serial", "99.9", "--parallel", "99,99").stdout
    assert "整体可用性：99.8900%" in both  # 0.999 * 0.9999
    assert _run(CAP, "compose").returncode == 1
    assert _run(CAP, "compose", "--serial", "abc").returncode == 1
    assert _run(CAP, "compose", "--serial", "101").returncode == 1
