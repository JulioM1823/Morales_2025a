#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Lightweight, deterministic launch sanity check.
# Runs the existing launch-check multiple times and fails nonzero if any run fails.
#
# Usage:
#   ./arxiv-picker.launch-sanity.sh
#   RUNS=10 ./arxiv-picker.launch-sanity.sh

RUNS="${RUNS:-3}"

fails=0
for i in $(seq 1 "$RUNS"); do
  echo "[SANITY] run ${i}/${RUNS}"
  if ! "$SCRIPT_DIR/arxiv-picker.launch-check.sh"; then
    ec=$?
    echo "[SANITY] failed run ${i} exit_code=${ec}" >&2
    fails=$((fails+1))
  fi
done

if [[ "$fails" -ne 0 ]]; then
  echo "[SANITY] failures=${fails}/${RUNS}" >&2
  exit 1
fi

echo "[SANITY] ok (${RUNS}/${RUNS})"
