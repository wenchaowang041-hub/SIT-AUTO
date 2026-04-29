from __future__ import annotations

import base64
import importlib
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from Libraries.controller_lib import (
        connect_ssh,
        load_data_file,
        normalize_server_list,
        normalize_suite_definition,
        read_controller_settings,
        resolve_server_list_file,
        resolve_suite_file,
        run_timestamp,
        write_json,
        workspace_root,
    )
    from Libraries.plan_lib import load_plan, resolve_plan_file
except ModuleNotFoundError:
    from TestController.Libraries.controller_lib import (
        connect_ssh,
        load_data_file,
        normalize_server_list,
        normalize_suite_definition,
        read_controller_settings,
        resolve_server_list_file,
        resolve_suite_file,
        run_timestamp,
        write_json,
        workspace_root,
    )
    from TestController.Libraries.plan_lib import load_plan, resolve_plan_file

SUPPORTED_STEP_TYPES = {"command", "fetch", "power_cycle"}


def check_environment() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    results.append(check_python_version())
    results.extend(check_python_modules(["yaml", "paramiko"]))
    results.extend(check_workspace_paths())
    results.extend(check_external_commands(["ipmitool"]))
    return finalize_report("environment", "local-controller", results)


def validate_suite(name: str) -> dict[str, Any]:
    suite = normalize_suite_definition(load_data_file(resolve_suite_file(name)), name)
    results: list[dict[str, Any]] = []

    for phase_name in ("pre_test_commands", "test_commands", "post_test_commands"):
        commands = suite.get(phase_name, [])
        if not isinstance(commands, list):
            results.append(report_item("ERROR", f"{phase_name} must be a list"))
            continue
        for index, command in enumerate(commands, start=1):
            prefix = f"{phase_name}[{index}]"
            results.extend(validate_suite_command(prefix, command))

    if not suite["test_commands"]:
        results.append(report_item("WARN", "suite has no test_commands"))

    report = finalize_report("suite", name, results)
    report["suite"] = suite
    return report


def validate_server_list(name: str, *, probe_ssh: bool = False, probe_bmc: bool = False) -> dict[str, Any]:
    settings = read_controller_settings()
    server_list = normalize_server_list(load_data_file(resolve_server_list_file(name)), name)
    results: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    if not server_list["targets"]:
        results.append(report_item("ERROR", "server list has no targets"))

    for index, target in enumerate(server_list["targets"], start=1):
        target_prefix = f"target[{index}]"
        target_name = str(target.get("name", ""))
        if not target_name:
            results.append(report_item("ERROR", f"{target_prefix} is missing name"))
        elif target_name in seen_names:
            results.append(report_item("ERROR", f"{target_prefix} has duplicate name: {target_name}"))
        else:
            seen_names.add(target_name)

        executor_type = target.get("executor_type")
        if executor_type not in {"local", "ssh"}:
            results.append(report_item("ERROR", f"{target_prefix} uses unsupported executor_type: {executor_type}"))

        if executor_type == "ssh":
            if not target.get("host"):
                results.append(report_item("ERROR", f"{target_prefix} is missing host"))
            if not target.get("username"):
                results.append(report_item("WARN", f"{target_prefix} has no username; SSH may fail"))
            if probe_ssh and target.get("host"):
                results.append(probe_ssh_target(target, settings["remote"]["python"]))
        elif executor_type == "local":
            results.append(report_item("INFO", f"{target_prefix} uses local executor"))

        if target.get("bmc"):
            provider = target["bmc"].get("provider", "ipmi")
            if provider not in {"ipmi", "redfish"}:
                results.append(report_item("ERROR", f"{target_prefix} has unsupported BMC provider: {provider}"))
            elif probe_bmc:
                results.append(probe_bmc_target(target))

    report = finalize_report("server_list", name, results)
    report["server_list"] = server_list
    return report


