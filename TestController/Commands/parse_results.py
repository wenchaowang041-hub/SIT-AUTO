from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from Libraries.controller_lib import read_controller_settings, write_json, workspace_root
except ModuleNotFoundError:
    from TestController.Libraries.controller_lib import read_controller_settings, write_json, workspace_root


def parse_results(
    *,
    run_dir: str | None = None,
    suite_name: str | None = None,
    master_suite_name: str | None = None,
    plan_name: str | None = None,
) -> dict[str, Any]:
    target_dir = resolve_results_directory(
        run_dir=run_dir,
        suite_name=suite_name,
        master_suite_name=master_suite_name,
        plan_name=plan_name,
    )

    if (target_dir / "summary.json").exists():
        report = parse_suite_run(target_dir)
    elif (target_dir / "master_summary.json").exists():
        report = parse_master_run(target_dir)
    elif (target_dir / "plan_summary.json").exists():
        report = parse_plan_run(target_dir)
    else:
        raise FileNotFoundError(f"no summary file found under {target_dir}")

    write_json(target_dir / "parsed_summary.json", report)
    return report


def resolve_results_directory(
    *,
    run_dir: str | None,
    suite_name: str | None,
    master_suite_name: str | None,
    plan_name: str | None,
) -> Path:
    results_root = workspace_root() / read_controller_settings()["controller"]["results_dir"]

    if run_dir:
        return Path(run_dir)
    if suite_name:
        return newest_directory(results_root / suite_name)
    if master_suite_name:
        return newest_directory(results_root / "_master" / master_suite_name)
    if plan_name:
        return newest_directory(results_root / "_plans" / plan_name)
    raise ValueError("one of run_dir, suite_name, master_suite_name, or plan_name must be provided")


def newest_directory(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"results path not found: {path}")
    directories = [item for item in path.iterdir() if item.is_dir()]
    if not directories:
        raise FileNotFoundError(f"no result directories found under: {path}")
    return max(directories, key=lambda item: item.stat().st_mtime)


def parse_suite_run(run_dir: Path) -> dict[str, Any]:
    payload = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    rows = payload["rows"]

    counts = count_rows(rows)
    per_target: dict[str, dict[str, int]] = {}
    failed_steps: list[dict[str, Any]] = []
    for row in rows:
        target_name = row["target_name"]
        per_target.setdefault(target_name, {"PASSED": 0, "FAILED": 0, "SKIPPED": 0})
        per_target[target_name][row["status"]] += 1
        if row["status"] == "FAILED":
            failed_steps.append(
                {
                    "target_name": target_name,
                    "phase": row["phase"],
                    "test_name": row["test_name"],
                    "type": row["type"],
                    "result_directory": row["result_directory"],
                }
            )

    return {
        "kind": "suite",
        "run_directory": str(run_dir),
        "suite_name": payload["suite_name"],
        "server_list_name": payload["server_list_name"],
        "run_id": payload["run_id"],
        "overall_status": "PASSED" if counts["FAILED"] == 0 else "FAILED",
        "counts": counts,
        "per_target": per_target,
        "failed_steps": failed_steps,
    }


def parse_master_run(run_dir: Path) -> dict[str, Any]:
    payload = json.loads((run_dir / "master_summary.json").read_text(encoding="utf-8"))
    rows = payload["rows"]
    status_counts = count_status_rows(rows)
    failed_server_lists = [row for row in rows if row["status"] == "FAILED"]
    return {
        "kind": "master_suite",
        "run_directory": str(run_dir),
        "suite_name": payload["suite_name"],
        "run_id": payload["run_id"],
        "overall_status": "PASSED" if status_counts["FAILED"] == 0 else "FAILED",
        "counts": status_counts,
        "failed_server_lists": failed_server_lists,
        "rows": rows,
    }


def parse_plan_run(run_dir: Path) -> dict[str, Any]:
    payload = json.loads((run_dir / "plan_summary.json").read_text(encoding="utf-8"))
    rows = payload["rows"]
    status_counts = count_status_rows(rows)
    failed_runs = [row for row in rows if row["status"] == "FAILED"]
    return {
        "kind": "plan",
        "run_directory": str(run_dir),
        "plan_name": payload["plan_name"],
        "run_id": payload["run_id"],
        "overall_status": "PASSED" if status_counts["FAILED"] == 0 else "FAILED",
        "counts": status_counts,
        "failed_runs": failed_runs,
        "rows": rows,
    }


def count_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"PASSED": 0, "FAILED": 0, "SKIPPED": 0}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    counts["TOTAL"] = len(rows)
    return counts


def count_status_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"PASSED": 0, "FAILED": 0, "SKIPPED": 0}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    counts["TOTAL"] = len(rows)
    return counts
