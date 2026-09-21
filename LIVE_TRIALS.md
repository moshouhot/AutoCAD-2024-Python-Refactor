# Live Trial Log

> 只记录真实执行事实。失败试验也保留，不用“最终成功”覆盖历史。

## Trial 1 — Core apply / redirected Desktop failure

基线 HEAD：`3510b85573d5be23313fbf0a57a87310040245ed`

执行前：

- Git clean；
- 相关 AutoCAD / 旧安装器进程 = 0；
- installer state = absent；
- Core plan warnings = 0；
- Core audit findings = 0；
- live diff：8528 registry values 全部为 create，0 change；2769 keys create；2 Junction create；0 conflict。

执行：

`python -m acad_portable --root .. install --apply`

结果：**FAIL**。

失败点：创建 desktop shortcut 前，代码尝试把 `%USERPROFILE%\Desktop` 当目录使用，Windows 返回 `WinError 183`。

独立只读检查确认：

- Windows 的实际 Desktop 由 `User Shell Folders\Desktop` 重定向到其他磁盘目录；
- `%USERPROFILE%\Desktop` 在本机是普通文件，不是目录。

这说明产品语义应是“解析 Windows 实际 Desktop Known Folder”，而不是拼接 `%USERPROFILE%\Desktop`。

### 失败时 journal

- status = `failed`；
- registry values journaled = 8528；
- junctions journaled = 2；
- shortcut journal entry = 1，但 shortcut 尚未成功写入。

live diff 复核：

- 8528/8528 registry values 已达到计划值；
- 2/2 Junction 已达到计划目标；
- 未进入 System32/VBA/WebView2/AcSign。

### 回滚

先修复“shortcut journal 已记录、但 shortcut 未成功创建”这一 rollback 边界并通过专项/全量测试，再执行：

`python -m acad_portable --root .. uninstall --apply`

结果：

- registry restored = 0；
- registry removed = **8528**；
- junctions removed = **2**；
- shortcuts restored/removed = 0/0；
- conflicts = **0**。

回滚后只读复核恢复到 apply 前状态：

- installer state = absent；
- registry same/change = 0/0，create = 8528；
- Junction same = 0，create = 2，conflict = 0。

### 修复

Python 改为按顺序读取 Windows：

1. `Explorer\User Shell Folders\Desktop`
2. `Explorer\Shell Folders\Desktop`
3. 最后才 fallback 到 `%USERPROFILE%\Desktop`

同时 plan audit 增加：如果 shortcut parent 已存在但不是目录，直接产生 finding，禁止进入 apply。

修复后真实 plan 已解析到重定向桌面目录，warnings = 0，audit findings = 0。

Trial 1 不计为产品 PASS，但它证明了：

- live fail-closed 生效；
- failed journal 可用于完整回滚本轮 registry/Junction 写入；
- 当前真实机状态在回滚后恢复到试验前 Core diff。

