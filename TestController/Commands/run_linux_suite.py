from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import shutil
from pathlib import Path
from typing import Any

try:
    from Libraries.controller_lib import (
        build_context,
        collect_results_from_target,
        command_should_stop,
        command_timeout,
        ensure_controller_result_dir,
        issue_power_cycle,
        load_data_file,
        local_runtime_result_dir,
        normalize_server_list,
        normalize_suite_definition,
        read_controller_settings,
        remote_runtime_result_dir,
        render_text,
        resolve_server_list_file,
        resolve_suite_file,
        run_timestamp,
        run_toolkit_command,
        run_toolkit_fetch,
        sync_setting_enabled,
        sync_toolkit_if_needed,
        write_json,
        write_summary_csv,
    )
except ModuleNotFoundError:
    from TestController.Libraries.controller_lib import (
        build_context,
        collect_results_from_target,
        command_should_stop,
        command_timeout,
        ensure_controller_result_dir,
        issue_power_cycle,
        load_data_file,
        local_runtime_result_dir,
        normalize_server_list,
        normalize_suite_definition,
        read_controller_settings,
        remote_runtime_result_dir,
        render_text,
        resolve_server_list_file,
        resolve_suite_file,
        run_timestamp,
        run_toolkit_command,
        run_toolkit_fetch,
        sync_setting_enabled,
        sync_toolkit_if_needed,
        write_json,
        write_summary_csv,
    )


def run_linux_suite(
    name: str,
    server_list: str,
    *,
    skip_toolkit_sync: bool = False,
    skip_user_sync: bool = False,
    skip_settings_sync: bool = False,
    stop_on_fail: bool | None = None,
    runtime_variables: dict[str, Any] | None = None,
    skip_targets: set[str] | None = None,
    target_names: set[str] | None = None,
    labels_any: set[str] | None = None,
    exclude_labels: set[str] | None = None,
    max_workers: int = 1,
) -> int:
    return run_linux_suite_with_details(
        name=name,
        server_list=server_list,
        skip_toolkit_sync=skip_toolkit_sync,
        skip_user_sync=skip_user_sync,
        skip_settings_sync=skip_settings_sync,
        stop_on_fail=stop_on_fail,
        runtime_variables=runtime_variables,
        skip_targets=skip_targets,
        target_names=target_names,
        labels_any=labels_any,
        exclude_labels=exclude_labels,
        max_workers=max_workers,
    )["failures"]


