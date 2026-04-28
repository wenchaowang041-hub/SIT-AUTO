from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 直接把 TestController 根目录加入搜索路径，保留旧平台按目录组织脚本的使用方式。
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from Commands.parse_results import parse_results
    from Commands.run_linux_suite import run_linux_suite
    from Commands.run_master_suite import run_master_suite
    from Commands.run_plan import run_plan
    from Commands.validate_platform import check_environment, run_preflight, validate_plan, validate_server_list, validate_suite
    from Libraries.controller_lib import list_server_list_names, list_suite_names, read_version
    from Libraries.plan_lib import list_plan_names
except ModuleNotFoundError:
    from TestController.Commands.parse_results import parse_results
    from TestController.Commands.run_linux_suite import run_linux_suite
    from TestController.Commands.run_master_suite import run_master_suite
    from TestController.Commands.run_plan import run_plan
    from TestController.Commands.validate_platform import (
        check_environment,
        run_preflight,
        validate_plan,
        validate_server_list,
        validate_suite,
    )
    from TestController.Libraries.controller_lib import list_server_list_names, list_suite_names, read_version
    from TestController.Libraries.plan_lib import list_plan_names


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Linux Test Controller")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list-suites", help="列出测试套件")
    sub.add_parser("list-server-lists", help="列出服务器清单")
    sub.add_parser("list-plans", help="列出计划文件")
    sub.add_parser("check-environment", help="检查控制器本地环境")

    validate_suite_parser = sub.add_parser("validate-suite", help="检查测试套件定义")
    validate_suite_parser.add_argument("--name", required=True, help="测试套件名称")

    validate_server_list_parser = sub.add_parser("validate-server-list", help="检查服务器清单定义")
    validate_server_list_parser.add_argument("--name", required=True, help="服务器清单名称")
    validate_server_list_parser.add_argument("--probe-ssh", action="store_true", help="尝试 SSH 联通与远端 Python 探测")
    validate_server_list_parser.add_argument("--probe-bmc", action="store_true", help="尝试 BMC 联通探测")

    validate_plan_parser = sub.add_parser("validate-plan", help="检查计划文件定义")
    validate_plan_parser.add_argument("--name", required=True, help="计划文件名称")

    preflight_parser = sub.add_parser("preflight", help="做一轮试跑前联合检查")
    preflight_parser.add_argument("--suite", required=True, help="测试套件名称")
    preflight_parser.add_argument("--server-list", required=True, help="服务器清单名称")
    preflight_parser.add_argument("--probe-ssh", action="store_true", help="尝试 SSH 联通与远端 Python 探测")
    preflight_parser.add_argument("--probe-bmc", action="store_true", help="尝试 BMC 联通探测")

    run_parser = sub.add_parser("run-suite", help="在一个服务器清单上执行测试套件")
    run_parser.add_argument("--name", required=True, help="测试套件名称")
    run_parser.add_argument("--server-list", required=True, help="服务器清单名称")
    add_shared_run_arguments(run_parser)

    master_parser = sub.add_parser("run-master-suite", help="在多个服务器清单上批量执行测试套件")
    master_parser.add_argument("--name", required=True, help="测试套件名称")
    master_parser.add_argument("--server-lists", nargs="+", required=True, help="服务器清单名称列表")
    add_shared_run_arguments(master_parser)

    plan_parser = sub.add_parser("run-plan", help="按计划文件顺序执行多个套件/清单")
    plan_parser.add_argument("--name", required=True, help="计划文件名称")
    plan_parser.add_argument("--var", action="append", default=[], help="运行时变量，格式 KEY=VALUE")

    parse_parser = sub.add_parser("parse-results", help="解析最近一次结果并生成摘要")
    parse_scope = parse_parser.add_mutually_exclusive_group(required=True)
    parse_scope.add_argument("--run-dir", help="直接指定结果目录")
    parse_scope.add_argument("--suite", help="解析某个 suite 的最近一次 run")
    parse_scope.add_argument("--master-suite", help="解析某个 master suite 的最近一次 run")
    parse_scope.add_argument("--plan", help="解析某个 plan 的最近一次 run")
    parse_parser.add_argument("--json", action="store_true", help="以 JSON 输出解析结果")

    return parser


