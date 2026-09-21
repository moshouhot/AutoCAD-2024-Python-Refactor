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

- [x] 正确解析 `reg1.dli` / `reg2.dli`，包括 `REG_EXPAND_SZ`。
- [x] 只允许预期 HKCU/HKLM AutoCAD roots。
- [x] legacy AutoCAD package paths 能转换为当前 root。
- [x] plan 中不存在旧 package root 残留（独立 plan audit = 0 findings）。
- [x] Core plan 不包含 `reg3.dli` / `regedge.dli` / `vba.dli` / `unreg.dli` 全量导入。
- [x] Core plan 不包含 System32/SysWOW64 写入。
- [x] Core 排除了 HKCU 历史插件状态和 `AcadVBA`，避免尚未部署的 loader 悬空。
- [x] Core 中计划写入的 AutoCAD Application loader 全部有实际目标或明确虚拟协议。

## D. P3 Fake install

- [x] 两个 CHS Junction 指向 `ACAOE/CHS`。
- [x] 普通安装计划不重置当前 CHS。
- [x] desktop shortcut 指向当前 `acad.exe /nologo`，并受配置开关控制。
- [x] wizard shortcut 目标正确。
- [x] auto-load 链路存在且可被静态验证。
- [x] FakeWindows 第二次执行产生完全相同的目标状态。
- [x] non-live ownership journal 已证明 uninstall 只恢复/删除本工具管理的 registry state；外部修改会转为 conflict 而不是覆盖。

## E. Non-live regression

- [x] 当前全量 pytest PASS（31 passed）。
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
- [x] `status` 可只读报告 installer journal；当前真实包状态为 `exists=false`，证明尚未执行 Python live install。
- [x] live diff 为只读：当前 Core 目标 registry `same=0 / change=0 / create=8528 / keys_create=2769`；两个 CHS Junction 均为新建；shortcut 为 2 existing + 1 create。
- [x] Trial 1 真实 apply 在 redirected Desktop 处失败后，journal 回滚实测删除 8528 本轮新值 + 2 Junction，0 conflict，并恢复到执行前 live diff。
- [x] Desktop 解析已修正为 `User Shell Folders` 优先，且 shortcut parent 非目录会在 plan audit 阶段阻断。
- [ ] 真实 Windows `--apply` 尚未执行。

### 当前真实包 non-live 证据

- Core plan operations：**11,554**
- plan warnings：0
- independent audit findings：0
- FakeWindows 两次 apply：幂等（历史已验证）
- Windows read-only preflight：管理员=True，.NET Release=533325，Auto-load=ready

### 当前 live state 更正

当前不能再使用旧的“registry 与 plan 完全一致”结论：

- installer journal：`status=complete`，registry journal **8656**；
- journal vs current registry：**8378 same / 278 changed / 0 missing**；
- 278 changed 中 **267 是明确 F:→D:**；另有 E: 历史用户路径；
- 当前 HKLM `AcadLocation` 指向 D: 的既有 AutoCAD 2024 环境；
- 最新 plan 对当前 live registry：**8375 same / 278 change / 0 create**。

因此当前 live state 只能判为 **DRIFTED / BLOCKED**，不能作为最新 F: Core PASS 证据。详见 `CURRENT_STATE_AUDIT.md`。

## F. MVP-A 真机验收

- [ ] 先取得不受 D:/E: 既有环境回写影响的可信 live baseline。
- [ ] Python Core install 成功。
- [ ] AutoCAD 2024 启动到可操作状态。
- [ ] 运行中 image path 为当前绿色包 `acad.exe`。
- [ ] 关键 AutoCAD 命令可执行。
- [ ] AppData / LocalAppData CHS 均解析到正确目标。
- [ ] 当前 CHS 用户状态未被普通安装 reset。
- [ ] desktop shortcut 可正常启动。
- [ ] `0加载应用程序` 测试 LSP 自动加载成功。
- [ ] 重复 install 可用。
- [ ] Core uninstall 不进行大范围共享状态清理。

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
