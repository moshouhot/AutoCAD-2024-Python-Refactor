# Python Functional Requirements

> Phase 2 产品规范。自本文件批准后，Python 是否完成以这里的功能契约为准，不再以 CMD 逐命令/逐副作用一致为准。

## 1. 产品目标

用 Python 重新实现 AutoCAD 2024 绿色版的**实际用户功能**。

旧 CMD 仅用于发现功能和历史依赖，不是最终规范。

MVP 优先：

- 先让 AutoCAD 核心安装/注册/用户数据映射真正工作；
- 再补 VBA 等重要可选能力；
- WebView2、Shell/AcSign、复杂卸载清理和极端安全问题后置。

## 2. MVP 分层

### MVP-A：Core Portable AutoCAD

这是第一开发目标。完成后必须可以从当前绿色包建立一个可运行 AutoCAD 2024 环境。

### MVP-B：VBA

在 MVP-A 真机通过后增加完整 VBA 能力。

VBA 不允许再以“导入旧 `vba.dli` 就算完成”为验收标准。

### Later

- WebView2 特殊部署；
- AcSign Windows Shell；
- Plot/Style Manager 系统 CPL；
- 文件关联增强；
- 任务栏固定；
- 复杂 Backup/Recovery；
- 高强度事务、并发和恶意输入防御。

## 3. MVP-A 功能需求

### FR-01 Package discovery

Python 必须从当前绿色包结构发现：

- AutoCAD 根目录；
- `acad.exe`；
- `ACAOE`；
- `ACAOE/CHS`；
- 本地注册模板来源；
- `Support/acad2024.lsp` / `appload.lsp`；
- `0加载应用程序`。

不依赖不存在的 `PackageManifest.json`。

缺少关键输入时明确失败。

### FR-02 Status / preflight

安装前至少检查：

- Windows；
- 管理员权限需求；
- AutoCAD 主文件存在；
- ACAOE 关键资源存在；
- .NET Framework 4.7+ 或兼容条件；
- 目标注册表版本信息是否可解析。

MVP 不需要设计完整事务系统。

### FR-03 AutoCAD core registry

Python 必须建立 AutoCAD 2024 正常启动所需的核心注册状态。

原则：

- `reg1.dli` 的 HKCU AutoCAD 用户/配置树是用户侧事实来源；
- `reg2.dli` 的 AutoCAD 产品树和 Applications 是重要事实来源；
- `reg3.dli` 只允许通过**显式 Core allowlist**读取少量 AutoCAD 自身集成注册，禁止整份导入；
- 已有真实启动失败证据支持补入 `AutoCAD.Application` COM / TypeLib bootstrap；
- `DwgCommon`、`Drawing Check`、`Hardcopy`、`ObjectDBX` 等当前属于候选 Core allowlist，是否每一组都是最小必需仍需在可信 live baseline 上验证；
- 当前已验证 279 个 Application loader 与包内容一致（文件型 loader 0 缺失）；
- 可以在 MVP 阶段把 legacy template 当**输入数据源**，但必须由 Python 解析、路径重写并受明确 root allowlist 约束；
- 不允许无脑导入 `reg3.dli` 全系统快照；
- 不允许通过导入 `regedge.dli` 伪造 WebView2 安装状态；
- 不允许整体导入 `unreg.dli`。

第一版允许保留较宽的 AutoCAD 自有 HKLM/HKCU 产品树，以换取 MVP 可用性；后续再做最小化。

这里的“较宽”仍只限 AutoCAD 自身产品/COM 候选边界，不代表允许把 Windows Installer、EdgeUpdate、Forms、AcSign Shell 或其他系统级 reg3 状态一起带入 Core。

### FR-04 Path rebasing

所有从 legacy template 读取的旧绝对路径必须转换为当前包/当前系统路径。

至少包括：

- AutoCAD 根目录；
- Autodesk Shared；
- UserProfile；
- Windows；
- Public；
- ProgramData；
- AppData / LocalAppData；
- 必要的短路径场景。

路径转换必须是显式规则，不能继续依赖 CMD 对整个文本做模糊替换。

### FR-05 CHS user data mapping

安装应建立：

- LocalAppData AutoCAD `chs` → `ACAOE/CHS`
- AppData AutoCAD `chs` → `ACAOE/CHS`

优先沿用 Junction，因为这是绿色版保持标准 AutoCAD 路径同时持久化用户数据的核心机制。

重复安装不得无条件清空当前 `ACAOE/CHS`。

### FR-06 CHS baseline / recovery semantics

必须区分：

- 当前用户 CHS；
- `guanfang.dll` 出厂基线。

普通安装不做全量 reset。

Recovery 功能后续可以提供显式 `--reset-chs` / `repair`，但必须是用户主动触发的语义。

### FR-07 Desktop shortcut

MVP 支持创建桌面 AutoCAD 快捷方式：

- target：当前 `acad.exe`；
- arguments：`/nologo`；
- desktop 路径使用 Windows 正规用户目录解析。

