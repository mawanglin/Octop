#!/usr/bin/env python3
"""项目骨架：按模板生成可以直接运行、自带测试的最小项目，再在此基础上写业务代码。

Usage:
    python scripts/scaffold.py list
    python scripts/scaffold.py new 模板 项目名 [-o 父目录]

模板：
  python-cli   Python 命令行工具（argparse + pyproject + pytest）
  fastapi      FastAPI 接口服务（增删改查示例 + 健康检查 + TestClient 测试 + Dockerfile）
  node-api     Node.js 接口服务（零依赖：node:http + node:test，不用 npm install 就能运行和测试）
  react-vite   React + TypeScript + Vite 前端（需要 npm install）
  static-web   纯静态网页（HTML + CSS + JS，双击即可打开）
目标目录已存在且非空时拒绝生成，不会覆盖任何文件。
Exit codes: 0 ok, 1 输入错误。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

GITIGNORE_PY = "__pycache__/\n*.pyc\n.venv/\nvenv/\n.pytest_cache/\n.ruff_cache/\n.mypy_cache/\ndist/\nbuild/\n*.egg-info/\n.env\n"
GITIGNORE_NODE = "node_modules/\ndist/\ncoverage/\n.env\n.env.local\n*.log\n"

TEMPLATES: dict[str, tuple[str, dict[str, str]]] = {
    "python-cli": (
        "Python 命令行工具",
        {
            "pyproject.toml": """[project]
name = "{name}"
version = "0.1.0"
description = "{title}"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.5"]

[project.scripts]
{name} = "{pkg}.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
""",
            "src/{pkg}/__init__.py": '"""{title}"""\n\n__version__ = "0.1.0"\n',
            "src/{pkg}/core.py": '''"""业务逻辑放在这里，保持和命令行解析分离，方便测试。"""

from __future__ import annotations


def greet(name: str, times: int = 1) -> list[str]:
    if times < 1:
        raise ValueError("times 必须大于等于 1")
    return [f"你好，{{name}}！" for _ in range(times)]
''',
            "src/{pkg}/cli.py": '''"""命令行入口。"""

from __future__ import annotations

import argparse
import sys

from {pkg} import __version__
from {pkg}.core import greet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="{name}", description="{title}")
    parser.add_argument("name", help="要问候的名字")
    parser.add_argument("-n", "--times", type=int, default=1, help="重复次数")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        for line in greet(args.name, args.times):
            print(line)
    except ValueError as exc:
        print(f"错误：{{exc}}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
''',
            "tests/test_cli.py": """import pytest

from {pkg}.cli import main
from {pkg}.core import greet


def test_greet_repeats() -> None:
    assert greet("小明", 2) == ["你好，小明！", "你好，小明！"]


def test_greet_rejects_zero() -> None:
    with pytest.raises(ValueError):
        greet("小明", 0)


def test_cli_prints(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["小明"]) == 0
    assert "你好，小明！" in capsys.readouterr().out


def test_cli_error_exit_code() -> None:
    assert main(["小明", "-n", "0"]) == 1
""",
            "README.md": """# {name}

{title}

## 开发

```bash
python -m venv .venv
source .venv/bin/activate          # Windows：.venv\\Scripts\\activate
pip install -e ".[dev]"
pytest                             # 运行测试
ruff check .                       # 代码规范
{name} 小明 -n 2                    # 运行
```

## 目录

- `src/{pkg}/core.py`：业务逻辑
- `src/{pkg}/cli.py`：命令行参数和入口
- `tests/`：测试
""",
            ".gitignore": GITIGNORE_PY,
        },
    ),
    "fastapi": (
        "FastAPI 接口服务",
        {
            "requirements.txt": "fastapi>=0.110\nuvicorn[standard]>=0.29\n",
            "requirements-dev.txt": "-r requirements.txt\npytest>=8\nhttpx>=0.27\nruff>=0.5\n",
            "app/__init__.py": "",
            "app/main.py": '''"""{title}：FastAPI 应用入口。"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="{title}", version="0.1.0")


class ItemIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="名称")
    price: float = Field(..., ge=0, description="价格，不能为负")
    tags: list[str] = Field(default_factory=list)


class Item(ItemIn):
    id: int


