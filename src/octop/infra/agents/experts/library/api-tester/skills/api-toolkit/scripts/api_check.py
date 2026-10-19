#!/usr/bin/env python3
"""接口测试工具：解析 OpenAPI / Swagger 文档、生成测试用例表、只读冒烟测试、curl 转 Python 代码。

Usage:
    python scripts/api_check.py list openapi.yaml|json|URL
    python scripts/api_check.py cases openapi.yaml -o 测试用例.xlsx
    python scripts/api_check.py smoke openapi.yaml --base http://127.0.0.1:8000 [--header "Authorization: Bearer xxx"] [-o 冒烟报告.xlsx]
    python scripts/api_check.py curl2py "curl -X POST https://api.example.com/v1/items -H 'Content-Type: application/json' -d '{\"a\":1}'"

list：方法、路径、摘要、参数（路径 / 查询 / 请求头）、请求体、响应码、是否需要鉴权；支持 OpenAPI 3.x 和 Swagger 2.0。
cases：每个接口生成 正常请求 / 缺少必填参数 / 参数类型错误 / 未鉴权（需要鉴权时）等用例，写明预期状态码。
smoke：只发 GET 请求（不会修改数据）。路径参数用文档里的 example / default，没有示例的接口跳过；
       记录状态码、耗时、返回类型，状态码不在文档声明的响应里或 ≥ 500 时判为失败。
curl2py：把 curl 命令（-X -H -d --data-raw --json -u -F -k）转成 httpx 代码。
Exit codes: 0 ok, 1 输入错误, 3 冒烟测试有失败。
"""

from __future__ import annotations

import argparse
import json
import pprint
import shlex
import sys
import time
from pathlib import Path
from typing import Any

METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


class ApiError(ValueError):
    pass


