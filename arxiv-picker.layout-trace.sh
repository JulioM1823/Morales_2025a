#!/usr/bin/env bash
set -euo pipefail

# Interactive layout trace helper.
# Usage:
#   DEBUG_LAYOUT=1 ./arxiv-picker.layout-trace.sh
# Then reproduce: grab divider (watch for flash), toggle sidebar, etc.
# Logs are captured to ./layout-trace-YYYYmmdd-HHMMSS.log

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

TS="$(date +"%Y%m%d-%H%M%S")"
OUT="layout-trace-$TS.log"

export DEBUG_LAYOUT="${DEBUG_LAYOUT:-1}"
export ARXIV_UI_DEBUG="${ARXIV_UI_DEBUG:-0}"

echo "Writing trace to: $OUT" >&2
echo "Tip: set ARXIV_UI_DEBUG=1 as well for deeper hit-test dumps." >&2

# Run as a foreground process so you can interact with the window.
# We tee stdout+stderr so you can paste just the [LayoutDebug] lines later.
./arxiv-picker.swift 2>&1 | tee "$OUT"
