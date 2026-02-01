#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$ROOT/build"
APP_NAME="AstroStack"
APP_DIR="$BUILD_DIR/$APP_NAME.app"
BIN_DIR="$APP_DIR/Contents/MacOS"
RES_DIR="$APP_DIR/Contents/Resources"
INFO_PLIST="$ROOT/Resources/Info.plist"
FILELIST="$BUILD_DIR/$APP_NAME.filelist"
MODULE_CACHE="$BUILD_DIR/ModuleCache"

SWIFTC="$(/usr/bin/xcrun --find swiftc 2>/dev/null || true)"
SDKROOT="$(/usr/bin/xcrun --sdk macosx --show-sdk-path 2>/dev/null || true)"
CODESIGN="$(/usr/bin/xcrun --find codesign 2>/dev/null || true)"
if [[ -z "$SWIFTC" || -z "$SDKROOT" ]]; then
  echo "[build-app] Xcode Command Line Tools not found." >&2
  exit 127
fi
if [[ -z "$CODESIGN" ]]; then
  echo "[build-app] codesign not found; install Xcode Command Line Tools." >&2
  exit 127
fi

mkdir -p "$BIN_DIR" "$RES_DIR" "$MODULE_CACHE"

if [[ ! -f "$INFO_PLIST" ]]; then
  echo "[build-app] missing Info.plist at $INFO_PLIST" >&2
  exit 1
fi

# Build relative file list to avoid spaces in path entries.
(
  cd "$ROOT"
  LANG=C find Sources -name "*.swift" -print0 | sort -z | xargs -0 -I{} echo "{}" > "$FILELIST"
)

BIN="$BIN_DIR/$APP_NAME"
(
  cd "$ROOT"
  "$SWIFTC" -module-name "$APP_NAME" -sdk "$SDKROOT" -module-cache-path "$MODULE_CACHE" -o "$BIN" @"$FILELIST"
)

cp "$INFO_PLIST" "$APP_DIR/Contents/Info.plist"

if [[ -f "$ROOT/Resources/MailScan.applescript" ]]; then
  cp "$ROOT/Resources/MailScan.applescript" "$RES_DIR/MailScan.applescript"
fi

ASSETS_DIR="$ROOT/Resources/Assets.xcassets"
if [[ -d "$ASSETS_DIR" ]]; then
  ACTOOL="$(/usr/bin/xcrun --find actool 2>/dev/null || true)"
  if [[ -z "$ACTOOL" ]]; then
    echo "[build-app] actool not found; install Xcode Command Line Tools." >&2
    exit 127
  fi
  PARTIAL_PLIST="$BUILD_DIR/Assets.partial.plist"
  rm -f "$RES_DIR/Assets.car" "$RES_DIR/AppIcon.icns" "$PARTIAL_PLIST"
  "$ACTOOL" --compile "$RES_DIR" \
            --platform macosx \
            --minimum-deployment-target 10.15 \
            --app-icon AppIcon \
            --output-partial-info-plist "$PARTIAL_PLIST" \
            "$ASSETS_DIR" >/dev/null
fi

if [[ -d "$ROOT/katex" ]]; then
  rm -rf "$RES_DIR/katex"
  cp -R "$ROOT/katex" "$RES_DIR/katex"
fi

# Ensure the bundle is valid on modern macOS (ad-hoc signing seals resources).
"$CODESIGN" --force --deep --sign - "$APP_DIR" >/dev/null

echo "[build-app] built $APP_DIR"