def load_spec(source: str) -> dict[str, Any]:
    if source.startswith(("http://", "https://")):
        import httpx

        resp = httpx.get(source, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        text = resp.text
    else:
        text = Path(source).read_text(encoding="utf-8")
    try:
        spec = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError:  # pragma: no cover - environment check
            raise ApiError("读取 YAML 需要 PyYAML：pip install pyyaml") from None
        spec = yaml.safe_load(text)
    if not isinstance(spec, dict) or "paths" not in spec:
        raise ApiError("不是 OpenAPI / Swagger 文档（缺少 paths）")
    return spec


def resolve(spec: dict[str, Any], obj: Any, depth: int = 0) -> Any:
    if isinstance(obj, dict) and "$ref" in obj and depth < 20:
        node: Any = spec
        for part in obj["$ref"].lstrip("#/").split("/"):
            node = node.get(part, {}) if isinstance(node, dict) else {}
        return resolve(spec, node, depth + 1)
    return obj


def operations(spec: dict[str, Any]) -> list[dict[str, Any]]:
    ops = []
    global_sec = bool(spec.get("security"))
    for path, item in spec["paths"].items():
        common = item.get("parameters", [])
        for method in METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            params = [resolve(spec, p) for p in [*common, *op.get("parameters", [])]]
            body = resolve(spec, op.get("requestBody", {}))
            body_params = [p for p in params if p.get("in") == "body"]  # Swagger 2.0
            schema = None
            if body:
                content = body.get("content", {})
                media = content.get("application/json") or next(iter(content.values()), {})
                schema = resolve(spec, media.get("schema", {}))
            elif body_params:
                schema = resolve(spec, body_params[0].get("schema", {}))
            ops.append({
                "method": method.upper(), "path": path, "summary": op.get("summary") or op.get("operationId") or "",
                "params": [p for p in params if p.get("in") != "body"],
                "body": schema, "body_required": bool(body.get("required")) or any(p.get("required") for p in body_params),
                "responses": sorted(str(k) for k in op.get("responses", {})),
                "auth": bool(op.get("security", spec.get("security"))) if "security" in op else global_sec,
                "tags": op.get("tags", []),
            })  # fmt: skip
    return ops


def example_for(spec: dict[str, Any], schema: dict[str, Any] | None, depth: int = 0) -> Any:
    s = resolve(spec, schema or {})
    if not s or depth > 4:
        return None
    for key in ("example", "default"):
        if key in s:
            return s[key]
    if s.get("enum"):
        return s["enum"][0]
    t = s.get("type")
    if t == "object" or "properties" in s:
        req = set(s.get("required", []))
        props = s.get("properties", {})
        keys = [k for k in props if k in req] or list(props)[:3]
        return {k: example_for(spec, props[k], depth + 1) for k in keys}
    if t == "array":
        return [example_for(spec, s.get("items"), depth + 1)]
    return {"integer": 1, "number": 1.0, "boolean": True, "string": "example"}.get(
        str(t), "example"
    )


def param_example(spec: dict[str, Any], p: dict[str, Any]) -> Any:
    if "example" in p:
        return p["example"]
    schema = resolve(
        spec, p.get("schema") or {k: v for k, v in p.items() if k in ("type", "enum", "default")}
    )
    for key in ("example", "default"):
        if key in schema:
            return schema[key]
    if schema.get("enum"):
        return schema["enum"][0]
    return None


def cmd_list(spec: dict[str, Any]) -> int:
    ops = operations(spec)
    title = spec.get("info", {}).get("title", "")
    print(f"{title} {spec.get('info', {}).get('version', '')}：{len(ops)} 个接口")
    print(
        "| 方法 | 路径 | 说明 | 参数 | 请求体 | 响应 | 鉴权 |\n|------|------|------|------|--------|------|------|"
    )
    for o in ops:
        params = (
            "、".join(
                f"{p.get('name')}({p.get('in')}{'*' if p.get('required') else ''})"
                for p in o["params"]
            )
            or "-"
        )
        body = "有" + ("（必填）" if o["body_required"] else "") if o["body"] else "-"
        print(
            f"| {o['method']} | {o['path']} | {o['summary']} | {params} | {body} | {','.join(o['responses'])} | {'是' if o['auth'] else '否'} |"
        )
    no_resp = [f"{o['method']} {o['path']}" for o in ops if not o["responses"]]
    if no_resp:
        print("没有声明响应的接口：" + "、".join(no_resp))
    return 0


def build_cases(spec: dict[str, Any]) -> list[list[str]]:
    rows = []
    for o in operations(spec):
        ok = next((c for c in o["responses"] if c.startswith("2")), "200")
        name = f"{o['method']} {o['path']}"
        req = [p for p in o["params"] if p.get("required")]
        body = example_for(spec, o["body"]) if o["body"] else None
        rows.append(
            [
                name,
                "正常请求",
                "必填参数和请求体使用合法值",
                json.dumps(body, ensure_ascii=False) if body is not None else "",
                ok,
            ]
        )
        for p in req:
            rows.append(
                [
                    name,
                    f"缺少必填参数 {p.get('name')}",
                    f"去掉 {p.get('in')} 参数 {p.get('name')}",
                    "",
                    "400 或 422",
                ]
            )
            t = resolve(spec, p.get("schema", {})).get("type", p.get("type"))
            if t in ("integer", "number", "boolean"):
                rows.append(
                    [
                        name,
                        f"参数 {p.get('name')} 类型错误",
                        f"{p.get('name')} 传字符串 'abc'",
                        "",
                        "400 或 422",
                    ]
                )
        if o["body"] and o["body_required"]:
            rows.append([name, "缺少请求体", "不传请求体", "", "400 或 422"])
            req_fields = resolve(spec, o["body"]).get("required", [])
            if req_fields:
                rows.append(
                    [
                        name,
                        f"请求体缺少必填字段 {req_fields[0]}",
                        f"去掉字段 {req_fields[0]}",
                        "",
                        "400 或 422",
                    ]
                )
        if o["auth"]:
            rows.append([name, "未鉴权", "不带鉴权头 / Token", "", "401"])
            rows.append([name, "鉴权无效", "使用过期或错误的 Token", "", "401 或 403"])
        if any(p.get("in") == "path" for p in o["params"]):
            rows.append([name, "资源不存在", "路径参数使用不存在的 id", "", "404"])
    return rows


def cmd_cases(spec: dict[str, Any], out: Path) -> int:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:  # pragma: no cover - environment check
        print("缺少依赖 openpyxl：请运行 `pip install openpyxl`", file=sys.stderr)
        return 2
    rows = build_cases(spec)
    wb = Workbook()
    ws = wb.active
    ws.title = "测试用例"
    ws.append(
        ["编号", "接口", "用例", "步骤 / 输入", "请求体示例", "预期状态码", "实际结果", "是否通过"]
    )
    for i, r in enumerate(rows, start=1):
        ws.append([f"TC{i:03d}", r[0], r[1], r[2], r[3], r[4], "", ""])
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="0E7490")
    for col, w in zip("ABCDEFGH", (8, 30, 24, 30, 40, 12, 16, 10), strict=True):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "C2"
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    print(f"已生成 {out}：{len(operations(spec))} 个接口，{len(rows)} 条用例")
    return 0


