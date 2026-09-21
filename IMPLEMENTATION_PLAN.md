# Implementation Plan

## P0 — 理解与产品边界

状态：**已完成首轮**。

产物：

- `CMD_FUNCTIONAL_SPEC.md`
- `REGISTRY_TEMPLATE_SPEC.md`
- `PAYLOAD_ARCHIVE_SPEC.md`
- `RUNTIME_FEATURE_SPEC.md`
- `PYTHON_FUNCTIONAL_REQUIREMENTS.md`

## P1 — CLI / Package Model

状态：**non-live 完成**。

实现：

- Python package `acad_portable`；
- `status`；
- package discovery；
- 当前包配置读取；
- preflight report。

不做系统写入。

## P2 — Registry parser / rebasing

状态：**non-live 完成**。

实现：

- Windows `.reg/.dli` parser；
- typed values；
- AutoCAD legacy root 识别；
- structured path rebasing；
- root allowlist；
- unresolved legacy path report。

先只输出 plan。

## P3 — Core install plan

状态：**non-live 完成**。

生成：

- AutoCAD HKLM/HKCU core registry operations；
- AppData / LocalAppData Junction operations；
- desktop shortcut operation；
- wizard shortcut operations；
- install-state operation。

要求 Fake Adapter 全部验证通过。

## P4 — Real Windows adapter

状态：**代码 + clean-host live 闭环完成**。

实现最小真实操作：

- registry set/delete-owned；
- directory/Junction；
- shortcut；
- state file。

不得增加 System32 / WebView2 / AcSign 写入。

历史漂移证据继续保留；最终验收已在用户卸载本机旧 CAD 2024 后建立的 clean-host baseline 上重新执行，不再依赖旧 journal。

## P5 — Local non-live acceptance

状态：**完成**。

当前证据：

- 41 passed；
- real package plan **11,559 operations**；
- warnings 0；
- audit findings 0；
- FakeWindows repeat apply 幂等；
- Windows temp Junction / shortcut 实测通过。
- 历史 Trial 1 live apply：redirected Desktop 暴露路径解析缺陷；journal rollback 已实测 0 conflict；该缺陷已修复。
- 后续历史 apply 曾形成 `status=complete`；但当前主机 journal vs live 已有 278 registry value 漂移，其中 267 为 F:→D:，因此“clean pre-live state”不再成立。
- 当前只读状态见 `CURRENT_STATE_AUDIT.md`；不得用旧的 0-overwrite diff 作为现状证据。

- 全量 pytest；
- dry-run plan；
- idempotency；
- historical path leakage 检查；
- no-reg3/regedge/unreg gate。

## P6 — 真机 AutoCAD Core 验证

状态：**完成（clean-host live PASS）**。完整证据见 `LIVE_TRIALS.md` Trial 4/5/6 与 `LIVE_ACCEPTANCE_REPORT.md`。

由本地 AI 只承担无法由当前工具可靠完成的真实 GUI/AutoCAD 操作：

- 执行已审查的 Core install；
- 启动 AutoCAD；
- 验证 image path；
- 验证 CHS/Junction；
- 验证 test LSP 自动加载。

本地 AI 只返回证据，不自行扩大范围。

最终 clean-host 结果：

- fresh install PASS；
- `AcadObject` CLSID 单变量 A/B 找到并修复启动 blocker；
- `acad.exe` 进入 `Drawing1.dwg`；
- COM 命令 PASS；
- autoload marker PASS；
- repeat install PASS；
- owned uninstall 0 conflict。

## P7 — Core 审计收口

状态：**完成**。

PR #2 已完成最终 Core 审计并合并到 `main`：

- final reviewed SHA：`36bafb0`；
- CI：Windows 3.11/3.14 + Ubuntu 3.11/3.14 全部 PASS；
- CodeQL：PASS；
- Sourcery：最终 review 无新 finding；
- Codex：`Didn't find any major issues`；
- merge commit：`23f1075a4e1bbd0cde0ce88e35772adf2b69c4ef`。

MVP-A Core 至此锁定；后续若继续工作，进入 MVP-B / 最小化优化，不再把它们视为 MVP-A blocker。

## P8 — VBA

Core 真机通过后开始。

按 `PYTHON_FUNCTIONAL_REQUIREMENTS.md` 分层实现：

- AcVBA Bundle；
- VBA 7.1 Runtime；
- AcadVBA registry；
- Forms 2.0（若完整 VBA）。

## 明确后置

- WebView2 legacy payload；
- AcSign Shell；
- plot/style CPL System32；
- taskbar pin；
- 制包工具链；
- 完整事务框架。

