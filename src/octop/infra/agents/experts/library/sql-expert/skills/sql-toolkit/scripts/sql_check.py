#!/usr/bin/env python3
"""SQL 工具：静态检查常见问题、在 SQLite 上看执行计划、把建表语句画成 Mermaid 表关系图。不修改任何数据。

Usage:
    python scripts/sql_check.py lint 查询.sql            （或直接传一条 SQL 字符串）
    python scripts/sql_check.py explain 数据库.db "SELECT ..."   （只读打开 SQLite，EXPLAIN QUERY PLAN）
    python scripts/sql_check.py er 建表.sql|数据库.db [-o 表关系.mmd]

lint 规则（等级：错误 / 警告 / 提示）：
  错误：UPDATE / DELETE 没有 WHERE；用 = NULL / != NULL 比较空值；
  警告：SELECT *；隐式连接 FROM a, b；WHERE 中对列套函数（索引失效）；LIKE 以 % 开头；NOT IN 子查询（遇 NULL 结果为空）；
        ORDER BY RAND()/RANDOM()；INSERT 不写列名；WHERE 1=1 的更新删除；DROP / TRUNCATE；
  提示：OR 连接不同列（可能用不上索引）；OFFSET 很大的深分页；没有 LIMIT 的 ORDER BY。
基于文本规则检查，不解析完整语法，适用于 MySQL / PostgreSQL / SQLite / SQL Server 的常见写法。
Exit codes: 0 无错误和警告, 3 有错误或警告, 1 输入错误。
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path


class SqlError(ValueError):
    pass


def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def mask_strings(sql: str) -> str:
    """Replace string literal contents with x so rules don't fire on text inside quotes."""
    return re.sub(r"'(?:[^']|'')*'", lambda m: "'" + "x" * (len(m.group(0)) - 2) + "'", sql)


def split_statements(sql: str) -> list[str]:
    out, buf, quote = [], [], False
    for ch in sql:
        if ch == "'":
            quote = not quote
        if ch == ";" and not quote:
            if "".join(buf).strip():
                out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        out.append("".join(buf).strip())
    return out


FUNC_ON_COL = re.compile(
    r"\b(?:WHERE|AND|OR|ON)\s+(?:NOT\s+)?(DATE|YEAR|MONTH|LOWER|UPPER|SUBSTR|SUBSTRING|LEFT|RIGHT|TRIM|CAST|CONVERT|DATE_FORMAT|TO_CHAR|IFNULL|COALESCE|ABS|ROUND|STRFTIME)\s*\(\s*[A-Za-z_][\w.]*",
    re.I,
)


