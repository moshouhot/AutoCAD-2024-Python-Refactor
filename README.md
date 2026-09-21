# AutoCAD 2024 CMD → Python Refactor

这是一个面向 AutoCAD 2024 绿色版安装逻辑的 **Python 重构与审计项目**。

项目目标不是逐行翻译旧 CMD，也不是追求 CMD 与 Python 的 1:1 副作用一致，而是：

> 先完整理解旧 CMD 及其配套资源承担的实际产品职责，再用 Python 重新实现一个更清晰、可维护、可测试的 MVP。

## 核心原则

- CMD 是**功能发现来源和历史参考实现**，不是绝对正确的产品规范。
- 明显的 CMD bug、偶然副作用、历史兼容垃圾和危险行为不要求复刻。
- MVP 优先：先保证主要功能真正可用，再逐步增强安全、事务和极端异常处理。
- 是否完成，以明确的用户功能和系统状态契约为准，而不是逐命令一致。

完整计划见 [`prd.md`](prd.md)。

## 当前阶段

当前处于 **Phase 1：完整理解 CMD**。

本阶段主要产物：

- [`CMD_FUNCTIONAL_SPEC.md`](CMD_FUNCTIONAL_SPEC.md)：从产品功能角度解释旧 CMD。
- [`REGISTRY_TEMPLATE_SPEC.md`](REGISTRY_TEMPLATE_SPEC.md)：把 `.dli` 注册模板拆成产品职责，而不是整体照搬。
- [`PAYLOAD_ARCHIVE_SPEC.md`](PAYLOAD_ARCHIVE_SPEC.md)：解释旧归档中的真实文件职责和交叉依赖。
- [`RUNTIME_FEATURE_SPEC.md`](RUNTIME_FEATURE_SPEC.md)：把 Junction、CHS、快捷方式、自动加载等运行时职责写成明确契约。
- [`PYTHON_FUNCTIONAL_REQUIREMENTS.md`](PYTHON_FUNCTIONAL_REQUIREMENTS.md)：新的 Python 产品规范，后续实现以此为准。
- [`DESIGN.md`](DESIGN.md)：Python MVP 的实现架构。
- [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)：从 Core CLI 到真机和 VBA 的开发顺序。
- [`ACCEPTANCE.md`](ACCEPTANCE.md)：可观察的验收条件。
- [`AUDIT.md`](AUDIT.md)：第三方审计入口、当前边界和重点问题。
- [`LIVE_ACCEPTANCE.md`](LIVE_ACCEPTANCE.md)：本地 AI/真机操作员的 Core MVP 窄验收流程。

Phase 1 原则上不急着写 Python，先把旧安装器真正做了什么搞清楚。

## 公开仓库边界

本仓库用于第三方代码审计，但**不会重新分发 Autodesk 产品文件或原始安装载荷**。

公开内容包括：

- 我们编写的 Python 源码；
- 测试；
- 设计与需求文档；
- 行为说明和审计结论；
- 必要时的脱敏/摘要证据。

本地参考但不上传的内容包括：

- `AutoCAD 2024/` 产品目录；
- Autodesk / Microsoft 等第三方 DLL、EXE、ARX、压缩载荷；
- 原始绿色版安装资源；
- 其他不应公开再分发的第三方文件。

因此第三方审计应以本仓库中的**需求、实现、测试和可复核证据**为主；对原始安装包的事实性结论，会在文档中记录来源文件、职责和必要的摘要/哈希，而不是上传原文件。

## 审计方式

推荐所有重要开发通过独立分支 / PR 完成，并让第三方审计者重点检查：

1. `CMD_FUNCTIONAL_SPEC.md` 是否存在遗漏或错误理解；
2. `PYTHON_FUNCTIONAL_REQUIREMENTS.md` 的产品取舍是否合理；
3. Python 是否实现了已经批准的功能契约；
4. 测试是否独立于实现，不使用循环论证作为 PASS 依据；
5. 是否出现不必要的危险系统操作。

## 免责声明

本项目不是 Autodesk 官方项目，也不隶属于 Autodesk。

