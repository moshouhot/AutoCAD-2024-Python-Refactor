# CMD Functional Specification

> 状态：Phase 1 / 持续补全

本文档的目标不是复述 514 行 CMD，而是把旧 CMD 还原为一份**产品功能说明书**。

旧 CMD 和本地资源仅作为事实来源。Python 最终是否实现某个行为，将在 Phase 2 的 `PYTHON_FUNCTIONAL_REQUIREMENTS.md` 中另行决定。

---

## 1. 参考基线

本地参考目录：

`F:\Nextcloud\project\AutoCAD 2024.1.9 绿色完整版`

主要参考物：

- `安装_AutoCAD V4 阉割版.cmd`：主控制脚本，当前扫描为 **514 行**。
- `AutoCAD 2024/ACAOE/配置.txt`：功能开关。
- `AutoCAD 2024/ACAOE/reg1.dli` ~ `reg4.dli`：注册表模板。
- `AutoCAD 2024/ACAOE/regedge.dli`：Edge/WebView2 相关注册模板。
- `AutoCAD 2024/ACAOE/vba.dli`：VBA / Forms 相关注册模板。
- `AutoCAD 2024/ACAOE/unreg.dli`：卸载/清理相关注册表模板。
- `AutoCAD 2024/ACAOE/guanfang.dll`、`default.dll`：CHS / 默认数据恢复资源。
- `AutoCAD 2024/ACAOE/Tohomedrive.dll`：系统级辅助载荷。
- `AutoCAD 2024/ACAOE/app/VBA.dll`：VBA 载荷。
- `AutoCAD 2024/ACAOE/app/auedgewebview.dll`：WebView2 相关载荷。
- `shortcut.dll`、`Pintf.dll` 等辅助文件。

这些第三方/历史资源只在本地用于分析，不纳入公开仓库。

---

## 2. 当前配置开关

`ACAOE/配置.txt` 当前内容：

| 配置 | 当前值 | 初步职责 |
|---|---:|---|
| 检测 NET安装 | 1 | 检查 .NET 运行条件 |
| 安装 VBA编程 | 1 | 安装/启用 AutoCAD VBA |
| 桌面快捷方式 | 1 | 创建桌面快捷方式 |
| 当前快捷方式 | 0 | 在安装器当前目录创建 AutoCAD 快捷方式 |
| 固定到任务栏 | 1 | 固定 AutoCAD 到任务栏 |
| 恢复原始数据 | 0 | 执行恢复流程 |
| 完全卸载程序 | 1 | 启用完整卸载行为 |
| 安装自定义配置 | 1 | 合并用户自定义配置 |
| 检测程序完整性 | 1 | 安装前/中进行文件完整性检查 |
| 跳过网络验证 | 0 | 当前 514 行主 CMD 未消费该配置；视为历史/外部扩展项 |

> Phase 1 只记录实际含义，不等于 Python 必须保留同名开关。

---

## 3. CMD 控制面概览

已识别的主要 label 可按职责初步分组：

### 3.1 启动、权限与环境发现

- `:UACPrompt`
- `:UACAdmin`
- `:jwmic1`
- `:jwmic2`
- `:GELLVAR`
- `:REQUEST`
- `:GEVAR1-5`

职责：获取管理员权限、系统/AutoCAD 路径和环境变量。具体变量契约待逐项补全。

### 3.2 菜单和参数入口

- `:QUICK`
- `:QUICKEN`
- `:MAINMENU`
- `:CONFIRM_UNINSTALL`
- `:CONFIRM_RECOVERY`
- `:-i` / `:/i`
- `:-u` / `:/u`
- `:-b` / `:/b`
- `:-r` / `:/r`
- `:-z` / `:/z`

职责：把交互菜单和命令行参数映射到安装、卸载、备份、恢复及注册处理流程。

### 3.3 安装 / 卸载 / 备份 / 恢复

- `:INSTALL`
- `:UNINSTALL`
- `:BACKUP`
- `:RECOVERY`

这是产品主流程，Phase 1 的重点。

### 3.4 检查与配置

- `:LIST`
- `:NOLIST`
- `:CHECKNET`
- `:CHECKFILE`
- `:WRITEPZ`
- `:SHUOMING`
- `:PEIZHI`

职责：完整性、网络、配置文件生成和配置交互。

### 3.5 绿色化 / 资源生成工具

- `:GREEN`
- `:obat`
- `:1JIANGREEN`
- `:REGTODLI`
- `:7ZREG`
- `:7ZCHS`
- `:ENCRYPTION`
- `:DELCHSFILE`
- `:TIQU`
- `:COPYFILE`
- `:COPYser`

