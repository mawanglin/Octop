#!/usr/bin/env python3
"""代码仓库架构扫描：按目录划分组件，统计组件之间的 import 依赖，找出循环依赖、分层违规、枢纽组件和超大文件，并输出 Mermaid 依赖图。

Usage:
    python scripts/arch_scan.py scan 项目目录 [--depth auto|1|2|3] [--root 子目录] [--exclude a,b]
                                [--layers cli,api,infra] [--include-tests] [--top 10]
                                [--mermaid 图.md] [--max-edges 40] [--json] [--fail-on-cycle]

分析对象：
  Python        ast 解析 import（绝对、相对、函数内的懒加载、TYPE_CHECKING 里的类型引用都分开统计）
  JS / TS       import / export … from / require() / import()，相对路径和 @/ 别名（指向 src）
  其他语言      只统计文件数和行数，不分析依赖
组件 = 源码根目录下前 --depth 层目录（默认 auto：挑 1～3 中第一个能分出 5 个以上组件的）；
源码根默认是 src/（如果有），再往下只有一个包目录时自动进入（如 src/octop）。
--layers 从外层到内层列出组件名，内层 import 外层算违规（例：cli,api,infra,utils 表示 infra 不能 import api）。
循环依赖按文件找（只看模块顶层 import，运行时真的会加载的）；只有算上函数内懒加载才成环的单独列出，严重程度低；
组件之间的双向依赖另列。
Exit codes: 0 正常, 3 有分层违规，或 --fail-on-cycle 且有循环依赖, 1 输入错误。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "build",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".next",
    "target",
    "site-packages",
    ".idea",
    ".vscode",
    "coverage",
    ".cache",
    "out",
    ".turbo",
    ".nuxt",
    "vendor",
}
TEST_DIR_NAMES = {"tests", "test", "__tests__", "spec", "specs", "e2e"}
NOT_SOURCE_DIRS = TEST_DIR_NAMES | {
    "docs",
    "doc",
    "scripts",
    "examples",
    "tools",
    "bin",
    "migrations",
}
JS_EXT = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
LANG_BY_EXT = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".swift": "Swift",
    ".scala": "Scala",
    ".vue": "Vue",
}
BIG_FILE = 800
JS_IMPORT = re.compile(
    r"""(?:^|[\s;])(?:import|export)\s+(?P<type>type\s+)?(?:[^'"`;]*?\sfrom\s+)?['"](?P<a>[^'"]+)['"]"""
    r"""|require\(\s*['"](?P<b>[^'"]+)['"]\s*\)|import\(\s*['"](?P<c>[^'"]+)['"]\s*\)""",
)


@dataclass
class Edge:
    runtime: int = 0
    lazy: int = 0
    typing: int = 0
    samples: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.runtime + self.lazy + self.typing


@dataclass
class SourceFile:
    path: Path
    rel: tuple[str, ...]
    lang: str
    loc: int


def is_test_path(rel: tuple[str, ...]) -> bool:
    name = rel[-1]
    return (
        any(p in TEST_DIR_NAMES for p in rel[:-1])
        or name.startswith("test_")
        or name.endswith(
            ("_test.py", ".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.tsx", ".spec.js")
        )
        or name == "conftest.py"
    )


def discover(base: Path, exclude: set[str], include_tests: bool) -> list[SourceFile]:
    out: list[SourceFile] = []
    stack = [base]
    while stack:
        cur = stack.pop()
        try:
            entries = sorted(cur.iterdir())
        except OSError:
            continue
        for p in entries:
            if p.is_symlink():
                continue
            if p.is_dir():
                if p.name in SKIP_DIRS or p.name in exclude or p.name.endswith(".egg-info"):
                    continue
                stack.append(p)
            elif p.suffix in LANG_BY_EXT:
                rel = p.relative_to(base).parts
                if not include_tests and is_test_path(rel):
                    continue
                if p.name.endswith(".d.ts"):
                    continue
                try:
                    loc = sum(
                        1
                        for line in p.read_text(encoding="utf-8", errors="replace").splitlines()
                        if line.strip()
                    )
                except OSError:
                    continue
                out.append(SourceFile(p, rel, LANG_BY_EXT[p.suffix], loc))
    return out


