#!/bin/bash
# Build script for the earthview-wallpaper .deb package.
#
# Stages the current source tree into the package layout, normalises
# ownership and permissions, then builds the archive.

set -euo pipefail

VERSION="2.0.5"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$SCRIPT_DIR/earthview-package"
SHARE_DIR="$PKG_DIR/usr/share/earthview"
SRC_DIR="$SCRIPT_DIR/wallpaper-changer"
OUTPUT="$SCRIPT_DIR/earthview-wallpaper_${VERSION}_all.deb"

echo "Building Earth View Wallpaper Engine v${VERSION} package..."

# Keep the declared version and the filename in sync.
CONTROL_VERSION="$(awk '/^Version:/ {print $2}' "$PKG_DIR/DEBIAN/control")"
if [ "$CONTROL_VERSION" != "$VERSION" ]; then
    echo "ERROR: DEBIAN/control says $CONTROL_VERSION but this script builds $VERSION." >&2
    exit 1
fi

# --- Stage payload -------------------------------------------------------
# Wipe generated content so removed modules never linger in the package.
rm -rf "$SHARE_DIR/sources" "$SHARE_DIR/wallpaper_collections"
find "$SHARE_DIR" -maxdepth 1 -name '*.py' -delete
find "$SHARE_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$SHARE_DIR" -name '*.pyc' -delete 2>/dev/null || true

install -d "$SHARE_DIR" "$SHARE_DIR/sources" "$SHARE_DIR/wallpaper_collections"

# Application modules (read-only data, mode 644).
for f in preferences.py timeaware.py flyover.py migrate_data.py; do
    install -m 644 "$SRC_DIR/$f" "$SHARE_DIR/$f"
done
install -m 644 "$SRC_DIR/data.json" "$SHARE_DIR/data.json"
install -m 644 "$SRC_DIR/logo.png" "$SHARE_DIR/logo.png"

# Entry point is executable.
install -m 755 "$SRC_DIR/indicator.py" "$SHARE_DIR/indicator.py"

install -m 644 "$SRC_DIR/sources/"*.py "$SHARE_DIR/sources/"
install -m 644 "$SRC_DIR/wallpaper_collections/"*.py "$SHARE_DIR/wallpaper_collections/"
install -m 644 "$SRC_DIR/wallpaper_collections/"*.json "$SHARE_DIR/wallpaper_collections/"

# Launcher wrapper.
chmod 755 "$PKG_DIR/usr/bin/earthview-wallpaper"

# NOTE: no wallpaper.jpg is shipped. The downloaded wallpaper is per-user
# runtime data and is written to ~/.cache/earthview/ at runtime, which keeps
# /usr/share read-only and root-owned.

# --- Documentation -------------------------------------------------------
# Debian policy requires a changelog and copyright file, and expects the
# changelog and man pages to be gzip compressed. Pristine sources live in
# packaging/ and are staged here, so the build never destroys its own inputs
# and repeated runs are idempotent.
DOC_SRC="$SCRIPT_DIR/packaging"
DOC_DIR="$PKG_DIR/usr/share/doc/earthview-wallpaper"
MAN_DIR="$PKG_DIR/usr/share/man/man1"

for required in changelog copyright earthview-wallpaper.1; do
    if [ ! -f "$DOC_SRC/$required" ]; then
        echo "ERROR: missing packaging/$required" >&2
        exit 1
    fi
done

rm -rf "$DOC_DIR" "$MAN_DIR"
install -d "$DOC_DIR" "$MAN_DIR"

install -m 644 "$DOC_SRC/copyright" "$DOC_DIR/copyright"
gzip -9nc "$DOC_SRC/changelog" > "$DOC_DIR/changelog.gz"
gzip -9nc "$DOC_SRC/earthview-wallpaper.1" > "$MAN_DIR/earthview-wallpaper.1.gz"
chmod 644 "$DOC_DIR/changelog.gz" "$MAN_DIR/earthview-wallpaper.1.gz"

# The changelog's top version must match what we are building.
CHANGELOG_VERSION="$(head -1 "$DOC_SRC/changelog" | sed -E 's/.*\(([^)]+)\).*/\1/')"
if [ "$CHANGELOG_VERSION" != "$VERSION" ]; then
    echo "ERROR: changelog top entry is $CHANGELOG_VERSION but building $VERSION." >&2
    exit 1
fi

# --- Icons ---------------------------------------------------------------
# Staged from packaging/icons so the installed theme always matches the
# master artwork. Each PNG must match its directory name or lintian fails.
ICON_SRC="$SCRIPT_DIR/packaging/icons"
ICON_DIR="$PKG_DIR/usr/share/icons/hicolor"

if [ ! -f "$ICON_SRC/earthview-wallpaper.svg" ]; then
    echo "ERROR: missing packaging/icons/earthview-wallpaper.svg" >&2
    exit 1
fi

rm -rf "$ICON_DIR"
for size in 32 48 64 128 256 512; do
    src="$ICON_SRC/earthview-wallpaper-${size}.png"
    if [ ! -f "$src" ]; then
        echo "ERROR: missing packaging/icons/earthview-wallpaper-${size}.png" >&2
        exit 1
    fi
    install -Dm644 "$src" "$ICON_DIR/${size}x${size}/apps/earthview-wallpaper.png"
done
install -Dm644 "$ICON_SRC/earthview-wallpaper.svg" \
               "$ICON_DIR/scalable/apps/earthview-wallpaper.svg"

# --- Normalise permissions ----------------------------------------------
# Directories 755 and data files 644 as policy requires; the build tree may
# carry group-writable bits from the working copy.
find "$PKG_DIR" -path "$PKG_DIR/DEBIAN" -prune -o -type d -exec chmod 755 {} +
find "$PKG_DIR/usr/share/icons" -type f -exec chmod 644 {} +
chmod 644 "$PKG_DIR/usr/share/applications/earthview-wallpaper.desktop"

# --- Maintainer scripts --------------------------------------------------
for script in postinst prerm postrm; do
    if [ -f "$PKG_DIR/DEBIAN/$script" ]; then
        chmod 755 "$PKG_DIR/DEBIAN/$script"
        bash -n "$PKG_DIR/DEBIAN/$script" \
            || { echo "ERROR: syntax error in DEBIAN/$script" >&2; exit 1; }
    fi
done
chmod 644 "$PKG_DIR/DEBIAN/control"

# --- Build ---------------------------------------------------------------
# --root-owner-group forces root:root ownership inside the archive without
# needing fakeroot. Without it, files inherit the build user and land in
# /usr/share owned by that user.
rm -f "$OUTPUT"
dpkg-deb --root-owner-group --build "$PKG_DIR" "$OUTPUT"

echo
echo "Package built: $(basename "$OUTPUT")"
echo
echo "Install with:"
echo "  sudo apt install $OUTPUT"
