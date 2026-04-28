# SIT-AUTO Linux 原框架版

这是当前主线项目。方向已经固定为“旧版 `TestController + Toolkit` 风格的 Linux 自动化平台”，不是 Web 控制面板。

如果明天在公司另一台电脑继续做，先读这份文件，再读：

1. [LINUX_QUICKSTART.md](C:/Users/72785/Desktop/SIT-AUTO/docs/LINUX_QUICKSTART.md)
2. [VERSION_DIFF_NOTES.md](C:/Users/72785/Desktop/SIT-AUTO/docs/VERSION_DIFF_NOTES.md)

## 你现在应该关注的目录

这些是主线目录：

- [TestController](C:/Users/72785/Desktop/SIT-AUTO/TestController)
- [TestControllerUserFiles](C:/Users/72785/Desktop/SIT-AUTO/TestControllerUserFiles)
- [Toolkit](C:/Users/72785/Desktop/SIT-AUTO/Toolkit)
- [ToolkitSettings](C:/Users/72785/Desktop/SIT-AUTO/ToolkitSettings)
- [ToolkitUserFiles](C:/Users/72785/Desktop/SIT-AUTO/ToolkitUserFiles)
- [scripts](C:/Users/72785/Desktop/SIT-AUTO/scripts)
- [tests](C:/Users/72785/Desktop/SIT-AUTO/tests)
- [docs](C:/Users/72785/Desktop/SIT-AUTO/docs)

这些是运行输出目录：

- [Results](C:/Users/72785/Desktop/SIT-AUTO/Results)
- [.runtime](C:/Users/72785/Desktop/SIT-AUTO/.runtime)

这些是归档，不是当前主线：

- [_archive/legacy_web_scaffold](C:/Users/72785/Desktop/SIT-AUTO/_archive/legacy_web_scaffold)
- [_references/source_packages](C:/Users/72785/Desktop/SIT-AUTO/_references/source_packages)

## 当前项目做到哪里了

已经完成：

- 原框架目录结构已经落地
- `run-suite`、`run-master-suite`、`run-plan` 已可用
- 套件支持 `pre_test_commands / test_commands / post_test_commands`
- ServerList 支持 YAML/JSON
- 支持 `local` 和 `ssh` 执行器
- 支持 `Toolkit / ToolkitUserFiles / ToolkitSettings` 分开同步
- 支持 `command / fetch / power_cycle`
- 支持 `check-environment / validate-suite / validate-server-list / validate-plan / preflight`
- 支持 `parse-results`
- 本地 pytest 已通过

还没在公司环境实机确认：

- 真实 Linux 目标的 `SSH + 远端 python + 文件同步 + 结果回收`
- 真实 BMC 的 `ipmi` 或 `redfish`
- 真实实验室清单下的长套件

## 根目录结构说明

```text
SIT-AUTO/
  TestController/            控制器主代码
  TestControllerUserFiles/   你要改的清单和计划
  Toolkit/                   目标机执行端
  ToolkitSettings/           运行时设置
  ToolkitUserFiles/          目标机侧附加文件
  scripts/                   Linux 启动脚本
  tests/                     当前主线测试
  docs/                      说明文档
  Results/                   运行结果
  .runtime/                  本地执行缓存
  _archive/                  旧路线归档
  _references/               参考压缩包归档
```

## 另一台电脑接手时先做什么

在 Linux 控制器上先执行：

```bash
bash scripts/bootstrap_controller_linux.sh
source .venv/bin/activate
python TestController/StartController.py check-environment
```

然后先改你自己的实验室清单，推荐从模板复制：

- [linux_template.yaml](C:/Users/72785/Desktop/SIT-AUTO/TestControllerUserFiles/ServerLists/linux_template.yaml)
- [json_template.json](C:/Users/72785/Desktop/SIT-AUTO/TestControllerUserFiles/ServerLists/json_template.json)

你最先会改的文件通常是：

- `TestControllerUserFiles/ServerLists/<你的清单>.yaml`
- `ToolkitSettings/user-settings.json`
- `TestControllerUserFiles/Plans/<你的计划>.yaml`