def pick_base(project: Path, root: str | None) -> tuple[Path, str]:
    """Return (source root, package prefix that absolute imports use)."""
    if root:
        base = (project / root).resolve()
        if not base.is_dir():
            raise SystemExit(f"--root 目录不存在：{project / root}")
        return base, ""
    base = project
    if (project / "src").is_dir():
        base = project / "src"
    kids = [
        p
        for p in base.iterdir()
        if p.name not in SKIP_DIRS
        and not p.name.startswith(".")
        and not p.name.endswith(".egg-info")
    ]
    dirs = [p for p in kids if p.is_dir() and p.name not in NOT_SOURCE_DIRS]
    files = [p for p in kids if p.is_file() and p.suffix in LANG_BY_EXT and p.name != "__init__.py"]
    if len(dirs) == 1 and not files and (dirs[0] / "__init__.py").is_file():
        return dirs[0], dirs[0].name
    return base, ""


def component_of(dirs: tuple[str, ...], depth: int) -> str:
    return "/".join(dirs[:depth]) if dirs else "(root)"


def count_components(files: list[SourceFile], depth: int) -> int:
    return len({component_of(f.rel[:-1], depth) for f in files})


def choose_depth(files: list[SourceFile], want: str) -> int:
    if want != "auto":
        return int(want)
    for d in (1, 2, 3):
        if count_components(files, d) >= 5:
            return d
    return 3 if count_components(files, 3) > count_components(files, 1) else 1


class PyImports(ast.NodeVisitor):
    def __init__(self) -> None:
        self.found: list[tuple[str, int, list[str], str]] = []  # (module, level, names, kind)
        self._func = 0
        self._typing = 0

    def _kind(self) -> str:
        if self._typing:
            return "typing"
        return "lazy" if self._func else "runtime"

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._func += 1
        self.generic_visit(node)
        self._func -= 1

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_If(self, node: ast.If) -> None:
        test = ast.unparse(node.test)
        if test in ("TYPE_CHECKING", "typing.TYPE_CHECKING"):
            self._typing += 1
            for child in node.body:
                self.visit(child)
            self._typing -= 1
            for child in node.orelse:
                self.visit(child)
        else:
            self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.found.append((alias.name, 0, [], self._kind()))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.found.append(
            (node.module or "", node.level, [a.name for a in node.names], self._kind())
        )


def py_module_files(files: list[SourceFile]) -> dict[tuple[str, ...], SourceFile]:
    """Dotted-module path (relative to the source root) -> the file that defines it."""
    out: dict[tuple[str, ...], SourceFile] = {}
    for f in files:
        if f.lang == "Python":
            out[f.rel[:-1] + (() if f.rel[-1] == "__init__.py" else (f.rel[-1][:-3],))] = f
    return out


