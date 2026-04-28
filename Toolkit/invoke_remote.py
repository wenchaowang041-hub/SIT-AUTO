from __future__ import annotations

import argparse
import base64
import json

try:
    from Libraries.toolkit_lib import collect_file, execute_command
except ModuleNotFoundError:
    from Toolkit.Libraries.toolkit_lib import collect_file, execute_command


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Linux Toolkit remote runner")
    parser.add_argument("--payload-b64", required=True, help="Base64 编码后的 JSON 负载")
    return parser.parse_args()


def main() -> int:
    # 这个脚本对应旧平台里的 invoke-remote 入口。
    args = parse_args()
    payload = json.loads(base64.b64decode(args.payload_b64.encode("utf-8")).decode("utf-8"))

    mode = payload["mode"]
    result_dir = payload["result_dir"]

    if mode == "command":
        return execute_command(
            command=payload["command"],
            result_dir=result_dir,
            timeout_sec=payload.get("timeout_sec", 300),
        )

    if mode == "fetch":
        return collect_file(
            remote_path=payload["remote_path"],
            result_dir=result_dir,
            local_name=payload.get("local_name"),
        )

    raise ValueError(f"unsupported mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
