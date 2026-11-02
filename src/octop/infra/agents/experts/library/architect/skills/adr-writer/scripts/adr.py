#!/usr/bin/env python3
"""架构决策记录（ADR）管理：新建、列表、检查、改状态、标记取代。

Usage:
    python scripts/adr.py new "标题" [--dir docs/adr] [--status 提议中] [--deciders "张三,李四"]
    python scripts/adr.py list [--dir docs/adr]
    python scripts/adr.py check [--dir docs/adr] [--json]
    python scripts/adr.py status 0003 已采纳 [--dir docs/adr]
    python scripts/adr.py supersede 0003 0007 [--dir docs/adr]     0007 取代 0003

文件名 NNNN-标题.md（四位编号，只增不改、不重用）；状态：提议中 / 已采纳 / 已弃用 / 已被取代（也认 proposed / accepted / deprecated / superseded）。
check 会查：编号重复或跳号、标题编号和文件名是否一致、必填章节是不是还是模板占位、备选方案是否不足两个、
已采纳的决策有没有写清代价和风险、取代关系是否两边都写了、取代的对象是否存在。
Exit codes: 0 没有"必须处理"项, 3 有"必须处理"项, 1 输入错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

STATUSES = ["提议中", "已采纳", "已弃用", "已被取代"]
ALIASES = {
    "proposed": "提议中",
    "accepted": "已采纳",
    "deprecated": "已弃用",
    "superseded": "已被取代",
}
FILE_RE = re.compile(r"^(\d{4})-(.+)\.md$")
PLACEHOLDER = re.compile(r"^[（(].*[）)]$|待填|TODO|___")

TEMPLATE = """# {num}. {title}

- 状态：{status}
- 日期：{today}
- 决策人：{deciders}

## 背景

（面临什么问题？现状和约束是什么？为什么现在必须决定？写事实，不写结论。）

## 决策驱动因素

- （这个决定最看重什么：例如上线时间、成本、团队熟悉度、一致性、可运维性）

## 备选方案

### 方案 A：（名称）

- 做法：
- 优点：
- 缺点：

### 方案 B：（名称）

- 做法：
- 优点：
- 缺点：

## 决策

（选哪个方案，一句话说清；再用两三句话说明为什么选它、不选其他的。）

## 后果

### 好处

- （这个决定带来什么）

### 代价和风险

- （要付出什么、可能出什么问题、怎么缓解）

## 重新评审条件