def py_edges(
    f: SourceFile, mods: dict[tuple[str, ...], SourceFile], prefix: str
) -> list[tuple[SourceFile, str, str]]:
    """Internal imports of one Python file as (target file, kind, spec)."""
    try:
        tree = ast.parse(f.path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    v = PyImports()
    v.visit(tree)
    out: list[tuple[SourceFile, str, str]] = []
    file_dir = f.rel[:-1]
    for module, level, names, kind in v.found:
        mparts = tuple(p for p in module.split(".") if p)
        if level:
            up = level - 1
            if up > len(file_dir):
                continue
            parts = (file_dir[: len(file_dir) - up] if up else file_dir) + mparts
        elif prefix:
            if not mparts or mparts[0] != prefix:
                continue
            parts = mparts[1:]
        else:
            parts = mparts
        hits = [mods[parts + (n,)] for n in names if parts + (n,) in mods]
        if not hits and parts in mods:
            hits = [mods[parts]]
        elif not hits and not parts and () in mods:
            hits = [mods[()]]
        for t in hits:
            out.append((t, kind, ".".join(mparts) or "." * level))
    return out


def js_module_files(files: list[SourceFile]) -> dict[tuple[str, ...], SourceFile]:
    out: dict[tuple[str, ...], SourceFile] = {}
    for f in files:
        if f.lang in ("JavaScript", "TypeScript"):
            stem = re.sub(r"\.[cm]?[jt]sx?$", "", f.rel[-1])
            out[f.rel[:-1] + (stem,)] = f
            if stem == "index":
                out.setdefault(f.rel[:-1], f)
    return out


def js_edges(
    f: SourceFile, mods: dict[tuple[str, ...], SourceFile]
) -> list[tuple[SourceFile, str, str]]:
    text = f.path.read_text(encoding="utf-8", errors="replace")
    out: list[tuple[SourceFile, str, str]] = []
    for m in JS_IMPORT.finditer(text):
        spec = m.group("a") or m.group("b") or m.group("c")
        if not spec:
            continue
        kind = "lazy" if m.group("c") else "typing" if m.group("type") else "runtime"
        if spec.startswith("@/"):
            cur: list[str] | None = [p for p in spec[2:].split("/") if p]
        elif spec.startswith("."):
            cur = list(f.rel[:-1])
            for seg in spec.split("/"):
                if seg == "..":
                    if not cur:
                        cur = None
                        break
                    cur.pop()
                elif seg not in (".", ""):
                    cur.append(seg)
        else:
            continue
        if not cur:
            continue
        key = tuple(cur)
        target = mods.get(key) or mods.get(key[:-1] + (re.sub(r"\.[cm]?[jt]sx?$", "", key[-1]),))
        if target is not None:
            out.append((target, kind, spec))
    return out


def tarjan(nodes: list[str], adj: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components with more than one node (iterative, so deep chains are safe)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on: set[str] = set()
    stack: list[str] = []
    sccs: list[list[str]] = []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        work = [(root, iter(sorted(adj.get(root, ()))))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on.add(root)
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(sorted(adj.get(w, ())))))
                    advanced = True
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[v])
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1:
                    sccs.append(sorted(comp))
    return sorted(sccs, key=lambda c: (-len(c), c))


def layer_index(comp: str, layers: list[str]) -> int | None:
    for i, name in enumerate(layers):
        if comp == name or comp.startswith(name + "/"):
            return i
    return None


def fid(f: SourceFile) -> str:
    return "/".join(f.rel)


def cycle_info(cycles: list[list[str]], comp: dict[str, str]) -> list[dict[str, object]]:
    return [
        {"文件数": len(c), "文件": c[:8], "涉及组件": sorted({comp[x] for x in c})} for c in cycles
    ]


