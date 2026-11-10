#!/usr/bin/env bash
# Build the Linux packages (.deb, AppImage, portable tar.gz).
#
# Usage:
#   bash scripts/build_linux.sh
#
# Requires: python3 with the project dependencies, PyInstaller, dpkg-deb,
# curl. The AppImage step downloads appimagetool on first use.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VERSION="$("$PYTHON" -c 'import utils.version as v; print(v.APP_VERSION)')"
GIT_HASH="$(git rev-parse --short HEAD 2>/dev/null || true)"
BUILD_TIME="$(date '+%Y-%m-%d %H:%M')"

echo "Building FIDUX ${VERSION} (${GIT_HASH:-no-git})"

# ---- Stamp build info so the running app can prove which build it is -------
"$PYTHON" - "$VERSION" "$GIT_HASH" "$BUILD_TIME" <<'PY'
import sys

version, git_hash, build_time = sys.argv[1:4]
with open("utils/_build_info.py", "w", encoding="utf-8") as handle:
    handle.write(f'BUILD_TIME = "{build_time}"\n')
    handle.write(f'GIT_HASH = "{git_hash}"\n')
    handle.write(f'VERSION = "{version}"\n')
PY
echo "Stamped utils/_build_info.py"

# ---- Clean stale artifacts -------------------------------------------------
rm -rf build/build-linux dist/linux
mkdir -p dist/linux

echo "[1/4] PyInstaller (onedir)"
"$PYTHON" -m PyInstaller scripts/build_linux.spec --noconfirm --clean \
    --workpath build/build-linux --distpath dist/linux

APP_DIR="dist/linux/FIDUX"
if [ ! -x "$APP_DIR/FIDUX" ]; then
    echo "PyInstaller did not produce $APP_DIR/FIDUX" >&2
    exit 1
fi

# ---- .deb ------------------------------------------------------------------
echo "[2/4] Debian package"
DEB_ROOT="dist/linux/deb-root"
rm -rf "$DEB_ROOT"
mkdir -p "$DEB_ROOT/DEBIAN" \
         "$DEB_ROOT/usr/lib/cam350-review" \
         "$DEB_ROOT/usr/bin" \
         "$DEB_ROOT/usr/share/applications" \
         "$DEB_ROOT/usr/share/icons/hicolor/256x256/apps"
cp -a "$APP_DIR/." "$DEB_ROOT/usr/lib/cam350-review/"
cp scripts/cam350-review.desktop "$DEB_ROOT/usr/share/applications/"
cp assets/icon.png "$DEB_ROOT/usr/share/icons/hicolor/256x256/apps/cam350-review.png"

cat > "$DEB_ROOT/usr/bin/cam350-review" <<'LAUNCHER'
#!/bin/sh
exec /usr/lib/cam350-review/FIDUX "$@"
LAUNCHER
chmod 755 "$DEB_ROOT/usr/bin/cam350-review"

cat > "$DEB_ROOT/DEBIAN/control" <<CONTROL
Package: cam350-review
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: FIDUX <support@fidux.app>
Depends: libc6, libstdc++6, libgl1, libegl1, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-xinerama0, libxcb-xkb1, libdbus-1-3, libfontconfig1, libfreetype6, libharfbuzz0b, libpng16-16, zlib1g
Description: FIDUX SMT Review
 Review PickPlace data, align component origins and check Gerber layers
 before running the SMT machines.
CONTROL

DEB_FILE="dist/linux/FIDUX_${VERSION}_amd64.deb"
dpkg-deb --build --root-owner-group "$DEB_ROOT" "$DEB_FILE"
rm -rf "$DEB_ROOT"

# ---- Portable tar.gz -------------------------------------------------------
echo "[3/4] Portable tarball"
PORTABLE="dist/linux/portable/FIDUX_${VERSION}_linux_x86_64"
rm -rf "dist/linux/portable"
mkdir -p "$PORTABLE"
cp -a "$APP_DIR/." "$PORTABLE/"
cp assets/icon.png "$PORTABLE/"
cat > "$PORTABLE/run.sh" <<'LAUNCHER'
#!/bin/sh
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/FIDUX" "$@"
LAUNCHER
chmod 755 "$PORTABLE/run.sh"
TAR_FILE="dist/linux/FIDUX_${VERSION}_linux_x86_64.tar.gz"
tar -czf "$TAR_FILE" -C "$PORTABLE" .
rm -rf "dist/linux/portable"

# ---- AppImage --------------------------------------------------------------
echo "[4/4] AppImage"
APPIMAGE_TOOL="build/tools/appimagetool-x86_64.AppImage"
if [ ! -x "$APPIMAGE_TOOL" ]; then
    mkdir -p build/tools
    if ! curl -fL --retry 3 -o "$APPIMAGE_TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"; then
        curl -fL --retry 3 -o "$APPIMAGE_TOOL" \
            "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    fi
    chmod +x "$APPIMAGE_TOOL"
fi

APPDIR="dist/linux/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a "$APP_DIR/." "$APPDIR/usr/bin/"
cp scripts/cam350-review.desktop "$APPDIR/cam350-review.desktop"
cp assets/icon.png "$APPDIR/cam350-review.png"
cp assets/icon.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/cam350-review.png"
cat > "$APPDIR/AppRun" <<'LAUNCHER'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/FIDUX" "$@"
LAUNCHER
chmod 755 "$APPDIR/AppRun"

APPIMAGE_FILE="dist/linux/FIDUX-${VERSION}-x86_64.AppImage"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE_TOOL" "$APPDIR" "$APPIMAGE_FILE"
rm -rf "$APPDIR"

# ---- Checksums -------------------------------------------------------------
(
    cd dist/linux
    : > SHA256SUMS.txt
    for file in *.deb *.AppImage *.tar.gz; do
        if [ -f "$file" ]; then
            sha256sum "$file" >> SHA256SUMS.txt
        fi
    done
)

echo ""
echo "Done. Linux packages:"
ls -lh dist/linux/*.deb dist/linux/*.AppImage dist/linux/*.tar.gz
cat dist/linux/SHA256SUMS.txt
