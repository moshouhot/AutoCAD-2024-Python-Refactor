# Registry Template Specification

> Phase 1 静态理解文档。这里记录 `.dli` 模板实际承担的职责，不把任何模板整体视为 Python 必须照搬的规范。

## 1. 分析方法

本项目新增两个只读工具：

- `tools/analyze_registry_templates.py`：统计 section/value/root、提取文件引用并按已知职责做启发式分类。
- `tools/query_registry_template.py`：按关键字查询本地 `.dli` 的 section 和值，用于人工复核。

原始 `.dli` 只存在于本地参考包，不上传公开仓库。

当前 7 个模板合计：

- **11,946 个 registry sections**；
- **18,999 个 values**；
- 涵盖 HKCU、HKLM、Classes、Installer、Shell、COM、VBA、WebView2 等多个完全不同的职责。

因此旧做法 `FOR %%a IN (reg*.dli) DO REGEDIT /S %%a` 本质上是在恢复一大份“抓包后的机器状态”，而不是表达一个最小、清晰的 AutoCAD 安装契约。

## 2. 模板角色总览

| 模板 | Sections | Values | 根 | 当前角色判断 |
|---|---:|---:|---|---|
| `reg1.dli` | 322 | 1,079 | HKCU | 当前用户 AutoCAD 配置、Profile、3DGS、用户级 Applications 等 |
| `reg2.dli` | 2,479 | 7,545 | HKLM | AutoCAD 产品级注册、ARX/CRX/DBX Applications、产品路径、VBA loader 等 |
| `reg3.dli` | 5,591 | 8,163 | HKCU + HKLM | Windows/COM/Shell/文件关联/Installer/WebView2/共享组件等大范围系统集成快照 |
| `reg4.dli` | 25 | 19 | HKCU + HKLM | 小规模人工定制/覆盖项，例如命令行颜色、Activity Insights、AcMr loader |
| `regedge.dli` | 3 | 23 | HKLM | Microsoft Edge WebView2 Runtime 115.0.1901.188 的 EdgeUpdate ClientState 快照 |
| `vba.dli` | 1,460 | 2,156 | HKLM | AutoCAD VBA Enabler + Microsoft VBA 7.1 + Forms 2.0 + MSI/Installer 元数据 |
| `unreg.dli` | 2,066 | 14 | HKLM + HKCU | 大范围删除模板；其中 2,006 个 section 是删除指令 |

## 3. `reg1.dli` — 用户侧 AutoCAD 状态

全部 322 个 section 位于：

`HKEY_CURRENT_USER\SOFTWARE\Autodesk\AutoCAD\...`

已确认包含：

- 当前产品版本与子版本；
- 3DGS / GPU Certification / Effects 图形设置；
- Profiles；
- 用户级 Applications；
- UI、General、命令行等用户配置；
- 一些 AppManager / Cloud 插件历史路径。

**当前判断：**`reg1.dli` 更像某台已经配置过的 AutoCAD 的 HKCU 快照，而不是安装 AutoCAD 必须原样导入的注册表。

Phase 2 需要继续区分：

1. AutoCAD 首次启动不能自动生成、必须预置的最小用户状态；
2. 绿色版为了把用户数据定位到包内而必须写的路径；
3. 纯偏好设置；
4. 历史机器/插件残留。

第 3、4 类不应默认进入 MVP。

## 4. `reg2.dli` — AutoCAD 产品级注册

全部 2,479 个 section 位于 HKLM。

大量内容位于：

`HKLM\SOFTWARE\Autodesk\AutoCAD\R24.3\ACAD-7101\Applications\...`

用于告诉 AutoCAD 各个内建 ARX/CRX/DBX 模块：

- 模块名称；
- loader 路径；
- `LOADCTRLS`；
- Commands；
- Groups。

### VBA 的关键桥接

`reg2.dli` 明确包含：

`...\ACAD-7101:804\Applications\AcadVBA`

其 loader 指向：

`C:\Program Files\Autodesk\ApplicationPlugins\AcVBA2024.Bundle\Contents\AcVBA.arx`

并注册 `VBAIDE`、`VBALOAD`、`VBARUN` 等命令。

这说明 VBA 至少有两层：

1. AutoCAD 自己知道 `AcadVBA` 模块存在；
2. VBA Runtime / COM / Forms 运行环境本身存在。

这两层不能再混成“导一个 vba.dli 就算 VBA 安装完成”。

### AcSign

`reg2.dli` 还包含 `AcadSign` 应用模块，loader 指向 AutoCAD 主目录的 `AcSign.arx`。这与 Windows Explorer 的 AcSign Shell 扩展相关，但不是同一层职责。

## 5. `reg3.dli` — 系统集成大快照

这是最不适合整体照搬的模板。

统计特征：

- 5,591 sections；
- 8,163 values；
- HKCU 278；
- HKLM 5,313。

静态分类已经命中：

- Shell extension；
- DWG 等文件关联；
- Property System；
- AcSign；
- WebView2 / EdgeUpdate；
- Windows Installer 元数据；
- AutoCAD core；
- 部分 VBA / 32-bit server。

还包含 Autodesk Genuine Service、CER、Microsoft EdgeUpdate、Windows Installer 等明显属于**机器安装状态**而不是“绿色版自身最小功能”的信息。

