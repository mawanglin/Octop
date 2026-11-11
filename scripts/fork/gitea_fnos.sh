#!/usr/bin/env bash
# 在 Gitea runner 上打飞牛原生版 FPK（fork 自用）。用法：gitea_fnos.sh <amd64|arm64>
# 需要在仓库根目录运行，dist/ 里已有 octop-*.whl。步骤与 .github/workflows/fork-release.yml 的
# fnos-site-packages + fnos-pack 一致。arm64 在 x86 机器上交叉安装：依赖按目标平台选轮子，
# 只有源码的 C 扩展（如 crcmod）装不了时 uv 会直接报错，不会悄悄装成 x86 的；装完再检查一遍 ELF 架构。
set -euo pipefail

arch="${1:?amd64|arm64}"
WHL="$(ls "$PWD"/dist/octop-*.whl | head -1)"
PY="$(uv python find 3.12)"
SP="$PWD/fnos/native/app/site-packages"

if [ ! -d /tmp/octop-pinned ] || ! ls /tmp/octop-pinned/*.whl >/dev/null 2>&1; then
  mkdir -p /tmp/octop-pinned
  uvx pip download --only-binary :all: --no-deps --no-cache-dir -d /tmp/octop-pinned \
    "mcp==1.28.1" "langchain-mcp-adapters==0.3.0"
fi

rm -rf "$SP"
mkdir -p "$SP"
if [ "$arch" = amd64 ]; then
  uv pip install --python "$PY" --target "$SP" --no-cache "$WHL"
else
  uv pip install --python "$PY" --target "$SP" --no-cache \
    --python-platform aarch64-manylinux_2_28 "$WHL"
fi
rm -rf "$SP/mcp" "$SP"/mcp-*.dist-info \
       "$SP/langchain_mcp_adapters" "$SP"/langchain_mcp_adapters-*.dist-info
for whl in /tmp/octop-pinned/*.whl; do "$PY" -m zipfile -e "$whl" "$SP"; done
cp "$WHL" "$SP/octop.whl"
mkdir -p "$SP/octop_harness/backends"
cp scripts/fnos/vendor/storage_errors.py "$SP/octop_harness/backends/storage_errors.py"
bash scripts/fnos/slim-site-packages.sh "$SP"

want=62
[ "$arch" = arm64 ] && want=183
"$PY" - "$SP" "$want" <<'PY'
import pathlib, sys
root, want = pathlib.Path(sys.argv[1]), int(sys.argv[2])
bad = []
for p in root.rglob("*"):
    if p.is_file() and not p.is_symlink() and (p.suffix == ".so" or ".so." in p.name):
        head = p.open("rb").read(20)
        if head[:4] == b"\x7fELF" and int.from_bytes(head[18:20], "little") != want:
            bad.append(str(p.relative_to(root)))
if bad:
    raise SystemExit("架构不对的原生文件：" + ", ".join(bad[:10]))
print("原生文件架构检查通过")
PY

if [ "$arch" = amd64 ]; then
  PYTHONPATH="$SP" "$PY" -c "import octop, mcp, langchain_mcp_adapters; from octop.launch import run_foreground_blocking; from octop_harness.backends.storage_errors import classify_storage_error; print('octop', octop.__version__)"
fi
test -d "$SP/octop"
FPK_NAME_PREFIX=Octop-fnos FPK_ARCH="$arch" bash scripts/build-fpk.sh native
ls -lh dist/*.fpk