def validate_plan(name: str) -> dict[str, Any]:
    plan = load_plan(name)
    results: list[dict[str, Any]] = []

    if not plan["runs"]:
        results.append(report_item("ERROR", "plan has no runs"))

    for run_definition in plan["runs"]:
        index = run_definition["index"]
        if not run_definition.get("suite"):
            results.append(report_item("ERROR", f"run[{index}] is missing suite"))
        else:
            try:
                resolve_suite_file(str(run_definition["suite"]))
            except FileNotFoundError as exc:
                results.append(report_item("ERROR", f"run[{index}] suite not found: {exc}"))

        if not run_definition["server_lists"]:
            results.append(report_item("ERROR", f"run[{index}] must define server_list or server_lists"))
        else:
            for server_list_name in run_definition["server_lists"]:
                try:
                    resolve_server_list_file(str(server_list_name))
                except FileNotFoundError as exc:
                    results.append(report_item("ERROR", f"run[{index}] server list not found: {exc}"))

    report = finalize_report("plan", name, results)
    report["plan"] = plan
    report["plan_file"] = str(resolve_plan_file(name))
    return report


def run_preflight(
    *,
    suite_name: str,
    server_list_name: str,
    probe_ssh: bool = False,
    probe_bmc: bool = False,
) -> dict[str, Any]:
    environment_report = check_environment()
    suite_report = validate_suite(suite_name)
    server_list_report = validate_server_list(server_list_name, probe_ssh=probe_ssh, probe_bmc=probe_bmc)

    results = environment_report["results"] + suite_report["results"] + server_list_report["results"]
    report = finalize_report("preflight", f"{suite_name}:{server_list_name}", results)
    report["environment"] = environment_report
    report["suite"] = suite_report
    report["server_list"] = server_list_report

    diagnostic_dir = workspace_root() / "Results" / "_diagnostics"
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    report_path = diagnostic_dir / f"preflight-{suite_name}-{server_list_name}-{run_timestamp()}.json"
    report["report_path"] = str(report_path)
    write_json(report_path, report)
    return report


def check_python_version() -> dict[str, Any]:
    if sys.version_info >= (3, 11):
        return report_item("OK", f"python version is {sys.version.split()[0]}")
    return report_item("ERROR", f"python 3.11+ is required, current is {sys.version.split()[0]}")


