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

## 8. MVP-B live 最新证据（2026-09-22）

### 已冻结正式候选

- 分支：`mvp-b/vba-foundation`
- non-live 候选提交：`99981f9 feat: add guarded VBA foundation`
- 该候选已通过：
  - `47 passed`；
  - plan / audit 0 finding；
  - VBA files `14 same / 0 create / 0 conflict`；
  - fresh live install 成功，install 后 diff 全 same / 0 conflict。

### VBA Runtime 已真正执行成功

在临时仅创建 VBA Enabler MSI Product identity 的 A/B 下：

- `MsiQueryProductState`：`-1 UNKNOWN -> 1 ADVERTISED`；
- “AutoCAD VBA 当前尚未安装”弹窗消失；
- `VBASTMT` 真正执行成功，`USERR1 -> 23.456`。

因此基础 VBA Runtime / AcVBA 命令链不是假通过。

### LoadDVB / VBALOAD 仍阻塞

- 外部 `Application.LoadDVB(drawline.dvb)` 长时间阻塞；
- AutoCAD 内部 `VBALOAD` 同一个 Autodesk sample 也长时间阻塞；
- 因此已排除“只是外部 COM probe/消息泵问题”。
- 窗口枚举没有“VBA 尚未安装”或明显安全提示。

### Forms 文件缺失已排除

当前 `C:\Windows\System32`：

- `FM20.DLL`
- `FM20chs.DLL`
- `FM20enu.DLL`

与 `VBA.dll` 归档内三个文件 SHA-256 完全一致。

### MSI Product / Feature / Component 已最小化

VBA Enabler：

- ProductCode：`{28B89EEF-7155-0409-0100-CF3F3A09B77D}`
- packed product：`FEE98B82551790401000FCF3A3907BD7`
- `AcVba.arx` component：
  - GUID：`{AEE576D1-AA16-4620-82C4-6C09437C48FF}`
  - packed：`1D675EEA61AA0264284CC69034C784FF`

严格可回滚 API A/B 已证明：

1. baseline：
   - Product = unknown；
   - `MsiGetProductCodeA(AcVba component)` = `1607`。
2. 只加空 Product key：
   - Product = `ADVERTISED(1)`；
   - `MsiGetProductCodeA` 仍 `1607`。
3. 再只加 AcVba Component mapping：
   - `MsiGetProductCodeA` = `0`；
   - 返回正确 VBA Enabler ProductCode；
   - `MsiGetComponentPath` 返回 `AcVba.arx`，state=`3`（component local）。
4. 再加 `Classes\Installer\Features`：
   - feature `P` / `Registry_Feature` = `ADVERTISED(1)`。
5. UserData Features 与空 InstallProperties 不会把 feature 变 local。
6. `InstallProperties\WindowsInstaller=1` 会把 Product 从 `1` 提升到 `5`（installed/default），但 feature 仍为 `1` advertised。
7. `LocalPackage=C:\Windows\Installer\57e86.msi` 在原始 `vba.dli` 中存在，但当前该文件不存在；**不要为了伪造 local state 无脑写入这个不存在的 cached MSI 路径。**

### vba.dli MSI 产品现状

`vba.dli` 共记录 14 个 MSI Product。

当前本机已经存在：

- Microsoft Visual Basic for Applications 7.1 (x64) 基础 Runtime；
- Microsoft Visual Basic for Applications 7.1 (x64) Chinese (Simplified)。

当前缺失的是 **AutoCAD 2024 VBA Enabler 的 Windows Installer Product/Feature/Component 图谱**；所以 LoadDVB blocker 优先看 Enabler，而不是 VBA7 Runtime 本身。

### AcVba.arx 静态证据

`AcVba.arx` 包含动态 MSI API 名：

- `MsiGetProductCodeA`
- `MsiProvideComponentA`
- `MsiProvideQualifiedComponentA`
- `MsiReinstallFeatureA`

它没有直接硬编码 VBA Enabler ProductCode。

