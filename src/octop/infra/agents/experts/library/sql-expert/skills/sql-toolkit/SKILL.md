---
name: sql-toolkit
description: "SQL 工具：sql_check.py lint 检查 .sql 文件或单条 SQL 的常见问题（UPDATE/DELETE 没有 WHERE、= NULL、SELECT *、隐式连接、WHERE 中对列套函数、LIKE 前导通配符、NOT IN 子查询、ORDER BY RAND、INSERT 不写列名、DROP/TRUNCATE、OR 跨列、深分页、ORDER BY 无 LIMIT），按错误/警告/提示分级；explain 以只读方式打开 SQLite 数据库输出 EXPLAIN QUERY PLAN 并标出全表扫描；er 把 CREATE TABLE 语句或 SQLite 库转成 Mermaid erDiagram（主键、外键、关系），并提示没有主键的表。写完 SQL 自查、看执行计划、画表关系图时使用。"
metadata:
  octop:
    emoji: "🗄️"
    label:
      zh: "SQL 工具"
      en: "SQL Toolkit"
    summary:
      zh: "SQL 静态检查、执行计划和表关系图。"
      en: "SQL lint, query plans and ER diagrams."
---

# SQL 工具

> `scripts/` 和 `references/` 路径相对于本技能目录；示例：`references/example-schema.sql`（建表）、`references/example-queries.sql`（含常见问题的查询）。

## 1. 静态检查

```bash
python scripts/sql_check.py lint 查询.sql
python scripts/sql_check.py lint "SELECT * FROM orders WHERE YEAR(created_at) = 2026"
```

| 等级 | 规则 |
|------|------|
| 错误 | UPDATE / DELETE 没有 WHERE；`= NULL` / `!= NULL` |
| 警告 | `SELECT *`；`FROM a, b` 隐式连接；条件中对列套函数（索引失效）；`LIKE '%…'`；`NOT IN (子查询)`；`ORDER BY RAND()`；INSERT 不写列名；`WHERE 1=1` 的更新删除；DROP / TRUNCATE |
| 提示 | OR 连接不同列；OFFSET ≥ 10000 的深分页；ORDER BY 没有 LIMIT |

基于文本规则，不做完整语法解析；字符串和注释里的内容不会误报。有错误或警告时退出码为 3。

## 2. SQLite 执行计划

```bash
python scripts/sql_check.py explain 数据库.db "SELECT o.id FROM orders o JOIN customers c ON c.id = o.customer_id WHERE c.city = '上海'"
```

以只读方式打开，只接受 SELECT / WITH。`SCAN 表` 表示全表扫描，`SEARCH … USING INDEX` 表示用到了索引。MySQL / PostgreSQL 请用户执行 `EXPLAIN`（PostgreSQL 推荐 `EXPLAIN (ANALYZE, BUFFERS)`）后把结果发来，按 `sql-optimization` 解读。

## 3. 表关系图

```bash
python scripts/sql_check.py er references/example-schema.sql -o outputs/sql/表关系.mmd
python scripts/sql_check.py er 数据库.db
```

识别列定义上的 `REFERENCES`、表级 `FOREIGN KEY … REFERENCES`、`PRIMARY KEY`（含联合主键）。输出 Mermaid `erDiagram`，可交给「流程图设计专家」渲染。没有外键约束的库只能画出表，关系需要按命名约定（如 `xxx_id`）人工补充。
