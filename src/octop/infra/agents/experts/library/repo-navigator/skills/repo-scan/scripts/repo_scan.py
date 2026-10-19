#!/usr/bin/env python3
"""代码仓库速览：语言和代码量、目录结构、依赖清单、入口文件和框架、模块调用关系图。只读，不修改任何文件。

Usage:
    python scripts/repo_scan.py scan 项目目录 [--top 15] [--json]
    python scripts/repo_scan.py tree 项目目录 [--depth 3]
    python scripts/repo_scan.py graph 项目目录 [--lang python|js] [--depth 2] [--max-nodes 40] [-o 模块关系.mmd]

scan：按语言统计文件数、代码行、注释行、空行；最大的文件；TODO/FIXME 数量；
      解析 package.json、pyproject.toml、requirements*.txt、go.mod、Cargo.toml、pom.xml、composer.json 的依赖和脚本；
      识别入口文件（main.py、manage.py、index.ts、main.go、Dockerfile、Makefile 等）、常见框架、测试和 CI 配置。
tree：带文件数的目录树（自动跳过 .git、node_modules、虚拟环境、构建产物等）。
graph：Python 用 ast 解析 import，JS/TS 解析相对路径的 import/require，按目录层级（--depth）汇总成 Mermaid 依赖图，
       并列出循环依赖。只统计项目内部模块之间的引用。
Exit codes: 0 ok, 1 输入错误。
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import tomllib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env", ".env", "dist", "build", "target",
             ".idea", ".vscode", ".next", ".nuxt", "coverage", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
             "vendor", "bower_components", ".gradle", "out", ".cache", "site-packages", ".terraform"}  # fmt: skip
LANGS: dict[str, tuple[str, str]] = {
    # 扩展名: (语言, 单行注释前缀)
    ".py": ("Python", "#"), ".js": ("JavaScript", "//"), ".mjs": ("JavaScript", "//"), ".cjs": ("JavaScript", "//"),
    ".jsx": ("JavaScript", "//"), ".ts": ("TypeScript", "//"), ".tsx": ("TypeScript", "//"), ".vue": ("Vue", "//"),
    ".go": ("Go", "//"), ".java": ("Java", "//"), ".kt": ("Kotlin", "//"), ".rs": ("Rust", "//"), ".c": ("C", "//"),
    ".h": ("C/C++ 头文件", "//"), ".cpp": ("C++", "//"), ".cc": ("C++", "//"), ".hpp": ("C++", "//"), ".cs": ("C#", "//"),
    ".php": ("PHP", "//"), ".rb": ("Ruby", "#"), ".swift": ("Swift", "//"), ".scala": ("Scala", "//"), ".dart": ("Dart", "//"),
    ".sh": ("Shell", "#"), ".bash": ("Shell", "#"), ".ps1": ("PowerShell", "#"), ".sql": ("SQL", "--"), ".lua": ("Lua", "--"),
    ".r": ("R", "#"), ".html": ("HTML", ""), ".css": ("CSS", ""), ".scss": ("SCSS", "//"), ".less": ("Less", "//"),
    ".md": ("Markdown", ""), ".yaml": ("YAML", "#"), ".yml": ("YAML", "#"), ".toml": ("TOML", "#"), ".json": ("JSON", ""),
    ".xml": ("XML", ""), ".proto": ("Protobuf", "//"),
}  # fmt: skip
DOC_LANGS = {"Markdown", "YAML", "TOML", "JSON", "XML"}
ENTRY_NAMES = {"main.py", "__main__.py", "manage.py", "app.py", "wsgi.py", "asgi.py", "server.py", "cli.py", "index.js",
               "index.ts", "main.js", "main.ts", "server.js", "server.ts", "app.js", "app.ts", "main.go", "Main.java",
               "Application.java", "main.rs", "lib.rs", "Program.cs", "index.php", "Dockerfile", "docker-compose.yml",
               "docker-compose.yaml", "compose.yaml", "Makefile", "Procfile", "vite.config.ts", "vite.config.js",
               "next.config.js", "webpack.config.js"}  # fmt: skip
FRAMEWORKS = {
    "fastapi": "FastAPI", "django": "Django", "flask": "Flask", "starlette": "Starlette", "tornado": "Tornado",
    "langchain": "LangChain", "langgraph": "LangGraph", "pytest": "pytest", "sqlalchemy": "SQLAlchemy", "celery": "Celery",
    "react": "React", "vue": "Vue", "next": "Next.js", "nuxt": "Nuxt", "svelte": "Svelte", "@angular/core": "Angular",
    "express": "Express", "koa": "Koa", "@nestjs/core": "NestJS", "vite": "Vite", "electron": "Electron",
    "jest": "Jest", "vitest": "Vitest", "tailwindcss": "Tailwind CSS", "antd": "Ant Design", "element-plus": "Element Plus",
    "github.com/gin-gonic/gin": "Gin", "github.com/labstack/echo": "Echo", "gorm.io/gorm": "GORM",
    "spring-boot": "Spring Boot", "mybatis": "MyBatis", "tokio": "Tokio", "actix-web": "Actix Web", "axum": "Axum",
    "laravel/framework": "Laravel",
}  # fmt: skip


class ScanError(ValueError):
    pass


def walk(root: Path) -> list[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")
        )
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if p.is_file() and not p.is_symlink():
                out.append(p)
    return out


def count_lines(path: Path, comment: str) -> tuple[int, int, int]:
    """(code, comment, blank) — single-line comments only; block comments count as code (rough but stable)."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0, 0, 0
    code = com = blank = 0
    for line in text.splitlines():
        s = line.strip()
        if not s:
            blank += 1
        elif comment and s.startswith(comment):
            com += 1
        else:
            code += 1
    return code, com, blank


