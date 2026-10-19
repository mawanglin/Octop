---
name: api-test-design
description: "接口测试设计：用例设计方法（等价类、边界值、错误推测、状态流转、权限矩阵、幂等和并发），断言清单（状态码、响应结构和字段类型、业务字段、数据库副作用、响应时间、错误码和提示），pytest + httpx 自动化模板（fixture 管理客户端和鉴权、参数化用例、环境变量读取 Token、测试数据准备与清理），常见鉴权方式的处理，缺陷报告格式（标题、环境、请求、预期、实际、复现步骤、严重程度）。补充业务用例、编写自动化接口测试、提交缺陷时使用。"
metadata:
  octop:
    emoji: "📋"
    label:
      zh: "用例设计与自动化"
      en: "API Test Design"
    summary:
      zh: "用例设计方法、断言清单和 pytest 模板。"
      en: "Test design methods, assertions and pytest templates."
---

# 接口测试设计

## 1. 用例设计方法

| 方法 | 例子（创建订单接口） |
|------|----------------------|
| 等价类 | 数量为正整数（有效）、0、负数、小数、字符串（无效） |
| 边界值 | 数量 1、最大值、最大值 + 1；字符串长度 0、上限、上限 + 1 |
| 错误推测 | 重复提交、超大请求体、特殊字符和表情、SQL / 脚本片段（只验证被正确拒绝或转义） |
| 状态流转 | 已支付的订单不能再取消；已取消的不能支付 |
| 权限矩阵 | 未登录 401；普通用户访问别人的订单 403 / 404；管理员可访问 |
| 幂等 | 同一个幂等键重复请求只生效一次；PUT 重复执行结果一致 |

## 2. 断言清单

1. 状态码；
2. 响应结构：必有字段、字段类型、枚举值；
3. 业务结果：金额、状态、数量正确；
4. 副作用：数据库或后续查询接口能看到变化（只在测试环境验证）；
5. 错误响应：错误码和提示信息符合约定，不泄露堆栈和内部信息；
6. 响应时间：设定合理上限（如 1 秒），超出记录为性能问题。

## 3. pytest + httpx 模板（保存到 `outputs/api/tests/test_books.py`）

```python
import os

import httpx
import pytest

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")


@pytest.fixture(scope="session")
def client():
    token = os.environ["API_TOKEN"]  # 不要把 Token 写进代码
    with httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {token}"}, timeout=10) as c:
        yield c


def test_list_books(client):
    r = client.get("/books", params={"page": 1})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)


@pytest.mark.parametrize("payload, status", [
    ({"title": "三体", "price": 23.5}, 201),
    ({"title": "三体"}, 422),            # 缺少必填字段 price
    ({"title": "", "price": -1}, 422),   # 边界值
])
def test_create_book(client, payload, status):
    r = client.post("/books", json=payload)
    assert r.status_code == status


def test_requires_auth():
    r = httpx.get(f"{BASE}/books")
    assert r.status_code == 401
```

运行：`API_TOKEN=xxx pytest outputs/api/tests -q`（Windows PowerShell：`$env:API_TOKEN="xxx"; pytest …`）。创建的数据用统一前缀（如 `autotest_`），在 fixture 结束时清理。

## 4. 缺陷报告格式

```markdown
**标题**：[订单] 数量为 0 时仍能创建订单
**环境**：测试环境 http://…，版本 v1.2.3
**请求**：POST /orders  {"product_id": 1, "qty": 0}
**预期**：422，提示数量必须大于 0
**实际**：201，生成了金额为 0 的订单
**复现步骤**：1. … 2. …
**严重程度**：一般（数据错误，可绕过）
```