这些入口中一部分属于“制作绿色包”的作者工具，不一定属于最终 Python 安装器。Phase 1 需要先区分**运行时安装职责**与**制包职责**。

---

## 4. 功能域清单

以下编号描述的是**产品职责**，不是 CMD 行号。

| ID | 功能域 | 当前理解 | Phase 1 状态 |
|---|---|---|---|
| F01 | 启动与权限 | UAC、管理员权限、系统环境发现 | 已解析 |
| F02 | AutoCAD 路径/版本发现 | 从注册表和目录推导 AutoCAD 根路径、共享目录、用户目录 | 已解析 |
| F03 | 安装主流程 | 安装前清理、目录准备、注册、依赖、快捷方式等 | 已解析 |
| F04 | 注册表 | `reg1~4/regedge/vba/unreg` 已按职责拆分并建立风险边界 | 已解析 |
| F05 | CHS / 中文用户数据 | CHS、Support、Template、Plotters、`Sample.cus` 与出厂基线 | 已解析 |
| F06 | VBA | AcVBA、VBA Runtime、Forms/FM20、Installer 痕迹已分层 | 已解析；产品取舍见 Phase 2 |
| F07 | WebView2 | 3 文件片段 + EdgeUpdate ClientState，不构成完整 Runtime | 已解析；MVP 后置 |
| F08 | Shell / AcSign / 系统辅助组件 | Tohomedrive 已拆为 Plot/Style、AcSign、Forms 三类职责 | 已解析；MVP 后置/分拆 |
| F09 | Shortcut / Pin | 桌面、当前目录、两个向导快捷方式、任务栏固定 | 已解析 |
| F10 | Junction / 路径适配 | AppData/LocalAppData `chs` → 包内 CHS | 已解析 |
| F11 | 自定义配置 | `0自定义配置文件` 可选合并；当前包不存在该目录 | 已解析 |
| F12 | 完整性 / 前置检查 | .NET 4.7+；当前 `list.dll` 实际只检查 `acad.exe` | 已解析 |
| F13 | 卸载 | 旧 CMD 的强杀、整树注册清理、用户目录清理等已拆分 | 已解析 |
| F14 | 备份 | HKCU/HKLM AutoCAD 注册表快照型备份 | 已解析 |
| F15 | Repair / Recovery | `default.dll` 注册模板 + `guanfang.dll` CHS 出厂恢复 | 已解析 |
| F16 | 制作绿色包工具链 | REG→DLI、抓包、资源抽取、封包、BAT→EXE | 已解析；排除出 Python 安装器 MVP |

---

## 4.1 启动与环境准备（首轮已读）

主脚本启动阶段（约 1–87 行）当前可确认：

1. 切换到 CP936，启用 delayed expansion，并把脚本目录作为工作目录。
2. 通过 `BCDEDIT` 成功与否判断是否已有管理员权限；否则用 `ShellExecute(..., "runas")` 自提升。
3. 定义 `REG ADD/QUERY/DELETE`、`shortcut.dll`、`hui7za.dll` 等辅助命令。
4. 获取当前用户 SID；优先 WMIC，失败后临时生成 PowerShell 脚本获取。
5. 通过 `reg1.dli + reg2.dli + reg3.dli` 临时导入/查询 AutoCAD 信息，得到：
   - 当前 AutoCAD 主版本；
   - 产品子键；
   - 产品名称；
   - DWG 关联版本；
   - `LocalRootFolder`；
   - `AllUsersFolder`；
   - `AutodeskSharedFolder`；
   - `AcadLocation`。
6. 根据这些值推导用户目录、Windows 目录、Public、ProgramData、CAD 根目录及其双反斜杠形式，供后续 `.dli` 路径替换使用。
7. 启动过程中存在 `%temp%\cad.log`、临时 `1.ps1`、窗口标题等辅助行为；这些目前只视为旧实现细节，不视为独立产品功能。

### 值得特别关注

- 第 50 行会在 `ACAOE` 目录执行 `REN *.exe *.dll`。这更像绿色包内部的历史封装约定，不应直接推导为 Python 产品需求。
- `GELLVAR` 为了读取注册表模板，会创建临时注册表镜像根并随后删除。Python 没有必要复制这种“先导入临时树再反查变量”的实现方式，只需在 Phase 2 保留真正需要的产品信息。

---

## 4.2 正常安装主流程 `:INSTALL`（156–199）

