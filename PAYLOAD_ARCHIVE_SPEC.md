# Payload Archive Specification

> Phase 1 静态理解文档。所有归档只做只读列目录，不执行旧安装器、不向系统解包。

## 1. 分析方法

`tools/analyze_payload_archives.py` 使用 Python `py7zr` 直接读取旧包中伪装为 `.dll` 的 7z 归档。

当前分析对象：

- `default.dll`
- `guanfang.dll`
- `Tohomedrive.dll`
- `app/VBA.dll`
- `app/auedgewebview.dll`

原始载荷不进入公开仓库，原始完整文件清单保存在本地 `analysis/`。

## 2. 总览

| 归档 | 文件数 | 解包后大小 | 当前职责判断 |
|---|---:|---:|---|
| `default.dll` | 3 | 3,070,426 B | 出厂注册模板基线 |
| `guanfang.dll` | 169 | 9,769,266 B | CHS / Support / Template / Plotters 出厂基线 |
| `Tohomedrive.dll` | 8 | 7,667,080 B | 少量系统级 Shell/绘图样式管理/旧 Forms 文件 |
| `VBA.dll` | 17 | 22,985,823 B | AutoCAD VBA Bundle + VBA 7.1 Runtime + Forms 2.0 |
| `auedgewebview.dll` | 3 | 9,160,429 B | WebView2 115.0.1901.188 的三个文件片段 |

## 3. `default.dll` — 注册模板出厂基线

只包含：

- `reg1.dli`
- `reg2.dli`
- `reg3.dli`

这与 CMD `:RECOVERY` 的行为一致：恢复时把这三个模板解回 ACAOE。

### Phase 1 结论

它不是程序 DLL，而是**三个注册表快照的压缩备份**。

Python 后续如果采用重新设计后的最小注册模型，就不必继续以该归档作为产品运行依赖；它最多保留为历史参考/恢复来源。

## 4. `guanfang.dll` — CHS 出厂基线

包含 169 个文件，主要分为：

- `Data Links`：1
- `Plotters`：28
- `Support`：59
- `Template`：81

典型内容：

- PC3 / CTB / STB / PMP；
- CUIX / MNR / DCL / PGP / PAT / LIN；
- ToolPalette / AuthorPalette；
- Profile AWS；
- DWT / DST / DWG / DGN 模板；
- `Support/Sample.cus`（136 B）。

### Phase 1 结论

`guanfang.dll` 的产品职责非常清晰：

> 提供一份可恢复的默认 CHS 用户资源基线。

这就是旧 CMD Recovery 删除当前 `chs` 后整包恢复的来源，也解释了 `Sample.cus` 为什么会被恢复出来。

Python 不一定要沿用“伪 DLL 7z”格式，但**CHS 基线恢复**本身属于真实产品能力。

## 5. `Tohomedrive.dll` — 8 个系统级文件

只有 8 个文件：

### `Windows/System32`

- `plotman.cpl`
- `styleman.cpl`
- `AcSignExt.dll`
- `AcSignExtRes.dll`
- `AcSignIcon.dll`
- `AcSignOpt.exe`

### `Windows/SysWOW64`

- `FM20.DLL`
- `FM20chs.DLL`

旧 CMD 使用 `-aoa` 把该包直接解到 `%HOMEDRIVE%`，因此这些目标可能被无条件覆盖。

### Phase 1 结论

这 8 个文件实际上混了至少三类完全不同的能力：

1. Plot/Style Manager 系统控制面板；
2. AutoCAD Digital Signature 的 Windows Shell 扩展；
3. 32 位 Forms 2.0 运行文件。

它不应再被当成一个不可分割的“必须部署包”。Python 应按功能分别决定是否需要。

## 6. `app/VBA.dll` — VBA 的真实文件载荷

包含 17 个文件。

### A. AutoCAD VBA Bundle

- `Program Files/Autodesk/ApplicationPlugins/AcVBA2024.Bundle/Contents/AcVba.arx`
- `PackageContents.xml`
- `vbaext.ico`

### B. Microsoft VBA Runtime

- `VBE6EXT.OLB`
- VBA 7.1：`VBE7.DLL`、`VBEUI.DLL`、`VBEUIRES.DLL`、`apc71.dll`
- 1033 / 2052 语言资源

### C. Microsoft Forms 2.0

- `Windows/System32/FM20.DLL`
- `FM20chs.DLL`
- `FM20enu.DLL`

### Phase 1 结论

VBA 不是一个单 DLL 功能，而是至少三个组件层：

1. AutoCAD 命令模块；
2. VBA 编辑/运行环境；
3. UserForm / Forms 2.0。

这与 `reg2.dli` + `vba.dli` 的注册表分层能互相对应。

Python 后续应根据“我们承诺怎样的 VBA 能力”决定最小部署，而不是简单重演 `7za x VBA.dll -o%HOMEDRIVE%`。

## 7. `app/auedgewebview.dll` — 不完整的 WebView2 片段

只有 3 个文件，而且版本固定为 `115.0.1901.188`：

- `msedgewebview2.exe.sig`
- `EBWebView/x64/EmbeddedBrowserWebView.dll`
- `msedgewebview2.exe`

### 与 `regedge.dli` 对照

`regedge.dli` 却声明了：

- `Installer/setup.exe`
- `Application/msedge.exe`
- EdgeUpdate ClientState
- 安装成功状态

这些关键文件并不在该三文件归档中。

### Phase 1 结论

旧方案不是一个完整的 WebView2 Runtime 安装器，而更像：

> 从某台已安装机器复制少量运行文件，再恢复一份 EdgeUpdate 状态快照。

因此 Python MVP **不应把“复制这 3 个文件 + 写 regedge.dli”视为正确 WebView2 安装**。

## 8. 资源与注册表的依赖映射

目前已经形成下列关系：

| 功能 | 文件来源 | 注册来源 |
|---|---|---|
| AutoCAD 核心 Applications | AutoCAD 主目录 | `reg2.dli` |
| 用户 Profile / 图形设置 | CHS + 当前用户状态 | `reg1.dli` / `reg4.dli` |
| CHS 默认资源 | `guanfang.dll` | `reg1.dli` 中部分路径/偏好 |
| VBA AutoCAD 模块 | `VBA.dll` | `reg2.dli` 的 `AcadVBA` |
| VBA Runtime | `VBA.dll` | `vba.dli` |
| Forms 2.0 | `VBA.dll` + `Tohomedrive.dll` 中不同位数文件 | `vba.dli` |
| AcSign Shell | `Tohomedrive.dll` | `reg3.dli` / `unreg.dli` |
| WebView2 | `auedgewebview.dll`（仅片段） | `regedge.dli` + `reg3.dli` 中相关状态 |

## 9. 对 MVP 的直接启示

这轮资源分析进一步证明：

> 旧 CMD 的“归档文件名”不是好的产品模块边界。

例如 `Tohomedrive.dll` 同时装 AcSign、Plot Manager 和 FM20；`vba.dli` 同时记录 VBA、Forms 和大量 MSI bookkeeping。

新的 Python 架构应该按**功能能力**建模，而不是按旧包文件名建模。

## 10. 下一步

Phase 1 继续完成：

1. CHS 当前目录与 `guanfang.dll` 基线的差异；
2. AutoCAD 主目录中 `reg2.dli` 所引用 loader 的存在性与功能分组；
3. `reg3.dli` 里真正值得 MVP 保留的文件关联 / COM / Shell 能力；
4. Shortcut / Junction / 自定义配置的输入输出契约；
5. 然后开始 Phase 2：写 `PYTHON_FUNCTIONAL_REQUIREMENTS.md`。