def scan(
    project: Path,
    depth_opt: str,
    root: str | None,
    exclude: set[str],
    include_tests: bool,
    layers: list[str],
) -> dict[str, object]:
    base, prefix = pick_base(project, root)
    files = discover(base, exclude, include_tests)
    if not files:
        raise SystemExit(f"{base} 下没有找到源码文件")
    analyzable = [f for f in files if f.lang in ("Python", "JavaScript", "TypeScript")]
    depth = choose_depth(analyzable or files, depth_opt)
    comp = {fid(f): component_of(f.rel[:-1], depth) for f in files}
    py_mods, js_mods = py_module_files(files), js_module_files(files)

    comp_files: dict[str, list[SourceFile]] = defaultdict(list)
    for f in files:
        comp_files[comp[fid(f)]].append(f)

    file_edges: dict[tuple[str, str], Edge] = defaultdict(Edge)
    edges: dict[tuple[str, str], Edge] = defaultdict(Edge)
    for f in analyzable:
        sid = fid(f)
        items = py_edges(f, py_mods, prefix) if f.lang == "Python" else js_edges(f, js_mods)
        for target, kind, spec in items:
            tid = fid(target)
            if tid == sid:
                continue
            setattr(file_edges[(sid, tid)], kind, getattr(file_edges[(sid, tid)], kind) + 1)
            if comp[sid] != comp[tid]:
                e = edges[(comp[sid], comp[tid])]
                setattr(e, kind, getattr(e, kind) + 1)
                if len(e.samples) < 3:
                    e.samples.append(f"{sid} → {spec}")

    fnodes = sorted(fid(f) for f in analyzable)
    strict_adj: dict[str, set[str]] = defaultdict(set)
    all_adj: dict[str, set[str]] = defaultdict(set)
    for (a, b), e in file_edges.items():
        if e.runtime:
            strict_adj[a].add(b)
        if e.runtime or e.lazy:
            all_adj[a].add(b)
    strict = tarjan(fnodes, strict_adj)
    lazy_only = [c for c in tarjan(fnodes, all_adj) if c not in strict]
    in_cycle = {comp[x] for c in strict for x in c}

    nodes = sorted(comp_files)
    fan_out: dict[str, set[str]] = defaultdict(set)
    fan_in: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        fan_out[a].add(b)
        fan_in[b].add(a)
    table = []
    for n in nodes:
        ce, ca = len(fan_out[n]), len(fan_in[n])
        table.append(
            {
                "组件": n,
                "文件数": len(comp_files[n]),
                "代码行": sum(f.loc for f in comp_files[n]),
                "依赖了": ce,
                "被依赖": ca,
                "不稳定度": round(ce / (ce + ca), 2) if ce + ca else None,
                "在环里": n in in_cycle,
            }
        )
    table.sort(key=lambda r: (-int(r["代码行"]), str(r["组件"])))  # type: ignore[call-overload]

    mutual = [
        {"组件": [a, b], f"{a}→{b}": e.runtime, f"{b}→{a}": edges[(b, a)].runtime}
        for (a, b), e in sorted(edges.items())
        if a < b and (b, a) in edges and e.runtime and edges[(b, a)].runtime
    ]
    violations = []
    for (a, b), e in sorted(edges.items()):
        if not layers:
            break
        ia, ib = layer_index(a, layers), layer_index(b, layers)
        if ia is not None and ib is not None and ia > ib and (e.runtime or e.lazy):
            violations.append({"从": a, "到": b, "次数": e.runtime + e.lazy, "示例": e.samples})

    langs: dict[str, dict[str, int]] = defaultdict(lambda: {"文件数": 0, "代码行": 0})
    for f in files:
        langs[f.lang]["文件数"] += 1
        langs[f.lang]["代码行"] += f.loc
    big = sorted((f for f in files if f.loc >= BIG_FILE), key=lambda f: -f.loc)
    hubs = [r["组件"] for r in table if int(r["依赖了"]) >= 5 and int(r["被依赖"]) >= 5]  # type: ignore[call-overload]

    return {
        "源码根": str(base),
        "包前缀": prefix,
        "分组深度": depth,
        "语言": dict(sorted(langs.items(), key=lambda kv: -kv[1]["代码行"])),
        "未分析依赖": sorted(
            {lang for lang in langs if lang not in ("Python", "JavaScript", "TypeScript")}
        ),
        "文件总数": len(files),
        "代码行总数": sum(f.loc for f in files),
        "组件": table,
        "依赖": [
            {
                "从": a,
                "到": b,
                "运行时": e.runtime,
                "懒加载": e.lazy,
                "仅类型": e.typing,
                "示例": e.samples,
            }
            for (a, b), e in sorted(edges.items(), key=lambda kv: (-kv[1].total, kv[0]))
        ],
        "循环依赖": cycle_info(strict, comp),
        "仅懒加载才成环": cycle_info(lazy_only, comp),
        "双向依赖": mutual,
        "分层违规": violations,
        "枢纽组件": hubs,
        "超大文件": [{"文件": fid(f), "代码行": f.loc} for f in big[:15]],
    }