当前已经完整读完正常安装主体。按产品职责可拆为：

### A. 安装前清理

第一句是：

`CALL :UNINSTALL 安装`

也就是说旧 CMD 在每次安装前先复用一部分卸载逻辑。即使参数是“安装”，在返回前仍会执行：

- 强制结束 `acad.exe` / `aclauncher.exe`；
- 删除多处 AutoCAD / VBA 注册表树；
- 删除 LocalAppData / AppData 下对应产品目录；
- 清理 CHS 缓存；
- 删除 AppCompat Layers；
- 删除已有快捷方式；
- 刷新 Shell 图标；
- 调用 `Pintf.dll` 做任务栏相关处理。

到 `IF %1==安装 GOTO :EOF` 后，才跳过真正的 `unstallser.cmd` / `unmyapp.cmd`。

**结论：**“安装前先做破坏性清场”是旧 CMD 的实现策略，不自动等于 Python MVP 的产品需求。

### B. 前置检查

根据配置可执行：

- `CHECKFILE`：依据 `list.dll` 检查 AutoCAD 主目录文件是否齐全；
- `CHECKNET`：实际检查的是 **.NET Framework 4.7+**，并不是互联网连通性；
- `RECOVERY`：可在安装前恢复默认资源。

### C. 用户目录 / Junction

创建 LocalAppData 与 AppData 下的 Autodesk 产品目录，并把两个 `chs` 路径通过 Junction 指向绿色包自身 `.\chs`。

该职责属于真正的“绿色化用户数据定位”，后续需要判断 Python 是否继续采用 Junction，还是采用更清晰的路径策略。

### D. Autodesk Shared / Shell 文件

把本地 `acshellex` 目录复制到 `%CommonProgramFiles%\Autodesk Shared\...`。

### E. 系统级载荷

- `Tohomedrive.dll` 使用 `-aoa` 解到 `%HOMEDRIVE%`，属于无条件覆盖式系统载荷；
- `app\au*.*` 使用 `-aos` 解到 `%HOMEDRIVE%`，已有文件则跳过。

该部分后续必须按**真实用户功能**重新拆解，不能因为旧 CMD 会解包就默认 Python 应照搬。

### F. 注册表路径重写与导入

CMD 先把 `.dli` 中制包时记录的路径替换为当前机器：

- UserProfile；
- Windows；
- Public；
- ProgramData；
- CAD 根目录；
- Autodesk Shared；
- 8.3 短路径。

随后执行：

`FOR %%a IN (reg*.dli) DO REGEDIT /S %%a`

因此正常安装会导入所有匹配 `reg*.dli` 的模板，包括 `regedge.dli`。注册表模板之间还可能引用其他归档负责部署的 DLL/EXE，后续必须按功能建立依赖关系。

### G. AppCompat / 快捷方式

- 给 `acad.exe` 和 `aclauncher.exe` 设置 `~ runasadmin`；
- 重建“添加绘图仪向导”和“添加打印样式表向导”快捷方式；
- 按配置创建桌面/当前目录快捷方式；
- 可按配置固定任务栏。

### H. 自定义配置

若开启“安装自定义配置”，使用 `XCOPY /U` 把 `0自定义配置文件` 合并到 CHS。

### I. VBA

脚本尝试用配置 `安装 VBA编程=1` 控制：

- 导入 `vba.dli`；
- 解包 `app\VBA.dll`。

但旧 CMD 把 `&&` 与 `&` 混用，因此**“配置开关是否真正同时控制注册与文件解包”必须按 cmd.exe 实际语义解释，不能按作者表面意图理解。**

Phase 2 会从“用户需要 AutoCAD VBA 到什么程度”重新定义需求，而不是复刻这条表达式。

### J. 卸载项与收尾

写入自身卸载信息，清理 GPU Certification 中部分字段和 Recent File List，刷新 Shell，并尝试调用可选的：

- `installser.cmd`
- `myapp.cmd`

这些脚本即使不存在也被静默忽略。

---

## 4.3 卸载 `:UNINSTALL`（202–225）

旧卸载流程当前确认会：

- 强杀 `acad.exe` 和 `aclauncher.exe`；
- 删除自身卸载项；
- 删除 AutoCAD / VBA 相关 HKLM/HKCU 注册表树；
- 可根据配置导入 `*un*.dli` 做更大范围清理；
- 删除 LocalAppData / AppData 产品目录；
- 删除 Autodesk Shared 下对应 Shell 目录；
- 删除 CHS 缓存；
- 删除 AppCompat Layers；
- 删除桌面和当前目录快捷方式；
- 调用任务栏处理；
- 正式卸载时再执行 `unstallser.cmd` / `unmyapp.cmd`。