# 示例用内存存储；正式项目换成数据库（SQLAlchemy / SQLModel 等）
_items: dict[int, Item] = {{}}
_next_id = 1


@app.get("/health", summary="健康检查")
def health() -> dict[str, str]:
    return {{"status": "ok"}}


@app.get("/items", response_model=list[Item], summary="列出全部")
def list_items(limit: int = 50, offset: int = 0) -> list[Item]:
    return list(_items.values())[offset : offset + limit]


@app.post("/items", response_model=Item, status_code=201, summary="新建")
def create_item(body: ItemIn) -> Item:
    global _next_id
    item = Item(id=_next_id, **body.model_dump())
    _items[item.id] = item
    _next_id += 1
    return item


@app.get("/items/{{item_id}}", response_model=Item, summary="查看")
def get_item(item_id: int) -> Item:
    if item_id not in _items:
        raise HTTPException(status_code=404, detail="不存在")
    return _items[item_id]


@app.put("/items/{{item_id}}", response_model=Item, summary="修改")
def update_item(item_id: int, body: ItemIn) -> Item:
    if item_id not in _items:
        raise HTTPException(status_code=404, detail="不存在")
    _items[item_id] = Item(id=item_id, **body.model_dump())
    return _items[item_id]


@app.delete("/items/{{item_id}}", status_code=204, summary="删除")
def delete_item(item_id: int) -> None:
    if _items.pop(item_id, None) is None:
        raise HTTPException(status_code=404, detail="不存在")
