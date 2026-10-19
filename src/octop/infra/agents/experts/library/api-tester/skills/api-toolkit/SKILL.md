---
name: api-toolkit
description: "接口测试工具：api_check.py list 解析 OpenAPI 3.x / Swagger 2.0（文件或 URL，JSON / YAML，支持 $ref）列出方法、路径、说明、参数、请求体、响应码和是否需要鉴权；cases 为每个接口生成正常请求、缺少必填参数、参数类型错误、缺少请求体或必填字段、未鉴权、鉴权无效、资源不存在等用例并导出 Excel；smoke 只对 GET 接口发请求（路径参数取文档的 example / default，没有示例的跳过），记录状态码和耗时，区分通过、失败、未通过鉴权、跳过；curl2py 把 curl 命令（-X -H -d --json -u -F -k）转成 httpx 代码。拿到接口文档、要做冒烟测试或把 curl 转成代码时使用。"
metadata:
  octop:
    emoji: "🧪"
    label:
      zh: "接口测试工具"
      en: "API Toolkit"
    summary:
      zh: "接口清单、用例表、只读冒烟测试和 curl 转代码。"
      en: "Endpoint lists, test cases, read-only smoke tests, curl to code."
---

# 接口测试工具

> `scripts/` 和 `references/` 路径相对于本技能目录；示例文档：`references/example-openapi.yaml`。

## 1. 接口清单

```bash
python scripts/api_check.py list references/example-openapi.yaml
python scripts/api_check.py list http://测试环境/openapi.json
```

参数后的 `*` 表示必填；"鉴权"一列综合了全局和接口级的 security 设置。FastAPI 默认文档地址是 `/openapi.json`，Spring 常见是 `/v3/api-docs`。

## 2. 测试用例表

```bash
python scripts/api_check.py cases references/example-openapi.yaml -o outputs/api/测试用例.xlsx
```

每个接口生成：正常请求（附请求体示例）、缺少必填参数、数字 / 布尔参数传字符串、缺少请求体或必填字段、未鉴权、鉴权无效、路径参数不存在。表中留有"实际结果""是否通过"两列供执行时填写。业务用例按 `api-test-design` 补充。

## 3. 冒烟测试（只读）

```bash
python scripts/api_check.py smoke references/example-openapi.yaml --base http://127.0.0.1:8000 --header "Authorization: Bearer $TOKEN" -o outputs/api/冒烟报告.xlsx
```

- 只发 GET；路径参数和必填查询参数使用文档中的 example / default，没有就跳过并说明原因——给文档补上 example 即可覆盖更多接口；
- 结果：通过（状态码 < 500 且在文档声明中）、失败（5xx 或未声明的状态码）、未通过鉴权（401 / 403，提示加 `--header`）、跳过；
- 有失败时退出码为 3。Token 从环境变量传入，不要写进文件。

## 4. curl 转代码

```bash
python scripts/api_check.py curl2py "curl -X POST https://api.example.com/v1/items -H 'Content-Type: application/json' -d '{\"name\":\"a\"}'"
```

生成 httpx 代码：JSON 请求体转成 Python 字典，`-k` 转成 `verify=False`（只用于测试环境），`-u` 转成 `auth=(…)`，`-F` 表单会提示改成文件上传写法。