def _deps_from_requirements(text: str) -> list[str]:
    out = []
    for ln in text.splitlines():
        ln = ln.split("#", 1)[0].strip()
        if ln and not ln.startswith(("-", "git+", "http")):
            out.append(re.split(r"[<>=!~;\[ ]", ln, maxsplit=1)[0])
    return out


def manifests(root: Path) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for p in walk(root):
        rel = p.relative_to(root).as_posix()
        if rel.count("/") > 3:
            continue
        name = p.name
        try:
            if name == "package.json":
                d = json.loads(p.read_text(encoding="utf-8"))
                found.append({"文件": rel, "类型": "npm", "名称": d.get("name", ""),
                              "依赖": sorted(d.get("dependencies", {})), "开发依赖": sorted(d.get("devDependencies", {})),
                              "脚本": d.get("scripts", {})})  # fmt: skip
            elif name == "pyproject.toml":
                d = tomllib.loads(p.read_text(encoding="utf-8"))
                proj = d.get("project", {})
                deps = _deps_from_requirements("\n".join(proj.get("dependencies", [])))
                poetry = d.get("tool", {}).get("poetry", {}).get("dependencies", {})
                deps += [k for k in poetry if k.lower() != "python"]
                found.append({"文件": rel, "类型": "Python", "名称": proj.get("name", ""), "依赖": sorted(set(deps)),
                              "脚本": proj.get("scripts", {})})  # fmt: skip
            elif re.fullmatch(r"requirements.*\.txt", name):
                found.append(
                    {
                        "文件": rel,
                        "类型": "pip",
                        "依赖": _deps_from_requirements(p.read_text(encoding="utf-8")),
                    }
                )
            elif name == "go.mod":
                text = p.read_text(encoding="utf-8")
                mod = re.search(r"^module\s+(\S+)", text, re.M)
                deps = re.findall(r"^\s*([\w.\-]+/[\w.\-/]+)\s+v[\d.]+", text, re.M)
                found.append(
                    {"文件": rel, "类型": "Go", "名称": mod.group(1) if mod else "", "依赖": deps}
                )
            elif name == "Cargo.toml":
                d = tomllib.loads(p.read_text(encoding="utf-8"))
                found.append({"文件": rel, "类型": "Rust", "名称": d.get("package", {}).get("name", ""),
                              "依赖": sorted(d.get("dependencies", {}))})  # fmt: skip
            elif name == "pom.xml":
                text = p.read_text(encoding="utf-8", errors="ignore")
                arts = re.findall(r"<artifactId>([^<]+)</artifactId>", text)
                found.append(
                    {
                        "文件": rel,
                        "类型": "Maven",
                        "名称": arts[0] if arts else "",
                        "依赖": arts[1:],
                    }
                )
            elif name == "composer.json":
                d = json.loads(p.read_text(encoding="utf-8"))
                found.append(
                    {
                        "文件": rel,
                        "类型": "Composer",
                        "名称": d.get("name", ""),
                        "依赖": sorted(d.get("require", {})),
                    }
                )
        except (ValueError, tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            found.append({"文件": rel, "类型": "解析失败", "错误": str(exc)[:80]})
    return found


def cmd_scan(root: Path, top: int, as_json: bool) -> int:
    files = walk(root)
    if not files:
        raise ScanError(f"{root} 里没有文件")
    stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    sizes: list[tuple[int, Path]] = []
    todos = Counter()
    entries, tests, ci = [], 0, []
    for p in files:
        rel = p.relative_to(root)
        lang = LANGS.get(p.suffix.lower())
        if p.name in ENTRY_NAMES:
            entries.append(rel.as_posix())
        if re.search(r"(^|/)(tests?|__tests__|spec)(/|$)", rel.parent.as_posix()) or re.match(
            r"(test_.*|.*_test|.*\.(test|spec))\.\w+$", p.name
        ):
            tests += 1
        if rel.as_posix().startswith(".github/workflows/") or p.name in (
            ".gitlab-ci.yml",
            "Jenkinsfile",
            ".travis.yml",
        ):
            ci.append(rel.as_posix())
        if not lang:
            continue
        code, com, blank = count_lines(p, lang[1])
        s = stats[lang[0]]
        s[0] += 1
        s[1] += code
        s[2] += com
        s[3] += blank
        if lang[0] not in DOC_LANGS:
            sizes.append((code, rel))
            try:
                for m in re.finditer(
                    r"\b(TODO|FIXME|HACK|XXX)\b", p.read_text(encoding="utf-8", errors="ignore")
                ):
                    todos[m.group(1)] += 1
            except OSError:
                pass
    mans = manifests(root)
    all_deps = {d.lower() for m in mans for d in m.get("依赖", []) + m.get("开发依赖", [])}
    frameworks = sorted(
        {
            label
            for key, label in FRAMEWORKS.items()
            if key in all_deps or any(d.endswith("/" + key) for d in all_deps)
        }
    )
    code_total = sum(v[1] for k, v in stats.items() if k not in DOC_LANGS)
    report = {
        "目录": str(root), "文件总数": len(files), "代码行（不含文档配置）": code_total,
        "语言": {k: {"文件": v[0], "代码": v[1], "注释": v[2], "空行": v[3]} for k, v in sorted(stats.items(), key=lambda kv: -kv[1][1])},
        "最大的文件": [{"文件": r.as_posix(), "代码行": n} for n, r in sorted(sizes, reverse=True)[:top]],
        "框架和主要库": frameworks, "入口和构建文件": sorted(entries)[:40], "测试文件数": tests, "CI 配置": ci,
        "TODO/FIXME": dict(todos), "依赖清单": mans,
        "README": next((f.name for f in root.iterdir() if f.name.lower().startswith("readme")), ""),
        "LICENSE": next((f.name for f in root.iterdir() if f.name.lower().startswith(("license", "licence", "copying"))), ""),
    }  # fmt: skip
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"{root}：{len(files)} 个文件，代码约 {code_total:,} 行")
    print("\n| 语言 | 文件 | 代码 | 注释 | 空行 |\n|------|------|------|------|------|")
    for k, v in report["语言"].items():
        print(f"| {k} | {v['文件']} | {v['代码']:,} | {v['注释']:,} | {v['空行']:,} |")
    print(f"\n框架和主要库：{'、'.join(frameworks) or '未识别'}")
    print(f"入口和构建文件：{'、'.join(report['入口和构建文件'][:15]) or '未找到'}")
    print(
        f"测试文件：{tests} 个；CI：{'、'.join(ci) or '无'}；README：{report['README'] or '无'}；LICENSE：{report['LICENSE'] or '无'}"
    )
    if todos:
        print("待办标记：" + "、".join(f"{k} {v}" for k, v in todos.most_common()))
    print(f"\n代码行最多的 {len(report['最大的文件'])} 个文件：")
    for item in report["最大的文件"]:
        print(f"- {item['代码行']:>6,}  {item['文件']}")
    for m in mans:
        line = f"\n依赖清单 {m['文件']}（{m['类型']}{'，' + m['名称'] if m.get('名称') else ''}）"
        deps = m.get("依赖", [])
        print(
            line
            + f"：{len(deps)} 个依赖"
            + (f"，{'、'.join(deps[:20])}{' …' if len(deps) > 20 else ''}" if deps else "")
        )
        if m.get("脚本"):
            print("  脚本：" + "、".join(f"{k}" for k in list(m["脚本"])[:15]))
    return 0


