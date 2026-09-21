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

## Trial 3 — Core launch / missing registration failure

在 Observed Live State 2 上进行真实 AutoCAD Core 启动验证。

### 启动 1：带 autoload probe

- 启动文件：本项目 `AutoCAD 2024/acad.exe`；
- PID：16828；
- 参数包含 `/nologo` 和 `live_autoload_probe.scr`；
- 运行中 image path 已确认来自本项目 F: 路径；
- 进程建立主窗口，但 probe marker 未生成；
- 主窗口标题：`AutoCAD 错误中断`。

关闭时只关闭本轮自己启动的 PID 16828，进程正常退出。

### 启动 2：排除 probe 本身

再次只使用 `/nologo` 启动：

- PID：3588；
- image path 仍是本项目 F: `acad.exe`；
- 同样进入 `AutoCAD 错误中断`。

因此可以排除 `live_autoload_probe.scr` 是本次失败原因。

### 独立读取错误窗口正文

为避免只根据窗口标题推断，使用只读 Win32 窗口文本探针重新启动并读取错误对话框。错误正文为：

> 安装出现问题，AutoCAD 无法继续。
> 如果注册表清理软件已删除或更改了运行 AutoCAD 所需的注册表项，会出现此错误。
> 要恢复所需的注册表项，您需要使用 Windows“控制面板”中的“添加/删除程序”功能重新安装 AutoCAD。

第三次探测 PID 31336 也只关闭该次自己启动的进程，并正常退出。

Windows Application log 在对应时间段未发现标准 1000/1001 acad.exe crash 事件，因此这是 AutoCAD 自己捕获并显示的安装/注册状态错误，而不是 Windows 未处理崩溃。

### 直接缺口证据

当前真实注册表只读查询确认以下 reg3 中的基础 COM 注册完全不存在：

- `HKCU\SOFTWARE\Classes\AutoCAD.Application.24`
- `HKLM\SOFTWARE\Classes\CLSID\{8B4929F8-076F-4AEC-AFEE-8928747B7AE3}`

而 reg3 明确把该 CLSID 的 `LocalServer32` 指向 AutoCAD `acad.exe /Automation`。

结论：当前“只使用 reg1 + reg2”的 Core 注册范围不足。下一步不是整份导入 reg3，而是先补最小 `AutoCAD.Application` COM bootstrap，再重复同一启动验收。

## Trial 4 — clean host reinstall / repeat install / Core launch still blocked

前提：用户已先在本机卸载 AutoCAD 2024，本机被重新批准作为当前项目的专用 CAD 2024 测试环境。

### Clean baseline

基线 `main`：

`7fad22451397c77ec0d1cc23d498f4bf0c27c3cd`

只读检查确认：

- `HKLM\SOFTWARE\Autodesk\AutoCAD\R24.3` 不存在；
- `HKCU\SOFTWARE\Autodesk\AutoCAD\R24.3` 不存在；
- `acad.exe` / `acLauncher.exe` 进程均不存在；
- Windows/admin/.NET preflight PASS；
- plan = 11,554 operations / 0 warnings / 0 audit findings；
- live diff = 1 registry same / 0 change / 8,652 create / 2,891 keys create；
- 2 Junction create / 0 conflict；
- 2 个已存在 shortcut 是包内 CHS 的绘图仪/打印样式向导快捷方式；Desktop shortcut 尚未存在。

旧 `.python-installer-state.json` 来自历史试验，虽然显示 `status=complete`，但当前 R24.3 根已经不存在，不能继续作为新 install 的 ownership baseline。

因此先把旧 journal 复制到：

`evidence-local/mvp-a-live-20260921T1642/stale-state-before-live.json`

随后只删除工作位置中的旧 state 文件，使 fresh install 从 `installer_state.exists=false` 开始。

### Fresh live install

执行：

`python -m acad_portable install --apply`

结果：**PASS**。

- applied operations = 11,553；
- 新 state = `complete`；
- registry journal = 8,653；
- Junction journal = 2；
- shortcuts journal = 3；
- conflicts = 0。

安装后只读 diff：

- registry = **8,653 same / 0 change / 0 create**；
- registry keys create = 0；
- Junction = **2 same / 0 create / 0 conflict**；
- shortcuts = **3 existing / 0 create**；
- details = empty。

直接查询还确认：

- `AcadLocation` → 当前 F: 项目 `AutoCAD 2024`；
- `AutodeskSharedFolder` → 当前 F: 项目 `Autodesk Shared`。

### Repeat install

第二次执行同一 `install --apply`：**PASS**。

执行后：

- registry 仍为 8,653 same / 0 change / 0 create；
- 2 Junction same；
- 3 shortcut existing；
- journal 数量没有膨胀；
- 未出现 ownership conflict。

因此本轮已经真实证明：当前 Core install 路径在 clean host 上能够完成并保持幂等。