def run_linux_suite_with_details(
    name: str,
    server_list: str,
    *,
    skip_toolkit_sync: bool = False,
    skip_user_sync: bool = False,
    skip_settings_sync: bool = False,
    stop_on_fail: bool | None = None,
    runtime_variables: dict[str, Any] | None = None,
    skip_targets: set[str] | None = None,
    target_names: set[str] | None = None,
    labels_any: set[str] | None = None,
    exclude_labels: set[str] | None = None,
    max_workers: int = 1,
) -> dict[str, Any]:
    # 这一层对应旧平台的 Run-WcsSuite：读套件、读 server list、执行阶段、回收结果、写摘要。
    if max_workers < 1:
        raise ValueError("max_workers must be >= 1")

    settings = read_controller_settings()
    suite = normalize_suite_definition(load_data_file(resolve_suite_file(name)), name)
    servers = normalize_server_list(load_data_file(resolve_server_list_file(server_list)), server_list)
    settings = merge_runtime_settings(settings, suite=suite, server_list=servers)
    sync_options = build_sync_options(
        settings=settings,
        suite=suite,
        skip_toolkit_sync=skip_toolkit_sync,
        skip_user_sync=skip_user_sync,
        skip_settings_sync=skip_settings_sync,
    )
    stamp = run_timestamp()

    result_root = ensure_controller_result_dir(settings, name, stamp)
    controller_log = result_root / "controller.log"
    controller_log.write_text("", encoding="utf-8")

    summary_rows: list[dict[str, Any]] = []
    runtime_variables = runtime_variables or {}
    skip_targets = skip_targets or set()
    target_names = target_names or set()
    labels_any = labels_any or set()
    exclude_labels = exclude_labels or set()

    run_manifest = {
        "suite": {
            "name": suite["name"],
            "description": suite["description"],
            "metadata": suite["metadata"],
        },
        "server_list": {
            "name": servers["name"],
            "description": servers["description"],
        },
        "run_id": stamp,
        "targets": [target["name"] for target in servers["targets"]],
        "filters": {
            "skip_targets": sorted(skip_targets),
            "target_names": sorted(target_names),
            "labels_any": sorted(labels_any),
            "exclude_labels": sorted(exclude_labels),
        },
        "sync_options": sync_options,
        "max_workers": max_workers,
    }
    write_json(result_root / "run_manifest.json", run_manifest)

    target_results: dict[int, dict[str, Any]] = {}
    executable_targets: list[tuple[int, dict[str, Any]]] = []
    for index, target in enumerate(servers["targets"]):
        target_name = target["name"]
        skip_reason = target_skip_reason(
            target=target,
            skip_targets=skip_targets,
            target_names=target_names,
            labels_any=labels_any,
            exclude_labels=exclude_labels,
        )
        if skip_reason:
            print(f"\n[Target] {target_name} SKIPPED")
            append_log(controller_log, f"[Target] {target_name} SKIPPED: {skip_reason}")
            target_results[index] = build_skipped_target_result(target_name, skip_reason)
            continue

        executable_targets.append((index, target))

    if max_workers == 1 or len(executable_targets) <= 1:
        for index, target in executable_targets:
            target_results[index] = execute_target(
                target=target,
                suite=suite,
                servers=servers,
                settings=settings,
                sync_options=sync_options,
                stamp=stamp,
                result_root=result_root,
                runtime_variables=runtime_variables,
                stop_on_fail=stop_on_fail,
                controller_log=controller_log,
            )
    else:
        worker_count = min(max_workers, len(executable_targets))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    execute_target,
                    target=target,
                    suite=suite,
                    servers=servers,
                    settings=settings,
                    sync_options=sync_options,
                    stamp=stamp,
                    result_root=result_root,
                    runtime_variables=runtime_variables,
                    stop_on_fail=stop_on_fail,
                    controller_log=controller_log,
                ): index
                for index, target in executable_targets
            }
            for future in as_completed(futures):
                target_results[futures[future]] = future.result()

    for index in sorted(target_results):
        summary_rows.extend(target_results[index]["rows"])

    total_failures = sum(1 for row in summary_rows if row["status"] == "FAILED")
    summary_payload = {
        "run_id": stamp,
        "suite_name": suite["name"],
        "server_list_name": servers["name"],
        "failures": total_failures,
        "rows": summary_rows,
        "max_workers": max_workers,
    }
    write_summary_csv(result_root / "summary.csv", summary_rows)
    write_json(result_root / "summary.json", summary_payload)

    return {
        "run_id": stamp,
        "suite_name": suite["name"],
        "server_list_name": servers["name"],
        "failures": total_failures,
        "summary_rows": summary_rows,
        "result_root": str(result_root),
        "run_manifest": run_manifest,
        "summary": summary_payload,
    }


def execute_target(
    *,
    target: dict[str, Any],
    suite: dict[str, Any],
    servers: dict[str, Any],
    settings: dict[str, Any],
    sync_options: dict[str, bool],
    stamp: str,
    result_root: Path,
    runtime_variables: dict[str, Any],
    stop_on_fail: bool | None,
    controller_log: Path,
) -> dict[str, Any]:
    target_name = target["name"]
    target_result_root = result_root / target_name
    rows: list[dict[str, Any]] = []
    target_failed = False

    try:
        print(f"\n[Target] {target_name}")
        append_log(controller_log, f"[Target] {target_name}")

        runtime_target_dir = (
            local_runtime_result_dir(stamp, target_name)
            if target["executor_type"] == "local"
            else remote_runtime_result_dir(settings, stamp, target_name)
        )

        if any(sync_options.values()):
            sync_toolkit_if_needed(target, settings, sync_options)

        phases = [
            ("pre_test", suite["pre_test_commands"]),
            ("test", suite["test_commands"]),
            ("post_test", suite["post_test_commands"]),
        ]

        target_failed = False
        skip_main_test_phases = False
        for phase_name, commands in phases:
            if not commands:
                continue
            if skip_main_test_phases and phase_name != "post_test":
                append_log(controller_log, f"  [Skip] {phase_name} skipped because a previous phase failed")
                continue
            phase_failed, phase_rows = execute_phase(
                phase_name=phase_name,
                commands=commands,
                suite=suite,
                servers=servers,
                settings=settings,
                target=target,
                stamp=stamp,
                runtime_variables=runtime_variables,
                runtime_target_dir=runtime_target_dir,
                local_target_dir=target_result_root,
                explicit_stop=stop_on_fail,
                controller_log=controller_log,
            )
            rows.extend(phase_rows)
            if phase_failed:
                target_failed = True
                if phase_name != "post_test":
                    skip_main_test_phases = True

        collect_results_from_target(target, runtime_target_dir, target_result_root)
        if target["executor_type"] == "local":
            cleanup_local_runtime_dir(Path(runtime_target_dir), controller_log)

        print(f"  [Result] {target_name} {'FAILED' if target_failed else 'PASSED'}")
        append_log(controller_log, f"  [Result] {target_name} {'FAILED' if target_failed else 'PASSED'}")
    except Exception as exc:
        target_failed = True
        target_result_root.mkdir(parents=True, exist_ok=True)
        message = f"{type(exc).__name__}: {exc}"
        write_json(
            target_result_root / "target_error.json",
            {
                "target_name": target_name,
                "error": message,
            },
        )
        append_log(controller_log, f"  [Result] {target_name} FAILED: {message}")
        rows.append(
            {
                "target_name": target_name,
                "phase": "target",
                "test_name": "TARGET-ERROR",
                "type": "target_error",
                "status": "FAILED",
                "return_code": 1,
                "result_directory": str(target_result_root),
                "message": message,
            }
        )

    return {
        "target_name": target_name,
        "failed": target_failed,
        "rows": rows,
    }