这与当前优先假设一致：`LoadDVB/VBALOAD` 进入 VBA 工程链后触发 Feature/Component provide/self-repair，因为 Enabler feature 仍处于 advertised 或 graph 不完整而发生等待/源解析。

### 当前系统清理状态

最后一次实验结束后已复核：

- packed VBA Enabler Product key：不存在；
- `MsiQueryProductState`：`-1`；
- owned AutoCAD 测试 PID：已退出。

### 已下放给本地 AI 的长耗时任务

任务文件：`LOCAL_AI_VBA_LOADDVB_TASK.md`

本地 AI 只负责：

- 在 `LoadDVB/VBALOAD` 阻塞时间窗抓 `MsiGetProductCode / MsiProvideComponent / MsiProvideQualifiedComponent / MsiReinstallFeature` 的**真实实参 + 返回值**；
- 明确 ProductCode / Feature / Component / install mode；
- 不修改正式 `src`；
- 不导入整份 `vba.dli`；
- 强制清理临时 Product gate 与 owned CAD PID。

## 9. 下一步决策点

等待本地 AI trace 的关键结果：**AcVba 实际请求哪个 Feature/Component，以及 `MsiProvide*` 的 install mode。**

- 若 trace 指向已证明的 AcVba component + `P` feature：做最小 Feature/Component identity A/B，直到 `VBALOAD + 普通宏运行` 真机 PASS。
- 若 `MsiProvide*` 指向 Microsoft VBA Runtime product：先核对该 runtime product 的现有 Feature/Component graph，禁止凭猜测补 Enabler 键。
- 若调用进入 source resolution：优先寻找不需要伪造不存在 `LocalPackage` 的最小 local identity；不要把旧 CMD 的整套 MSI bookkeeping 直接复制进正式 planner。
- 只有 `VBALOAD / VBAIDE / 普通宏运行` 都有真实证据后，才把最小 MSI identity 纳入正式 planner、补测试、repeat install / owned uninstall，再提交下一候选。

## 10. 2026-09-22 主审计者新增静态收敛

正式产品代码仍冻结在 `99981f9`，本轮仅增加诊断工具/证据；再次全量回归仍为 **47 passed**，installer journal 仍为 `complete / conflict_count=0`。

### AcVba 初始化链已独立复核

- `AcVba + 0x12E00`：session initializer。
- session vtable：`AcVba + 0x288C8`。
- `vtable + 0x90` → `AcVba + 0x1C7F0`。
- `vtable + 0x98` → `AcVba + 0x1D9E0`。
- `0x1D9E0` 在 `0x1DE4E` 调 `AcVba + 0x1858`；失败且 locale 不是 `0x409` 时，在 `0x1DE83` 以 `0x409` fallback 再调一次。
- `AcVba + 0x1858` 已确认：优先从 `HKLM\\Software\\Microsoft\\VBA\\Vbe71DllPath` 加载 VBE7，`GetProcAddress("DllVbeInit")`，调用后直接向上传递 HRESULT。

### VBE7!DllVbeInit 又收窄一层

当前机器 `VBE7.DLL!DllVbeInit` export：RVA `0x6BB68`。

它的第一阶段直接调用 `VBE7 + 0x6BA60`。该函数显式可返回：

- `0x80040111 = CLASS_E_CLASSNOTAVAILABLE`
- `0x8007000E = E_OUTOFMEMORY`

其中 `0x80040111` 的精确条件已静态确认：

```text
RDX != 0xFF1CE
AND DWORD[VBE7 + 0x3EC460] != 0
```

`VBE7 + 0x3EC460` 在 DLL 文件初始映像为 `0`。AcVba 当前传入的 DllVbeInit 第 5 参数来自固定 host context（约 `AcVba + 0x28650`），正常不会等于 `0xFF1CE`。

因此如果动态抓到 `0x80040111`，优先解释为 **VBE 内部实例/重入状态**，不要自动归因于缺 COM 注册。

`DllVbeInit` 的第二阶段是在 `0x6BA60` 成功后调用新对象的 `vtable + 0xC8`；因此动态上：

