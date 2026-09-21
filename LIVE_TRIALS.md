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

## Observed Live State 2 — complete state with incomplete provenance

> 这不是补写成“成功 Trial 2”。这里只记录主审计者在后续接管时能够独立观察到的事实。

2026-09-21 后续只读复核时发现：

- `AutoCAD 2024/ACAOE/.python-installer-state.json` 已存在；
- 文件 mtime：`2026-09-21T13:26:14.363863`；
- state `status = complete`；
- schema = 1；
- journal 中：
  - registry values = 8528；
  - created registry keys = 2769；
  - created Junctions = 2；
  - shortcuts = 3；
- 两个 Junction 都指向本项目 `AutoCAD 2024/ACAOE/CHS`；
- desktop shortcut journal 路径为当前 Windows 重定向桌面 `E:\360data\Desktop\AutoCAD 2024.lnk`。

这说明 Trial 1 回滚之后，真实机器上**至少发生过一次能够把 journal 写到 `complete` 的 Core apply**。

但是当前冻结文档中没有对应的完整执行记录（命令、stdout/stderr、当时 HEAD、操作者、前后基线），因此不能把它追认为一个完整的、可审计的 “Trial 2 PASS”。

### 后续只读一致性检查

接管后运行当前 HEAD 的 `diff --json`，最初发现两个 reg1 抓包值与当前 AutoCAD 运行状态不同：

- `LastRunTime`
- `MiniDump\SessionStartCount`

这两个值属于 AutoCAD 自己产生的运行时状态，不应该由安装器拥有。Core planner 已将它们从安装计划中排除，并增加回归测试。

修正后的当前计划：

- registry values = 8526；
- current registry same = 8526；
- change = 0；
- create = 0；
- Junction same = 2，conflict = 0；
- shortcuts existing = 3；
- diff details = empty。

全量测试：`31 passed`。

### 结论

当前机器存在一个与最新 Core plan **只读一致**的已应用状态，但其成功 apply 的完整来源证据缺失。

因此：

- 可以把它当作下一步真机功能验证的当前测试状态；
- 不能把它当作“完整 Core MVP 验收 PASS”的历史证据；
- 后续不应为了补文档而重新 apply/uninstall，只需继续做尚未完成的真实 AutoCAD 功能验收。

