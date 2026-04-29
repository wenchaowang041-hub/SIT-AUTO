#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USERFILES_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="${1:-./smoke-system-check}"

mkdir -p "$OUT_DIR"

echo "[INFO] output directory: $OUT_DIR"
bash "$USERFILES_DIR/tools/collect_system_info.sh" "$OUT_DIR/system-info"
bash "$USERFILES_DIR/tools/check_linux_health.sh" | tee "$OUT_DIR/health-check.txt"
status="${PIPESTATUS[0]}"

if [ "$status" -eq 0 ]; then
  echo "PASSED" >"$OUT_DIR/status.txt"
else
  echo "FAILED" >"$OUT_DIR/status.txt"
fi

exit "$status"