- 若 `0x6BA60 < 0`：第一阶段失败；
- 若 `0x6BA60 == 0` 但 `DllVbeInit < 0`：失败来自对象 `vtable + 0xC8` 初始化。

### 已准备精简动态 tracer

新增：

`tools/trace_acvba_init_returns.py`

Python 语法已验证。它只 attach/记录，不 patch、不改 HRESULT、不 kill 进程，自动等待并 hook：

- `AcVba + 0x12E00`
- `AcVba + 0x1C7F0`
- `AcVba + 0x1D9E0`
- `AcVba + 0x1858`
- `VBE7!DllVbeInit`
- `VBE7 + 0x6BA60`

并记录 `VBE7 + 0x3EC460` 的运行时值。

本地 AI 精简任务文件：

`LOCAL_AI_VBA_DLLVBEINIT_TRACE_TASK.md`

下一步只需要拿到这组**动态 HRESULT**。拿到后再决定最小 A/B；在此之前不要继续扩大 MSI / Forms / Registry 猜测。

## 11. 2026-09-22 MVP-B 正式候选已冻结

前述动态 trace 已完成，最终根因不再是假设：VBE7 初始化首先因 Windows Installer component graph 不完整失败。

已确认真实调用链包含：

- `MsiGetProductCodeA("{5999F473-6855-46D1-8093-B1C463B1DE9B}")`；
- 返回 product `{78E1A395-FD21-499A-91A2-6135BA6112B6}`；
- `MsiProvideComponentA(..., "ProductFiles", "{947E220A-D2BF-4D90-98CB-0941399B9A27}", -2)`；
- `MsiProvideQualifiedComponentA("{3842D06A-0601-4380-AEF5-01E200EF51BA}", "2052", -2)`；
- 后续 VBE7 还真实请求 FM20 component `{6CF249E5-3A41-4320-A66C-AF0A9E58C4F6}`。

在经过严格可回滚的 Product / Feature / Component subset A/B 后，正式 Python planner 已加入最小 VBA MSI identity，同时继续排除：

- SourceList；
- LocalPackage；
- InstallSource；
- Uninstall metadata；
- cached MSI；
- 2052 的 CHM/help component；
- 任何整份 `vba.dli` 导入。

System32 的 `FM20.DLL / FM20chs.DLL / FM20enu.DLL` **仍不由 Python installer 部署或覆盖**。当前机器三者与包内载荷哈希一致；正式 planner 只要求运行所需的 `FM20.DLL` 与 `FM20chs.DLL` 已存在，并发布已被动态证据证明需要的 MSI component identity。

共享 Microsoft VBA 文件采用 `reuse_existing`：已有不同版本时不覆盖、不接管；AcVBA Bundle 仍 strict。

共享 VBA/MSI registry 采用 `preserve_existing`：

- 缺失时创建并进入 ownership journal；
- 首次安装遇到已有不同值时保留、不接管；
- 已由本 installer 拥有的值仍支持后续升级；
- 外部修改后自动释放 ownership，uninstall 不抢回。

### 冻结候选

```text
full SHA: a22f4c33c1415dcb79384646863180bf4249e4f2
short:    a22f4c3
commit:   feat: complete guarded VBA MSI identity
```

冻结时只提交 tracked `src/acad_portable/*` + tracked tests，没有提交大量诊断脚本/DWG。

### 本地主审计门禁

- `python -m pytest -q` → **56 passed**；
- `python -m acad_portable plan --json` → warnings `[]` / audit findings `[]`；
- operations = `11784`；
- 只读 `diff --json`：
  - registry change = `0`；
  - junction conflict = `0`；
  - file conflict = `0`；
  - files = `3 same / 11 reuse / 0 create / 0 conflict`；
  - runtime/external registry changes被分类为 `external_preserved`。

### 耗时 live 验收已剥离

任务文件：

`LOCAL_AI_MVP_B_LIVE_ACCEPTANCE_TASK.md`