### Real AutoCAD launch

在 `0加载应用程序` 中放入一次性 probe LSP，并用 `/b` script 同时准备 startup marker；两者只用于本轮测试，不属于产品。

真实启动：

- `acad.exe` PID：`28940`；
- ExecutablePath：当前 F: 项目 `AutoCAD 2024\acad.exe`；
- CommandLine 包含 `/nologo /b ...live_probe.scr`；
- AutoCAD 进程确实创建成功，但两个 marker 均未生成。

Win32 只读窗口探针确认：

- 窗口标题：`AutoCAD 错误中断`；
- 错误正文：

> 安装出现问题，AutoCAD 无法继续。
> 如果注册表清理软件已删除或更改了运行 AutoCAD 所需的注册表项，会出现此错误。
> 要恢复所需的注册表项，您需要使用 Windows“控制面板”中的“添加/删除程序”功能重新安装 AutoCAD。

因此：

- 不是旧 journal 污染导致；
- 不是 D:/E:/F: 混合注册状态导致；
- 不是 probe 脚本本身导致；
- 当前 clean install 的文件路径/Junction/shortcut/已计划 registry 都正确落地；
- **剩余 blocker 已进一步收窄为：MVP-A Core registry allowlist 仍缺 AutoCAD 启动必需注册。**

本轮只关闭自己启动的 PID 28940；当前已应用状态保留，不执行 uninstall，便于继续做最小缺项诊断。

### 调试分工

从这一点开始，耗时的 Frida / registry trace / 窗口调试交给本地 AI；主 AI 只负责：

1. 审核本地 AI 的 trace 是否为真实启动证据；
2. 判断缺失项是否属于 Core 而不是 Installer/Edge/Forms/AcSign/Shell 噪音；
3. 决定最小 allowlist 补集；
4. 审核代码、测试和最终 live acceptance。

本地 AI 任务规范见 `LOCAL_AI_LIVE_DEBUG_TASK.md`。

## Trial 5 — AcadObject CLSID 单变量 A/B 因果验证

在 Trial 4 的 clean install 基础上继续定位“AutoCAD 错误中断”。

### 启动 trace

Frida 注册表 trace 捕获到 `acad.exe` 在启动路径：

`CheckCOMServerRelativePaths -> InstallUserData`

明确访问：

`HKCR\CLSID\{E89B39BB-5AE4-4C52-9011-B70FC663F249}\InProcServer32`

并返回 `rc=2`（key/path not found）。

原始证据：

- `evidence-local/mvp-a-live-20260921T1642/com_trace.ndjson`
- `evidence-local/mvp-a-live-20260921T1642/registry_trace.ndjson`

对应 `reg3.dli` 官方抓取模板仅包含两个 section：

- `HKLM\SOFTWARE\Classes\CLSID\{E89B39BB-5AE4-4C52-9011-B70FC663F249}` → `AcadObject`
- `...\InProcServer32` → `axdb.dll`，`ThreadingModel=Apartment`

### 单变量 A/B

使用 `temp_acadobject_gate.py` 只控制这一组 CLSID，不修改其他 registry。

**B（CLSID 存在）**：

- 64-bit HKLM Classes 中该 CLSID 内容完整；
- 启动当前 F: 项目 `acad.exe /nologo`；
- 真实 PID `34936`；
- 主窗口标题：`Autodesk AutoCAD 2024 - [Drawing1.dwg]`；
- COM `AutoCAD.Application.24` 可获取；
- `command_probe.ps1` 实际执行 `SETVAR USERR1 12.345`，结果 `0 -> 12.345 -> 0`；
- 证明 AutoCAD 不仅进主界面，命令执行链也正常。

**A（只删除该 CLSID）**：

- gate 脚本先验证该树只能包含 `AcadObject / axdb.dll / Apartment`，随后删除；
- 同一文件、同一其他 registry 状态重新启动；
- 真实 PID `36564`；
- 窗口立即恢复 `AutoCAD 错误中断`；
- 错误正文仍为“运行 AutoCAD 所需的注册表项被删除或更改”。

因此当前证据支持：

> **`AcadObject` CLSID `{E89B39BB-5AE4-4C52-9011-B70FC663F249}` 是当前 MVP-A Core 启动所需的最小已证明缺口。**

本轮不据此扩大到其他 CLSID/TypeLib，也不整体导入 reg3。

### 候选实现

Python planner 仅把上述 CLSID subtree 加入现有 `AUTOCAD_REG3_CORE_PREFIXES`；相邻未证明的 `AcadWipeout` CLSID 明确保持排除，并有负向单测。

候选 non-live 结果：

- pytest：40 passed；
- plan：11,559 operations；
- warnings：0；
- audit findings：0。

下一步：先提交候选，再通过 `install --apply` 让 Python ownership journal 正式接管这组新键，然后重新执行 live startup / autoload / uninstall 闭环。

