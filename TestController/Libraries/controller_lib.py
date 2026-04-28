from __future__ import annotations

import base64
import csv
import json
import posixpath
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import paramiko
import yaml

SUPPORTED_DATA_SUFFIXES = (".yaml", ".yml", ".json")


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def controller_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_data_file(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        return load_json(path)
    return load_yaml(path)


def read_controller_settings() -> dict[str, Any]:
    # 控制器默认设置来自 yaml，再叠加 ToolkitSettings 里的外置 JSON。
    settings = load_yaml(controller_root() / "DefaultControllerSettings.yaml")
    toolkit_settings_file = workspace_root() / "ToolkitSettings" / "user-settings.json"
    if toolkit_settings_file.exists():
        settings = deep_merge(settings, load_json(toolkit_settings_file))
    return settings


def read_version() -> str:
    settings = read_controller_settings()
    version_file = workspace_root() / settings["controller"]["version_file"]
    return version_file.read_text(encoding="utf-8").strip()


def resolve_named_file(name: str, search_roots: list[Path]) -> Path:
    requested = Path(name)
    if requested.suffix:
        candidates = [root / requested.name for root in search_roots]
    else:
        candidates = [root / f"{name}{suffix}" for root in search_roots for suffix in SUPPORTED_DATA_SUFFIXES]

    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(name)


def resolve_suite_file(name: str) -> Path:
    try:
        return resolve_named_file(
            name,
            [
                controller_root() / "TestSuites",
                workspace_root() / "TestControllerUserFiles" / "TestSuites",
            ],
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"test suite was not found: {name}") from exc


def resolve_server_list_file(name: str) -> Path:
    try:
        return resolve_named_file(name, [workspace_root() / "TestControllerUserFiles" / "ServerLists"])
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"server list was not found: {name}") from exc


def list_named_entries(*directories: Path) -> list[str]:
    names: set[str] = set()
    for directory in directories:
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if path.is_file() and path.suffix.lower() in SUPPORTED_DATA_SUFFIXES:
                names.add(path.stem)
    return sorted(names)


def list_suite_names() -> list[str]:
    return list_named_entries(
        controller_root() / "TestSuites",
        workspace_root() / "TestControllerUserFiles" / "TestSuites",
    )


def list_server_list_names() -> list[str]:
    return list_named_entries(workspace_root() / "TestControllerUserFiles" / "ServerLists")


def run_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_controller_result_dir(settings: dict[str, Any], suite_name: str, stamp: str) -> Path:
    path = workspace_root() / settings["controller"]["results_dir"] / suite_name / f"Run-{stamp}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_runtime_root() -> Path:
    path = workspace_root() / ".runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_runtime_result_dir(stamp: str, target_name: str) -> Path:
    path = local_runtime_root() / "Results" / stamp / target_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def remote_runtime_result_dir(settings: dict[str, Any], stamp: str, target_name: str) -> str:
    base = settings["remote"]["results_dir"].rstrip("/")
    return f"{base}/{stamp}/{target_name}"


def render_text(template: str | None, context: dict[str, Any]) -> str:
    if template is None:
        return ""
    return template.format_map(SafeFormatDict(flatten_context(context)))


def flatten_context(context: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in context.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}_{key}"
        if isinstance(value, dict):
            flattened.update(flatten_context(value, full_key))
        else:
            flattened[full_key] = value
            if not prefix:
                flattened[key] = value
    return flattened


class SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def normalize_suite_definition(raw_suite: dict[str, Any], suite_name: str) -> dict[str, Any]:
    # 兼容旧式 test_commands，同时向新版靠拢，支持 metadata / variables / pre/post。
    defaults = {
        "stop_on_fail": True,
        "timeout_sec": 300,
    }
    defaults = deep_merge(defaults, raw_suite.get("defaults", {}))
    return {
        "name": suite_name,
        "description": raw_suite.get("description", ""),
        "metadata": raw_suite.get("metadata", {}),
        "settings": raw_suite.get("settings", {}),
        "variables": raw_suite.get("variables", {}),
        "defaults": defaults,
        "pre_test_commands": raw_suite.get("pre_test_commands", []),
        "test_commands": raw_suite.get("test_commands", []),
        "post_test_commands": raw_suite.get("post_test_commands", []),
    }


def normalize_server_list(raw_server_list: dict[str, Any], server_list_name: str) -> dict[str, Any]:
    # ServerList 允许自带变量和 target 默认值，方便同一套件复用到多套环境。
    defaults = raw_server_list.get("defaults", {})
    global_variables = raw_server_list.get("variables", {})
    targets = []
    for target in raw_server_list.get("targets", []):
        merged_target = deep_merge(defaults, target)
        merged_target.setdefault("executor_type", "ssh")
        merged_target.setdefault("port", 22)
        merged_target.setdefault("labels", [])
        merged_target.setdefault("variables", {})
        targets.append(merged_target)
    return {
        "name": server_list_name,
        "description": raw_server_list.get("description", ""),
        "settings": raw_server_list.get("settings", {}),
        "variables": global_variables,
        "targets": targets,
    }