def mermaid(res: dict[str, object], max_edges: int) -> str:
    def nid(n: str) -> str:
        return "n_" + re.sub(r"[^0-9A-Za-z]", "_", n)

    cyc = {r["组件"] for r in res["组件"] if r["在环里"]}  # type: ignore[attr-defined]
    edges = res["依赖"]  # type: ignore[assignment]
    shown = edges[:max_edges]  # type: ignore[index]
    nodes: set[str] = set()
    for e in shown:
        nodes.update((e["从"], e["到"]))
    lines = ["```mermaid", "flowchart LR"]
    sizes = {r["组件"]: r for r in res["组件"]}  # type: ignore[attr-defined]
    for n in sorted(nodes):
        r = sizes[n]
        lines.append(f'    {nid(n)}["{n}<br/>{r["文件数"]} 文件 / {r["代码行"]} 行"]')
    for e in shown:
        n = e["运行时"] + e["懒加载"] + e["仅类型"]
        arrow = "-->" if e["运行时"] else "-.->"
        lines.append(f"    {nid(e['从'])} {arrow}|{n}| {nid(e['到'])}")
    for n in sorted(nodes & cyc):
        lines.append(f"    style {nid(n)} fill:#fee2e2,stroke:#b91c1c")
    lines.append("```")
    if len(edges) > max_edges:  # type: ignore[arg-type]
        lines.append(f"\n> 依赖共 {len(edges)} 条，图里只画了次数最多的 {max_edges} 条。")  # type: ignore[arg-type]
    lines.append(
        "\n> 实线是模块顶层 import，虚线是只在函数内懒加载或只做类型引用；红色是含有文件级循环依赖的组件；线上的数字是 import 语句条数。"
    )
    return "\n".join(lines)


def render_cycles(cycles: list[dict[str, object]], limit: int = 6) -> list[str]:
    out = []
    for c in cycles[:limit]:
        files = "、".join(c["文件"])  # type: ignore[arg-type]
        more = (
            f" 等共 {c['文件数']} 个文件"
            if int(c["文件数"]) > len(c["文件"])
            else f"（{c['文件数']} 个文件）"
        )  # type: ignore[arg-type,call-overload]
        out.append(f"- {files}{more}；涉及组件：{'、'.join(c['涉及组件'])}")  # type: ignore[arg-type]
    if len(cycles) > limit:
        out.append(f"- 另有 {len(cycles) - limit} 个环，--json 可看全部")
    return out


