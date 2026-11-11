#!/usr/bin/env bash
# Gitea runner 上装构建工具（fork 自用）。runner 容器里 Node 版的 Action（setup-uv、setup-node）
# 下载时 TLS 握手失败（ALPN），curl 正常，所以用 curl 直接装，并写入 $GITHUB_PATH。
#   gitea_tools.sh uv              装 uv，并用它装 Python 3.12
#   gitea_tools.sh node <主版本>    装该主版本的最新 Node（20 / 24），并打开 corepack
set -euo pipefail

add_path() { if [ -n "${GITHUB_PATH:-}" ]; then echo "$1" >> "$GITHUB_PATH"; fi; export PATH="$1:$PATH"; }

case "${1:-}" in
  uv)
    # 先用 PyPI（比 GitHub 稳），失败再退回官方安装脚本；两者都重试。
    ok=
    for i in 1 2 3 4 5; do
      if python3 -m pip install --quiet --user uv; then ok=1; break; fi
      sleep 5
    done
    if [ -z "$ok" ]; then
      for i in 1 2 3 4 5; do
        if curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh; then ok=1; break; fi
        sleep 10
      done
    fi
    [ -n "$ok" ] || { echo "uv 安装失败" >&2; exit 1; }
    add_path "$HOME/.local/bin"
    uv --version
    for i in 1 2 3 4 5; do uv python install 3.12 && break; echo "uv python install 重试（$i/5）"; sleep 10; done
    uv python find 3.12
    ;;
  node)
    major="${2:?node 主版本}"
    base="https://nodejs.org/dist/latest-v${major}.x"
    file="$(curl -fsSL --retry 5 "$base/SHASUMS256.txt" | awk '/linux-x64\.tar\.xz$/ {print $2; exit}')"
    [ -n "$file" ] || { echo "找不到 Node ${major} 的 linux-x64 安装包" >&2; exit 1; }
    dest="/opt/node-${major}"
    sudo -n true 2>/dev/null && SUDO=sudo || SUDO=
    $SUDO mkdir -p "$dest"
    curl -fsSL --retry 5 --retry-all-errors "$base/$file" | $SUDO tar -xJ -C "$dest" --strip-components=1
    add_path "$dest/bin"
    node --version
    corepack enable 2>/dev/null || $SUDO "$dest/bin/corepack" enable
    ;;
  *)
    echo "用法：$0 uv | node <主版本>" >&2
    exit 2
    ;;
esac