def build_context(
    *,
    target: dict[str, Any],
    stamp: str,
    local_result_dir: Path,
    suite: dict[str, Any],
    server_list: dict[str, Any],
    settings: dict[str, Any],
    phase: str,
    test_name: str,
    runtime_variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged_variables = deep_merge(suite.get("variables", {}), server_list.get("variables", {}))
    merged_variables = deep_merge(merged_variables, target.get("variables", {}))
    merged_variables = deep_merge(merged_variables, runtime_variables or {})
    return {
        "target": {
            "name": target["name"],
            "host": target["host"],
            "executor_type": target["executor_type"],
            "labels": target.get("labels", []),
        },
        "suite": {
            "name": suite["name"],
            "description": suite["description"],
        },
        "server_list": {
            "name": server_list["name"],
            "description": server_list["description"],
        },
        "settings": settings,
        "variables": merged_variables,
        "target_name": target["name"],
        "target_host": target["host"],
        "suite_name": suite["name"],
        "server_list_name": server_list["name"],
        "phase": phase,
        "test_name": test_name,
        "run_id": stamp,
        "local_result_dir": str(local_result_dir),
        "artifact_dir": str(local_result_dir / test_name),
        "target_labels": target.get("labels", []),
    }


def build_payload(payload: dict[str, Any]) -> str:
    return base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("utf-8")


def command_should_stop(command: dict[str, Any], suite_defaults: dict[str, Any], explicit_stop: bool | None) -> bool:
    if explicit_stop is not None:
        return explicit_stop
    if "stop_on_fail" in command:
        return bool(command["stop_on_fail"])
    return bool(suite_defaults.get("stop_on_fail", True))


def command_timeout(command: dict[str, Any], suite_defaults: dict[str, Any]) -> int:
    return int(command.get("timeout_sec", suite_defaults.get("timeout_sec", 300)))


def sync_setting_enabled(setting_name: str, suite_defaults: dict[str, Any], controller_defaults: dict[str, Any]) -> bool:
    if setting_name in suite_defaults:
        return bool(suite_defaults[setting_name])
    return bool(controller_defaults.get(setting_name, True))


def sync_toolkit_if_needed(target: dict[str, Any], settings: dict[str, Any], sync_options: dict[str, bool]) -> None:
    # 本地目标不需要同步；SSH 目标则按开关上传 Toolkit / ToolkitUserFiles / ToolkitSettings。
    if target["executor_type"] == "local" or not any(sync_options.values()):
        return

    client = connect_ssh(target)
    try:
        sftp = client.open_sftp()
        try:
            remote_toolkit_dir = expand_remote_path(sftp, settings["remote"]["toolkit_dir"])
            remote_toolkit_user_dir = expand_remote_path(sftp, settings["remote"]["toolkit_user_dir"])
            remote_toolkit_settings_dir = expand_remote_path(
                sftp,
                settings["remote"].get(
                    "toolkit_settings_dir",
                    posixpath.join(settings["remote"]["root_dir"], "ToolkitSettings"),
                ),
            )

            if sync_options.get("toolkit", False) and (workspace_root() / "Toolkit").exists():
                upload_tree(sftp, workspace_root() / "Toolkit", remote_toolkit_dir)
            if sync_options.get("toolkit_user", False) and (workspace_root() / "ToolkitUserFiles").exists():
                upload_tree(sftp, workspace_root() / "ToolkitUserFiles", remote_toolkit_user_dir)
            if sync_options.get("toolkit_settings", False) and (workspace_root() / "ToolkitSettings").exists():
                upload_tree(sftp, workspace_root() / "ToolkitSettings", remote_toolkit_settings_dir)
        finally:
            sftp.close()
    finally:
        client.close()


def run_toolkit_command(
    target: dict[str, Any],
    settings: dict[str, Any],
    command: str,
    timeout_sec: int,
    remote_result_dir: str | Path,
) -> int:
    payload = {
        "mode": "command",
        "command": command,
        "timeout_sec": timeout_sec,
        "result_dir": str(remote_result_dir),
    }
    return invoke_toolkit(target, settings, payload, timeout_sec + 30)


def run_toolkit_fetch(
    target: dict[str, Any],
    settings: dict[str, Any],
    remote_path: str,
    local_name: str | None,
    remote_result_dir: str | Path,
) -> int:
    payload = {
        "mode": "fetch",
        "remote_path": remote_path,
        "local_name": local_name,
        "result_dir": str(remote_result_dir),
    }
    return invoke_toolkit(target, settings, payload, 60)


def invoke_toolkit(target: dict[str, Any], settings: dict[str, Any], payload: dict[str, Any], timeout_sec: int) -> int:
    payload_b64 = build_payload(payload)

    if target["executor_type"] == "local":
        invoke_script = workspace_root() / "Toolkit" / "invoke_remote.py"
        completed = subprocess.run(
            [sys.executable, str(invoke_script), "--payload-b64", payload_b64],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        return completed.returncode

    remote_python = settings["remote"]["python"]
    remote_invoke = posixpath.join(settings["remote"]["toolkit_dir"], "invoke_remote.py")
    command = f"{remote_python} {remote_invoke} --payload-b64 '{payload_b64}'"
    return run_ssh_command(target, command, timeout_sec)


def collect_results_from_target(
    target: dict[str, Any],
    remote_target_result_dir: str | Path,
    local_target_result_dir: Path,
) -> None:
    if target["executor_type"] == "local":
        source_dir = Path(remote_target_result_dir)
        local_target_result_dir.parent.mkdir(parents=True, exist_ok=True)
        local_target_result_dir.mkdir(parents=True, exist_ok=True)
        for item in source_dir.iterdir():
            destination = local_target_result_dir / item.name
            if item.is_dir():
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)
        return

    # SSH 目标的结果目录按运行生成，理论上是新的；如果本地已经有控制器生成的文件，
    # 这里保留本地目录，并把远端采集结果合并回来。
    local_target_result_dir.mkdir(parents=True, exist_ok=True)

    client = connect_ssh(target)
    try:
        sftp = client.open_sftp()
        try:
            download_tree(sftp, expand_remote_path(sftp, str(remote_target_result_dir)), local_target_result_dir)
        finally:
            sftp.close()
    finally:
        client.close()


def issue_power_cycle(target: dict[str, Any], provider: str, reconnect_timeout_sec: int) -> int:
    bmc = target.get("bmc") or {}
    if not bmc:
        print(f"[WARN] target {target['name']} is missing BMC settings")
        return 1

    if provider == "ipmi":
        completed = subprocess.run(
            [
                "ipmitool",
                "-I",
                "lanplus",
                "-H",
                bmc["address"],
                "-U",
                bmc["username"],
                "-P",
                bmc["password"],
                "chassis",
                "power",
                "cycle",
            ],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            print(completed.stderr)
            return completed.returncode
    else:
        result = issue_redfish_power_cycle(bmc)
        if result != 0:
            return result

    if target["executor_type"] == "local":
        return 0
    return 0 if wait_for_ssh(target["host"], int(target.get("port", 22)), reconnect_timeout_sec) else 1


def issue_redfish_power_cycle(bmc: dict[str, Any]) -> int:
    system_path = bmc.get("system_path", "/redfish/v1/Systems/System.Embedded.1")
    url = f"https://{bmc['address']}{system_path}/Actions/ComputerSystem.Reset"
    payload = b'{"ResetType":"PowerCycle"}'
    request = urllib.request.Request(url, data=payload, method="POST")
    request.add_header("Content-Type", "application/json")

    credentials = f"{bmc['username']}:{bmc['password']}".encode("utf-8")
    auth = base64.b64encode(credentials).decode("ascii")
    request.add_header("Authorization", f"Basic {auth}")

    ssl_context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, context=ssl_context, timeout=15):
            return 0
    except urllib.error.URLError as exc:
        print(exc)
        return 1


def wait_for_ssh(host: str, port: int, timeout_sec: int) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=5):
                return True
        except OSError:
            time.sleep(5)
    return False


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def connect_ssh(target: dict[str, Any]) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=target["host"],
        port=int(target.get("port", 22)),
        username=target.get("username") or None,
        password=target.get("password") or None,
        look_for_keys=False,
        allow_agent=False,
        timeout=10,
    )
    return client