def render(res: dict[str, object], top: int) -> str:
    out = ["# 架构扫描结果", ""]
    out.append(
        f"源码根：{res['源码根']}（包前缀：{res['包前缀'] or '无'}；按前 {res['分组深度']} 层目录分组）"
    )
    langs = "，".join(
        f"{k} {v['文件数']} 个文件 / {v['代码行']} 行" for k, v in res["语言"].items()
    )  # type: ignore[attr-defined]
    out.append(f"语言：{langs}；合计 {res['文件总数']} 个文件、{res['代码行总数']} 行（不含空行）")
    if res["未分析依赖"]:
        out.append(f"只统计了规模、没有分析依赖的语言：{'、'.join(res['未分析依赖'])}")  # type: ignore[arg-type]
    shown = max(top, 1) * 2
    out += [
        "",
        "## 组件",
        "",
        "| 组件 | 文件数 | 代码行 | 依赖了 | 被依赖 | 不稳定度 | 含循环依赖 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in res["组件"][:shown]:  # type: ignore[index]
        inst = "-" if r["不稳定度"] is None else r["不稳定度"]
        out.append(
            f"| {r['组件']} | {r['文件数']} | {r['代码行']} | {r['依赖了']} | {r['被依赖']} | {inst} | {'是' if r['在环里'] else ''} |"
        )
    if len(res["组件"]) > shown:  # type: ignore[arg-type]
        out.append(
            f"\n（共 {len(res['组件'])} 个组件，只列出代码行最多的 {shown} 个；--json 可看全部）"
        )  # type: ignore[arg-type]
    out.append(
        "\n不稳定度 = 依赖了 /（依赖了 + 被依赖）：越接近 0 越被大家依赖、越不该随便改；越接近 1 越依赖别人、越容易跟着变。"
    )
    out += ["", "## 循环依赖（文件之间，模块顶层 import）", ""]
    if res["循环依赖"]:
        out += render_cycles(res["循环依赖"])  # type: ignore[arg-type]
        out.append(
            "\n环里的文件没法单独理解、测试和替换。先找环里依赖最少的那条，改成依赖接口，或把共用部分抽到环外。"
        )
    else:
        out.append("没有发现。")
    if res["仅懒加载才成环"]:
        out += ["", "算上函数内懒加载后，还有这些环（严重程度较低，但说明依赖方向有问题）：", ""]
        out += render_cycles(res["仅懒加载才成环"], 4)  # type: ignore[arg-type]
    if res["双向依赖"]:
        out += ["", "## 组件之间的双向依赖", ""]
        for m in res["双向依赖"][:top]:  # type: ignore[index]
            a, b = m["组件"]
            out.append(f"- {a} ⇄ {b}：{a}→{b} {m[f'{a}→{b}']} 处，{b}→{a} {m[f'{b}→{a}']} 处")
        out.append(
            "\n双向依赖不一定有文件环，但说明两个组件的边界没分清，读代码确认哪一边是“上层”。"
        )
    if res["分层违规"]:
        out += ["", "## 分层违规", ""]
        for v in res["分层违规"]:  # type: ignore[attr-defined]
            out.append(f"- {v['从']} → {v['到']}（{v['次数']} 处），例如：{v['示例'][0]}")
    elif res.get("_layers"):
        out += ["", "## 分层违规", "", "没有发现。"]
    out += ["", "## 依赖最多的组件对", ""]
    for e in res["依赖"][:top]:  # type: ignore[index]
        extra = []
        if e["懒加载"]:
            extra.append(f"懒加载 {e['懒加载']}")
        if e["仅类型"]:
            extra.append(f"仅类型 {e['仅类型']}")
        out.append(
            f"- {e['从']} → {e['到']}：运行时 {e['运行时']}"
            + (f"（{'，'.join(extra)}）" if extra else "")
            + f"；例：{e['示例'][0]}"
        )
    if res["枢纽组件"]:
        out += [
            "",
            f"枢纽组件（依赖了 ≥5 个、又被 ≥5 个依赖）：{'、'.join(res['枢纽组件'])}——改动容易牵一发动全身。",
        ]  # type: ignore[arg-type]
    if res["超大文件"]:
        out += ["", f"## 超大文件（≥{BIG_FILE} 行）", ""]
        for b in res["超大文件"][:top]:  # type: ignore[index]
            out.append(f"- {b['文件']}：{b['代码行']} 行")
    out += [
        "",
        "## 说明",
        "",
        "- 只根据 import 关系和目录划分，看不到运行时调用、消息队列、数据库共享等隐形依赖；目录划分和真实的模块边界不一致时，用 --depth / --root 调整。",
        "- 结果是评审的线索，不是结论：每个环、每个违规都要读代码确认。",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="代码仓库架构扫描")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan", help="扫描项目")
    p.add_argument("project")
    p.add_argument("--depth", default="auto", choices=["auto", "1", "2", "3"])
    p.add_argument("--root", help="源码根目录（相对项目目录），默认自动判断")
    p.add_argument("--exclude", default="", help="要跳过的目录名，逗号分隔")
    p.add_argument(
        "--layers", default="", help="从外层到内层的组件名，逗号分隔；内层 import 外层算违规"
    )
    p.add_argument("--include-tests", action="store_true", help="把测试文件也算进去")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--mermaid", help="把 Mermaid 依赖图写到这个文件")
    p.add_argument("--max-edges", type=int, default=40)
    p.add_argument("--json", action="store_true")
    p.add_argument("--fail-on-cycle", action="store_true")
    args = ap.parse_args(argv)

    project = Path(args.project)
    if not project.is_dir():
        print(f"目录不存在：{project}", file=sys.stderr)
        return 1
    layers = [s.strip() for s in args.layers.split(",") if s.strip()]
    try:
        res = scan(
            project.resolve(),
            args.depth,
            args.root,
            {s.strip() for s in args.exclude.split(",") if s.strip()},
            args.include_tests,
            layers,
        )
    except SystemExit as exc:
        print(exc.code, file=sys.stderr)
        return 1
    res["_layers"] = bool(layers)
    if args.mermaid:
        out = Path(args.mermaid)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("# 组件依赖图\n\n" + mermaid(res, args.max_edges) + "\n", encoding="utf-8")
    if args.json:
        res.pop("_layers", None)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(render(res, args.top))
        if args.mermaid:
            print(f"\nMermaid 依赖图已写入 {args.mermaid}")
    if res["分层违规"] or (args.fail_on_cycle and res["循环依赖"]):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
