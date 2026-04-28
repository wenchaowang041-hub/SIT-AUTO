from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from Commands.run_linux_suite import run_linux_suite_with_details
    from Libraries.controller_lib import read_controller_settings, run_timestamp, write_json, workspace_root
except ModuleNotFoundError:
    from TestController.Commands.run_linux_suite import run_linux_suite_with_details
    from TestController.Libraries.controller_lib import read_controller_settings, run_timestamp, write_json, workspace_root


def run_master_suite(
    name: str,
    server_lists: list[str],
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
) -> int:
    return run_master_suite_with_details(
        name=name,
        server_lists=server_lists,
        skip_toolkit_sync=skip_toolkit_sync,
        skip_user_sync=skip_user_sync,
        skip_settings_sync=skip_settings_sync,
        stop_on_fail=stop_on_fail,
        runtime_variables=runtime_variables,
        skip_targets=skip_targets,
        target_names=target_names,
        labels_any=labels_any,
        exclude_labels=exclude_labels,
    )["total_failures"]


def run_master_suite_with_details(
    name: str,
    server_lists: list[str],
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
) -> dict[str, Any]:
    # 先做串行版 MasterSuite，重点是保留原框架的批量入口和批量结果汇总。
    settings = read_controller_settings()
    stamp = run_timestamp()
    master_root = ensure_master_result_dir(settings, name, stamp)

    rows: list[dict[str, object]] = []
    total_failures = 0
    run_details: list[dict[str, Any]] = []
    for server_list in server_lists:
        print(f"\n[MasterSuite] start server list: {server_list}")
        detail = run_linux_suite_with_details(
            name=name,
            server_list=server_list,
            skip_toolkit_sync=skip_toolkit_sync,
            skip_user_sync=skip_user_sync,
            skip_settings_sync=skip_settings_sync,
            stop_on_fail=stop_on_fail,
            runtime_variables=runtime_variables or {},
            skip_targets=skip_targets or set(),
            target_names=target_names or set(),
            labels_any=labels_any or set(),
            exclude_labels=exclude_labels or set(),
        )
        rows.append(
            {
                "server_list": server_list,
                "failures": detail["failures"],
                "status": "PASSED" if detail["failures"] == 0 else "FAILED",
                "result_root": detail["result_root"],
            }
        )
        run_details.append(detail)
        total_failures += int(detail["failures"])

    summary = {
        "suite_name": name,
        "run_id": stamp,
        "total_failures": total_failures,
        "rows": rows,
        "filters": {
            "skip_targets": sorted(skip_targets or set()),
            "target_names": sorted(target_names or set()),
            "labels_any": sorted(labels_any or set()),
            "exclude_labels": sorted(exclude_labels or set()),
        },
        "sync_options": {
            "toolkit": not skip_toolkit_sync,
            "toolkit_user": not skip_user_sync,
            "toolkit_settings": not skip_settings_sync,
        },
    }
    write_json(master_root / "master_summary.json", summary)
    return {
        **summary,
        "result_root": str(master_root),
        "runs": run_details,
    }


def ensure_master_result_dir(settings: dict[str, object], suite_name: str, stamp: str) -> Path:
    result_dir = settings["controller"]["results_dir"]  # type: ignore[index]
    path = workspace_root() / result_dir / "_master" / suite_name / f"MasterRun-{stamp}"
    path.mkdir(parents=True, exist_ok=True)
    return path