测试 AI 必须只测试 `a22f4c33c1415dcb79384646863180bf4249e4f2`，不得修改正式 src/tests。

验收覆盖：

1. upgrade-in-place；
2. `VBASTMT`；
3. Autodesk sample `LoadDVB / UnloadDVB`；
4. standalone 普通宏真实运行；
5. `VBAIDE`；
6. 4 个关键 MSI API 返回 0；
7. repeat install；
8. owned uninstall；
9. fresh install 后完整再验；
10. shared VBA / FM20 前后哈希不变。

在该 live acceptance 返回前，不继续修改正式候选。

## 12. 2026-09-23 live acceptance re-audit：上一轮 BLOCKED 口径已纠正

上一轮证据目录：

`evidence-local/mvp-b-live-acceptance-20260923T005024/`

真实结果：

- candidate lock 正确，正式 `src/tests` 未改；
- upgrade-in-place PASS，`APPLIED 11783`，0 conflict；
- VBASTMT PASS；
- VBAIDE PASS；
- 4 个关键 MSI API 全部 return 0；
- shared VBA/FM20 14/14 hash 不变；
- `cntrline.dvb` / `Menu.dvb` COM LoadDVB+UnloadDVB PASS；
- `VBANEW` 能创建 AutoCAD-native `ACADProject`，标准模块普通宏真实运行 PASS，`USERR1=45.678`；
- `VBE.VBProjects.Add(101/100)` 返回 `0x800A01B8`；该路径不是 AutoCAD-native 创建工程的必要路径。

上一轮被判 BLOCKED 的直接原因是 `drawline.dvb` LoadDVB 失败，但主审计复核正式需求后确认：

- `ACCEPTANCE.md` 的 MVP-B 必选只有 `VBALOAD / VBAIDE / 普通宏`；
- `PYTHON_FUNCTIONAL_REQUIREMENTS.md` 明确 UserForm / Forms 2.0 仅在声明“完整 VBA”时要求；
- 本 HANDOFF 也一直写明“先实现 VBA 基础能力，不默认扩大到 Forms 2.0”。

因此，把含 UserForm 的 `drawline.dvb` 当成基础 MVP-B 必过样例，是上一版 delegated task 的**验收设计错误**；
`VBE.VBProjects.Add(101)` 作为必过门槛同样撤销。旧任务 `LOCAL_AI_MVP_B_LIVE_ACCEPTANCE_TASK.md` 已标记 SUPERSEDED。

### 12.1 Forms2 / UserForm blocker 已静态收敛

对 Autodesk sample 做 CFB/OLE directory 对比：

- 成功的 `cntrline.dvb`、`Menu.dvb`：没有真正 `VBA_Project/<Form>` UserForm storage；
- 失败的 `drawline.dvb`、`txtht.dvb`、`BlockReplace.dvb`、`acad_cg.dvb`：都有 Microsoft Forms UserForm storage。

原始 `vba.dli` 中 FM20 的 64 位 COM 类共 61 个；sample 二进制静态命中：

- `drawline.dvb`：仅 `{C62A69F0-16DC-11CE-9E98-00AA00574A4F}` = Microsoft Forms 2.0 Form；
- `txtht.dvb`：同样仅根 Form；
- `BlockReplace.dvb`：Form + Frame；
- `acad_cg.dvb`：Form + Frame + MultiPage；
- `cntrline.dvb` / `Menu.dvb`：0 个 Forms COM CLSID 命中。

当前系统 Registry64：

- `{C62A69F0-...}` UserForm CLSID：缺失；
- `Forms.Form.1`：缺失；
- Forms TypeLib `...\2.0\0\win64`：缺失；
- `C:\Windows\System32\FM20.DLL`：存在。

Registry32 中上述 Forms 类存在，并指向 `SysWOW64\FM20.DLL`。

原始 `AutoCAD 2024/ACAOE/vba.dli` 则明确包含对应的 **64 位** UserForm/Frame/MultiPage CLSID subtree，
`InprocServer32=C:\Windows\system32\FM20.DLL`、`ThreadingModel=Apartment`；因此 Forms2 64 位 COM 注册缺失是 source-backed 证据，不是猜测。

