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
| 当前快捷方式 | 0 | 当前目录/当前上下文快捷方式，待确认 |
| 固定到任务栏 | 1 | 固定 AutoCAD 到任务栏 |
| 恢复原始数据 | 0 | 执行恢复流程 |
| 完全卸载程序 | 1 | 启用完整卸载行为 |
| 安装自定义配置 | 1 | 合并用户自定义配置 |
| 检测程序完整性 | 1 | 安装前/中进行文件完整性检查 |
| 跳过网络验证 | 0 | 是否绕过网络检查，具体目的待确认 |

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
| F01 | 启动与权限 | UAC、管理员权限、系统环境发现 | 分析中 |
| F02 | AutoCAD 路径/版本发现 | 从注册表和目录推导 AutoCAD 根路径、共享目录、用户目录 | 分析中 |
| F03 | 安装主流程 | 安装前清理、目录准备、注册、依赖、快捷方式等 | 分析中 |
| F04 | 注册表 | 导入 `reg*.dli`，重写与当前路径有关的值 | 分析中 |
| F05 | CHS / 中文用户数据 | CHS 目录、Support、Template、Plotters、`Sample.cus` 等 | 已确认存在，待完整拆分 |
| F06 | VBA | VBA 文件、AcadVBA 注册、Forms/FM20 等 | 已确认存在，待重新定义产品边界 |
| F07 | WebView2 | `auedgewebview.dll` + `regedge.dli` | 待确认真实用途和是否属于 MVP |
| F08 | Shell / AcSign / 系统辅助组件 | `Tohomedrive.dll` 等系统级载荷 | 待确认真实用户功能 |
| F09 | Shortcut / Pin | 桌面快捷方式、其他快捷方式、任务栏固定 | 分析中 |
| F10 | Junction / 路径适配 | 将用户目录/CHS 等映射到绿色包目录 | 分析中 |
| F11 | 自定义配置 | `0自定义配置文件` 等配置合并 | 分析中 |
| F12 | 完整性 / 网络前置检查 | .NET、文件列表、网络验证 | 分析中 |
| F13 | 卸载 | 注册表、目录、快捷方式及共享组件清理 | 分析中 |
| F14 | 备份 | 注册表/配置备份 | 分析中 |
| F15 | Repair / Recovery | `default.dll` / `guanfang.dll` 恢复默认数据 | 分析中 |
| F16 | 制作绿色包工具链 | REG→DLI、CHS/REG 打包、提取/复制等 | 待判断是否完全排除出 Python MVP |

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

## 7. 下一批待分析

按以下顺序继续：

1. `:INSTALL` 完整控制流；
2. 安装过程中实际导入的 `reg*.dli` 和路径重写；
3. `guanfang.dll` / `default.dll` 与 CHS；
4. `VBA.dll` / `vba.dli`；
5. `Tohomedrive.dll`；
6. `auedgewebview.dll` / `regedge.dli`；
7. Shortcut / Junction / 自定义配置；
8. `:UNINSTALL`；
9. `:BACKUP` / `:RECOVERY`；
10. 将制包工具链与运行时安装职责彻底分开。

