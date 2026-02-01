#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="AstroStack"
BUILD_DIR="$ROOT/build"
APP_DIR="$BUILD_DIR/$APP_NAME.app"
DEST_DIR="/Applications"
DEST_APP="$DEST_DIR/$APP_NAME.app"

if [[ ! -d "$APP_DIR" ]]; then
  "$ROOT/scripts/build-app.sh"
fi

if [[ ! -d "$APP_DIR" ]]; then
  echo "[install-app] missing app bundle at $APP_DIR" >&2
  exit 1
fi

if [[ -d "$DEST_APP" ]]; then
  rm -rf "$DEST_APP"
fi

if ! /usr/bin/ditto "$APP_DIR" "$DEST_APP"; then
  echo "[install-app] failed to install to $DEST_APP" >&2
  echo "[install-app] try rerunning with sudo if permissions are required." >&2
  exit 1
fi

echo "[install-app] installed $DEST_APP"
