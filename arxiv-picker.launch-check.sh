#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

DEBUG_LAUNCH=1 ARXIV_LAUNCH_CHECK=1 "$SCRIPT_DIR/arxiv-picker.swift" </dev/null
