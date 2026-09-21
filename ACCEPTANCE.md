# Acceptance

## A. Phase 1 / 设计门禁

- [x] CMD 514 行控制结构已拆解。
- [x] 安装/卸载/备份/恢复与制包工具链已分离。
- [x] 7 个 `.dli` 已统计和职责分类。
- [x] 5 个关键归档已只读列目录。
- [x] CHS 当前状态与出厂基线已区分。
- [x] 279 个 AutoCAD Application loader 已做包内覆盖验证；文件型缺失 0。
- [x] Python MVP 产品边界已写入 `PYTHON_FUNCTIONAL_REQUIREMENTS.md`。

## B. P1 Package Model

- [x] 能从项目根发现当前 AutoCAD 包。
- [x] `acad.exe` / ACAOE / CHS / legacy templates 缺失时给出明确错误。
- [x] 能正确读取 GB18030/UTF-16 legacy 输入。
- [x] `status` 不修改系统。

## C. P2 Registry plan

- [x] 正确解析 `reg1.dli` / `reg2.dli` 以及 allowlist 内的 `reg3.dli` Core 候选项，包括 `REG_EXPAND_SZ`。
- [x] 只允许预期 HKCU/HKLM AutoCAD roots。
- [x] legacy AutoCAD package paths 能转换为当前 root。
- [x] plan 中不存在旧 package root 残留（独立 plan audit = 0 findings）。
- [x] Core plan 不包含 `reg3.dli` / `regedge.dli` / `vba.dli` / `unreg.dli` 全量导入。
- [x] `reg3.dli` 只通过显式 Core prefix allowlist 进入 plan；不会把 Windows Installer / EdgeUpdate / Forms / AcSign Shell 整体带入。
- [x] Core plan 不包含 System32/SysWOW64 写入。
- [x] Core 排除了 HKCU 历史插件状态和 `AcadVBA`，避免尚未部署的 loader 悬空。
- [x] Core 中计划写入的 AutoCAD Application loader 全部有实际目标或明确虚拟协议。
- [x] 当前 Core allowlist 已在 clean-host live 环境证明**足以启动和操作 AutoCAD 2024**。
- [ ] `DwgCommon / Drawing Check / Hardcopy / ObjectDBX` 是否每一组都属于“最小必需集合”仍未逐组证明；这是后续最小化问题，不阻断 MVP-A 功能验收。

## D. P3 Fake install

- [x] 两个 CHS Junction 指向 `ACAOE/CHS`。
- [x] 普通安装计划不重置当前 CHS。
- [x] desktop shortcut 指向当前 `acad.exe /nologo`，并受配置开关控制。
- [x] wizard shortcut 目标正确。
- [x] auto-load 链路存在且可被静态验证。
- [x] FakeWindows 第二次执行产生完全相同的目标状态。
- [x] non-live ownership journal 已证明 uninstall 只恢复/删除本工具管理的 registry state；外部修改会转为 conflict 而不是覆盖。

## E. Non-live regression

- [x] 当前全量 pytest PASS（40 passed）。
- [x] 所有 Phase 1 静态分析工具可重复运行。
- [x] GitHub CI：`d74ce5e` 在 Windows 3.11 / 3.14、Ubuntu 3.11 / 3.14 四矩阵全部 PASS（run `35570091621`）。
- [x] GitHub CodeQL：Python analysis PASS（run `35570091637`）。
- [ ] `git status` 只含预期源码/文档变化（提交后复核）。
- [x] 本轮未执行真实 CMD 安装器。
- [x] 本轮未写 System32/SysWOW64。

## E.1 P4 Real Windows Adapter（代码级）

