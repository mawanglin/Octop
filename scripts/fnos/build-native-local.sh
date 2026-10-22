#!/usr/bin/env bash
# =============================================================================
# Fork 专用：在本机构建飞牛原生版（x86_64）FPK，不经过 GitHub Actions。
#
# 步骤与 .github/workflows/fork-release.yml 的 fnos-site-packages / fnos-pack
# 两个 job 一致：
#   1. make build：构建前端和 wheel（--skip-build 时复用 dist/ 里当前版本的 wheel）
#   2. 用 Python 3.12 把 wheel 及依赖装进 fnos/native/app/site-packages，
#      固定 mcp / langchain-mcp-adapters 版本、补 vendor 文件、精简、导入自检
#   3. bash scripts/build-fpk.sh native（首次运行会下载 fnpack 到 .verify/）
#   4. 默认删除 site-packages（--keep-site-packages 保留，便于排查）
#
# 用法（仓库根目录）：
#   bash scripts/fnos/build-native-local.sh
#   bash scripts/fnos/build-native-local.sh --skip-build
# 产物：dist/Octop-fnos-native-<版本>.fpk，在飞牛应用中心「手动安装」。
#
# 只支持 x86_64 Linux：fnpack 只有 linux-amd64 版本，ARM 包的依赖需要在
# ARM 机器上安装，请用 GitHub 的 fork-v* 发布流程。需要 uv、Node.js / npm。
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

SKIP_BUILD=0
KEEP_SP=0
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=1 ;;
    --keep-site-packages) KEEP_SP=1 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "未知参数：$arg（可选 --skip-build、--keep-site-packages）" >&2; exit 1 ;;
  esac
done

if [ "$(uname -s)" != "Linux" ] || [ "$(uname -m)" != "x86_64" ]; then
  echo "只支持在 x86_64 Linux 上构建（fnpack 只有 linux-amd64 版本），当前：$(uname -s) $(uname -m)" >&2
  exit 1
fi
command -v uv >/dev/null || { echo "需要 uv：https://docs.astral.sh/uv/" >&2; exit 1; }

VER="$(sed -nE 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' pyproject.toml | head -1)"
echo "[local-fpk] 版本：$VER"

PY="$(uv python find 3.12 2>/dev/null || true)"
if [ -z "$PY" ]; then
  echo "[local-fpk] 安装 Python 3.12（uv 管理，不影响项目虚拟环境）..."
  # uv may report errors refreshing other versions' links on some filesystems
  # even though 3.12 itself installed; only fail if 3.12 is still missing.
  uv python install 3.12 || true
  PY="$(uv python find 3.12 2>/dev/null || true)"
  [ -n "$PY" ] || { echo "Python 3.12 安装失败" >&2; exit 1; }
fi
echo "[local-fpk] Python：$PY"

WHEEL="dist/octop-${VER}-py3-none-any.whl"
if [ "$SKIP_BUILD" = 0 ]; then
  command -v npm >/dev/null || { echo "需要 Node.js / npm 构建前端" >&2; exit 1; }
  make build
fi
[ -f "$WHEEL" ] || { echo "找不到 $WHEEL（去掉 --skip-build 重新构建）" >&2; exit 1; }

SP="$ROOT/fnos/native/app/site-packages"
cleanup() {
  if [ "$KEEP_SP" = 0 ]; then rm -rf "$SP"; fi
}
trap cleanup EXIT
rm -rf "$SP"
mkdir -p "$SP"

echo "[local-fpk] 安装依赖到 site-packages..."
uv pip install --quiet --python "$PY" --target "$SP" --no-cache "$WHEEL"
rm -rf "$SP/mcp" "$SP"/mcp-*.dist-info \
       "$SP/langchain_mcp_adapters" "$SP"/langchain_mcp_adapters-*.dist-info
uv pip install --quiet --python "$PY" --target "$SP" --no-deps --no-cache \
  "mcp==1.28.1" "langchain-mcp-adapters==0.3.0"
cp "$WHEEL" "$SP/octop.whl"
mkdir -p "$SP/octop_harness/backends"
cp scripts/fnos/vendor/storage_errors.py "$SP/octop_harness/backends/storage_errors.py"
rm -f "$SP/.lock"
bash scripts/fnos/slim-site-packages.sh "$SP"
# Like the release workflow, the self-check runs after slimming and leaves .pyc
# caches for the imported modules in the package (faster first start on the NAS).
PYTHONPATH="$SP" "$PY" -c "import octop, mcp, langchain_mcp_adapters; from octop.launch import run_foreground_blocking; from octop_harness.backends.storage_errors import classify_storage_error; print('[local-fpk] 自检通过 octop', octop.__version__)"

FPK_NAME_PREFIX=Octop-fnos FPK_ARCH=amd64 bash scripts/build-fpk.sh native

OUT="dist/Octop-fnos-native-${VER}.fpk"
[ -f "$OUT" ] || { echo "没有生成 $OUT" >&2; exit 1; }
echo "[local-fpk] 完成：$OUT（$(( $(stat -c %s "$OUT") / 1048576 )) MB）"
echo "[local-fpk] 在飞牛应用中心「手动安装」选择此文件即可升级。"