def cmd_tree(root: Path, depth: int) -> int:
    print(root.name + "/")

    def count(d: Path) -> int:
        return sum(1 for _ in walk(d))

    def rec(d: Path, prefix: str, level: int) -> None:
        try:
            children = sorted((c for c in d.iterdir() if c.name not in SKIP_DIRS and not c.name.startswith(".") or c.name in (".github",)),
                              key=lambda c: (c.is_file(), c.name.lower()))  # fmt: skip
        except OSError:
            return
        dirs = [c for c in children if c.is_dir()]
        files = [c for c in children if c.is_file()]
        shown_files = files[:8] if level < depth else []
        hidden = len(files) - len(shown_files)
        items: list[tuple[Path, bool]] = [(c, True) for c in dirs] + [
            (c, False) for c in shown_files
        ]
        for i, (c, is_dir) in enumerate(items):
            last = i == len(items) - 1 and not hidden
            branch = "└── " if last else "├── "
            if is_dir:
                print(f"{prefix}{branch}{c.name}/  ({count(c)} 个文件)")
                if level < depth:
                    rec(c, prefix + ("    " if last else "│   "), level + 1)
            else:
                print(f"{prefix}{branch}{c.name}")
        if hidden:
            print(f"{prefix}└── …{'另有 ' if shown_files else ''}{hidden} 个文件")

    rec(root, "", 1)
    return 0


