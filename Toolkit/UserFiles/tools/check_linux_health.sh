#!/usr/bin/env bash
set -u

STATUS=0

pass() {
  echo "[PASS] $*"
}

warn() {
  echo "[WARN] $*"
}

fail() {
  echo "[FAIL] $*"
  STATUS=1
}

if [ -r /etc/os-release ]; then
  pass "/etc/os-release is readable"
else
  fail "/etc/os-release is not readable"
fi

if command -v python3 >/dev/null 2>&1; then
  pass "python3 is available: $(python3 --version 2>&1)"
else
  fail "python3 is not available"
fi

root_usage="$(df -P / | awk 'NR==2 {gsub(/%/, "", $5); print $5}')"
if [ -n "$root_usage" ]; then
  if [ "$root_usage" -ge 95 ]; then
    fail "root filesystem usage is ${root_usage}%"
  else
    pass "root filesystem usage is ${root_usage}%"
  fi
else
  fail "failed to read root filesystem usage"
fi

if command -v lsblk >/dev/null 2>&1; then
  pass "lsblk is available"
else
  fail "lsblk is not available"
fi

if command -v nvme >/dev/null 2>&1; then
  pass "nvme-cli is available"
else
  warn "nvme-cli is not installed; NVMe inventory will be limited"
fi

if command -v lspci >/dev/null 2>&1; then
  pass "lspci is available"
else
  warn "lspci is not installed; PCIe inventory will be limited"
fi

exit "$STATUS"
