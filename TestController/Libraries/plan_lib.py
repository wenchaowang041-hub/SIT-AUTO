from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from Libraries.controller_lib import (
        deep_merge,
        list_named_entries,
        load_data_file,
        resolve_named_file,
        workspace_root,
    )
except ModuleNotFoundError:
    from TestController.Libraries.controller_lib import (
        deep_merge,
        list_named_entries,
        load_data_file,
        resolve_named_file,
        workspace_root,
    )


def plan_directories() -> list[Path]:
    return [
        workspace_root() / "TestControllerUserFiles" / "Plans",
        workspace_root() / "TestController" / "Plans",
    ]


def resolve_plan_file(name: str) -> Path:
    try:
        return resolve_named_file(name, plan_directories())
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"plan file was not found: {name}") from exc


def list_plan_names() -> list[str]:
    return list_named_entries(*plan_directories())


def load_plan(name: str) -> dict[str, Any]:
    raw_plan = load_data_file(resolve_plan_file(name))
    return normalize_plan_definition(raw_plan, name)


def normalize_plan_definition(raw_plan: dict[str, Any], plan_name: str) -> dict[str, Any]:
    defaults = {
        "skip_toolkit_sync": False,
        "skip_user_sync": False,
        "skip_settings_sync": False,
        "stop_on_fail": None,
        "runtime_variables": {},
        "skip_targets": [],
        "target_names": [],
        "labels_any": [],
        "exclude_labels": [],
    }
    defaults = deep_merge(defaults, raw_plan.get("defaults", {}))

    runs: list[dict[str, Any]] = []
    for index, raw_run in enumerate(raw_plan.get("runs", []), start=1):
        normalized = deep_merge(defaults, raw_run)
        normalized["index"] = index
        normalized["server_lists"] = normalize_server_list_selection(normalized)
        runs.append(normalized)

    return {
        "name": plan_name,
        "description": raw_plan.get("description", ""),
        "defaults": defaults,
        "runs": runs,
    }


def normalize_server_list_selection(run_definition: dict[str, Any]) -> list[str]:
    if run_definition.get("server_lists"):
        return list(run_definition["server_lists"])
    if run_definition.get("server_list"):
        return [str(run_definition["server_list"])]
    return []