**Phase 1 结论：**`reg3.dli` 应被视为官方安装/抓包过程中捕获到的 Windows 系统集成快照。

Python 后续应按能力拆分，例如：

- DWG 文件关联；
- AutoCAD COM / TypeLib；
- Shell Extension；
- AcSign Windows Shell 集成；
- Property System；
- 其他必要共享组件。

每项再独立决定是否进入 MVP，而不是整体 `REGEDIT /S reg3.dli`。

## 6. `reg4.dli` — 人工覆盖/定制层

只有 25 个 section。

已确认包含：

- Activity Insights 相关状态；
- `AcMr.dll` 用户级 loader；
- 自定义命令行/文本窗口颜色；
- `CustomColors` 等偏好项。

**Phase 1 结论：**它更像作者的个性化/精简定制层，不是 AutoCAD 基础安装规范。除非产品明确要求这些默认偏好，否则大部分不应进入 Python MVP。

## 7. `regedge.dli` — WebView2 安装状态快照

只有 3 个 section，全部位于：

`HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\ClientState\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}`

里面硬编码：

- WebView2 版本 `115.0.1901.188`；
- `UninstallString`；
- `EBWebView` 路径；
- installer result；
- EdgeUpdate cohort；
- 当前状态。

**Phase 1 结论：**这是 Microsoft EdgeUpdate 的安装状态记录，不是 WebView2 Runtime 的完整部署契约。

Python 后续如果需要 WebView2，合理方向应该是：

1. 检测现有 Runtime 是否满足；或
2. 使用完整、明确的 Runtime 部署来源。

不应通过伪造 EdgeUpdate ClientState 来“假装已经安装”。

## 8. `vba.dli` — VBA + Forms + MSI 状态混合快照

统计特征：

- 1,460 sections；
- 2,156 values；
- 551 个 section 被静态规则识别为 Forms 2.0 相关；
- 267 个 section 属于 Installer/MSI 元数据类；
- 21 个 section 明确体现 VBA 产品信息。

已确认有三个层次：

### A. AutoCAD VBA Enabler 产品标识

包含：

`HKLM\SOFTWARE\Autodesk\AutoCAD\R24.3\AutoCAD 2024 VBA Enabler`

### B. Microsoft VBA 7.1 Runtime

引用 `VBE7.DLL`、`VBEUI.DLL`、`APC71ITL.DLL`、多语言资源和 `VBE6EXT.OLB`，同时还保存大量 Installer bookkeeping。

### C. Microsoft Forms 2.0

大量 CLSID / Interface / TypeLib / `InprocServer32` 指向：

`C:\Windows\system32\FM20.DLL`

并引用多语言 FM20 资源。

**Phase 1 结论：**`vba.dli` 更像官方 VBA Enabler 安装后的完整注册表抓取，不是 Python 应整体导入的最小模板。

Python 产品需求应拆成：

1. AutoCAD VBA 模块；
2. Microsoft VBA Runtime；
3. UserForm / Forms 2.0；
4. 是否需要模拟 MSI/Installer bookkeeping。

第 4 项很可能不是 MVP 用户功能，但等 Phase 2 再正式决定。

## 9. `unreg.dli` — 不能直接移植的破坏性清理模板

2,066 个 section 中有 **2,006 个是删除 section**。

它不只是删除本项目写入的少量键，还覆盖：

- Windows Installer Products / Components / UpgradeCodes；
- Forms 2.0 TypeLib / Interface；
- AcSign；
- Shell Extensions；
- 文件关联；
- AutoCAD HKLM/HKCU 主树；
- 共享 DLL / Shell 状态。

**Phase 1 结论：**`unreg.dli` 是“尽可能把抓包安装状态清掉”的历史工具，不适合作为 Python 卸载器规格。

Python MVP 卸载原则更应接近：

> 删除 Python 安装器明确创建/拥有的状态；对共享系统组件和已有用户状态默认保守。

具体边界留到 Phase 2。

## 10. 对 Python 重构的直接影响

通过这轮注册表解剖，已经可以否定一个旧假设：

> “把 `reg1~4.dli + regedge.dli + vba.dli` 正确改路径后全部导入，就等于正确安装。”

更合理的 Python 注册层应该按**能力**组织，而不是按旧文件组织，例如：

- AutoCAD core；
- AutoCAD applications；
- user profile；
- file associations；
- COM / TypeLib；
- VBA；
- Forms 2.0；
- Shell integration。

这些只是功能模型，不是现在就固定代码目录。

真正进入 MVP 的最小集合，要在 Phase 2 基于用户功能决定。

## 11. 仍需继续核实

1. `reg1.dli` 中哪些 HKCU 值是 AutoCAD 第一次启动可自动生成的，哪些必须预置。
2. `reg2.dli` 中哪些 `Applications` loader 属于主程序实际需要的内建模块。
3. `reg3.dli` 的 COM / TypeLib / 文件关联 / Shell 能力各自的最小集合。
4. VBA Runtime / Forms 2.0 真实文件与注册表的对应关系。
5. `Tohomedrive.dll` 和 `VBA.dll` 的实际文件清单，与上述模板建立依赖映射。
