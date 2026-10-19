---
name: project-scaffold
description: "项目骨架：scaffold.py 生成可直接运行、自带测试的最小项目——python-cli（argparse + pyproject + pytest）、fastapi（增删改查 + 健康检查 + TestClient 测试 + Dockerfile）、node-api（零依赖 node:http + node:test）、react-vite（React + TypeScript + Vite）、static-web（纯静态网页）；目标目录非空时拒绝生成。从零开始一个新项目或新服务时使用，并给出目录结构和技术选型建议。"
metadata:
  octop:
    emoji: "🏗️"
    label:
      zh: "项目骨架"
      en: "Project Scaffold"
    summary:
      zh: "一条命令生成能跑、带测试的项目模板。"
      en: "Generates runnable, tested starter projects."
---

# 项目骨架

> `scripts/` 路径相对于本技能目录。

## 1. 生成

```bash
python scripts/scaffold.py list
python scripts/scaffold.py new fastapi order-service -o outputs/code --title 订单服务
```

| 模板 | 适合 | 生成后 |
|------|------|--------|
| `python-cli` | 命令行工具、数据处理脚本、定时任务 | `pip install -e ".[dev]"` → `pytest` |
| `fastapi` | 后端接口、给前端或小程序用的 API | `pip install -r requirements-dev.txt` → `pytest` → `uvicorn app.main:app --reload` |
| `node-api` | 轻量接口、Webhook 接收、无法装依赖的环境 | 无需安装，`npm test` / `npm start` |
| `react-vite` | 管理后台、单页应用 | `npm install` → `npm run dev` |
| `static-web` | 展示页、单页小工具 | 双击 `index.html` |

项目名只能用英文字母开头（字母、数字、`-`、`_`），中文名用 `--title`。生成后**先跑一次测试**确认模板在用户环境里可用，再开始写业务代码。

## 2. 选型建议

先问清楚：谁用、部署在哪（个人电脑 / NAS / 云服务器 / 小程序）、数据量、团队熟悉的语言。默认选择：

| 需求 | 推荐 |
|------|------|
| 后端接口 | Python + FastAPI；团队熟悉 JS 时用 Node（Express / Fastify） |
| 数据库 | 单机小项目 SQLite；多用户、并发写入用 PostgreSQL；缓存和队列再加 Redis |
| 前端 | React + TypeScript + Vite；组件库 Ant Design / shadcn/ui；只是几个页面时不用框架 |
| 部署 | Docker Compose；静态页面放对象存储或 Nginx |
| 鉴权 | 自用工具用简单令牌；多用户用成熟方案（如 OAuth / 现成的认证库），不要自己写密码加密 |

不为"以后可能用到"引入微服务、消息队列、复杂框架；先用最简单能工作的方案，需要时再拆。

## 3. 推荐目录结构

```
后端（Python）          前端（React）              全栈
app/                    src/                       backend/   ← fastapi 模板
  main.py   入口         components/ 通用组件        frontend/  ← react-vite 模板
  routers/  路由         pages/      页面            docker-compose.yml
  services/ 业务逻辑     api/        请求封装        README.md
  models/   数据模型     hooks/
tests/                  App.tsx
```

路由只做参数校验和调用，业务逻辑放 services，数据库访问集中在一处；前端请求统一封装在 `api/`，不在组件里到处写 fetch。