''',
            "tests/__init__.py": "",
            "tests/test_main.py": """from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/health").json() == {{"status": "ok"}}


def test_crud_flow() -> None:
    created = client.post("/items", json={{"name": "苹果", "price": 3.5}})
    assert created.status_code == 201
    item_id = created.json()["id"]
    assert client.get(f"/items/{{item_id}}").json()["name"] == "苹果"
    updated = client.put(f"/items/{{item_id}}", json={{"name": "苹果", "price": 4}})
    assert updated.json()["price"] == 4
    assert client.delete(f"/items/{{item_id}}").status_code == 204
    assert client.get(f"/items/{{item_id}}").status_code == 404


def test_validation_error() -> None:
    assert client.post("/items", json={{"name": "", "price": -1}}).status_code == 422
""",
            "Dockerfile": """FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
""",
            "README.md": """# {name}

{title}

## 开发

```bash
python -m venv .venv
source .venv/bin/activate          # Windows：.venv\\Scripts\\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload      # 启动，接口文档：http://127.0.0.1:8000/docs
pytest                             # 运行测试
```

## 部署

```bash
docker build -t {name} .
docker run -p 8000:8000 {name}
```
""",
            ".gitignore": GITIGNORE_PY,
        },
    ),
    "node-api": (
        "Node.js 接口服务",
        {
            "package.json": """{{
  "name": "{name}",
  "version": "0.1.0",
  "description": "{title}",
  "type": "module",
  "main": "src/server.js",
  "engines": {{ "node": ">=18" }},
  "scripts": {{
    "start": "node src/server.js",
    "dev": "node --watch src/server.js",
    "test": "node --test"
  }}
}}
""",
            "src/app.js": """// 路由和业务逻辑：零依赖，只用 Node.js 内置模块。
import {{ createServer }} from "node:http";

const items = new Map();
let nextId = 1;

function send(res, status, body) {{
  res.writeHead(status, {{ "Content-Type": "application/json; charset=utf-8" }});
  res.end(body === undefined ? "" : JSON.stringify(body));
}}

async function readJson(req) {{
  let raw = "";
  for await (const chunk of req) {{
    raw += chunk;
    if (raw.length > 1e6) throw new Error("请求体过大");
  }}
  return raw ? JSON.parse(raw) : {{}};
}}

function validate(body) {{
  if (typeof body.name !== "string" || !body.name.trim()) return "name 不能为空";
  if (typeof body.price !== "number" || body.price < 0) return "price 必须是非负数字";
  return null;
}}

export function createApp() {{
  return createServer(async (req, res) => {{
    const url = new URL(req.url, "http://localhost");
    const match = url.pathname.match(/^\\/items\\/(\\d+)$/);
    try {{
      if (req.method === "GET" && url.pathname === "/health") return send(res, 200, {{ status: "ok" }});
      if (req.method === "GET" && url.pathname === "/items") return send(res, 200, [...items.values()]);
      if (req.method === "POST" && url.pathname === "/items") {{
        const body = await readJson(req);
        const error = validate(body);
        if (error) return send(res, 422, {{ error }});
        const item = {{ id: nextId++, name: body.name, price: body.price }};
        items.set(item.id, item);
        return send(res, 201, item);
      }}
      if (match) {{
        const id = Number(match[1]);
        if (!items.has(id)) return send(res, 404, {{ error: "不存在" }});
        if (req.method === "GET") return send(res, 200, items.get(id));
        if (req.method === "DELETE") {{
          items.delete(id);
          return send(res, 204);
        }}
      }}
      return send(res, 404, {{ error: "接口不存在" }});
    }} catch (err) {{
      return send(res, 400, {{ error: err instanceof SyntaxError ? "JSON 格式错误" : String(err.message) }});
    }}
  }});
}}
""",
            "src/server.js": """import {{ createApp }} from "./app.js";

const port = Number(process.env.PORT || 3000);
createApp().listen(port, () => console.log(`已启动：http://127.0.0.1:${{port}}`));
""",
            "test/app.test.js": """import {{ test, before, after }} from "node:test";
import assert from "node:assert/strict";
import {{ createApp }} from "../src/app.js";

let server;
let base;

before(async () => {{
  server = createApp();
  await new Promise((resolve) => server.listen(0, resolve));
  base = `http://127.0.0.1:${{server.address().port}}`;
}});

after(() => server.close());

test("health", async () => {{
  const res = await fetch(`${{base}}/health`);
  assert.deepEqual(await res.json(), {{ status: "ok" }});
}});

test("create, read and delete an item", async () => {{
  const created = await fetch(`${{base}}/items`, {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({{ name: "苹果", price: 3.5 }}),
  }});
  assert.equal(created.status, 201);
  const {{ id }} = await created.json();
  assert.equal((await (await fetch(`${{base}}/items/${{id}}`)).json()).name, "苹果");
  assert.equal((await fetch(`${{base}}/items/${{id}}`, {{ method: "DELETE" }})).status, 204);
  assert.equal((await fetch(`${{base}}/items/${{id}}`)).status, 404);
}});

test("rejects invalid input", async () => {{
  const res = await fetch(`${{base}}/items`, {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({{ name: "", price: -1 }}),
  }});
  assert.equal(res.status, 422);
}});
""",
            "README.md": """# {name}

{title}（零依赖，需要 Node.js 18+）

```bash
npm start      # 启动：http://127.0.0.1:3000/health
npm run dev    # 修改代码后自动重启
npm test       # 运行测试
```

需要数据库、鉴权、参数校验库时再按需 `npm install`（如 better-sqlite3、zod）。
""",
            ".gitignore": GITIGNORE_NODE,
        },
    ),
    "react-vite": (
        "React + TypeScript + Vite 前端",
        {
            "package.json": """{{
  "name": "{name}",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {{
    "dev": "vite",
    "build": "tsc -b && vite build",
    "typecheck": "tsc -b",
    "preview": "vite preview"
  }},
  "dependencies": {{
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  }},
  "devDependencies": {{
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.4",
    "vite": "^5.4.0"
  }}
}}
""",
            "index.html": """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""",
            "vite.config.ts": """import {{ defineConfig }} from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({{
  plugins: [react()],
  // 开发时把 /api 转发到后端，避免跨域
  server: {{ proxy: {{ "/api": "http://127.0.0.1:8000" }} }},
}});
""",
            "tsconfig.json": """{{
  "compilerOptions": {{
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "skipLibCheck": true,
    "noEmit": true
  }},
  "include": ["src"]
}}
""",
            "src/main.tsx": """import {{ StrictMode }} from "react";
import {{ createRoot }} from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
""",
            "src/App.tsx": """import {{ useState }} from "react";

type Todo = {{ id: number; text: string; done: boolean }};

export default function App() {{
  const [todos, setTodos] = useState<Todo[]>([]);
  const [text, setText] = useState("");

  const add = () => {{
    const value = text.trim();
    if (!value) return;
    setTodos([...todos, {{ id: Date.now(), text: value, done: false }}]);
    setText("");
  }};

  return (
    <main className="container">
      <h1>{title}</h1>
      <form onSubmit={{(e) => {{ e.preventDefault(); add(); }}}}>
        <label htmlFor="todo">待办</label>
        <input id="todo" value={{text}} onChange={{(e) => setText(e.target.value)}} placeholder="输入后回车" />
        <button type="submit">添加</button>
      </form>
      <ul>
        {{todos.map((t) => (
          <li key={{t.id}}>
            <label>
              <input
                type="checkbox"
                checked={{t.done}}
                onChange={{() => setTodos(todos.map((x) => (x.id === t.id ? {{ ...x, done: !x.done }} : x)))}}
              />
              <span className={{t.done ? "done" : ""}}>{{t.text}}</span>
            </label>
          </li>
        ))}}
      </ul>
    </main>
  );
}}
""",
            "src/index.css": """:root {{ color-scheme: light dark; font-family: system-ui, "PingFang SC", "Microsoft YaHei", sans-serif; }}
body {{ margin: 0; }}
.container {{ max-width: 640px; margin: 0 auto; padding: 24px 16px; }}
form {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
input:not([type="checkbox"]) {{ flex: 1; min-width: 0; padding: 8px; }}
.done {{ text-decoration: line-through; opacity: 0.6; }}
""",
            "README.md": """# {name}

{title}

```bash
npm install
npm run dev        # 开发：http://localhost:5173
npm run typecheck  # 类型检查
npm run build      # 构建到 dist/
```

后端接口地址在 `vite.config.ts` 的 proxy 里配置。
""",
            ".gitignore": GITIGNORE_NODE,
        },
    ),
    "static-web": (
        "纯静态网页",
        {
            "index.html": """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <main class="container">
    <h1>{title}</h1>
    <p id="message">页面已加载。</p>
    <button id="btn" type="button">点我</button>
  </main>
  <script src="app.js"></script>
</body>
</html>
""",
            "style.css": """:root {{ color-scheme: light dark; --accent: #2563eb; }}
body {{ margin: 0; font-family: system-ui, "PingFang SC", "Microsoft YaHei", sans-serif; }}
.container {{ max-width: 720px; margin: 0 auto; padding: 24px 16px; }}
button {{ padding: 10px 16px; min-height: 44px; border: 0; border-radius: 8px; background: var(--accent); color: #fff; }}
""",
            "app.js": """document.addEventListener("DOMContentLoaded", () => {{
  let count = 0;
  document.getElementById("btn").addEventListener("click", () => {{
    count += 1;
    document.getElementById("message").textContent = `点击了 ${{count}} 次`;
  }});
}});
""",
            "README.md": "# {name}\n\n{title}\n\n双击 `index.html` 即可打开；部署时把整个目录上传到任意静态网站托管即可。\n",
        },
    ),
}


def slug(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("项目名只能用英文字母开头，包含字母、数字、- 和 _，最长 64 个字符")
    return name


def create(template: str, name: str, parent: Path, title: str | None = None) -> list[Path]:
    if template not in TEMPLATES:
        raise ValueError(f"没有模板 {template}，可选：{', '.join(TEMPLATES)}")
    name = slug(name)
    target = parent / name
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError(f"{target} 已存在且非空，不会覆盖；换一个项目名或目录")
    label, files = TEMPLATES[template]
    values = {"name": name, "pkg": name.replace("-", "_").lower(), "title": title or name}
    written = []
    for rel, body in files.items():
        path = target / rel.format(**values)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body.format(**values), encoding="utf-8", newline="\n")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    new = sub.add_parser("new")
    new.add_argument("template")
    new.add_argument("name")
    new.add_argument("-o", "--output", default=".", help="父目录，默认当前目录")
    new.add_argument("--title", help="项目中文名称，默认同项目名")
    args = parser.parse_args(argv)

    if args.cmd == "list":
        for key, (label, files) in TEMPLATES.items():
            print(f"- {key}：{label}（{len(files)} 个文件）")
        return 0
    try:
        written = create(args.template, args.name, Path(args.output), args.title)
    except ValueError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    root = Path(args.output) / args.name
    print(f"已生成 {args.template}：{root}")
    for p in written:
        print(f"  {p.relative_to(root).as_posix()}")
    print("下一步：按 README.md 安装依赖并运行测试，然后用 code_check.py run 自检。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
