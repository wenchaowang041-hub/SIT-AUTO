#!/usr/bin/env bash
set -euo pipefail

# 在 Linux 控制器上创建虚拟环境并安装最小依赖。
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements-controller.txt

python TestController/StartController.py check-environment

echo
echo "控制器基础依赖安装完成。"
echo "下一步建议："
echo "  1. 编辑 TestControllerUserFiles/ServerLists 下的实际清单"
echo "  2. 运行: python TestController/StartController.py preflight --suite linux_smoke --server-list <你的清单> --probe-ssh"
