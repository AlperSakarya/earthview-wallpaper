#!/bin/bash
# Build script for earthview-wallpaper .deb package
# Copies the latest source files into the package structure and builds it.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$SCRIPT_DIR/earthview-package"
SHARE_DIR="$PKG_DIR/usr/share/earthview"
SRC_DIR="$SCRIPT_DIR/wallpaper-changer"

echo "Building Earth View Wallpaper Engine v2.0 package..."

# Clean old share directory (except logo and wallpaper placeholder)
find "$SHARE_DIR" -name "*.py" -delete
find "$SHARE_DIR" -name "*.json" -not -name "data.json" -delete 2>/dev/null || true
rm -rf "$SHARE_DIR/sources" "$SHARE_DIR/wallpaper_collections"

# Copy main files
cp "$SRC_DIR/indicator.py" "$SHARE_DIR/"
cp "$SRC_DIR/preferences.py" "$SHARE_DIR/"
cp "$SRC_DIR/timeaware.py" "$SHARE_DIR/"
cp "$SRC_DIR/flyover.py" "$SHARE_DIR/"
cp "$SRC_DIR/migrate_data.py" "$SHARE_DIR/"
cp "$SRC_DIR/data.json" "$SHARE_DIR/"
cp "$SRC_DIR/logo.png" "$SHARE_DIR/"

# Copy sources module
mkdir -p "$SHARE_DIR/sources"
cp "$SRC_DIR/sources/"*.py "$SHARE_DIR/sources/"

# Copy collections module and data
mkdir -p "$SHARE_DIR/wallpaper_collections"
cp "$SRC_DIR/wallpaper_collections/"*.py "$SHARE_DIR/wallpaper_collections/"
cp "$SRC_DIR/wallpaper_collections/"*.json "$SHARE_DIR/wallpaper_collections/"

# Set permissions
chmod 755 "$SHARE_DIR/indicator.py"
chmod 755 "$PKG_DIR/DEBIAN/postinst"
find "$SHARE_DIR" -name "*.py" -exec chmod 644 {} \;
chmod 755 "$SHARE_DIR/indicator.py"

# Build the package
dpkg-deb --build "$PKG_DIR" "$SCRIPT_DIR/earthview-wallpaper_2.0.1_all.deb"

echo "Package built: earthview-wallpaper_2.0.1_all.deb"
