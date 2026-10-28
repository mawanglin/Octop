#!/usr/bin/env bash
# Fork 专用：把 Wails 构建出的 Linux 桌面程序打成 deb、rpm、AppImage。
#
# 用法：scripts/fork/linux_packages.sh <amd64|arm64> <版本号> <程序文件> <输出目录>
# 输出：<输出目录>/Octop-desktop-linux-<arch>-<版本号>.{deb,rpm,AppImage}
#
# 程序依赖系统的 GTK4 和 WebKitGTK 6.0（与官方 tar.gz 一样），包里不带这两个库。
# 工具（nfpm、appimagetool）从 GitHub Release 下载预编译文件，缓存在 $OCTOP_PKG_TOOLS（默认 /tmp/octop-pkg-tools）。
set -euo pipefail

ARCH="${1:?arch: amd64|arm64}"
VERSION="${2:?version}"
BINARY="${3:?binary path}"
OUT="${4:?output dir}"

NFPM_VERSION="${NFPM_VERSION:-2.41.1}"
APPIMAGETOOL_VERSION="${APPIMAGETOOL_VERSION:-1.9.0}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ICON="${ROOT}/desktop/src/build/appicon.png"
TOOLS="${OCTOP_PKG_TOOLS:-/tmp/octop-pkg-tools}"

case "$ARCH" in
  amd64) ai_arch="x86_64" ;;
  arm64) ai_arch="aarch64" ;;
  *) echo "unknown arch: $ARCH" >&2; exit 2 ;;
esac
[[ -f "$BINARY" ]] || { echo "binary not found: $BINARY" >&2; exit 1; }
[[ -f "$ICON" ]] || { echo "icon not found: $ICON" >&2; exit 1; }
mkdir -p "$OUT" "$TOOLS"
OUT="$(cd "$OUT" && pwd)"
BINARY="$(cd "$(dirname "$BINARY")" && pwd)/$(basename "$BINARY")"

fetch() { # url dest
  [[ -s "$2" ]] || curl -fsSL --retry 5 --retry-delay 5 -o "$2" "$1"
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cat > "${work}/octop.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Octop
Comment=Self-hosted AI assistant platform
Exec=octop-desktop
Icon=octop
Terminal=false
Categories=Utility;Network;
EOF

# ---------------------------------------------------------------- deb / rpm
host_arch="$(uname -m)"
case "$host_arch" in
  x86_64) nfpm_host="x86_64" ;;
  aarch64|arm64) nfpm_host="arm64" ;;
  *) echo "unsupported host: $host_arch" >&2; exit 1 ;;
esac
nfpm_tgz="${TOOLS}/nfpm-${NFPM_VERSION}-${nfpm_host}.tar.gz"
fetch "https://github.com/goreleaser/nfpm/releases/download/v${NFPM_VERSION}/nfpm_${NFPM_VERSION}_Linux_${nfpm_host}.tar.gz" "$nfpm_tgz"
tar -xzf "$nfpm_tgz" -C "$work" nfpm

cat > "${work}/nfpm.yaml" <<EOF
name: octop-desktop
arch: ${ARCH}
platform: linux
version: "${VERSION}"
version_schema: none
section: utils
maintainer: Octop fork <noreply@github.com>
description: Octop desktop client (self-hosted AI assistant platform)
homepage: https://github.com/mawanglin/Octop
license: Apache-2.0
contents:
  - src: ${BINARY}
    dst: /usr/bin/octop-desktop
    file_info: {mode: 0755}
  - src: ${work}/octop.desktop
    dst: /usr/share/applications/octop.desktop
    file_info: {mode: 0644}
  - src: ${ICON}
    dst: /usr/share/icons/hicolor/512x512/apps/octop.png
    file_info: {mode: 0644}
overrides:
  deb:
    depends: [libgtk-4-1, libwebkitgtk-6.0-4]
  rpm:
    depends: [gtk4, webkitgtk6.0]
EOF

for fmt in deb rpm; do
  "${work}/nfpm" package --config "${work}/nfpm.yaml" --packager "$fmt" \
    --target "${OUT}/Octop-desktop-linux-${ARCH}-${VERSION}.${fmt}"
done

# ----------------------------------------------------------------- AppImage
ait="${TOOLS}/appimagetool-${APPIMAGETOOL_VERSION}-${host_arch}.AppImage"
fetch "https://github.com/AppImage/appimagetool/releases/download/${APPIMAGETOOL_VERSION}/appimagetool-${host_arch/arm64/aarch64}.AppImage" "$ait"
chmod +x "$ait"

appdir="${work}/Octop.AppDir"
mkdir -p "${appdir}/usr/bin"
install -m 0755 "$BINARY" "${appdir}/usr/bin/octop-desktop"
cp "${work}/octop.desktop" "${appdir}/octop.desktop"
cp "$ICON" "${appdir}/octop.png"
cat > "${appdir}/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "${HERE}/usr/bin/octop-desktop" "$@"
EOF
chmod +x "${appdir}/AppRun"

command -v desktop-file-validate >/dev/null || {
  echo "appimagetool 需要 desktop-file-validate（apt install desktop-file-utils）" >&2
  exit 1
}
# 不依赖 FUSE：让 appimagetool 解包后直接运行。
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$ai_arch" "$ait" --no-appstream "$appdir" \
  "${OUT}/Octop-desktop-linux-${ARCH}-${VERSION}.AppImage"

ls -lh "${OUT}"/Octop-desktop-linux-"${ARCH}"-"${VERSION}".*