## 明天现场建议顺序

1. 先跑环境检查
2. 再跑 `preflight`
3. 先跑 `linux_smoke`
4. 烟测通了再跑 `linux_regression`
5. 最后再碰 `linux_power_cycle`

对应命令：

```bash
python TestController/StartController.py check-environment
python TestController/StartController.py preflight --suite linux_smoke --server-list <你的清单> --probe-ssh
python TestController/StartController.py run-suite --name linux_smoke --server-list <你的清单>
python TestController/StartController.py parse-results --suite linux_smoke
```

如果要检查 BMC：

```bash
python TestController/StartController.py preflight --suite linux_power_cycle --server-list <你的清单> --probe-ssh --probe-bmc
```

## 当前最重要的入口文件

控制器入口：

- [StartController.py](C:/Users/72785/Desktop/SIT-AUTO/TestController/StartController.py)

控制器执行链：

- [run_linux_suite.py](C:/Users/72785/Desktop/SIT-AUTO/TestController/Commands/run_linux_suite.py)
- [run_master_suite.py](C:/Users/72785/Desktop/SIT-AUTO/TestController/Commands/run_master_suite.py)
- [run_plan.py](C:/Users/72785/Desktop/SIT-AUTO/TestController/Commands/run_plan.py)

检查与解析：

- [validate_platform.py](C:/Users/72785/Desktop/SIT-AUTO/TestController/Commands/validate_platform.py)
- [parse_results.py](C:/Users/72785/Desktop/SIT-AUTO/TestController/Commands/parse_results.py)

公共库：

- [controller_lib.py](C:/Users/72785/Desktop/SIT-AUTO/TestController/Libraries/controller_lib.py)
- [plan_lib.py](C:/Users/72785/Desktop/SIT-AUTO/TestController/Libraries/plan_lib.py)

Toolkit：

- [invoke_remote.py](C:/Users/72785/Desktop/SIT-AUTO/Toolkit/invoke_remote.py)
- [toolkit_lib.py](C:/Users/72785/Desktop/SIT-AUTO/Toolkit/Libraries/toolkit_lib.py)

## 示例文件

套件：

- [controller_smoke.yaml](C:/Users/72785/Desktop/SIT-AUTO/TestController/TestSuites/controller_smoke.yaml)
- [linux_smoke.yaml](C:/Users/72785/Desktop/SIT-AUTO/TestController/TestSuites/linux_smoke.yaml)
- [linux_regression.yaml](C:/Users/72785/Desktop/SIT-AUTO/TestController/TestSuites/linux_regression.yaml)
- [linux_power_cycle.yaml](C:/Users/72785/Desktop/SIT-AUTO/TestController/TestSuites/linux_power_cycle.yaml)

计划：

- [plan_template.yaml](C:/Users/72785/Desktop/SIT-AUTO/TestControllerUserFiles/Plans/plan_template.yaml)
- [local_trial.yaml](C:/Users/72785/Desktop/SIT-AUTO/TestControllerUserFiles/Plans/local_trial.yaml)

## 如果接手的人是另一个工程师或另一个 AI

请直接按下面事实理解当前状态：

- 主线不是 `app/` 那套 Web 原型，它已经被移到 `_archive/legacy_web_scaffold`
- 现在真正可运行的是 `TestController + Toolkit`
- `pyproject.toml` 和 `requirements-controller.txt` 现在都是围绕控制器主线收的
- 本地验证通过，但公司 Linux 环境仍需要第一次实机联调
- 第一目标不是扩功能，而是先打通 `preflight -> linux_smoke -> parse-results`

## 补充文档

- [LINUX_QUICKSTART.md](C:/Users/72785/Desktop/SIT-AUTO/docs/LINUX_QUICKSTART.md)
- [PLATFORM_BLUEPRINT.md](C:/Users/72785/Desktop/SIT-AUTO/docs/PLATFORM_BLUEPRINT.md)
- [VERSION_DIFF_NOTES.md](C:/Users/72785/Desktop/SIT-AUTO/docs/VERSION_DIFF_NOTES.md)
