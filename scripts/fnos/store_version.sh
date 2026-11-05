#!/usr/bin/env bash
# 飞牛商店版本映射。规则见 fnos/README.md「版本号映射」。
#   1.0.2b8 → 1.0.208
#   1.0.2   → 1.0.300

fnos_store_version() {
  local ver="${1:-}"
  local major minor patch num store_patch
  # Fork 版本 <官方版本>.postM（M 为 1–99）：在官方编码的 patch 后追加两位，
  #   1.0.2b9.post10 → 1.0.20910，1.0.2.post1 → 1.0.30001，1.0.3b1.post1 → 1.0.30101。
  # 早期 post1–post9 按一位编码发布过（1.0.2091…1.0.2099），两位编码的值总是更大，已装旧包的机器仍能升级。
  # fork 版本之间单调递增；编码值高于同代官方包，装了 fork 包后商店不会提示换回官方包。
  if [[ "$ver" =~ ^(.+)\.post([0-9]+)$ ]]; then
    local base="${BASH_REMATCH[1]}" post=$((10#${BASH_REMATCH[2]})) base_store
    if [ "$post" -lt 1 ] || [ "$post" -gt 99 ]; then
      echo "飞牛商店版本无法编码 post 序号（只支持 1–99）: $ver" >&2
      return 1
    fi
    base_store="$(fnos_store_version "$base")" || return 1
    printf '%s%02d\n' "$base_store" "$post"
    return 0
  fi
  if [[ "$ver" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)b([0-9]+)$ ]]; then
    major="${BASH_REMATCH[1]}"
    minor="${BASH_REMATCH[2]}"
    patch="${BASH_REMATCH[3]}"
    num=$((10#${BASH_REMATCH[4]}))
    if [ "$num" -lt 1 ] || [ "$num" -gt 99 ]; then
      echo "飞牛商店版本无法编码 beta 序号: $ver" >&2
      return 1
    fi
    store_patch=$((patch * 100 + num))
  elif [[ "$ver" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    major="${BASH_REMATCH[1]}"
    minor="${BASH_REMATCH[2]}"
    patch="${BASH_REMATCH[3]}"
    store_patch=$((patch * 100 + 100))
  else
    echo "飞牛商店版本只接受 X.Y.Z 或 X.Y.ZbN，收到: $ver" >&2
    return 1
  fi
  printf '%s\n' "${major}.${minor}.${store_patch}"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  fnos_store_version "${1:-}"
fi