def add_shared_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--skip-toolkit-sync", action="store_true", help="跳过 Toolkit 同步")
    parser.add_argument("--skip-user-sync", action="store_true", help="跳过 ToolkitUserFiles 同步")
    parser.add_argument("--skip-settings-sync", action="store_true", help="跳过 ToolkitSettings 同步")
    parser.add_argument("--stop-on-fail", action="store_true", help="任一步失败后立即停止当前目标")
    parser.add_argument("--skip-targets", nargs="*", default=[], help="要跳过的 target 名称")
    parser.add_argument("--targets", nargs="*", default=[], help="只执行这些 target 名称")
    parser.add_argument("--labels", nargs="*", default=[], help="只执行带这些标签之一的 target")
    parser.add_argument("--exclude-labels", nargs="*", default=[], help="排除带这些标签的 target")
    parser.add_argument("--var", action="append", default=[], help="运行时变量，格式 KEY=VALUE")


def parse_runtime_variables(items: list[str]) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"invalid --var value: {item}")
        key, raw_value = item.split("=", 1)
        parsed[key] = coerce_value(raw_value)
    return parsed


def coerce_value(raw_value: str) -> object:
    lowered = raw_value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if raw_value.isdigit():
        return int(raw_value)
    return raw_value


def print_report(report: dict[str, object], *, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"status: {report.get('status', report.get('overall_status', 'UNKNOWN'))}")
    if "error_count" in report:
        print(f"errors: {report['error_count']}")
    if "warning_count" in report:
        print(f"warnings: {report['warning_count']}")
    if "counts" in report:
        print(f"counts: {report['counts']}")
    if "report_path" in report:
        print(f"report_path: {report['report_path']}")

    results = report.get("results")
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                print(f"[{item.get('level', 'INFO')}] {item.get('message', '')}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    print(f"Linux Test Controller Version: {read_version()}")
    try:
        if args.command == "list-suites":
            for item in list_suite_names():
                print(item)
            return 0

        if args.command == "list-server-lists":
            for item in list_server_list_names():
                print(item)
            return 0

        if args.command == "list-plans":
            for item in list_plan_names():
                print(item)
            return 0

        if args.command == "check-environment":
            report = check_environment()
            print_report(report)
            return 0 if report["status"] == "PASSED" else 1

        if args.command == "validate-suite":
            report = validate_suite(args.name)
            print_report(report)
            return 0 if report["status"] == "PASSED" else 1

        if args.command == "validate-server-list":
            report = validate_server_list(args.name, probe_ssh=args.probe_ssh, probe_bmc=args.probe_bmc)
            print_report(report)
            return 0 if report["status"] == "PASSED" else 1

        if args.command == "validate-plan":
            report = validate_plan(args.name)
            print_report(report)
            return 0 if report["status"] == "PASSED" else 1

        if args.command == "preflight":
            report = run_preflight(
                suite_name=args.suite,
                server_list_name=args.server_list,
                probe_ssh=args.probe_ssh,
                probe_bmc=args.probe_bmc,
            )
            print_report(report)
            return 0 if report["status"] == "PASSED" else 1

        if args.command == "run-suite":
            return run_linux_suite(
                name=args.name,
                server_list=args.server_list,
                skip_toolkit_sync=args.skip_toolkit_sync,
                skip_user_sync=args.skip_user_sync,
                skip_settings_sync=args.skip_settings_sync,
                stop_on_fail=True if args.stop_on_fail else None,
                runtime_variables=parse_runtime_variables(args.var),
                skip_targets=set(args.skip_targets),
                target_names=set(args.targets),
                labels_any=set(args.labels),
                exclude_labels=set(args.exclude_labels),
            )

        if args.command == "run-master-suite":
            return run_master_suite(
                name=args.name,
                server_lists=args.server_lists,
                skip_toolkit_sync=args.skip_toolkit_sync,
                skip_user_sync=args.skip_user_sync,
                skip_settings_sync=args.skip_settings_sync,
                stop_on_fail=True if args.stop_on_fail else None,
                runtime_variables=parse_runtime_variables(args.var),
                skip_targets=set(args.skip_targets),
                target_names=set(args.targets),
                labels_any=set(args.labels),
                exclude_labels=set(args.exclude_labels),
            )

        if args.command == "run-plan":
            return run_plan(name=args.name, runtime_variables=parse_runtime_variables(args.var))

        if args.command == "parse-results":
            report = parse_results(
                run_dir=args.run_dir,
                suite_name=args.suite,
                master_suite_name=args.master_suite,
                plan_name=args.plan,
            )
            print_report(report, as_json=args.json)
            return 0
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 2

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