def run_ssh_command(target: dict[str, Any], command: str, timeout_sec: int) -> int:
    client = connect_ssh(target)
    try:
        _, stdout, stderr = client.exec_command(command, timeout=timeout_sec)
        error_text = stderr.read().decode("utf-8", errors="replace")
        if error_text.strip():
            print(error_text)
        return stdout.channel.recv_exit_status()
    finally:
        client.close()


def upload_tree(sftp: paramiko.SFTPClient, local_dir: Path, remote_dir: str) -> None:
    ensure_remote_dir(sftp, remote_dir)
    for item in local_dir.iterdir():
        remote_path = posixpath.join(remote_dir, item.name)
        if item.is_dir():
            upload_tree(sftp, item, remote_path)
        else:
            sftp.put(str(item), remote_path)


def download_tree(sftp: paramiko.SFTPClient, remote_dir: str, local_dir: Path) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    for entry in sftp.listdir_attr(remote_dir):
        remote_path = posixpath.join(remote_dir, entry.filename)
        local_path = local_dir / entry.filename
        if stat.S_ISDIR(entry.st_mode):
            download_tree(sftp, remote_path, local_path)
        else:
            sftp.get(remote_path, str(local_path))


def ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    parts = remote_dir.split("/")
    current = ""
    for part in parts:
        if not part:
            continue
        current = f"{current}/{part}" if current else f"/{part}" if remote_dir.startswith("/") else part
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def expand_remote_path(sftp: paramiko.SFTPClient, remote_path: str) -> str:
    if remote_path == "~":
        return sftp.normalize(".")
    if remote_path.startswith("~/"):
        return posixpath.join(sftp.normalize("."), remote_path[2:])
    return remote_path


def write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "target_name",
        "phase",
        "test_name",
        "type",
        "status",
        "return_code",
        "result_directory",
        "message",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
