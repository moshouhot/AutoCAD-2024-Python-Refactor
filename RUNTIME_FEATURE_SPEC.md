# Runtime Feature Specification

> Phase 1 补充：把 CMD 运行时功能还原成明确的输入/输出契约。

## 1. CHS：当前状态与出厂基线是两回事

`guanfang.dll` 出厂基线包含 **169 个文件**。

当前 `ACAOE/CHS` 有 **170 个文件**，与基线比较：

- 基线缺失于当前：6 个；
- 当前额外：7 个；
- 同名但大小变化：5 个。

当前缺少的基线项主要是旧 AppManager / FeaturedApps CUIX/MNR；当前额外项包括：

- `acad2024.cfg`
- `AcLivePreviewContext.dll`
- `ContextualTabSelectorRules.dll`
- `DAP`
- GraphicsCache
- `AutoCorrectorCounterfile.xml`
- `CommandAutoCorrectDic.cus`

大小变化项包括 Profile、CUIX、命令权重 XML 和两个向导快捷方式。

### 产品含义

必须把两种功能分开：

1. **日常安装**：当前 CHS 是用户/运行状态，应尽量保留。
2. **Recovery / Reset**：明确要求恢复出厂状态时，才使用 `guanfang.dll` 基线替换。

旧 CMD 的 Recovery 是“整目录删除后恢复”，但 Python 是否沿用这种破坏性策略留到 Phase 2。

## 2. Junction：绿色版用户数据定位

旧 CMD 在安装时创建：

- `%LOCALAPPDATA%\Autodesk\<Product>\<Version>\chs`
- `%APPDATA%\Autodesk\<Product>\<Version>\chs`

两个路径都通过目录 Junction 指向：

`ACAOE\CHS`

### 产品含义

这是旧绿色版的核心机制之一：

> 让 AutoCAD 仍然看到标准 AppData 路径，但真实用户数据保存在绿色包内。

该能力属于 Python MVP 候选，而不是 CMD 偶然副作用。

## 3. 快捷方式

旧 CMD 创建/维护三类快捷方式：

1. 桌面 AutoCAD 快捷方式：目标 `acad.exe`，参数 `/nologo`。
2. 可选“当前目录”快捷方式：放在绿色包外层目录。
3. CHS 下两个向导快捷方式：
   - 添加绘图仪向导 → `addplwiz.exe /language zh-cn`
   - 添加打印样式表向导 → `styshwiz.exe`

桌面目录优先读取 `User Shell Folders\Desktop`，失败后逐级回退。

任务栏固定通过私有 `Pintf.dll` 完成，属于单独的 Shell 集成功能，不应和“创建快捷方式”混成一个能力。

## 4. 自定义配置

旧 CMD 在配置开启时执行：

`XCOPY /S /E /Y /U <AutoCADRoot>\0自定义配置文件\*.* ACAOE\CHS\`

`/U` 的语义使它只更新目标中已经存在的同名文件，而不是任意添加新文件。

### 当前包事实

当前 `AutoCAD 2024` 根目录**不存在 `0自定义配置文件`**。

因此即使配置中 `安装自定义配置=1`，对这份包来说实际是 no-op。

### 产品含义

这是一个可选“覆盖已有 CHS 配置”的机制，不是当前包 MVP 的必需输入。

## 5. 自动加载 `0加载应用程序`

当前包明确提供：

- `Support/acad2024.lsp`
- `Support/appload.lsp`
- 根目录 `0加载应用程序/`

`acad2024.lsp` 末尾会：

`(load "appload.lsp")`

`appload.lsp` 会：

1. 把 `<AutoCADRoot>\0加载应用程序` 加入 `ACAD` 搜索路径；
2. 枚举该目录第一层文件；
3. 自动加载 ARX、LSP、FAS、VLX；
4. 还尝试支持 .NET DLL，但旧代码的 DLL `wcmatch` 模式存在明显实现瑕疵。

目录自带说明明确写着：

> 将应用程序丢进本文件夹后，启动 CAD 可自动加载。

### 产品含义

这是明确的用户功能，应保留“自动加载扩展目录”的能力；Python 不需要复制旧 LSP 的匹配 bug。

## 6. AutoCAD Application loaders 与文件覆盖关系

对 `reg2.dli` 的 `Applications` 做静态覆盖检查：

- loader 总数：**279**；
- AutoCAD 根目录绝对路径：171；
- 相对路径：106；
- 外部 `ApplicationPlugins`：1（AcadVBA）；
- 虚拟协议：1（`WebFeature://...`）；
- 在映射到当前包后，文件型 loader 缺失：**0**。

### 产品含义

`reg2.dli` 的 AutoCAD Applications 部分和当前绿色包文件具有高度一致性，说明它不是随机残留，而是 AutoCAD 主程序功能注册的重要来源。

但是 Python 仍然应该只使用 AutoCAD 产品树中明确需要的部分，而不是因此接受 `reg3.dli` 等全局系统快照。

## 7. 外部可选脚本

CMD 安装/卸载过程中会静默尝试：

- `installser.cmd`
- `unstallser.cmd`
- `myapp.cmd`
- `unmyapp.cmd`

当前包中这四个文件**全部不存在**。

因此对当前产品而言它们不是实际运行职责，Python MVP 无需为不存在的 hook 设计兼容层。

## 8. .NET 检查

旧 `CHECKNET` 检查的是：

`HKLM\Microsoft\NET Framework Setup\NDP\v4\Full\Release`

并要求至少 .NET Framework 4.7 对应 release。

它不是“网络检查”。

Python 可以保留“运行条件检查”的产品目的，但无需沿用 `CHECKNET` 这个误导命名。

## 9. 当前包不存在 PackageManifest

当前 `AutoCAD 2024.1.9 绿色完整版` 中没有 `PackageManifest.json`。

因此新的 Python MVP 不能依赖旧项目曾经使用过的 manifest 结构，必须根据当前包实际结构建立自己的最小 package contract。