def _package_prefix(root: Path) -> list[str]:
    """When *root* is itself inside a package (has __init__.py), imports use the enclosing package names."""
    prefix: list[str] = []
    d = root
    while (d / "__init__.py").is_file():
        prefix.insert(0, d.name)
        d = d.parent
    return prefix


def _py_modules(root: Path) -> dict[str, Path]:
    mods: dict[str, Path] = {}
    prefix = _package_prefix(root)
    for p in walk(root):
        if p.suffix != ".py":
            continue
        rel = p.relative_to(root).with_suffix("")
        parts = list(rel.parts)
        if parts and parts[0] in ("src", "lib") and len(parts) > 1:
            parts = parts[1:]
        if parts[-1] == "__init__":
            parts = parts[:-1]
        parts = [*prefix, *parts]
        if parts:
            mods[".".join(parts)] = p
    return mods


def _collapse(name: str, depth: int, sep: str = ".") -> str:
    return sep.join(name.split(sep)[:depth])


def py_edges(root: Path, depth: int) -> Counter[tuple[str, str]]:
    mods = _py_modules(root)
    tops = {m.split(".")[0] for m in mods}
    edges: Counter[tuple[str, str]] = Counter()
    for mod, path in mods.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        is_pkg = path.name == "__init__.py"
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = mod.split(".")
                    base = base if is_pkg else base[:-1]
                    base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                    targets = [".".join([*base, node.module] if node.module else base)]
                elif node.module:
                    targets = [node.module]
            for t in targets:
                if t.split(".")[0] not in tops:
                    continue
                src, dst = _collapse(mod, depth), _collapse(t, depth)
                if src != dst:
                    edges[(src, dst)] += 1
    return edges


JS_IMPORT = re.compile(
    r"""(?:import\s+(?:[^'"]*?\s+from\s+)?|require\(\s*|import\(\s*)['"](\.{1,2}/[^'"]+)['"]"""
)