当前最强假设：基础 VBA 已可用；失败的 UserForm DVB 缺的是 64 位 Forms2 COM runtime registration，而不是 VBA MSI product/component identity。

### 12.2 新的正确收口路径

基础 MVP-B 收口任务：

`LOCAL_AI_MVP_B_CLOSEOUT_TASK.md`

只使用**不含 UserForm**的 Autodesk `cntrline.dvb`，要求真正 `_.-VBALOAD` 后项目出现在 VBE，再验 VBAIDE、VBANEW 普通宏，并继续完成上一轮因错误 fail-fast 被跳过的：

- repeat install；
- owned uninstall；
- fresh install；
- fresh live #2；
- fresh repeat install；
- ownership/shared-file final closure。

Forms2 是独立非阻塞诊断任务：

`LOCAL_AI_FORMS2_USERFORM_AB_TASK.md`

已新增严格可回滚 gate：

`tools/temp_forms2_userform_gate.py`

当前只读 baseline：

```text
FM20 exists=True
CLSID64 present=False
ProgID64 present=False
TypeLibWin64 present=False
```

Forms2 A/B 分层：

1. 仅 UserForm CLSID；
2. CLSID + TypeLib win64 leaf；
3. 只有仍失败才加 `Forms.Form.1` ProgID。

每层必须 strict cleanup；不允许扩大成 61 CLSID / Interfaces / 整份 vba.dli，除非新的运行证据要求。

正式候选 `a22f4c3` 在这轮主审计中仍未修改。

## 13. MVP-B 基础能力最终关闭（2026-09-24）

本章为最终收口章节，只追加结论，不删除前述历史取证内容。

### 13.1 正式范围与冻结候选

MVP-B 的正式范围限定为：

```text
VBALOAD + VBAIDE + AutoCAD-native 普通宏
```

冻结产品候选保持不变：

```text
full SHA: a22f4c33c1415dcb79384646863180bf4249e4f2
commit:   feat: complete guarded VBA MSI identity
```

正式 `src/acad_portable` + `tests` 与该冻结 SHA 完全一致。

### 13.2 最终证据

Corrected closeout evidence 目录：

`evidence-local/mvp-b-closeout-20260923T081612/`

在该目录下完成并通过：

- 两轮真实 `-VBALOAD cntrline.dvb` PASS；两轮 unload 后 project count = 0。
- 两轮 `VBAIDE` PASS。
- 两轮 `VBANEW` + AutoCAD-native 普通宏 PASS；宏实际产生 `USERR1=45.678` 可观察效果，并在运行后恢复。
- 4 个关键 MSI API 全部 return 0。
- repeat install / owned uninstall / fresh install / fresh repeat install 全 PASS，uninstall conflict = 0。
- final diff：registry change = 0、junction conflict = 0、file conflict = 0。
- final state：`complete`，`conflict_count = 0`。
- baseline / final 14 个 shared VBA/FM20 文件按路径 + SHA256 完全一致。

### 13.3 机械证据复核

- Codex 独立重跑 pytest：**56 passed**。
- Pi evidence collection run `mvp-b-evidence-collect-20260924` 状态 COMPLETED，机械确认 SHA / diff / tests / final state / shared hash 证据。
- 最终 PASS 决策由 Codex 独立作出，不由 Pi 采集或本收口文档自行认定。

### 13.4 已知正常交互（非缺陷）

当 `SECURELOAD=1` 且 sample 不在 `TRUSTEDPATHS` 时，`VBALOAD` 会弹出宏启用提示。
这是正常的安全交互，不是安装缺陷。

### 13.5 后续边界

- Forms2 / UserForm 64-bit 注册**仍未纳入**基础 MVP-B；这是后续独立阶段。
- 基础 MVP-B **不宣称** UserForm / Forms2 已支持。
- 基础 MVP-B **不宣称** 含 UserForm 的 `drawline.dvb` 已通过。

