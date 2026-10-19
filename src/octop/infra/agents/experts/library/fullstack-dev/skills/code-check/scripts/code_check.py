#!/usr/bin/env python3
"""代码自检：识别项目的语言和工具链，依次运行语法检查、代码规范、类型检查、测试和构建，汇总通过 / 失败并摘出报错。

Usage:
    python scripts/code_check.py detect [项目目录]                 只列出会运行哪些检查，不执行
    python scripts/code_check.py run [项目目录] [--only lint,type,test,build] [--stack python,node]
                                    [--timeout 600] [--tail 30] [--json]

支持：
  Python  语法（内置，不写文件）、ruff / flake8、mypy（项目有 mypy 配置时）、pytest / unittest；
          优先使用项目自己的 .venv / venv 解释器
  Node    package.json 里的 lint、typecheck / type-check、test、build 脚本（npm / pnpm / yarn），
          没有 typecheck 脚本但有 tsconfig.json 时运行 tsc --noEmit
  Go      go vet、go test        Rust  cargo check、cargo clippy、cargo test
  Java    mvn test / gradle test（优先使用项目里的 mvnw / gradlew）
不会修改源代码；不自动安装依赖，缺少的工具会列为"跳过"并给出安装命令。
Exit codes: 0 全部通过, 3 有检查失败或超时, 1 输入错误或没有可运行的检查。
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
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
    "vendor",
    ".idea",
}
KIND_LABEL = {"lint": "规范", "type": "类型", "test": "测试", "build": "构建"}
# No cache dirs: the check must leave the user's project untouched.
RUFF_ARGS = ["check", "--no-cache", "--output-format", "concise", "."]
ERROR_LINE = re.compile(r"error|错误|failed|fail\b|exception|traceback|✗|✖", re.I)


@dataclass
class Check:
    stack: str
    kind: str
    name: str
    cmd: list[str] = field(default_factory=list)
    available: bool = True
    reason: str = ""
    status: str = ""
    seconds: float = 0.0
    output: str = ""


class CheckError(ValueError):
    pass


def _files(root: Path, suffixes: tuple[str, ...], limit: int = 5000) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if name.endswith(suffixes):
                out.append(Path(dirpath) / name)
                if len(out) >= limit:
                    return out
    return out


def _has_module(py: str, module: str) -> bool:
    probe = f"import importlib.util,sys;sys.exit(importlib.util.find_spec({module!r}) is None)"
    try:
        return subprocess.run([py, "-c", probe], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _python(root: Path) -> str:
    for rel in (
        ".venv/bin/python",
        "venv/bin/python",
        ".venv/Scripts/python.exe",
        "venv/Scripts/python.exe",
    ):
        cand = root / rel
        if cand.is_file():
            return str(cand)
    return sys.executable


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def python_checks(root: Path) -> list[Check]:
    py_files = _files(root, (".py",))
    markers = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
    if not py_files and not any((root / m).is_file() for m in markers):
        return []
    py = _python(root)
    checks = [Check("python", "lint", "Python 语法检查", cmd=["(内置)"])]
    if _has_module(py, "ruff"):
        checks.append(
            Check("python", "lint", "Python 代码规范（ruff）", [py, "-m", "ruff", *RUFF_ARGS])
        )
    elif shutil.which("ruff"):
        checks.append(
            Check(
                "python",
                "lint",
                "Python 代码规范（ruff）",
                [str(shutil.which("ruff")), *RUFF_ARGS],
            )
        )
    elif _has_module(py, "flake8"):
        checks.append(
            Check("python", "lint", "Python 代码规范（flake8）", [py, "-m", "flake8", "."])
        )
    else:
        checks.append(
            Check(
                "python",
                "lint",
                "Python 代码规范",
                available=False,
                reason="未安装 ruff：pip install ruff",
            )
        )
    cfg = _read(root / "pyproject.toml") + _read(root / "setup.cfg")
    has_mypy_cfg = "[tool.mypy]" in cfg or "[mypy]" in cfg or (root / "mypy.ini").is_file()
    if has_mypy_cfg:
        if _has_module(py, "mypy"):
            checks.append(
                Check(
                    "python",
                    "type",
                    "Python 类型检查（mypy）",
                    [py, "-m", "mypy", "--cache-dir", os.devnull, "."],
                )
            )
        else:
            checks.append(
                Check(
                    "python",
                    "type",
                    "Python 类型检查",
                    available=False,
                    reason="项目配置了 mypy 但未安装：pip install mypy",
                )
            )
    has_tests = any(p.name.startswith("test_") or p.name.endswith("_test.py") for p in py_files)
    if has_tests:
        if _has_module(py, "pytest"):
            checks.append(
                Check(
                    "python",
                    "test",
                    "Python 测试（pytest）",
                    [py, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                )
            )
        else:
            checks.append(
                Check(
                    "python",
                    "test",
                    "Python 测试（unittest）",
                    [py, "-m", "unittest", "discover", "-s", ".", "-p", "test*.py"],
                )
            )
    return checks


def node_checks(root: Path) -> list[Check]:
    pkg_path = root / "package.json"
    if not pkg_path.is_file():
        return []
    try:
        pkg = json.loads(_read(pkg_path))
    except json.JSONDecodeError as exc:
        raise CheckError(f"package.json 不是合法的 JSON：{exc}") from None
    scripts: dict[str, str] = pkg.get("scripts") or {}
    if (root / "pnpm-lock.yaml").is_file() and shutil.which("pnpm"):
        pm = "pnpm"
    elif (root / "yarn.lock").is_file() and shutil.which("yarn"):
        pm = "yarn"
    else:
        pm = "npm"
    pm_path = shutil.which(pm)
    has_deps = bool(pkg.get("dependencies") or pkg.get("devDependencies"))
    missing = ""
    if not pm_path:
        missing = "未找到 Node.js / npm：先安装 Node.js（https://nodejs.org）"
    elif has_deps and not (root / "node_modules").is_dir():
        missing = f"依赖未安装：先在项目目录运行 {pm} install"
    checks: list[Check] = []
    plan = [
        ("lint", "lint"),
        ("type", "typecheck"),
        ("type", "type-check"),
        ("test", "test"),
        ("build", "build"),
    ]
    for kind, script in plan:
        body = scripts.get(script, "")
        if not body or "no test specified" in body:
            continue
        name = f"Node {KIND_LABEL[kind]}（{pm} run {script}）"
        checks.append(
            Check("node", kind, name, [pm_path or pm, "run", script], not missing, missing)
        )
    has_type_script = any(c.kind == "type" for c in checks)
    tsc = root / "node_modules" / ".bin" / ("tsc.cmd" if os.name == "nt" else "tsc")
    if not has_type_script and (root / "tsconfig.json").is_file():
        if tsc.is_file():
            checks.append(
                Check("node", "type", "TypeScript 类型检查（tsc --noEmit）", [str(tsc), "--noEmit"])
            )
        else:
            checks.append(
                Check(
                    "node",
                    "type",
                    "TypeScript 类型检查",
                    available=False,
                    reason=f"未安装 typescript：{pm} install",
                )
            )
    if not checks:
        checks.append(
            Check(
                "node",
                "test",
                "Node 项目",
                available=False,
                reason="package.json 里没有 lint / test / build 脚本",
            )
        )
    return checks


def _tool_checks(stack: str, tool: str, items: list[tuple[str, str, list[str]]]) -> list[Check]:
    path = shutil.which(tool)
    return [
        Check(
            stack, kind, name, [path or tool, *args], bool(path), "" if path else f"未找到 {tool}"
        )
        for kind, name, args in items
    ]


def other_checks(root: Path) -> list[Check]:
    checks: list[Check] = []
    if (root / "go.mod").is_file():
        checks += _tool_checks(
            "go",
            "go",
            [
                ("lint", "Go 静态检查（go vet）", ["vet", "./..."]),
                ("test", "Go 测试", ["test", "./..."]),
            ],
        )
    if (root / "Cargo.toml").is_file():
        checks += _tool_checks(
            "rust", "cargo", [("build", "Rust 编译检查（cargo check）", ["check", "--quiet"])]
        )
        if shutil.which("cargo-clippy"):
            checks += _tool_checks(
                "rust", "cargo", [("lint", "Rust 规范（clippy）", ["clippy", "--quiet"])]
            )
        checks += _tool_checks("rust", "cargo", [("test", "Rust 测试", ["test", "--quiet"])])
    if (root / "pom.xml").is_file():
        wrapper = root / ("mvnw.cmd" if os.name == "nt" else "mvnw")
        if wrapper.is_file():
            checks.append(
                Check("java", "test", "Java 测试（mvnw test）", [str(wrapper), "-q", "-B", "test"])
            )
        else:
            checks += _tool_checks(
                "java", "mvn", [("test", "Java 测试（mvn test）", ["-q", "-B", "test"])]
            )
    elif (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file():
        wrapper = root / ("gradlew.bat" if os.name == "nt" else "gradlew")
        if wrapper.is_file():
            checks.append(
                Check("java", "test", "Java 测试（gradlew test）", [str(wrapper), "test", "-q"])
            )
        else:
            checks += _tool_checks(
                "java", "gradle", [("test", "Java 测试（gradle test）", ["test", "-q"])]
            )
    return checks


def detect(root: Path, stacks: set[str] | None, kinds: set[str] | None) -> list[Check]:
    if not root.is_dir():
        raise CheckError(f"找不到目录 {root}")
    checks = python_checks(root) + node_checks(root) + other_checks(root)
    return [
        c for c in checks if (not stacks or c.stack in stacks) and (not kinds or c.kind in kinds)
    ]


def syntax_check(root: Path) -> tuple[bool, str]:
    problems = []
    for path in _files(root, (".py",)):
        try:
            ast.parse(path.read_bytes(), filename=str(path))
        except SyntaxError as exc:
            rel = path.relative_to(root).as_posix()
            problems.append(f"{rel}:{exc.lineno}:{exc.offset}: 语法错误 {exc.msg}")
        except ValueError as exc:
            problems.append(f"{path.relative_to(root).as_posix()}: {exc}")
    return not problems, "\n".join(problems)


def run_check(check: Check, root: Path, timeout: int) -> None:
    start = time.monotonic()
    if check.cmd == ["(内置)"]:
        ok, out = syntax_check(root)
        check.status, check.output = ("通过" if ok else "失败"), out
        check.seconds = time.monotonic() - start
        return
    env = {
        **os.environ,
        "CI": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "FORCE_COLOR": "0",
        "NO_COLOR": "1",
    }
    try:
        proc = subprocess.run(
            check.cmd,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        check.status, check.output = "超时", f"超过 {timeout} 秒没有结束"
    except OSError as exc:
        check.status, check.output = "跳过", f"无法运行：{exc}"
    else:
        check.output = re.sub(r"\x1b\[[0-9;]*m", "", (proc.stdout or "") + (proc.stderr or ""))
        if proc.returncode == 0:
            check.status = "通过"
        elif "pytest" in " ".join(check.cmd) and proc.returncode == 5:
            check.status, check.output = "跳过", "没有收集到测试用例"
        else:
            check.status = "失败"
    check.seconds = time.monotonic() - start


def excerpt(output: str, tail: int) -> list[str]:
    lines = [ln.rstrip() for ln in output.splitlines() if ln.strip()]
    if len(lines) <= tail:
        return lines
    hits = [ln for ln in lines[:-tail] if ERROR_LINE.search(ln)][:8]
    return hits + (["…"] if hits else []) + lines[-tail:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("detect", "run"):
        p = sub.add_parser(name)
        p.add_argument("path", nargs="?", default=".")
        p.add_argument("--only", help="只运行这些类型：lint,type,test,build")
        p.add_argument("--stack", help="只检查这些技术栈：python,node,go,rust,java")
        p.add_argument("--json", action="store_true")
    run_p = sub.choices["run"]
    run_p.add_argument("--timeout", type=int, default=600, help="单项检查超时秒数")
    run_p.add_argument("--tail", type=int, default=30, help="失败时显示输出的最后几行")
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    kinds = {k.strip() for k in args.only.split(",")} if args.only else None
    stacks = {s.strip() for s in args.stack.split(",")} if args.stack else None
    try:
        if kinds and kinds - set(KIND_LABEL):
            raise CheckError(f"--only 可选 {','.join(KIND_LABEL)}")
        checks = detect(root, stacks, kinds)
    except CheckError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    if not checks:
        print(f"失败：{root} 中没有识别到 Python / Node / Go / Rust / Java 项目", file=sys.stderr)
        return 1

    if args.cmd == "detect":
        if args.json:
            print(json.dumps([asdict(c) for c in checks], ensure_ascii=False, indent=2))
            return 0
        print(f"项目：{root}")
        for c in checks:
            state = "将运行" if c.available else f"跳过（{c.reason}）"
            cmd = " ".join(c.cmd)
            print(
                f"- [{KIND_LABEL[c.kind]}] {c.name}：{state}"
                + (f"\n    {cmd}" if c.available else "")
            )
        return 0

    for c in checks:
        if c.available:
            run_check(c, root, args.timeout)
        else:
            c.status, c.output = "跳过", c.reason
    counts = {s: sum(c.status == s for c in checks) for s in ("通过", "失败", "超时", "跳过")}
    if args.json:
        print(
            json.dumps(
                {"path": str(root), "counts": counts, "checks": [asdict(c) for c in checks]},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"项目：{root}")
        for c in checks:
            took = f"  {c.seconds:.1f}s" if c.status != "跳过" else ""
            print(f"[{c.status}] {c.name}{took}")
            if c.status in ("失败", "超时"):
                for ln in excerpt(c.output, args.tail):
                    print(f"    {ln}")
            elif c.status == "跳过" and c.output:
                print(f"    {c.output}")
        summary = "，".join(f"{v} {k}" for k, v in counts.items() if v)
        print(f"结论：{summary}")
        if counts["跳过"]:
            print("注意：跳过的检查没有运行，不能算作通过；装好对应工具后再运行一次。")
    return 3 if counts["失败"] or counts["超时"] else 0


if __name__ == "__main__":
    sys.exit(main())