- [x] `install` 默认 dry-run，必须显式 `--apply` 才进入真实执行层。
- [x] 真实 registry adapter 只支持 Core 已审计的 `REG_SZ / REG_EXPAND_SZ / REG_DWORD`。
- [x] 创建 Junction 前对已有/悬空 reparse path fail-closed，不主动删除已有目录。
- [x] shortcut 覆盖前保存原始字节；uninstall 只在当前文件仍等于本工具写入版本时恢复/删除。
- [x] registry 写入前记录原值；重复 install 不覆盖最初 before-state。
- [x] uninstall 遇到安装后外部修改会保留外部值并报告 conflict。
- [x] Windows 临时目录实测：真实 Junction 创建/读取/移除 PASS。
- [x] Windows 临时目录实测：真实 `.lnk` 创建 PASS。
- [x] Windows 临时目录实测：dangling Junction 被识别为已有 reparse path 并 fail-closed。
- [x] `status` 可只读报告 installer journal；最终 clean-host 验收前后均实测。
- [x] 最终候选 fresh install 后 live diff：registry `8656 same / 0 change / 0 create`；2 Junction same；3 shortcut existing。
- [x] Trial 1 真实 apply 在 redirected Desktop 处失败后，journal 回滚实测删除 8528 本轮新值 + 2 Junction，0 conflict，并恢复到执行前 live diff。
- [x] Desktop 解析已修正为 `User Shell Folders` 优先，且 shortcut parent 非目录会在 plan audit 阶段阻断。
- [x] 真实 Windows `install --apply` / repeat install / `uninstall --apply` 已在 clean-host 环境完成闭环。

### 当前真实包 non-live 证据

- Core plan operations：**11,559**
- plan warnings：0
- independent audit findings：0
- FakeWindows 两次 apply：幂等（历史已验证）
- Windows read-only preflight：管理员=True，.NET Release=533325，Auto-load=ready

### 最新 clean-host live 证据

旧 D:/E:/F: 混合状态已经被专用 clean-host 验收取代；历史漂移仍保留在 `CURRENT_STATE_AUDIT.md`，但不再代表当前候选状态。

最终候选 `a46c33b`：

- pytest：**40 passed**；
- plan：**11,559 operations / 0 warnings / 0 audit findings**；
- fresh install：**11,558 actual operations**，0 conflict；
- install 后 diff：**8656 same / 0 change / 0 create**；
- 真机 `acad.exe`：进入 `Autodesk AutoCAD 2024 - [Drawing1.dwg]`；
- image path：当前 F: 项目 `acad.exe`；
- COM 命令：`USERR1 0 -> 12.345 -> 0`；
- autoload：测试 LSP 自动生成 `__mvp_a_autoload_marker.txt`；
- repeat install：PASS，diff 再次归零；
- uninstall：registry restored=1 / removed=8655，shortcuts restored=2 / removed=1，junctions removed=2，**conflicts=0**；
- uninstall 后 `AcadObject` CLSID 与 HKLM R24.3 均不存在，installer state 不存在；
- HKCU 保留的 36 keys / 80 values 为 AutoCAD 运行时及外部 ApplicationPlugins 写入状态，符合 owned-uninstall 契约。

## F. MVP-A 真机验收

- [x] 已取得不受旧 D:/E: CAD 2024 注册状态影响的 clean-host baseline。
- [x] Python Core install 成功。
- [x] AutoCAD 2024 启动到可操作状态（`Drawing1.dwg`）。
- [x] 运行中 image path 为当前绿色包 `acad.exe`。
- [x] 关键 AutoCAD 命令可执行（COM `SETVAR` 实测）。
- [x] AppData / LocalAppData CHS 均由 installer journal 指向当前 `ACAOE/CHS`。
- [x] 普通安装未执行 CHS recovery/reset。
- [ ] desktop shortcut 可正常启动。
- [x] `0加载应用程序` 测试 LSP 自动加载成功。
- [x] 重复 install 可用且恢复 plan 状态。
- [x] Core uninstall 只清理 ownership journal 管理状态，0 conflict；未进行大范围共享状态清理。

## G. VBA（MVP-B）

Core MVP-A 通过之前不进入。

- [ ] `VBALOAD`
- [ ] `VBAIDE`
- [ ] 普通宏执行
- [ ] 若承诺 Forms：UserForm 显示、控件和事件

## 最终状态规则

单元测试 PASS 不等于真机 PASS；真机 PASS 也不等于第三方审计 PASS。

最终交付至少需要：

1. 实现验证；
2. 非 live 回归；
3. 真机功能验收；
4. 独立审计。
