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

实现：

- Python package `acad_portable`；
- `status`；
- package discovery；
- 当前包配置读取；
- preflight report。

不做系统写入。

## P2 — Registry parser / rebasing

实现：

- Windows `.reg/.dli` parser；
- typed values；
- AutoCAD legacy root 识别；
- structured path rebasing；
- root allowlist；
- unresolved legacy path report。

先只输出 plan。

## P3 — Core install plan

生成：

- AutoCAD HKLM/HKCU core registry operations；
- AppData / LocalAppData Junction operations；
- desktop shortcut operation；
- wizard shortcut operations；
- install-state operation。

要求 Fake Adapter 全部验证通过。

## P4 — Real Windows adapter

实现最小真实操作：

- registry set/delete-owned；
- directory/Junction；
- shortcut；
- state file。

不得增加 System32 / WebView2 / AcSign 写入。

## P5 — Local non-live acceptance

- 全量 pytest；
- dry-run plan；
- idempotency；
- historical path leakage 检查；
- no-reg3/regedge/unreg gate。

## P6 — 真机 AutoCAD Core 验证

由本地 AI 只承担无法由当前工具可靠完成的真实 GUI/AutoCAD 操作：

- 执行已审查的 Core install；
- 启动 AutoCAD；
- 验证 image path；
- 验证 CHS/Junction；
- 验证 test LSP 自动加载。

本地 AI 只返回证据，不自行扩大范围。

## P7 — Core 审计收口

公开 PR + 第三方审计。

修复 Core 问题后锁定 MVP-A。

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