def build_skipped_target_result(target_name: str, skip_reason: str) -> dict[str, Any]:
    return {
        "target_name": target_name,
        "failed": False,
        "rows": [
            {
                "target_name": target_name,
                "phase": "target",
                "test_name": "SKIPPED",
                "type": "skip",
                "status": "SKIPPED",
                "return_code": 0,
                "result_directory": "",
                "message": skip_reason,
            }
        ],
    }


def cleanup_local_runtime_dir(path: Path, controller_log: Path) -> None:
    if not path.exists():
        return
    try:
        shutil.rmtree(path)
    except OSError as exc:
        append_log(controller_log, f"  [Warn] failed to clean local runtime directory {path}: {exc}")


def execute_phase(
    *,
    phase_name: str,
    commands: list[dict[str, Any]],
    suite: dict[str, Any],
    servers: dict[str, Any],
    settings: dict[str, Any],
    target: dict[str, Any],
    stamp: str,
    runtime_variables: dict[str, Any],
    runtime_target_dir: str | Path,
    local_target_dir: Path,
    explicit_stop: bool | None,
    controller_log: Path,
) -> tuple[bool, list[dict[str, Any]]]:
    phase_failed = False
    phase_rows: list[dict[str, Any]] = []

    for command in commands:
        test_name = command["test"]
        command_type = command["type"].lower()
        append_log(controller_log, f"  [Step] {phase_name}::{test_name} ({command_type})")
        print(f"  [Step] {phase_name}::{test_name} ({command_type})")
        phase_result_name = f"{phase_name}-{test_name}"

        context = build_context(
            target=target,
            stamp=stamp,
            local_result_dir=local_target_dir,
            suite=suite,
            server_list=servers,
            settings=settings,
            phase=phase_name,
            test_name=test_name,
            runtime_variables=runtime_variables,
        )

        if not command_is_enabled(command, context):
            append_log(controller_log, "    command skipped by condition or target selector")
            phase_rows.append(
                {
                    "target_name": target["name"],
                    "phase": phase_name,
                    "test_name": test_name,
                    "type": command_type,
                    "status": "SKIPPED",
                    "return_code": 0,
                    "result_directory": "",
                    "message": "command skipped by condition or target selector",
                }
            )
            continue

        step_result_dir = (
            runtime_target_dir / phase_result_name
            if isinstance(runtime_target_dir, Path)
            else f"{runtime_target_dir}/{phase_result_name}"
        )

        return_code = run_single_command(
            command=command,
            command_type=command_type,
            target=target,
            settings=settings,
            context=context,
            step_result_dir=step_result_dir,
            local_step_result_dir=local_target_dir / phase_result_name,
            suite_defaults=suite["defaults"],
        )

        status = "PASSED" if return_code == 0 else "FAILED"
        phase_rows.append(
            {
                "target_name": target["name"],
                "phase": phase_name,
                "test_name": test_name,
                "type": command_type,
                "status": status,
                "return_code": return_code,
                "result_directory": str(local_target_dir / phase_result_name),
                "message": "",
            }
        )
        append_log(controller_log, f"    return_code={return_code}")

        if return_code != 0:
            phase_failed = True
            if command_should_stop(command, suite["defaults"], explicit_stop):
                append_log(controller_log, "    stop_on_fail triggered; remaining steps on this target are skipped")
                break

    return phase_failed, phase_rows