def cmd_smoke(
    spec: dict[str, Any], base: str, headers: list[str], out: Path | None, timeout: float
) -> int:
    import httpx

    hdrs = {}
    for h in headers:
        k, _, v = h.partition(":")
        hdrs[k.strip()] = v.strip()
    results = []
    with httpx.Client(
        base_url=base.rstrip("/"), headers=hdrs, timeout=timeout, follow_redirects=False
    ) as client:
        for o in operations(spec):
            if o["method"] != "GET":
                continue
            path, query, skip = o["path"], {}, ""
            for p in o["params"]:
                val = param_example(spec, p)
                if p.get("in") == "path":
                    if val is None:
                        skip = f"路径参数 {p.get('name')} 没有示例值"
                        break
                    path = path.replace("{" + str(p.get("name")) + "}", str(val))
                elif p.get("in") == "query" and (p.get("required") or val is not None):
                    if val is None:
                        skip = f"必填查询参数 {p.get('name')} 没有示例值"
                        break
                    query[p["name"]] = val
            if skip:
                results.append(["GET", o["path"], "跳过", "", "", skip])
                continue
            t0 = time.perf_counter()
            try:
                resp = client.get(path, params=query)
            except httpx.HTTPError as exc:
                results.append(
                    [
                        "GET",
                        o["path"],
                        "失败",
                        "",
                        "",
                        f"请求出错：{type(exc).__name__} {exc}"[:120],
                    ]
                )
                continue
            ms = round((time.perf_counter() - t0) * 1000)
            code = str(resp.status_code)
            declared = o["responses"]
            if resp.status_code in (401, 403):
                # Rejected by auth: the endpoint itself was not exercised.
                results.append(
                    [
                        "GET",
                        o["path"],
                        "未通过鉴权",
                        code,
                        ms,
                        "用 --header 'Authorization: Bearer …' 提供鉴权后重测",
                    ]
                )
                continue
            ok = resp.status_code < 500 and (
                not declared
                or code in declared
                or f"{code[0]}XX" in declared
                or "default" in declared
            )
            note = (
                ""
                if ok
                else (
                    "服务端错误"
                    if resp.status_code >= 500
                    else f"状态码不在文档声明的 {','.join(declared)} 中"
                )
            )
            results.append(
                [
                    "GET",
                    o["path"],
                    "通过" if ok else "失败",
                    code,
                    ms,
                    note or resp.headers.get("content-type", ""),
                ]
            )
    passed = sum(1 for r in results if r[2] == "通过")
    failed = [r for r in results if r[2] == "失败"]
    skipped = sum(1 for r in results if r[2] == "跳过")
    unauth = sum(1 for r in results if r[2] == "未通过鉴权")
    print(
        f"冒烟测试 {base}：通过 {passed}，失败 {len(failed)}，未通过鉴权 {unauth}，跳过 {skipped}（只测试 GET 接口）"
    )
    for r in results:
        print(
            f"- [{r[2]}] {r[0]} {r[1]} {r[3]} {f'{r[4]}ms' if r[4] != '' else ''} {r[5]}".rstrip()
        )
    if out:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "冒烟测试"
        ws.append(["方法", "路径", "结果", "状态码", "耗时(ms)", "说明"])
        for r in results:
            ws.append(r)
        out.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(out))
        print(f"已生成 {out}")
    return 3 if failed else 0