def js_edges(root: Path, depth: int) -> Counter[tuple[str, str]]:
    edges: Counter[tuple[str, str]] = Counter()
    exts = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue")
    for p in walk(root):
        if p.suffix not in exts:
            continue
        rel_dir = p.parent.relative_to(root)
        src = "/".join(rel_dir.parts[:depth]) or "."
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in JS_IMPORT.finditer(text):
            target = (p.parent / m.group(1)).resolve()
            try:
                rel = target.relative_to(root.resolve())
            except ValueError:
                continue
            # "./utils" may be a directory (index file) or a file without extension.
            parts = rel.parts if target.is_dir() else rel.parent.parts
            dst = "/".join(parts[:depth]) or "."
            if dst != src:
                edges[(src, dst)] += 1
    return edges


def find_cycles(edges: Counter[tuple[str, str]]) -> list[list[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        graph[a].add(b)
    cycles: list[list[str]] = []
    seen: set[frozenset[str]] = set()
    for a, b in edges:
        if a in graph.get(b, set()):
            key = frozenset((a, b))
            if key not in seen:
                seen.add(key)
                cycles.append([a, b])
    return cycles


def cmd_graph(root: Path, lang: str | None, depth: int, max_nodes: int, out: Path | None) -> int:
    if lang is None:
        counts = Counter(LANGS.get(p.suffix.lower(), ("", ""))[0] for p in walk(root))
        lang = "python" if counts["Python"] >= counts["JavaScript"] + counts["TypeScript"] else "js"
    edges = py_edges(root, depth) if lang == "python" else js_edges(root, depth)
    if not edges:
        raise ScanError("没有找到项目内部模块之间的引用（检查 --lang 和项目目录）")
    degree: Counter[str] = Counter()
    for (a, b), n in edges.items():
        degree[a] += n
        degree[b] += n
    keep = {n for n, _ in degree.most_common(max_nodes)}
    ids = {name: f"n{i}" for i, name in enumerate(sorted(keep))}
    lines = ["graph LR"]
    for name, nid in ids.items():
        lines.append(f'  {nid}["{name}"]')
    for (a, b), n in sorted(edges.items(), key=lambda kv: -kv[1]):
        if a in keep and b in keep:
            lines.append(f"  {ids[a]} -->|{n}| {ids[b]}")
    mmd = "\n".join(lines) + "\n"
    cycles = find_cycles(edges)
    print(
        f"{lang} 模块依赖：{len(degree)} 个模块（按前 {depth} 层汇总），{len(edges)} 条依赖关系"
        + (f"，图中保留引用最多的 {len(keep)} 个" if len(keep) < len(degree) else "")
    )
    indegree: Counter[str] = Counter()
    for (_a, b), n in edges.items():
        indegree[b] += n
    print("被引用最多：" + "、".join(f"{n}（{c} 次）" for n, c in indegree.most_common(5)))
    if cycles:
        print(
            "目录 / 模块之间相互引用（可能存在循环依赖）："
            + "；".join(" ⇄ ".join(c) for c in cycles[:10])
        )
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(mmd, encoding="utf-8")
        print(f"已生成 {out}（Mermaid，可交给流程图设计专家渲染成图片）")
    else:
        print(mmd)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("root")
    s.add_argument("--top", type=int, default=15)
    s.add_argument("--json", action="store_true")
    t = sub.add_parser("tree")
    t.add_argument("root")
    t.add_argument("--depth", type=int, default=3)
    g = sub.add_parser("graph")
    g.add_argument("root")
    g.add_argument("--lang", choices=["python", "js"])
    g.add_argument("--depth", type=int, default=2)
    g.add_argument("--max-nodes", type=int, default=40)
    g.add_argument("-o", "--output")
    args = parser.parse_args(argv)
    try:
        root = Path(args.root).resolve()
        if not root.is_dir():
            raise ScanError(f"{args.root} 不是目录")
        if args.cmd == "scan":
            return cmd_scan(root, args.top, args.json)
        if args.cmd == "tree":
            return cmd_tree(root, args.depth)
        return cmd_graph(
            root, args.lang, args.depth, args.max_nodes, Path(args.output) if args.output else None
        )
    except (OSError, ScanError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