- （出现什么情况要回头重新决定，例如：数据量超过 ___、团队规模超过 ___、依赖的服务停止维护）
"""


@dataclass
class Adr:
    path: Path
    number: str
    slug: str
    title: str = ""
    status: str = ""
    date: str = ""
    supersedes: list[str] = field(default_factory=list)
    superseded_by: list[str] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    title_number: str = ""


def normalize_status(value: str) -> str | None:
    v = value.strip()
    if v in STATUSES:
        return v
    return ALIASES.get(v.lower())


def slugify(title: str) -> str:
    s = re.sub(r"[^\w一-鿿\- ]", "", title.strip().lower())
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:60] or "decision"


def parse(path: Path) -> Adr:
    m = FILE_RE.match(path.name)
    assert m
    adr = Adr(path=path, number=m.group(1), slug=m.group(2))
    text = path.read_text(encoding="utf-8")
    cur = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("# ") and not adr.title:
            mt = re.match(r"#\s*(\d{4})\.?\s*(.*)", line)
            if mt:
                adr.title_number, adr.title = mt.group(1), mt.group(2).strip()
            else:
                adr.title = line[2:].strip()
            continue
        mk = re.match(r"^-\s*(状态|日期|取代|被取代|决策人)\s*[:：]\s*(.*)$", line)
        if mk and cur is None:
            key, val = mk.group(1), mk.group(2).strip()
            if key == "状态":
                adr.status = val
            elif key == "日期":
                adr.date = val
            elif key == "取代":
                adr.supersedes = re.findall(r"\d{4}", val)
            elif key == "被取代":
                adr.superseded_by = re.findall(r"\d{4}", val)
            continue
        if line.startswith("## "):
            if cur is not None:
                adr.sections[cur] = "\n".join(buf).strip()
            cur, buf = line[3:].strip(), []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        adr.sections[cur] = "\n".join(buf).strip()
    return adr


def load_all(directory: Path) -> tuple[list[Adr], list[Path]]:
    adrs, bad = [], []
    if not directory.is_dir():
        return [], []
    for p in sorted(directory.iterdir()):
        if p.suffix != ".md" or p.name.lower() in ("readme.md", "index.md", "template.md"):
            continue
        if FILE_RE.match(p.name):
            adrs.append(parse(p))
        else:
            bad.append(p)
    return adrs, bad


def has_content(text: str) -> bool:
    """True when the section holds anything beyond template placeholders."""
    for raw in text.splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+[.、)])\s*", "", raw).strip()
        line = re.sub(r"^(?:做法|优点|缺点)\s*[:：]\s*", "", line).strip()
        if line and not PLACEHOLDER.search(line) and not line.startswith("#"):
            return True
    return False


def options_filled(text: str) -> int:
    n = 0
    for block in re.split(r"(?m)^###\s+", text)[1:]:
        head, _, body = block.partition("\n")
        if has_content(body) and not PLACEHOLDER.search(head.split("：", 1)[-1].strip()):
            n += 1
    return n


@dataclass
class Issue:
    level: str
    adr: str
    message: str


def check(adrs: list[Adr], bad: list[Path]) -> list[Issue]:
    issues: list[Issue] = []
    by_num: dict[str, list[Adr]] = {}
    for a in adrs:
        by_num.setdefault(a.number, []).append(a)
    for num, group in by_num.items():
        if len(group) > 1:
            issues.append(
                Issue("必须处理", num, f"编号 {num} 重复：{'、'.join(g.path.name for g in group)}")
            )
    for p in bad:
        issues.append(Issue("提示", p.name, "文件名不符合 NNNN-标题.md，已忽略"))
    nums = sorted(int(n) for n in by_num)
    if nums:
        missing = [f"{i:04d}" for i in range(nums[0], nums[-1] + 1) if i not in nums]
        if missing:
            issues.append(
                Issue(
                    "提示",
                    "-",
                    f"编号不连续，缺：{'、'.join(missing)}（编号不重用，被删除的 ADR 请改状态而不是删文件）",
                )
            )
    for a in adrs:
        name = a.path.name
        if a.title_number and a.title_number != a.number:
            issues.append(
                Issue(
                    "必须处理", name, f"标题里的编号 {a.title_number} 和文件名的 {a.number} 不一致"
                )
            )
        status = normalize_status(a.status)
        if status is None:
            issues.append(
                Issue(
                    "必须处理", name, f"状态“{a.status or '空'}”不合法，应为：{'、'.join(STATUSES)}"
                )
            )
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.date or ""):
            issues.append(Issue("建议修改", name, f"日期“{a.date or '空'}”应为 YYYY-MM-DD"))
        for sec in ("背景", "备选方案", "决策", "后果"):
            if sec not in a.sections:
                issues.append(Issue("必须处理", name, f"缺少“{sec}”一节"))
        if status == "已采纳" or status == "已被取代":
            if not has_content(a.sections.get("背景", "")):
                issues.append(Issue("必须处理", name, "“背景”还是模板占位，没有写内容"))
            if not has_content(a.sections.get("决策", "")):
                issues.append(Issue("必须处理", name, "“决策”还是模板占位，没有写内容"))
            if options_filled(a.sections.get("备选方案", "")) < 2:
                issues.append(Issue("必须处理", name, "备选方案不足两个（只有一个选项的不叫决策）"))
            risks = re.search(
                r"###\s*代价和风险\s*\n(.*?)(?=\n###|\Z)", a.sections.get("后果", ""), re.DOTALL
            )
            if not risks or not has_content(risks.group(1)):
                issues.append(Issue("必须处理", name, "没写“代价和风险”，每个决定都有代价"))
            if not has_content(a.sections.get("重新评审条件", "")):
                issues.append(Issue("提示", name, "没写“重新评审条件”，以后不知道什么时候该回头看"))
        elif status == "提议中" and not has_content(a.sections.get("背景", "")):
            issues.append(Issue("提示", name, "还是模板，背景没写"))
        if status == "已被取代" and not a.superseded_by:
            issues.append(Issue("必须处理", name, "状态是已被取代，但没有写“被取代：NNNN”"))
        for n in a.superseded_by:
            target = by_num.get(n)
            if not target:
                issues.append(Issue("必须处理", name, f"被取代：{n} 不存在"))
            elif a.number not in target[0].supersedes:
                issues.append(
                    Issue("建议修改", name, f"{n} 没有写“取代：{a.number}”，取代关系只写了一边")
                )
        for n in a.supersedes:
            target = by_num.get(n)
            if not target:
                issues.append(Issue("必须处理", name, f"取代：{n} 不存在"))
            elif a.number not in target[0].superseded_by:
                issues.append(
                    Issue("建议修改", name, f"{n} 没有写“被取代：{a.number}”，取代关系只写了一边")
                )
    order = {"必须处理": 0, "建议修改": 1, "提示": 2}
    return sorted(issues, key=lambda i: (order[i.level], i.adr))


def set_header_line(text: str, key: str, value: str | None) -> str:
    """Set (or remove, when value is None) a '- key：value' header line."""
    lines = text.splitlines()
    pat = re.compile(rf"^-\s*{key}\s*[:：]")
    for i, line in enumerate(lines):
        if pat.match(line):
            if value is None:
                del lines[i]
            else:
                lines[i] = f"- {key}：{value}"
            return "\n".join(lines) + "\n"
    if value is None:
        return text
    anchor = max(
        (i for i, ln in enumerate(lines) if re.match(r"^-\s*(状态|日期|决策人)\s*[:：]", ln)),
        default=0,
    )
    lines.insert(anchor + 1, f"- {key}：{value}")
    return "\n".join(lines) + "\n"


def find(directory: Path, number: str) -> Adr:
    num = number.zfill(4)
    adrs, _ = load_all(directory)
    hits = [a for a in adrs if a.number == num]
    if not hits:
        raise SystemExit(f"在 {directory} 找不到编号 {num} 的 ADR")
    return hits[0]


def cmd_new(args: argparse.Namespace) -> int:
    directory = Path(args.dir)
    status = normalize_status(args.status)
    if status is None:
        print(f"状态不合法：{args.status}，应为 {'、'.join(STATUSES)}", file=sys.stderr)
        return 1
    if not args.title.strip():
        print("标题不能为空", file=sys.stderr)
        return 1
    adrs, _ = load_all(directory)
    nxt = max((int(a.number) for a in adrs), default=0) + 1
    num = f"{nxt:04d}"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{num}-{slugify(args.title)}.md"
    path.write_text(
        TEMPLATE.format(
            num=num,
            title=args.title.strip(),
            status=status,
            today=date.today().isoformat(),
            deciders=args.deciders or "（待填）",
        ),
        encoding="utf-8",
    )
    print(path)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    adrs, _ = load_all(Path(args.dir))
    if not adrs:
        print(f"{args.dir} 里还没有 ADR")
        return 0
    print("| 编号 | 状态 | 日期 | 标题 |\n|---|---|---|---|")
    for a in adrs:
        print(f"| {a.number} | {a.status} | {a.date} | {a.title} |")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    directory = Path(args.dir)
    if not directory.is_dir():
        print(f"目录不存在：{directory}", file=sys.stderr)
        return 1
    adrs, bad = load_all(directory)
    issues = check(adrs, bad)
    if args.json:
        print(
            json.dumps(
                {"adr数": len(adrs), "问题": [asdict(i) for i in issues]},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"检查 {len(adrs)} 份 ADR（{directory}）")
        for i in issues:
            print(f"[{i.level}] {i.adr}：{i.message}")
        if not issues:
            print("没有发现问题。")
    return 3 if any(i.level == "必须处理" for i in issues) else 0


def cmd_status(args: argparse.Namespace) -> int:
    status = normalize_status(args.status)
    if status is None:
        print(f"状态不合法：{args.status}，应为 {'、'.join(STATUSES)}", file=sys.stderr)
        return 1
    if status == "已被取代":
        print("请用 supersede 命令标记取代关系", file=sys.stderr)
        return 1
    adr = find(Path(args.dir), args.number)
    adr.path.write_text(
        set_header_line(adr.path.read_text(encoding="utf-8"), "状态", status), encoding="utf-8"
    )
    print(f"{adr.path.name} → {status}")
    return 0


def cmd_supersede(args: argparse.Namespace) -> int:
    directory = Path(args.dir)
    old, new = find(directory, args.old), find(directory, args.new)
    if old.number == new.number:
        print("不能自己取代自己", file=sys.stderr)
        return 1
    t_old = set_header_line(old.path.read_text(encoding="utf-8"), "状态", "已被取代")
    t_old = set_header_line(t_old, "被取代", "、".join(sorted({*old.superseded_by, new.number})))
    old.path.write_text(t_old, encoding="utf-8")
    t_new = set_header_line(
        new.path.read_text(encoding="utf-8"),
        "取代",
        "、".join(sorted({*new.supersedes, old.number})),
    )
    new.path.write_text(t_new, encoding="utf-8")
    print(f"{old.path.name} 已被 {new.path.name} 取代")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="架构决策记录管理")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = {"default": "docs/adr", "help": "ADR 目录，默认 docs/adr"}
    n = sub.add_parser("new")
    n.add_argument("title")
    n.add_argument("--dir", **d)
    n.add_argument("--status", default="提议中")
    n.add_argument("--deciders", default="")
    n.set_defaults(fn=cmd_new)
    li = sub.add_parser("list")
    li.add_argument("--dir", **d)
    li.set_defaults(fn=cmd_list)
    c = sub.add_parser("check")
    c.add_argument("--dir", **d)
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)
    st = sub.add_parser("status")
    st.add_argument("number")
    st.add_argument("status")
    st.add_argument("--dir", **d)
    st.set_defaults(fn=cmd_status)
    sp = sub.add_parser("supersede")
    sp.add_argument("old")
    sp.add_argument("new")
    sp.add_argument("--dir", **d)
    sp.set_defaults(fn=cmd_supersede)
    args = ap.parse_args(argv)
    try:
        return int(args.fn(args))
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