def curl_to_python(cmd: str) -> str:
    tokens = shlex.split(cmd.replace("\\\n", " "))
    if not tokens or tokens[0] != "curl":
        raise ApiError("请传入以 curl 开头的命令")
    method, url, headers, data, auth, files, verify, json_body = (
        None,
        "",
        {},
        None,
        None,
        [],
        True,
        None,
    )
    i = 1
    while i < len(tokens):
        t = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if t in ("-X", "--request"):
            method, i = nxt.upper(), i + 1
        elif t in ("-H", "--header"):
            k, _, v = nxt.partition(":")
            headers[k.strip()] = v.strip()
            i += 1
        elif t in ("-d", "--data", "--data-raw", "--data-binary", "--data-urlencode"):
            data, i = nxt, i + 1
        elif t == "--json":
            json_body, i = nxt, i + 1
        elif t in ("-u", "--user"):
            auth, i = nxt, i + 1
        elif t in ("-F", "--form"):
            files.append(nxt)
            i += 1
        elif t in ("-k", "--insecure"):
            verify = False
        elif t in ("--url",):
            url, i = nxt, i + 1
        elif not t.startswith("-"):
            url = t
        i += 1
    if not url:
        raise ApiError("curl 命令里没有 URL")
    if (
        json_body is None
        and data is not None
        and "json" in headers.get("Content-Type", headers.get("content-type", "")).lower()
    ):
        json_body = data
        data = None
    method = method or ("POST" if data is not None or json_body is not None or files else "GET")
    lines = ["import httpx", ""]
    args = [repr(method), repr(url)]
    if headers:
        hdrs = {
            k: v
            for k, v in headers.items()
            if not (json_body is not None and k.lower() == "content-type")
        }
        if hdrs:
            lines.append(f"headers = {json.dumps(hdrs, ensure_ascii=False, indent=4)}")
            args.append("headers=headers")
    if json_body is not None:
        try:
            parsed = json.loads(json_body)
            lines.append(f"payload = {pprint.pformat(parsed, sort_dicts=False)}")
        except json.JSONDecodeError:
            lines.append(f"payload = {json_body!r}  # 不是合法 JSON，请检查")
        args.append("json=payload")
    elif data is not None:
        args.append(f"content={data!r}")
    if files:
        form = {}
        for f in files:
            k, _, v = f.partition("=")
            form[k] = v
        lines.append(
            f"form = {form!r}  # 以 @ 开头的值是文件路径，需改成 files={{'字段': open('路径', 'rb')}}"
        )
        args.append("data=form")
    if auth:
        user, _, pwd = auth.partition(":")
        args.append(f"auth=({user!r}, {pwd!r})")
    client_args = "" if verify else "verify=False"
    lines += ["", f"with httpx.Client({client_args}) as client:", f"    resp = client.request({', '.join(args)})",
              "    print(resp.status_code)", "    print(resp.text[:2000])"]  # fmt: skip
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    lst = sub.add_parser("list")
    lst.add_argument("spec")
    c = sub.add_parser("cases")
    c.add_argument("spec")
    c.add_argument("-o", "--output", required=True)
    s = sub.add_parser("smoke")
    s.add_argument("spec")
    s.add_argument("--base", required=True)
    s.add_argument("--header", action="append", default=[])
    s.add_argument("--timeout", type=float, default=15)
    s.add_argument("-o", "--output")
    cp = sub.add_parser("curl2py")
    cp.add_argument("command")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "curl2py":
            print(curl_to_python(args.command), end="")
            return 0
        spec = load_spec(args.spec)
        if args.cmd == "list":
            return cmd_list(spec)
        if args.cmd == "cases":
            return cmd_cases(spec, Path(args.output))
        return cmd_smoke(
            spec, args.base, args.header, Path(args.output) if args.output else None, args.timeout
        )
    except (OSError, ApiError, ValueError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
