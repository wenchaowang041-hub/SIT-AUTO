# Toolkit/UserFiles

这里对应旧平台里的 `ToolkitUserFiles`，现在已经合并到 `Toolkit/UserFiles`。

当前先保留目录结构，后续可以继续往里面放：

- 厂商 CLI
- 固件
- 诊断脚本
- 自定义二进制

当前已内置：

- `tools/collect_system_info.sh`：只读采集系统、磁盘、NVMe、PCIe、网络和 dmesg 摘要。
- `tools/check_linux_health.sh`：检查 python3、根分区空间、lsblk、nvme-cli、lspci 等基础条件。
- `tests/smoke_system_check.sh`：调用基础采集和健康检查。
- `tests/storage_inventory_check.sh`：采集存储、NVMe 和 PCIe 存储设备清单。
