#!/usr/bin/env python3
"""正则表达式测试：用一批样例检查匹配结果和捕获组，验证"应该匹配 / 不应该匹配"的预期，提示常见陷阱。

Usage:
    python scripts/regex_test.py "PATTERN" -s 样例1 -s 样例2 [--mode search|fullmatch|findall] [--flags i,m,s,x]
    python scripts/regex_test.py "PATTERN" --file 样例.txt                    （每行一个样例）
    python scripts/regex_test.py "PATTERN" -M 应匹配1 -M 应匹配2 -N 不应匹配1  （校验类正则，默认按 fullmatch）
    python scripts/regex_test.py "PATTERN" -s 文本 --replace "替换为\\1"

使用 Python 的 re 语法（与 JavaScript / Java / PCRE 大体相同，差异见 SKILL.md）。
匹配在子进程中执行并设置超时（--timeout，默认 2 秒），防止灾难性回溯把程序卡住。
提示项：嵌套量词（(a+)+ 一类，可能灾难性回溯）、校验时没有锚定 ^…$、[A-z] 范围、IP / 域名里没转义的点、
        JavaScript 风格的 (?<name>…) 命名组、贪婪的 .* 可能吞掉过多内容。
Exit codes: 0 ok（预期全部满足）, 3 有预期不满足或超时, 1 正则语法错误或输入错误。
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import re
import sys
from pathlib import Path
from typing import Any

FLAG_MAP = {"i": re.I, "m": re.M, "s": re.S, "x": re.X, "a": re.A}


def lint(pattern: str, validating: bool) -> list[str]:
    tips = []
    if re.search(r"\((?:[^()\\]|\\.)*[+*](?:\?)?\)[+*{]", pattern):
        tips.append(
            "存在嵌套量词（如 (a+)+、(\\w*)*），遇到不匹配的长输入可能灾难性回溯；改成不重叠的写法或使用原子分组"
        )
    if validating and not (pattern.startswith("^") or pattern.startswith("\\A")):
        tips.append(
            "用于校验输入时，建议用 ^…$ 锚定整串（本工具校验模式已按整串匹配，但很多语言的 test()/find() 是部分匹配）"
        )
    if "[A-z]" in pattern or "[a-Z]" in pattern:
        tips.append("[A-z] 还包含 [ \\ ] ^ _ ` 等符号，应写成 [A-Za-z]")
    if re.search(
        r"\\d[+*]?(?:\{[\d,]+\})?\.\\d|[a-z]\.(?:com|cn|net|org)\b", pattern
    ) and not re.search(r"\\\.", pattern):
        tips.append("看起来在匹配 IP / 域名 / 小数，但 . 没有转义（. 匹配任意字符），应写成 \\.")
    if "(?<" in pattern and not re.search(r"\(\?<[=!]", pattern):
        tips.append("(?<name>…) 是 JavaScript / .NET 的命名组写法，Python 要写成 (?P<name>…)")
    if re.search(r"(?<!\\)\.\*(?!\?)", pattern) and not validating:
        tips.append(".* 是贪婪匹配，会尽量多吞内容；只想匹配到第一个结束符时用 .*? 或 [^结束符]*")
    return tips


def evaluate(
    pattern: str, flags: int, mode: str, samples: list[str], replace: str | None
) -> list[dict[str, Any]]:
    rx = re.compile(pattern, flags)
    out = []
    for s in samples:
        row: dict[str, Any] = {"sample": s}
        if mode == "findall":
            ms = list(rx.finditer(s))
            row["matched"] = bool(ms)
            row["all"] = [m.group(0) for m in ms][:20]
            m = ms[0] if ms else None
        else:
            m = rx.fullmatch(s) if mode == "fullmatch" else rx.search(s)
            row["matched"] = m is not None
        if m:
            row["match"] = m.group(0)
            row["span"] = m.span()
            row["groups"] = list(m.groups())
            row["named"] = m.groupdict()
        if replace is not None:
            row["replaced"] = rx.sub(replace, s)
        out.append(row)
    return out


def _worker(q: Any, args: tuple[Any, ...]) -> None:
    try:
        q.put(("ok", evaluate(*args)))
    except Exception as exc:  # noqa: BLE001 - report any engine error back to the parent
        q.put(("err", f"{type(exc).__name__}: {exc}"))


def run_with_timeout(args: tuple[Any, ...], timeout: float) -> list[dict[str, Any]] | None:
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    proc = ctx.Process(target=_worker, args=(q, args), daemon=True)
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        return None
    status, payload = q.get(timeout=5)
    if status == "err":
        raise ValueError(payload)
    return list(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("pattern")
    parser.add_argument("-s", "--sample", action="append", default=[])
    parser.add_argument("--file")
    parser.add_argument("-M", "--expect-match", action="append", default=[])
    parser.add_argument("-N", "--expect-no-match", action="append", default=[])
    parser.add_argument("--mode", choices=["search", "fullmatch", "findall"])
    parser.add_argument("--flags", default="")
    parser.add_argument("--replace")
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args(argv)

    flags = 0
    for f in filter(None, (x.strip().lower() for x in args.flags.split(","))):
        if f not in FLAG_MAP:
            print(f"失败：未知标志 {f}，可选 {','.join(FLAG_MAP)}", file=sys.stderr)
            return 1
        flags |= FLAG_MAP[f]
    try:
        re.compile(args.pattern, flags)
    except re.error as exc:
        pos = exc.pos if exc.pos is not None else 0
        print(
            f"正则语法错误：{exc.msg}（第 {pos + 1} 个字符）\n  {args.pattern}\n  {' ' * pos}^",
            file=sys.stderr,
        )
        if "(?<" in args.pattern:
            print("提示：Python 的命名组写法是 (?P<name>…)", file=sys.stderr)
        return 1

    samples = list(args.sample)
    if args.file:
        samples += [
            ln for ln in Path(args.file).read_text(encoding="utf-8").splitlines() if ln != ""
        ]
    expect = {
        **dict.fromkeys(args.expect_match, True),
        **dict.fromkeys(args.expect_no_match, False),
    }
    samples += [s for s in expect if s not in samples]
    if not samples:
        print("失败：请用 -s / --file / -M / -N 提供样例", file=sys.stderr)
        return 1
    validating = bool(expect)
    mode = args.mode or ("fullmatch" if validating else "search")

    for tip in lint(args.pattern, validating):
        print(f"[提示] {tip}")
    results = run_with_timeout((args.pattern, flags, mode, samples, args.replace), args.timeout)
    if results is None:
        print(
            f"[超时] 匹配超过 {args.timeout} 秒没有结束，很可能是灾难性回溯；检查嵌套量词和可重叠的分支"
        )
        return 3
    print(f"模式：{mode}　正则：{args.pattern}")
    wrong = 0
    for r in results:
        s = r["sample"]
        mark = "✓ 匹配" if r["matched"] else "✗ 不匹配"
        line = f"- {mark}  {s!r}"
        if s in expect and expect[s] != r["matched"]:
            wrong += 1
            line += f"  ← 预期{'应该匹配' if expect[s] else '不应该匹配'}"
        print(line)
        if r["matched"]:
            if mode == "findall":
                print(f"    全部结果：{r['all']}")
            elif r["match"] != s:
                print(f"    匹配到：{r['match']!r}（位置 {r['span'][0]}–{r['span'][1]}）")
            if r["groups"]:
                print(f"    分组：{r['groups']}")
            if r["named"]:
                print(f"    命名组：{r['named']}")
        if "replaced" in r:
            print(f"    替换后：{r['replaced']!r}")
    if expect:
        print(
            f"预期检查：{len(expect) - wrong}/{len(expect)} 符合"
            + ("" if not wrong else f"，{wrong} 个不符合")
        )
    return 3 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
