#!/usr/bin/env bash
set -u

OUT_DIR="${1:-./system-info}"
mkdir -p "$OUT_DIR"

run_capture() {
  local name="$1"
  shift
  {
    echo "### $name"
    echo "command: $*"
    echo
    "$@"
  } >"$OUT_DIR/$name.txt" 2>&1 || true
}

run_shell_capture() {
  local name="$1"
  local command="$2"
  {
    echo "### $name"
    echo "command: $command"
    echo
    bash -lc "$command"
  } >"$OUT_DIR/$name.txt" 2>&1 || true
}

date -Is >"$OUT_DIR/collected_at.txt" 2>&1 || true
run_capture hostname hostname
run_capture uname uname -a
run_capture uptime uptime
run_shell_capture os-release "cat /etc/os-release"
run_capture cpu lscpu
run_capture memory free -h
run_capture filesystems df -hT
run_capture block lsblk -o NAME,TYPE,SIZE,MODEL,SERIAL,FSTYPE,MOUNTPOINT
run_shell_capture nvme "if command -v nvme >/dev/null 2>&1; then nvme list; else echo 'nvme command not found'; fi"
run_shell_capture pcie "if command -v lspci >/dev/null 2>&1; then lspci -nn; else echo 'lspci command not found'; fi"
run_shell_capture network "ip -brief address || ifconfig -a"
run_shell_capture dmesg-errors "dmesg --level=err,warn 2>/dev/null | tail -n 200 || true"

cat >"$OUT_DIR/README.txt" <<EOF
System information was collected with read-only commands.
This directory is safe to archive as a test artifact.
EOF

echo "system info collected: $OUT_DIR"