**Phase 1 事实判断：**它混合了“删除本项目创建内容”和“清理用户/共享状态”两类职责。Python 卸载器后续需要重新定义边界。

---

## 4.4 备份 `:BACKUP`（228–235）

备份不是复制整个用户目录，而是：

1. 先确认当前用户 AutoCAD 注册存在；
2. 删除旧备份；
3. 导出 HKCU AutoCAD 主树；
4. 导出 HKLM AutoCAD 主树；
5. 把结果留在安装包内，供下次安装时重新使用。

因此“备份用户界面设置”在旧实现里实际上是**注册表快照型备份**，范围可能比 UI 设置更大。

---

## 4.5 Recovery `:RECOVERY`（238–243）

Recovery 当前只有两个核心动作：

1. 从 `default.dll` 解出默认 `.dli` 数据到 ACAOE；
2. 删除当前 `chs`，再从 `guanfang.dll` 完整恢复 CHS。

这解释了为什么 `Sample.cus`、模板、Plotters 等资源可以通过 Recovery 一次性恢复。

对 Python 来说，产品职责应描述为“恢复出厂注册模板 / CHS 用户数据”，而不是必须继续使用两个伪装成 DLL 的 7z 包。

---

## 4.6 配置系统的重要发现

当前 `配置.txt` 有 10 行，但 CMD 自身 `WRITEPZ` 默认生成器只管理 9 个变量：

1. 安装 VBA编程
2. 桌面快捷方式
3. 当前快捷方式
4. 固定到任务栏
5. 恢复原始数据
6. 完全卸载程序
7. 安装自定义配置
8. 检测程序完整性
9. 检测 NET安装

当前文件额外存在：

`跳过网络验证=0`

但在 514 行主 CMD 中：

- 没有 `PEIZ10`；
- 没有出现“跳过网络验证”文本；
- `CHECKNET` 实际只检查 .NET Framework 版本。

**当前结论：**第 10 行至少对这份主 CMD 而言是“未被主脚本消费的配置项”。它可能来自外部 EXE、其他版本或历史遗留，暂不能列为已确认产品功能。

---

## 4.7 制作绿色包工具链（338–514）

这一段已经可以明确与正常安装流程分层。

它提供的不是最终用户安装功能，而是**作者制包工具**，包括：

- 从抓取的 REG 生成绿色包注册模板；
- 把真实安装路径替换成绿色包路径；
- 抽取 AutoCAD / Shared / Start Menu / 用户 CHS 文件；
- 从 System32 / SysWOW64 收集 AcSign、FM20、plot/style manager 等文件；
- 生成 `Tohomedrive.dll`；
- 把 `.dli` 打成 `default.dll`；
- 把 CHS 打成 `guanfang.dll`；
- 把 BAT 转 EXE；
- 删除运行时缓存后重新封装。

### Phase 1 当前结论

`338–514` 应被视为**“绿色包生产流水线”**，不是 Python MVP 安装器需要 1:1 重构的运行时主流程。

Python 项目真正需要继承的，是这里揭示出的**资源来源和功能依赖关系**。例如：

- `Tohomedrive.dll` 中某些文件为什么存在；
- `default.dll` / `guanfang.dll` 是怎么生成的；
- 哪些 CHS 文件被认为是“出厂基线”；
- 哪些注册表树来自官方安装抓取。

是否继续提供“制作绿色包”能力，应作为独立产品决定，而不能混进安装 MVP。

---

## 5. Phase 1 解析规则

对于每个功能域，必须回答：

1. **用户功能是什么？**
2. **CMD 如何实现？**
3. **依赖哪些文件 / 注册表 / 外部程序？**
4. **输入条件和配置开关是什么？**
5. **最终系统状态是什么？**
6. **哪些只是历史实现细节或偶然副作用？**
7. **还有哪些 UNKNOWN？**

Phase 1 不在这里决定 Python 必须怎样实现，只负责把事实搞清楚。

---

## 6. 已知需要特别警惕的旧 CMD 行为

以下项目只作为审阅提醒，不在 Phase 1 直接下产品结论：

- 可能存在整树注册表删除；
- 可能无条件覆盖系统目录文件；
- 可能强制终止 AutoCAD；
- `&&` 与 `&` 混用可能形成与作者意图不同的执行顺序；
- 注册模板可能引用由其他归档负责部署的 DLL/EXE，不能只看单条 `REGEDIT`；
- 当前机器历史残留不能作为“安装器已经正确部署”的证明。

