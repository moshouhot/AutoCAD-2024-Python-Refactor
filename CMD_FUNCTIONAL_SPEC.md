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

