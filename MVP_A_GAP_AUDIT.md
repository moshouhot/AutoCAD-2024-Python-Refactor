# MVP-A Gap Audit

> 2026-09-21。目标：把 `PYTHON_FUNCTIONAL_REQUIREMENTS.md` 的 MVP-A（FR-01 ~ FR-12）逐条对照当前候选实现，区分“代码已实现”“non-live 已验证”“必须等专用环境 live 验证”。

## 结论

当前没有发现需要推翻架构的缺口。

MVP-A 的代码/非 live 主体已经基本齐全；剩余关键问题集中在**真机充分性验证**，不是继续机械复制 CMD：

1. 当前精选 Core registry allowlist 是否足够让 AutoCAD 2024 稳定启动；
2. `DwgCommon / Drawing Check / Hardcopy / ObjectDBX` 是否全部必要；
3. `0加载应用程序` 是否在真实启动中自动加载；
4. repeat install / uninstall 是否在专用环境中闭环；
5. 当前主机 D:/E:/F: 混合注册状态不能再作为最终证据。

最终 live 验收使用**一个长期独立 CAD 2024 测试 Windows 环境**，不要求每轮创建快照。

---

## FR 对照表

| FR | 要求 | 当前状态 | 证据 / 剩余项 |
|---|---|---|---|
| FR-01 | Package discovery | **PASS (non-live)** | `PackageLayout.discover()` 要求 `acad.exe`、ACAOE/CHS、reg1/2/3、配置、两个 LSP、`0加载应用程序`；缺失输入有测试。 |
| FR-02 | Status / preflight | **PASS (non-live)** | Windows/admin/.NET、autoload chain 已实现；reg2 版本门禁只接受**活动 HKLM Autodesk AutoCAD 根**下唯一的 `R24.3`，无法解析、其他版本、deleted-only 或无关 registry root 均 fail-fast；CLI 会干净返回 `ERROR` 而不是 traceback。 |
| FR-03 | AutoCAD core registry | **CANDIDATE / LIVE-BLOCKED** | reg1 + reg2 + 显式 reg3 Core allowlist；整份 reg3/regedge/vba/unreg 被排除。`AutoCAD.Application` 有真实缺口证据；其余候选组尚待专用环境验证充分性/必要性。 |
| FR-04 | Path rebasing | **PASS (non-live)** | structured rebasing + unresolved legacy audit。现包模板存在 `D:\00`、旧用户、`ADMINI~1/PROGRA~` 痕迹，但当前最终 plan 中这些已全部为 0 残留。 |
| FR-05 | CHS Junction | **PASS (non-live)** | AppData + LocalAppData 两个 `chs` → 包内 CHS；Fake + Windows temp junction 测试通过；冲突目录/Junction fail-closed。 |
| FR-06 | CHS baseline / recovery semantics | **PASS for MVP-A** | 普通 install 不 reset CHS；`guanfang.dll` recovery 明确后置为主动功能，不是普通安装副作用。 |
| FR-07 | Desktop shortcut | **PASS (non-live)** | target=current `acad.exe`，arguments=`/nologo`，Desktop 使用 Windows User Shell Folder 解析；真实 temp shortcut 创建测试通过。最终“能启动 CAD”属于 live。 |
| FR-08 | Plotter/style wizard shortcuts | **PASS (non-live)** | plan 创建两个 CHS wizard shortcut；目标文件存在性由 plan audit 检查。最终用户点击验证可随 live 一并做。 |
| FR-09 | Auto-load extensions | **PARTIAL / LIVE-BLOCKED** | 静态链路已证实：`acad2024.lsp` → `appload.lsp` → `0加载应用程序`，支持 LSP/FAS/VLX/ARX；真实 AutoCAD 启动时自动加载仍需 live marker 证明。.NET DLL 明确后置。 |
| FR-10 | Optional custom config | **N/A for current package** | 当前包没有 `0自定义配置文件`；按规范不是 MVP 必需输入。 |
| FR-11 | Install metadata | **PASS** | `.python-installer-state.json` 记录 install payload、registry journal、junction/shortcut ownership，用于 status/uninstall。 |
| FR-12 | Owned uninstall | **PASS (non-live), LIVE pending** | 重复 install 保留首次 before；uninstall 恢复原值；外部改过的 registry/shortcut 产生 conflict 并保留外部状态；不执行 unreg/System32/Forms/AcSign 清理。最终真实 uninstall 仍需专用环境闭环。 |

---

## 本轮新修复

### G-01 — Registry version 静默兜底

**问题**：`InstallPlanner` 原来在 `reg2.dli` 无法解析 `Rxx.x` 时自动使用 `R24.3`。

这违反 FR-02，因为错误/不匹配模板可能被伪装成合法 AutoCAD 2024 plan。

**修复**：

- 无法从 `reg2.dli` key 解析版本时抛 `PackageError`；
- 版本证据必须来自活动的 `HKEY_LOCAL_MACHINE\\SOFTWARE\\Autodesk\\AutoCAD\\...` 产品树，不能由其他 hive/vendor 下碰巧含 `\\AutoCAD\\R24.3` 的键满足；
- CLI 在 plan/install/diff 路径统一捕获 `PackageError`，输出明确 `ERROR` 并返回 2；
- 增加负向回归测试。

当前全量：**39 passed**。

---

## 当前不应继续扩展的方向

在 MVP-A live 闭环前，不因为旧 CMD 中存在就继续加入：

- VBA / FM20 / Forms；
- WebView2 legacy payload；
- AcSign Shell；
- System32 plot/style CPL；
- taskbar pin；
- Recovery/Backup 完整产品化；
- 制包工具链；
- 为了“安全完美”额外建设大型事务/并发框架。

这些都不是当前 Core blocker。

---

## 下一阶段门槛

代码层面的下一步不是继续扩大功能，而是：

1. 维持 Core plan `warnings = 0 / audit findings = 0`；
2. CI / CodeQL 保持全绿；
3. 在专用 CAD 2024 测试环境建立只读 baseline；
4. 集中执行一次完整 live acceptance：install → AutoCAD 启动 → CHS → shortcut → auto-load → repeat install → uninstall；
5. 只有真实运行暴露明确缺口时，才继续调整 Core allowlist。

在此之前，`MVP-A = CODE/NON-LIVE READY, LIVE BLOCKED`。

