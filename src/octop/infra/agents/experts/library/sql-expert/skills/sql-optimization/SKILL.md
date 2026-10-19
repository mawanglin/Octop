---
name: sql-optimization
description: "SQL 优化与设计：索引设计原则（最左前缀、选择性、覆盖索引、联合索引列顺序、过多索引的写入代价），执行计划解读（MySQL type/key/rows/Extra、PostgreSQL Seq Scan/Index Scan/cost、SQLite SCAN/SEARCH），慢查询常见原因和改写（函数作用于列、隐式类型转换、OR、深分页、子查询改 JOIN、N+1），表结构设计（主键、范式与反范式、时间和金额类型、软删除），MySQL / PostgreSQL / SQLite / SQL Server / Oracle 常见语法差异（分页、自增、字符串拼接、日期函数、UPSERT）。优化慢查询、设计索引或表、跨数据库改写 SQL 时使用。"
metadata:
  octop:
    emoji: "⚡"
    label:
      zh: "优化与设计"
      en: "SQL Optimization"
    summary:
      zh: "索引、执行计划、慢查询改写和方言差异。"
      en: "Indexes, plans, rewrites and dialect differences."
---

# SQL 优化与设计

## 1. 索引设计

- **最左前缀**：联合索引 (a, b, c) 能用于 `a`、`a,b`、`a,b,c` 的条件；只有 `b` 用不上。
- **列顺序**：等值条件的列在前，范围条件（>、<、BETWEEN）的列在后；选择性高的列优先。
- **覆盖索引**：查询的列都在索引里时不用回表，`SELECT *` 会破坏这一点。
- **代价**：每个索引都会拖慢写入、占用空间；低选择性的列（性别、状态）单独建索引意义不大。

## 2. 执行计划速读

| 数据库 | 看什么 | 危险信号 |
|--------|--------|----------|
| MySQL `EXPLAIN` | type、key、rows、Extra | type=ALL（全表）、Extra 含 Using filesort / Using temporary、rows 很大 |
| PostgreSQL `EXPLAIN ANALYZE` | 节点类型、actual time、rows 估计与实际 | 大表 Seq Scan、估计行数与实际差几个数量级（需 ANALYZE 更新统计） |
| SQLite `EXPLAIN QUERY PLAN` | SCAN / SEARCH | 大表 SCAN |

## 3. 慢查询常见原因和改写

| 原因 | 改写 |
|------|------|
| `WHERE DATE(created_at) = '2026-10-19'` | `WHERE created_at >= '2026-10-19' AND created_at < '2026-10-20'` |
| 字符串列和数字比较（隐式转换） | 两边类型一致：`phone = '13800000000'` |
| `OR` 跨列 | 拆成 `UNION ALL`，或分别建索引 |
| `LIMIT 100000, 20` 深分页 | 游标分页：`WHERE id > 上一页最后 id ORDER BY id LIMIT 20` |
| `NOT IN (子查询)` | `NOT EXISTS` |
| 循环里逐条查询（N+1） | 一次 `IN (...)` 或 JOIN 查出来 |
| `COUNT(*)` 大表实时统计 | 缓存计数或近似值 |

## 4. 表结构设计

- 每张表有主键；业务唯一性用唯一索引保证。
- 金额用 DECIMAL，不用 FLOAT；时间统一时区（存 UTC 或带时区类型）。
- 软删除字段（`deleted_at`）记得进入索引和唯一约束的设计。
- 先满足第三范式，确有性能需求再有意识地冗余，并说明同步方式。

## 5. 方言差异速查

| 功能 | MySQL | PostgreSQL | SQLite | SQL Server | Oracle |
|------|-------|-----------|--------|-----------|--------|
| 分页 | `LIMIT n OFFSET m` | 同左 | 同左 | `OFFSET m ROWS FETCH NEXT n ROWS ONLY` | 12c+ 同 SQL Server |
| 自增 | `AUTO_INCREMENT` | `GENERATED … AS IDENTITY` / `SERIAL` | `INTEGER PRIMARY KEY` | `IDENTITY(1,1)` | `GENERATED AS IDENTITY` |
| 拼接 | `CONCAT(a, b)` | `a \|\| b` | `a \|\| b` | `a + b` / `CONCAT` | `a \|\| b` |
| 当前时间 | `NOW()` | `NOW()` | `datetime('now')` | `GETDATE()` | `SYSDATE` |
| UPSERT | `INSERT … ON DUPLICATE KEY UPDATE` | `INSERT … ON CONFLICT … DO UPDATE` | 同 PostgreSQL | `MERGE` | `MERGE` |
