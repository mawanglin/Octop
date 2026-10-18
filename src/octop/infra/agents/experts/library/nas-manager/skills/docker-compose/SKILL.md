---
name: docker-compose
description: "docker-compose 体检与修改建议：compose_check.py 只读检查一个或多个 compose 文件，找出宿主机端口冲突、container_name 重复、YAML 错误（错误），docker.sock 挂载、privileged、数据库和管理端口对所有地址开放、环境变量明文密码、没有重启策略、镜像 latest 或无标签（警告），没有健康检查、没有时区、linuxserver 镜像缺 PUID/PGID、相对路径挂载、host 网络、宿主机目录不存在（建议）；附常见服务的推荐写法和安全修改流程。用户发来 compose 文件、容器起不来或想检查安全性时使用。"
metadata:
  octop:
    emoji: "🐳"
    label:
      zh: "Compose 体检"
      en: "Compose Check"
    summary:
      zh: "检查容器配置的冲突、权限和明文密码。"
      en: "Find port clashes, risky privileges and plaintext secrets."
---

# docker-compose 体检

> `scripts/` 和 `references/` 路径相对于本技能目录；示例（故意包含常见问题）：`references/example-compose.yml`。

## 1. 运行

```bash
python scripts/compose_check.py inbound/docker-compose.yml [其他项目的 compose 文件 ...] [--check-paths]
```

多个项目的 compose 文件一起检查时，可以发现跨项目的端口冲突。`--check-paths` 在 NAS 本机运行时检查宿主机挂载目录是否存在。

## 2. 常见修改

```yaml
services:
  app:
    image: lscr.io/linuxserver/qbittorrent:5.0.3   # 固定版本，升级时手动改
    restart: unless-stopped
    environment:
      - TZ=Asia/Shanghai
      - PUID=1000                                  # NAS 用户 id：SSH 后运行 id 用户名
      - PGID=1000
    ports:
      - "127.0.0.1:3306:3306"                      # 只给本机访问的端口绑定 127.0.0.1
    env_file: .env                                 # 密码放 .env：MYSQL_ROOT_PASSWORD=...
    volumes:
      - /vol1/docker/app/config:/config           # 绝对路径
```

- 明文密码 → `.env` 文件 + `${变量名}` 引用；`.env` 权限设为仅自己可读，不要上传到公开仓库。
- 端口冲突 → 改左边的宿主机端口（如 `8081:8080`），容器内端口不变。
- docker.sock → 只给 Portainer、Watchtower 等可信管理工具，能用 `:ro` 就加。
- privileged → 只有硬件直通（如核显转码）等场景需要，优先用 `devices: - /dev/dri:/dev/dri`。

## 3. 安全修改流程

1. 备份原文件：`cp docker-compose.yml docker-compose.yml.bak`
2. 修改后校验：`docker compose config`（能正常输出即语法正确）
3. 重建：`docker compose up -d`（数据在挂载目录中不会丢失；不要加 `-v` 删除卷）
4. 观察：`docker compose ps`、`docker compose logs -f 服务名`
