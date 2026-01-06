#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="$SCRIPT_DIR/arxiv-picker.swift"

if [[ ! -f "$TARGET" ]]; then
  echo "[watch] missing $TARGET" >&2
  exit 1
fi

pid=""

stop_app() {
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    echo "[watch] stopping pid=${pid}"
    kill -TERM "${pid}" 2>/dev/null || true
    # Give it a moment to exit cleanly.
    for _ in {1..20}; do
      if ! kill -0 "${pid}" 2>/dev/null; then
        pid=""
        return
      fi
      sleep 0.1
    done
    echo "[watch] force-killing pid=${pid}"
    kill -KILL "${pid}" 2>/dev/null || true
    pid=""
  fi
}

start_app() {
  echo "[watch] launching"
  # Run as a script (doesn't require +x).
  local sample_pdf="${ARXIV_SAMPLE_PDF:-1}"
  ARXIV_SAMPLE_PDF="$sample_pdf" /usr/bin/env swift "$TARGET" &
  pid=$!
  echo "[watch] running pid=${pid}"
}

cleanup() {
  stop_app
}

trap cleanup INT TERM EXIT

# Launch once immediately.
start_app

last_mtime="$(stat -f %m "$TARGET")"

echo "[watch] watching $TARGET (save to relaunch)"

while true; do
  sleep 0.25
  mtime="$(stat -f %m "$TARGET")"
  if [[ "$mtime" != "$last_mtime" ]]; then
    last_mtime="$mtime"
    # Debounce a little to avoid double reloads.
    sleep 0.15

    echo "[watch] change detected; typechecking"
    if swiftc -typecheck "$TARGET"; then
      stop_app
      start_app
    else
      echo "[watch] typecheck failed; not relaunching" >&2
    fi
  fi
done