“当前目录快捷方式”和任务栏 pin 可以后置。

### FR-08 Plotter/style wizard shortcuts

如果 CHS 下对应快捷方式不存在或路径失效，Python 应能够重建：

- 添加绘图仪向导；
- 添加打印样式表向导。

这是 CHS 用户体验的一部分，不需要复刻旧快捷方式二进制本身。

### FR-09 Auto-load extensions folder

MVP 必须保留：

`0加载应用程序`

的用户能力。

必须保证：

- `acad2024.lsp` 能触发自动加载逻辑；
- 扩展目录被加入 AutoCAD 支持路径；
- LSP/FAS/VLX/ARX 能自动加载。

.NET DLL 自动加载可在后续明确实现，不复制旧 LSP 的匹配缺陷。

### FR-10 Optional custom config

当前包没有 `0自定义配置文件`，因此不是 MVP 必需输入。

如果未来目录存在，可定义为“只覆盖 CHS 中已有同名配置”的可选功能。

### FR-11 Install metadata

可以写入我们自己的安装状态，用于：

- `status`；
- uninstall；
- troubleshooting。

不要求复制旧 CMD 的 `DisplayName=...lite` 等历史文案。

### FR-12 Uninstall (MVP)

卸载原则：

> 只删除 Python 安装器明确拥有的状态。

第一版至少可以删除：

- Python 创建的 Junction；
- Python 创建的快捷方式；
- Python 自己创建/管理的核心注册项；
- Python 安装状态。

默认不得：

- 整树删除 Windows Installer 状态；
- 删除 Forms/Office 共享组件；
- 全盘强杀所有 AutoCAD；
- 大面积删除用户 AppData；
- 执行旧 `unreg.dli`。

## 4. MVP-B：VBA 功能需求

在 Core MVP 真机可启动后实施。

目标按能力拆分：

1. `AcVBA2024.Bundle`；
2. Microsoft VBA 7.1 Runtime；
3. `AcadVBA` AutoCAD 注册；
4. UserForm / Forms 2.0（若声明“完整 VBA”）。

验收必须是实际功能：

- `VBALOAD`；
- `VBAIDE`；
- 普通宏运行；
- 若包含 Forms：UserForm 显示和事件。

MSI bookkeeping 是否模拟，不属于默认 MVP 用户功能，除非运行实证证明必要。

## 5. MVP 明确排除

### EX-01 WebView2 legacy pseudo-install

不复制：

- 3 文件 WebView2 片段；
- `regedge.dli` EdgeUpdate ClientState 伪安装状态。

Core MVP 只检测已有 WebView2；如果 AutoCAD 某功能确实依赖它，再另立完整方案。

### EX-02 AcSign Windows Shell

不在 Core MVP 向 System32 部署 AcSignExt/AcSignIcon。

AutoCAD 自身 `AcSign.arx` 可以随核心 Application 注册存在，但 Explorer 属性页/图标 overlay 属于后续 Shell feature。

### EX-03 Plot/style system CPL

`plotman.cpl` / `styleman.cpl` 的 System32 部署暂不进入 Core MVP。

### EX-04 Taskbar pin

不依赖旧 `Pintf.dll` 做任务栏固定。

### EX-05 Green-package authoring toolchain

CMD 338–514 的制包功能不属于 Python 安装器 MVP：

- REG→DLI；
- 抓取官方安装；
- 重新封装 Tohomedrive；
- BAT→EXE；
- 生成 default/guanfang。

## 6. 明确不复制的旧行为

- `%temp%/cad.log`；
- 临时 `1.ps1`；
- CMD title/color；
- 安装前先调用破坏性 UNINSTALL 清场；
- 无条件 `-aoa` 覆盖 System32；
- `&&` / `&` 偶然语义；
- 不存在的 `installser/myapp` hook；
- `跳过网络验证` 这条当前主 CMD 未消费的配置；
- `reg4.dli` 中纯个性化颜色/Activity Insights 默认项。

## 7. CLI 形态

MVP 优先 CLI，不做 GUI。

建议命令：

```text
python -m acad_portable status
python -m acad_portable install
python -m acad_portable uninstall
python -m acad_portable repair
```

具体命令名可在实现阶段调整。

## 8. MVP-A 完成定义

必须满足：

1. 干净/可控测试环境中执行 install 成功；
2. AutoCAD 2024 从当前绿色包路径启动到可操作状态；
3. 运行中的 image path 是本包 `acad.exe`；
4. 核心 Applications loader 不悬空；
5. AppData / LocalAppData CHS 映射正确；
6. CHS 现有用户状态不会因普通安装被 reset；
7. 桌面快捷方式可启动正确 AutoCAD；
8. `0加载应用程序` 中的测试 LSP 能自动加载；
9. 重复执行 install 不明显破坏当前状态；
10. uninstall 不执行旧式大范围系统清理。

MVP-A 通过后，再进入 VBA。