def run_single_command(
    *,
    command: dict[str, Any],
    command_type: str,
    target: dict[str, Any],
    settings: dict[str, Any],
    context: dict[str, Any],
    step_result_dir: str | Path,
    local_step_result_dir: Path,
    suite_defaults: dict[str, Any],
) -> int:
    if command_type == "command":
        return run_toolkit_command(
            target=target,
            settings=settings,
            command=render_text(command["command"], context),
            timeout_sec=command_timeout(command, suite_defaults),
            remote_result_dir=step_result_dir,
        )

    if command_type == "fetch":
        return run_toolkit_fetch(
            target=target,
            settings=settings,
            remote_path=render_text(command["remote_path"], context),
            local_name=command.get("local_name"),
            remote_result_dir=step_result_dir,
        )

    if command_type == "power_cycle":
        return_code = issue_power_cycle(
            target=target,
            provider=command.get("provider", "ipmi"),
            reconnect_timeout_sec=int(command.get("reconnect_timeout_sec", 600)),
        )
        write_json(
            local_step_result_dir / "metadata.json",
            {
                "mode": "power_cycle",
                "target": target["name"],
                "provider": command.get("provider", "ipmi"),
                "return_code": return_code,
            },
        )
        return return_code

    raise ValueError(f"unsupported step type: {command_type}")


def append_log(log_path: Path, line: str) -> None:
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def command_is_enabled(command: dict[str, Any], context: dict[str, Any]) -> bool:
    if not command.get("enabled", True):
        return False
    if not matches_target_selector(command, context):
        return False
    if "when" not in command:
        return True
    rendered = render_text(str(command["when"]), context).strip().lower()
    return rendered in {"1", "true", "yes", "on"}


def matches_target_selector(command: dict[str, Any], context: dict[str, Any]) -> bool:
    target_info = context.get("target", {})
    target_name = str(target_info.get("name", ""))
    target_labels = set(target_info.get("labels", []))

    selected_target_names = set(command.get("target_names", []))
    if selected_target_names and target_name not in selected_target_names:
        return False

    excluded_target_names = set(command.get("exclude_target_names", []))
    if target_name in excluded_target_names:
        return False

    labels_any = set(command.get("target_labels_any", []))
    if labels_any and not target_labels.intersection(labels_any):
        return False

    labels_all = set(command.get("target_labels_all", []))
    if labels_all and not labels_all.issubset(target_labels):
        return False

    excluded_labels = set(command.get("exclude_target_labels", []))
    if excluded_labels and target_labels.intersection(excluded_labels):
        return False

    return True


def target_skip_reason(
    *,
    target: dict[str, Any],
    skip_targets: set[str],
    target_names: set[str],
    labels_any: set[str],
    exclude_labels: set[str],
) -> str | None:
    target_name = target["name"]
    target_labels = set(target.get("labels", []))

    if target_name in skip_targets:
        return "target skipped by --skip-targets"
    if target_names and target_name not in target_names:
        return "target not selected by --targets"
    if labels_any and not target_labels.intersection(labels_any):
        return "target labels do not match --labels"
    if exclude_labels and target_labels.intersection(exclude_labels):
        return "target excluded by --exclude-labels"
    return None


def build_sync_options(
    *,
    settings: dict[str, Any],
    suite: dict[str, Any],
    skip_toolkit_sync: bool,
    skip_user_sync: bool,
    skip_settings_sync: bool,
) -> dict[str, bool]:
    controller_defaults = settings["controller"]
    suite_defaults = suite["defaults"]
    return {
        "toolkit": not skip_toolkit_sync and sync_setting_enabled("sync_toolkit", suite_defaults, controller_defaults),
        "toolkit_user": not skip_user_sync
        and sync_setting_enabled("sync_toolkit_user", suite_defaults, controller_defaults),
        "toolkit_settings": not skip_settings_sync
        and sync_setting_enabled("sync_toolkit_settings", suite_defaults, controller_defaults),
    }


def merge_runtime_settings(base_settings: dict[str, Any], *, suite: dict[str, Any], server_list: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(base_settings))
    if suite.get("settings"):
        merged = deep_merge_local(merged, suite["settings"])
    if server_list.get("settings"):
        merged = deep_merge_local(merged, server_list["settings"])
    return merged


def deep_merge_local(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_local(merged[key], value)
        else:
            merged[key] = value
    return merged