def check_python_modules(module_names: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for module_name in module_names:
        try:
            importlib.import_module(module_name)
            results.append(report_item("OK", f"python module is available: {module_name}"))
        except Exception as exc:  # pragma: no cover - defensive
            results.append(report_item("ERROR", f"python module import failed: {module_name}: {exc}"))
    return results


def check_workspace_paths() -> list[dict[str, Any]]:
    required_paths = [
        workspace_root() / "TestController",
        workspace_root() / "TestController" / "UserFiles" / "ServerLists",
        workspace_root() / "Toolkit",
        workspace_root() / "Toolkit" / "Settings" / "user-settings.json",
    ]
    results: list[dict[str, Any]] = []
    for path in required_paths:
        if path.exists():
            results.append(report_item("OK", f"path exists: {path}"))
        else:
            results.append(report_item("ERROR", f"path missing: {path}"))
    return results


def check_external_commands(command_names: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for command_name in command_names:
        resolved = shutil.which(command_name)
        if resolved:
            results.append(report_item("OK", f"external command is available: {command_name} -> {resolved}"))
        else:
            results.append(report_item("WARN", f"external command not found: {command_name}"))
    return results


def validate_suite_command(prefix: str, command: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if not isinstance(command, dict):
        return [report_item("ERROR", f"{prefix} must be a mapping")]

    if not command.get("test"):
        results.append(report_item("ERROR", f"{prefix} is missing test"))

    command_type = str(command.get("type", "")).lower()
    if command_type not in SUPPORTED_STEP_TYPES:
        results.append(report_item("ERROR", f"{prefix} has unsupported type: {command_type}"))
        return results

    if command_type == "command" and not command.get("command"):
        results.append(report_item("ERROR", f"{prefix} command step is missing command"))
    if command_type == "fetch" and not command.get("remote_path"):
        results.append(report_item("ERROR", f"{prefix} fetch step is missing remote_path"))
    if command_type == "power_cycle" and not command.get("provider"):
        results.append(report_item("WARN", f"{prefix} power_cycle step did not specify provider; default ipmi will be used"))

    if not results:
        results.append(report_item("OK", f"{prefix} passed validation"))
    return results


def probe_ssh_target(target: dict[str, Any], remote_python: str) -> dict[str, Any]:
    target_name = target["name"]
    try:
        client = connect_ssh(target)
        try:
            _, stdout, stderr = client.exec_command(f"{remote_python} --version", timeout=15)
            exit_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode("utf-8", errors="replace").strip()
            error_output = stderr.read().decode("utf-8", errors="replace").strip()
            if exit_code == 0:
                message = output or error_output or f"{remote_python} --version succeeded"
                return report_item("OK", f"ssh probe passed for {target_name}: {message}")
            return report_item("ERROR", f"ssh probe failed for {target_name}: {error_output or output or exit_code}")
        finally:
            client.close()
    except Exception as exc:
        return report_item("ERROR", f"ssh probe failed for {target_name}: {exc}")


def probe_bmc_target(target: dict[str, Any]) -> dict[str, Any]:
    bmc = target.get("bmc") or {}
    provider = bmc.get("provider", "ipmi")
    if provider == "redfish":
        return probe_redfish_bmc(target["name"], bmc)
    return probe_ipmi_bmc(target["name"], bmc)


def probe_ipmi_bmc(target_name: str, bmc: dict[str, Any]) -> dict[str, Any]:
    if not shutil.which("ipmitool"):
        return report_item("WARN", f"ipmitool not installed; skipped IPMI probe for {target_name}")

    address = bmc.get("address")
    username = bmc.get("username")
    password = bmc.get("password")
    if not address or not username or not password:
        return report_item("ERROR", f"ipmi probe skipped for {target_name}: incomplete BMC credentials")

    completed = subprocess.run(
        [
            "ipmitool",
            "-I",
            "lanplus",
            "-H",
            address,
            "-U",
            username,
            "-P",
            password,
            "chassis",
            "power",
            "status",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if completed.returncode == 0:
        output = completed.stdout.strip() or "power status query succeeded"
        return report_item("OK", f"ipmi probe passed for {target_name}: {output}")
    return report_item("ERROR", f"ipmi probe failed for {target_name}: {completed.stderr.strip() or completed.stdout.strip()}")


def probe_redfish_bmc(target_name: str, bmc: dict[str, Any]) -> dict[str, Any]:
    address = bmc.get("address")
    username = bmc.get("username")
    password = bmc.get("password")
    if not address or not username or not password:
        return report_item("ERROR", f"redfish probe skipped for {target_name}: incomplete BMC credentials")

    credentials = f"{username}:{password}".encode("utf-8")
    auth = base64.b64encode(credentials).decode("ascii")
    request = urllib.request.Request(f"https://{address}/redfish/v1", method="GET")
    request.add_header("Authorization", f"Basic {auth}")
    ssl_context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, context=ssl_context, timeout=15) as response:
            return report_item("OK", f"redfish probe passed for {target_name}: HTTP {response.status}")
    except urllib.error.URLError as exc:
        return report_item("ERROR", f"redfish probe failed for {target_name}: {exc}")


def report_item(level: str, message: str) -> dict[str, str]:
    return {"level": level, "message": message}


def finalize_report(report_type: str, subject: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    errors = [item for item in results if item["level"] == "ERROR"]
    warnings = [item for item in results if item["level"] == "WARN"]
    status = "PASSED" if not errors else "FAILED"
    return {
        "type": report_type,
        "subject": subject,
        "status": status,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "results": results,
    }