def lint_statement(stmt: str) -> list[tuple[str, str]]:
    s = mask_strings(strip_comments(stmt))
    flat = re.sub(r"\s+", " ", s).strip()
    up = flat.upper()
    issues: list[tuple[str, str]] = []
    kind = up.split(" ", 1)[0] if up else ""
    if kind in ("UPDATE", "DELETE") and " WHERE " not in f" {up} ":
        issues.append(
            ("错误", f"{kind} 没有 WHERE，会影响整张表；确认后先用 SELECT 预览受影响的行")
        )
    if (
        re.search(r"\bWHERE\s+1\s*=\s*1\b", up)
        and kind in ("UPDATE", "DELETE")
        and not re.search(r"\b1\s*=\s*1\s+AND\b", up)
    ):
        issues.append(("警告", "WHERE 1=1 没有其他条件，等于更新 / 删除整张表"))
    if re.search(r"(?:=|<>|!=)\s*NULL\b", up):
        issues.append(("错误", "与 NULL 比较要用 IS NULL / IS NOT NULL，= NULL 永远不成立"))
    if re.search(r"\bSELECT\s+(?:DISTINCT\s+)?(?:\w+\.)?\*", up) and not re.search(
        r"\bEXISTS\s*\(\s*SELECT\s+\*", up
    ):
        issues.append(
            (
                "警告",
                "SELECT * 会读取不需要的列、无法走覆盖索引，表结构变化时也容易出错；写明需要的列",
            )
        )
    if re.search(r"\bFROM\s+[\w.]+(?:\s+(?:AS\s+)?\w+)?\s*,\s*[\w.]+", up) and " JOIN " not in up:
        issues.append(
            ("警告", "FROM a, b 是隐式连接，漏写条件就会变成笛卡尔积；改用显式 JOIN … ON")
        )
    m = FUNC_ON_COL.search(flat)
    if m:
        issues.append(
            (
                "警告",
                f"条件里对列使用函数 {m.group(1).upper()}()，该列上的索引会失效；改成对常量做变换或范围比较",
            )
        )
    if re.search(
        r"\bLIKE\s+'%", re.sub(r"\s+", " ", strip_comments(stmt)).upper()
    ):  # literal text matters here
        issues.append(
            ("警告", "LIKE '%…' 以通配符开头无法使用普通索引，数据量大时考虑全文索引或改为前缀匹配")
        )
    if re.search(r"\bNOT\s+IN\s*\(\s*SELECT\b", up):
        issues.append(("警告", "NOT IN (子查询) 中只要有 NULL，结果就为空；改用 NOT EXISTS"))
    if re.search(r"\bORDER\s+BY\s+(?:RAND|RANDOM|NEWID)\s*\(\s*\)", up):
        issues.append(
            ("警告", "ORDER BY RAND() 需要给每行排序，大表很慢；改用随机主键范围或预先抽样")
        )
    if kind == "INSERT" and re.match(
        r"INSERT\s+(?:INTO\s+)?[\w.`\"\[\]]+\s+(?:VALUES|SELECT)\b", up
    ):
        issues.append(
            ("警告", "INSERT 没有写列名，表结构调整后会插错列；写成 INSERT INTO t (a, b) VALUES …")
        )
    if kind in ("DROP", "TRUNCATE"):
        issues.append(("警告", f"{kind} 不可恢复，执行前确认备份和目标环境"))
    where = re.search(r"\bWHERE\b(.*?)(?:\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|$)", up)
    if where and " OR " in where.group(1):
        cols = set(re.findall(r"([A-Z_][\w.]*)\s*(?:=|>|<|\bIN\b|\bLIKE\b)", where.group(1)))
        if len(cols) > 1:
            issues.append(
                ("提示", "OR 连接了不同列，可能用不上索引；可以改成 UNION ALL 或分别建索引")
            )
    off = re.search(r"\bOFFSET\s+(\d+)|\bLIMIT\s+(\d+)\s*,\s*\d+", up)
    if off and int(off.group(1) or off.group(2)) >= 10000:
        issues.append(
            (
                "提示",
                "深分页（OFFSET 很大）会扫描并丢弃前面所有行；改用“上一页最后一个 id”做游标分页",
            )
        )
    if (
        kind == "SELECT"
        and " ORDER BY " in up
        and " LIMIT " not in up
        and " TOP " not in up
        and " FETCH " not in up
    ):
        issues.append(("提示", "ORDER BY 没有 LIMIT，会对全部结果排序；只需要前几条时加 LIMIT"))
    return issues


def cmd_lint(source: str) -> int:
    p = Path(source)
    text = p.read_text(encoding="utf-8") if p.suffix.lower() == ".sql" and p.is_file() else source
    stmts = split_statements(text)
    if not stmts:
        raise SqlError("没有找到 SQL 语句")
    total = {"错误": 0, "警告": 0, "提示": 0}
    for i, stmt in enumerate(stmts, start=1):
        issues = lint_statement(stmt)
        flat = re.sub(r"\s+", " ", strip_comments(stmt)).strip()
        print(f"[{i}] {flat[:70]}{'…' if len(flat) > 70 else ''}")
        if not issues:
            print("    没有发现问题")
        for lv, msg in issues:
            total[lv] += 1
            print(f"    - [{lv}] {msg}")
    print(
        f"共 {len(stmts)} 条语句：错误 {total['错误']}，警告 {total['警告']}，提示 {total['提示']}"
    )
    return 3 if total["错误"] or total["警告"] else 0


def cmd_explain(db: Path, sql: str) -> int:
    if not db.is_file():
        raise SqlError(f"找不到数据库文件 {db}")
    if not re.match(r"\s*(SELECT|WITH)\b", sql, re.I):
        raise SqlError("explain 只接受 SELECT / WITH 查询")
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
    except sqlite3.Error as exc:
        raise SqlError(f"SQLite 报错：{exc}") from None
    finally:
        conn.close()
    print("执行计划：")
    scans = []
    for row in rows:
        detail = str(row[-1])
        print(f"- {detail}")
        m = re.match(r"SCAN (?:TABLE )?(\w+)(?! USING (?:COVERING )?INDEX)", detail)
        if m and "USING" not in detail:
            scans.append(m.group(1))
    if scans:
        print(
            f"全表扫描：{'、'.join(scans)}。如果这些表数据量大，检查 WHERE / JOIN 列上是否有合适的索引。"
        )
    else:
        print("没有全表扫描。")
    return 0


TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?([\w.]+)[`\"\]]?\s*\((.*?)\)\s*[^()]*?(?:;|$)",
    re.I | re.S,
)


def _split_columns(body: str) -> list[str]:
    parts, depth, buf = [], 0, []
    for ch in body:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf).strip())
    return parts


def schema_from_sql(text: str) -> dict[str, dict[str, object]]:
    tables: dict[str, dict[str, object]] = {}
    for m in TABLE_RE.finditer(strip_comments(text)):
        name = m.group(1).split(".")[-1]
        cols: list[tuple[str, str, str]] = []
        fks: list[tuple[str, str]] = []
        pks: set[str] = set()
        for part in _split_columns(m.group(2)):
            up = part.upper()
            pk = re.match(r"(?:CONSTRAINT\s+\w+\s+)?PRIMARY\s+KEY\s*\(([^)]+)\)", part, re.I)
            fk = re.match(
                r"(?:CONSTRAINT\s+\w+\s+)?FOREIGN\s+KEY\s*\(([^)]+)\)\s*REFERENCES\s+[`\"\[]?([\w.]+)",
                part,
                re.I,
            )
            if pk:
                pks |= {c.strip(' `"[]') for c in pk.group(1).split(",")}
            elif fk:
                for c in fk.group(1).split(","):
                    fks.append((c.strip(' `"[]'), fk.group(2).split(".")[-1]))
            elif not re.match(r"(UNIQUE|INDEX|KEY|CHECK|CONSTRAINT)\b", up):
                cm = re.match(r"[`\"\[]?(\w+)[`\"\]]?\s+([\w]+(?:\s*\([^)]*\))?)?", part)
                if not cm:
                    continue
                col, typ = cm.group(1), (cm.group(2) or "").replace(" ", "")
                ref = re.search(r"REFERENCES\s+[`\"\[]?([\w.]+)", part, re.I)
                if ref:
                    fks.append((col, ref.group(1).split(".")[-1]))
                if "PRIMARY KEY" in up:
                    pks.add(col)
                cols.append((col, typ or "text", ""))
        tables[name] = {
            "columns": [(c, t, "PK" if c in pks else "") for c, t, _ in cols],
            "fks": fks,
        }
    return tables


def schema_from_db(db: Path) -> dict[str, dict[str, object]]:
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        names = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        tables: dict[str, dict[str, object]] = {}
        for n in names:
            cols = [
                (r[1], r[2] or "text", "PK" if r[5] else "")
                for r in conn.execute(f'PRAGMA table_info("{n}")')
            ]
            fks = [(r[3], r[2]) for r in conn.execute(f'PRAGMA foreign_key_list("{n}")')]
            tables[n] = {"columns": cols, "fks": fks}
        return tables
    finally:
        conn.close()


def to_mermaid(tables: dict[str, dict[str, object]]) -> str:
    lines = ["erDiagram"]
    for name, t in tables.items():
        lines.append(f"  {name} {{")
        for col, typ, key in t["columns"]:  # type: ignore[attr-defined]
            fk = any(c == col for c, _ in t["fks"])  # type: ignore[attr-defined]
            mark = ", ".join(x for x in (key, "FK" if fk else "") if x)
            base = re.match(r"\w+", str(typ))
            safe_type = base.group(0) if base else "text"  # Mermaid types can't contain "(50)"
            lines.append(f"    {safe_type} {col}{(' ' + mark) if mark else ''}")
        lines.append("  }")
    for name, t in tables.items():
        for col, ref in t["fks"]:  # type: ignore[attr-defined]
            if ref in tables:
                lines.append(f'  {ref} ||--o{{ {name} : "{col}"')
    return "\n".join(lines) + "\n"


def cmd_er(source: Path, out: Path | None) -> int:
    if not source.is_file():
        raise SqlError(f"找不到 {source}")
    if source.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
        tables = schema_from_db(source)
    else:
        tables = schema_from_sql(source.read_text(encoding="utf-8"))
    if not tables:
        raise SqlError("没有找到 CREATE TABLE 语句")
    mmd = to_mermaid(tables)
    fk_n = sum(len(t["fks"]) for t in tables.values())  # type: ignore[arg-type]
    no_pk = [n for n, t in tables.items() if not any(k for _c, _t, k in t["columns"])]  # type: ignore[attr-defined]
    print(f"{len(tables)} 张表，{fk_n} 个外键关系")
    if no_pk:
        print(f"没有主键的表：{'、'.join(no_pk)}（建议补充主键）")
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(mmd, encoding="utf-8")
        print(f"已生成 {out}（Mermaid erDiagram，可交给流程图设计专家渲染）")
    else:
        print(mmd)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    lint = sub.add_parser("lint")
    lint.add_argument("source", help=".sql 文件或一条 SQL")
    ex = sub.add_parser("explain")
    ex.add_argument("db")
    ex.add_argument("sql")
    er = sub.add_parser("er")
    er.add_argument("source")
    er.add_argument("-o", "--output")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "lint":
            return cmd_lint(args.source)
        if args.cmd == "explain":
            return cmd_explain(Path(args.db), args.sql)
        return cmd_er(Path(args.source), Path(args.output) if args.output else None)
    except (OSError, SqlError, sqlite3.Error) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