---

## 7. Phase 1 收口状态

上述原始待分析项已经分别在第 4、8、9、10 节完成静态职责拆解：

- `:INSTALL / :UNINSTALL / :BACKUP / :RECOVERY` 控制流已读完；
- 7 个 `.dli` 已按产品职责分类；
- `default.dll / guanfang.dll / Tohomedrive.dll / VBA.dll / auedgewebview.dll` 已只读列目录并建立职责映射；
- Shortcut / Junction / 自定义配置 / .NET / 完整性检查已定位；
- 制包工具链已经与运行时安装器明确分层。

因此：

> **Phase 1 在当前 Python MVP 所需的静态功能理解范围内可以视为完成。**

这不代表所有功能都已被 Python 实现，也不代表真机行为已经通过。以下内容属于后续阶段而不是 Phase 1 未完成项：

- 哪些旧职责进入 MVP / Later（Phase 2 产品取舍）；
- Core 最小注册集合的真机充分性；
- VBA / Forms 2.0 的真实运行闭环；
- WebView2 / AcSign / System32 组件是否未来需要产品化；
- 当前 D:/E:/F: 混合 live 环境的重新验收。

---

## 8. 注册表模板职责地图

已使用只读工具对 7 个 `.dli` 做结构盘点。这里记录的是**用途分区**，不是要求 Python 整份导入。

### `reg1.dli` — 用户侧 AutoCAD 配置

- 1887 行；
- 322 个 registry section；
- 全部落在 `HKCU\SOFTWARE\Autodesk\AutoCAD\R24.3...`；
- 主要承担用户 profile、图形设置、路径、历史用户状态等。

**判断：**这里混有“AutoCAD 能工作所需默认值”和“抓包机器上的用户状态”。Python 后续不能把整份 `reg1.dli` 当产品规范。

### `reg2.dli` — AutoCAD HKLM 产品/应用注册

- 12504 行；
- 2479 个 section；
- 全部位于 `HKLM\SOFTWARE\Autodesk\AutoCAD\R24.3...`；
- 包含大量 AutoCAD Applications 注册。

已确认 `AcadVBA` 在这里：

- `DESCRIPTION = AcVBA Command Module`
- `LOADCTRLS = 0x0d`
- `LOADER = C:\Program Files\Autodesk\ApplicationPlugins\AcVBA2024.Bundle\Contents\AcVBA.arx`
- Commands 包含 `VBAIDE`、`VBALOAD`、`VBAUNLOAD`。

`AcadLocation` 也在 `reg2.dli` 中，制包时记录为作者机器的 AutoCAD 路径，安装时由 CMD 动态替换。

**判断：**这是 Python 后续定义“AutoCAD 核心 HKLM 注册”的主要事实来源，但需要按应用/功能裁剪。

### `reg3.dli` — 系统级集成集合

- 19640 行；
- 5591 个 section；
- 涵盖 HKCU Classes、HKLM Classes、COM、TypeLib、Windows Installer、Shell Extension 等多个系统域。

已确认它包含 AcSign Shell 集成，例如：

- `AcSignExt` CLSID → `C:\Windows\system32\AcSignExt.dll`
- `AcSignIcon` CLSID → `AcSignIcon.dll`
- 多种文件类型的 `Enable/Disable Digital Signature Icons` shell command → `acsignopt.exe`

同时还有大量 Windows Installer / Package Cache / 其他安装器历史记录。

**判断：**`reg3.dli` 不能作为一个整体进入 Python MVP。必须拆成“文件关联”“AutoCAD COM”“Shell/AcSign”“Installer 历史”等职责；后两类尤其不能盲目复制。

### `reg4.dli` — 小型补充状态

- 81 行；
- 25 个 section；
- 包含一个 TypeLib、部分当前用户 profile / Applications / GPU Preference 等补充状态。

**判断：**更像抓包后的补丁型差量，而不是独立核心注册模板。Phase 2 默认不把它整体视为必需。

### `regedge.dli` — WebView2 EdgeUpdate 状态

- 30 行；
- 只有 3 个 section；
- 全部位于 EdgeUpdate `ClientState`。

模板声明 WebView2 版本 `115.0.1901.188`，并引用：

- `Installer\setup.exe`；
- `Application\msedge.exe`；
- `EBWebView` 根路径。

