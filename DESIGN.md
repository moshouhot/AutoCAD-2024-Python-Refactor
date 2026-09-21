# Design

## 1. 设计目标

MVP-A 采用 **CLI + 可测试计划模型 + Windows 执行适配层**。

目标不是建立复杂安装框架，而是把“读包 → 生成明确操作 → 执行 → 验证”分开，避免再次把 CMD 的文本替换、副作用和产品逻辑混在一起。

## 2. 分层

```text
CLI
 ↓
PackageModel / FeatureConfig
 ↓
InstallPlanner
 ↓
Operation Plan
 ↓
WindowsAdapter
```

### PackageModel

只负责理解当前绿色包：

- 根目录；
- AutoCAD 主目录；
- ACAOE / CHS；
- legacy registry templates；
- Support / auto-load 目录；
- 可选资源。

### RegistrySource

只把 legacy `.dli` 当**输入数据**读取。

职责：

- 解析 registry sections/values；
- 对字符串路径做结构化 rebasing；
- 按 allowlist 选择产品自有 roots；
- 生成 registry operations。

禁止直接 `REGEDIT /S reg3.dli`。

### InstallPlanner

把产品需求转换成显式 operations，例如：

- EnsureDirectory
- EnsureJunction
- SetRegistryValue
- DeleteOwnedRegistryTree
- CreateShortcut
- WriteInstallState

MVP 不需要完整事务引擎。

### WindowsAdapter

执行具体 Windows 操作。

必须同时提供：

- `FakeWindowsAdapter`：测试使用；
- `RealWindowsAdapter`：真机阶段使用。

业务层不直接散落 `reg.exe`、`mklink`、PowerShell 命令。

## 3. 注册表策略

Core MVP 的 legacy 数据源：

- `reg1.dli`：HKCU AutoCAD 用户树；
- `reg2.dli`：HKLM AutoCAD 产品树及 Applications。
- `reg3.dli`：仅从显式 `AUTOCAD_REG3_CORE_PREFIXES` allowlist 读取 AutoCAD 自身 Core 集成候选项，例如 `AutoCAD.Application` COM/TypeLib、DwgCommon、Drawing Check、Hardcopy、ObjectDBX。

第一版允许相对宽松地保留 AutoCAD 自有树，以优先证明可运行。

`reg3.dli` 的这部分不是“第三份 Core 模板整体导入”，而是一个严格前缀 allowlist。真实启动失败已经证明 `reg1 + reg2` 单独不足；其中 `AutoCAD.Application` bootstrap 有直接缺口证据，其余 reg3 Core 候选项仍需后续 live baseline 证明必要性。

明确排除：

- `reg3.dli` 整体导入；
- `regedge.dli`；
- `unreg.dli`；
- `vba.dli`（Core MVP 阶段）。

## 4. 路径转换

不要对整个文件做无边界 search/replace。

只转换 registry string value 中已识别的路径前缀：

- legacy `AcadLocation` → 当前 AutoCAD root；
- legacy Autodesk Shared → 当前 Shared root；
- legacy user/system known folders → 当前环境对应目录。

无法识别但包含历史绝对路径的值应被报告，而不是静默写入。

## 5. CHS

普通安装：

- 保留 `ACAOE/CHS` 当前内容；
- 创建/修复两个用户 `chs` Junction。

Recovery：

- 与 install 分离；
- 后续显式实现基于 `guanfang.dll` 的恢复。

## 6. Shortcut

Core MVP 只要求：

- Desktop shortcut；
- CHS 内两个 wizard shortcuts 必要时重建。

Taskbar pin 后置。

## 7. Auto-load

安装时只验证现有链路完整：

- `Support/acad2024.lsp`
- `Support/appload.lsp`
- `0加载应用程序`

MVP 不重写 LSP，除非验证证明旧实现阻塞真实功能。

## 8. 状态文件

Python 可以维护自己的小型状态文件，记录：

- package path；
- version；
- 本工具管理的 registry roots；
- 创建的 Junction / shortcut；
- install timestamp。

它是 uninstall/status 的依据，不冒充 Windows Installer。

## 9. 错误处理

MVP 只要求：

- 关键输入缺失时 fail-fast；
- 每个 operation 有明确错误；
- 不把失败报告成成功；
- 写入前可以生成 dry-run plan。

完整 rollback、并发、恶意输入防御后置。

