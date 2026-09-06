#!/bin/bash
# Build "Open Notebook.app" (AppleScript applet) with a custom icon and install it.
#   scripts/app/build-app.sh [icon.png] [install-dir]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$ROOT/scripts/app/OpenNotebook.applescript"
ICON_PNG="${1:-$HOME/Pictures/Gojo3D.png}"
DEST_DIR="${2:-/Applications}"
APP="$DEST_DIR/Open Notebook.app"
BUILD="$ROOT/data/app/build"
rm -rf "$BUILD" && mkdir -p "$BUILD"

echo "Compiling applet..."
osacompile -s -o "$BUILD/Open Notebook.app" "$SRC"

echo "Generating icon from $ICON_PNG..."
ICONSET="$BUILD/AppIcon.iconset"; mkdir -p "$ICONSET"
SQ="$BUILD/square.png"
# Pad to square (macOS icon grid), 1024x1024
sips -s format png -Z 1024 "$ICON_PNG" --out "$SQ" >/dev/null
sips -p 1024 1024 "$SQ" --out "$SQ" >/dev/null 2>&1 || true
for s in 16 32 128 256 512; do
  sips -z $s $s "$SQ" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2)); sips -z $d $d "$SQ" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$BUILD/applet.icns"

RES="$BUILD/Open Notebook.app/Contents/Resources"
cp "$BUILD/applet.icns" "$RES/applet.icns"
PLIST="$BUILD/Open Notebook.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName 'Open Notebook'" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string 'Open Notebook'" "$PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 'Open Notebook'" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.ro28.open-notebook" "$PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.ro28.open-notebook" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleIconFile applet" "$PLIST" 2>/dev/null || true
# Refresh the applet's stale icon cache and sign ad-hoc so Gatekeeper is happy locally
rm -f "$RES/applet.rsrc" "$RES/Assets.car"
/usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$PLIST" 2>/dev/null || true
codesign --force --deep -s - "$BUILD/Open Notebook.app" >/dev/null 2>&1 || true

echo "Installing to $APP"
rm -rf "$APP"
cp -R "$BUILD/Open Notebook.app" "$APP"
touch "$APP"
echo "✅ Built: $APP"