但当前 `auedgewebview.dll` 归档只有 3 个文件，并**不包含**前两者。

**判断：**旧包不是一个自洽的完整 WebView2 Runtime 安装源。Python 不应通过导入 `regedge.dli` 假装完整 Runtime 已安装。

### `vba.dli` — VBA Enabler + Microsoft Forms + Installer 痕迹

- 5836 行；
- 1460 个 section；
- 混合了：
  - AutoCAD VBA Enabler 状态；
  - VBA / VBE TypeLib；
  - Microsoft Forms 2.0 COM 类；
  - `FM20.DLL` TypeLib / Interface / CLSID；
  - Windows Installer 产品/组件记录。

已确认标准 `Forms.*` ProgID（包括 `Forms.Form.1`、Button、TextBox、ListBox、ComboBox 等）及大量 `Forms.HTML:*` 类型。

Microsoft Forms 2.0 TypeLib 明确指向 `C:\Windows\system32\FM20.DLL`。

**判断：**`vba.dli` 不是“一个 VBA 注册表文件”这么简单，它更像从官方 VBA Enabler 安装状态抓出的广泛快照。Python 后续应围绕“AutoCAD VBA 能实际运行”定义最小职责，而不是导入全部 Installer 痕迹。

### `unreg.dli` — 大范围删除模板

- 4161 行；
- 2066 个 section；
- 其中 **2006 个是删除 section**。

删除范围覆盖：

- Windows Installer Products / Features / UpgradeCodes / Components；
- COM / Interface / CLSID；
- Autodesk Installer；
- Forms.*；
- Shell Extension；
- AcSign 等。

**判断：**这是旧作者为了“彻底清理抓包安装状态”生成的大型删除清单，不适合作为 Python 卸载规范。Python 卸载应优先删除自己明确创建的状态。

---

## 9. 归档载荷职责地图

使用 `py7zr` 只读列目录，没有向系统解包。

### `default.dll`

- 3 个文件；
- 就是 `reg1.dli / reg2.dli / reg3.dli`。

因此它本质上是“默认注册模板快照”。

### `guanfang.dll`

- 169 个文件；
- 22 个目录；
- 未压缩总量约 9.8 MB；
- 主要是 CHS 下的 Support、Template、Plotters、Data Links 等官方/初始用户数据。

其中明确包含 `Support/Sample.cus`。

因此它本质上是“CHS 出厂基线包”。

### `Tohomedrive.dll`

仅 8 个文件：

- System32：`plotman.cpl`、`styleman.cpl`、`AcSignExt.dll`、`AcSignExtRes.dll`、`AcSignIcon.dll`、`AcSignOpt.exe`
- SysWOW64：`FM20.DLL`、`FM20chs.DLL`

**判断：**这个包把至少三类职责混在一起：打印/样式管理、数字签名 Shell、Forms 共享组件。Python 不应继续把它当单一功能整包部署。

### `app/VBA.dll`

- 17 个文件；
- 约 23 MB；
- 包含：
  - `AcVBA2024.Bundle`（`AcVba.arx`、`PackageContents.xml`、图标）；
  - VBA7.1 核心及中英文资源；
  - `VBE6EXT.OLB`；
  - System32 下的 `FM20.DLL / FM20chs.DLL / FM20enu.DLL`。

**判断：**这个包至少覆盖 AutoCAD VBA 插件、VBA Runtime、Microsoft Forms 三个子职责，应分别定义验收。

### `app/auedgewebview.dll`

只有 3 个文件：

- `msedgewebview2.exe.sig`
- `EBWebView/x64/EmbeddedBrowserWebView.dll`
- `msedgewebview2.exe`

**判断：**这是一个不完整的 Runtime 片段，不能单独支撑 `regedge.dli` 声明的完整 EdgeUpdate 安装状态。

---

## 10. 当前包中的可选/空操作职责

已扫描当前目录：

- 不存在 `installser.cmd`；
- 不存在 `unstallser.cmd`；
- 不存在 `myapp.cmd`；
- 不存在 `unmyapp.cmd`；
- 不存在 `0自定义配置文件` 目录。

因此这些 CMD 调用/复制动作在**当前这个 AutoCAD 2024.1.9 绿色完整版**中属于可选扩展点或静默 no-op，不能因为 CMD 中写了调用就自动列为当前产品必需功能。

另外：

`list.dll` 只有 22 字节，UTF-16 内容实际上只有：

`acad.exe`

所以当前“检测程序完整性=1”只证明主 `acad.exe` 存在，并不是严格意义上的完整性验证。

