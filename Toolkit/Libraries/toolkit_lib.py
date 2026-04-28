from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def ensure_directory(path: str | Path) -> Path:
    target = Path(path).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    return target


def execute_command(command: str, result_dir: str | Path, timeout_sec: int = 300) -> int:
    # Toolkit 端只负责在目标机本地执行命令，并把输出写到结果目录。
    result_path = ensure_directory(result_dir)
    completed = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )

    (result_path / "stdout.log").write_text(completed.stdout, encoding="utf-8")
    (result_path / "stderr.log").write_text(completed.stderr, encoding="utf-8")
    (result_path / "metadata.json").write_text(
        json.dumps(
            {
                "mode": "command",
                "command": command,
                "exit_code": completed.returncode,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return completed.returncode


def collect_file(remote_path: str, result_dir: str | Path, local_name: str | None = None) -> int:
    # 这里的 collect 不是回传给控制器，而是先把目标机本地文件归档到目标机结果目录。
    source = Path(remote_path).expanduser()
    result_path = ensure_directory(result_dir)

    if not source.exists():
        (result_path / "stderr.log").write_text(f"file not found: {remote_path}", encoding="utf-8")
        return 1

    destination = result_path / (local_name or source.name)
    shutil.copy2(source, destination)
    (result_path / "metadata.json").write_text(
        json.dumps(
            {
                "mode": "fetch",
                "remote_path": remote_path,
                "saved_as": destination.name,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0
