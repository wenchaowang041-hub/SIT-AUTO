from TestController.Commands.parse_results import parse_results
from TestController.Commands.run_linux_suite import run_linux_suite_with_details
from TestController.Commands.run_plan import run_plan_with_details
from TestController.Commands.validate_platform import check_environment, validate_plan, validate_server_list, validate_suite


def test_controller_validation_commands_pass_for_local_assets():
    assert check_environment()["status"] == "PASSED"
    assert validate_suite("linux_smoke")["status"] == "PASSED"
    assert validate_server_list("local_json_demo")["status"] == "PASSED"
    assert validate_plan("local_trial")["status"] == "PASSED"


def test_run_suite_with_details_and_parse_results():
    detail = run_linux_suite_with_details(
        name="controller_smoke",
        server_list="local_json_demo",
        skip_toolkit_sync=True,
        skip_user_sync=True,
        skip_settings_sync=True,
        labels_any={"json"},
    )
    assert detail["failures"] == 0

    report = parse_results(suite_name="controller_smoke")
    assert report["overall_status"] == "PASSED"


def test_run_suite_supports_parallel_targets():
    detail = run_linux_suite_with_details(
        name="controller_smoke",
        server_list="local_json_demo",
        skip_toolkit_sync=True,
        skip_user_sync=True,
        skip_settings_sync=True,
        labels_any={"json"},
        max_workers=2,
    )
    assert detail["failures"] == 0
    assert detail["run_manifest"]["max_workers"] == 2
    assert detail["summary"]["max_workers"] == 2


def test_run_plan_and_parse_plan_results():
    detail = run_plan_with_details(name="local_trial")
    assert detail["total_failures"] == 0

    report = parse_results(plan_name="local_trial")
    assert report["overall_status"] == "PASSED"
