# Handoff

## 一句话结论

**MVP-A Core 已完成并闭环。** Trial 6 已取得 fresh install、真实 AutoCAD 启动、命令执行、LSP autoload、repeat install、owned uninstall 的完整 live 证据；PR #2 与最终文档 PR #3 均已合并到 `main`。当前工作应进入 **MVP-B：VBA 基础能力**，不要再把已解决的 Core registry 启动问题当作 blocker。

## 1. 已完成状态

- `main` 当前包含 MVP-A 最终闭环，历史关键 merge：
  - PR #2 merge：`23f1075a4e1bbd0cde0ce88e35772adf2b69c4ef`
  - PR #3 merge：`aff5ecc0feb394b1068e9db85adbcaea7340d3e8`
- Trial 6：`MVP-A Core live functional closure = PASS`。
- Python installer 已证明：
  - clean install PASS；
  - AutoCAD 2024 真机进入 `Drawing1.dwg`；
  - COM 命令探针可执行；
  - `0加载应用程序` LSP autoload PASS；
  - repeat install 幂等；
  - owned uninstall 0 conflict。
- 最终第三方审计链：CI / CodeQL / Sourcery / Codex 均通过。

## 2. 当前工作分支

`mvp-b/vba-foundation`

该分支从 `main@aff5ecc` 创建，用于 MVP-B VBA 基础能力开发。

## 3. MVP-B 当前目标

先实现 **VBA 基础能力**，不默认扩大到 Forms 2.0：

1. 部署 `AcVBA2024.Bundle`；
2. 部署 Microsoft VBA 7.1 Runtime；
3. 恢复 `AcadVBA` AutoCAD 注册；
4. 真机验收：`VBALOAD`、`VBAIDE`、普通宏运行。

`UserForm / Forms 2.0` 暂作为后续独立能力；只有基础 VBA 已闭环且有直接运行证据时再决定是否纳入本阶段。

## 4. 已确认的输入事实

- `配置.txt` 使用 `gb18030`，现有开关：`安装 VBA编程=1`。
- `AutoCAD 2024/ACAOE/app/VBA.dll` 是 7z 归档，密码由既有分析工具按 `zzz` 读取。
- 归档含 17 个文件，主要分三组：
  - `Program Files/Autodesk/ApplicationPlugins/AcVBA2024.Bundle/...`
  - `Program Files/Common Files/microsoft shared/VBA/VBA7.1/...` + `VBE6EXT.OLB`
  - `Windows/System32/FM20*.DLL`
- 本阶段默认只取前两组；`FM20*.DLL` 属于 Forms 2.0，不应随基础 VBA 无条件写入 System32。
- `reg2.dli` 已包含 `...Applications\\AcadVBA`，Core planner 当前明确排除它。
- `vba.dli` 同时混有 VBA Runtime、Forms 2.0 和大量 MSI bookkeeping，**禁止整份导入**。

## 5. 实现原则

- Core 默认行为必须保持不变；VBA 由 `安装 VBA编程` 开关独立控制。
- 归档按明确 allowlist 解包，不做整包 `-aoa` 式覆盖。
- 文件写入必须进入 ownership journal；uninstall 只能恢复/删除本安装器拥有的文件。
- `vba.dli` 只允许显式 VBA Runtime allowlist；禁止带入 MSI/Installer、Forms 2.0、Shell/WebView2 等状态。
- 修改后先跑 non-live 单测与 plan audit，再进入真机。

## 6. 下一步

1. 为安装计划增加“受控文件部署”操作与文件 ownership journal。
2. 增加 `PackageLayout` 对 `VBA.dll` / `vba.dli` 的发现。
3. 实现 VBA Bundle + VBA 7.1 的文件 allowlist。
4. 将 `reg2` 的 `AcadVBA` 仅在 VBA 开启时加入计划。
5. 从 `vba.dli` 提炼 VBA Runtime 最小 registry allowlist，并以负向测试确保 Forms/MSI 不进入。
6. non-live 全绿后，再做真实 `VBALOAD / VBAIDE / 宏运行` 验收。

## 7. 不要做的事

- 不再重做 MVP-A 启动注册表 trace；该 blocker 已在 Trial 5/6 解决。
- 不整份导入 `vba.dli`。
- 不把 `FM20*.DLL` 默认写入 System32。
- 不模拟 MSI bookkeeping，除非后续 live trace 证明功能必需。
- 不进入 WebView2 / AcSign Shell / plot-style CPL / taskbar pin。

