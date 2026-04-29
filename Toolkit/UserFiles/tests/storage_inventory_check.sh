#!/usr/bin/env bash
set -u

OUT_DIR="${1:-./storage-inventory-check}"
mkdir -p "$OUT_DIR"

STATUS=0

capture_required() {
  local name="$1"
  shift
  echo "[INFO] collecting $name"
  if "$@" >"$OUT_DIR/$name.txt" 2>&1; then
    echo "[PASS] $name"
  else
    echo "[FAIL] $name"
    STATUS=1
  fi
}

capture_optional() {
  local name="$1"
  shift
  echo "[INFO] collecting $name"
  if "$@" >"$OUT_DIR/$name.txt" 2>&1; then
    echo "[PASS] $name"
  else
    echo "[WARN] $name collection failed or command is unavailable"
  fi
}

capture_required lsblk lsblk -o NAME,TYPE,SIZE,MODEL,SERIAL,FSTYPE,MOUNTPOINT
capture_optional nvme-list bash -lc "command -v nvme >/dev/null 2>&1 && nvme list"
capture_optional pcie-storage bash -lc "command -v lspci >/dev/null 2>&1 && lspci -nn | grep -Ei 'non-volatile|storage|raid|sata|sas|nvme'"

if [ "$STATUS" -eq 0 ]; then
  echo "PASSED" >"$OUT_DIR/status.txt"
else
  echo "FAILED" >"$OUT_DIR/status.txt"
fi

exit "$STATUS"
