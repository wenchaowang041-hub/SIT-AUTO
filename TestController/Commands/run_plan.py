from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from Commands.run_linux_suite import run_linux_suite_with_details
    from Commands.run_master_suite import run_master_suite_with_details
    from Libraries.controller_lib import read_controller_settings, run_timestamp, write_json, workspace_root
    from Libraries.plan_lib import load_plan
except ModuleNotFoundError:
    from TestController.Commands.run_linux_suite import run_linux_suite_with_details
    from TestController.Commands.run_master_suite import run_master_suite_with_details
    from TestController.Libraries.controller_lib import read_controller_settings, run_timestamp, write_json, workspace_root
    from TestController.Libraries.plan_lib import load_plan


def run_plan(
    name: str,
    *,
    runtime_variables: dict[str, Any] | None = None,
    max_workers: int | None = None,
) -> int:
    return run_plan_with_details(name=name, runtime_variables=runtime_variables, max_workers=max_workers)["total_failures"]


def run_plan_with_details(
    name: str,
    *,
    runtime_variables: dict[str, Any] | None = None,
    max_workers: int | None = None,
) -> dict[str, Any]:
    plan = load_plan(name)
    settings = read_controller_settings()
    stamp = run_timestamp()
    result_root = ensure_plan_result_dir(settings, plan["name"], stamp)

    rows: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    total_failures = 0

    for run_definition in plan["runs"]:
        run_workers = int(max_workers if max_workers is not None else run_definition.get("jobs", 1))
        merged_runtime_variables = dict(run_definition.get("runtime_variables", {}))
        merged_runtime_variables.update(runtime_variables or {})

        common_args = {
            "name": run_definition["suite"],
            "skip_toolkit_sync": bool(run_definition.get("skip_toolkit_sync", False)),
            "skip_user_sync": bool(run_definition.get("skip_user_sync", False)),
            "skip_settings_sync": bool(run_definition.get("skip_settings_sync", False)),
            "stop_on_fail": run_definition.get("stop_on_fail"),
            "runtime_variables": merged_runtime_variables,
            "skip_targets": set(run_definition.get("skip_targets", [])),
            "target_names": set(run_definition.get("target_names", [])),
            "labels_any": set(run_definition.get("labels_any", [])),
            "exclude_labels": set(run_definition.get("exclude_labels", [])),
            "max_workers": run_workers,
        }

        if len(run_definition["server_lists"]) == 1:
            detail = run_linux_suite_with_details(
                server_list=run_definition["server_lists"][0],
                **common_args,
            )
            execution_mode = "suite"
            failures = int(detail["failures"])
        else:
            detail = run_master_suite_with_details(
                server_lists=run_definition["server_lists"],
                **common_args,
            )
            execution_mode = "master_suite"
            failures = int(detail["total_failures"])

        run_row = {
            "index": run_definition["index"],
            "suite": run_definition["suite"],
            "server_lists": run_definition["server_lists"],
            "execution_mode": execution_mode,
            "failures": failures,
            "status": "PASSED" if failures == 0 else "FAILED",
            "result_root": detail["result_root"],
            "jobs": run_workers,
        }
        rows.append(run_row)
        runs.append(detail)
        total_failures += failures

    summary = {
        "plan_name": plan["name"],
        "description": plan["description"],
        "run_id": stamp,
        "total_failures": total_failures,
        "rows": rows,
    }
    write_json(result_root / "plan_summary.json", summary)
    write_json(result_root / "plan_runs.json", runs)
    return {
        **summary,
        "result_root": str(result_root),
        "runs": runs,
    }


def ensure_plan_result_dir(settings: dict[str, Any], plan_name: str, stamp: str) -> Path:
    path = workspace_root() / settings["controller"]["results_dir"] / "_plans" / plan_name / f"PlanRun-{stamp}"
    path.mkdir(parents=True, exist_ok=True)
    return path
