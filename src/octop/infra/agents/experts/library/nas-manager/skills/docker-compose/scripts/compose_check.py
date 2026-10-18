#!/usr/bin/env python3
"""docker-compose 体检：找出 NAS 上常见的安全、稳定性和可维护性问题。只读，不修改文件、不启动容器。

Usage:
    python scripts/compose_check.py docker-compose.yml [更多 compose 文件 ...] [--check-paths] [--json]

检查项（等级：错误 / 警告 / 建议）：
  错误：同一宿主机端口被多个服务占用、container_name 重复、YAML 无法解析；
  警告：挂载 docker.sock、privileged: true、数据库/管理端口（3306、5432、6379、27017、2375、22 等）对所有地址开放、
        环境变量里直接写密码/令牌、没有设置重启策略、镜像用 latest 或不写标签；
  建议：没有健康检查、没有设置时区 TZ、linuxserver 等镜像未设置 PUID/PGID、相对路径挂载、network_mode: host、
        --check-paths 时宿主机挂载目录不存在。
Exit codes: 0 无错误和警告, 3 有错误或警告, 1 输入错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - environment check
    print("缺少依赖 PyYAML：请运行 `pip install pyyaml`", file=sys.stderr)
    sys.exit(2)

SENSITIVE_PORTS = {22: "SSH", 23: "Telnet", 2375: "Docker API（无加密）", 2376: "Docker API", 3306: "MySQL", 5432: "PostgreSQL",
                   6379: "Redis", 27017: "MongoDB", 9200: "Elasticsearch", 11211: "Memcached", 5900: "VNC", 3389: "RDP"}  # fmt: skip
SECRET_KEY = re.compile(
    r"(PASSWORD|PASSWD|PWD|SECRET|TOKEN|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY)$", re.I
)
PUID_IMAGES = re.compile(r"linuxserver/|lscr\.io/|hotio/")


class ComposeError(ValueError):
    pass


def _env(service: dict[str, Any]) -> dict[str, str]:
    env = service.get("environment") or {}
    if isinstance(env, list):
        out = {}
        for item in env:
            k, _, v = str(item).partition("=")
            out[k] = v
        return out
    return {str(k): "" if v is None else str(v) for k, v in env.items()}


def _ports(service: dict[str, Any]) -> list[tuple[str, int, str]]:
    """(host_ip, host_port, raw) for published ports; container-only ports are ignored."""
    out = []
    for p in service.get("ports") or []:
        if isinstance(p, dict):
            if p.get("published"):
                for hp in _expand(str(p["published"])):
                    out.append((str(p.get("host_ip", "")), hp, json.dumps(p, ensure_ascii=False)))
            continue
        raw = str(p).split("/")[0]
        parts = raw.rsplit(":", 2) if raw.count(":") >= 2 else raw.split(":")
        if len(parts) == 3:
            ip, host, _c = parts
        elif len(parts) == 2:
            ip, (host, _c) = "", parts
        else:
            continue
        for hp in _expand(host):
            out.append((ip.strip("[]"), hp, str(p)))
    return out


def _expand(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1)) if a.isdigit() and b.isdigit() else []
    return [int(spec)] if spec.isdigit() else []


def _volumes(service: dict[str, Any]) -> list[tuple[str, str]]:
    out = []
    for v in service.get("volumes") or []:
        if isinstance(v, dict):
            out.append((str(v.get("source", "")), str(v.get("target", ""))))
        else:
            parts = str(v).split(":")
            if len(parts) >= 2:
                out.append((parts[0], parts[1]))
    return out


def check(files: list[Path], check_paths: bool) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    def add(level: str, svc: str, msg: str) -> None:
        issues.append({"等级": level, "服务": svc, "问题": msg})

    by_port: dict[int, list[tuple[str, str]]] = defaultdict(list)
    names: dict[str, list[str]] = defaultdict(list)
    for f in files:
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            add(
                "错误",
                f.name,
                f"YAML 无法解析：{str(exc).splitlines()[0]}（检查缩进和冒号后的空格）",
            )
            continue
        services = (doc or {}).get("services")
        if not isinstance(services, dict) or not services:
            add("错误", f.name, "没有找到 services")
            continue
        for name, svc in services.items():
            svc = svc or {}
            image = str(svc.get("image", ""))
            if svc.get("container_name"):
                names[str(svc["container_name"])].append(name)
            if image and "@sha256:" not in image:
                tag = image.rsplit("/", 1)[-1].partition(":")[2]
                if not tag:
                    add(
                        "警告",
                        name,
                        f"镜像「{image}」没有写版本标签，默认是 latest，更新后可能不兼容；建议固定版本号",
                    )
                elif tag == "latest":
                    add(
                        "警告",
                        name,
                        f"镜像「{image}」使用 latest，重建容器时可能意外升级；建议固定版本号",
                    )
            if not svc.get("restart") and not (svc.get("deploy") or {}).get("restart_policy"):
                add(
                    "警告",
                    name,
                    "没有设置重启策略，NAS 重启后不会自动启动；建议 restart: unless-stopped",
                )
            if svc.get("privileged"):
                add(
                    "警告",
                    name,
                    "privileged: true 给了容器几乎全部宿主机权限，确认确实需要（如硬件直通），否则删除",
                )
            for src, _dst in _volumes(svc):
                if "docker.sock" in src:
                    add(
                        "警告",
                        name,
                        f"挂载了 {src}：容器可以控制宿主机上所有容器，等同 root 权限；仅给可信的管理工具，并尽量加 :ro",
                    )
                elif src.startswith((".", "~")) or (src and not src.startswith("/") and "/" in src):
                    add(
                        "建议",
                        name,
                        f"相对路径挂载「{src}」依赖执行目录，换目录启动会挂错位置；NAS 上建议用绝对路径",
                    )
                elif check_paths and src.startswith("/") and not Path(src).exists():
                    add(
                        "建议",
                        name,
                        f"宿主机目录 {src} 不存在，启动时会被自动创建为 root 所有的空目录",
                    )
            for ip, port, raw in _ports(svc):
                by_port[port].append((ip or "0.0.0.0", name))
                if port in SENSITIVE_PORTS and ip in ("", "0.0.0.0", "::"):
                    add(
                        "警告",
                        name,
                        f"端口 {raw} 把 {SENSITIVE_PORTS[port]} 暴露在所有网卡上；只给本机用时改成 127.0.0.1:{port}:…，不要在路由器上转发",
                    )
            env = _env(svc)
            for k, v in env.items():
                if (
                    SECRET_KEY.search(k)
                    and v
                    and not v.startswith("${")
                    and not k.endswith("_FILE")
                ):
                    add(
                        "警告",
                        name,
                        f"环境变量 {k} 直接写了明文值；建议放到 .env 文件并用 ${{{k}}} 引用，.env 不要上传到公开仓库",
                    )
            if not svc.get("healthcheck"):
                add("建议", name, "没有健康检查（healthcheck），容器卡死时不会被发现")
            if "TZ" not in env and not any("localtime" in s for s, _ in _volumes(svc)):
                add(
                    "建议",
                    name,
                    "没有设置时区，日志和计划任务时间可能差 8 小时；建议 TZ=Asia/Shanghai",
                )
            if PUID_IMAGES.search(image) and not {"PUID", "PGID"} <= set(env):
                add("建议", name, "该镜像支持 PUID/PGID，设置为 NAS 用户的 id 可以避免文件权限问题")
            if svc.get("network_mode") == "host":
                add(
                    "建议",
                    name,
                    "network_mode: host 会占用宿主机端口且绕过端口映射，确认没有端口冲突",
                )
    wild = ("0.0.0.0", "::")
    for port, owners in sorted(by_port.items()):
        clash = {s for i, (ip1, s) in enumerate(owners) for ip2, s2 in owners[i + 1 :]
                 if s != s2 and (ip1 == ip2 or ip1 in wild or ip2 in wild) for s in (s, s2)}  # fmt: skip
        if clash:
            add(
                "错误",
                "、".join(sorted(clash)),
                f"宿主机端口 {port} 被多个服务占用，只有一个能启动",
            )
    for cname, svcs in names.items():
        if len(svcs) > 1:
            add("错误", "、".join(svcs), f"container_name「{cname}」重复")
    order = {"错误": 0, "警告": 1, "建议": 2}
    return sorted(issues, key=lambda i: (order[i["等级"]], i["服务"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("files", nargs="+")
    parser.add_argument("--check-paths", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    files = [Path(f) for f in args.files]
    missing = [str(f) for f in files if not f.is_file()]
    if missing:
        print(f"失败：找不到 {'、'.join(missing)}", file=sys.stderr)
        return 1
    issues = check(files, args.check_paths)
    if args.json:
        print(json.dumps(issues, ensure_ascii=False, indent=2))
    else:
        counts = {lv: sum(1 for i in issues if i["等级"] == lv) for lv in ("错误", "警告", "建议")}
        print(
            f"检查 {len(files)} 个文件：错误 {counts['错误']}，警告 {counts['警告']}，建议 {counts['建议']}"
        )
        for i in issues:
            print(f"- [{i['等级']}] {i['服务']}：{i['问题']}")
        print(
            "本工具只读检查，修改 compose 文件前请先备份，改完用 `docker compose config` 校验后再重建容器。"
        )
    return 3 if any(i["等级"] in ("错误", "警告") for i in issues) else 0


if __name__ == "__main__":
    sys.exit(main())
